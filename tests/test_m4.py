"""M4 (ps2_5, 5a, 6, 7): lethal floors, drowning, the air rifle, holding the
phone, the level 5-7 achievements - each against what the binary does
(docs/notes/M4_NOTES.md)."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from papasangre2.autopilot import Autopilot                      # noqa: E402
from papasangre2.save.achievements import check_achievements_for_level  # noqa: E402
from papasangre2.save.progress import InMemoryProgress           # noqa: E402
from papasangre2.save.tracker import GameTracker                 # noqa: E402
from papasangre2.core.messages import MessageBus                 # noqa: E402
from papasangre2.sim import Sim                                   # noqa: E402


def loads(sim):
    return sim.sent('PGE_MESSAGE_LoadLevelWithName')


def floor(sim, name):
    return next(f for f in sim.level.floors if f.name == name)


def move(sim, x, y):
    sim.bus.post('PGE_MESSAGE_MovePlayerToPosition', {'position': (float(x), float(y))})
    sim.step(0.1)


# ---------------------------------------------------------------- floors
def test_walking_into_a_pool_kills_with_its_death_sound():
    sim = Sim('ps2_5')
    sim.step(0.5)
    sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': 'surface1'})
    sim.step(0.1)
    pool = floor(sim, 'surface1')
    assert pool.spatial_sound.name == '5_object_bubble_1_SPA' and pool.spatial_sound.looping
    move(sim, -40, -60)
    assert pool.killed
    assert pool.lethal_sound.name.startswith('5_death_bottomless_water')
    assert not pool.spatial_sound.playing                   # its bubbles stop
    assert not loads(sim)                                   # not until the death sound ends
    sim.run_until(lambda: loads(sim), limit=30)
    assert loads(sim)[-1] == {'name': 'ps2_5', 'deathCause': 'surface'}
    assert sim.sent('PGE_MESSAGE_ShutDownLevel')


def test_a_pools_sound_sits_at_its_nearest_edge_to_you():
    """computeNewPlayerPosition: the rectangle inset by 15 px, clamped."""
    sim = Sim('ps2_5')
    sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': 'surface1'})
    sim.step(0.1)
    pool = floor(sim, 'surface1')                           # (-90, -78) 96 x 38
    rx, ry, rw, rh = pool.rect
    move(sim, rx - 50, ry - 50)
    assert pool.spatial_sound.planar[:2] == (rx + 15, ry + 15)
    move(sim, rx + rw + 50, ry + 20)
    assert pool.spatial_sound.planar[:2] == (rx + rw - 15, ry + 20)


def test_a_roof_that_falls_on_you_kills_with_its_own_cause():
    sim = Sim('ps2_7')
    sim.step(0.5)
    trap = floor(sim, 'trigger1')
    move(sim, 80, -160)
    assert trap.player_is_on_surface and not trap.killed
    sim.bus.post('PGE_MESSAGE_SetLethalForSurfaceWithName', {'name': 'trigger1', 'value': 'YES'})
    assert trap.killed
    sim.run_until(lambda: loads(sim), limit=30)
    assert loads(sim)[-1] == {'name': 'ps2_7', 'deathCause': 'ceiling'}


def test_a_lethal_switch_elsewhere_is_harmless():
    sim = Sim('ps2_7')
    sim.step(0.5)
    sim.bus.post('PGE_MESSAGE_SetLethalForSurfaceWithName', {'name': 'trigger1', 'value': 'YES'})
    sim.step(1.0)
    assert floor(sim, 'trigger1').is_lethal and not floor(sim, 'trigger1').killed


def test_pause_agents_holds_the_fires_but_not_the_unpausable_one():
    sim = Sim('ps2_7')
    for n in ('surface1', 'surface2'):
        sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': n})
    sim.step(0.1)
    s1, s2 = floor(sim, 'surface1'), floor(sim, 'surface2')    # surface2 is unpausable
    sim.bus.post('PGE_MESSAGE_PauseAgents', {})
    assert s1.paused and s1.spatial_sound.paused
    assert not s2.paused and s2.spatial_sound.playing
    sim.bus.post('PGE_MESSAGE_UnpauseAgents', {})
    assert s1.spatial_sound.playing


def test_a_fire_put_out_while_paused_stays_out():
    """unpauseAgents resumes - play rate 1 - which does not restart a sound
    that deactivate stopped in the meantime."""
    sim = Sim('ps2_7')
    sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': 'surface1'})
    sim.step(0.1)
    s1 = floor(sim, 'surface1')
    fire = s1.spatial_sound
    sim.bus.post('PGE_MESSAGE_PauseAgents', {})
    sim.bus.post('PGE_MESSAGE_DeactivateAgentWithName', {'name': 'surface1'})
    sim.bus.post('PGE_MESSAGE_UnpauseAgents', {})
    sim.step(0.2)
    assert not fire.playing


# ------------------------------------------------------------ underwater
def test_the_smoke_chokes_then_drowns():
    sim = Sim('ps2_7')
    sim.step(0.5)
    p = sim.player
    move(sim, -80, -120)                                    # smoke_surface
    assert p.is_underwater
    start = sim.now
    sim.run_until(lambda: p.gagging, limit=30)
    assert 14.8 < sim.now - start < 15.1                    # 3/4 of 20 s (from the step in)
    assert p.gagging_s3d.name == '7_coughing' and p.gagging_s3d.looping
    assert sim.sent('PGE_MESSAGE_ActivateAgentWithName')[-1]['name'] == 'violin_thrill'  # OnGagging
    sim.run_until(lambda: p.drowning, limit=30)
    assert 19.8 < sim.now - start < 20.1
    assert p.gagging_s3d.name.startswith('7_coughing_to_death')
    sim.run_until(lambda: loads(sim), limit=60)
    assert loads(sim)[-1] == {'name': 'ps2_7', 'deathCause': 'drown'}


def test_leaving_the_smoke_resets_the_clock():
    sim = Sim('ps2_7')
    sim.step(0.5)
    p = sim.player
    move(sim, -80, -120)
    sim.run_until(lambda: p.gagging, limit=30)
    move(sim, 0, -250)                                      # the room: not underwater
    assert not p.gagging and p.underwater_duration == 0.0
    assert not p.is_underwater


# ------------------------------------------------------------- the rifle
def _range(sim):
    mi = sim.interpreter
    sim.run_until(lambda: mi.player_can_use_hands, limit=120)
    sim.bus.post('PGE_MESSAGE_ChangeHandAction', {'leftHand': 'shoot'})
    return Autopilot(sim)


def test_the_rifle_kills_the_nearest_duck_in_the_cone():
    sim = Sim('ps2_6')
    ap = _range(sim)
    sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': 'duck1'})
    sim.step(1.0)
    d = sim.level.agent('duck1')
    ap.face(*d.position)
    sim.step(1.2)
    assert d in sim.player.agents_in_shooting_range
    assert sim.hand('L')
    sim.step(0.1)
    assert d.dead and d not in sim.player.agents_in_shooting_range
    names = sim.played()
    assert 'gunshot' in names and any(n.startswith('duck_hit_SPA') for n in names)
    assert sim.progress.total_kills == 1
    assert sim.sent('PGE_MESSAGE_AgentDidDie') and sim.sent('PGE_MESSAGE_PlayerDidShoot')
    sim.run_until(lambda: sim.level.agent('hit1').active, limit=3)   # OnShoot, 0.9 s
    sim.run_until(lambda: not d.active, limit=5)            # the hit sound ends
    assert not d.active


def test_a_shot_at_nothing_is_a_shot_all_the_same():
    sim = Sim('ps2_6')
    ap = _range(sim)
    ap.face(sim.player.position[0], sim.player.position[1] - 100)   # at nobody
    sim.step(1.2)
    sim.player.agents_in_shooting_range.clear()
    assert sim.hand('L')
    assert len(sim.sent('PGE_MESSAGE_PlayerDidShoot')) == 1
    assert sim.progress.total_kills == 0


def test_the_rifle_needs_its_reload_time():
    sim = Sim('ps2_6')
    _range(sim)
    sim.step(1.2)
    assert sim.hand('L')
    sim.step(0.5)                                           # reloadTime 1.0
    sim.hand('L')
    assert len(sim.sent('PGE_MESSAGE_PlayerDidShoot')) == 1


# -------------------------------------------------------------- the phone
def _hold_it_up(sim):
    for n in ('phone_vibrate', 'picture_portrait'):
        sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': n})
    sim.step(0.1)


def test_held_flat_nothing_happens():
    sim = Sim('ps2_5a')
    _hold_it_up(sim)
    sim.step(3.0)
    assert not sim.level.agent('phone_vibrate').active
    assert not sim.level.agent('picture_portrait').active


def test_held_upright_he_complains_0_8_s_later():
    sim = Sim('ps2_5a')
    _hold_it_up(sim)
    sim.rotate('portrait')
    pp = sim.level.agent('picture_portrait')
    sim.step(0.7)
    assert not pp.active
    sim.step(0.2)
    assert pp.active and not sim.level.agent('phone_vibrate').active


def test_held_sideways_the_phone_vibrates():
    sim = Sim('ps2_5a')
    _hold_it_up(sim)
    sim.rotate('landscape')
    pv = sim.level.agent('phone_vibrate')
    sim.run_until(lambda: pv.active, limit=1.0)
    assert pv.active
    sim.step(2.0)
    assert len(sim.sent('PGE_MESSAGE_Vibrate')) == 3        # 0.2, 1.2 and 1.7 s


def test_an_agent_asking_later_hears_how_it_is_held_already():
    """CheckDeviceRotation: the next accelerometer sample says it again."""
    sim = Sim('ps2_5a')
    sim.rotate('landscape')
    _hold_it_up(sim)
    sim.run_until(lambda: sim.level.agent('phone_vibrate').active, limit=1.0)
    assert sim.level.agent('phone_vibrate').active


# ------------------------------------------------------------------ rails
def test_a_sound_on_the_x_rail_moves_with_you_sideways():
    sim = Sim('ps2_7')
    beam = sim.level.agent('beam1')                         # onXrail
    sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': 'beam1'})
    sim.step(0.2)
    x0, y0 = beam.position
    px, py = sim.player.position
    move(sim, px + 7, py + 3)
    assert beam.position == (x0 + 7, y0)


# ----------------------------------------------------------- achievements
def _tracker(**kw):
    t = GameTracker(MessageBus())
    for k, v in kw.items():
        setattr(t, k, v)
    return t


def test_level_5_is_90_seconds_or_less():
    p = InMemoryProgress()
    assert check_achievements_for_level(p, _tracker(time_elapsed=90.0), 'ps2_5') == 'level_5'
    p = InMemoryProgress()
    assert check_achievements_for_level(p, _tracker(time_elapsed=90.05), 'ps2_5') is None
    assert p.game_center_percent('act1') == 100.0


def test_level_6_is_every_shot_a_kill_under_22():
    p = InMemoryProgress()
    t = _tracker(nb_shoots=18, nb_enemies_killed=18)
    assert check_achievements_for_level(p, t, 'ps2_6') == 'level_6'
    assert p.game_center_percent('superBullet') == 33.0
    assert p.game_center_percent('act2') == 15.0
    p = InMemoryProgress()
    assert check_achievements_for_level(p, _tracker(nb_shoots=19, nb_enemies_killed=18),
                                        'ps2_6') is None
    assert check_achievements_for_level(p, _tracker(nb_shoots=22, nb_enemies_killed=22),
                                        'ps2_6') is None


def test_level_7_is_140_seconds_or_less():
    p = InMemoryProgress()
    assert check_achievements_for_level(p, _tracker(time_elapsed=139.9), 'ps2_7') == 'level_7'
    assert p.game_center_percent('act2') == 30.0


def test_the_level_clock_counts_every_tick():
    sim = Sim('ps2_5')
    t = GameTracker(sim.bus)
    sim.level.tracker = t
    sim.step(2.0)
    assert abs(t.time_elapsed - 2.0) < 0.06


def test_kills_report_the_kill_achievements():
    p = InMemoryProgress()
    p.total_kills = 5
    assert p.game_center_percent('kill25') == 20.0
    assert p.game_center_percent('kil100') == 5.0
    assert p.game_center_percent('kill500') == 1.0


# ------------------------------------------------------ whole levels, played
def test_level_5_can_be_finished_round_the_pools():
    from papasangre2.autopilot import play_level_5
    for seed in (1, 2):
        assert play_level_5(Sim('ps2_5', seed=seed)) == 'won'


def test_level_5a_can_be_finished_holding_the_phone_sideways():
    from papasangre2.autopilot import play_level_5a
    assert play_level_5a(Sim('ps2_5a', seed=1)) == 'won'


def test_level_5a_scolds_you_for_holding_it_upright_first():
    from papasangre2.autopilot import play_level_5a
    sim = Sim('ps2_5a', seed=1)
    orig = sim.rotate

    def upright_then_sideways(o):
        orig('portrait')
        sim.run_until(lambda: sim.level.agent('picture_portrait').active, limit=2)
        orig(o)
    sim.rotate = upright_then_sideways
    assert play_level_5a(sim) == 'won'
    assert '5a_SPEECH_portrait_alert_SPA_UOS' in sim.played()


def test_level_6_can_be_finished_shooting_every_duck():
    from papasangre2.autopilot import play_level_6
    sim = Sim('ps2_6', seed=1)
    assert play_level_6(sim) == 'won'
    assert len(sim.sent('PGE_MESSAGE_AgentDidDie')) == 18     # 7 ducks and 11 evil ones


def test_level_7_can_be_finished_following_the_cat():
    from papasangre2.autopilot import play_level_7
    for seed in (1, 2):
        sim = Sim('ps2_7', seed=seed)
        assert play_level_7(sim) == 'won'
        assert sim.played().count('7_floor_escape_PRE') == 2     # out of both holes


def test_the_shake_memory_can_be_shaken_from_any_side_of_papa():
    """Decision 13: reaching Papa from his north-east used to leave you 11 px
    out of the shake memory's 10 px reach with your feet locked."""
    import math
    from papasangre2.autopilot import go_to
    sim = Sim('ps2_5a', seed=1)
    ap = Autopilot(sim)
    mi, lv = sim.interpreter, sim.level
    come = lv.agent('introA_come_here_prompt')
    ap.wait_for(lambda: mi.player_can_walk and come.active, limit=120)
    cx, cy = come.position
    go_to(ap, cx + 30 * math.cos(math.radians(330)), cy + 30 * math.sin(math.radians(330)),
          within=4, until=lambda: come.in_collide_range or not come.active)
    go_to(ap, cx, cy, until=lambda: come.in_collide_range or not come.active)
    ap.wait_for(lambda: lv.agent('hold_it_up_prompt').active, limit=120)
    sim.rotate('landscape')
    shake = lv.agent('intro2_collectible')
    ap.wait_for(lambda: shake.active, limit=120)
    sim.step(1.0)
    px, py = sim.player.position
    assert math.hypot(px - shake.position[0], py - shake.position[1]) > 10    # the trap spot
    for _ in range(7):                          # decision 14: seven shakes
        sim.shake()
    assert shake.collected
