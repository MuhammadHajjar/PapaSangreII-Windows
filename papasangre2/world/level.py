"""`PGELevel` as Papa Sangre II has it - the room, its floors, agents and clock.

docs/notes/M2_NOTES.md ("PGELevel") has the addresses.  The level **is a
surface** (the room) and is the first entry of its own floor list, so:

* `surfaceForPosition:` always finds at least the room inside the room's
  rectangle (highest `z` wins, ties go to the first, only active floors);
* the room's `OnEnter` fires the first time the player stands where no
  higher floor is active - at the spawn point in most levels;
* each 0.05 s tick updates every floor **including the room**, and then the
  room once more - so the room's delayed triggers count down at double speed.

The tick (`-[PGELevel update]`, NSTimer 0.05 s): agents `update:0.05` in load
order; floors `update:0.05`; the player `update:0.1` every other tick; the
player's underwater clock; the room again; the tracker's `timeElapsed`.

Agent activity: the loader sets an agent's `active` through KVC and again from
a block 0.05 s later.  On a device the load itself takes longer than that, so
those blocks have all run before the level's first triggers are delivered (the
opening lines of every level start at load and would be cut off otherwise).
The port runs them as main-queue blocks queued at load, which lands them in
the same place: before the first idle notification.  PORT-SIDE, recorded in
DIVERGENCES.md.
"""

from __future__ import annotations

import math
import random

import numpy as np

from ..assets.tiled import LevelData, LevelObject, ns_bool, ns_float
from ..audio.monitor import MonitorPump
from ..core.messages import MessageBus, Params
from ..entities.agent import GameAgent
from ..entities.collectible import Collectible
from ..entities.enemy import Enemy
from ..entities.follower import Follower
from ..entities.player import Player
from ..entities.sound_agent import SoundAgent
from . import requested
from .surface import Surface, rect_contains

TICK = 0.05
PLAYER_TICK = 0.1
#: loadLevelStructure/Agents/Player's 0.05 s `active` block (50,000,000 ns).
ACTIVE_DELAY = 0.05
#: actuallyLoadDataFromJsonFile: FadeOutMenuAtmos + RemoveFullScreenImage.
MENU_ATMOS_DELAY = 5.0

#: REQUESTED changes to the shipped level data, by (level, object): Muhammad's
#: decisions, listed in docs/DIVERGENCES.md.
#:   decision 13: ps2_5a's shake memory takes the reach every other shake
#:   target in the game has (1000 px) instead of the default 10, which left a
#:   player who reached Papa from his north-east side unable ever to shake it.
#: REQUESTED (decision 21): the idle hints are heard.  The original never
#: plays them - `inactivityTime` stays +inf, no level changes it, and nothing
#: the player does resets the clock.  Here a level with hints plays the next
#: one after IDLE_HINT_TIME s without a step, while walking is allowed and
#: nobody is talking; it stays silent otherwise.  Each hint plays once.
IDLE_HINT_TIME = 30.0

REQUESTED_DATA = {
    ('ps2_5a', 'intro2_collectible'): {'collide_radius': 1000.0},
    # the tester, 2026-09-26: the sparkler collects when you reach it, like
    # every memory - not at the end of its 8 s loop (so you had to stand on it)
    ('ps2_3', 'easter_egg'): {'ignore_loop': True},
    # the submarine's power going (the large explosion) plays flat, not placed
    # 120 px off; the gain is what it was heard at from there (rendered)
    ('ps2_9', 'explosion_large'): {'spatialized': False, 'gain': 0.7},
    # the collapsing house comes after you from its start sound on, and its
    # loop takes over as that sound fades (1.5 s before its end)
    ('ps2_14', 'explosions'): {'chase_during_intro': True, 'intro_lead': 1.5},
    # the burning oil can: sprayable from the 80 px its data asks for (the
    # original reads beatRange nowhere - 30 px), in the wider cone ps2_14's
    # second door has (0.8), and from right on top of it whatever the angle
    ('ps2_14', 'can'): {'beat_radius': 80.0, 'beat_dot_prod': 0.8, 'close_reach': 10.0},
    # "Jump! Use both feet at the same time!" - every 22 s, not every 7.5 s,
    # while you are near the ice killing penguins
    ('ps2_15', 'real_jump_prompt'): {'repeat_gap': 15.0},
    # the hold music: at the data's gain 1 it was as loud as the voice over it
    # (measured: 0.035 a channel against 0.034); 6 dB under it
    ('ps2_18b', 'music'): {'gain': 0.5},
    # The museum music behind the Intro's last door (INTRO_door_closed_loop_SPA)
    # played flat, in your head: its data never says spatialized, and the
    # original's default is NO - so it did there too.  The owner and the tester
    # (2026-09-27): it must come from the door, and be heard from anywhere in
    # the garden, since it is how you find your way there.  Placed, then, at
    # gain 36 with a ceiling of 5 after distance (rendered: ahead of you it is
    # 0.029 a channel up close, 0.025 at 200 px, 0.016 at 400 px - a voice line
    # is 0.05; the data's gain 7 under OpenAL's usual ceiling of 1 would have
    # been 0.005 everywhere).
    ('ps2_Intro', 'door_closed'): {'spatialized': True, 'final_gain': 36.0, 'max_gain': 5.0},
}

AGENT_CLASSES = {
    'Sound': SoundAgent,
    'Collectible': Collectible,
    'Monster': Enemy,
    'Follower': Follower,
}


class Path:
    """`PGEPath`: a name and a polyline."""

    def __init__(self, name: str, points) -> None:
        self.name = name
        self.points = [(float(x), float(y)) for x, y in points]

    def __len__(self) -> int:
        return len(self.points)


class Level(Surface):
    """One loaded level."""

    kind = 'level'

    def __init__(self, bus: MessageBus, data: LevelData, bank=None,
                 voice_over: bool = True, progress=None,
                 rng: random.Random | None = None, vibrate=None,
                 reverb=None) -> None:
        super().__init__(bus, data.rect, surface_id=0, z=0, name=data.name, rng=rng)
        self.world = self
        self.data = data
        self.bank = bank
        self.voice_over = voice_over
        #: Lines that take their ``blind_`` (VoiceOver) take even when
        #: ``voice_over`` is off - REQUESTED, see Game.load.
        self.always_blind: set[str] = set()
        self.progress = progress
        self.reverb_fn = reverb
        self.monitors = MonitorPump()
        self.collectibles_collected = 0
        #: the run's `PGEGameTracker` (set by the game before load)
        self.tracker = None
        #: REQUESTED: lines switched off in Settings (heard at once).
        self.suppressed_lines: set[str] = set()
        #: Called with a sound's name when a narration line plays to its end.
        self.on_line_ended = None
        #: Plays the menu's whoosh for a shake a memory takes (decision 14).
        self.play_whoosh = None
        # -- init
        self.inactivity_time = math.inf
        self.last_activity = bus.now
        self.inactivity_sounds: list[str] = []
        self.current_inactivity_sound = 0
        self.inactivity_sound = None
        self.hit_wall_sound = 'hitwall'
        self.player_update_value = 0
        self.shut_down = False
        self.paused_game = False
        #: picturesTaken: Papa beaten so far (-[PGEEnemy wasBeaten], ps2_18)
        self.pictures_taken = 0
        self.floors: list[Surface] = [self]
        self.agents: list[GameAgent] = []
        self.paths: list[Path] = []
        self.player: Player | None = None
        #: The engine builds the level inside ``bus.scope(scope_key)``.
        self.scope_key = ('level', id(self))
        self._subs = []
        for name, handler in (
            ('PGE_MESSAGE_PlayerMovedToPosition', self._player_moved),
            ('PGE_MESSAGE_ShutDownLevel', self._shut_down_level),
            ('PGE_MESSAGE_ChangeReverbSettings', self._change_reverb_settings),
            ('PGE_MESSAGE_ChangeInactivitySoundList', self._change_inactivity_sound_list),
            ('PGE_MESSAGE_ChangeInactivityTime', self._change_inactivity_time),
            ('PGE_MESSAGE_DeallocAgentWithName', self._dealloc_agent_with_name),
            ('PGE_MESSAGE_EnableWalk', lambda *_: self._set_can_walk(True)),
            ('PGE_MESSAGE_DisableWalk', lambda *_: self._set_can_walk(False)),
            ('PGE_MESSAGE_SetControlSettingsToDefault', lambda *_: self._set_can_walk(True)),
        ):
            bus.subscribe(name, handler)
            self._subs.append((name, handler))
        #: decision 21: whether the player may walk, for the idle hints
        self.can_walk = False

    # ------------------------------------------------------------ building
    def load(self, rng: random.Random | None = None) -> None:
        """loadLevelStructure: / loadLevelAgents: / loadPlayer:, then LevelInited."""
        d = self.data
        rng = rng or self.rng
        requested.apply(d)                  # decision 21: Muhammad's additions
        # -- structure: the room, then every surface
        self.apply(d.room)
        self.z = int(ns_float(d.room.applied.get('z', 0)))
        if d.inactivity_sound_list:
            self._change_inactivity_sound_list(None, {'soundList': d.inactivity_sound_list})
        if self.reverb_fn is not None:
            self.reverb_fn(*d.reverb)
        for obj in d.floors:
            s = Surface(self.bus, obj.rect, obj.surface_id, obj.z, obj.is_circle,
                        name=obj.name, rng=rng, world=self)
            s.level_name = self.name
            s.position = (obj.x, obj.y)
            s.apply(obj)
            s.on_activated = self.surface_was_activated
            self.floors.append(s)
        for obj in d.paths:
            self.paths.append(Path(obj.name, obj.polyline))
        # -- agents
        for obj in d.agents:
            cls = AGENT_CLASSES.get(obj.type, GameAgent)
            a = cls(self.bus, self, obj, rng=rng)
            for attr, value in REQUESTED_DATA.get((self.name, obj.name), {}).items():
                setattr(a, attr, value)
            a.agent_id = obj.agent_id
            a.playlist_name = self.name
            self.agents.append(a)
            if 'active' in obj.applied and ns_bool(obj.applied['active']):
                a.set_active(True)                      # the KVC pass
            want = ns_bool(obj.applied['active']) if 'active' in obj.applied else False
            self.bus.dispatch_async(lambda a=a, want=want: a.set_active(want))
        # -- player
        if d.player is not None:
            p = Player(self.bus, level=self, bank=self.bank, progress=self.progress, rng=rng)
            p.position = (d.player.x, d.player.y)
            self.player = p
            p.apply(d.player)
            self.bus.post('PGE_MESSAGE_SetControlSettingsToDefault', {})
            self.bus.post('PGE_MESSAGE_MovePlayerToPosition', {'position': p.position})
        self.bus.post('PGE_MESSAGE_LevelInited', {'level': self})
        self.bus.call_after(MENU_ATMOS_DELAY, self._after_load)

    def _after_load(self) -> None:
        self.bus.post('PGE_MESSAGE_FadeOutMenuAtmos', {})
        self.bus.post('PGE_MESSAGE_RemoveFullScreenImage', {})

    def path_with_name(self, name) -> Path | None:
        for p in self.paths:
            if p.name == name:
                return p
        return None

    def agent(self, name: str) -> GameAgent | None:
        for a in self.agents:
            if a.name == name:
                return a
        return None

    # ------------------------------------------------------------ floors
    def surface_for_position(self, x: float, y: float) -> Surface | None:
        """`surfaceForPosition:` (0x10003fedc)."""
        best = None
        best_z = -2 ** 31
        for f in self.floors:
            if not rect_contains(f.rect, x, y):
                continue
            if f.z <= best_z:
                continue
            if not f.active:
                continue
            if f.is_circle and not f.circle_contains(x, y):
                continue
            best, best_z = f, f.z
        return best

    def _current_surface(self) -> Surface | None:
        cur = None
        for f in self.floors:
            if f.player_is_on_surface:
                cur = f
        return cur

    def can_player_move_to_position(self, x: float, y: float) -> bool:
        """`canPlayerMoveToPosition:` (0x1000402f4)."""
        if not rect_contains(self.rect, x, y):
            return False
        cur = self._current_surface()
        tgt = self.surface_for_position(x, y)
        cid = cur.surface_id if cur is not None else 0
        tid = tgt.surface_id if tgt is not None else 0
        if cid == tid:
            return True
        if (cur is not None and cur.is_walled) or (tgt is not None and tgt.is_walled):
            return False
        return True

    def compute_player_moved_to_position(self, x: float, y: float, just_stepped: bool) -> None:
        """`computePlayerMovedToPosition:justStepped:` (0x1000406dc)."""
        p = self.player
        prefix = p.footsteps_prefix if p is not None else None
        cur = self._current_surface()
        tgt = self.surface_for_position(x, y)
        tid = tgt.surface_id if tgt is not None else 0
        if cur is not None and cur.surface_id == tid:
            if just_stepped and tgt is not None:
                tgt.trigger_on_step()
            if tgt is not None and tgt.footsteps_prefix is not None:
                prefix = tgt.footsteps_prefix
        else:
            if cur is not None:
                cur.player_is_on_surface = False
                cur.trigger_on_exit()
            if tgt is not None:
                if not tgt.player_is_on_surface:
                    tgt.trigger_on_enter(just_stepped)
                tgt.player_is_on_surface = True
                if tgt.footsteps_prefix is not None:
                    prefix = tgt.footsteps_prefix
                if p is not None:
                    if tgt.trip_bpm > 0:
                        p.set_trip_bpm(tgt.trip_bpm)
                    if tgt.run_bpm > 0:
                        p.run_bpm = tgt.run_bpm
                    p.shuffle_sound = tgt.shuffle_sound if tgt.shuffle_sound is not None else ''
                    p.is_underwater = tgt.is_underwater
                    if not tgt.is_underwater:
                        p.reset_underwater_duration()
        if prefix is not None and p is not None:
            p.footsteps_prefix = prefix
        self.bus.post('PGE_MESSAGE_PlayerWalkedOnSurfaceWithId',
                      {'id': tid, 'name': tgt.name if tgt is not None else None})

    def _set_can_walk(self, value: bool) -> None:
        self.can_walk = value
        self.last_activity = self.bus.now

    def _player_moved(self, _n, params: Params) -> None:
        if params.get('justStepped'):
            self.last_activity = self.bus.now       # decision 21: a step is activity
        pos = params.get('position', (0.0, 0.0))
        self.compute_player_moved_to_position(float(pos[0]), float(pos[1]),
                                              bool(params.get('justStepped')))

    def surface_was_activated(self) -> None:
        """`surfaceWasActivated`: re-evaluate where the player stands."""
        if self.player is not None:
            self.compute_player_moved_to_position(*self.player.position, False)

    def _narrating(self) -> bool:
        """A skippable line (a narration) is playing."""
        for a in self.agents:
            s = a.sound
            if a.active and getattr(a, 'skippable', False) and s is not None and s.playing:
                return True
        return False

    # ------------------------------------------------------------ sounds
    def highest_priority_playing_sound(self) -> int:
        """`highestPriorityPlayingSound` (0x10003fc58)."""
        best = 0
        for a in self.agents:
            if a.active and a.sound is not None and a.sound.playing and a.sound_priority > best:
                best = a.sound_priority
        return best

    def _change_reverb_settings(self, _n, params: Params) -> None:
        if self.reverb_fn is None:
            return
        self.reverb_fn(ns_float(params['reverbRoomSize']) if 'reverbRoomSize' in params else None,
                       ns_float(params['reverbDampening']) if 'reverbDampening' in params else None,
                       ns_float(params['reverbVolume']) if 'reverbVolume' in params else None)

    def _change_inactivity_sound_list(self, _n, params: Params) -> None:
        self.inactivity_sounds = [s for s in str(params.get('soundList', '')).split('&')]
        self.current_inactivity_sound = 0

    def _change_inactivity_time(self, _n, params: Params) -> None:
        self.inactivity_time = ns_float(params.get('value', 0))
        self.last_activity = self.bus.now

    def play_inactivity_sound(self) -> None:
        """`playInactivitySound` - unreachable in PS2: no level sets a time."""
        if not self.inactivity_sounds or self.bank is None:
            return
        if self.inactivity_sound is not None and self.inactivity_sound.playing:
            self.inactivity_sound.stop()
        name = self.inactivity_sounds[self.current_inactivity_sound % len(self.inactivity_sounds)]
        s = self.bank.sound(name)
        self.inactivity_sound = s
        if s is None:
            return
        s.spatialized = False
        s.looping = False
        s.play()
        self.last_activity = self.bus.now + s.duration
        self.current_inactivity_sound += 1
        hook = self.on_line_ended                   # the PC version, after it
        if hook is not None:
            self.monitors.add_end_callback(s, lambda n=s.name: hook(n), self)

    # ------------------------------------------------------------ the tick
    def tick(self) -> None:
        """One `-[PGELevel update]`."""
        if self.shut_down:
            return
        if self.inactivity_sounds:
            now = self.bus.now
            if self.inactivity_sound is not None and self.inactivity_sound.playing:
                self.last_activity = now
            elif not self.can_walk or self.highest_priority_playing_sound() > 0 \
                    or self._narrating():
                self.last_activity = now            # decision 21: not idle then
            requested = self.inactivity_time == math.inf
            wait = IDLE_HINT_TIME if requested else self.inactivity_time
            # the tester (2026-09-26): each hint once - the original's own
            # clock, never started, would have gone round the list for ever
            once = not requested or self.current_inactivity_sound < len(self.inactivity_sounds)
            if once and wait < (now - self.last_activity):
                self.play_inactivity_sound()
        for a in list(self.agents):
            a.update(TICK)
        for f in list(self.floors):
            f.update(TICK)
        self.player_update_value += 1
        if self.player is not None and self.player_update_value & 1:
            self.player.update(PLAYER_TICK)
        if self.player is not None:
            self.player.increase_underwater_duration(TICK)
        self.update(TICK)                          # [self update:0.05] - the room again
        if self.tracker is not None:               # PGEGameTracker timeElapsed += 0.05
            self.tracker.time_elapsed = float(np.float32(np.float32(self.tracker.time_elapsed)
                                                         + np.float32(TICK)))

    # --------------------------------------------------------- shutting down
    def _shut_down_level(self, _n, params: Params) -> None:
        """`shutDownLevel:` (0x100041da8): everyone but the sender goes quiet."""
        sender = params.get('senderName')
        for a in self.agents:
            if a.name != sender:
                a.deactivate_with_no_callback()
                a.clear_delays()
        for f in list(self.floors):
            f.deactivate()
        if self.inactivity_sound is not None and self.inactivity_sound.playing:
            self.inactivity_sound.stop()
        self.inactivity_sounds.clear()
        # the level's own shutdown locks the player out (0x1000420d0..)
        for name in ('PGE_MESSAGE_DisableHands', 'PGE_MESSAGE_DisableWalk',
                     'PGE_MESSAGE_DisableRotation'):
            self.bus.post(name, {})

    def _dealloc_agent_with_name(self, _n, params: Params) -> None:
        """`deallocAgentWithName:` (0x100042a38): every agent of that name goes
        quiet (its timers cancelled, `deactivateWithNoCallback`, its delays
        cleared); the last of them leaves the level, and as the level held the
        last reference it is freed - it hears nothing more."""
        name = params.get('name')
        last = None
        for a in list(self.agents):
            if a.name == name:
                self.bus.cancel_owner(a)
                a.deactivate_with_no_callback()
                a.clear_delays()
                last = a
        if last is not None:
            self.agents.remove(last)
            self.monitors.remove_owner(last)
            self.bus.forget(last)

    def dispose(self) -> None:
        """Forget the level: nothing it owns may hear another message."""
        self.shut_down = True
        self.monitors.clear()
        for a in self.agents:
            if a.sound is not None and a.sound.playing:
                a.sound.stop()
        self.bus.drop_scope(self.scope_key)

    def __repr__(self) -> str:
        return f'<Level {self.name} {len(self.agents)} agents {len(self.floors)} floors>'
