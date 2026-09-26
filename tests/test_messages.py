"""The message bus - the port's NSNotificationCenter / NSNotificationQueue.

Carried over unchanged from the PS1 port: the bus itself is plain plumbing and
PS2's notification centre is the same Foundation class.  What changed in PS2 is
who schedules delayed triggers (the objects themselves - see
test_triggers.py), not the bus.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from papasangre2.core.messages import MessageBus                   # noqa: E402
from papasangre2.core.triggers import addressed_to                 # noqa: E402


class Recorder:
    def __init__(self, bus, name=None):
        self.seen = []
        bus.subscribe(name, self._on)

    def _on(self, name, params):
        self.seen.append((name, dict(params)))

    def names(self):
        return [n for n, _ in self.seen]


# ------------------------------------------------------------- message bus
def test_post_is_immediate_and_enqueue_is_not():
    bus = MessageBus()
    r = Recorder(bus)
    bus.post('A')
    assert r.names() == ['A']
    bus.enqueue('B')
    assert r.names() == ['A']          # not yet
    bus.drain()
    assert r.names() == ['A', 'B']


def test_enqueued_messages_keep_their_order():
    bus = MessageBus()
    r = Recorder(bus)
    for n in 'ABCD':
        bus.enqueue(n)
    bus.drain()
    assert r.names() == list('ABCD')


def test_drain_keeps_going_for_messages_raised_during_the_drain():
    bus = MessageBus()
    r = Recorder(bus)

    def chain(name, params):
        if name == 'A':
            bus.enqueue('B')
        elif name == 'B':
            bus.enqueue('C')

    bus.subscribe(None, chain)
    bus.enqueue('A')
    bus.drain()
    assert r.names() == ['A', 'B', 'C']


def test_delayed_messages_fire_at_their_time():
    bus = MessageBus()
    r = Recorder(bus)
    bus.post_after(1.0, 'LATER')
    bus.update(0.5)
    assert r.names() == []
    bus.update(1.0)
    assert r.names() == ['LATER']


def test_a_delayed_message_is_delivered_directly_not_queued():
    """The two trigger paths do not agree, and the port has to match both.

    -[PGEObjectWithTriggers triggerWithType:] ends an immediate trigger in
    enqueueNotification:postingStyle:NSPostWhenIdle, but a delayed one goes
    through startTriggerAfterDelay:, which ends in postNotificationName:object:.
    So a delayed message overtakes anything already sitting on the queue.
    """
    bus = MessageBus()
    order = []
    bus.subscribe(None, lambda n, p: order.append(n))
    bus.post_after(1.0, 'DELAYED')
    bus.enqueue('QUEUED')
    bus.update(1.0)
    assert order == ['DELAYED', 'QUEUED'], order


def test_delayed_messages_can_be_cancelled():
    bus = MessageBus()
    r = Recorder(bus)
    bus.post_after(1.0, 'LATER', token='t')
    assert bus.cancel('t') == 1
    bus.update(2.0)
    assert r.names() == []


def test_broadcast_reaches_everyone_and_names_are_filtered_by_the_receiver():
    """This is why triggers naming a missing agent quietly do nothing."""
    bus = MessageBus()
    hits = []
    for who in ('door', 'note1'):
        def make(w):
            def h(name, params):
                if addressed_to(params, w):
                    hits.append(w)
            return h
        bus.subscribe('PGE_MESSAGE_ActivateAgentWithName', make(who))
    bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': 'door'})
    bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': 'nobody'})
    assert hits == ['door']
