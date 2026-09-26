"""The level: its clock, its floors, and who counts delayed triggers down."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from papasangre2.assets.tiled import LevelData, LevelObject, parse_triggers   # noqa: E402
from papasangre2.core.messages import MessageBus                           # noqa: E402
from papasangre2.world.level import Level, PLAYER_TICK, TICK               # noqa: E402


def obj(t, name, props, **kw):
    o = LevelObject(t, None, name, 'L', raw=props, **kw)
    o.triggers, _ = parse_triggers(t, props)
    return o


def level_with(room_props=None, agent_props=None, floors=(), player=True):
    room = obj('Room', 'room', room_props or {})
    data = LevelData('t_1', (-50, -50, 100, 100), (50, 50), room, (1.5, 50, 1))
    if agent_props is not None:
        a = obj('Sound', 'snd', agent_props)
        a.agent_id = 0
        data.agents.append(a)
    for i, (props, rect, z, active) in enumerate(floors):
        f = obj('Surface', 'floor%d' % i, props)
        f.rect, f.z, f.surface_id = rect, z, i + 1
        f.applied.update({k: v for k, v in props.items() if not k.startswith('On')})
        f.applied['active'] = active
        data.floors.append(f)
    if player:
        p = obj('Player', '', {})
        p.x, p.y = 1.5, 1.5
        data.player = p
    bus = MessageBus()
    seen = []
    bus.subscribe(None, lambda n, p: seen.append(n))
    lv = Level(bus, data)
    with bus.scope(lv.scope_key):
        lv.load()
    bus.update(0.0)
    return lv, bus, seen


def test_the_tick_is_a_twentieth_of_a_second_and_the_player_runs_at_half_rate():
    assert TICK == 0.05 and PLAYER_TICK == 0.1
    lv, _, _ = level_with()
    calls = []
    lv.player.update = lambda dt: calls.append(dt)
    for _ in range(6):
        lv.tick()
    assert calls == [0.1, 0.1, 0.1]              # ticks 1, 3, 5


def test_the_level_is_its_own_first_floor_and_ticks_twice():
    # [floorArray addObject:self] in -[PGELevel init], then [self update:] again
    lv, bus, seen = level_with(room_props={'OnEnter': 'Ping:afterDelay=0.2'})
    assert lv.floors[0] is lv
    seen.clear()
    lv.trigger('OnEnter')
    for _ in range(2):                           # 2 ticks = 0.1 s of game time
        lv.tick()
    assert 'PGE_MESSAGE_Ping' not in seen
    lv.tick()                                    # 0.15 s: the room has counted 0.3
    bus.update(0.15)
    assert 'PGE_MESSAGE_Ping' in seen


def test_the_room_gets_on_enter_at_the_spawn_point():
    lv, bus, seen = level_with(room_props={'OnEnter': 'DisableWalk'})
    assert 'PGE_MESSAGE_DisableWalk' in seen
    assert lv.player_is_on_surface


def test_an_inactive_agent_still_counts_its_delays_down():
    lv, bus, seen = level_with(agent_props={'OnActivate': 'Ping:afterDelay=0.1'})
    a = lv.agents[0]
    assert not a.active
    a.trigger('OnActivate')
    for _ in range(4):
        lv.tick()
    bus.update(0.2)
    assert 'PGE_MESSAGE_Ping' in seen


def test_an_inactive_surface_freezes_its_delays():
    lv, bus, seen = level_with(floors=[({'OnEnter': 'Ping:afterDelay=0.1'}, (-10, -10, 5, 5), 5, False)])
    f = lv.floors[1]
    f.trigger('OnEnter')
    for _ in range(10):
        lv.tick()
    bus.update(0.5)
    assert 'PGE_MESSAGE_Ping' not in seen
    f.set_active(True)
    for _ in range(4):
        lv.tick()
    bus.update(0.7)
    assert 'PGE_MESSAGE_Ping' in seen


def test_the_highest_active_floor_wins_and_ties_go_to_the_first():
    lv, _, _ = level_with(floors=[({}, (0, 0, 10, 10), 5, True),
                                  ({}, (0, 0, 10, 10), 5, True),
                                  ({}, (0, 0, 10, 10), 9, False)])
    assert lv.surface_for_position(5, 5) is lv.floors[1]
    lv.floors[3].set_active(True)
    assert lv.surface_for_position(5, 5) is lv.floors[3]
    assert lv.surface_for_position(-20, -20) is lv          # the room itself
    # CGRectContainsPoint: the far edges are outside
    assert lv.surface_for_position(10, 5) is lv


def test_walls_keep_you_in_and_out():
    lv, _, _ = level_with(floors=[({'isWalled': 'YES'}, (10, -5, 10, 10), 5, True)])
    assert not lv.can_player_move_to_position(60, 0)          # outside the room
    assert lv.can_player_move_to_position(5, 0)
    assert not lv.can_player_move_to_position(12, 0)          # into a walled floor
