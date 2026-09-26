"""M6 (ps2_11a, 11b, 13, 12): the player on a path (the train), agents freed
from a level, the zoo's animals, the water pistol, the level 11b-13
achievements - each against what the binary does (docs/notes/M6_NOTES.md)."""

import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from papasangre2.core.messages import MessageBus                 # noqa: E402
from papasangre2.save.achievements import check_achievements_for_level  # noqa: E402
from papasangre2.save.progress import InMemoryProgress           # noqa: E402
from papasangre2.save.tracker import GameTracker                 # noqa: E402
from papasangre2.sim import Sim                                   # noqa: E402


def loads(sim):
    return sim.sent('PGE_MESSAGE_LoadLevelWithName')


# ------------------------------------------------------------- the train
def _on_the_train(sim):
    """Board it as a player does: onto the waiting train (its OnCollide)."""
    start = sim.level.agent('train_start')
    sim.run_until(lambda: start.active, limit=30)
    sim.bus.post('PGE_MESSAGE_MovePlayerToPosition', {'position': start.position})
    sim.run_until(lambda: sim.player.has_path, limit=2)
    return sim.player


def test_the_train_carries_you_at_its_path_speed():
    sim = Sim('ps2_12')
    p = _on_the_train(sim)
    assert p.has_path and p.path_speed == 30.0
    y0 = p.position[1]
    sim.step(10.0)
    assert abs((p.position[1] - y0) - 300.0) < 8.0             # 30 px/s, up the track


def test_the_train_moves_every_other_update():
    """railUpdate: two player updates (0.2 s) per move, each twice the step."""
    sim = Sim('ps2_12')
    p = _on_the_train(sim)
    ys = []
    for _ in range(8):
        sim.step(0.05)
        ys.append(p.position[1])
    moves = [b - a for a, b in zip(ys, ys[1:]) if b != a]
    assert moves and all(abs(m - 6.0) < 0.5 for m in moves)    # 2 x 0.1 s x 30 px/s
    assert len(moves) in (1, 2)


def test_the_path_end_fires_when_the_last_point_becomes_the_target():
    sim = Sim('ps2_12')
    p = _on_the_train(sim)
    fired = []
    p.trigger = lambda t, _o=p.trigger: (fired.append(t), _o(t))[1]
    p.position = (p.wanted_patrol_point[0], p.wanted_patrol_point[1] - 1.0)
    sim.step(0.5)
    assert 'OnPathEnd' in fired and p.path_current_point == 0
    assert p.wanted_patrol_point == (-28.0, -1932.0) or p.wanted_patrol_point[1] < 0


def test_shutting_the_level_stops_the_train_and_your_facing():
    sim = Sim('ps2_12')
    p = _on_the_train(sim)
    sim.step(1.0)
    sim.bus.post('PGE_MESSAGE_ShutDownLevel', {})
    pos = p.position
    sim.step(1.0)
    assert not p.has_path and p.position == pos
    assert p.orientation_vector == (0.0, 0.0) and p.next_step_position == pos


def test_another_agents_stop_does_not_stop_the_train():
    sim = Sim('ps2_12')
    p = _on_the_train(sim)
    sim.bus.post('PGE_MESSAGE_StopFollowingPath', {'senderName': 'beacon'})
    assert p.has_path
    sim.bus.post('PGE_MESSAGE_StopFollowingPath', {})
    assert not p.has_path


# -------------------------------------------------------- freeing agents
def test_a_freed_agent_is_silenced_and_gone():
    sim = Sim('ps2_11b')
    a = sim.level.agent('animal_13')
    sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': 'animal_13'})
    sim.step(0.5)
    sim.bus.post('PGE_MESSAGE_DeallocAgentWithName', {'name': 'animal_13'})
    assert a not in sim.level.agents
    assert not a.active and (a.sound is None or not a.sound.playing)
    sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': 'animal_13'})
    sim.step(0.5)
    assert not a.active                                     # it hears nothing more


# ------------------------------------------------------------- the zoo
def test_an_animal_already_calling_is_not_played_twice():
    sim = Sim('ps2_11b')
    a, b = sim.level.agent('animal_13'), sim.level.agent('animal_14')
    s = sim.bank.sound('randomAnimal_owl_a')
    sim.bank.any_sound_with_prefix = lambda prefix: s
    sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': 'animal_13'})
    sim.step(0.2)
    assert a.sound is s and s.playing
    fired = []
    b.trigger = lambda t, _o=b.trigger: (fired.append(t), _o(t))[1]
    sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': 'animal_14'})
    sim.step(0.2)
    assert 'OnSoundEnd' in fired and b.sound is None


# -------------------------------------------------------- the water pistol
def test_the_water_pistol_soaks_a_forgotten_man_and_alerts_the_rest():
    from papasangre2.autopilot import Autopilot
    sim = Sim('ps2_11b')
    mi = sim.interpreter
    sim.run_until(lambda: mi.player_can_use_hands, limit=120)
    fm = sim.level.agent('forgetfulman_a')
    sim.run_until(lambda: fm.active, limit=10)
    ap = Autopilot(sim)
    ap.face(*fm.position, rate=math.radians(360))
    sim.run_until(lambda: fm.is_in_shooting_range, limit=5)
    sim.step(1.1)
    ap.face(*fm.position, rate=math.radians(360))
    n = len(sim.sent('PGE_MESSAGE_AlertAllEnemies'))
    assert sim.hand('L')
    sim.step(0.1)
    assert 'water_pistol' in ''.join(sim.played())
    assert len(sim.sent('PGE_MESSAGE_AlertAllEnemies')) > n  # the player's OnShoot
    assert fm.dead and sim.sent('PGE_MESSAGE_AgentDidDie')


# ----------------------------------------------------------- achievements
def _tracker(**kw):
    t = GameTracker(MessageBus())
    for k, v in kw.items():
        setattr(t, k, v)
    return t


def test_level_11b_is_over_20_soaked_without_a_miss():
    p = InMemoryProgress()
    t = _tracker(nb_enemies_killed=21, nb_shoots=21)
    assert check_achievements_for_level(p, t, 'ps2_11b') == 'level_11b'
    assert p.game_center_percent('superBullet') == 34.0
    assert p.game_center_percent('act2') == 100.0
    for k, s in ((20, 20), (21, 22)):
        assert check_achievements_for_level(InMemoryProgress(),
                                            _tracker(nb_enemies_killed=k, nb_shoots=s),
                                            'ps2_11b') is None


def test_level_12_is_over_19_ducks_without_a_miss():
    p = InMemoryProgress()
    assert check_achievements_for_level(p, _tracker(nb_enemies_killed=20, nb_shoots=20),
                                        'ps2_12') == 'level_12'
    assert p.game_center_percent('act3') == 15.0
    assert check_achievements_for_level(InMemoryProgress(),
                                        _tracker(nb_enemies_killed=19, nb_shoots=19),
                                        'ps2_12') is None


def test_level_13_is_all_13_collectibles():
    p = InMemoryProgress()
    assert check_achievements_for_level(p, _tracker(collectibles_collected=13),
                                        'ps2_13') == 'level_13'
    assert p.game_center_percent('act3') == 30.0
    assert check_achievements_for_level(InMemoryProgress(), _tracker(collectibles_collected=12),
                                        'ps2_13') is None


# ------------------------------------------------------ whole levels, played
def test_level_11a_can_be_finished():
    from papasangre2.autopilot import play_level_11a
    assert play_level_11a(Sim('ps2_11a', seed=1)) == 'won'


def test_level_11b_can_be_finished_soaking_the_forgotten_men():
    from papasangre2.autopilot import play_level_11b
    sim = Sim('ps2_11b', seed=1)
    assert play_level_11b(sim) == 'won'
    assert sim.sent('PGE_MESSAGE_AgentDidDie')


def test_level_13_can_be_finished_under_the_sea():
    from papasangre2.autopilot import play_level_13
    assert play_level_13(Sim('ps2_13', seed=1)) == 'won'


def test_level_12_can_be_finished_on_the_train():
    from papasangre2.autopilot import play_level_12
    sim = Sim('ps2_12', seed=1)
    assert play_level_12(sim) == 'won'
    assert sim.sent('PGE_MESSAGE_MakePlayerFollowPathWithName')
