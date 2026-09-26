"""`PGEFollower` - ps2_8's penguin: it follows you, and near you it cracks the ice.

Recovered from the PS2 binary (docs/notes/M5_NOTES.md, "PGEFollower"):

* `init` 0x100063f64: smallRadius 30, largeRadius 60, speed 10, chaseSpeed 15,
  state 201, agentType 200, collideRadius = smallRadius; observes
  `SendAgentAwayFromPlayer`.
* three states: **201 following** (collide radius small, at chaseSpeed
  towards you, its chase sound), **202 close** (collide radius large,
  standing, its proximity sound, `OnProximity` on the way in), **203 sent
  away** (collide radius small, at chaseSpeed straight away from you, its
  scared sound, back to following after `moveAwayTime`);
* `checkCollisionsWithPlayer` 0x100065058 is its own: following and inside
  the collide radius -> close and `FollowerIsClose`; close and outside it ->
  following and `FollowerIsFar`; sent away and outside it -> `FollowerIsFar`.
  No `OnCollide`, no reach for the hands, no squared distance kept;
* `sendAwayFromPlayer:` 0x100064e3c: the time from `duration` (10 s without),
  and only a close penguin goes (state 203);
* the floor it stands on counts how long it has been close
  (`followerTime`, PGESurface) and cracks under you when that runs out;
* shot (`wasShot` 0x100065300) or beaten (`wasBeaten` 0x100065734): counted
  as a kill, it stops and falls silent, `FollowerDidDie`, the tracker's
  `incrementPenguinKills` (a penguin and an enemy - so with `FollowerDidDie`
  a penguin counts twice as an enemy), and its shot or beaten sound plays where
  its own sound was; dead, and it deactivates when that sound ends.  A beating
  fires `OnStab`; a shot, `OnShoot` (the agent's own).  With no such sound it
  deactivates at once and is not marked dead.
"""

from __future__ import annotations

import random

import numpy as np

from ..assets.tiled import LevelObject, ns_float
from ..core.messages import MessageBus, Params
from ..assets import requested
from .agent import GameAgent
from .player import play

_F32 = np.float32

FOLLOWING, CLOSE, SENT_AWAY = 201, 202, 203
WAITING_FOR_INTRO = 10
AGENT_TYPE = 200
SMALL_RADIUS = 30.0
LARGE_RADIUS = 60.0
SPEED = 10.0
CHASE_SPEED = 15.0
#: sendAwayFromPlayer: with no duration (0x41200000).
MOVE_AWAY_TIME = 10.0


class Follower(GameAgent):
    """`PGEFollower`."""

    kind = 'follower'

    def __init__(self, bus: MessageBus, world, obj: LevelObject | None = None,
                 rng: random.Random | None = None) -> None:
        self._follower_defaults()
        super().__init__(bus, world, None, rng=rng)
        self._follower_defaults()
        if obj is not None:
            self.build(obj)
        bus.subscribe('PGE_MESSAGE_SendAgentAwayFromPlayer', self._send_away_from_player)

    def _follower_defaults(self) -> None:
        self.small_radius = SMALL_RADIUS
        self.large_radius = LARGE_RADIUS
        self.speed = SPEED
        self.chase_speed = CHASE_SPEED
        self.state = FOLLOWING
        self.player_position = (0.0, 0.0)
        self.agent_type = AGENT_TYPE
        self.in_radius = False
        self.collide_radius = self.small_radius
        self.current_sound: str | None = None
        self.move_away_time = 0.0
        self.move_away_timer = 0.0
        self.chase_sound: str | None = None
        self.proximity_sound: str | None = None
        self.scared_sound: str | None = None
        self.shot_sound: str | None = None
        self.beaten_sound: str | None = None

    def build(self, obj: LevelObject) -> None:
        super().build(obj)
        a = obj.applied
        for key, attr in (('chaseSound', 'chase_sound'), ('proximitySound', 'proximity_sound'),
                          ('scaredSound', 'scared_sound'), ('shotSound', 'shot_sound'),
                          ('beatenSound', 'beaten_sound')):
            if key in a:
                setattr(self, attr, str(a[key]))
        for key, attr in (('smallRadius', 'small_radius'), ('largeRadius', 'large_radius')):
            if key in a:
                setattr(self, attr, ns_float(a[key]))

    # ------------------------------------------------------------ sounds
    def play_sound(self, name) -> float:
        """`playSound:` - looping."""
        return self.play_sound_looping(name, True)

    def play_sound_looping(self, name, looping: bool) -> float:
        """`playSound:looping:` (0x100064b8c).

        The same name as last time returns at once - whether or not that sound
        is still playing (after `UnpauseAgents` has played it once through, it
        stays silent until the penguin's state changes).  Otherwise the old
        sound stops and the playlist's sound of that exact name takes its
        place, placed on the penguin with its reverb, and plays.
        """
        if self.current_sound is not None and name is not None and self.current_sound == name:
            return float(self.sound.duration) if self.sound is not None else 0.0
        self.current_sound = name
        if self.sound is not None:
            self.sound.stop()
        bank = self.bank
        s = bank.sound(str(name)) if (bank is not None and name) else None
        self.sound = s
        self.update_spatialized_sound()
        self.setup_reverb_parameters()
        if s is None:
            return 0.0
        play(s, looping)
        return float(s.duration)

    # -------------------------------------------------------------- active
    def activate(self) -> None:
        """`-[PGEFollower activate]` (0x100064628): an intro sound first, and
        the agent's own activation only when it ends (state 10 meanwhile)."""
        self.current_sound = ''
        self.state_at_previous_frame = -1
        if not self.intro_sound:
            GameAgent.activate(self)
            return
        self.play_sound_looping(self.intro_sound, False)
        saved = self.state
        self.state = WAITING_FOR_INTRO
        s = self.sound
        if s is None or self.world is None:
            return                            # add3DSoundMonitor: to nil

        def monitor(pos, dur):
            if pos >= dur:
                def after():
                    self.super_activate()
                    self.state = saved
                self.bus.dispatch_async(after)
                return True
            return False
        self.world.monitors.add(s, monitor, self)

    def super_activate(self) -> None:
        """`superActivate` (0x100064a88)."""
        GameAgent.activate(self)

    def deactivate(self) -> None:
        """`-[PGEFollower deactivate]` (0x100064ac4): the floors hear it is gone."""
        self.bus.post('PGE_MESSAGE_FollowerIsFar', {})
        super().deactivate()

    def _reset_agent_with_name(self, _n, params: Params) -> None:
        """`-[PGEFollower resetAgentWithName:]` (0x1000644b8)."""
        if params.get('name') != self.name:
            return
        self.set_active(False)
        if self.initial_position is not None:
            self.position = self.initial_position
        self.state = FOLLOWING
        self.dead = False

    # --------------------------------------------------------- shot, beaten
    def was_shot(self) -> None:
        """`-[PGEFollower wasShot]` (0x100065300)."""
        if self.dead:
            return
        GameAgent.was_shot(self)
        self._die(self.shot_sound, stabbed=False)

    def was_beaten(self) -> None:
        """`-[PGEFollower wasBeaten]` (0x100065734).

        REQUESTED (decision 18, 2026-09-25): a penguin killed with the knife
        dies with the requested penguin death, which has the stab in it, in place
        of the original's (the same file for all four penguins)."""
        if self.dead:
            return
        GameAgent.was_beaten(self)
        name = self.beaten_sound
        bank = self.bank
        if (name and 'penguin' in name and 'death' in name and bank is not None
                and bank.has(requested.PENGUIN_STAB_DEATH)):
            name = requested.PENGUIN_STAB_DEATH
        self._die(name, stabbed=True)

    def _die(self, sound_name, stabbed: bool) -> None:
        self.speed = 0.0
        own = self.sound
        if own is not None:
            own.stop()
        self.bus.post('PGE_MESSAGE_FollowerDidDie', {})
        if stabbed:
            self.trigger('OnStab')
        tracker = getattr(self.world, 'tracker', None) if self.world is not None else None
        if tracker is not None:
            tracker.increment_penguin_kills()
        if not sound_name or self.bank is None:
            self.bus.dispatch_async(self.deactivate)
            return
        s = self.bank.any_sound_with_prefix(str(sound_name))
        if s is None:
            # messages to nil: not placed, not played, duration 0
            self.dead = True
            self.bus.dispatch_async(self.deactivate)
            return
        s.spatialized = True
        # where its own sound was (nil answers a zero position)
        where = own.planar if own is not None else (0.0, 0.0, 0.0)
        if stabbed:
            s.planar = where
            play(s, False)
        else:
            play(s, False)
            s.planar = where
        self.dead = True
        if float(s.duration) != 0.0 and self.world is not None:
            def monitor(pos, d):
                if pos >= d:
                    self.bus.dispatch_async(self.deactivate)
                    return True
                return False
            self.world.monitors.add(s, monitor, self)
        else:
            self.bus.dispatch_async(self.deactivate)

    # ---------------------------------------------------------- the player
    def check_collisions_with_player(self) -> None:
        """`-[PGEFollower checkCollisionsWithPlayer]` (0x100065058)."""
        if not self._active:
            return
        dx = _F32(self.player_position[0] - self.position[0])
        dy = _F32(self.player_position[1] - self.position[1])
        d2 = _F32(_F32(dx * dx) + _F32(dy * dy))
        r = _F32(self.collide_radius)
        rr = _F32(r * r)
        if self.state == FOLLOWING and d2 < rr:
            self.state = CLOSE
            self.bus.post('PGE_MESSAGE_FollowerIsClose', {})
        elif self.state == CLOSE and d2 > rr:
            self.state = FOLLOWING
            self.bus.post('PGE_MESSAGE_FollowerIsFar', {})
        elif self.state == SENT_AWAY and d2 > rr:
            self.bus.post('PGE_MESSAGE_FollowerIsFar', {})

    def _send_away_from_player(self, _n, params: Params) -> None:
        """`sendAwayFromPlayer:` (0x100064e3c) - a clap, in ps2_8."""
        name = params.get('name')
        if name is not None and name != self.name:
            return
        if params.get('duration') is not None:
            self.move_away_time = ns_float(params['duration'])
        else:
            self.move_away_time = MOVE_AWAY_TIME
        if self.state == CLOSE:
            self.move_away_timer = 0.0
            self.state = SENT_AWAY

    # -------------------------------------------------------------- update
    def update(self, dt: float) -> None:
        """`-[PGEFollower update:]` (0x100064144)."""
        super().update(dt)
        if not self._active or self.paused:
            return
        self.check_collisions_with_player()
        s = self.state
        if s == SENT_AWAY:
            self.collide_radius = self.small_radius
            self.speed = self.chase_speed
            self.play_sound(self.scared_sound)
            self.find_direction_to_player()
            ox, oy = self.orientation_vector
            self.orientation_vector = (-ox, -oy)
            self.move_away_timer = float(_F32(_F32(self.move_away_timer) + _F32(dt)))
            if _F32(self.move_away_timer) > _F32(self.move_away_time):
                self.state = FOLLOWING
        elif s == CLOSE:
            if self.state_at_previous_frame != CLOSE:
                self.trigger('OnProximity')
            self.collide_radius = self.large_radius
            self.speed = 0.0
            self.play_sound(self.proximity_sound)
        elif s == FOLLOWING:
            self.collide_radius = self.small_radius
            self.speed = self.chase_speed
            self.play_sound(self.chase_sound)
            self.find_direction_to_player()
        self.state_at_previous_frame = s
