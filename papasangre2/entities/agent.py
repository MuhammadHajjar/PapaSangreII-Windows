"""`PGEGameAgent` as Papa Sangre II has it - the base of every agent.

Recovered in docs/notes/M2_NOTES.md ("PGEGameAgent").  The points the data
leans on:

* `setActive:YES` from inactive **defers** `activate` to a main-queue block;
  `setActive:NO` from active runs `deactivate` at once;
* activation by name counts `activationCounter` down (default 1) and only
  activates at zero or below;
* `deactivate` stops the sound without its end trigger (`forceStopCallback`)
  and then fires `OnDeactivate`;
* collisions: entering `collideRadius` (default 10) fires `OnCollide` once and
  tells the player the agent is within reach; leaving tells it again;
* the "shooting range": the agent is within `shootRange` (default 450) and
  inside a cone of cos > 0.92 (about 23 degrees) of where the player faces -
  entering it fires `OnEnteringShootRange`.  That is how the Intro knows you
  have turned to face the record player or the fountain;
* the "beating range" is the same cone within `beatRadius` (default 30);
  entering it plays `beatRangeSound` once.  A beat of the player's
  (`PlayerDidBeat`) beats every active agent inside it (`wasBeaten`) and
  misses every other active one (`wasMissed` and `OnBeatMissed`);
* a shake (`PGE_ACTION_Shake`) within `collideRadius` fires `OnShake`, unless
  the level is paused;
* a louder sound (`StartedSoundWithPriority` from someone else, higher
  priority) stops this agent's sound and fires its `OnSoundEnd`;
* path following at `speed` (default 10 px/s), a new patrol point whenever the
  agent stops getting closer to the current one.
"""

from __future__ import annotations

import contextlib
import math
import random

import numpy as np

from ..assets.tiled import LevelObject, ns_bool, ns_float, ns_int
from ..core.messages import MessageBus, Params
from ..core.triggers import TriggerHost
from .player import REVERB, play, setup_reverb

_F32 = np.float32


def _div(a: float, b: float) -> float:
    """IEEE division, as Objective-C does it: 0/0 is NaN, x/0 is +-inf."""
    try:
        return a / b
    except ZeroDivisionError:
        if a == 0 or math.isnan(a):
            return math.nan
        return math.copysign(math.inf, a) * (math.copysign(1.0, b))

COLLIDE_RADIUS = 10.0
SPEED = 10.0
SHOOT_RANGE = 450.0
BEAT_RADIUS = 30.0
BEAT_DOT_PROD = 0.92
TICK = 0.05
FADE_TICK = 0.05           # fadeOutSound: NSTimer interval
#: userDidRotateDevice: - dispatch_after 800,000,000 ns, then tryToActivateAgent.
ROTATE_RETRY = 0.8
#: Decision 14: the soundless shake targets that play the whoosh, by (level,
#: agent) - the memories do it themselves (entities/collectible.py).
SHAKE_WHOOSH = {('ps2_18b', 'instruction_shake')}


class GameAgent(TriggerHost):
    """One agent of a level."""

    kind = 'agent'

    def __init__(self, bus: MessageBus, world, obj: LevelObject | None = None,
                 rng: random.Random | None = None) -> None:
        super().__init__(bus, name='unnamed agent', rng=rng)
        self.world = world
        self.agent_type = 0
        self.agent_id = 0
        self.playlist_name = ''
        self.orientation_vector = (0.0, 0.0)
        self.shoot_range = SHOOT_RANGE
        self.speed = SPEED
        self.collide_radius = COLLIDE_RADIUS
        self.wet_gain = 1.0
        self.dry_gain = 1.0
        self.gain = 1.0
        self.beat_dot_prod = BEAT_DOT_PROD
        self.beat_radius = BEAT_RADIUS
        #: REQUESTED: nearer than this, in beating range whatever the angle
        #: (0 = never; only ps2_14's oil can, world/level.py REQUESTED_DATA)
        self.close_reach = 0.0
        self.beat_range_sound: str | None = None
        self.activation_counter = 1
        self._active = False
        self.paused = False
        self.unpausable = False
        self.force_stop_callback = False
        self.in_collide_range = False
        self.is_in_shooting_range = False
        self.is_in_beating_range = False
        self.squared_distance_from_player = 0.0
        self.player_position = (0.0, 0.0)
        self.player_orientation = 0.0
        self.player_orientation_vector = (0.0, 0.0)
        self.sound = None
        self.sounds: list[str] = []
        self.sound_list = ''
        self.sound_priority = 0
        self.intro_sound: str | None = None
        self.path = None
        self.has_path = False
        self.path_current_point = 0
        self.wanted_patrol_point = (0.0, 0.0)
        self.squared_distance_from_next_patrol_point = math.inf
        self.state = 0
        self.state_at_previous_frame = 0
        self.chase_speed = 0.0
        self.pause_sound: str | None = None
        self.pause_s3d = None
        self.sound_was_playing = False
        self.sound_was_paused = False
        self.pause_sound_was_paused = False
        self.follow_path_when_inactive = False
        self.requires_unplug = False
        self.requires_portrait_picture = False
        self.requires_landscape_picture = False
        self._listening_for_rotation = False
        self.initial_position: tuple[float, float] | None = None
        self.fade_reduce_step = 0.0
        self.dead = False
        self._fade_token = None
        if obj is not None:
            self.build(obj)
        for name, handler in (
            ('PGE_MESSAGE_PlayerMovedToPosition', self._player_moved),
            ('PGE_MESSAGE_MoveAgentToPosition', self._move_agent_to_position),
            ('PGE_MESSAGE_PlayerDidRotateToFixedAngle', self._player_did_rotate),
            ('PGE_MESSAGE_ActivateAgentWithName', self._activate_agent_with_name),
            ('PGE_MESSAGE_DeactivateAgentWithName', self._deactivate_agent_with_name),
            ('PGE_MESSAGE_FollowPathWithName', self._follow_path_with_name),
            ('PGE_MESSAGE_StopFollowingPath', self._stop_following_path),
            ('PGE_MESSAGE_LevelInited', self._level_inited),
            ('PGE_ACTION_HandsClapped', self._player_clapped),
            ('PGE_ACTION_Hand', self._hands_action),
            ('PGE_MESSAGE_PlaySpatialSoundOnAgentWithName', self._play_spatial_sound_on_agent),
            ('PGE_MESSAGE_ChangeSoundListOnAgentWithName', self._change_sound_list),
            ('PGE_MESSAGE_PlayerDidCollideAWall', lambda *_: self.trigger('OnHitWall')),
            ('PGE_MESSAGE_PauseAgents', lambda *_: self.pause_agents()),
            ('PGE_MESSAGE_UnpauseAgents', lambda *_: self.unpause_agents()),
            ('PGE_MESSAGE_StartedSoundWithPriority', self._started_sound_with_priority),
            ('PGE_MESSAGE_ResetAgentWithName', self._reset_agent_with_name),
            ('PGE_MESSAGE_FadeOutAgentWithName', self._fade_out_sound),
            ('PGE_MESSAGE_ActivateTriggerWithName', self._activate_trigger_with_name),
            ('PGE_ACTION_Shake', self._shake_detected),
            ('PGE_MESSAGE_AudioRouteChanged', self._audio_route_changed),
            ('PGE_MESSAGE_PlayerDidBeat', self._player_did_beat),
        ):
            bus.subscribe(name, handler)

    # ------------------------------------------------------------ building
    def build(self, obj: LevelObject) -> None:
        """What `createObjectFromDict:` set on this agent."""
        self.name = obj.name
        self.set_position(obj.x, obj.y)
        self.add_triggers(obj.triggers)
        a = obj.applied
        for key, attr, conv in (
            ('collideRadius', 'collide_radius', ns_float),
            ('shootRange', 'shoot_range', ns_float),
            ('speed', 'speed', ns_float),
            ('chaseSpeed', 'chase_speed', ns_float),
            ('gain', 'gain', ns_float),
            ('wetGain', 'wet_gain', ns_float),
            ('dryGain', 'dry_gain', ns_float),
            ('soundPriority', 'sound_priority', ns_int),
            ('activationCounter', 'activation_counter', ns_int),
            ('beatRadius', 'beat_radius', ns_float),
            ('beatDotProd', 'beat_dot_prod', ns_float),
            ('followPathWhenInactive', 'follow_path_when_inactive', ns_bool),
            ('requiresUnplug', 'requires_unplug', ns_bool),
            ('requiresPortraitPicture', 'requires_portrait_picture', ns_bool),
            ('requiresLandscapePicture', 'requires_landscape_picture', ns_bool),
            ('unpausable', 'unpausable', ns_bool),
        ):
            if key in a:
                setattr(self, attr, conv(a[key]))
        if 'soundList' in a:
            self.set_sound_list(str(a['soundList']))
        if 'introSound' in a:
            self.intro_sound = str(a['introSound'])
        if 'pauseSound' in a:
            self.pause_sound = str(a['pauseSound'])
        if 'beatRangeSound' in a:
            self.beat_range_sound = str(a['beatRangeSound'])
        # 'beatRange' (ps2_14, 15, 17) sets an ivar nothing reads: the reach
        # of a beat is beatRadius, which no level sets.

    def set_position(self, x: float, y: float) -> None:
        """`setPosition:` - the first position is kept as the initial one."""
        self.position = (float(x), float(y))
        if self.initial_position is None:
            self.initial_position = self.position

    def set_sound_list(self, value: str) -> None:
        """`setSoundList:` -> `setSoundsFromString:` (split on "&")."""
        self.sound_list = value
        self.sounds = value.split('&')

    @property
    def bank(self):
        return self.world.bank if self.world is not None else None

    # -------------------------------------------------------------- active
    @property
    def active(self) -> bool:
        return self._active

    def set_active(self, value: bool) -> None:
        """`setActive:` (0x1000227bc)."""
        old = self._active
        self._active = bool(value)
        if not old and value:
            self.bus.dispatch_async(self.activate)
        elif old and not value:
            self.deactivate()
        self.send_activity_changed_message()

    def send_activity_changed_message(self) -> None:
        self.bus.post('PGE_MESSAGE_AgentActivityChanged',
                      {'name': self.name, 'agentId': self.agent_id,
                       'active': self._active, 'agentType': self.agent_type})

    def activate(self) -> None:
        """`activate` (0x100023720)."""
        self.force_stop_callback = False
        if not self._active:
            self._active = True
            self.send_activity_changed_message()
        self.trigger('OnActivate')
        self.check_collisions_with_player()

    def try_to_activate_agent(self) -> None:
        """`tryToActivateAgent` (0x100022d54).

        An agent that needs the phone held a certain way listens for
        `PGE_INPUT_RotateDevice` and asks how it is held
        (`PGE_INPUT_CheckDeviceRotation`); `userDidRotateDevice:` takes it from
        there.  The counter has been counted down either way.
        """
        self.activation_counter -= 1
        if self.requires_landscape_picture or self.requires_portrait_picture:
            if not self._listening_for_rotation:
                # addObserver: again on every call; a second registration
                # changes nothing (the first clears the requirement), so one.
                self._listening_for_rotation = True
                with self._level_scope():
                    self.bus.subscribe('PGE_INPUT_RotateDevice', self._user_did_rotate_device)
            self.bus.post('PGE_INPUT_CheckDeviceRotation', {})
            return
        if self.activation_counter <= 0:
            self.set_active(True)
            self.check_collisions_with_player()
            self.check_ranges()

    def _level_scope(self):
        """Subscriptions made during play go with the level when it goes."""
        key = getattr(self.world, 'scope_key', None)
        return self.bus.scope(key) if key is not None else contextlib.nullcontext()

    def _user_did_rotate_device(self, _n, params: Params) -> None:
        """`userDidRotateDevice:` (0x100022ef8): held the way it wants, the
        requirement is dropped for good and it tries again 0.8 s later."""
        o = params.get('orientation')
        if o == 'portrait' and self.requires_portrait_picture:
            self.requires_portrait_picture = False
            self.bus.call_after(ROTATE_RETRY, self.try_to_activate_agent)
        elif o == 'landscape' and self.requires_landscape_picture:
            self.requires_landscape_picture = False
            self.bus.call_after(ROTATE_RETRY, self.try_to_activate_agent)

    def _activate_agent_with_name(self, _n, params: Params) -> None:
        if params.get('name') == self.name:
            self.try_to_activate_agent()

    def _deactivate_agent_with_name(self, _n, params: Params) -> None:
        """`deactivateAgentWithName:` (0x1000232a0)."""
        target = params.get('name')
        if target != self.name:
            if target != '*':
                return
            if 'type' in params and ns_int(params['type']) != self.agent_type:
                return
        if self.requires_landscape_picture or self.requires_portrait_picture:
            self.bus.unsubscribe_all(self._user_did_rotate_device)
            self._listening_for_rotation = False
        self.set_active(False)
        if ns_bool(params.get('clean', 'NO')):
            self.clear_delays()

    def deactivate_with_no_callback(self) -> None:
        """`deactivateWithNoCallback` (0x100023810)."""
        self.force_stop_callback = True
        if self.sound is not None and self.sound.playing:
            self.sound.stop()
        if self.sound is not None and self.world is not None:
            self.world.monitors.remove_sound(self.sound)
        self.sound = None
        self._active = False
        self.send_did_move_message()
        self.send_activity_changed_message()
        if self.in_collide_range:
            self.bus.post('PGE_MESSAGE_InCollideRangeValueChanged',
                          {'senderName': self.name, 'value': False})

    def deactivate(self) -> None:
        """`deactivate` (0x100023b44)."""
        self.deactivate_with_no_callback()
        self.trigger('OnDeactivate')

    def _reset_agent_with_name(self, _n, params: Params) -> None:
        if params.get('name') != self.name:
            return
        self.set_active(False)
        if self.initial_position is not None:
            self.position = self.initial_position
        self.state = 0
        self.dead = False
        self.send_did_move_message()

    # ---------------------------------------------------------- the player
    def _player_moved(self, _n, params: Params) -> None:
        """`playerMovedToPosition:` (0x100022340)."""
        pos = params.get('position', (0.0, 0.0))
        self.player_position = (float(pos[0]), float(pos[1]))
        if not self._active:
            return
        if self.player_position[0] != 0.0 and self.player_position[1] != 0.0:
            self.check_collisions_with_player()
        self.update_spatialized_sound()
        self.check_ranges()
        if params.get('justStepped'):
            self.trigger('OnStep')

    def _player_did_rotate(self, _n, params: Params) -> None:
        """`playerDidRotate:` (0x10002471c)."""
        self.player_orientation = float(params.get('orientation', 0.0))
        ov = params.get('orientationVector', (0.0, 0.0))
        self.player_orientation_vector = (float(ov[0]), float(ov[1]))
        self.update_spatialized_sound()
        self.check_ranges()

    def check_collisions_with_player(self) -> None:
        """`checkCollisionsWithPlayer` (0x100025664)."""
        if not self._active or self.collide_radius <= 0:
            return
        dx = _F32(self.player_position[0] - self.position[0])
        dy = _F32(self.player_position[1] - self.position[1])
        sq = _F32(dx * dx + dy * dy)
        self.squared_distance_from_player = float(sq)
        r = _F32(self.collide_radius)
        was = self.in_collide_range
        if sq < r * r:
            if not was:
                self.collides_with_player()
                self.in_collide_range = True
                self.bus.post('PGE_MESSAGE_InCollideRangeValueChanged',
                              {'senderName': self.name, 'value': True})
            else:
                self.in_collide_range = True
        else:
            self.in_collide_range = False
            if was:
                self.bus.post('PGE_MESSAGE_InCollideRangeValueChanged',
                              {'senderName': self.name, 'value': False})

    def collides_with_player(self) -> None:
        self.trigger('OnCollide')

    def check_ranges(self) -> None:
        """`checkRanges` (0x10002487c): the facing cone."""
        shoot = beat = False
        if self._active and self.collide_radius > 0:
            dx = _F32(self.position[0] - self.player_position[0])
            dy = _F32(self.position[1] - self.player_position[1])
            dist = _F32(math.sqrt(float(_F32(dx * dx + dy * dy))))
            with np.errstate(divide='ignore', invalid='ignore'):
                ux = float(_F32(dx / dist))
                uy = float(_F32(dy / dist))
            px, py = self.player_orientation_vector
            dot = _F32(px * ux + py * uy)
            if dot > _F32(self.beat_dot_prod) and dist < _F32(self.shoot_range):
                shoot = True
                beat = bool(dist < _F32(self.beat_radius))
            elif dist < _F32(self.close_reach):
                beat = True             # right on top of it: no angle to miss by
        self.set_is_in_shooting_range(shoot)
        self.set_is_in_beating_range(beat)

    def set_is_in_beating_range(self, value: bool) -> None:
        """`setIsInBeatingRange:` (0x100025124): coming into it, an active,
        living agent plays its `beatRangeSound` - at gain 0.5, once, and left
        where that sound last was (the agent does not place it)."""
        if (not self.is_in_beating_range and value and self._active and not self.dead
                and self.beat_range_sound and self.bank is not None):
            s = self.bank.any_sound_with_prefix(self.beat_range_sound)
            if s is not None:
                s.gain = 0.5
                play(s, False)
        self.is_in_beating_range = bool(value)

    def set_is_in_shooting_range(self, value: bool) -> None:
        """`setIsInShootingRange:` (0x100025064)."""
        old = self.is_in_shooting_range
        self.is_in_shooting_range = value
        if not old and value and self._active:
            self.trigger('OnEnteringShootRange')
            self.bus.post('PGE_MESSAGE_AgentEnteredOrExitedShootRange', {'agent': self})
        if old and not value and self._active:
            self.bus.post('PGE_MESSAGE_AgentEnteredOrExitedShootRange', {'agent': self})

    # ------------------------------------------------------------ shot at
    def was_shot(self) -> None:
        """`-[PGEGameAgent wasShot]` (0x100025444): one more kill in the save
        (whatever was hit), then `OnShoot` if active."""
        progress = getattr(self.world, 'progress', None)
        if progress is not None:
            progress.total_kills = progress.total_kills + 1
        self.trigger_on_shoot()

    def was_missed(self) -> None:
        """`-[PGEGameAgent wasMissed]` (0x1000254d8)."""
        self.trigger_on_shoot_missed()

    # ------------------------------------------------------------- beaten
    def _player_did_beat(self, _n, _p) -> None:
        """`playerDidBeat:` (0x100024f30): active and in the beating range ->
        `wasBeaten` and the player's beat touched something; active and out of
        it -> `wasMissed` (so `OnShootMissed`) and `OnBeatMissed`."""
        if not self._active:
            return
        if self.is_in_beating_range:
            self.was_beaten()
            player = self.world.player if self.world is not None else None
            if player is not None:
                player.shot_touched_a_target = True
        else:
            self.was_missed()
            self.trigger('OnBeatMissed')

    def was_beaten(self) -> None:
        """`-[PGEGameAgent wasBeaten]` (0x1000253c8): one more kill in the save."""
        progress = getattr(self.world, 'progress', None)
        if progress is not None:
            progress.total_kills = progress.total_kills + 1

    # -------------------------------------------------------------- shaken
    def _shake_detected(self, _n, _p) -> None:
        """`shakeDetected:` (0x10002411c): not while the level is paused;
        active, and the player nearer than `collideRadius` (by the squared
        distance last measured) -> `OnShake`."""
        if self.world is not None and getattr(self.world, 'paused_game', False):
            return
        if not self._active:
            return
        r = _F32(self.collide_radius)
        if _F32(self.squared_distance_from_player) < _F32(r * r):
            self.trigger('OnShake')
            self._requested_shake_whoosh()

    def _requested_shake_whoosh(self) -> None:
        """REQUESTED (decision 14): a shake that something with no sound of its
        own is counting - ps2_18b's record, `OnShake ... afterCount=7` - plays
        the game's whoosh, up to the shake that releases it."""
        w = self.world
        if w is None or (getattr(w, 'name', None), self.name) not in SHAKE_WHOOSH:
            return
        want = 'ONSHAKE'
        counting = any(t.trigger_type.upper() == want and a is not None and a >= -1
                       for t, a in zip(self.triggers, self._after))
        hook = getattr(w, 'play_whoosh', None)
        if counting and hook is not None:
            hook()

    # ---------------------------------------------------------- headphones
    def _audio_route_changed(self, _n, params: Params) -> None:
        """`audioRouteChanged:` (0x100023fe8): an agent that `requiresUnplug`,
        active, hearing the headphones come out, drops the requirement and
        fires `OnRouteChange` (ps2_18b).  The original also turns the iPod
        music player to full volume, which has no counterpart here."""
        if not (self.requires_unplug and self._active):
            return
        if not ns_bool(params.get('unplugged', False)):
            return
        self.requires_unplug = False
        self.trigger('OnRouteChange')

    def trigger_on_shoot(self) -> None:
        """`triggerOnShoot` (0x10002553c)."""
        if self._active:
            self.trigger('OnShoot')

    def trigger_on_shoot_missed(self) -> None:
        """`triggerOnShootMissed` (0x1000254e8)."""
        if self._active:
            self.trigger('OnShootMissed')

    def _player_clapped(self, _n, _p) -> None:
        if self._active:
            self.trigger('OnClap')

    def _hands_action(self, _n, params: Params) -> None:
        """`handsActionMessageReceived:` (0x100024a48): within reach only."""
        if not self.in_collide_range or not self._active:
            return
        player = self.world.player if self.world is not None else None
        if player is not None and _F32(player.reload_timer) <= _F32(player.reload_time):
            return
        if player is not None:
            self.bus.dispatch_async(lambda: setattr(player, 'reload_timer', 0.0))
        hand = params.get('Hand')
        if hand == 'L':
            self.trigger('OnLeftHand')
        if hand == 'R':
            self.trigger('OnRightHand')

    # --------------------------------------------------------------- sound
    def setup_reverb_parameters(self, sound=None) -> None:
        """`-[PGEGameAgent setupReverbParameters:]` (0x100021df4).

        As the player's version, plus the agent's own ``gain`` onto the sound
        (a PlaySpatialSound with no ``gain`` parameter plays at it).  Its
        ``stream`` / ``unloadOnStop`` copy is memory management with no
        counterpart here.
        """
        s = sound if sound is not None else self.sound
        setup_reverb(s, self.dry_gain, self.wet_gain)
        if s is not None:
            s.gain = self.gain

    def find_direction_to_player(self) -> float:
        """`-[PGEGameAgent findDirectionToPlayer]` (0x100025590)."""
        ox = self.player_position[0] - self.position[0]
        oy = self.player_position[1] - self.position[1]
        n = float(_F32(math.sqrt(ox * ox + oy * oy)))
        if n == 0.0:
            self.orientation_vector = (0.0, 0.0)
        else:
            self.orientation_vector = (ox / n, oy / n)
        return float(_F32(_div(n, float(_F32(self.chase_speed)))))

    def update_spatialized_sound(self) -> None:
        """`updateSpatializedSound` (0x100024de4)."""
        if self.sound is not None and self.sound.spatialized:
            self.sound.planar = self.position

    def send_did_move_message(self) -> None:
        """`sendDidMoveMessage` - checkRanges."""
        self.check_ranges()

    def _play_spatial_sound_on_agent(self, _n, params: Params) -> None:
        """`playSpatialSoundOnAgentWithName:` (0x100026348)."""
        if params.get('agentName') != self.name:
            return
        name = params.get('soundName')
        if name is None or self.bank is None:
            return
        s = self.bank.any_sound_containing(str(name))
        if s is None:
            return
        s.spatialized = True
        self.setup_reverb_parameters(s)
        loop = ns_bool(name) if 'loop' in params else False
        if 'gain' in params:
            s.gain = ns_float(params['gain'])
        s.planar = self.position
        play(s, loop)

    def _change_sound_list(self, _n, params: Params) -> None:
        if params.get('name') is None or params.get('name') != self.name:
            return
        self.set_sound_list(str(params.get('soundList', '')))
        self.update_spatialized_sound()

    def _started_sound_with_priority(self, _n, params: Params) -> None:
        """`startedSoundWithPriority:` (0x100024220)."""
        if self.sound_priority == 0:
            return
        if params.get('name') == self.name:
            return
        if ns_int(params.get('priority', 0)) <= self.sound_priority:
            return
        if self.sound is not None and self.sound.playing:
            self.sound.stop()
            if self.world is not None:
                self.world.monitors.remove_sound(self.sound)
            self.trigger('OnSoundEnd')

    def _fade_out_sound(self, _n, params: Params) -> None:
        """`fadeOutSound:` (0x100023b88): a 0.05 s timer, then stop."""
        if params.get('name') != self.name or self.sound is None:
            return
        duration = ns_float(params.get('duration', 0))
        if duration < 0:
            duration = 1.0
        steps = int(float(_F32(duration) / _F32(FADE_TICK)))
        self.fade_reduce_step = float(_F32(self.sound.gain) / _F32(steps)) if steps else self.sound.gain
        token = (id(self), 'fade')
        self.bus.cancel(token)
        sound = self.sound

        def reduce():
            if self.sound is not sound:
                return
            g = float(_F32(sound.gain) - _F32(self.fade_reduce_step))
            sound.gain = g if g > 0 else 0.0
            self.bus.call_after(FADE_TICK, reduce, token)

        self.bus.call_after(FADE_TICK, reduce, token)

        def stop_after():
            self.bus.cancel(token)
            if sound.playing:
                sound.stop()
            sound.gain = self.gain
        self.bus.call_after(duration, stop_after)

    def _activate_trigger_with_name(self, _n, params: Params) -> None:
        if params.get('senderName') == self.name and params.get('name'):
            self.trigger(str(params['name']))

    def _move_agent_to_position(self, _n, params: Params) -> None:
        if self.position[0] != 0.0 and self.position[1] != 0.0:
            self.check_collisions_with_player()
        if params.get('name') is None or params.get('name') != self.name:
            return
        self.position = (ns_float(params.get('x', 0)), ns_float(params.get('y', 0)))
        self.send_did_move_message()
        self.update_spatialized_sound()

    # --------------------------------------------------------------- paths
    def _follow_path_with_name(self, _n, params: Params) -> None:
        """`followPathWithName:` (0x100025de8)."""
        if params.get('senderName') != self.name:
            return
        want = params.get('name')
        if self.path is not None and want is not None and self.path.name == want:
            return
        path = self.world.path_with_name(want) if self.world is not None else None
        self.path = path
        if path is None:
            return
        self.has_path = True
        self.state = 1
        self.find_next_patrol_point()

    def _stop_following_path(self, _n, params: Params) -> None:
        """`stopFollowingPath:` (0x100025cb8)."""
        if params.get('senderName') != self.name:
            return
        self.state = 0
        self.orientation_vector = (0.0, 0.0)
        self.has_path = False

    def find_next_patrol_point(self) -> None:
        """`findNextPatrolPoint` (0x100025a14)."""
        if self.state != 1 or self.path is None:
            return
        pts = self.path.points
        if self.path_current_point >= len(pts):
            self.path_current_point = 0
            self.wanted_patrol_point = pts[0]
            self.trigger('OnPathEnd')
        else:
            self.wanted_patrol_point = pts[self.path_current_point]
        wx, wy = pts[self.path_current_point]
        ox, oy = wx - self.position[0], wy - self.position[1]
        n = float(_F32(math.sqrt(ox * ox + oy * oy)))
        if n > 0:
            ox, oy = ox / n, oy / n
        self.orientation_vector = (ox, oy)
        self.squared_distance_from_next_patrol_point = float(_F32(n) * _F32(n))
        self.path_current_point += 1

    # -------------------------------------------------------------- update
    def update(self, dt: float) -> None:
        """`-[PGEGameAgent update:]` (0x1000224f8)."""
        self.update_delays(dt)
        if self.paused:
            return
        moving = self._active or self.follow_path_when_inactive
        if self.has_path and moving:
            wx, wy = self.wanted_patrol_point
            px, py = self.position
            sq = _F32(_F32(wx - px) * _F32(wx - px) + _F32(wy - py) * _F32(wy - py))
            if sq == 0 or sq > _F32(self.squared_distance_from_next_patrol_point):
                self.squared_distance_from_next_patrol_point = math.inf
                self.find_next_patrol_point()
            else:
                self.squared_distance_from_next_patrol_point = float(sq)
        if self.speed > 0 and self.orientation_vector != (0.0, 0.0) and moving:
            px, py = self.position
            ox, oy = self.orientation_vector
            sp = float(_F32(self.speed))
            self.position = (px + ox * sp * dt, py + oy * sp * dt)
            self.send_did_move_message()
            self.update_spatialized_sound()
            self.check_collisions_with_player()

    # --------------------------------------------------------------- pause
    def pause_agents(self) -> None:
        """`pauseAgents` (0x1000272e4): freeze, and play the pause sound.

        The pause sound loops, placed where the agent's sound is (the origin
        when it has none).
        """
        if self.unpausable:
            return
        self.paused = True
        s = self.sound
        self.sound_was_playing = bool(s is not None and s.playing)
        if s is not None:
            s.pause()
        if not self.pause_sound or self.bank is None:
            return
        p = self.bank.any_sound_with_prefix(self.pause_sound)
        self.pause_s3d = p
        if p is None:
            return
        p.spatialized = True
        p.planar = s.planar if s is not None else (0.0, 0.0)
        play(p, True)

    def unpause_agents(self) -> None:
        """`unpauseAgents` (0x1000274e8).

        The agent's sound is started again with a plain `play` - from the top
        and not looping, which is what `-[S3DSound play]` (`play:NO`) does.
        """
        if self.unpausable:
            return
        self.paused = False
        if self._active and self.sound_was_playing and self.sound is not None:
            self.sound.stop()
            play(self.sound, False)
        if self.pause_s3d is not None and self.pause_s3d.playing:
            self.pause_s3d.stop()

    def _level_inited(self, _n, _p) -> None:
        self.trigger('OnLoad')

    def __repr__(self) -> str:
        return f'<{type(self).__name__} {self.name!r} {"on" if self._active else "off"}>'
