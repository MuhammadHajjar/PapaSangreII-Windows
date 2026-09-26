"""`PGESurface` - a floor: footsteps, walls, and the enter/exit/step triggers.

Recovered from the PS2 binary (docs/notes/M2_NOTES.md, "PGESurface", and
docs/notes/M4_NOTES.md for the lethal half):

* `initWithRectangle:surfaceId:z:isCircle:` (0x100043114): gain 1,
  stepTriggerOdds 100, activationCounter 1, playerIsOnSurface NO, deathGain 1,
  and **active YES** at the end;
* the loader sets `active` YES again before the properties and then applies
  the data's `active` key straight through KVC, so a surface's activity is
  known the moment it is built (agents get theirs 0.05 s later);
* `triggerOnEnter:` / `triggerOnExit` fire once unless `multipleOnEnter`;
  `triggerOnStep` fires when `arc4random() % 100 < stepTriggerOdds`;
* `update:` does nothing while inactive, only resets the follower timer while
  paused, and counts its delayed triggers down last.

Lethal floors (M4): standing on an `isLethal` surface - on entering it, on its
activation under you, or when `SetLethalForSurfaceWithName` turns it lethal -
`kill`s: `OnKill`, walk and hands off, its own sound stops and the
`deathSound` plays flat at `deathGain`; at its end the level shuts down and
`LoadLevelWithName` reloads it with `deathCause` (default "surface").  A
surface with a `sound` plays it looping from the point of its rectangle
(inset 15 px) nearest the player.  `deadlyTime` / `safeTime` switch
`isLethal` in a cycle, `lethalAfter` kills whoever stands still on it that
long, and a follower close for `followerTime` kills too (M5).
"""

from __future__ import annotations

import random

import numpy as np

from ..assets.tiled import LevelObject, ns_bool, ns_float, ns_int
from ..core.messages import MessageBus, Params
from ..core.triggers import TriggerHost

_F32 = np.float32

#: computeNewPlayerPosition: - the sound keeps this far inside the rectangle.
SOUND_INSET = 15.0
#: update: - the follower alert stops once the follower has been away this long.
FOLLOWER_ALERT_LINGER = 0.2
#: restartLevel - the cause when the surface names none.
DEFAULT_DEATH_CAUSE = 'surface'


def s3d_playing(sound) -> bool:
    """`-[S3DSound playing]`: a paused sound (play rate 0) is still playing."""
    return sound is not None and (sound.playing or bool(getattr(sound, 'paused', False)))


#: `CGRectContainsPoint` on a standardised rect: [min, max) on both axes.


def rect_contains(rect, x: float, y: float) -> bool:
    rx, ry, rw, rh = rect
    if rw < 0:
        rx, rw = rx + rw, -rw
    if rh < 0:
        ry, rh = ry + rh, -rh
    return rx <= x < rx + rw and ry <= y < ry + rh


class Surface(TriggerHost):
    """One floor rectangle (or circle) of a level."""

    kind = 'surface'

    def __init__(self, bus: MessageBus, rect, surface_id: int = 0, z: int = 0,
                 is_circle: bool = False, name: str = '',
                 rng: random.Random | None = None, world=None) -> None:
        super().__init__(bus, name=name, rng=rng)
        self.rect = tuple(float(v) for v in rect)
        self.surface_id = int(surface_id)
        self.z = int(z)
        self.is_circle = bool(is_circle)
        #: the level: its playlist (`playListWithName:levelName`) and monitors
        self.world = world
        # -- initWithRectangle:surfaceId:z:isCircle: defaults
        self.gain = 1.0
        self.step_trigger_odds = 100
        self.activation_counter = 1
        self.player_is_on_surface = False
        self.death_gain = 1.0
        self.entered = False
        self.exited = False
        self.multiple_on_enter = False
        self.is_walled = False
        self.paused = False
        self.unpausable = False
        self.is_underwater = False
        self.footsteps_prefix: str | None = None
        self.footsteps_gain = 0.0
        self.shuffle_sound: str | None = None
        self.trip_bpm = 0.0
        self.run_bpm = 0.0
        self.still_limit = 0.0
        self.still_timer = 0.0
        self.follower_timer = 0.0
        self.sound: str | None = None
        self.death_cause: str | None = None
        self.death_sound: str | None = None
        self.is_lethal = False
        self.lethal_after = 0.0
        self.deadly_time = 0.0
        self.safe_time = 0.0
        self.deadly_timer = 0.0
        self.safe_timer = 0.0
        self.follower_time = 0.0
        self.follower_alert_sound: str | None = None
        self.follower_not_deadly = False
        self.is_follower_close = False
        self.not_on4 = False
        self.killed = False
        self.last_player_pos = (0.0, 0.0)
        #: updateJump: the times of the last jumps made on this floor
        self.jumps_time: list[float] = []
        #: the S3DSounds: the surface's own, the death sound, the follower alert
        self.spatial_sound = None
        self.lethal_sound = None
        self.follower_alert = None
        self.level_name = ''
        self._active = True
        #: Filled by the level: called on setActive:YES (SurfaceWasActivated).
        self.on_activated = None

        bus.subscribe('PGE_MESSAGE_ActivateAgentWithName', self._activate_with_name)
        bus.subscribe('PGE_MESSAGE_DeactivateAgentWithName', self._deactivate_with_name)
        # initWithRectangle:... and -[PGELevel init] both observe the jump
        bus.subscribe('PGE_ACTION_Jump', self._player_jumped)
        if self.kind != 'level':
            # -[PGELevel init] is not initWithRectangle:...; the room has none
            # of these (it has its own PlayerMovedToPosition).
            for msg, handler in (
                ('PGE_MESSAGE_SetLethalForSurfaceWithName', self._set_lethal_for_surface_with_name),
                ('PGE_MESSAGE_PlayerMovedToPosition', self._player_moved_to_position),
                ('PGE_MESSAGE_FollowerIsClose', lambda *_: self.set_follower_is_close()),
                ('PGE_MESSAGE_FollowerIsFar', lambda *_: self.set_follower_is_far()),
                ('PGE_MESSAGE_PauseAgents', lambda *_: self.pause_agents()),
                ('PGE_MESSAGE_UnpauseAgents', lambda *_: self.unpause_agents()),
            ):
                bus.subscribe(msg, handler)

    # ------------------------------------------------------------ building
    def apply(self, obj: LevelObject) -> None:
        """The loader's properties, as `createObjectFromDict:` sets them."""
        a = obj.applied
        self.add_triggers(obj.triggers)
        if 'runBPM' in a:
            self.run_bpm = ns_float(a['runBPM'])
        if 'tripBPM' in a:
            self.trip_bpm = ns_float(a['tripBPM'])
        if 'footstepsPrefix' in a:
            self.footsteps_prefix = str(a['footstepsPrefix'])
        if 'footstepsGain' in a:
            self.footsteps_gain = ns_float(a['footstepsGain'])
        if 'shuffleSound' in a:
            self.shuffle_sound = str(a['shuffleSound'])
        if 'multipleOnEnter' in a:
            self.multiple_on_enter = ns_bool(a['multipleOnEnter'])
        if 'isWalled' in a:
            self.is_walled = ns_bool(a['isWalled'])
        if 'stepTriggerOdds' in a:
            self.step_trigger_odds = ns_int(a['stepTriggerOdds'])
        if 'activationCounter' in a:
            self.activation_counter = ns_int(a['activationCounter'])
        if 'gain' in a:
            self.gain = ns_float(a['gain'])
        if 'isUnderwater' in a:
            self.is_underwater = ns_bool(a['isUnderwater'])
        if 'stillLimit' in a:
            self.still_limit = ns_float(a['stillLimit'])
        if 'deathCause' in a:
            self.death_cause = str(a['deathCause'])
        if 'deathSound' in a:
            self.death_sound = str(a['deathSound'])
        if 'deathGain' in a:
            self.death_gain = ns_float(a['deathGain'])
        if 'lethalAfter' in a:
            self.lethal_after = ns_float(a['lethalAfter'])
        if 'deadlyTime' in a:
            self.deadly_time = ns_float(a['deadlyTime'])
        if 'safeTime' in a:
            self.set_safe_time(ns_float(a['safeTime']))
        if 'followerTime' in a:
            self.follower_time = ns_float(a['followerTime'])
        if 'followerAlertSound' in a:
            self.follower_alert_sound = str(a['followerAlertSound'])
        if 'followerNotDeadly' in a:
            self.follower_not_deadly = ns_bool(a['followerNotDeadly'])
        if 'notOn4' in a:
            self.not_on4 = ns_bool(a['notOn4'])
        if 'unpausable' in a:
            self.unpausable = ns_bool(a['unpausable'])
        if 'active' in a:
            self._active = ns_bool(a['active'])
        if 'isLethal' in a:
            self.set_is_lethal(ns_bool(a['isLethal']))
        if 'sound' in a:
            self.set_sound(str(a['sound']))

    def set_safe_time(self, value: float) -> None:
        """`setSafeTime:` (0x100043d78): the safe timer starts 0.1 s short."""
        self.safe_timer = float(_F32(float(_F32(value)) + -0.1))
        self.safe_time = float(value)

    def set_sound(self, name: str) -> None:
        """`setSound:` (0x100043dcc): the sound starts from a main-queue block."""
        self.sound = name

        def later():
            if self._active:
                self.initialise_sound()
        self.bus.dispatch_async(later)

    # -------------------------------------------------------------- active
    @property
    def active(self) -> bool:
        return self._active

    def set_active(self, value: bool) -> None:
        """`setActive:` (0x1000447d8)."""
        self._active = bool(value)
        if value:
            if self.on_activated is not None:
                self.on_activated()          # PGE_MESSAGE_SurfaceWasActivated
            self.check_lethal()
            if self.sound is not None:
                self.initialise_sound()

    def _activate_with_name(self, _n: str, params: Params) -> None:
        """`activateWithName:` (0x100044368)."""
        if not self.name or params.get('name') != self.name:
            return
        self.activation_counter -= 1
        if self.activation_counter <= 0:
            self.set_active(True)
            self.still_timer = 0.0
            self.trigger('OnActivate')

    def _deactivate_with_name(self, _n: str, params: Params) -> None:
        """`deactivateWithName:` (0x1000444ec)."""
        target = params.get('name')
        if target is None:
            return
        if target != self.name:
            if target != '*':
                return
            if 'type' in params and ns_int(params['type']) != 0:
                return                        # 0x10004465c: any non-zero type skips surfaces
        if ns_bool(params.get('clean', 'NO')):
            self.clear_delays()
        self.deactivate()

    def deactivate(self) -> None:
        """`deactivate` (0x100044750): inactive, sound off and let go of,
        OnDeactivate.

        Letting go matters: the playlist's sound is one object, shared by every
        surface that names it (ps2_14's three fire doors).  A put-out door that
        kept it went on moving it to itself on every step - so the next door's
        fire jumped back to the first one, behind you (the tester's report;
        the port had missed the ``spatialSound = nil``, 0x1000447ac)."""
        self.set_active(False)
        if s3d_playing(self.spatial_sound):
            self.spatial_sound.stop()
            self.spatial_sound = None
        self.trigger('OnDeactivate')

    # ------------------------------------------------------------ triggers
    def trigger_on_enter(self, just_stepped: bool) -> None:
        """`triggerOnEnter:` (0x1000448cc)."""
        if self.entered and not self.multiple_on_enter:
            return
        self.entered = True
        self.player_is_on_surface = True
        self.trigger('OnEnter')
        if just_stepped:
            self.trigger_on_step()
        self.check_lethal()

    def trigger_on_exit(self) -> None:
        """`triggerOnExit` (0x100044998)."""
        if self.exited and not self.multiple_on_enter:
            return
        self.exited = True
        self.player_is_on_surface = False
        self.trigger('OnExit')

    def trigger_on_step(self) -> None:
        """`triggerOnStep` (0x100044a34): `arc4random() % 100 < stepTriggerOdds`."""
        if self.rng.randrange(0, 2 ** 32) % 100 < self.step_trigger_odds:
            self.trigger('OnStep')
        self.still_timer = 0.0

    def trigger_on_trip(self) -> None:
        self.trigger('OnTrip')

    def trigger_on_pebble(self) -> None:
        """`triggerOnPebble` (0x100044ac4)."""
        self.trigger('OnPebble')

    # -------------------------------------------------------------- lethal
    def set_is_lethal(self, value: bool) -> None:
        """`setIsLethal:` (0x100044af4)."""
        self.is_lethal = bool(value)
        self.check_lethal()

    def check_lethal(self) -> None:
        """`checkLethal` (0x100044b10)."""
        if self.is_lethal and self.player_is_on_surface:
            self.kill()

    # ---------------------------------------------------------------- jump
    def _player_jumped(self, _n, _p) -> None:
        """`playerJumped` (0x100045414): the floor the player stands on fires
        `OnJump` and counts the jump."""
        if not self.player_is_on_surface:
            return
        self.trigger('OnJump')
        self.update_jump()

    def update_jump(self) -> None:
        """`updateJump` (0x10004547c) - the player's clap counter over again,
        with 0.5 s: the last four jumps kept; three or more whose gaps average
        (over the count, not the gaps) under 0.5 s -> `OnJumpTooMuch`, and the
        count starts again."""
        self.jumps_time.append(self.bus.now)
        while len(self.jumps_time) >= 5:
            self.jumps_time.pop(0)
        n = len(self.jumps_time) - 1
        total = _F32(0.0)
        for i in range(max(n, 0)):
            total = _F32(float(total) + (self.jumps_time[i + 1] - self.jumps_time[i]))
        if len(self.jumps_time) >= 3 and float(total / _F32(len(self.jumps_time))) < 0.5:
            self.trigger('OnJumpTooMuch')
            self.jumps_time.clear()

    def _set_lethal_for_surface_with_name(self, _n, params: Params) -> None:
        """`setLethalForSurfaceWithName:` (0x1000452b4)."""
        if params.get('name') == self.name:
            self.set_is_lethal(ns_bool(params.get('value')))

    def kill(self) -> None:
        """`kill` (0x100044b74)."""
        if self.killed:
            return
        self.trigger('OnKill')
        if self.follower_not_deadly:
            return                           # OnKill every time; nothing else
        self.bus.post('PGE_MESSAGE_DisableWalk', {})
        self.bus.post('PGE_MESSAGE_DisableHands', {})
        self.killed = True
        if self.spatial_sound is not None:
            self.spatial_sound.stop()
        self.play_death_sound()

    def _bank(self):
        return getattr(self.world, 'bank', None) if self.world is not None else None

    def play_death_sound(self) -> None:
        """`playDeathSound` (0x100044cd0).

        No level name or no death sound: nothing more happens (the player is
        left without walk or hands, as in the original).  A death sound that
        is not in the playlist: the level shuts down and restarts at once.
        """
        if not self.level_name or self.death_sound is None:
            return
        bank = self._bank()
        s = bank.any_sound_with_prefix(self.death_sound) if bank is not None else None
        self.lethal_sound = s
        if s is None:
            self.bus.post('PGE_MESSAGE_ShutDownLevel', {})
            self.restart_level()
            return
        s.spatialized = False
        s.gain = self.death_gain
        s.looping = False
        s.play()

        def monitor(pos, dur):
            if pos >= dur:
                def after():
                    self.bus.post('PGE_MESSAGE_ShutDownLevel', {})
                    self.restart_level()
                self.bus.dispatch_async(after)
                return True
            return False
        self.world.monitors.add(s, monitor, self)

    def restart_level(self) -> None:
        """`restartLevel` (0x100045120): reload this level with the cause."""
        cause = self.death_cause if self.death_cause is not None else DEFAULT_DEATH_CAUSE
        self.bus.post('PGE_MESSAGE_LoadLevelWithName',
                      {'name': self.level_name, 'deathCause': cause})

    # --------------------------------------------------------------- sound
    def initialise_sound(self) -> None:
        """`initialiseSound` (0x100043f3c).

        ``notOn4`` skips the sound on an iPhone 4 only; the port is never one.
        A new activation takes the playlist's sound again without stopping it
        first, as the original does.
        """
        bank = self._bank()
        s = bank.sound(self.sound) if (bank is not None and self.sound) else None
        self.spatial_sound = s
        if s is None:
            return
        s.gain = self.gain
        s.spatialized = True
        rx, ry, rw, rh = self.rect
        s.planar = (float(_F32(rx + rw * 0.5)), float(_F32(ry + rh * 0.5)), 0.0)
        if self._active:
            s.looping = True
            s.play()
            self.compute_new_player_position(*self.last_player_pos)

    def compute_new_player_position(self, px: float, py: float) -> None:
        """`computeNewPlayerPosition:` (0x1000442a4): the sound moves to the
        point of the rectangle, 15 px in from its edges, nearest the player."""
        s = self.spatial_sound
        if s is None:
            return
        rx, ry, rw, rh = self.rect
        lo_x = rx + SOUND_INSET
        lo_y = ry + SOUND_INSET
        if lo_x > px:
            x = lo_x
        else:
            hi = lo_x + (rw + -2 * SOUND_INSET)
            x = hi if hi < px else px
        if lo_y > py:
            y = lo_y
        else:
            hi = lo_y + (rh + -2 * SOUND_INSET)
            y = hi if hi < py else py
        s.planar = (float(_F32(x)), float(_F32(y)), 0.0)
        # sendDidMoveMessage (0x100044364) is empty

    def _player_moved_to_position(self, _n, params: Params) -> None:
        """`playerMovedToPosition:` (0x1000441a0)."""
        pos = params.get('position', (0.0, 0.0))
        self.last_player_pos = (float(pos[0]), float(pos[1]))
        self.compute_new_player_position(*self.last_player_pos)

    # ------------------------------------------------------------ follower
    def set_follower_is_close(self) -> None:
        self.is_follower_close = True

    def set_follower_is_far(self) -> None:
        self.is_follower_close = False

    # ------------------------------------------------------------- pausing
    def pause_agents(self) -> None:
        """`pauseAgents` (0x100045708), for `PauseAgents`."""
        if self.unpausable:
            return
        self.paused = True
        self.follower_timer = 0.0
        if s3d_playing(self.follower_alert):
            self.follower_alert.stop()
        if s3d_playing(self.spatial_sound):
            self.spatial_sound.pause()
        if s3d_playing(self.lethal_sound):
            self.lethal_sound.pause()

    def unpause_agents(self) -> None:
        """`unpauseAgents` (0x10004580c): resume is play rate 1, so a sound
        that was stopped meanwhile stays stopped."""
        if self.unpausable:
            return
        self.paused = False
        self.follower_timer = 0.0
        if self.follower_alert is not None:
            self.follower_alert.stop()
        if self.spatial_sound is not None:
            self.spatial_sound.resume()
        if self.lethal_sound is not None:
            self.lethal_sound.resume()

    # ------------------------------------------------------------ geometry
    def contains(self, x: float, y: float) -> bool:
        return rect_contains(self.rect, x, y)

    def circle_contains(self, x: float, y: float) -> bool:
        """The circle test in `surfaceForPosition:` (float32 distance)."""
        rx, ry, rw, rh = self.rect
        dx = np.float32(rx + rw * 0.5 - x)
        dy = np.float32(ry + rh * 0.5 - y)
        d = float(np.float32(dx * dx + dy * dy)) ** 0.5
        return d < rw * 0.5

    # -------------------------------------------------------------- update
    def update(self, dt: float) -> None:
        """`-[PGESurface update:]` (0x1000437fc)."""
        if not self._active:
            return
        if self.paused:
            self.follower_timer = 0.0
            return
        step = _F32(dt)
        # -- the follower (a penguin close behind you)
        if self.player_is_on_surface and self.is_follower_close and self.follower_time > 0:
            if not s3d_playing(self.follower_alert) and self.follower_timer == 0:
                bank = self._bank()
                s = bank.sound(self.follower_alert_sound) \
                    if (bank is not None and self.follower_alert_sound) else None
                self.follower_alert = s
                if s is not None:
                    s.spatialized = False
                    s.looping = False
                    s.play()
            self.follower_timer = float(_F32(self.follower_timer) + step)
        elif self.follower_timer > FOLLOWER_ALERT_LINGER:
            self.follower_timer = 0.0
            if s3d_playing(self.follower_alert):
                self.follower_alert.stop()
        if (self.follower_time > 0 and _F32(self.follower_timer) > _F32(self.follower_time)
                and not self.killed):
            if self.follower_alert is not None:
                self.follower_alert.stop()
            self.kill()
        # -- the deadly / safe cycle
        if self.deadly_time != 0 and self.safe_time != 0:
            if self.is_lethal:
                self.deadly_timer = float(_F32(self.deadly_timer) + step)
                if _F32(self.deadly_timer) > _F32(self.deadly_time):
                    self.deadly_timer = 0.0
                    self.safe_timer = 0.0
                    self.set_is_lethal(False)
                    self.trigger('OnDeadlyNo')
            else:
                self.safe_timer = float(_F32(self.safe_timer) + step)
                if _F32(self.safe_timer) > _F32(self.safe_time):
                    self.safe_timer = 0.0
                    self.deadly_timer = 0.0
                    self.set_is_lethal(True)
                    self.trigger('OnDeadlyYes')
        # -- standing still on it
        if self.player_is_on_surface:
            self.still_timer = float(_F32(self.still_timer) + step)
            lim = _F32(self.still_limit)
            if (lim > 0 and _F32(self.still_timer) > lim
                    and _F32(self.still_timer) < _F32(lim + step)):
                self.trigger('OnStillLimit')
            if (self.lethal_after != 0 and _F32(self.still_timer) > _F32(self.lethal_after)
                    and not self.killed):
                self.kill()
        self.update_delays(dt)

    def __repr__(self) -> str:
        return f'<Surface {self.name or self.surface_id} z{self.z} {"on" if self._active else "off"}>'
