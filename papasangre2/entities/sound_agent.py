"""`PGESound` as Papa Sangre II has it - every narration line, loop and cue.

docs/notes/M2_NOTES.md ("PGESound") has the addresses.  In order:

* `activate`: with an `introSound`, play it first and only when it ends run
  the base activation (`OnActivate`) and start the real sound; without one,
  `OnActivate` now and the sound on the next pass of the run loop;
* `createSpatializedSound`: pick one of `soundList` at random; a sound with a
  priority that is not above what is already playing is **dropped** - its
  `OnSoundEnd` fires at once; the VoiceOver variant `blind_<name>` is
  preferred when VoiceOver is on (the port's **Blind intro** setting); then
  gain, fade-in over `fadeInTime` towards `finalGain` in 10 ms steps, and a
  monitor that fires `OnSoundEnd` when a non-looping sound ends;
* a skippable sound posts `ShowSkipButton` when it starts; the skip input
  (`PGE_INPUT_DoubleTap`) stops every active, skippable, playing sound and
  fires its `OnSkip` - or its `OnSoundEnd` when it has no `OnSkip`;
* rails: `onXrail` / `onYrail` make the sound follow the player's motion on
  that axis (while active, or always with `onInactiveRail`).
"""

from __future__ import annotations

import random

import numpy as np

from ..assets.tiled import LevelObject, ns_bool, ns_float
from ..core.messages import MessageBus, Params
from ..world.surface import s3d_playing
from .agent import GameAgent
from .player import play

_F32 = np.float32

FADE_STEP_TIME = 0.01            # the step is computed for the 10 ms pump
END_MUSIC_LEAD = 0.2             # PlayEndMusic 0.2 s before the end
PICTURE_RETREAT = '18_SPEECH_papa_picture_retreat_'


class SoundAgent(GameAgent):
    """`PGESound`."""

    kind = 'sound'

    def __init__(self, bus: MessageBus, world, obj: LevelObject | None = None,
                 rng: random.Random | None = None) -> None:
        self.looping = False
        self.spatialized = False
        self.skippable = False
        self.on_x_rail = False
        self.on_y_rail = False
        self.on_inactive_rail = False
        self.final_gain = 1.0
        self.fade_in_time = 0.0
        self.needs_fade_in = False
        self.preload_end_music = False
        self.started_end_music = False
        self._last_player = None
        #: REQUESTED (tester, 2026-09-26), set in world/level.py
        #: REQUESTED_DATA: a looping sound that waits this long between passes
        #: (0 = the original's back-to-back loop).
        self.repeat_gap = 0.0
        self._generation = 0
        super().__init__(bus, world, obj, rng)
        self.unpausable = True                    # init: setUnpausable:
        bus.subscribe('PGE_INPUT_DoubleTap', self._on_double_tap)

    def build(self, obj: LevelObject) -> None:
        super().build(obj)
        a = obj.applied
        for key, attr, conv in (
            ('looping', 'looping', ns_bool),
            ('spatialized', 'spatialized', ns_bool),
            ('skippable', 'skippable', ns_bool),
            ('onXrail', 'on_x_rail', ns_bool),
            ('onYrail', 'on_y_rail', ns_bool),
            ('onInactiveRail', 'on_inactive_rail', ns_bool),
            ('finalGain', 'final_gain', ns_float),
            ('fadeInTime', 'fade_in_time', ns_float),
            ('preloadEndMusic', 'preload_end_music', ns_bool),
        ):
            if key in a:
                setattr(self, attr, conv(a[key]))

    # ----------------------------------------------------------- activate
    def activate(self) -> None:
        """`-[PGESound activate]` (0x100032ab4)."""
        if self.intro_sound:
            s = self.play_sound(self.intro_sound, False)
            if s is not None and self.world is not None:
                def monitor(pos, dur):
                    if pos >= dur:
                        def after():
                            super(SoundAgent, self).activate()
                            self.create_spatialized_sound()
                        self.bus.dispatch_async(after)
                        return True
                    return False
                self.world.monitors.add(s, monitor, self)
            return
        super().activate()
        self.bus.dispatch_async(self.create_spatialized_sound)

    def play_sound(self, name: str, looping: bool):
        """`playSound:looping:` - by prefix, placed here, played."""
        if self.bank is None:
            return None
        if self.sound is not None and self.sound.playing:
            self.sound.stop()
        s = self.bank.any_sound_with_prefix(name)
        self.sound = s
        if s is None:
            return None
        self.update_spatialized_sound()
        self.setup_reverb_parameters()
        s.gain = self.gain
        play(s, looping)
        return s

    def create_spatialized_sound(self) -> None:
        """`createSpatializedSound` (0x10003341c)."""
        if not self.sounds:
            return
        name = self.sounds[self.rand() % len(self.sounds)]
        if self.world is not None and name in getattr(self.world, 'suppressed_lines', ()):
            # REQUESTED: a line the player has switched off (the Intro's skip
            # explanation) counts as heard at once - its OnSoundEnd carries on.
            self.trigger_on_sound_end()
            return
        if self.sound_priority >= 1:
            if self.sound_priority <= (self.world.highest_priority_playing_sound()
                                       if self.world is not None else 0):
                self.trigger_on_sound_end()
                return
            self.bus.post('PGE_MESSAGE_StartedSoundWithPriority',
                          {'name': self.name, 'priority': self.sound_priority})
        if self.preload_end_music:
            self.bus.post('PGE_MESSAGE_PreloadEndMusic', {})
        if self.sound is not None:
            self.sound.stop()
        s = None
        bank = self.bank
        # 0x10003371c: Papa's retreat line is the one for the pictures taken so
        # far - no VoiceOver take, no animal rule
        picture = name.startswith(PICTURE_RETREAT)
        if picture:
            if bank is not None:
                n = getattr(self.world, 'pictures_taken', 0) if self.world is not None else 0
                s = bank.any_sound_with_prefix('%s%d' % (name, n))
        elif bank is not None:
            w = self.world
            if w is not None and (w.voice_over or name in getattr(w, 'always_blind', ())):
                s = bank.any_sound_with_prefix('blind_%s' % name)
            if s is None:
                s = bank.sound(name)
            if s is None:
                s = bank.any_sound_with_prefix(name)
        self.sound = s
        if not picture and s is not None and 'randomAnimal' in (s.name or '') and s3d_playing(s):
            # 0x1000339e4: an animal sound another agent is playing already -
            # this one skips its turn: OnSoundEnd at once, and no sound.
            self.trigger('OnSoundEnd')
            self.sound = None
            return
        if s is None:
            return
        self.setup_reverb_parameters()
        s.spatialized = self.spatialized
        if self.spatialized:
            self.update_spatialized_sound()
        s.gain = self.gain
        self._generation += 1
        play(s, self.looping and not self.repeat_gap)
        step = 0.0
        if self.fade_in_time > 0 and _F32(self.gain) != _F32(self.final_gain):
            steps = _F32(self.fade_in_time) / _F32(FADE_STEP_TIME)
            step = float(_F32(1.0) / _F32(steps / _F32(self.final_gain - self.gain)))
            self.needs_fade_in = True
        if self.world is not None:
            self.world.monitors.add(s, self._make_monitor(s, step), self)
            hook = getattr(self.world, 'on_line_ended', None)
            if self.looping and hook is not None:
                # port-side: a looping prompt's PC version follows its first pass
                said = []

                def first_pass(sound=s):
                    if not said and self.sound is sound:
                        said.append(1)
                        hook(sound.name)
                self.world.monitors.add_end_callback(s, first_pass, self)
        if self.skippable and self._active:
            self.bus.post('PGE_MESSAGE_ShowSkipButton', {'sender': self.name})

    def _make_monitor(self, sound, step: float):
        def monitor(pos, dur):
            if self.force_stop_callback or self.sound is not sound:
                return True
            if (self.preload_end_music and not self.started_end_music
                    and dur - END_MUSIC_LEAD <= pos):
                self.bus.post('PGE_MESSAGE_PlayEndMusic', {})
                self.started_end_music = True
            if abs(float(_F32(sound.gain) - _F32(self.final_gain))) > 0.01 and step > 0:
                if self.needs_fade_in:
                    sound.gain = float(_F32(sound.gain) + _F32(step))
                    if abs(float(_F32(sound.gain) - _F32(self.final_gain))) <= 0.01:
                        self.needs_fade_in = False
            if self.looping and self.repeat_gap and pos >= dur:
                gen = self._generation
                self.bus.call_after(self.repeat_gap, lambda: self._repeat(sound, gen))
                return True
            if not self.looping and pos >= dur:
                hook = getattr(self.world, 'on_line_ended', None)
                if hook is not None:
                    hook(sound.name)
                self.bus.dispatch_async(self.trigger_on_sound_end)
                return True
            return False
        return monitor

    def _repeat(self, sound, gen: int) -> None:
        """The next pass of a `repeat_gap` loop, if nothing has replaced it."""
        if (not self._active or self.force_stop_callback or self.sound is not sound
                or gen != self._generation or self.world is None):
            return
        if self.spatialized:
            self.update_spatialized_sound()
        play(sound, False)
        self.world.monitors.add(sound, self._make_monitor(sound, 0.0), self)

    # ---------------------------------------------------------------- end
    def trigger_on_sound_end(self) -> None:
        """`triggerOnSoundEnd` (0x10003435c)."""
        if self.skippable:
            self.bus.post('PGE_MESSAGE_RemoveSkipButton', {'sender': self.name})
        self.trigger('OnSoundEnd')

    def _on_double_tap(self, _n, _p) -> None:
        """`onDoubleTap` (0x100034400) - the skip."""
        if not (self.skippable and self._active):
            return
        if self.sound is None or not self.sound.playing:
            return
        self.bus.post('PGE_MESSAGE_RemoveSkipButton', {'sender': self.name})
        self.sound.stop()
        if self.world is not None:
            self.world.monitors.remove_sound(self.sound)
        if self.has_trigger('OnSkip'):
            self.trigger('OnSkip')
        else:
            self.trigger_on_sound_end()

    def deactivate(self) -> None:
        """`-[PGESound deactivate]`: the skip button goes with it."""
        if self.skippable:
            self.bus.post('PGE_MESSAGE_RemoveSkipButton', {'sender': self.name})
        super().deactivate()

    # --------------------------------------------------------------- rails
    def _player_moved(self, name, params: Params) -> None:
        """`-[PGESound playerMovedToPosition:]` (0x100033140): rails, then super."""
        pos = params.get('position', (0.0, 0.0))
        new = (float(pos[0]), float(pos[1]))
        old = self.player_position
        if old[0] != 0.0 and old[1] != 0.0:
            if self.on_x_rail and (self._active or self.on_inactive_rail):
                self.position = ((new[0] - old[0]) + self.position[0], self.position[1])
            if self.on_y_rail and (self._active or self.on_inactive_rail):
                self.position = (self.position[0], (new[1] - old[1]) + self.position[1])
            if self.on_x_rail or self.on_y_rail:
                self.send_did_move_message()      # on a rail, moved or not
        super()._player_moved(name, params)
