"""`PGEEnemy` - the mind lice - driven in the simulator, state by state."""

import math
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from papasangre2.entities.enemy import (AGENT_TYPE, Enemy, WAITING,   # noqa: E402
                                        cg_point_from_string)
from papasangre2.sim import Sim                                      # noqa: E402


def louse_level(level='ps2_1', name='louse1'):
    sim = Sim(level, voice_over=True, seed=2)
    louse = sim.level.agent(name)
    return sim, louse


def wake(sim, louse):
    """Activate it and let its intro play out: it ends up still (0)."""
    sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': louse.name})
    assert sim.run_until(lambda: louse.active and louse.state == 0
                         and louse.current_sound == louse.still_sound, limit=30)


def states(sim, louse, until, limit=60.0):
    seen = [louse.state]

    def watch():
        if louse.state != seen[-1]:
            seen.append(louse.state)
        return until()
    sim.run_until(watch, limit=limit)
    return seen


def test_init_defaults_are_the_originals():
    sim, louse = louse_level()
    assert isinstance(louse, Enemy) and louse.agent_type == AGENT_TYPE == 200
    assert louse.patrol_speed == 10.0 and louse.state == 0
    assert louse.chase_speed == 8.0                  # the level's own value
    assert louse.aware_sound == 'mindlouse_aware_SPA'


def test_the_intro_sound_holds_it_in_waiting_until_it_ends():
    sim, louse = louse_level()
    sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': 'louse1'})
    sim.run_until(lambda: louse.state == WAITING, limit=2)
    assert louse.waiting_for_intro and louse.current_sound == 'mindlouse_appear_SPA'
    assert 'mindlouse_appear_SPA' in sim.played()
    assert not sim.sent('PGE_MESSAGE_AgentActivityChanged') or louse.active
    sim.run_until(lambda: not louse.waiting_for_intro, limit=10)
    sim.step(0.1)
    assert louse.state == 0 and 'mindlouse_still_SPA' in sim.played()


def test_alerted_to_a_position_it_goes_there_and_gives_up():
    sim, louse = louse_level()
    wake(sim, louse)
    sim.bus.post('PGE_MESSAGE_PlayerMovedToPosition', {'position': (40.0, 60.0)})
    sim.bus.post('PGE_MESSAGE_AlertAllEnemies', {'to': 'position'})
    assert louse.state == 4
    sim.step(0.05)                       # it takes the spot, then the player moves on
    sim.bus.post('PGE_MESSAGE_PlayerMovedToPosition', {'position': (-150.0, -150.0)})
    seen = states(sim, louse, lambda: len(sim.sent(
        'PGE_MESSAGE_SendAgentToInitialPosition')) > 0, limit=60)
    assert seen[:3] == [WAITING, 5, 6]
    assert seen[3] == WAITING              # while the not-there sound plays
    played = sim.played()
    assert played.index('mindlouse_aware_SPA') < played.index('mindlouse_chase_SPA') \
        < played.index('mindlouse_notthere_SPA')
    # OnPlayerLastPosition -> SendAgentToInitialPosition (ps2_1's data)
    assert sim.sent('PGE_MESSAGE_SendAgentToInitialPosition')
    assert louse.wanted_position == (40.0, 60.0)


def test_it_heads_for_where_the_player_was_at_chase_speed():
    sim, louse = louse_level()
    wake(sim, louse)
    sim.bus.post('PGE_MESSAGE_PlayerMovedToPosition', {'position': (40.0, 60.0)})
    sim.bus.post('PGE_MESSAGE_AlertAllEnemies', {'to': 'position'})
    sim.run_until(lambda: louse.state == 5, limit=10)
    sim.step(0.2)
    assert louse.speed == 8.0
    ox, oy = louse.orientation_vector
    wx, wy = 40.0 - louse.position[0], 60.0 - louse.position[1]
    n = math.hypot(wx, wy)
    assert ox * wx / n + oy * wy / n > 0.99             # pointing at the spot


def test_an_inactive_or_chasing_louse_ignores_alerts():
    sim, louse = louse_level()
    sim.bus.post('PGE_MESSAGE_AlertAllEnemies', {'to': 'position'})
    sim.step(0.2)
    assert louse.state == 0                               # asleep
    wake(sim, louse)
    louse.state = 3
    sim.bus.post('PGE_MESSAGE_AlertAllEnemies', {'to': 'position'})
    assert louse.state == 3


def test_a_radius_limits_who_hears_it():
    sim, louse = louse_level()
    wake(sim, louse)
    sim.bus.post('PGE_MESSAGE_PlayerMovedToPosition', {'position': (-100.0, -100.0)})
    sim.bus.post('PGE_MESSAGE_AlertAllEnemies', {'to': 'position', 'radius': '50'})
    assert louse.state == 0 and louse.within_radius is False
    sim.bus.post('PGE_MESSAGE_PlayerMovedToPosition', {'position': (90.0, 90.0)})
    sim.bus.post('PGE_MESSAGE_AlertAllEnemies', {'to': 'position', 'radius': '50'})
    assert louse.state == 4


def test_to_player_is_a_chase_and_fires_on_chase():
    sim, louse = louse_level()
    wake(sim, louse)
    sim.bus.post('PGE_MESSAGE_AlertAllEnemies', {'to': 'player'})
    assert louse.state == 2
    sim.step(0.01)                                        # triggers are queued
    assert any(p.get('name') == 'violin_thrill'
               for p in sim.sent('PGE_MESSAGE_ActivateAgentWithName'))   # OnChase
    seen = states(sim, louse, lambda: louse.state == 3, limit=10)
    assert seen == [2, WAITING, 3]


def test_an_alert_during_the_intro_is_kept_for_after_it():
    sim, louse = louse_level()
    sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': 'louse1'})
    sim.run_until(lambda: louse.state == WAITING, limit=2)
    louse.state = 2                                       # alerted to the player
    sim.step(0.1)
    assert louse.delayed_alerted
    sim.run_until(lambda: not louse.waiting_for_intro, limit=10)
    assert not louse.delayed_alerted
    sim.run_until(lambda: louse.state == 3, limit=10)
    assert louse.state == 3


def test_touching_the_player_is_an_attack_and_on_collide():
    sim, louse = louse_level()
    wake(sim, louse)
    louse.position = sim.player.position
    sim.step(0.1)
    assert louse.state == 7 and louse.speed == 0.0
    sim.step(0.01)
    assert any(p.get('name') == 'fail_sound'
               for p in sim.sent('PGE_MESSAGE_ActivateAgentWithName'))


def test_sent_home_it_walks_back_and_stops():
    sim, louse = louse_level()
    wake(sim, louse)
    louse.position = (60.0, 40.0)
    sim.bus.post('PGE_MESSAGE_SendAgentToInitialPosition', {'name': 'someone else'})
    assert louse.state == 0
    sim.bus.post('PGE_MESSAGE_SendAgentToInitialPosition', {})      # no name: everyone
    assert louse.state == 9
    sim.run_until(lambda: louse.state == 0, limit=30)
    hx, hy = louse.initial_position
    assert math.hypot(louse.position[0] - hx, louse.position[1] - hy) < 4


def test_pausing_agents_plays_the_pause_sound_where_it_is():
    sim, louse = louse_level()
    wake(sim, louse)
    sim.step(0.2)
    sim.bus.post('PGE_MESSAGE_PauseAgents', {})
    assert louse.paused and louse.pause_s3d is not None
    assert louse.pause_s3d.name == 'mindlouse_still_SPA' and louse.pause_s3d.playing
    assert louse.pause_s3d.looping and louse.pause_s3d.spatialized
    state = louse.state
    sim.step(1.0)
    assert louse.state == state                           # frozen
    sim.bus.post('PGE_MESSAGE_UnpauseAgents', {})
    assert not louse.paused and not louse.pause_s3d.playing
    # the pause sound *is* its still sound - one shared instance, as in the
    # original's playlist - so unpausing stops it; its next update restarts it
    assert louse.pause_s3d is louse.sound
    sim.step(0.1)
    assert louse.sound.playing and louse.sound.looping


def test_unpausing_replays_a_different_sound_from_the_top_unlooped():
    sim, louse = louse_level()
    sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': 'louse1'})
    sim.run_until(lambda: louse.current_sound == 'mindlouse_appear_SPA', limit=2)
    sim.step(0.5)
    sim.bus.post('PGE_MESSAGE_PauseAgents', {})
    assert louse.pause_s3d is not louse.sound
    sim.bus.post('PGE_MESSAGE_UnpauseAgents', {})
    assert louse.sound.playing and not louse.sound.looping and louse.sound.offset == 0.0


def test_is_still_counts_the_waiting_state_and_the_odd_104():
    sim, louse = louse_level()
    for s, want in ((0, True), (6, True), (104, True), (WAITING, True), (1, False), (5, False)):
        louse.state = s
        assert louse.is_still() is want


def test_cg_point_from_string():
    assert cg_point_from_string('{12.5, -3}') == (12.5, -3.0)
    assert cg_point_from_string('nonsense') == (0.0, 0.0)


def test_sent_home_from_home_stays_home():
    """findDirectionTo: has no zero guard in the original (the direction is
    NaN and the enemy is lost); decision 16: it stays where it is."""
    sim, louse = louse_level()
    wake(sim, louse)
    louse.position = louse.initial_position
    sim.bus.post('PGE_MESSAGE_SendAgentToInitialPosition', {})
    sim.step(0.5)
    assert louse.state == 0
    assert louse.position == louse.initial_position
    assert louse.orientation_vector == (0.0, 0.0)


def test_the_shutdown_locks_the_player_out():
    sim, louse = louse_level()
    sim.bus.post('PGE_MESSAGE_ShutDownLevel', {'senderName': 'fail_sound'})
    for name in ('PGE_MESSAGE_DisableHands', 'PGE_MESSAGE_DisableWalk',
                 'PGE_MESSAGE_DisableRotation'):
        assert sim.sent(name), name


@pytest.mark.parametrize('level', ['ps2_1', 'ps2_2', 'ps2_3', 'ps2_4'])
def test_the_museum_levels_can_be_finished(level):
    # The museum autopilot is a simple player: in ps2_4 the louse catches it
    # on about half the seeds, and which ones moves with every random draw
    # the level makes (a footstep take is one).  The level must be winnable.
    from papasangre2.autopilot import play_collect_level
    results = []
    for seed in (1, 2, 3, 4):
        results.append(play_collect_level(Sim(level, voice_over=True, seed=seed)))
        if results[-1] == 'won':
            break
    assert results[-1] == 'won', results


def test_a_louder_line_leaves_a_waiting_memory_playing():
    """Menu level 3 (ps2_2): bumping the third memory's case starts "you need to
    smash this one too" (priority 3).  The memory (priority 2) keeps looping -
    -[PGECollectible soundPriority] is 0 until it is collected."""
    sim = Sim('ps2_2', voice_over=True, seed=1)
    m = sim.level.agent('memory3')
    sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': 'memory3'})
    sim.run_until(lambda: m.sound is not None and m.sound.name == m.loop_sound
                  and m.sound.playing, limit=20)
    loop = m.sound
    assert m.sound_priority == 0 and m._own_priority == 2
    sim.player.position = (m.position[0] - 12.0, m.position[1])
    sim.bus.post('PGE_MESSAGE_PlayerMovedToPosition', {'position': sim.player.position})
    sim.run_until(lambda: sim.level.agent('smash_instructions2').active, limit=5)
    sim.step(1.0)
    assert '2_SPEECH_precollect_3_UOS' in sim.played()
    assert loop.playing and m.sound is loop and not m.collected
