"""Dying and winning in the museum: the lose screen's count and narration,
the lost memories, the death atmosphere, and the achievements."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_game import GameSim, make_game                          # noqa: E402

from papasangre2.core.messages import MessageBus                   # noqa: E402
from papasangre2.save.achievements import (check_achievements_for_level,  # noqa: E402
                                           update_stats_and_achievements)
from papasangre2.save.progress import InMemoryProgress             # noqa: E402
from papasangre2.save.tracker import GameTracker                   # noqa: E402
from papasangre2.shell import achievement_text, achievements_menu  # noqa: E402


def game(tmp_path):
    g = make_game(tmp_path)
    g.progress = InMemoryProgress()
    return g


def die_in(g, level='ps2_1', louse='louse1'):
    """Load the level, wake the louse, walk into it; the outcome is set."""
    g.load(level)
    gs = GameSim(g)
    g.update(1.0)
    lv = g.level
    m = lv.agent(louse)
    lv.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': louse})
    gs.run_until(lambda: m.active and m.current_sound == m.still_sound, limit=30)
    m.position = lv.player.position
    gs.run_until(lambda: g.finished, limit=60)
    return gs


def after_screen(g, seconds):
    for _ in range(int(seconds * 100)):
        g.menu_update(0.01)


# --------------------------------------------------------------- dying
def test_a_louse_kills_you_and_the_level_is_lost(tmp_path):
    g = game(tmp_path)
    gs = die_in(g)
    assert g.outcome == ('lose', 'ps2_1', '')
    assert 'louse_death_UOS' in gs.played()
    assert g.progress.values['ps2_1_failed'] == 1


def test_level_1s_narrations_play_in_turn_then_the_lost_memories(tmp_path):
    g = game(tmp_path)
    heard = []
    for _ in range(5):
        die_in(g)
        heard.append(g.atmos_voice_over.name)
    assert heard == ['ps2_1_fail_a', 'ps2_1_fail_b', 'ps2_1_fail_c',
                     'lost_memory_1_UOS', 'lost_memory_2_UOS']
    assert g.progress.values['ps2_1_failed'] == 5
    assert g.progress.memories_lost == 2
    assert g.progress.has_played_level_end_sound('ps2_1_fail_b')


def test_a_level_with_no_narration_loses_a_memory_at_once(tmp_path):
    g = game(tmp_path)
    die_in(g, 'ps2_2', 'forgetfulman1')
    assert g.atmos_voice_over.name == 'lost_memory_1_UOS'


def test_the_memories_run_1_to_25_then_start_again(tmp_path):
    g = game(tmp_path)
    g.progress.memories_lost = 25
    g.load('ps2_2')
    g.play_fail_sound_for_level(2, '', 'ps2_2')
    assert g.progress.memories_lost == 1
    assert g.atmos_voice_over.name == 'lost_memory_1_UOS'


def test_the_death_atmosphere_comes_0_7_s_after_the_narration(tmp_path):
    g = game(tmp_path)
    die_in(g)
    s = g.atmos_voice_over
    started = g.menu_now
    while s.playing:
        g.menu_update(0.01)
    ended = g.menu_now
    assert ended - started >= s.duration - 0.05
    after_screen(g, 0.65)
    assert not any(a.name == 'menu_death_atmos' for a in g.atmos)
    after_screen(g, 0.1)
    atmos = [a for a in g.atmos if a.name == 'menu_death_atmos']
    assert atmos and atmos[0].playing and atmos[0].looping
    after_screen(g, 3.1)
    assert abs(atmos[0].gain - 0.5) < 1e-6                 # faded in over 3 s


def test_dying_locks_the_controls(tmp_path):
    g = game(tmp_path)
    gs = die_in(g)
    for name in ('PGE_MESSAGE_DisableWalk', 'PGE_MESSAGE_DisableHands',
                 'PGE_MESSAGE_DisableRotation'):
        assert gs.sent(name), name


# -------------------------------------------------------- achievements
def tracked(level='ps2_1'):
    bus = MessageBus()
    t = GameTracker(bus)
    return bus, t


class _Level:
    def __init__(self, name):
        self.name = name


def test_the_tracker_counts_and_resets_on_every_load():
    bus, t = tracked()
    bus.post('PGE_MESSAGE_LevelInited', {'level': _Level('ps2_2')})
    for _ in range(3):
        bus.post('PGE_ACTION_HandsClapped', {})
    bus.post('PGE_MESSAGE_PlayerDidTrip', {})
    bus.post('PGE_MESSAGE_PlayerMovedToPosition', {'position': (1.0, 2.0)})
    t.increment_collectibles()
    assert (t.nb_claps, t.nb_trips, t.nb_steps, t.collectibles_collected) == (3, 1, 1, 1)
    assert t.attempt == 1
    bus.post('PGE_MESSAGE_LevelInited', {'level': _Level('ps2_2')})
    assert (t.nb_claps, t.nb_trips, t.nb_steps, t.collectibles_collected) == (0, 0, 0, 0)
    assert t.attempt == 2                                     # the same level again
    bus.post('PGE_MESSAGE_LevelInited', {'level': _Level('ps2_3')})
    assert t.attempt == 1


def test_each_museum_level_has_its_own_test():
    for level, setup, earned in (
        ('ps2_1', dict(), True), ('ps2_1', dict(nb_trips=1), False),
        ('ps2_2', dict(nb_claps=10), True), ('ps2_2', dict(nb_claps=9), False),
        ('ps2_3', dict(collectibles_collected=5), True),
        ('ps2_3', dict(collectibles_collected=4), False),
        ('ps2_4', dict(), True), ('ps2_4', dict(nb_claps=1), False),
    ):
        p = InMemoryProgress()
        _bus, t = tracked()
        for k, v in setup.items():
            setattr(t, k, v)
        got = check_achievements_for_level(p, t, level)
        ident = 'level_' + level[-1]
        assert (got == ident) is earned, (level, setup)
        assert p.achievement_completed(ident) is earned
        act = {'ps2_1': 20, 'ps2_2': 40, 'ps2_3': 60, 'ps2_4': 80}[level]
        assert p.game_center_percent('act1') == act          # earned or not


def test_steps_add_up_across_levels_and_the_odd_divisor():
    p = InMemoryProgress()
    _bus, t = tracked()
    t.nb_steps = 843
    update_stats_and_achievements(p, t)
    update_stats_and_achievements(p, t)
    assert p.total_steps == 1686
    assert abs(p.game_center_percent('10000steps') - 16.86) < 1e-9
    assert abs(p.game_center_percent('1000000steps') - 1686 / 84390 * 100) < 1e-9


def test_an_earned_achievement_stays_earned():
    p = InMemoryProgress()
    p.memories_lost = 24
    assert p.game_center_percent('memoryLost') == 100.0
    p.memories_lost = 1
    assert p.game_center_percent('memoryLost') == 100.0


def test_winning_level_1_without_a_trip_earns_dead_can_dance(tmp_path):
    g = game(tmp_path)
    g.load('ps2_1')
    gs = GameSim(g)
    from papasangre2.autopilot import play_collect_level
    assert play_collect_level(gs) == 'won'
    assert g.outcome[0] == 'win'
    assert g.tracker.nb_trips == 0 and g.earned_achievement == 'level_1'
    text = achievement_text(g.hub['ps2_1'], g.progress)
    assert text == ('Achievement: Dead Can Dance, achieved. You completed the level without '
                    'tripping over your feet.')
    assert g.progress.total_steps > 0


def test_the_win_screen_gives_the_hint_when_it_was_not_earned(tmp_path):
    g = game(tmp_path)
    assert achievement_text(g.hub['ps2_4'], g.progress) == (
        'Achievement: Lifeless Soul of the Party, not achieved. Get out without clapping.')


def test_the_win_screen_keeps_the_achievement_as_a_row(tmp_path):
    from papasangre2.shell.menu import level_complete_menu
    g = game(tmp_path)
    text = achievement_text(g.hub['ps2_4'], g.progress)
    m = level_complete_menu('ps2_5', 'Well done.', text)
    assert [i.label for i in m.items][:2] == ['Continue', text]
    assert m.items[1].action == 'info'


def test_the_achievements_menu_reads_them_all(tmp_path):
    g = game(tmp_path)
    g.progress.set_percentage_for_achievement(100, 'level_2')
    g.progress.submit_achievement('act1', 40.0)
    m = achievements_menu(list(g.hub.values()), g.progress)
    labels = [i.label for i in m.items]
    assert labels[0] == ('Dead Can Dance, not achieved. Complete the level without '
                         'tripping over your feet.')
    assert labels[1].startswith('Standing Ovation, achieved. You clapped 10 times')
    assert 'Exterminating Angel, not achieved. Get all the ducks without wasting a single shot.' in labels
    assert 'Act 1, not achieved, 40 percent' in labels and labels[-1] == 'Main menu'


def test_enter_on_a_game_center_achievement_says_how_to_earn_it(tmp_path):
    from papasangre2.shell.menu import GAME_CENTER_ONLY
    g = game(tmp_path)
    g.progress.submit_achievement('kill25', 100.0)
    m = achievements_menu(list(g.hub.values()), g.progress)
    rows = {i.label.split(',')[0]: i for i in m.items if i.action == 'explain'}
    assert len(rows) == len(GAME_CENTER_ONLY)
    assert m.choose() is not None
    act1 = next(i for i in m.items if i.label.startswith('Act 1,'))
    assert act1.value == ('Finish levels 2 to 6. It goes up as you finish them, and it is '
                          'yours when you finish level 6, Are you being Preserved?')
    assert next(i for i in m.items if i.label.startswith('25 kills')).label == '25 kills, achieved'
    sb = next(i for i in m.items if i.label.startswith('Super bullet')).value
    assert 'Exterminating Angel in level 8' in sb and 'King of the Jungle in level 14' in sb
    assert all(i.value and '?.' not in i.value for i in rows.values())
