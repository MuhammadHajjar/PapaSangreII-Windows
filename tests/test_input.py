"""Controls: the agreed keyboard and pad layouts, clap and jump as chords, and a
fake pad that has real axes (the triggers are the feet now, and a stub
without axes would hide every trigger bug)."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from papasangre2.input.chords import CHORD_WINDOW, ChordResolver      # noqa: E402
from papasangre2.input.keymap import Action, KeyMap                   # noqa: E402
from papasangre2.input.padmap import PadMap                           # noqa: E402


# ------------------------------------------------------------------ keyboard
def test_the_agreed_keyboard_layout():
    km = KeyMap()
    assert km.keys_for(Action.FOOT_LEFT) == ['a'] and km.keys_for(Action.FOOT_RIGHT) == ['d']
    assert km.keys_for(Action.HAND_LEFT) == ['q'] and km.keys_for(Action.HAND_RIGHT) == ['e']
    assert km.keys_for(Action.TURN_LEFT) == ['left'] and km.keys_for(Action.TURN_RIGHT) == ['right']
    assert km.keys_for(Action.PHONE_UPRIGHT) == ['up']
    assert km.keys_for(Action.PHONE_SIDEWAYS) == ['down']
    assert set(km.keys_for(Action.SHAKE)) == {'left ctrl', 'right ctrl'}
    assert km.keys_for(Action.UNPLUG) == ['u']
    assert 'return' in km.keys_for(Action.SKIP)


def test_nothing_on_the_keyboard_quits():
    km = KeyMap()
    assert not hasattr(Action, 'QUIT')
    assert km.keys_for(Action.PAUSE) == ['escape']


def test_no_two_gameplay_actions_share_a_key():
    assert KeyMap().conflicts() == {}


def test_clap_and_jump_have_no_keys_of_their_own():
    # they are chords of the hands and of the feet
    for name in ('CLAP', 'JUMP', 'SWIM', 'ACTION'):
        assert not hasattr(Action, name)


def test_rebinding_round_trip(tmp_path):
    p = str(tmp_path / 'keys.json')
    km = KeyMap(path=p)
    km.bind(Action.HAND_LEFT, ['z'])
    km.save()
    again = KeyMap.load(p)
    assert again.keys_for(Action.HAND_LEFT) == ['z']
    again.reset()
    assert again.keys_for(Action.HAND_LEFT) == ['q']


# ----------------------------------------------------------------------- pad
def test_the_agreed_pad_layout():
    pm = PadMap()
    assert pm.buttons_for(Action.FOOT_LEFT) == ['lefttrigger']
    assert pm.buttons_for(Action.FOOT_RIGHT) == ['righttrigger']
    assert pm.buttons_for(Action.HAND_LEFT) == ['leftshoulder']
    assert pm.buttons_for(Action.HAND_RIGHT) == ['rightshoulder']
    assert pm.buttons_for(Action.PHONE_UPRIGHT) == ['dpup']
    assert pm.buttons_for(Action.PHONE_SIDEWAYS) == ['dpdown']
    assert pm.buttons_for(Action.VOLUME_DOWN) == ['dpleft']
    assert pm.buttons_for(Action.VOLUME_UP) == ['dpright']
    assert pm.buttons_for(Action.SHAKE) == ['y']
    assert pm.buttons_for(Action.UNPLUG) == ['x']
    assert pm.buttons_for(Action.CONFIRM) == ['a'] and pm.buttons_for(Action.PAUSE) == ['start']


class FakeController:
    """A pad with the axes a real one has: two triggers and a left stick."""

    def __init__(self):
        self.axes = {}

    def get_axis(self, axis):
        return self.axes.get(axis, 0)

    def quit(self):
        pass


def fake_gamepad():
    import pygame
    from papasangre2.input.gamepad import Gamepad
    g = Gamepad.__new__(Gamepad)
    g.padmap = PadMap()
    g.controller = FakeController()
    g.joystick = None
    g.name = 'fake'
    g.held = set()
    g._hat = (0, 0)
    g._trigger_down = {'lefttrigger': False, 'righttrigger': False}
    g._names = {}
    return g, pygame


def test_pulling_a_trigger_is_a_foot_press_and_letting_go_releases_it():
    g, pygame = fake_gamepad()
    g.controller.axes[pygame.CONTROLLER_AXIS_TRIGGERLEFT] = 32767
    events = g.poll_triggers()
    assert [(a, ph) for a, ph, _ in events] == [('foot_left', 'down')]
    g.controller.axes[pygame.CONTROLLER_AXIS_TRIGGERLEFT] = 0
    events = g.poll_triggers()
    assert [(a, ph) for a, ph, _ in events] == [('foot_left', 'up')]


def test_the_left_stick_turns():
    g, pygame = fake_gamepad()
    g.controller.axes[pygame.CONTROLLER_AXIS_LEFTX] = -32767
    assert g.turn_rate() < -0.99
    g.controller.axes[pygame.CONTROLLER_AXIS_LEFTX] = 0
    assert g.turn_rate() == 0.0
    g.controller.axes[pygame.CONTROLLER_AXIS_RIGHTX] = 32767
    assert g.turn_rate() == 0.0                  # the right stick does nothing


# -------------------------------------------------------------------- chords
def run(events, until):
    """Feed (action, t) presses, pumping update() every millisecond."""
    r = ChordResolver()
    out = []
    evs = sorted(events, key=lambda e: e[1])
    t = 0.0
    i = 0
    while t <= until:
        while i < len(evs) and evs[i][1] <= t + 1e-9:
            out += [(p.action, round(p.t, 3)) for p in r.feed(evs[i][0], 'down', evs[i][1])]
            i += 1
        out += [(p.action, round(p.t, 3)) for p in r.update(t)]
        t = round(t + 0.001, 3)
    return out


def test_both_hands_together_clap_and_nothing_else():
    assert run([('hand_left', 0.100), ('hand_right', 0.130)], 0.5) == [('clap', 0.13)]


def test_both_feet_together_jump_and_nothing_else():
    assert run([('foot_right', 0.200), ('foot_left', 0.210)], 0.5) == [('jump', 0.21)]


def test_a_lone_hand_waits_for_the_window_then_goes_through():
    out = run([('hand_left', 0.100)], 0.5)
    assert [a for a, _ in out] == ['hand_left']
    assert abs(out[0][1] - (0.100 + CHORD_WINDOW)) <= 0.0015     # 1 ms pump


def test_a_partner_after_the_window_is_two_separate_presses():
    out = run([('hand_left', 0.100), ('hand_right', 0.100 + CHORD_WINDOW + 0.02)], 0.5)
    assert [a for a, _ in out] == ['hand_left', 'hand_right']


def test_walking_is_never_mistaken_for_a_jump():
    # even a very fast run - 350 BPM is the fastest surface limit - is 170 ms a step
    steps = [('foot_left' if i % 2 == 0 else 'foot_right', 0.1 + i * 0.17) for i in range(10)]
    out = run(steps, 2.5)
    assert [a for a, _ in out] == [s for s, _ in steps]


def test_other_actions_pass_straight_through():
    r = ChordResolver()
    assert [(p.action) for p in r.feed('shake', 'down', 1.0)] == ['shake']
    assert r.feed('shake', 'up', 1.1) == []
