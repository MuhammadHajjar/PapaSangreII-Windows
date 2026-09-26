"""Two hands together clap; two feet together jump.

On the iPhone a clap and a jump were the same gesture - a two-finger tap -
told apart by where the fingers landed: both on the upper part of the screen,
one each side, over the hand buttons, is `PGE_INPUT_HandsClapped`; both on the
lower half, one each side, over the foot pads, is `PGE_INPUT_Jump`
(`-[PGEStepsViewController handClapDetected:]`, 0x10000fdac).  The recogniser
is created with `setDelaysTouchesBegan:YES` and `setCancelsTouchesInView:YES`
(`initGestureRecognition`, 0x10000f7f8): a lone touch is held back until the
two-finger tap has failed, and a recognised tap swallows both touches - so a
clap is never also two hand presses, and a jump never two steps.

On a keyboard that is Q and E together, and A and D together (the owner's
call, 2026-09-23 - the same layout as the touchscreen).  So the first key of a
pair is held for a short window: if its partner arrives inside it, both become
one clap or one jump; if not, the single press goes through when the window
closes.  UIKit's own wait cannot be read out of the binary, so the window is
PORT-SIDE - 50 ms to start, to be tuned by playing.  It applies to a
controller's triggers and shoulders the same way, since they arrive as the
same actions.
"""

from __future__ import annotations

from dataclasses import dataclass

from .keymap import Action

#: How long a lone hand or foot waits for its partner.  PORT-SIDE.
CHORD_WINDOW = 0.05

PAIRS = {
    Action.HAND_LEFT.value: (Action.HAND_RIGHT.value, 'clap'),
    Action.HAND_RIGHT.value: (Action.HAND_LEFT.value, 'clap'),
    Action.FOOT_LEFT.value: (Action.FOOT_RIGHT.value, 'jump'),
    Action.FOOT_RIGHT.value: (Action.FOOT_LEFT.value, 'jump'),
}


@dataclass
class Press:
    """What the game sees: an action, or 'clap' / 'jump', at a time."""
    action: str
    t: float


class ChordResolver:
    """Feed it key/button presses; it hands back presses, claps and jumps."""

    def __init__(self, window: float = CHORD_WINDOW) -> None:
        self.window = window
        self.pending: dict[str, float] = {}       # action -> time pressed

    def feed(self, action: str, phase: str, t: float) -> list[Press]:
        """One raw event.  Only presses of the four paired actions are held."""
        if phase != 'down':
            return []
        pair = PAIRS.get(action)
        if pair is None:
            return [Press(action, t)]
        partner, chord = pair
        if partner in self.pending and t - self.pending[partner] <= self.window:
            del self.pending[partner]
            self.pending.pop(action, None)
            return [Press(chord, t)]
        if action in self.pending:
            # the same key again inside the window: the first stands
            return []
        self.pending[action] = t
        return []

    def update(self, now: float) -> list[Press]:
        """Release every lone press whose window has closed."""
        out = []
        for action, t in sorted(self.pending.items(), key=lambda kv: kv[1]):
            if now - t >= self.window:
                out.append(Press(action, now))
        for p in out:
            del self.pending[p.action]
        return out

    def clear(self) -> None:
        self.pending.clear()
