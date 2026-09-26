"""`PGECollectible` as Papa Sangre II has it - the fragments of memory.

docs/notes/M2_NOTES.md ("PGECollectible"):

* `activate`: the intro sound (unless it is the loop sound itself), then the
  loop; the base activation (`OnActivate`, collision check) straight away;
* reaching it (`collideRadius`) collects it - unless it is collected with a
  hand (`collectWithLeftHand` / `collectWithRightHand`) or a shake, when only
  `OnCollide` fires and the hand press does the collecting while in reach;
* collecting: with `ignoreLoop` at once, otherwise at the end of the current
  pass of the loop; `OnCollect`, then the collect sound; when that ends the
  `nextCollectible` is activated, `OnSoundEnd` fires and it deactivates;
* a skippable collect sound can be skipped like any other.
"""

from __future__ import annotations

import random

import numpy as np

from ..assets.tiled import LevelObject, ns_bool, ns_float
from ..core.messages import MessageBus, Params
from .agent import GameAgent
from .player import play

END_MUSIC_LEAD = 0.2
#: REQUESTED (decision 14, 2026-09-25): a memory collected by shaking takes
#: this many shakes (Ctrl presses) - the number the game itself asks for in
#: its one multi-shake scene (ps2_18b, afterCount=7).  The original collects on
#: the first shake the accelerometer reports.
SHAKES_TO_COLLECT = 7


class Collectible(GameAgent):
    """`PGECollectible`."""

    kind = 'collectible'

    def __init__(self, bus: MessageBus, world, obj: LevelObject | None = None,
                 rng: random.Random | None = None) -> None:
        self.collected = False
        self.collect_at_end_of_loop = False
        self.skippable = False
        self.collect_with_left_hand = False
        self.collect_with_right_hand = False
        self.collect_with_shake = False
        self.cancel_wet_gain = False
        self.ignore_loop = False
        self.preload_end_music = False
        self.started_end_music = False
        self.collect_gain = 1.0
        self.collect_sound: str | None = None
        self.loop_sound: str | None = None
        self.next_collectible: str | None = None
        self.collect_with_shake_timer = 0.0
        self.shakes = 0
        super().__init__(bus, world, obj, rng)
        self.unpausable = True
        bus.subscribe('PGE_INPUT_DoubleTap', self._on_double_tap)
        bus.subscribe('PGE_ACTION_Shake', self._shake)
        bus.subscribe('PGE_MESSAGE_CollectAgentWithName', self._collect_with_name)

    @property
    def sound_priority(self) -> int:
        """`-[PGECollectible soundPriority]` (0x10001b328): 0 until collected.

        So a memory still waiting to be picked up is never silenced by a
        louder line (`startedSoundWithPriority:` ignores priority 0), and does
        not count towards the level's highest playing priority.  `collect`
        sets `collected` only after `playCollectSound`, so the collect sound
        never announces its own priority either.
        """
        return self._own_priority if getattr(self, 'collected', False) else 0

    @sound_priority.setter
    def sound_priority(self, value) -> None:
        self._own_priority = int(value)

    def build(self, obj: LevelObject) -> None:
        super().build(obj)
        a = obj.applied
        for key, attr, conv in (
            ('skippable', 'skippable', ns_bool),
            ('collectWithLeftHand', 'collect_with_left_hand', ns_bool),
            ('collectWithRightHand', 'collect_with_right_hand', ns_bool),
            ('collectWithShake', 'collect_with_shake', ns_bool),
            ('cancelWetGain', 'cancel_wet_gain', ns_bool),
            ('ignoreLoop', 'ignore_loop', ns_bool),
            ('preloadEndMusic', 'preload_end_music', ns_bool),
            ('collectGain', 'collect_gain', ns_float),
            ('collectSound', 'collect_sound', str),
            ('loopSound', 'loop_sound', str),
            ('nextCollectible', 'next_collectible', str),
        ):
            if key in a:
                setattr(self, attr, conv(a[key]))
        # -[PGECollectible setGain:] (0x10001ac90): setting the gain also sets
        # the collect sound's gain while that is still 1 - so a memory that
        # names only a gain collects at it.  The original applies the keys in
        # NSDictionary order; the port takes the file's (PORT-SIDE: only
        # ps2_13's easter_egg, gain 0.5 with collectGain 1.0, depends on it).
        cg = 1.0
        for key, value in a.items():
            if key == 'collectGain':
                cg = ns_float(value)
            elif key == 'gain' and cg == 1.0:
                cg = ns_float(value)
        self.collect_gain = cg

    # ------------------------------------------------------------- sounds
    def _place(self, s) -> None:
        s.spatialized = True
        self.setup_reverb_parameters(s)
        self.sound = s
        self.update_spatialized_sound()
        s.gain = self.gain

    def activate(self) -> None:
        """`-[PGECollectible activate]` (0x10001b1e4)."""
        self.play_intro_sound()
        super().activate()

    def play_intro_sound(self) -> None:
        """`playIntroSound` (0x10001c018)."""
        if self.collected:
            return
        if not self.intro_sound or len(self.intro_sound) < 2 or self.intro_sound == self.loop_sound:
            self.start_loop()
            return
        if self.sound is not None and self.sound.playing:
            self.sound.stop()
        s = self.bank.sound(self.intro_sound) if self.bank is not None else None
        if s is None:
            return
        self._place(s)
        play(s, False)

        def monitor(pos, dur):
            if pos >= dur:
                self.bus.dispatch_async(self.start_loop)
                return True
            return False
        self.world.monitors.add(s, monitor, self)

    def start_loop(self) -> None:
        """`startLoop` (0x10001c884)."""
        if self.collected:
            return
        if self.sound is not None and self.sound.playing:
            self.sound.stop()
        s = self.bank.sound(self.loop_sound) if (self.bank is not None and self.loop_sound) else None
        if s is None:
            return
        self._place(s)
        self.world.monitors.add_end_callback(s, self.end_of_loop, self)
        play(s, True)

    def end_of_loop(self) -> None:
        """`endOfLoop` (0x10001cb30)."""
        if self.collect_at_end_of_loop:
            self.play_collect_sound()
            self.collected = True
            if self.world is not None:
                self.world.collectibles_collected += 1
                if getattr(self.world, 'tracker', None) is not None:
                    self.world.tracker.increment_collectibles()

    def deactivate(self) -> None:
        """`-[PGECollectible deactivate]` (0x10001b2e0): no longer collected."""
        self.collected = False
        self.shakes = 0
        super().deactivate()

    def update(self, dt: float) -> None:
        """`-[PGECollectible update:]` (0x10001ad08): a shake collectible left
        in reach collects itself after 20 s."""
        super().update(dt)
        if self._active and self.in_collide_range and self.collect_with_shake:
            self.collect_with_shake_timer = float(np.float32(self.collect_with_shake_timer)
                                                  + np.float32(dt))
            if self.collect_with_shake_timer > 20.0:
                self.collect_with_shake_timer = 0.0
                self.collect()

    def _collect_with_name(self, _n, params: Params) -> None:
        """`collectWithName:` (0x10001c770), for `CollectAgentWithName`."""
        if params.get('name') == self.name:
            self.collect()

    # ------------------------------------------------------------ collect
    def collides_with_player(self) -> None:
        """`-[PGECollectible collidesWithPlayer]` (0x10001addc)."""
        if not (self.collect_with_right_hand or self.collect_with_left_hand
                or self.collect_with_shake):
            self.collect()
        super().collides_with_player()

    def collect(self) -> None:
        """`collect` (0x10001ae7c)."""
        if not self._active or self.collected:
            return
        if self.ignore_loop:
            self.play_collect_sound()
            self.collected = True
            if self.world is not None:
                self.world.collectibles_collected += 1
                if getattr(self.world, 'tracker', None) is not None:
                    self.world.tracker.increment_collectibles()
        else:
            self.collect_at_end_of_loop = True

    def _hands_action(self, n, params: Params) -> None:
        """`-[PGECollectible handsActionMessageReceived:]` (0x10001af58)."""
        if self.in_collide_range and self._active:
            hand = params.get('Hand')
            if hand == 'L' and self.collect_with_left_hand:
                self.collect()
            elif hand == 'R' and self.collect_with_right_hand:
                self.collect()
        super()._hands_action(n, params)

    def _shake(self, _n, _p) -> None:
        """`shakeMessageReceived:` (0x10001b170): active, in reach, and a shake
        collectible -> `collect`.  REQUESTED (decision 14): it takes
        SHAKES_TO_COLLECT shakes, and each one the memory takes plays the
        game's whoosh, since shaking it makes no sound of its own."""
        if not (self.collect_with_shake and self.in_collide_range and self._active):
            return
        if self.collected or self.collect_at_end_of_loop:
            return
        hook = getattr(self.world, 'play_whoosh', None) if self.world is not None else None
        if hook is not None:
            hook()
        self.shakes += 1
        if self.shakes >= SHAKES_TO_COLLECT:
            self.shakes = 0
            self.collect()

    def play_collect_sound(self) -> None:
        """`playCollectSound` (0x10001b37c)."""
        if self.sound is not None:
            self.sound.stop()
            if self.world is not None:
                self.world.monitors.remove_sound(self.sound)
        self.trigger('OnCollect')
        s = None
        if self.collect_sound and self.bank is not None:
            s = self.bank.sound(self.collect_sound)
            if s is None:
                s = self.bank.any_sound_with_prefix(self.collect_sound)
        self.sound = s
        if s is None:
            self._collect_sound_finished(no_sound=True)
            return
        if self.cancel_wet_gain:
            # [self setWetGain:0] - the collectible's own wet gain, which
            # setupReverbParameters then puts on the sound: a dry cutscene.
            self.wet_gain = 0.0
        self.setup_reverb_parameters(s)
        s.gain = self.collect_gain
        if s.spatialized:             # the playlist's own flag (0x10001b600), not forced
            self.update_spatialized_sound()
        play(s, False)
        if self.preload_end_music:
            self.bus.post('PGE_MESSAGE_PreloadEndMusic', {})
        if self.sound_priority >= 1:
            self.bus.post('PGE_MESSAGE_StartedSoundWithPriority',
                          {'name': self.name, 'priority': self.sound_priority})

        def monitor(pos, dur):
            if self.preload_end_music and not self.started_end_music and dur - END_MUSIC_LEAD <= pos:
                self.bus.post('PGE_MESSAGE_PlayEndMusic', {})
                self.started_end_music = True
            if pos >= dur:
                hook = getattr(self.world, 'on_line_ended', None)
                if hook is not None:
                    hook(s.name)
                self.bus.dispatch_async(self._collect_sound_finished)
                return True
            return False
        self.world.monitors.add(s, monitor, self)
        if self.skippable and self._active:
            self.bus.post('PGE_MESSAGE_ShowSkipButton', {'sender': self.name})

    def _activate_next(self) -> None:
        if self.next_collectible:
            self.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': self.next_collectible})

    def _collect_sound_finished(self, no_sound: bool = False) -> None:
        """The collect sound's end block (and the no-sound path)."""
        if no_sound:
            self._activate_next()
            if self.preload_end_music:
                self.bus.post('PGE_MESSAGE_PlayEndMusic', {})
            self.trigger('OnSoundEnd')
            self.deactivate()
            return
        self._active = self._active            # setActive: on the block's path
        self._activate_next()
        if self.skippable:
            self.bus.post('PGE_MESSAGE_RemoveSkipButton', {'sender': self.name})
        self.trigger('OnSoundEnd')
        self.deactivate()

    def _on_double_tap(self, _n, _p) -> None:
        """`-[PGECollectible onDoubleTap]` (0x10001c47c)."""
        if not (self.skippable and self._active):
            return
        if self.sound is None or not self.sound.playing or not self.collected:
            return
        self.sound.stop()
        if self.world is not None:
            self.world.monitors.remove_sound(self.sound)
        if self.has_trigger('OnSkip'):
            self.trigger('OnSkip')
        else:
            self.trigger('OnSoundEnd')
        self._activate_next()
        self.deactivate()
