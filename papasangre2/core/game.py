"""The game around the level: `PGEngine` and the view controllers' audio.

What this owns, each recovered (docs/notes/M2_NOTES.md):

* **loading** (`-[PGEngine loadLevelWithName:]`, 0x100047100): a
  `LoadLevelWithName` for another level is a **win** - the level is completed,
  the next unlocked, `PresentWinVC`; for the same level it is a **loss** -
  `PresentLoseVC` with the death cause; the shell answers both with the
  after-level screen (decision 5);
* **the menu audio** in the `ps2_menu` playlist: UI sounds at most one per
  0.1 s and never over themselves (`playUiSoundWithName:`), the menu
  atmosphere `menu_death_atmos` faded in over 3 s to 0.5 and out over 2 s on
  `FadeOutMenuAtmos`, and the end music `<level>_end_music_loop` at 0.4 when a
  level asks for it (`playEndMusicForCurrentLevel`);
* **the skip button** (`-[PGEStepsViewController showSkipButton]` /
  `skipButtonPressed:`): shown while a skippable line plays; pressing it posts
  `PGE_INPUT_DoubleTap` and clicks; with VoiceOver on, 1.0 s after it appears
  the **skip ping** plays - here only while the Skip ping setting is on;
* **the pause text** (`SetPauseText`, a key into the hub list's texts);
* the two port-side hooks the settings need: lines switched off (the Skip
  explanation setting) and the spoken PC equivalents after tutorial lines.
"""

from __future__ import annotations

import os
import random
import time

from ..assets import pack
from ..assets.hublist import load_hub_list
from ..assets.tiled import level_path, load_level, ns_float
from ..audio.monitor import MonitorPump
from ..entities.player import level_number
from ..input.device import Phone
from ..input.interpreter import MoveInterpretor
from ..save.achievements import check_achievements_for_level, update_stats_and_achievements
from ..save.tracker import GameTracker
from ..assets import requested
from ..world import requested as requested_lines
from ..world.level import Level, TICK
from .messages import MessageBus, Params

MENU_PLAYLIST = 'ps2_menu'
MENU_ATMOS = 'menu_death_atmos'
ATMOS_GAIN = 0.5            # playAtmosWithName: / fadeInMenuAtmos: target
ATMOS_FADE_IN = 3.0         # playMenuAtmos: fadeInMenuAtmos:3
ATMOS_FADE_OUT = 2.0        # fadeOutMenuAtmosMessageReceived: fadeOutMenuAtmos:2
ATMOS_STEP = 0.05           # the fade timers' interval
END_MUSIC_GAIN = 0.4
END_MUSIC_FALLBACK = 'ps2_2'
UI_SOUND_GAP = 0.1          # playUiSoundWithName: |interval| < 0.1 -> skip
SKIP_PING_DELAY = 1.0       # showSkipButton: dispatch_after 1,000,000,000 ns
SKIP_PING = 'skipButtonAppeared'
#: The Intro's record-player line that explains the skip ping (Settings,
#: "Skip explanation").  Both takes: the VoiceOver one is picked first.
SKIP_EXPLANATION_LINES = ('ps2_skip_tuto', 'blind_ps2_skip_tuto')
#: playFailSoundForLevel:deathCause: - the menu death atmosphere 0.7 s after
#: the narration ends (dispatch_after 700,000,000 ns).
DEATH_ATMOS_DELAY = 0.7
#: ... and levels up to 5 fall back on a lost memory, 1 to 25 in turn.
LOST_MEMORY_MAX_LEVEL = 5
LOST_MEMORY_WRAP = 26


class Game:
    """One sitting: the persistent bus and controls, and the current level."""

    def __init__(self, bundle: str, progress, settings, bank_factory,
                 menu_bank=None, say=None, rumble=None, engine=None,
                 tutorial_lines=None, rng: random.Random | None = None,
                 ui_clock=None) -> None:
        self.bundle = bundle
        self.progress = progress
        self.settings = settings
        self.bank_factory = bank_factory
        self.menu_bank = menu_bank
        self.say = say or (lambda text: None)
        self.rumble = rumble or (lambda: None)
        self.engine = engine
        self.tutorial_lines = tutorial_lines or {}
        self.rng = rng or random.Random()
        #: The UI sounds' 0.1 s spacing is wall-clock time in the original
        #: (NSDate), so it keeps working in the menus, where no game time
        #: passes.  Tests hand in their own clock.
        self.ui_clock = ui_clock or time.monotonic
        self.bus = MessageBus()
        self.interpreter = MoveInterpretor(self.bus)
        #: how the (imaginary) phone is held - Up / Down keys (decision 1)
        self.phone = Phone(self.bus)
        self.level: Level | None = None
        self.bank = None
        self.level_name = ''
        self.hub = {e.file_name: e for e in load_hub_list(bundle)}
        self.outcome = None               # ('win', level, next) | ('lose', level, cause)
        self.skip_button = False
        self.pause_text = ''
        self.now = 0.0
        self._tick_acc = 0.0
        self.atmos = []                   # (sound, gain target) of the menu atmosphere
        self._fade = None                 # ('in'|'out', step)
        self._last_ui = None
        self.history: list[str] = []
        #: `PGEGameTracker`: the counters the achievements read.
        self.tracker = GameTracker(self.bus)
        #: the level achievement the last win earned, if any
        self.earned_achievement: str | None = None
        #: The menu audio's own clock: the death narration and the timers
        #: after it keep running on the after-level screen, where no game
        #: time passes (dispatch_after and S3D monitors run on real time).
        self.menu_now = 0.0
        self.menu_monitors = MonitorPump()
        self._menu_timers: list[tuple[float, object]] = []
        self.atmos_voice_over = None
        for name, handler in (
            ('PGE_MESSAGE_LoadLevelWithName', self._load_level_with_name),
            ('PGE_MESSAGE_PreloadEndMusic', lambda *_: None),
            ('PGE_MESSAGE_PlayEndMusic', lambda *_: self.play_end_music()),
            ('PGE_MESSAGE_PresentAdiosVC', self._present_adios),
            ('PGE_MESSAGE_FadeOutMenuAtmos', lambda *_: self.fade_out_menu_atmos(ATMOS_FADE_OUT)),
            ('PGE_MESSAGE_ShowSkipButton', self._show_skip_button),
            ('PGE_MESSAGE_RemoveSkipButton', self._remove_skip_button),
            ('PGE_MESSAGE_SetPauseText', self._set_pause_text),
        ):
            self.bus.subscribe(name, handler)

    # ------------------------------------------------------------ levels
    def has_level(self, name: str) -> bool:
        return pack.isfile(level_path(self.bundle, name))

    def title(self, name: str) -> str:
        e = self.hub.get(name)
        return e.title if e is not None else name

    def load(self, name: str) -> Level:
        """Load a level and start it."""
        self.unload()
        self.outcome = None
        self.skip_button = False
        self.pause_text = ''
        self.level_name = name
        self.history.append(name)
        self.bank = self.bank_factory(name)
        requested.add_to(self.bank)
        requested_lines.ensure_sounds(self.bank, name)     # decision 21
        data = load_level(level_path(self.bundle, name), name)
        lv = Level(self.bus, data, bank=self.bank, voice_over=self.settings.blind_intro,
                   progress=self.progress, rng=self.rng, reverb=self._reverb)
        lv.tracker = self.tracker
        if not self.settings.skip_explanation:
            lv.suppressed_lines.update(SKIP_EXPLANATION_LINES)
        elif not self.settings.blind_intro:
            # REQUESTED (2026-09-24): the sighted take of the skip explanation
            # is 0.57 s of silence, so with Blind intro off the spoken
            # VoiceOver take plays instead; the rest of the Intro stays sighted.
            lv.always_blind.add(SKIP_EXPLANATION_LINES[0])
        lv.on_line_ended = self._line_ended
        lv.play_whoosh = self.play_whoosh
        self.level = lv
        self.interpreter.lock_controls()
        with self.bus.scope(lv.scope_key):
            lv.load()
        if lv.player is not None:
            lv.player.vibrate_fn = self.rumble
        self.progress.player_did_play_level(name)
        self.bus.update(self.now)
        return lv

    def unload(self) -> None:
        if self.level is not None:
            self.level.dispose()
            self.level = None
        if self.bank is not None:
            self.bank.stop_all()
            self.bank = None
        self.bus.clear()

    def _reverb(self, room_size, dampening, volume) -> None:
        if self.engine is None:
            return
        cur = getattr(self.engine, 'reverb_settings', (2.1, 5.0, 1.0))
        self.engine.set_reverb(room_size if room_size is not None else cur[0],
                               dampening if dampening is not None else cur[1],
                               volume if volume is not None else cur[2])

    def _load_level_with_name(self, _n, params: Params) -> None:
        """`loadLevelWithName:` (0x100047100): win, lose, or a plain load."""
        target = params.get('name')
        current = self.level_name
        if not target:
            return
        if target != current:
            self.progress.player_did_complete_level(current)
            self.progress.player_did_unlock_level(target)
            self.earned_achievement = check_achievements_for_level(
                self.progress, self.tracker, current)
            self.outcome = ('win', current, target)
        else:
            cause = params.get('deathCause') or ''
            self.outcome = ('lose', current, cause)
            self.present_lose(current, cause)
        update_stats_and_achievements(self.progress, self.tracker)

    def _present_adios(self, _n, _p) -> None:
        """`-[PGEViewController presentAdiosVC]` (0x10005e73c): the end of the
        game (ps2_18b).  Out of gameplay, and the Adios screen - no level
        loaded, so no win, no achievement check, nothing saved."""
        if self.outcome is None:
            self.outcome = ('end', self.level_name, None)

    # ------------------------------------------------------------- death
    def present_lose(self, level: str, cause: str) -> None:
        """`-[PGEViewController presentLoseVC:]` (0x10005e430): the lose
        screen counts the death (`checkFails` -> `failedLevel:`) and the
        engine plays the death narration."""
        self.progress.failed_level(level)
        self.play_fail_sound_for_level(level_number(level), cause, level)

    def end_of_level_sounds_for_death_cause(self, cause: str, level: str) -> list[str]:
        """`endOfLevelSoundsForDeathCause:` (0x10004972c), in playlist order."""
        if self.menu_bank is None:
            return []
        prefix = f'{level}_fail_{cause}' if cause else f'{level}_fail'
        return self.menu_bank.names_in_order(prefix)

    def unplayed_end_of_level_sound(self, n: int, cause: str, level: str) -> str | None:
        """`unplayedEndOfLevelSoundForLevel:deathCause:` (0x100049398)."""
        sounds = self.end_of_level_sounds_for_death_cause(cause, level)
        played = [s for s in sounds if self.progress.has_played_level_end_sound(s)]
        left = [s for s in sounds if s not in played]
        if left:
            return left[0]
        if n >= 5 and played:
            return played[self.rng.randrange(len(played))]
        return None

    def play_fail_sound_for_level(self, n: int, cause: str, level: str) -> str | None:
        """`playFailSoundForLevel:deathCause:` (0x100048e90).

        A narration for this level (and cause) not heard yet; failing that,
        for levels up to 5, the next lost memory (1 to 25, then round again).
        When it ends, 0.7 s later, the menu's death atmosphere.
        """
        name = self.unplayed_end_of_level_sound(n, cause, level)
        if n <= LOST_MEMORY_MAX_LEVEL and not name:
            self.progress.memories_lost = self.progress.memories_lost + 1
            if self.progress.memories_lost >= LOST_MEMORY_WRAP:
                self.progress.memories_lost = 1
            name = 'lost_memory_%i_UOS' % self.progress.memories_lost
        elif name:
            self.progress.just_played_level_end_sound(name)
        if not name or self.menu_bank is None:
            return name
        s = self.menu_bank.sound(name)
        if s is None:
            return name
        self.atmos_voice_over = s
        self.atmos.append(s)
        s.spatialized = False
        s.gain = 1.0
        s.looping = False
        s.play()

        def ended(pos, dur):
            if pos < dur:
                return False
            self.call_menu_later(DEATH_ATMOS_DELAY, self.play_menu_death_atmos)
            return True
        self.menu_monitors.add(s, ended, self)
        return name

    def play_menu_death_atmos(self) -> None:
        """`playMenuDeathAtmos` - `playAtmosWithName:` + `fadeInMenuAtmos:3`."""
        self.play_menu_atmos()

    # -------------------------------------------------------- menu clock
    def call_menu_later(self, delay: float, fn) -> None:
        self._menu_timers.append((self.menu_now + float(delay), fn))

    def menu_update(self, dt: float) -> None:
        """The menu audio's time: its monitors, its timers, its fades."""
        self.menu_now += dt
        self.menu_monitors.advance(dt)
        if self._menu_timers:
            due = [t for t in self._menu_timers if t[0] <= self.menu_now]
            if due:
                self._menu_timers = [t for t in self._menu_timers if t[0] > self.menu_now]
                for _when, fn in sorted(due, key=lambda t: t[0]):
                    fn()
        self._update_fade(dt)

    # ------------------------------------------------------------ the loop
    def update(self, dt: float) -> None:
        """Advance game time: the 10 ms monitors, the 0.05 s tick, the bus."""
        steps = max(1, int(round(dt / 0.01))) if dt > 0 else 0
        for _ in range(steps):
            self.now += 0.01
            self.bus.now = self.now
            lv = self.level
            if lv is not None and not lv.paused_game:
                lv.monitors.advance(0.01)
                self._tick_acc += 0.01
                while self._tick_acc >= TICK - 1e-9:
                    self._tick_acc -= TICK
                    lv.tick()
            self.menu_update(0.01)
            self.bus.update(self.now)
        self.sync_listener()

    def sync_listener(self) -> None:
        if self.engine is None or self.level is None or self.level.player is None:
            return
        p = self.level.player
        self.engine.set_listener(p.position, p.bearing_degrees)
        if self.bank is not None:
            self.engine.update_positions(self.bank.live_sounds())

    @property
    def finished(self) -> bool:
        return self.outcome is not None

    # ------------------------------------------------------------ pausing
    def pause(self) -> None:
        """`-[PGELevel pause:]`: the clock stops and the sounds hold."""
        lv = self.level
        if lv is None or lv.paused_game:
            return
        lv.paused_game = True
        self._paused_sounds = [s for s in self.bank.live_sounds() if s.playing] if self.bank else []
        for s in self._paused_sounds:
            s.pause()

    def resume(self) -> None:
        lv = self.level
        if lv is None or not lv.paused_game:
            return
        lv.paused_game = False
        for s in getattr(self, '_paused_sounds', []):
            s.resume()
        self._paused_sounds = []

    # ------------------------------------------------------------ the skip
    def _show_skip_button(self, _n, _p) -> None:
        self.skip_button = True
        if self.settings.skip_ping:
            self.bus.call_after(SKIP_PING_DELAY, lambda: self.play_ui_sound(SKIP_PING))

    def _remove_skip_button(self, _n, _p) -> None:
        self.skip_button = False

    def skip(self) -> bool:
        """`skipButtonPressed:` - only while the button is there to press."""
        if not self.skip_button:
            return False
        self.bus.post('PGE_INPUT_DoubleTap', {})
        self.skip_button = False
        self.play_ui_sound('click_button')
        self.bus.update(self.now)
        return True

    def _set_pause_text(self, _n, params: Params) -> None:
        e = self.hub.get(self.level_name)
        key = params.get('name')
        self.pause_text = (e.texts.get(key, '') if e is not None else '') if key else ''

    # --------------------------------------------------------- tutorial
    def _line_ended(self, sound_name: str) -> None:
        """Decision 8: after a tutorial line, the same instruction for a PC
        - unless PC instructions is switched off in Settings."""
        if not self.settings.pc_instructions:
            return
        text = self.tutorial_lines.get(sound_name)
        if text:
            self.say(text() if callable(text) else text)

    def play_whoosh(self) -> None:
        """Decision 14: the game's own `whoosh` (menu buttons playlist, which
        the original never plays) for each shake a memory takes; flat, from
        the start on every press.  Settings can switch it off (Shake sound)."""
        if not getattr(self.settings, 'shake_whoosh', True):
            return
        s = self.menu_bank.sound('whoosh') if self.menu_bank is not None else None
        if s is None:
            return
        s.stop()
        s.spatialized = False
        s.gain = 1.0
        s.looping = False
        s.play()

    # ------------------------------------------------------------ menu audio
    def play_ui_sound(self, name: str) -> None:
        """`playUiSoundWithName:` (0x10004a594)."""
        now = self.ui_clock()
        if self._last_ui is not None and abs(now - self._last_ui) < UI_SOUND_GAP:
            return
        s = self.menu_bank.sound(name) if self.menu_bank is not None else None
        if s is None or s.playing:
            return
        self._last_ui = now
        s.spatialized = False
        s.gain = 1.0
        s.looping = False
        s.play()

    def play_menu_atmos(self) -> None:
        """`playMenuAtmos`: menu_death_atmos, faded in over 3 s.

        `playAtmosWithName:` first calls `stopMenuAtmos`, which stops and
        forgets every atmosphere sound - the end music, a death narration.
        """
        s = self.menu_bank.sound(MENU_ATMOS) if self.menu_bank is not None else None
        if s is None:
            return
        for old in self.atmos:
            if old is not s:
                old.stop()
        self.atmos = [s]
        s.spatialized = False
        s.looping = True
        s.gain = 0.0
        if not s.playing:
            s.play()
        self._fade = ('in', ATMOS_STEP / ATMOS_FADE_IN * ATMOS_GAIN, ATMOS_FADE_IN)

    def fade_out_menu_atmos(self, duration: float) -> None:
        """`fadeOutMenuAtmos:` (0x100049ba8)."""
        if not self.atmos:
            return
        g = max((s.gain for s in self.atmos), default=0.0)
        self._fade = ('out', g * ATMOS_STEP / duration, duration)

    def _update_fade(self, dt: float) -> None:
        if self._fade is None:
            return
        kind, step, left = self._fade
        left -= dt
        # the original steps every 0.05 s; stepping per 10 ms by a fifth is the same ramp
        for s in self.atmos:
            if kind == 'in':
                s.gain = min(ATMOS_GAIN, s.gain + step * dt / ATMOS_STEP)
            else:
                s.gain = max(0.0, s.gain - step * dt / ATMOS_STEP)
        if left <= 0:
            if kind == 'out':
                for s in self.atmos:
                    s.stop()
                self.atmos = []
            self._fade = None
        else:
            self._fade = (kind, step, left)

    def play_end_music(self) -> None:
        """`playEndMusicForCurrentLevel` (0x100047f1c)."""
        if self.menu_bank is None:
            return
        s = self.menu_bank.sound('%s_end_music_loop' % self.level_name)
        if s is None:
            s = self.menu_bank.sound('%s_end_music_loop' % END_MUSIC_FALLBACK)
        if s is None:
            return
        self._fade = None
        self.atmos = [s]
        s.spatialized = False
        s.looping = True
        s.gain = END_MUSIC_GAIN
        s.play()

    def stop_menu_audio(self) -> None:
        for s in self.atmos:
            s.stop()
        self.atmos = []
        self._fade = None
