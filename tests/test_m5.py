"""M5 (ps2_8, 9, 10): the penguin and the ice, the submarine's steam, pebbles
over the abyss - each against what the binary does (docs/notes/M5_NOTES.md)."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from papasangre2.autopilot import Autopilot                      # noqa: E402
from papasangre2.core.messages import MessageBus                 # noqa: E402
from papasangre2.save.achievements import check_achievements_for_level  # noqa: E402
from papasangre2.save.progress import InMemoryProgress           # noqa: E402
from papasangre2.save.tracker import GameTracker                 # noqa: E402
from papasangre2.sim import Sim                                   # noqa: E402


def loads(sim):
    return sim.sent('PGE_MESSAGE_LoadLevelWithName')


def floor(sim, name):
    return next(f for f in sim.level.floors if f.name == name)


def move(sim, x, y):
    sim.bus.post('PGE_MESSAGE_MovePlayerToPosition', {'position': (float(x), float(y))})
    sim.step(0.1)


def _penguin(sim):
    mi = sim.interpreter
    sim.run_until(lambda: mi.player_can_walk, limit=60)
    p = sim.level.agent('penguin')
    sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': 'penguin'})
    return p


# ------------------------------------------------------------ the penguin
def test_the_penguin_waddles_up_and_stops_close():
    sim = Sim('ps2_8')
    p = _penguin(sim)
    start = sim.player.position
    d0 = Autopilot(sim).distance_to(*p.position)
    sim.run_until(lambda: p.state == 202, limit=60)
    assert p.state == 202 and p.speed == 0.0
    assert Autopilot(sim).distance_to(*p.position) < min(d0, 30.0)
    assert sim.player.position == start
    assert sim.sent('PGE_MESSAGE_FollowerIsClose')
    assert p.sound.name == 'penguin_proximity_SPA' and p.collide_radius == 50.0
    sim.run_until(lambda: sim.level.agent('penguin_close').active, limit=1)   # OnProximity
    assert sim.level.agent('penguin_close').active


def test_a_clap_sends_a_close_penguin_away_for_three_seconds():
    sim = Sim('ps2_8')
    p = _penguin(sim)
    sim.run_until(lambda: p.state == 202, limit=60)
    sim.step(0.3)
    sim.clap()
    sim.step(0.1)
    assert p.state == 203 and p.move_away_time == 3.0
    sim.step(0.5)
    assert p.sound.name == 'penguin_scared_SPA'
    before = Autopilot(sim).distance_to(*p.position)
    sim.step(1.0)
    assert Autopilot(sim).distance_to(*p.position) > before           # going away
    sim.run_until(lambda: p.state == 201, limit=5)
    assert p.state == 201


def test_a_clap_does_nothing_to_a_penguin_that_is_not_close():
    sim = Sim('ps2_8')
    p = _penguin(sim)
    sim.step(0.3)
    assert p.state == 201
    sim.clap()
    sim.step(0.1)
    assert p.state == 201


def test_the_ice_gives_under_you_and_a_close_penguin():
    sim = Sim('ps2_8')
    p = _penguin(sim)
    sim.run_until(lambda: p.state == 202, limit=60)
    t = sim.now
    sim.run_until(lambda: '8_alert_ice_thin' in sim.played(), limit=1)
    sim.run_until(lambda: loads(sim), limit=30)
    assert loads(sim)[-1] == {'name': 'ps2_8', 'deathCause': 'surface'}
    assert any(n.startswith('ice_death') for n in sim.played())
    assert sim.now - t > 5.0                                # followerTime 5


def test_the_penguins_clock_resets_once_it_is_far():
    sim = Sim('ps2_8')
    p = _penguin(sim)
    sim.run_until(lambda: p.state == 202, limit=60)
    sim.step(3.0)
    ice = next(f for f in sim.level.floors if f.follower_time == 5.0)
    assert ice.follower_timer > 2.5
    move(sim, sim.player.position[0], sim.player.position[1] + 120)
    sim.step(0.5)
    assert ice.follower_timer == 0.0


# -------------------------------------------------------------- the steam
def test_a_vent_starts_safe_and_blows_a_moment_later():
    """setSafeTime: the safe timer starts 0.1 s short of the safe time."""
    sim = Sim('ps2_9')
    zone = floor(sim, 'death_zone_1')
    sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': 'death_zone_1'})
    sim.step(0.05)
    assert not zone.is_lethal
    sim.step(0.2)
    assert zone.is_lethal
    assert sim.level.agent('steam1_on').active or \
        any(n == 'PGE_MESSAGE_ActivateAgentWithName' and p.get('name') == 'steam1_on'
            for _, n, p in sim.messages)


def test_a_vent_cycles_deadly_then_safe():
    sim = Sim('ps2_9')
    zone = floor(sim, 'death_zone_1')                       # deadly 1.8, safe 4.0
    sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': 'death_zone_1'})
    sim.run_until(lambda: zone.is_lethal, limit=1)
    t = sim.now
    sim.run_until(lambda: not zone.is_lethal, limit=5)
    assert 1.75 < sim.now - t < 1.95
    t = sim.now
    sim.run_until(lambda: zone.is_lethal, limit=6)
    assert 3.95 < sim.now - t < 4.15


def test_standing_in_the_steam_when_it_blows_kills():
    sim = Sim('ps2_9')
    sim.step(0.5)
    zone = floor(sim, 'death_zone_1')
    sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': 'death_zone_1'})
    move(sim, -30, -352)
    sim.run_until(lambda: loads(sim), limit=20)
    assert zone.killed
    assert loads(sim)[-1] == {'name': 'ps2_9', 'deathCause': 'surface'}


def test_the_trapped_man_is_freed_with_the_left_hand():
    sim = Sim('ps2_9')
    mi = sim.interpreter
    sim.run_until(lambda: mi.player_can_use_hands, limit=60)
    man = sim.level.agent('man_trapped')
    sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': 'man_trapped'})
    move(sim, man.position[0], man.position[1] - 20)
    sim.run_until(lambda: man.in_collide_range, limit=2)
    assert sim.hand('L')
    sim.run_until(lambda: sim.level.agent('man_released').active, limit=2)
    assert not man.active and not floor(sim, 'walled_room').active


# --------------------------------------------------------------- pebbles
def _at_the_edge(sim):
    mi = sim.interpreter
    sim.run_until(lambda: mi.player_can_use_hands, limit=60)
    move(sim, 198, -83)                                     # 6 px from the abyss
    return Autopilot(sim)


def test_a_pebble_over_the_edge_falls_into_the_abyss():
    sim = Sim('ps2_10')
    ap = _at_the_edge(sim)
    ap.face(260, -83)
    sim.step(1.0)
    n = len(sim.played())
    assert sim.hand('R')
    sim.step(1.5)
    assert sim.played()[n:][0] == 'throw_abyss'
    assert sim.level.agent('first_throw_over_prompt').active     # OnPebble, 1 s later
    assert len(sim.sent('PGE_MESSAGE_PlayerDidThrow')) == 1


def test_a_pebble_on_the_path_lands_on_stone():
    sim = Sim('ps2_10')
    ap = _at_the_edge(sim)
    ap.face(100, -83)
    sim.step(1.0)
    n = len(sim.played())
    assert sim.hand('R')
    sim.step(1.5)
    assert sim.played()[n:][0].startswith('throw_gravel')
    assert not sim.level.agent('first_throw_over_prompt').active


# ----------------------------------------------------------- achievements
def _tracker(**kw):
    t = GameTracker(MessageBus())
    for k, v in kw.items():
        setattr(t, k, v)
    return t


def test_level_8_is_no_claps_at_all():
    p = InMemoryProgress()
    assert check_achievements_for_level(p, _tracker(nb_claps=0), 'ps2_8') == 'level_8'
    assert check_achievements_for_level(InMemoryProgress(), _tracker(nb_claps=1), 'ps2_8') is None
    assert p.game_center_percent('act2') == 45.0


def test_level_9_is_130_seconds_or_less():
    p = InMemoryProgress()
    assert check_achievements_for_level(p, _tracker(time_elapsed=130.0), 'ps2_9') == 'level_9'
    assert check_achievements_for_level(InMemoryProgress(), _tracker(time_elapsed=130.1),
                                        'ps2_9') is None
    assert p.game_center_percent('act2') == 60.0


def test_level_10_is_under_21_throws():
    p = InMemoryProgress()
    assert check_achievements_for_level(p, _tracker(nb_throws=20), 'ps2_10') == 'level_10'
    assert check_achievements_for_level(InMemoryProgress(), _tracker(nb_throws=21),
                                        'ps2_10') is None
    assert p.game_center_percent('act2') == 75.0


def test_a_penguins_death_counts_as_a_kill():
    bus = MessageBus()
    t = GameTracker(bus)
    bus.post('PGE_MESSAGE_FollowerDidDie', {})
    assert t.nb_enemies_killed == 1


# ------------------------------------------------------ whole levels, played
def test_level_8_can_be_finished_clapping_the_penguin_away():
    from papasangre2.autopilot import play_level_8
    sim = Sim('ps2_8', seed=1)
    assert play_level_8(sim) == 'won'
    assert sim.sent('PGE_MESSAGE_SendAgentAwayFromPlayer')


def test_level_9_can_be_finished_timing_the_steam():
    from papasangre2.autopilot import play_level_9
    for seed in (1, 2):
        assert play_level_9(Sim('ps2_9', seed=seed)) == 'won'


def test_level_10_can_be_finished_across_the_abyss():
    from papasangre2.autopilot import play_level_10
    sim = Sim('ps2_10', seed=1)
    assert play_level_10(sim) == 'won'
    assert sim.level.agent('picture').collected or '10_SPEECH_picture_found_UOS' in sim.played()
