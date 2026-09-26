"""The game around the level: winning, the skip button and its ping, the menu
audio, and the three REQUESTED settings (Blind intro, Skip ping, Skip
explanation).  Headless, with fake sounds that end."""

import os
import random
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from papasangre2.autopilot import play_intro                    # noqa: E402
from papasangre2.core.game import Game                          # noqa: E402
from papasangre2.sim import FakeBank, Progress                  # noqa: E402
from papasangre2.util import paths                              # noqa: E402
from papasangre2.util.settings import Settings                  # noqa: E402


class Clock:
    def __init__(self):
        self.game = None
        self.log = []

    @property
    def now(self):
        # sounds play in real time: the menu clock, which runs in levels and
        # on the after-level screen alike
        return self.game.menu_now if self.game else 0.0


class SaveStub(Progress):
    def __init__(self):
        super().__init__()
        self.values = {}

    def player_did_complete_level(self, n): self.values[n + '_completed'] = True
    def player_did_unlock_level(self, n): self.values[n + '_locked'] = True
    def player_did_play_level(self, n): self.values['lastLevelPlayed'] = n


def make_game(tmp_path, **settings):
    bundle = paths.game_bundle()
    clock = Clock()
    rng = random.Random(3)
    s = Settings(str(tmp_path / 'settings.json'))
    for k, v in settings.items():
        s.set(k, v)
    said = []
    g = Game(bundle, SaveStub(), s, lambda name: FakeBank(clock, bundle, name, rng),
             menu_bank=FakeBank(clock, bundle, 'ps2_menu', rng), say=said.append,
             tutorial_lines={'INTRO_SPEECH_training_6_SPA_UOS': 'press Q and E together',
                             'INTRO_SPEECH_prompt_no_walk_SPA_UOS': 'press A, then D'},
             rng=rng, ui_clock=lambda: clock.now)
    clock.game = g
    g.said = said
    g.clock = clock
    return g


class GameSim:
    """Lets the Intro autopilot drive a Game instead of a bare Sim."""

    def __init__(self, g):
        self.g = g
        self.bus = g.bus
        self.interpreter = g.interpreter
        self.log = g.clock.log
        self.messages = []
        self.bus.subscribe(None, lambda n, p: self.messages.append((g.now, n, dict(p))))

    @property
    def now(self):
        return self.g.now

    @property
    def level(self):
        return self.g.level

    @property
    def player(self):
        return self.g.level.player

    @property
    def progress(self):
        return self.g.progress

    def step(self, dt=0.01):
        self.g.update(dt)

    def run_until(self, pred, limit=600.0, dt=0.01):
        end = self.g.now + limit
        while self.g.now < end:
            if pred():
                return True
            self.g.update(dt)
        return pred()

    def foot(self, f):
        ok = self.interpreter.foot_pressed(f) and self.interpreter.foot_released(f)
        self.bus.update(self.g.now)
        return ok

    def hand(self, h):
        ok = self.interpreter.hand_pressed(h)
        self.bus.update(self.g.now)
        return ok

    def clap(self):
        ok = self.interpreter.hands_clapped()
        self.bus.update(self.g.now)
        return ok

    def turn(self, r):
        ok = self.interpreter.rotate_by(r)
        self.bus.update(self.g.now)
        return ok

    def skip(self):
        self.g.skip()

    def sent(self, name):
        return [p for _, n, p in self.messages if n == name]

    def played(self):
        return [n for _, w, n in self.log if w == 'play']


def test_finishing_the_intro_is_a_win_that_unlocks_the_next_level(tmp_path):
    g = make_game(tmp_path)
    g.load('ps2_Intro')
    play_intro(GameSim(g))
    assert g.outcome == ('win', 'ps2_Intro', 'ps2_1')
    assert g.progress.values['ps2_Intro_completed'] and g.progress.values['ps2_1_locked']


def test_the_end_music_starts_before_the_last_line_ends(tmp_path):
    g = make_game(tmp_path)
    g.load('ps2_Intro')
    play_intro(GameSim(g))
    assert [s.name for s in g.atmos] == ['ps2_Intro_end_music_loop']
    assert g.atmos[0].playing and abs(g.atmos[0].gain - 0.4) < 1e-9


def test_the_skip_button_skips_only_while_it_is_up_and_pings(tmp_path):
    g = make_game(tmp_path)
    g.load('ps2_Intro')
    gs = GameSim(g)
    assert not g.skip()                                   # nothing skippable yet
    gs.run_until(lambda: g.skip_button, limit=300)
    t = g.now
    gs.run_until(lambda: 'skipButtonAppeared' in gs.played(), limit=2)
    assert 'skipButtonAppeared' in gs.played()
    assert abs(g.now - t - 1.0) < 0.05                    # 1 s after the button
    g.update(0.2)                  # UI sounds are at least 0.1 s apart
    assert g.skip()
    assert 'click_button' in gs.played()
    assert not g.skip_button


def test_skip_ping_off_is_silent(tmp_path):
    g = make_game(tmp_path, skipPing=False)
    g.load('ps2_Intro')
    gs = GameSim(g)
    gs.run_until(lambda: g.skip_button, limit=300)
    g.update(2.0)
    assert 'skipButtonAppeared' not in gs.played()


def test_skip_explanation_off_goes_straight_to_the_opening_scene(tmp_path):
    g = make_game(tmp_path, skipExplanation=False)
    g.load('ps2_Intro')
    gs = GameSim(g)
    g.update(1.0)
    played = gs.played()
    assert not any('skip_tuto' in n for n in played)
    assert 'INTRO_intro_UOS' in played


def test_blind_intro_off_still_speaks_the_skip_explanation(tmp_path):
    """REQUESTED: the sighted take is silence, so the spoken one plays."""
    g = make_game(tmp_path, blindIntro=False)
    g.load('ps2_Intro')
    gs = GameSim(g)
    g.update(1.0)
    assert 'blind_ps2_skip_tuto' in gs.played()
    assert 'ps2_skip_tuto' not in gs.played()


def test_blind_intro_off_keeps_the_rest_of_the_intro_sighted(tmp_path):
    g = make_game(tmp_path, blindIntro=False)
    g.load('ps2_Intro')
    gs = GameSim(g)
    play_intro(gs)
    blind = {n for n in gs.played() if n.startswith('blind_')}
    assert blind == {'blind_ps2_skip_tuto'}
    assert g.outcome == ('win', 'ps2_Intro', 'ps2_1')


def test_skip_explanation_off_with_blind_intro_off_plays_neither_take(tmp_path):
    g = make_game(tmp_path, blindIntro=False, skipExplanation=False)
    g.load('ps2_Intro')
    gs = GameSim(g)
    g.update(1.0)
    assert not any('skip_tuto' in n for n in gs.played())


def test_blind_intro_on_plays_the_voiceover_line(tmp_path):
    g = make_game(tmp_path)
    g.load('ps2_Intro')
    gs = GameSim(g)
    g.update(1.0)
    assert 'blind_ps2_skip_tuto' in gs.played()


def test_a_tutorial_line_is_followed_by_its_pc_version(tmp_path):
    g = make_game(tmp_path)
    g.load('ps2_Intro')
    play_intro(GameSim(g))
    assert 'press Q and E together' in g.said


def test_a_looping_prompt_gets_its_pc_version_once_after_the_first_pass(tmp_path):
    g = make_game(tmp_path)
    g.load('ps2_Intro')
    gs = GameSim(g)
    from papasangre2.autopilot import intro_opening
    ap = intro_opening(gs)
    gs.run_until(lambda: ap.active('no_walk_prompt')
                 and g.level.agent('no_walk_prompt').sound is not None, limit=400)
    s = g.level.agent('no_walk_prompt').sound
    assert s is not None and s.looping
    g.update(s.duration * 3 + 0.5)                     # three passes, nobody walks
    assert g.said.count('press A, then D') == 1


def test_the_pause_text_is_the_levels_objective(tmp_path):
    g = make_game(tmp_path)
    g.load('ps2_Intro')
    assert g.pause_text == 'Collect the fragments of memory.'


def test_pausing_freezes_the_level(tmp_path):
    g = make_game(tmp_path)
    g.load('ps2_Intro')
    g.update(0.5)
    g.pause()
    playing = [s for s in g.bank.live_sounds() if s.playing]
    before = g.level.player_update_value
    g.update(3.0)
    assert g.level.player_update_value == before
    assert not any(s.playing for s in playing)
    g.resume()
    g.update(0.2)
    assert g.level.player_update_value > before


def test_the_menu_atmosphere_fades_in_to_half(tmp_path):
    g = make_game(tmp_path)
    g.play_menu_atmos()
    assert g.atmos and g.atmos[0].name == 'menu_death_atmos' and g.atmos[0].gain == 0.0
    g.update(3.1)
    assert abs(g.atmos[0].gain - 0.5) < 1e-6
    g.fade_out_menu_atmos(2.0)
    g.update(2.1)
    assert g.atmos == []


def test_menu_sounds_keep_playing_where_no_game_time_passes(tmp_path):
    """The 0.1 s spacing is wall-clock time: in a menu the game clock stands
    still, and every click and back must still be heard."""
    g = make_game(tmp_path)
    wall = [100.0]
    g.ui_clock = lambda: wall[0]
    played = []
    g.menu_bank.sound = lambda name: _Once(name, played)
    for name in ('click_button', 'click_button', 'back_button'):
        g.play_ui_sound(name)
        wall[0] += 0.3                   # a person pressing keys; game time frozen
    assert played == ['click_button', 'click_button', 'back_button']
    assert g.now == 0.0


def test_two_ui_sounds_closer_than_a_tenth_of_a_second_play_once(tmp_path):
    g = make_game(tmp_path)
    wall = [5.0]
    g.ui_clock = lambda: wall[0]
    played = []
    g.menu_bank.sound = lambda name: _Once(name, played)
    g.play_ui_sound('click_button')
    wall[0] += 0.05
    g.play_ui_sound('back_button')
    assert played == ['click_button']


class _Once:
    def __init__(self, name, log):
        self.name, self.log, self.playing = name, log, False

    def play(self):
        self.log.append(self.name)
