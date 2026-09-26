"""The menus, driven the way a player drives them: move, choose, adjust."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from papasangre2.shell import (level_complete_menu, level_failed_menu,   # noqa: E402
                               level_menu, main_menu, pause_menu, settings_menu)
from papasangre2.util import paths                                       # noqa: E402
from papasangre2.util.settings import Settings                           # noqa: E402


class Progress:
    def __init__(self, unlocked=(), last=None):
        self.unlocked = set(unlocked)
        self.values = {'lastLevelUnlocked': last} if last else {}

    def is_level_unlocked(self, n):
        return n in self.unlocked

    @property
    def last_unlocked_level(self):
        return self.values.get('lastLevelUnlocked') or 'ps2_Intro'


def labels(menu):
    return [i.label for i in menu.items]


def test_main_menu_uses_the_originals_labels():
    m = main_menu(Progress())
    assert labels(m) == ['Start the game', 'Select Level', 'Settings',
                         'Achievements', 'About', 'Check for updates', 'Quit']
    assert m.choose() == ('continue', 'ps2_Intro')


def test_continue_names_the_furthest_level():
    m = main_menu(Progress(['ps2_1'], last='ps2_1'), titles={'ps2_1': 'Mind the Lice'})
    assert m.items[0].label == 'Continue, Mind the Lice'
    assert m.choose() == ('continue', 'ps2_1')


def test_level_list_reads_like_the_accessible_list():
    m = level_menu(paths.game_bundle(), Progress(['ps2_1']))
    ls = labels(m)
    assert ls[0] == 'Play Level 1: You are dead'
    assert ls[1] == 'Play Level 2: Mind the Lice'
    assert ls[2].endswith('; locked') and ls[2].startswith('Level 3: ')
    assert ls[-1] == 'Main menu'
    assert len(ls) == 23                                    # 22 levels + Main menu
    m.move(2)
    assert m.choose()[0] == 'blocked'


def test_settings_switches_flip_and_are_remembered(tmp_path):
    s = Settings(str(tmp_path / 'settings.json'))
    m = settings_menu(s)
    ls = labels(m)
    assert 'Blind intro, on' in ls and 'Skip ping, on' in ls and 'Skip explanation, on' in ls
    m.index = ls.index('Skip ping, on')
    kind, item = m.choose()                     # Enter flips it
    assert kind == 'toggled' and item.label == 'Skip ping, off'
    assert Settings(str(tmp_path / 'settings.json')).skip_ping is False
    assert m.adjust_current(+1) == 'Skip ping, on'   # left/right flips it too


def test_turning_speed_moves_in_steps(tmp_path):
    s = Settings(str(tmp_path / 'settings.json'))
    m = settings_menu(s)
    m.index = 1
    assert m.adjust_current(+1) == 'Turning speed, 135 degrees per second'


def test_pause_reads_the_objective_then_the_buttons():
    m = pause_menu('Collect the fragments of memory.')
    assert m.announce() == 'Pause. Collect the fragments of memory. Continue game.'
    assert labels(m)[:4] == ['Continue game', 'Restart Level', 'Settings', 'Quit game']


def test_the_win_screen_reads_the_success_text_first():
    m = level_complete_menu('ps2_1', "Well done, you've learnt how to see with your ears.")
    assert m.announce().startswith("Level complete. Well done, you've learnt how to see")
    assert labels(m)[:3] == ['Continue', 'Play this again', 'Select Level']
    assert m.choose() == ('next', 'ps2_1')


def test_the_lose_screen_has_no_skip():
    m = level_failed_menu()
    assert m.title == 'You are still dead'
    assert 'Skip this level' not in labels(m)


# ------------------------------------------------ the buttons' UI sounds
def sounds(menu):
    return {i.label: i.ui_sound() for i in menu.items}


def test_main_menu_buttons_click_and_quit_plays_back():
    snd = sounds(main_menu(Progress()))
    assert snd['Select Level'] == snd['Settings'] == snd['Achievements'] == 'click_button'
    assert snd['About'] == snd['Start the game'] == 'click_button'
    assert snd['Quit'] == 'back_button'


def test_escape_on_the_main_menu_does_nothing():
    assert main_menu(Progress()).cancellable is False


def test_choosing_a_level_clicks_and_main_menu_plays_back():
    """AccessibleAllLevelsViewController: didSelectRow plays nothing - the
    click is REQUESTED (the tester, 2026-09-26); userPressedMainMenu plays
    back_button."""
    m = level_menu(paths.game_bundle(), Progress(['ps2_1']))
    assert all(i.ui_sound() == 'click_button' for i in m.items if i.action == 'play')
    assert m.items[-1].ui_sound() == 'back_button'
    assert m.cancel.ui_sound() == 'back_button'


def test_pause_buttons_match_the_original(tmp_path):
    snd = sounds(pause_menu('x'))
    assert snd['Continue game'] == snd['Restart Level'] == snd['Settings'] == 'click_button'
    assert snd['Quit game'] == 'back_button'
    m = pause_menu('x')
    assert (m.cancel.action, m.cancel.ui_sound()) == ('resume', 'click_button')


def test_settings_back_plays_back(tmp_path):
    m = settings_menu(Settings(str(tmp_path / 's.json')))
    assert sounds(m)['Back'] == 'back_button'
    assert m.cancel.ui_sound() == 'back_button'


def test_win_replay_is_silent_but_lose_replay_clicks():
    win = sounds(level_complete_menu('ps2_1'))
    assert win['Continue'] == 'click_button'
    assert win['Play this again'] is None
    assert win['Main Menu'] == 'back_button'
    lose = sounds(level_failed_menu())
    assert lose['Play this again'] == 'click_button'
    assert lose['Main Menu'] == 'back_button'


def test_the_version_is_the_changelogs_newest_heading():
    import re
    from papasangre2 import __version__
    text = open(os.path.join(ROOT, 'changelog.txt'), encoding='utf-8').read()
    heads = re.findall(r'^(\d{4}-\d{2}-\d{2}(?: number \d+)?)$', text, re.M)
    assert heads and heads[0] == __version__
    assert open(os.path.join(ROOT, 'VERSION'), encoding='utf-8').read().strip() == __version__
    # newest first, and a number only where a day has more than one
    days = [h.split(' ')[0] for h in heads]
    assert days == sorted(days, reverse=True)
    for day in set(days):
        same = [h for h in heads if h.startswith(day)]
        assert len(same) == 1 and same[0] == day or all(' number ' in h for h in same), same


def test_about_says_the_version_first():
    from papasangre2.shell import about_menu
    m = about_menu(['Writer\nNeil Bennun'], 'PC word.', '2026-09-26 number 2')
    assert m.items[0].label == 'Version 2026-09-26 number 2'
