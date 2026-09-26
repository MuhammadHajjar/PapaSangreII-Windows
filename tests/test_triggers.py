"""PS2 trigger grammar and firing, against the addresses they were read from.

Several of these deliberately differ from the PS1 port, because PS2's engine
differs: afterCount, malformed statements, the minDelay/maxDelay pair, and
delays that belong to their object instead of the run loop.
"""

import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from papasangre2.assets.tiled import (parse_trigger_statement,           # noqa: E402
                                      parse_triggers, message_name)
from papasangre2.core.messages import MessageBus                        # noqa: E402
from papasangre2.core.triggers import TriggerHost, addressed_to         # noqa: E402


def host_with(obj_type, **props):
    bus = MessageBus()
    h = TriggerHost(bus, name='thing', position=(1.0, -2.5), rng=random.Random(7))
    ts, bad = parse_triggers(obj_type, props)
    h.add_triggers(ts)
    seen = []
    bus.subscribe(None, lambda n, p: seen.append((n, dict(p))))
    return bus, h, seen


# ----------------------------------------------------------------- grammar
def test_statement_with_parameters():
    t = parse_trigger_statement('OnCollide', 'ActivateAgentWithName:name=door;count=1')
    assert t.notification_name == 'ActivateAgentWithName'
    assert t.parameters == {'name': 'door'}
    assert t.count == '1'


def test_min_and_max_delay_are_consumed_not_passed_on():
    t = parse_trigger_statement('OnActivate', 'PlaySound:soundName=x;minDelay=1;maxDelay=3')
    assert t.parameters == {'soundName': 'x'}
    assert (t.min_delay, t.max_delay) == ('1', '3')


def test_more_than_one_colon_keeps_the_first_part_and_no_parameters():
    # 0x10003f340: objectAtIndex:0 - PS1's port kept the whole string instead
    t = parse_trigger_statement('OnActivate', 'ActivateAgentWithName:name=x:afterDelay=2')
    assert t.notification_name == 'ActivateAgentWithName'
    assert t.parameters == {}


def test_a_pair_without_equals_drops_the_whole_statement():
    # 0x10003f448 returns nil; parseTriggersForNames skips it (0x10003ebd0).
    # ps2_11b's forgetfulman: "ActivateAgentWithName:forgetfulman3;afterDelay=3"
    assert parse_trigger_statement('OnShoot', 'ActivateAgentWithName:forgetfulman3;afterDelay=3') is None
    ts, bad = parse_triggers('Monster', {
        'OnShoot': 'ActivateAgentWithName:name=hit;afterDelay=0.3|ActivateAgentWithName:forgetfulman3;afterDelay=3'})
    assert [t.parameters.get('name') for t in ts] == ['hit']
    assert len(bad) == 1


def test_numbered_keys_are_extra_triggers_of_the_same_type():
    ts, _ = parse_triggers('Sound', {'OnActivate': 'A', 'OnActivate_2': 'B'})
    assert [(t.trigger_type, t.notification_name) for t in ts] == [('OnActivate', 'A'), ('OnActivate', 'B')]


def test_a_trigger_name_not_in_the_types_list_is_dropped():
    # Room OnLeftHand, Surface OnSoundEnd and Sound OnXrail are in the data
    assert parse_triggers('Room', {'OnLeftHand': 'X'})[0] == []
    assert parse_triggers('Surface', {'OnSoundEnd': 'X'})[0] == []
    assert parse_triggers('Sound', {'OnXrail': 'X'})[0] == []


def test_message_names_are_normalised():
    assert message_name('PlaySound') == 'PGE_MESSAGE_PlaySound'
    assert message_name('PGE_MESSAGE_PlaySound') == 'PGE_MESSAGE_PlaySound'


# ------------------------------------------------------------------ firing
def test_firing_enqueues_with_sender_and_position():
    bus, h, seen = host_with('Sound', OnActivate='PlaySound:soundName=x')
    assert h.trigger('onactivate') == 1          # case-insensitive
    assert seen == []                            # enqueued, not posted
    bus.drain()
    name, params = seen[0]
    assert name == 'PGE_MESSAGE_PlaySound'
    assert params['soundName'] == 'x' and params['senderName'] == 'thing'
    assert params['position'] == '{1, -2.5}'


def test_count_limits_firing_and_keeps_counting_down():
    bus, h, seen = host_with('Sound', OnActivate='A:count=2')
    fired = [h.trigger('OnActivate') for _ in range(4)]
    assert fired == [1, 1, 0, 0]
    assert h._count[0] == -2                     # decremented every time


def test_aftercount_fires_from_the_n_plus_first_time():
    # 0x1000286c4: held while afterCount >= 1, decremented every time.
    bus, h, seen = host_with('Sound', OnActivate='A:afterCount=2')
    assert [h.trigger('OnActivate') for _ in range(4)] == [0, 0, 1, 1]


def test_count_and_aftercount_both_count_on_every_call():
    bus, h, seen = host_with('Sound', OnActivate='A:count=2;afterCount=1')
    # call 1: count 2>0 ok, after 1 holds -> no.  call 2: count 1>0, after 0 -> fires.
    # call 3: count 0 -> no.
    assert [h.trigger('OnActivate') for _ in range(3)] == [0, 1, 0]


# ------------------------------------------------------------------ delays
def test_after_delay_waits_for_its_owners_updates():
    bus, h, seen = host_with('Sound', OnActivate='A:afterDelay=0.1')
    h.trigger('OnActivate')
    bus.drain()
    assert seen == [] and len(h.delayed) == 1
    h.update_delays(0.05); bus.drain()
    assert seen == []
    h.update_delays(0.05); bus.drain()
    # float32: 0.1 - 0.05 - 0.05 is a hair above or below zero; the original
    # fires only once it is strictly below
    h.update_delays(0.05); bus.drain()
    assert [n for n, _ in seen] == ['PGE_MESSAGE_A']


def test_a_one_second_delay_at_the_twenty_hertz_tick():
    bus, h, seen = host_with('Sound', OnActivate='A:afterDelay=1')
    h.trigger('OnActivate')
    ticks = 0
    while not seen and ticks < 100:
        h.update_delays(0.05)
        bus.drain()
        ticks += 1
    # float32 arithmetic decides whether the 20th or 21st tick crosses zero;
    # whichever it is, it must be the one the original's float arithmetic gives
    import numpy as np
    d = np.float32(1.0)
    expect = 0
    while True:
        d = np.float32(d - np.float32(0.05))
        expect += 1
        if d < 0:
            break
    assert ticks == expect


def test_clearing_cancels_pending_delays():
    bus, h, seen = host_with('Sound', OnActivate='A:afterDelay=0.5')
    h.trigger('OnActivate')
    assert h.clear_delays() == 1
    for _ in range(20):
        h.update_delays(0.05)
    bus.drain()
    assert seen == []


def test_random_delay_needs_both_bounds():
    bus, h, seen = host_with('Sound', OnActivate='A:minDelay=1')
    h.trigger('OnActivate')
    assert h.delayed == []                       # max missing: immediate
    bus.drain()
    assert [n for n, _ in seen] == ['PGE_MESSAGE_A']
    bus, h, seen = host_with('Sound', OnActivate='A:minDelay=1;maxDelay=3')
    h.trigger('OnActivate')
    assert len(h.delayed) == 1 and 1.0 <= float(h.delayed[0].delay) < 3.0


def test_after_delay_wins_over_min_and_max():
    bus, h, seen = host_with('Sound', OnActivate='A:afterDelay=0.2;minDelay=5;maxDelay=6')
    h.trigger('OnActivate')
    assert abs(float(h.delayed[0].delay) - 0.2) < 1e-6


def test_broadcast_names_are_filtered_by_the_receiver():
    assert addressed_to({'name': 'door'}, 'door')
    assert not addressed_to({'name': 'nobody'}, 'door')
    assert not addressed_to({}, 'door')
