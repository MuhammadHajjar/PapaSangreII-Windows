"""M8 (ps2_18, 18b, the end): the camera on Papa, "keep moving", unplugging
the headphones, the last shake, the end of the game - each against what the
binary does (docs/notes/M8_NOTES.md)."""

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


def _spy(host):
    fired = []
    host.trigger = lambda t, _o=host.trigger: (fired.append(t), _o(t))[1]
    return fired


def _move_to(sim, x, y):
    sim.bus.post('PGE_MESSAGE_MovePlayerToPosition', {'position': (x, y)})
    sim.step(0.1)


def _face(sim, x, y):
    from papasangre2.autopilot import Autopilot
    Autopilot(sim).face(x, y, rate=math.radians(720))


def _unplug(sim):
    sim.bus.post('PGE_MESSAGE_AudioRouteChanged', {'unplugged': True})
    sim.bus.update(sim.now)


# ------------------------------------------------------------ keep moving
def test_standing_still_on_a_keep_moving_floor_says_keep_moving():
    sim = Sim('ps2_18')
    floor = next(f for f in sim.level.floors if f.name == 'shout_trigger_1')
    assert floor.still_limit == 8.0
    _move_to(sim, -120, -140)
    assert floor.player_is_on_surface
    fired = _spy(floor)
    sim.step(7.5)
    assert 'OnStillLimit' not in fired
    sim.step(1.0)
    assert fired.count('OnStillLimit') == 1
    assert any(x.startswith(('18_SPEECH_keep_moving', '18_SPEECH__keep_moving')) for x in sim.played())
    sim.step(10.0)
    assert fired.count('OnStillLimit') == 1                # once per stand, not again


# -------------------------------------------------------------- the camera
def _papa(sim, name='4_papa_1'):
    papa = sim.level.agent(name)
    sim.bus.post('PGE_MESSAGE_EnableHands', {})
    sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': name})
    sim.run_until(lambda: papa.active and sim.player.right_hand_action == 'beat', limit=10)
    sim.step(3.0)
    return papa


def test_a_picture_of_papa_close_enough():
    sim = Sim('ps2_18')
    papa = _papa(sim)
    _move_to(sim, papa.position[0] - 40, papa.position[1])
    _face(sim, *papa.position)
    assert papa.is_in_beating_range                        # beatRadius 45
    fired = _spy(papa)
    sim.hand('R')
    sim.step(0.1)
    assert 'OnStab' in fired and papa.dead
    assert sim.level.pictures_taken == 1
    assert papa.sound.name.startswith('18_SPEECH_papa_picture_1')
    assert papa.sound.spatialized                          # the hit from his side
    click = [x for x in sim.played() if x.startswith('18_camera_photo_taken')]
    assert click and not sim.bank.sound(click[-1]).spatialized   # the click from yours
    assert sim.tracker.nb_beats == 1


def test_a_picture_from_too_far_sends_papa_away_and_costs_two_beats():
    sim = Sim('ps2_18')
    papa = _papa(sim)
    _move_to(sim, papa.position[0] - 80, papa.position[1])
    _face(sim, *papa.position)
    assert not papa.is_in_beating_range
    fired = _spy(papa)
    player_fired = _spy(sim.player)
    sim.hand('R')
    sim.step(1.5)
    assert 'OnBeatMissed' in fired and 'OnBeatMissed' in player_fired
    assert not papa.active and not papa.dead               # gone, to come back later
    assert any(x.startswith('18_papa_woosh') for x in sim.played())
    # the player's miss sound is the camera (beatSound), and camera_out_of_range
    # posts a PlayerDidBeat of its own: two beats for one wasted picture
    assert any(x.startswith('18_camera_photo_taken') for x in sim.played())
    assert sim.tracker.nb_beats == 2


# ------------------------------------------------------------- headphones
def test_unplugging_fires_the_route_change_once_and_only_when_active():
    sim = Sim('ps2_18b')
    det = sim.level.agent('route_change_detector')
    fired = _spy(det)
    _unplug(sim)
    assert 'OnRouteChange' not in fired                    # not active yet
    sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': 'route_change_detector'})
    sim.step(0.2)
    _unplug(sim)
    assert fired.count('OnRouteChange') == 1 and not det.requires_unplug
    _unplug(sim)
    assert fired.count('OnRouteChange') == 1
    sim.step(1.2)
    assert sim.level.agent('music').active                 # afterDelay=1


# ------------------------------------------------------------ the last shake
def _shake_ready(sim):
    sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': 'instruction_shake'})
    sim.run_until(lambda: sim.level.agent('instruction_shake').active, limit=5)
    whooshes = []
    sim.level.play_whoosh = lambda: whooshes.append(sim.now)
    return whooshes


def test_the_record_takes_sixteen_shakes_each_a_whoosh():
    """The data's `afterCount=7` fired on the eighth; the owner chose 16
    (2026-09-26, from the tester): afterCount=15.  Decision 14's whoosh for
    each shake it counts, the releasing one included, and none after."""
    sim = Sim('ps2_18b')
    whooshes = _shake_ready(sim)
    after = sim.level.agent('after_shake')
    for i in range(15):
        sim.shake()
        sim.step(0.2)
        assert not after.active, i
    sim.shake()
    sim.step(0.3)
    assert after.active
    assert len(whooshes) == 16
    sim.shake()
    assert len(whooshes) == 16


def test_the_end_of_the_game_is_the_adios_screen():
    from papasangre2.autopilot import outcome_of, play_level_18b
    sim = Sim('ps2_18b', seed=1)
    assert play_level_18b(sim) == 'end'
    assert outcome_of(sim) == 'end'
    assert sim.sent('PGE_MESSAGE_ShutDownLevel')
    assert '18b_SPEECH_aftershake' in sim.played()
    assert not sim.sent('PGE_MESSAGE_LoadLevelWithName')


def test_the_adios_menu_is_main_menu_then_quit():
    from papasangre2.shell import adios_menu
    m = adios_menu()
    assert [i.label for i in m.items] == ['Main Menu', 'Quit']
    assert m.items[0].ui_sound() == 'back_button'          # quitButtonTouched:


# ----------------------------------------------------------- achievements
def test_level_18_is_three_pictures_and_no_more():
    t = GameTracker(MessageBus())
    t.nb_beats = 3
    p = InMemoryProgress()
    assert check_achievements_for_level(p, t, 'ps2_18') == 'level_18'
    assert p.game_center_percent('act3') == 100.0
    t.nb_beats = 4
    q = InMemoryProgress()
    assert check_achievements_for_level(q, t, 'ps2_18') is None
    assert q.game_center_percent('act3') == 100.0


# ------------------------------------------------------ whole levels, played
def test_level_18_can_be_finished_with_three_pictures():
    from papasangre2.autopilot import play_level_18
    sim = Sim('ps2_18', seed=1)
    assert play_level_18(sim) == 'won'
    assert sim.level.pictures_taken == 3 and sim.tracker.nb_beats == 3
    assert sim.sent('PGE_MESSAGE_LoadLevelWithName')[-1]['name'] == 'ps2_18b'


def test_the_game_ends_with_its_end_music_and_records_nothing(tmp_path):
    """Through the Game: ps2_18b ends in `PresentAdiosVC` - the Adios screen
    (outcome 'end'), no level loaded, so no win and no achievement check; the
    end music is ps2_18b's own; each counted shake whooshes."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from test_game import GameSim, make_game
    g = make_game(tmp_path)
    g.load('ps2_18b')
    gs = GameSim(g)
    lv = g.level
    assert gs.run_until(lambda: lv.agent('prompt_unplug').active, limit=120)
    g.bus.post('PGE_MESSAGE_AudioRouteChanged', {'unplugged': True})
    assert gs.run_until(lambda: lv.agent('instruction_shake').active, limit=10)
    for _ in range(8):
        g.bus.post('PGE_ACTION_Shake', {})
        gs.step(0.3)
    assert gs.run_until(lambda: g.outcome is not None, limit=120)
    assert g.outcome == ('end', 'ps2_18b', None)
    assert 'ps2_18b_end_music_loop' in gs.played()
    assert gs.played().count('whoosh') == 8
    assert 'ps2_18b_completed' not in g.progress.values
