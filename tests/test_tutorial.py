"""The PC versions of the tutorial lines: the right lines, the current keys."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from papasangre2.input.keymap import Action, KeyMap              # noqa: E402
from papasangre2.input.padmap import PadMap                      # noqa: E402
from papasangre2.sim import FakeBank                             # noqa: E402
from papasangre2.tutorial import key_name, pc_about, pc_lines    # noqa: E402
from papasangre2.util import paths                               # noqa: E402


def test_every_mapped_line_is_a_real_sound_of_the_levels_built():
    import random

    class C:
        now = 0.0
        log = []
    names = set()
    for level in ('ps2_Intro', 'ps2_1', 'ps2_2', 'ps2_3', 'ps2_4',
                  'ps2_5', 'ps2_5a', 'ps2_6', 'ps2_7', 'ps2_8', 'ps2_9', 'ps2_10',
                  'ps2_11a', 'ps2_11b', 'ps2_12', 'ps2_13',
                  'ps2_14', 'ps2_15', 'ps2_16', 'ps2_17', 'ps2_18', 'ps2_18b'):
        names |= set(FakeBank(C(), paths.game_bundle(), level, random.Random(1)).specs)
    for name in pc_lines(KeyMap()):
        assert name in names, name


def test_the_museum_lines_say_the_pc_way():
    lines = pc_lines(KeyMap())
    assert lines['1_SPEECH_prompt_no_clap_UOS']() == lines['INTRO_SPEECH_prompt_no_clap_SPA_UOS']()
    assert 'Press either one' in lines['1_SPEECH_precollect_3_UOS']()
    assert 'at the same time' in lines['4_SPEECH_oncollect_4_UOS']()


def test_the_level_5_to_7_lines_say_the_pc_way():
    lines = pc_lines(KeyMap())
    hold = lines['5a_SPEECH_prompt_hold_it_up_SPA_UOS']()
    assert 'Up arrow holds the phone upright' in hold and 'Down arrow holds it on its side' in hold
    assert 'Left Control or Right Control' in lines['5a_SPEECH_intro2_SPA_UOS']()
    assert 'Q: it fires the rifle' in lines['6_SPEECH_instructions_shoot_ducks_UOS']()
    assert lines['7_SPEECH_warning_floor_fall_UOS']() == 'On this computer, your hands are Q and E.'


def test_the_lines_name_the_default_keys():
    lines = pc_lines(KeyMap())
    assert 'Q' in lines['INTRO_SPEECH_prompt_no_clap_SPA_UOS']() and \
           'E' in lines['INTRO_SPEECH_prompt_no_clap_SPA_UOS']()
    walk = lines['INTRO_SPEECH_prompt_no_walk_SPA_UOS']()
    assert 'A and D' in walk
    turn = lines['INTRO_SPEECH_training_0a_SPA_UOS']()
    assert 'Left arrow and Right arrow' in turn
    skip = lines['blind_ps2_skip_tuto']()
    assert 'press Enter or keypad Enter to skip' in skip and 'Escape pauses' in skip


def test_a_rebound_key_is_spoken_as_rebound(tmp_path):
    km = KeyMap(path=str(tmp_path / 'k.json'))
    km.bind(Action.HAND_LEFT, ['z'])
    assert 'Z' in pc_lines(km)['INTRO_SPEECH_training_10a_UOS']()


def test_the_controller_is_mentioned_only_when_one_is_connected():
    lines = pc_lines(KeyMap(), PadMap(), pad_connected=lambda: False)
    assert 'controller' not in lines['INTRO_SPEECH_prompt_no_walk_SPA_UOS']()
    lines = pc_lines(KeyMap(), PadMap(), pad_connected=lambda: True)
    assert 'On the controller' in lines['INTRO_SPEECH_prompt_no_walk_SPA_UOS']()


def test_key_names_read_well():
    assert key_name('return') == 'Enter' and key_name('a') == 'A'
    assert key_name('left ctrl') == 'Left Control'


def test_the_about_text_says_how_to_turn_without_a_gyro():
    t = pc_about(KeyMap())
    assert 'Left arrow' in t and 'Gyro' in t
