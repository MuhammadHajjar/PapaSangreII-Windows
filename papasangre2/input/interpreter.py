"""`PGEMoveInterpretor` as Papa Sangre II has it - input to action messages.

The walking rule is PS1's (docs/notes/M2_NOTES.md, "PGEMoveInterpretor"):
you place one foot, then the other; the foot you just used stays "off" for
two seconds; stand still that long and both feet come free again (with a
`PGE_ACTION_Shuffle`, which PS2's player ignores).  What PS2 changed:

* after a step the re-checks at +0.1 s and +2.0 s are `performSelector:
  afterDelay:` calls that **cancel the previous step's** pending ones, so only
  the last step's pair is ever waiting (PS1 queued one pair per step);
* `playerStateDidChange:` re-evaluates the feet **before** it stores the new
  state, and a trip stamps both feet with the trip's time;
* hands: one hand posts `PGE_ACTION_Hand {Hand: L|R}`, both together post
  `PGE_ACTION_HandsClapped` - gated on `playerCanUseHands` and not tripped;
* jump: gated on `playerCanJump` (off by default), clears both feet's dates,
  shows "jump" for 0.2 s, posts `PGE_ACTION_Jump`.

Timing uses the bus clock for both the stamps and the re-checks, so the 2.0 s
re-check always sees at least 2.0 s of foot time (the PS1 port once scheduled
off a different clock and the shuffle fired only sometimes).
"""

from __future__ import annotations

from ..core.messages import MessageBus, Params

LEFT, RIGHT, NONE = 'L', 'R', 'N'
OFF, ON, PRESSED, JUMP = 'off', 'on', 'pressed', 'jump'

FOOT_LOCKOUT = 2.0               # updateFeetView: fmov s9, #2.0
SHUFFLE_MAX = 99.0               # float 99
INTERVAL_CLAMP = 100.0           # float/double 100
SAME_FOOT_TRIP = 1.0             # footButtonReleased: fmov d0, #1.0
RECHECK_DELAYS = (0.1, 2.0)      # the block at 0x1000070d4
JUMP_VIEW_TIME = 0.2             # the block at 0x100007cc4
HANDS_VIEW_TIME = 0.1


class MoveInterpretor:
    """Feet, hands, turning and jumping, with the original's gates."""

    def __init__(self, bus: MessageBus) -> None:
        self.bus = bus
        self.player_can_walk = False
        self.player_can_rotate = False
        self.player_can_jump = False
        self.player_can_use_hands = False
        self.player_can_swim = False
        self.player_state = 0
        self.hands_action = 0
        self.last_left_foot: float | None = None
        self.last_right_foot: float | None = None
        self.last_left_hand: float | None = None
        self.last_right_hand: float | None = None
        self.last_foot_button_pressed: str | None = None
        self.feet = {LEFT: OFF, RIGHT: OFF}
        self.hands = {LEFT: OFF, RIGHT: OFF}
        for name, handler in (
            ('PGE_MESSAGE_SetControlSettingsToDefault', lambda *_: self.set_settings_to_default()),
            ('PGE_MESSAGE_DisableWalk', lambda *_: self._set('player_can_walk', False, feet=True)),
            ('PGE_MESSAGE_EnableWalk', lambda *_: self._set('player_can_walk', True, feet=True)),
            ('PGE_MESSAGE_DisableRotation', lambda *_: self._set('player_can_rotate', False)),
            ('PGE_MESSAGE_EnableRotation', lambda *_: self._set('player_can_rotate', True)),
            ('PGE_MESSAGE_EnableJump', lambda *_: self._set('player_can_jump', True)),
            ('PGE_MESSAGE_DisableJump', lambda *_: self._set('player_can_jump', False)),
            ('PGE_MESSAGE_EnableHands', lambda *_: self.enable_hands()),
            ('PGE_MESSAGE_DisableHands', lambda *_: self.disable_hands()),
            ('PGE_MESSAGE_EnableSwim', lambda *_: self._set('player_can_swim', True, feet=True, hands=True)),
            ('PGE_MESSAGE_DisableSwim', lambda *_: self._set('player_can_swim', False, feet=True, hands=True)),
            ('PGE_MESSAGE_PlayerStateDidChange', self._player_state_did_change),
        ):
            bus.subscribe(name, handler)
        self.lock_controls()

    # ------------------------------------------------------------ gating
    def _set(self, attr: str, value: bool, feet: bool = False, hands: bool = False) -> None:
        setattr(self, attr, value)
        if hands:
            self.update_hands_view(NONE)
        if feet:
            self.update_feet_view(NONE)

    def lock_controls(self) -> None:
        """`lockControls` (0x100005c70)."""
        self.player_can_walk = self.player_can_rotate = False
        self.player_can_jump = self.player_can_use_hands = False
        self.player_can_swim = False
        self.update_feet_view(NONE)
        self.update_hands_view(NONE)

    def set_settings_to_default(self) -> None:
        """`setSettingsToDefault` (0x100005cf8): walk, turn, hands; no jump, swim."""
        self.player_can_walk = True
        self.player_can_rotate = True
        self.player_can_jump = False
        self.player_can_use_hands = True
        self.player_can_swim = False
        self.player_state = 0
        self.update_feet_view(NONE)
        self.update_hands_view(NONE)

    def enable_hands(self) -> None:
        self.player_can_use_hands = True
        self.update_hands_view(NONE)
        self.hands_action = 1

    def disable_hands(self) -> None:
        self.player_can_use_hands = False
        self.update_hands_view(NONE)

    def _player_state_did_change(self, _n, params: Params) -> None:
        """`playerStateDidChange:` (0x100005d90)."""
        new = int(params.get('state', self.player_state))
        if new != self.player_state:
            self.update_feet_view(NONE)          # with the old state
            self.player_state = new
            self.update_hands_view(NONE)
        if new == 3:
            self.last_right_foot = self.last_left_foot = self.bus.now

    # -------------------------------------------------------------- feet
    def foot_pressed(self, foot: str) -> bool:
        """`footButtonPressed:` (PS1's, unchanged)."""
        if not self.player_can_walk or self.player_state == 3:
            return False
        if self.feet.get(foot) == OFF:
            return False
        self.feet[foot] = PRESSED
        self.bus.post('PGE_MESSAGE_UpdateFeetView', dict(self.feet))
        return True

    def foot_released(self, foot: str) -> bool:
        """`footButtonReleased:` (0x100006abc) - the step itself."""
        if not self.player_can_walk or self.player_state == 3:
            return False
        if self.feet.get(foot) == OFF:
            return False
        now = self.bus.now
        info = {'lastFoot': foot}
        left, right = self.last_left_foot, self.last_right_foot
        tripped = False
        if left is not None and right is not None:
            if left < right and foot == RIGHT and abs(now - right) < SAME_FOOT_TRIP:
                tripped = True
            elif left > right and foot == LEFT and abs(now - left) < SAME_FOOT_TRIP:
                tripped = True
        if tripped:
            # unreachable behind the "off" gate, kept because the binary has it
            self.bus.post('PGE_ACTION_Trip', info)
        else:
            if foot == LEFT:
                self.last_left_foot = now
            else:
                self.last_right_foot = now
            self.bus.post('PGE_ACTION_OneStep', info)
            self.last_foot_button_pressed = foot
        self.update_feet_view(foot)
        self.bus.dispatch_async(self._schedule_rechecks)
        return not tripped

    def _schedule_rechecks(self) -> None:
        """The block at 0x1000070d4: cancel "N" and "N+1", then +0.1 and +2.0."""
        self.bus.cancel((id(self), 'feet', NONE))
        self.bus.cancel((id(self), 'feet', 'N+1'))
        for delay in RECHECK_DELAYS:
            self.bus.call_after(delay, lambda: self.update_feet_view(NONE),
                                (id(self), 'feet', NONE))

    def update_feet_view(self, arg: str) -> None:
        """`updateFeetView:` (0x10000612c)."""
        if not self.player_can_walk:
            self.feet = {LEFT: OFF, RIGHT: OFF}
        elif arg == '2':
            self.feet = {LEFT: JUMP, RIGHT: JUMP}
        elif arg == '0':
            self.feet = {LEFT: ON, RIGHT: ON}
        elif self.player_state == 3:
            self.feet = {LEFT: OFF, RIGHT: OFF}
        else:
            now = self.bus.now
            feet = {}
            for foot, stamp in ((LEFT, self.last_left_foot), (RIGHT, self.last_right_foot)):
                gap = 0.0 if stamp is None else abs(now - stamp)
                gap = min(gap, INTERVAL_CLAMP)
                last = self.last_foot_button_pressed == foot
                if last and gap < FOOT_LOCKOUT:
                    feet[foot] = OFF
                    continue
                if last and FOOT_LOCKOUT <= gap < SHUFFLE_MAX:
                    self.bus.post('PGE_ACTION_Shuffle', {})
                    self.last_foot_button_pressed = NONE
                feet[foot] = ON
            self.feet = feet
        self.bus.post('PGE_MESSAGE_UpdateFeetView', dict(self.feet))

    # ------------------------------------------------------------- hands
    def update_hands_view(self, arg: str) -> None:
        """`updateHandsView:` (0x1000071a4) - only a view; kept for the log."""
        if not self.player_can_use_hands:
            self.hands = {LEFT: OFF, RIGHT: OFF}
        elif arg == '0':
            self.hands = {LEFT: ON, RIGHT: ON}
        elif arg == '2':
            self.hands = {LEFT: PRESSED, RIGHT: PRESSED}
        elif self.player_state == 3:
            self.hands = {LEFT: OFF, RIGHT: OFF}
        else:
            now = self.bus.now
            self.hands = {
                LEFT: PRESSED if self.last_left_hand is not None and abs(now - self.last_left_hand) < 0.1 else ON,
                RIGHT: PRESSED if self.last_right_hand is not None and abs(now - self.last_right_hand) < 0.1 else ON,
            }
        self.bus.post('PGE_MESSAGE_UpdateHandsView', dict(self.hands))

    def hand_pressed(self, hand: str) -> bool:
        """`handButtonPressed:` (0x1000076f4)."""
        if not self.player_can_use_hands or self.player_state == 3:
            return False
        if hand == LEFT:
            self.last_left_hand = self.bus.now
        elif hand == RIGHT:
            self.last_right_hand = self.bus.now
        self.bus.post('PGE_ACTION_Hand', {'Hand': hand})
        token = (id(self), 'hands', NONE)
        self.bus.cancel(token)
        self.bus.call_after(HANDS_VIEW_TIME, lambda: self.update_hands_view(NONE), token)
        return True

    def hands_clapped(self) -> bool:
        """`handsClapped:` (0x1000079e0)."""
        if not self.player_can_use_hands or self.player_state == 3:
            return False
        self.last_left_hand = self.last_right_hand = self.bus.now
        self.update_hands_view('2')
        token = (id(self), 'hands', '0')
        self.bus.cancel(token)
        self.bus.call_after(HANDS_VIEW_TIME, lambda: self.update_hands_view('0'), token)
        self.bus.post('PGE_ACTION_HandsClapped', {})
        return True

    # -------------------------------------------------------------- jump
    def jump(self) -> bool:
        """`jump:` (0x100007b70)."""
        if self.player_state == 3 or not self.player_can_jump:
            return False
        self.last_left_foot = self.last_right_foot = None
        self.update_feet_view('2')

        def block():
            token = (id(self), 'feet', '0')
            self.bus.cancel(token)
            self.bus.call_after(JUMP_VIEW_TIME, lambda: self.update_feet_view('0'), token)
        self.bus.dispatch_async(block)
        self.bus.post('PGE_ACTION_Jump', {})
        return True

    # ------------------------------------------------------------ turning
    def rotate_by(self, radians: float) -> bool:
        """`rotatePlayerFromAngle:` - PGE_INPUT_RotateFromAngle, if allowed."""
        if not self.player_can_rotate:
            return False
        self.bus.post('PGE_ACTION_RotatePlayerFromAngle', {'value': float(radians)})
        return True

    def describe_state(self) -> str:
        allowed = [n for n, on in (('walk', self.player_can_walk),
                                   ('turn', self.player_can_rotate),
                                   ('jump', self.player_can_jump),
                                   ('hands', self.player_can_use_hands)) if on]
        return ', '.join(allowed) if allowed else 'controls locked'
