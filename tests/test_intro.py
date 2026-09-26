"""ps2_Intro, played in the simulator with the real level data and real sound
durations: the whole level, the Blind intro variant, skipping, walking,
tripping and walls."""

import math
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from papasangre2.autopilot import Autopilot, play_intro           # noqa: E402
from papasangre2.sim import Sim                                    # noqa: E402


@pytest.fixture(scope='module')
def full_blind():
    s = Sim('ps2_Intro', voice_over=True, seed=3)
    return s, play_intro(s)


@pytest.fixture(scope='module')
def full_sighted():
    s = Sim('ps2_Intro', voice_over=False, seed=3)
    return s, play_intro(s)


def test_the_intro_can_be_played_to_the_end(full_blind):
    s, lines = full_blind
    assert lines[-1].endswith('LoadLevelWithName ps2_1')
    played = s.played()
    for i in range(1, 6):
        # a collectible that has finished deactivates, and -[PGECollectible
        # deactivate] clears `collected`; its collect sound is the record
        assert s.level.agent('memory%d' % i).collect_sound in played
    assert s.level.collectibles_collected >= 5


def test_the_door_ends_the_level_with_shut_down_first(full_blind):
    s, _ = full_blind
    names = [n for _, n, _ in s.messages]
    i = names.index('PGE_MESSAGE_ShutDownLevel')
    assert names.index('PGE_MESSAGE_LoadLevelWithName') > i


def test_the_blind_intro_plays_the_voiceover_lines(full_blind, full_sighted):
    blind = {n for n in full_blind[0].played() if n.startswith('blind_')}
    assert blind == {'blind_ps2_skip_tuto', 'blind_INTRO_SPEECH_training_0_SPA_UOS',
                     'blind_INTRO_SPEECH_bird_flock_SPA_UOS'}
    sighted = full_sighted[0].played()
    assert not any(n.startswith('blind_') for n in sighted)
    assert 'ps2_skip_tuto' in sighted
    assert 'INTRO_SPEECH_training_0_SPA_UOS' in sighted


def test_footsteps_are_named_by_speed_and_ground(full_blind):
    steps = [n for n in full_blind[0].played() if n.startswith('foot')]
    grounds = ('gravel', 'wetter_stone', 'squelch_gravel')
    assert steps and all(n.split('_', 1)[0] in ('footwalk', 'footrun') and
                         n.split('_', 1)[1].startswith(grounds) for n in steps)
    # updateBPMCounter divides by the number of steps, not of gaps, so the
    # original's first steps read fast and used the running bank; REQUESTED
    # (the tester, 2026-09-26), they walk until three steps are known.  A
    # steady 150 a minute walks throughout.
    assert steps[1].startswith('footwalk') and steps[2].startswith('footwalk')
    assert steps[-1].startswith('footwalk')


def test_the_opening_locks_everything_until_the_record_player_says_so():
    s = Sim('ps2_Intro')
    s.step(1.0)
    mi = s.interpreter
    assert not (mi.player_can_walk or mi.player_can_rotate or mi.player_can_use_hands)
    assert not s.foot('L')
    assert not s.turn(0.1)


def test_a_step_glides_you_five_pixels_at_twenty_five_a_second():
    s = Sim('ps2_Intro')
    s.bus.post('PGE_MESSAGE_EnableWalk', {})
    start = s.player.position
    assert s.foot('L')
    assert s.player.position == start               # the step itself does not move you
    s.step(0.1)
    moved = math.dist(start, s.player.position)
    assert abs(moved - 2.5) < 1e-6                  # 25 px/s for one 0.1 s player update
    s.step(0.5)
    assert abs(math.dist(start, s.player.position) - 5.0) < 1e-6


def test_the_same_foot_twice_does_nothing_for_two_seconds():
    s = Sim('ps2_Intro')
    s.bus.post('PGE_MESSAGE_EnableWalk', {})
    assert s.foot('L')
    s.step(0.5)
    assert not s.foot('L')
    s.step(1.6)
    assert s.foot('L')                              # past 2.0 s the foot is free again


def test_hurrying_trips_you_and_the_record_player_warns_you():
    s = Sim('ps2_Intro')
    s.bus.post('PGE_MESSAGE_EnableWalk', {})
    for i in range(12):
        s.foot('L' if i % 2 == 0 else 'R')
        s.step(0.18)                                # ~330 steps a minute: over the room's 280
        if s.player.state == 3:
            break
    assert s.player.state == 3
    assert s.progress.trip_times == 1
    assert any('global_warning_trip' in n for n in s.played())
    s.step(2.1)
    assert s.player.state == 0                      # back up after two seconds


def test_walking_into_the_edge_of_the_world_is_a_wall():
    s = Sim('ps2_Intro')
    s.bus.post('PGE_MESSAGE_EnableWalk', {})
    s.bus.post('PGE_MESSAGE_EnableRotation', {})
    ap = Autopilot(s)
    ap.face(s.player.position[0], 10_000)           # straight north, to the room's edge
    for _ in range(200):
        ap.step_once()
        if s.progress.wall_times:
            break
    assert s.progress.wall_times >= 1
    assert any(n.startswith('hitwall') for n in s.played())


def test_skipping_a_skippable_line_takes_its_skip_branch():
    s = Sim('ps2_Intro')
    ap = Autopilot(s)
    ap.wait_for(lambda: ap.active('skip_tuto') and s.level.agent('skip_tuto').sound is not None, limit=5)
    # skip_tuto is not skippable: the skip input does nothing to it
    s.step(1.0)
    s.skip()
    assert s.level.agent('skip_tuto').sound.playing
    # Intro0 is skippable; its OnSkip brings in Intro0a without bird_flock
    ap.wait_for(lambda: ap.active('Intro0') and s.level.agent('Intro0').sound is not None
                and s.level.agent('Intro0').sound.playing, limit=200)
    s.step(1.0)
    s.skip()
    ap.wait_for(lambda: ap.active('Intro0a'), limit=5)
    assert ap.active('Intro0a')
    assert 'INTRO_bird_flock_UOS' not in s.played()
