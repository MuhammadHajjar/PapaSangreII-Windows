"""The game's own menu loop, driven by scripted key presses: which UI sound
each button asks for, and what Escape does on each screen."""

import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from papasangre2.input.keymap import Action                      # noqa: E402
from papasangre2.shell import (level_complete_menu, level_menu,  # noqa: E402
                               main_menu, pause_menu)
from papasangre2.util import paths                              # noqa: E402

_spec = importlib.util.spec_from_file_location('ps2_play', os.path.join(ROOT, 'apps', 'play.py'))
play = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(play)


class Rep:
    def __init__(self):
        self.said = []

    def say(self, text, interrupt=True):
        self.said.append(text)

    def show(self, text):
        pass


class Src:
    quit_requested = False


class StubApp:
    """Just what run_menu touches: speech, input frames, UI sounds."""

    def __init__(self, keys):
        self.rep = Rep()
        self.src = Src()
        self.frames = [[(k.value, 'down', 0.0)] for k in keys]
        self.sounds = []

    def pump(self):
        if not self.frames:
            self.src.quit_requested = True
            return []
        return self.frames.pop(0)

    def ui(self, name):
        self.sounds.append(name)


class Progress:
    def __init__(self, unlocked=()):
        self.unlocked = set(unlocked)
        self.values = {}

    def is_level_unlocked(self, n):
        return n in self.unlocked

    @property
    def last_unlocked_level(self):
        return 'ps2_Intro'


A = Action


def run(menu, keys):
    app = StubApp(keys)
    return play.run_menu(app, menu), app.sounds


def test_select_level_clicks():
    got, snd = run(main_menu(Progress()), [A.MENU_DOWN, A.CONFIRM])
    assert got == ('levels', None) and snd == ['click_button']


def test_quit_on_the_main_menu_plays_back():
    got, snd = run(main_menu(Progress()), [A.MENU_UP, A.CONFIRM])
    assert got == ('quit', None) and snd == ['back_button']


def test_escape_on_the_main_menu_is_ignored():
    got, snd = run(main_menu(Progress()), [A.CANCEL, A.MENU_DOWN, A.CONFIRM])
    assert got == ('levels', None) and snd == ['click_button']


def test_launching_a_level_from_the_list_clicks():
    # silent in the original; the click is REQUESTED (the tester, 2026-09-26)
    m = level_menu(paths.game_bundle(), Progress(['ps2_Intro']))
    got, snd = run(m, [A.CONFIRM])
    assert got == ('play', 'ps2_Intro') and snd == ['click_button']


def test_the_level_lists_main_menu_and_escape_play_back():
    m = level_menu(paths.game_bundle(), Progress(['ps2_Intro']))
    got, snd = run(m, [A.MENU_UP, A.CONFIRM])
    assert got == ('back', None) and snd == ['back_button']
    got, snd = run(level_menu(paths.game_bundle(), Progress()), [A.CANCEL])
    assert got == ('back', None) and snd == ['back_button']


def test_escape_in_pause_continues_the_game_with_a_click():
    got, snd = run(pause_menu('Collect the fragments of memory.'), [A.CANCEL])
    assert got == ('resume', None) and snd == ['click_button']


def test_quit_game_in_pause_plays_back():
    got, snd = run(pause_menu(''), [A.MENU_DOWN, A.MENU_DOWN, A.MENU_DOWN, A.CONFIRM])
    assert got == ('main', None) and snd == ['back_button']


def test_play_this_again_after_a_win_is_silent():
    got, snd = run(level_complete_menu('ps2_1'), [A.MENU_DOWN, A.CONFIRM])
    assert got == ('replay', None) and snd == []


def test_click_and_back_really_sound_through_the_engine(tmp_path):
    """Rendered, not assumed: each menu press in a row is heard, with no game
    time passing in between (the old game-clock spacing swallowed all but the
    first)."""
    import time
    import numpy as np
    from papasangre2.audio.bank import SoundBank
    from papasangre2.audio.engine import AudioEngine
    from papasangre2.core.game import Game
    from papasangre2.util.settings import Settings
    eng = AudioEngine()
    eng.open(loopback=True)
    try:
        bank = SoundBank(eng, paths.game_bundle())
        bank.load_playlist('ps2_menu')
        g = Game(paths.game_bundle(), Progress(), Settings(str(tmp_path / 's.json')),
                 lambda n: None, menu_bank=bank, engine=eng)
        energies = []
        for name in ('click_button', 'back_button', 'click_button'):
            g.play_ui_sound(name)
            buf = np.asarray(eng.render(44100 // 2), dtype=np.float64)
            energies.append(float(np.sum(buf ** 2)))
            time.sleep(0.12)                  # a quick player, still > 0.1 s
        assert all(e > 1e-3 for e in energies), energies
        assert g.now == 0.0
    finally:
        eng.close()


def test_enter_on_an_explained_row_says_the_explanation_and_stays():
    from papasangre2.shell import Menu, MenuItem
    m = Menu('Achievements', [MenuItem('Act 1, not achieved, 40 percent', 'explain',
                                       'Finish levels 2 to 6.', sound=None),
                              MenuItem('Main menu', 'back')])
    app = StubApp([A.CONFIRM, A.MENU_DOWN, A.CONFIRM])
    got = play.run_menu(app, m)
    assert 'Finish levels 2 to 6.' in app.rep.said
    assert got == ('back', None)


# ---------------------------------------------------------------- updates
class FakeRelease:
    tag = '2026-12-01'
    asset_size = 1000

    def changes(self):
        return 'Fixed the thing.'


class FakePlan:
    staging = 'C:/nowhere/staging'
    remove = ['_internal/old.pyd']
    downloaded = 4200
    download_size = 4200


class FakeService:
    def __init__(self, results):
        self.results = list(results)
        self.busy = False
        self.cancelled = False
        self.percent = 50
        self.checks = 0

    def check(self):
        self.busy = True
        self.checks += 1
        return True

    def install(self, release):
        self.busy = True
        return True

    def cancel(self):
        self.cancelled = True

    def poll(self):
        if self.results:
            r = self.results.pop(0)
            if r is not None:
                self.busy = False
            return r
        return None


class UpdApp(StubApp):
    def __init__(self, keys, results, tmp_path):
        super().__init__(keys)
        from papasangre2.util.settings import Settings
        self.settings = Settings(str(tmp_path / 'settings.json'))
        self.updates = FakeService(results)
        self.update_offered = False
        self.update_started = False
        self.restarting = False
        self.frames = [f for f in self.frames]

    def say(self, text):
        self.rep.say(text)


def _allow(monkeypatch, applied):
    monkeypatch.setattr(play.updater, 'can_update', lambda: (True, ''))
    monkeypatch.setattr(play.updater, 'apply', lambda staging, remove: applied.append((staging, remove)))


def test_the_quiet_check_offers_a_new_version(tmp_path):
    app = UpdApp([], [('checked', FakeRelease(), None)], tmp_path)
    app.updates.busy = True
    assert play.poll_quiet_check(app)[0] == 'update_found'
    none = UpdApp([], [('checked', None, None)], tmp_path)
    none.updates.busy = True
    assert play.poll_quiet_check(none) is None


def test_the_offer_is_update_now_or_not_now_and_nothing_else():
    from papasangre2.shell import update_offer_menu, update_ready_menu
    assert [i.label for i in update_offer_menu('x').items] == ['Update now', 'Not now']
    assert [i.label for i in update_ready_menu('x').items] == ['Update now', 'Not now']
    assert update_offer_menu('x').cancel.action == 'no'


def test_update_now_downloads_and_restarts_with_nothing_more_to_answer(tmp_path, monkeypatch):
    applied = []
    _allow(monkeypatch, applied)
    # Enter on "Update now"; two frames of download, then the plan - and no second question
    app = UpdApp([A.CONFIRM], [None, None, ('installed', FakePlan(), None)], tmp_path)
    app.frames += [[], [], []]
    monkeypatch.setattr(play, 'PROGRESS_EVERY', 0.0)
    assert play.offer_update(app, FakeRelease()) is True
    said = ' '.join(app.rep.said)
    assert 'Version 2026-12-01 is available' in said and 'Fixed the thing.' in said
    assert '50 percent' in said and 'Update ready' not in said
    assert applied == [('C:/nowhere/staging', ['_internal/old.pyd'])] and app.restarting


def test_not_now_asks_again_next_start(tmp_path, monkeypatch):
    applied = []
    _allow(monkeypatch, applied)
    app = UpdApp([A.MENU_DOWN, A.CONFIRM], [], tmp_path)
    assert play.offer_update(app, FakeRelease()) is False
    assert not applied and 'offered again the next time' in app.rep.said[-1]
    esc = UpdApp([A.CANCEL], [], tmp_path)
    assert play.offer_update(esc, FakeRelease()) is False
    assert 'offered again the next time' in esc.rep.said[-1]


def test_escape_stops_the_download(tmp_path, monkeypatch):
    _allow(monkeypatch, [])
    app = UpdApp([A.CONFIRM], [None, ('installed', None, None)], tmp_path)
    app.frames += [[(A.CANCEL.value, 'down', 0.0)], []]
    assert play.offer_update(app, FakeRelease()) is False
    assert app.updates.cancelled and 'Download stopped.' in app.rep.said


def test_a_downloaded_update_is_offered_the_same_way(tmp_path, monkeypatch):
    applied = []
    _allow(monkeypatch, applied)
    later = UpdApp([A.MENU_DOWN, A.CONFIRM], [], tmp_path)
    assert play.ask_restart(later, 'x', [], 'Ready.') is False
    assert not applied and 'offered again' in later.rep.said[-1]
    now = UpdApp([A.CONFIRM], [], tmp_path)
    assert play.ask_restart(now, 'x', ['r'], 'Ready.') is True
    assert applied == [('x', ['r'])] and now.restarting


def test_check_for_updates_answers_when_there_is_nothing_new(tmp_path, monkeypatch):
    _allow(monkeypatch, [])
    app = UpdApp([], [None, ('checked', None, None)], tmp_path)
    app.frames = [[], [], []]
    assert play.check_now(app) is False
    assert app.rep.said[-1].startswith('You have the newest version')


def test_check_for_updates_says_why_it_failed(tmp_path, monkeypatch):
    _allow(monkeypatch, [])
    app = UpdApp([], [('checked', None, 'could not reach GitHub. Check your internet connection')],
                 tmp_path)
    app.frames = [[], []]
    play.check_now(app)
    assert app.rep.said[-1] == ('Could not check for updates: could not reach GitHub. '
                                'Check your internet connection.')


def test_an_update_cannot_be_offered_where_it_cannot_install(tmp_path, monkeypatch):
    monkeypatch.setattr(play.updater, 'can_update', lambda: (False, 'the game is in a folder it '
                                                                   'cannot write to'))
    app = UpdApp([], [], tmp_path)
    assert play.offer_update(app, FakeRelease()) is False
    assert 'cannot update itself here' in app.rep.said[-1]
