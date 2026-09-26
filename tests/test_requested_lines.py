"""Decisions 21 and 22 (2026-09-26), from a tester's reports: the lines the
original recorded and never plays, heard; the knife swing on your side; the
shot that hits what is in front of you."""

import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from papasangre2.sim import Sim                                   # noqa: E402


def _face(sim, x, y):
    from papasangre2.autopilot import Autopilot
    Autopilot(sim).face(x, y, rate=math.radians(720))


def _move_to(sim, x, y):
    sim.bus.post('PGE_MESSAGE_MovePlayerToPosition', {'position': (x, y)})
    sim.step(0.1)


def _said(sim, prefix):
    return [x for x in sim.played() if x.startswith(prefix)]


def _hands_on(sim):
    sim.bus.post('PGE_MESSAGE_EnableHands', {})
    sim.bus.post('PGE_MESSAGE_EnableWalk', {})
    sim.step(0.5)


# ------------------------------------------------------------ nothing unheard
def test_every_recorded_line_can_be_heard():
    from unused_speech import unused
    assert unused(with_requested=True) == []
    assert len(unused(with_requested=False)) == 16          # what the original leaves


# ------------------------------------------------------------- the shot
def test_a_sound_in_front_of_the_duck_does_not_take_the_shot():
    sim = Sim('ps2_6')
    sim.run_until(lambda: sim.interpreter.player_can_use_hands, limit=120)
    sim.bus.post('PGE_MESSAGE_ChangeHandAction', {'leftHand': 'shoot'})
    sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': 'duck1'})
    sim.step(1.0)
    duck = sim.level.agent('duck1')
    _face(sim, *duck.position)
    sim.step(1.2)
    p = sim.player
    atmos = next(a for a in sim.level.agents if a.kind == 'sound' and a.active and a.collide_radius > 0)
    ox, oy = p.orientation_vector
    atmos.position = (p.position[0] + 6 * ox, p.position[1] + 6 * oy)   # right in front
    sim.step(0.2)
    assert sim.hand('L')
    sim.step(0.1)
    assert duck.dead


def test_a_monster_behind_you_is_never_shot():
    sim = Sim('ps2_6')
    sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': 'duck1'})
    sim.step(1.0)
    duck = sim.level.agent('duck1')
    _face(sim, *duck.position)
    sim.step(0.5)
    p = sim.player
    ox, oy = p.orientation_vector
    duck.position = (p.position[0] - 40 * ox, p.position[1] - 40 * oy)   # behind
    duck.is_in_shooting_range = True             # what a stale list would believe
    if duck not in p.agents_in_shooting_range:
        p.agents_in_shooting_range.append(duck)
    p.shoot()
    sim.step(0.1)
    assert not duck.dead


def test_a_bear_missed_while_moving_can_be_shot_when_still():
    sim = Sim('ps2_15')
    bear = sim.level.agent('forgetfulman1')
    sim.run_until(lambda: bear.active, limit=60)
    sim.step(3.0)
    _move_to(sim, bear.position[0] - 60, bear.position[1])
    _face(sim, *bear.position)
    p = sim.player
    bear.state = 3
    p.shoot()
    assert not bear.dead                         # invincible while moving
    bear.state = 0
    p.shoot()
    assert bear.dead                             # the original had dropped it


def test_the_nearest_is_the_nearest_even_with_a_penguin_about():
    sim = Sim('ps2_17')
    p = sim.player
    for name in ('penguin', 'forgetfulman1'):
        sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': name})
    sim.run_until(lambda: sim.level.agent('penguin').active and sim.level.agent('forgetfulman1').active,
                  limit=20)
    pen, bear = sim.level.agent('penguin'), sim.level.agent('forgetfulman1')
    ox, oy = p.orientation_vector
    if (ox, oy) == (0.0, 0.0):
        _face(sim, p.position[0] + 10, p.position[1])
        ox, oy = p.orientation_vector
    pen.position = (p.position[0] + 90 * ox, p.position[1] + 90 * oy)
    bear.position = (p.position[0] + 30 * ox, p.position[1] + 30 * oy)
    assert p.shot_targets()[:2] == [bear, pen]


# ---------------------------------------------------- the knife and the hands
def test_waving_the_knife_about_draws_a_line():
    sim = Sim('ps2_15')
    _hands_on(sim)
    p = sim.player
    assert p.right_hand_action == 'beat'
    _face(sim, p.position[0], p.position[1] - 100)          # at nothing
    for i in range(4):
        assert not _said(sim, '15_SPEECH_prompt_stop_slashing'), i
        sim.hand('R')
        sim.step(1.0)
    assert _said(sim, '15_SPEECH_prompt_stop_slashing')


def test_waving_the_hands_left_and_right_draws_a_line_and_the_same_hand_does_not():
    sim = Sim('ps2_1')
    _hands_on(sim)
    for h in 'LLLLLL':
        sim.hand(h)
        sim.step(0.6)
    assert not _said(sim, '1_SPEECH_prompt_hands')
    for i, h in enumerate('LRLRLR'):
        assert not _said(sim, '1_SPEECH_prompt_hands'), i
        sim.hand(h)
        sim.step(0.6)
    first = _said(sim, '1_SPEECH_prompt_hands')
    assert len(first) == 1
    sim.step(8.0)                                           # it has finished
    for h in 'LRLRLR':
        sim.hand(h)
        sim.step(0.6)
    again = _said(sim, '1_SPEECH_prompt_hands')
    assert len(again) == 2 and again[1] != again[0]          # another take


def test_the_original_third_press_line_is_gone_in_level_1():
    sim = Sim('ps2_1')
    _hands_on(sim)
    sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': 'hand_detector'})
    sim.step(0.5)
    for h in 'LLL':
        sim.hand(h)
        sim.step(0.6)
    assert not sim.level.agent('hand_prompt').active


# ------------------------------------------------------ walls and trips
def test_the_trip_line_is_heard_twice_in_each_of_the_first_two_levels():
    sim = Sim('ps2_1')
    sim.progress.trip_times = 7                              # earlier levels' trips
    p = sim.player
    for i in range(3):
        n = len(_said(sim, 'global_warning_trip'))
        p.trip()
        sim.step(4.0)
        assert len(_said(sim, 'global_warning_trip')) == n + (1 if i < 2 else 0), i


def test_no_trip_or_wall_line_after_level_two():
    # the tester heard them in every level and asked for them up to level 2
    sim = Sim('ps2_2')
    p = sim.player
    p.trip()
    sim.step(4.0)
    p.player_did_collide_a_wall(None)
    sim.step(4.0)
    assert not _said(sim, 'global_warning_trip') and not _said(sim, 'global_warning_hitwall')


# ---------------------------------------------------------- the idle hints
def test_standing_still_draws_the_level_hint_and_a_step_resets_it():
    sim = Sim('ps2_1')
    assert sim.run_until(lambda: sim.interpreter.player_can_use_hands, limit=120)
    sim.clap()                                               # "if you can hear me, clap"
    assert sim.run_until(lambda: sim.interpreter.player_can_walk, limit=120)
    sim.step(20.0)
    sim.foot('L')
    sim.step(20.0)
    assert not _said(sim, '1_SPEECH_hint')
    assert sim.run_until(lambda: bool(_said(sim, '1_SPEECH_hint')), limit=60)


def test_no_hint_while_you_cannot_walk():
    sim = Sim('ps2_1')
    sim.bus.post('PGE_MESSAGE_DisableWalk', {})
    sim.step(60.0)
    assert not _said(sim, '1_SPEECH_hint')


def test_the_levels_without_hints_get_theirs():
    assert Sim('ps2_9').level.inactivity_sounds == ['9_SPEECH_hint']
    assert Sim('ps2_10').level.inactivity_sounds == ['10_SPEECH_hint']
    assert Sim('ps2_14').level.inactivity_sounds == []       # its data named level 7's
    s = Sim('ps2_18')
    assert s.level.inactivity_sounds == ['11b_SPEECH_hint_shooting']
    assert s.bank.sound('11b_SPEECH_hint_shooting') is not None


# ---------------------------------------------------------- level lines
def test_the_burning_walls_warn_again_in_level_14():
    sim = Sim('ps2_14')
    _move_to(sim, -150, 20)                                   # a warning3 floor
    sim.step(0.3)
    assert _said(sim, '14_SPEECH__warning_short')


def test_quick_move_after_smashing_a_memory_in_level_16():
    sim = Sim('ps2_16')
    _hands_on(sim)
    sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': 'memory1'})
    m = sim.level.agent('memory1')
    sim.run_until(lambda: m.active, limit=10)
    _move_to(sim, m.position[0] - 10, m.position[1])
    sim.step(1.0)
    sim.hand('L')
    sim.step(0.5)
    assert not _said(sim, '16_SPEECH_oncollect_1')
    sim.step(1.0)
    assert _said(sim, '16_SPEECH_oncollect_1')


def test_other_takes_join_their_lines():
    assert '18_SPEECH__keep_moving' in Sim('ps2_18').level.agent('keep_moving').sounds
    assert '14_SPEECH_smash_it_UOS' in Sim('ps2_14').level.agent('use_extinguisher_to_collect_2').sounds


def test_face_the_music_is_asked_again_in_the_intro():
    sim = Sim('ps2_Intro')
    sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': 'intro1a'})
    a = sim.level.agent('intro1a')
    sim.run_until(lambda: a.active and a.sound is not None, limit=5)
    sim.step(a.sound.duration + 9.0)
    assert _said(sim, 'INTRO_SPEECH_training_1a_prompt')


def test_facing_the_music_in_time_asks_nothing():
    sim = Sim('ps2_Intro')
    sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': 'intro1a'})
    a = sim.level.agent('intro1a')
    sim.run_until(lambda: a.active and a.sound is not None, limit=5)
    sim.step(a.sound.duration + 1.0)
    sim.level.agent('memory1active').trigger('OnEnteringShootRange')
    sim.step(12.0)
    assert not _said(sim, 'INTRO_SPEECH_training_1a_prompt')


def test_keep_going_once_in_the_turn():
    sim = Sim('ps2_Intro')
    for name in ('see_fountain_prompt', 'see_gramophone_prompt'):
        sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': name})
        sim.step(12.0)
    assert len(_said(sim, 'INTRO_SPEECH_training_thats_it')) == 1


def test_pull_yourself_out_if_you_stay_in_the_hole():
    sim = Sim('ps2_7')
    sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': 'floor_fall_warning'})
    w = sim.level.agent('floor_fall_warning')
    sim.run_until(lambda: w.active and w.sound is not None, limit=5)
    sim.step(w.sound.duration + 3.0)
    assert not _said(sim, '7_SPEECH_prompt_pull_yourself_out')
    sim.step(3.0)
    assert _said(sim, '7_SPEECH_prompt_pull_yourself_out')


def test_no_pull_prompt_once_you_climb():
    sim = Sim('ps2_7')
    _hands_on(sim)
    sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': 'floor_fall_warning'})
    w = sim.level.agent('floor_fall_warning')
    sim.run_until(lambda: w.active and w.sound is not None, limit=5)
    sim.step(w.sound.duration + 1.0)
    sim.hand('L')
    sim.step(8.0)
    assert not _said(sim, '7_SPEECH_prompt_pull_yourself_out')
