"""`PGEEnemy` - the level data's `Monster`: the mind lice and everything after.

Recovered from Papa Sangre II's own binary (engine 1_1_013); it differs a lot
from the first game's (`update:` 38 % similar), so nothing here is the PS1
port's.  Notes: docs/notes/M3_NOTES.md.

``init`` (0x10001dc40): speed 10, chaseSpeed 15, patrolSpeed 10, state 0,
agentType 200, shotSound agony_SPA, awareSound hey_SPA, beatenSound
stab_and_death; listens for ``AlertAllEnemies`` and
``SendAgentToInitialPosition``.

``update:`` (0x10001debc) runs the agent's own update (delays, path, the step
along ``orientationVector`` at ``speed``) and then, while active, alive and
not paused, checks the collision and runs one state from a ten-entry jump
table (0x10001ec30).  ``state_atPreviousFrame`` is the state this frame
*started* in, so "entry" work runs once per visit:

====  ===============  ======================================================
0     still            stillSound (looping), speed 0
1     patrol           patrolSpeed, patrolSound looping
2     alerted, player  entry: awareSound once, chaseSpeed, chase (3) when it
                       ends; a louse still playing its intro only remembers
                       the alert (``delayedAlerted``)
3     chase            chaseSpeed, chaseSound, steer at the player
4     alerted, place   entry: awareSound once, head for where the player is,
                       go (5) when it ends; already heading somewhere: go now
5     going there      chaseSound, chaseSpeed; once the distance to the goal
                       grows, it has passed it: (6)
6     not there        entry: notThereSound once; when it ends, still (0) and
                       ``OnPlayerLastPosition``; speed 0, forget the goal
7     attack           touching the player: speed 0, attackSound
8     alerted, agent   entry: awareSound once, then (5)
9     going home       steer at the initial position at patrolSpeed with
                       patrolSound; home (within ~3 px) or overshot: (0)
10    waiting          nothing - a sound is playing and a delayed state change
                       will move it on (any state above 9 does nothing)
====  ===============  ======================================================

The delayed changes are ``performSelector:withObject:afterDelay:`` and nothing
cancels them (the level's shutdown cancels only its floors' requests).
"""

from __future__ import annotations

import math
import random
import re

import numpy as np

from ..assets.tiled import LevelObject, ns_bool, ns_float
from ..core.messages import MessageBus, Params
from .agent import GameAgent
from .player import play

_F32 = np.float32

AGENT_TYPE = 200
SPEED = 10.0
CHASE_SPEED = 15.0
PATROL_SPEED = 10.0
SHOT_SOUND = 'agony_SPA'
AWARE_SOUND = 'hey_SPA'
BEATEN_SOUND = 'stab_and_death'
WAITING = 10
#: -[PGEEnemy update:] state 9: within this *squared* distance it is home.
HOME_SQUARED = 10.0
#: -[PGEEnemy isStill]: 0, 6, 104 (0x68 - set by nothing in PS2) and 10.
STILL_STATES = (0, 6, 104, WAITING)


def _div(a: float, b: float) -> float:
    """IEEE division, as Objective-C does it: 0/0 is NaN, x/0 is +-inf."""
    try:
        return a / b
    except ZeroDivisionError:
        if a == 0 or math.isnan(a):
            return math.nan
        return math.copysign(math.inf, a) * (math.copysign(1.0, b))


def cg_point_from_string(text) -> tuple[float, float]:
    """`CGPointFromString`: "{x, y}"; anything else is (0, 0)."""
    m = re.match(r'\s*\{\s*([-+0-9.eE]+)\s*,\s*([-+0-9.eE]+)\s*\}', str(text))
    if not m:
        return (0.0, 0.0)
    return (float(m.group(1)), float(m.group(2)))


class Enemy(GameAgent):
    """One `Monster`."""

    kind = 'enemy'

    def __init__(self, bus: MessageBus, world, obj: LevelObject | None = None,
                 rng: random.Random | None = None) -> None:
        # -[PGEEnemy init]: the defaults go in before the data's keys
        self._enemy_defaults()
        super().__init__(bus, world, None, rng=rng)
        self._enemy_defaults()
        if obj is not None:
            self.build(obj)
        for name, handler in (
            ('PGE_MESSAGE_AlertAllEnemies', self._alert_enemy),
            ('PGE_MESSAGE_SendAgentToInitialPosition', self._send_to_initial_position),
        ):
            bus.subscribe(name, handler)

    def _enemy_defaults(self) -> None:
        self.path_current_point = 0
        self.speed = SPEED
        self.chase_speed = CHASE_SPEED
        self.patrol_speed = PATROL_SPEED
        self.state = 0
        self.player_position = (0.0, 0.0)
        self.agent_type = AGENT_TYPE
        self.shot_sound = SHOT_SOUND
        self.aware_sound = AWARE_SOUND
        self.beaten_sound = BEATEN_SOUND
        self.still_sound: str | None = None
        self.patrol_sound: str | None = None
        self.chase_sound: str | None = None
        self.not_there_sound: str | None = None
        self.attack_sound: str | None = None
        self.proximity_sound: str | None = None
        self.proximity_sound_radius = 0.0
        self.proximity_s3d = None
        self.invincible = False
        self.invincible_when_moving = False
        self.squared_distance_from_goal = math.inf
        self.delayed_alerted = False
        self.waiting_for_intro = False
        self.current_sound: str | None = None
        self.wanted_position = (0.0, 0.0)
        self.has_wanted_position = False
        self.chasing_time = 0.0
        self.within_radius = False
        #: REQUESTED (tester, 2026-09-26), set in world/level.py REQUESTED_DATA:
        #: comes after the player while its intro plays, and chases with its
        #: chase sound `intro_lead` seconds before the intro ends.
        self.chase_during_intro = False
        self.intro_lead = 0.0

    def build(self, obj: LevelObject) -> None:
        super().build(obj)
        a = obj.applied
        for key, attr in (('awareSound', 'aware_sound'), ('stillSound', 'still_sound'),
                          ('patrolSound', 'patrol_sound'), ('chaseSound', 'chase_sound'),
                          ('notThereSound', 'not_there_sound'), ('attackSound', 'attack_sound'),
                          ('shotSound', 'shot_sound'), ('beatenSound', 'beaten_sound')):
            if key in a:
                setattr(self, attr, str(a[key]))
        for key, attr in (('chaseSpeed', 'chase_speed'), ('patrolSpeed', 'patrol_speed'),
                          ('proximitySoundRadius', 'proximity_sound_radius')):
            if key in a:
                setattr(self, attr, ns_float(a[key]))
        for key, attr in (('invincible', 'invincible'),
                          ('invincibleWhenMoving', 'invincible_when_moving')):
            if key in a:
                setattr(self, attr, ns_bool(a[key]))
        if 'proximitySound' in a:
            self.set_proximity_sound(str(a['proximitySound']))

    # ------------------------------------------------------------- states
    def change_state_to(self, state: int) -> None:
        """`changeStateTo:` - just `setState:` (a selector for the delays)."""
        self.state = int(state)

    def _change_state_later(self, delay: float, state: int) -> None:
        """`performSelector:@selector(changeStateTo:) withObject:@n afterDelay:d`."""
        self.bus.call_after(float(delay), lambda: self.change_state_to(state))

    def is_still(self) -> bool:
        return self.state in STILL_STATES

    # -------------------------------------------------------------- sound
    def play_sound(self, name) -> float:
        """`playSound:` - looping."""
        return self.play_sound_looping(name, True)

    def play_sound_looping(self, name, looping: bool) -> float:
        """`playSound:looping:` (0x100020bd8): the sound's duration.

        The same sound, still playing, is left alone; anything else stops the
        current sound and starts the new one by prefix, placed on the agent,
        with its reverb set up.
        """
        s = self.sound
        if (name is not None and self.current_sound == name
                and s is not None and s.playing):
            return float(s.duration)
        if name is None:
            return 0.0
        if s is not None:
            s.stop()
            if self.world is not None:
                self.world.monitors.remove_sound(s)
        bank = self.bank
        s = bank.any_sound_with_prefix(str(name)) if bank is not None else None
        self.sound = s
        self.update_spatialized_sound()
        self.current_sound = str(name)
        self.setup_reverb_parameters()
        if s is None:
            return 0.0
        play(s, looping)
        return float(s.duration)

    # --------------------------------------------------------- activation
    def activate(self) -> None:
        """`-[PGEEnemy activate]` (0x10001edcc): an intro sound first."""
        self.current_sound = ''
        self.state_at_previous_frame = -1
        if self.intro_sound:
            self.waiting_for_intro = True
            self.play_sound_looping(self.intro_sound, False)
            saved = self.state
            self.state = WAITING
            s = self.sound
            chase = self.chase_during_intro
            lead = self.intro_lead if chase else 0.0
            if chase:
                # ps2_14's collapsing house: it had stood still through all
                # 8.4 s of its start sound, then left a quiet gap before its
                # loop - "no real danger".  Now it moves at once.
                self.speed = self.chase_speed
                self.find_direction_to(*self.player_position)
            if s is not None and self.world is not None:
                def monitor(pos, dur):
                    if pos < dur - lead:
                        if chase and self._active:
                            self.find_direction_to(*self.player_position)
                        return False

                    def after():
                        self.activate_delayed_sound()
                        GameAgent.activate(self)          # superActivate
                        self.state = 3 if chase else saved
                    self.bus.dispatch_async(after)
                    return True
                self.world.monitors.add(s, monitor, self)
            return
        self.waiting_for_intro = False
        GameAgent.activate(self)

    def activate_delayed_sound(self) -> None:
        """`activateDelayedSound` (0x10001f2a4): an alert heard during the intro."""
        self.waiting_for_intro = False
        if not self.delayed_alerted:
            return
        self.delayed_alerted = False
        d = self.play_sound_looping(self.aware_sound, False)
        self.speed = self.chase_speed
        self._change_state_later(d, 3)
        if d > 0:
            self.change_state_to(WAITING)
        self.chasing_time = 0.0

    def deactivate(self) -> None:
        """`-[PGEEnemy deactivate]` (0x10001ecc0)."""
        if self.sound is not None and self.sound.playing:
            self.sound.stop()
        self.state = -1
        GameAgent.deactivate(self)
        self.state_at_previous_frame = -1

    def _activate_enemy(self, _n, params: Params) -> None:
        """`activateEnemy:` - nothing in PS2 posts to it."""
        name = params.get('name')
        if name is not None and name == self.name:
            self.set_active(True)

    # ------------------------------------------------------------ alerts
    def _alert_enemy(self, _n, params: Params) -> None:
        """`alertEnemy:` (0x10001f800), for `AlertAllEnemies`."""
        if not self._active or self.state in (2, 3):
            return
        if params.get('radius') is not None:
            r = _F32(ns_float(params['radius']))
            dx = _F32(self.player_position[0] - self.position[0])
            dy = _F32(self.player_position[1] - self.position[1])
            if _F32(dx * dx + dy * dy) > _F32(r * r):
                self.within_radius = False
                return
        name = params.get('name')
        if name is not None and name != self.name:
            return
        to = params.get('to')
        if to == 'player':
            self.change_state_to(2)
            self.trigger('OnChase')
        elif to == 'position':
            self.change_state_to(4)
            self.trigger('OnChase')
        elif to == 'agent':
            self.change_state_to(8)
            if params.get('position') is not None:
                self.wanted_position = cg_point_from_string(params['position'])
                self.find_direction_to(*self.wanted_position)
            self.trigger('OnChase')

    def _send_to_initial_position(self, _n, params: Params) -> None:
        """`sendToInitialPosition:` (0x10001fd3c) - no name means every enemy."""
        name = params.get('name')
        if name is not None and name != self.name:
            return
        self.change_state_to(9)

    # ------------------------------------------------------------ shot at
    def was_shot(self) -> None:
        """`-[PGEEnemy wasShot]` (0x100020070).

        Dead already, or `invincibleWhenMoving` and not still: nothing.  Else
        the kill is counted and `OnShoot` fires; an `invincible` one stops
        there.  Otherwise it stops, its shot sound plays where it stands, its
        own sound stops, it is dead (`AgentDidDie`), and when the shot sound
        ends `OnShotSoundEnd` fires and it deactivates.
        """
        if self.dead:
            return
        if self.invincible_when_moving and not self.is_still():
            return
        GameAgent.was_shot(self)
        if self.invincible:
            return
        self.speed = 0.0
        bank = self.bank
        s = bank.any_sound_with_prefix(str(self.shot_sound)) \
            if (bank is not None and self.shot_sound is not None) else None
        if s is not None:
            s.spatialized = True
            x, y = self.position
            s.planar = (float(_F32(x)), float(_F32(y)), 0.0)
            play(s, False)
        if self.sound is not None:
            self.sound.stop()
        self.sound = None
        self.dead = True
        self.bus.post('PGE_MESSAGE_AgentDidDie', {})
        dur = float(s.duration) if s is not None else 0.0
        if dur != 0.0:
            def monitor(pos, d):
                if pos >= d:
                    def after():
                        self.on_shot_sound_end()
                        self.deactivate()
                    self.bus.dispatch_async(after)
                    return True
                return False
            self.world.monitors.add(s, monitor, self)
        else:
            self.bus.dispatch_async(self.deactivate)

    def on_shot_sound_end(self) -> None:
        """`onShotSoundEnd` (0x100020b60)."""
        self.trigger('OnShotSoundEnd')

    def was_beaten(self) -> None:
        """`-[PGEEnemy wasBeaten]` (0x100020474).

        Dead already, or `invincibleWhenMoving` and not still: nothing (no
        `invincible` check here, unlike a shot).  Else the kill is counted,
        `OnStab` fires, it stops, its own sound stops and the beaten sound
        takes its place - for an enemy named `4_papa_...` the level counts one
        more picture taken and the sound is `beatenSound` followed by that
        count.  Placed where it stands, played; dead (`AgentDidDie`); and when
        it ends `OnBeatenSoundEnd` fires and it deactivates.
        """
        if self.dead:
            return
        if self.invincible_when_moving and not self.is_still():
            return
        GameAgent.was_beaten(self)
        self.trigger('OnStab')
        self.speed = 0.0
        if self.sound is not None:
            self.sound.stop()
        bank = self.bank
        name = str(self.beaten_sound) if self.beaten_sound is not None else ''
        if self.name.startswith('4_papa_') and self.world is not None:
            self.world.pictures_taken = self.world.pictures_taken + 1
            name = '%s%d' % (name, self.world.pictures_taken)
        s = bank.any_sound_with_prefix(name) if (bank is not None and self.beaten_sound is not None) else None
        self.sound = s
        if s is not None:
            s.spatialized = True
            self.setup_reverb_parameters()
            x, y = self.position
            s.planar = (float(_F32(x)), float(_F32(y)), 0.0)
            play(s, False)
        self.dead = True
        self.bus.post('PGE_MESSAGE_AgentDidDie', {})
        dur = float(s.duration) if s is not None else 0.0
        if dur != 0.0:
            def monitor(pos, d):
                if pos >= d:
                    def after():
                        self.on_beaten_sound_end()
                        self.deactivate()
                    self.bus.dispatch_async(after)
                    return True
                return False
            self.world.monitors.add(s, monitor, self)
        else:
            self.bus.dispatch_async(self.deactivate)

    def on_beaten_sound_end(self) -> None:
        """`onBeatenSoundEnd` (0x100020b3c)."""
        self.trigger('OnBeatenSoundEnd')

    def collides_with_player(self) -> None:
        """`-[PGEEnemy collidesWithPlayer]` (0x10001f654): it attacks."""
        if self.state == 7 or self.dead:
            return
        self.speed = 0.0
        self.change_state_to(7)
        GameAgent.collides_with_player(self)

    # --------------------------------------------------------- direction
    def find_direction_to(self, x: float, y: float) -> float:
        """`-[PGEEnemy findDirectionTo:]` (0x10001f740).

        REQUESTED (decision 16, 2026-09-25): the original has no zero guard,
        so an enemy sent where it already stands - home, when every enemy is
        sent home - gets a direction of 0/0 and is lost at NaN; in ps2_15 that
        stranded a bear the level needs.  Here it gets no direction and stays.
        """
        ox = x - self.position[0]
        oy = y - self.position[1]
        n = float(_F32(math.sqrt(ox * ox + oy * oy)))
        if n == 0.0:
            self.orientation_vector = (0.0, 0.0)
        else:
            self.orientation_vector = (_div(ox, n), _div(oy, n))
        self.squared_distance_from_goal = float(_F32(n) * _F32(n))
        return float(_F32(_div(n, float(_F32(self.chase_speed)))))

    def _squared_distance_to(self, point) -> float:
        dx = self.position[0] - point[0]
        dy = self.position[1] - point[1]
        return float(_F32(dx * dx + dy * dy))

    # ---------------------------------------------------- proximity sound
    def set_proximity_sound(self, name: str) -> None:
        """`setProximitySound:` (0x10001f43c): a flat loop, silent until near."""
        self.proximity_sound = name
        if self.proximity_s3d is not None:
            self.proximity_s3d.stop()
        bank = self.bank
        s = bank.sound(name) if bank is not None else None
        self.proximity_s3d = s
        if s is None:
            return
        s.spatialized = False
        s.gain = 0.0
        self.setup_reverb_parameters()          # on self.sound, as the original
        play(s, True)

    def adjust_proximity_sound_gain(self) -> None:
        """`adjustProximitySoundGain` (0x10001f554): (1 - d^2/r^2)^4 inside r."""
        s = self.proximity_s3d
        if s is None:
            return
        sq = _F32(self.squared_distance_from_player)
        r = _F32(self.proximity_sound_radius)
        if sq < r * r:
            ratio = float(_F32(sq / (r * r)))
            s.gain = float(_F32(math.pow(1.0 - ratio, 4.0)))
        else:
            s.gain = 0.0

    # -------------------------------------------------------------- update
    def update(self, dt: float) -> None:
        """`-[PGEEnemy update:]` (0x10001debc)."""
        GameAgent.update(self, dt)
        if not self._active or self.dead or self.paused:
            return
        self.check_collisions_with_player()
        state = self.state
        prev = self.state_at_previous_frame
        dt = float(_F32(dt))
        if state == 0:
            self.play_sound(self.still_sound)
            self.speed = 0.0
        elif state == 1:
            self.speed = self.patrol_speed
            self.play_sound_looping(self.patrol_sound, True)
        elif state == 2:
            if prev == 3:
                self.state = 3
            elif prev != 2:
                if self.waiting_for_intro:
                    self.delayed_alerted = True
                else:
                    d = self.play_sound_looping(self.aware_sound, False)
                    self.speed = self.chase_speed
                    self._change_state_later(d, 3)
                    if d > 0:
                        self.change_state_to(WAITING)
                    self.chasing_time = 0.0
        elif state == 3:
            self.speed = self.chase_speed
            self.play_sound(self.chase_sound)
            self.find_direction_to_player()
            self.chasing_time = float(_F32(self.chasing_time) + _F32(dt))
        elif state == 4:
            if self.has_wanted_position:
                self.find_direction_to_player()
                self.change_state_to(5)
            else:
                d = self.play_sound_looping(self.aware_sound, False)
                self._change_state_later(d, 5)
                if d > 0:
                    self.change_state_to(WAITING)
                self.find_direction_to_player()
            self.wanted_position = self.player_position
            if prev != 4:
                self.squared_distance_from_goal = self._squared_distance_to(self.wanted_position)
                self.chasing_time = 0.0
                self.has_wanted_position = True
                self.speed = self.chase_speed
        elif state == 5:
            self.play_sound(self.chase_sound)
            self.speed = self.chase_speed
            sq = self._squared_distance_to(self.wanted_position)
            if not (sq <= self.squared_distance_from_goal):      # NaN too, as fcmp/b.le
                self.change_state_to(6)
            self.squared_distance_from_goal = sq
            self.chasing_time = float(_F32(self.chasing_time) + _F32(dt))
        elif state == 6:
            if prev != 6:
                d = self.play_sound_looping(self.not_there_sound, False)
                self._change_state_later(d, 0)
                self.bus.call_after(d, lambda: self.trigger('OnPlayerLastPosition'))
                if d > 0:
                    self.change_state_to(WAITING)
            self.speed = 0.0
            self.has_wanted_position = False
        elif state == 7:
            self.speed = 0.0
            if self.attack_sound:
                self.play_sound(self.attack_sound)
            self.chasing_time = float(_F32(self.chasing_time) + _F32(dt))
        elif state == 8:
            if prev != 8:
                d = self.play_sound_looping(self.aware_sound, False)
                self.speed = self.chase_speed
                self._change_state_later(d, 5)
                if d > 0:
                    self.change_state_to(WAITING)
                self.chasing_time = 0.0
        elif state == 9:
            home = self.initial_position or self.position
            if prev != 9:
                self.squared_distance_from_goal = math.inf
                self.find_direction_to(*home)
            self.play_sound(self.patrol_sound)
            self.speed = self.patrol_speed
            sq = self._squared_distance_to(home)
            if not (sq <= self.squared_distance_from_goal) or sq < HOME_SQUARED:
                self.change_state_to(0)
            self.squared_distance_from_goal = sq
        self.state_at_previous_frame = state
        if self.proximity_sound is not None and self.proximity_sound_radius != 0:
            self.adjust_proximity_sound_gain()

    def send_did_move_message(self) -> None:
        """`-[PGEEnemy sendDidMoveMessage]` - checkRanges only."""
        self.check_ranges()
