"""`PGEPlayer` as Papa Sangre II has it.

Everything here is read from the PS2 binary; docs/notes/M2_NOTES.md
("PGEPlayer") has the addresses.  What changed from PS1 and matters most:

* **a step does not move you**: `moveForwardOneStep:` only sets
  `nextStepPosition` (5 px ahead); `update:` (every 0.1 s) glides the position
  towards it at `stepSpeed` 25 px/s, and it is the glide that posts
  `PlayerMovedToPosition`;
* footsteps are named `<speed>_<prefix>` ("footwalk_gravel", "footrun_gravel"),
  with no left/right;
* the surface under the next step sets the footstep bank, the footstep gain,
  and (through the level) the trip and run tempos;
* tripping and walking into walls play a spoken warning the first two times
  in the whole game, on levels numbered 9 or less;
* hands and clapping are the player's now (`handsActionMessageReceived:`,
  `clap:`), as is `PGE_MESSAGE_PlaySound` with its sound priorities;
* the air rifle (M4): a hand whose action is "shoot" fires at the nearest
  agent in the shooting cone (`shoot:`); every other agent in the cone is
  missed;
* underwater (M4, ps2_7's smoke): the level adds 0.05 s every tick while the
  player stands on an `isUnderwater` floor; past 3/4 of `underwaterMaxDuration`
  `OnGagging` fires and the gagging sound loops, past all of it the player
  drowns (`restartLevel:@"drown"`).  Any other floor resets the clock.
"""

from __future__ import annotations

import math
import random

import numpy as np

from ..core.messages import MessageBus, Params
from ..core.triggers import TriggerHost
from ..assets.tiled import ns_bool, ns_float, ns_int

STATE_STILL, STATE_WALKING, STATE_RUNNING, STATE_TRIPPED = 0, 1, 2, 3
STATE_NAMES = ('Standing', 'Walking', 'Running', 'Tripping', 'Jumping',
               'Rotating', 'Swimming')

#: -[PGEPlayer init] (0x100029c18)
PIXELS_PER_STEP = 5.0
STEP_SPEED = 25.0
PATH_SPEED = 10.0
FOOTSTEPS_GAIN = 0.5
TRIP_BPM = 10000.0
RUN_BPM = 180.0
WET_GAIN = 0.5
DRY_GAIN = 1.0
#: increaseUnderwaterDuration: - gagging starts past this share of the maximum.
GAGGING_SHARE = 0.75
#: shoot: - the rifle's reverb send.
SHOOT_WET_GAIN = 0.5
BEAT_SOUND = 'stab_missed'
#: beat: - the miss sound's reverb send (setWetGain: 0.5)
BEAT_WET_GAIN = 0.5
#: Decision 17's exception: what you hold is heard on your side, whoever
#: sends it - ps2_18's camera click comes from you, the hit from Papa; the
#: knife's swing (`beatsound`, ps2_15/17) from you, the stab from the bear.
IN_YOUR_HANDS = ('18_camera_photo_taken', 'beatsound')
#: REQUESTED (decision 21): waving your hands or the knife about for nothing
#: draws a line - ps2_1's "stop waving your hands" (6 empty presses, left and
#: right in turn, each within WAVE_GAP of the last), ps2_15's "stop waving
#: that knife around" (4 swings that hit nothing, each within WAVE_GAP).
WAVING = {
    'ps2_1': ('hands', '1_SPEECH_prompt_hands', 6),
    'ps2_15': ('knife', '15_SPEECH_prompt_stop_slashing_UOS', 4),
}
WAVE_GAP = {'hands': 1.5, 'knife': 3.0}
#: REQUESTED (decision 21): the wall and trip lines ("You've walked into a
#: wall...", "On your feet, quick!") for the first WARNING_TIMES + 1 of each
#: level; the original counts them over the whole game, so after the Intro
#: they were never heard again.  The tester then heard them in every level
#: and asked for them up to level 2 only (2026-09-26): WARNING_LEVELS.
PER_LEVEL_WARNINGS = True
WARNING_LEVELS = ('ps2_Intro', 'ps2_1')
#: Decision 19: footsteps whose trip sounds are filed under another name -
#: the Intro's squelchy gravel (trip_gravel_squelch_*) and ps2_3's cracker
#: floor (its folder's trips are named trip_stone_*).
TRIP_ALIASES = {'squelch_gravel': 'gravel_squelch', 'cracker': 'stone'}
#: updateBPMCounter: at most five intervals, footrun at 200 - bpm_constaint.
SPEED_THRESHOLD_BPM = 200.0
#: checkStepBPM: the tempo reset while fewer than three steps are known.
EARLY_WALK_BPM = 30.0
TRIP_RECOVERY = 2.0
#: trip: -> AlertAllEnemies 0.3 s later (dispatch_after 300,000,000 ns).
TRIP_ALERT_DELAY = 0.3
#: rotatePlayer...: PlayerDidRotateToFixedAngle only past 5 degrees.
HRTF_UPDATE_ANGLE = math.radians(5.0)        # 0.08726646259971647
#: the spoken warnings: first two in the game, levels numbered <= 9.
WARNING_TIMES = 1
WARNING_MAX_LEVEL = 9
#: setupReverbParameters: - the same five values for every sound it touches.
REVERB = dict(auto_mix=True, min_distance=1.0, max_distance=100.0,
              min_wet_send=0.05, max_wet_send=0.3)

_F32 = np.float32


def level_number(name: str) -> int:
    """`[[[name componentsSeparatedByString:@"_"] objectAtIndex:1] intValue]`."""
    parts = (name or '').split('_')
    if len(parts) < 2:
        return 0                               # objectAtIndex:1 would throw; no level hits this
    return ns_int(parts[1])


def setup_reverb(sound, dry_gain: float, wet_gain: float) -> None:
    """`-[PGEPlayer setupReverbParameters:]` (and the agents' version)."""
    if sound is None:
        return
    sound.dry_gain = dry_gain
    sound.wet_gain = wet_gain
    sound.send_to_reverb = wet_gain > 0
    sound.reverb_mix = dict(REVERB)


def play(sound, looping: bool = False) -> None:
    """`[S3DSound play:looping]`."""
    sound.looping = bool(looping)
    sound.play()


class Player(TriggerHost):
    """The listener, and the only thing the player moves."""

    kind = 'player'

    def __init__(self, bus: MessageBus, level=None, bank=None, progress=None,
                 rng: random.Random | None = None, vibrate=None) -> None:
        super().__init__(bus, name='player', position=(0.0, 0.0), rng=rng)
        self.level = level
        self.bank = bank
        self.progress = progress
        self.vibrate_fn = vibrate
        # -- init
        self.last_hrtf_angle = math.inf
        self.player_angle = 0.0
        self.orientation_vector = (1.0, 0.0)
        self.pixels_per_step = PIXELS_PER_STEP
        self.footsteps_gain = FOOTSTEPS_GAIN
        self.walk_bpm = 0.0
        self.walk_times: list[float] = []
        self.trip_bpm = TRIP_BPM
        self.run_bpm = RUN_BPM
        self.bpm_constraint = 0.0
        self.last_foot = ''
        self.speed = ''
        self.beat_sound = BEAT_SOUND
        self.path_speed = PATH_SPEED
        self.step_speed = STEP_SPEED
        self.left_hand_action = ''
        self.right_hand_action = ''
        self.wet_gain = WET_GAIN
        self.dry_gain = DRY_GAIN
        self.state = STATE_STILL
        self.proximity_radius = 0.0
        self.next_step_position = (0.0, 0.0)
        self.next_step_orientation = (0.0, 0.0)
        self.just_stepped = False
        self.footsteps_prefix: str | None = None
        self.shuffle_sound = ''
        self.clap_sound: str | None = None
        self.jump_sound: str | None = None
        self.empty_left_hand_sound: str | None = None
        self.empty_right_hand_sound: str | None = None
        self.disable_clap = False
        self.clap_times: list[float] = []
        self.objects_in_range: set[str] = set()
        self.reload_time = 0.0
        self.reload_timer = 0.0
        self.constant_speed = 0.0
        self.has_path = False
        # -- riding a path (makePlayerFollowPathWithName:)
        self.path = None
        self.path_current_point = 0
        self.wanted_patrol_point = (0.0, 0.0)
        self.next_path_direction = (0.0, 0.0)
        self.squared_distance_from_next_patrol_point = 0.0
        self.rail_update = 0
        self.is_underwater = False
        # -- the rifle
        self.shoot_sound: str | None = None
        self.shot_touched_a_target = False
        #: agentsInShootingRange - an NSMutableSet; kept in arrival order
        self.agents_in_shooting_range: list = []
        # -- underwater
        self.underwater_duration = 0.0
        self.underwater_max_duration = 0.0
        self.gagging_sound: str | None = None
        self.drowning_sound: str | None = None
        self.gagging_s3d = None
        self.gagging = False
        self.drowning = False
        self.voice_over_sound = None
        self.voice_over_priority = 0
        #: decision 21: this level's own wall and trip counts, and the waving
        self.level_trip_times = 0
        self.level_wall_times = 0
        self._wave = []
        self._wave_line = None
        self._wave_last = None
        self.start_angle = 0.0
        self.paused = False

        for name, handler in (
            ('PGE_MESSAGE_LevelInited', self._level_inited),
            ('PGE_ACTION_RotatePlayerFromAngle', self._rotate_from),
            ('PGE_ACTION_RotatePlayerToFixedAngle', self._rotate_to),
            ('PGE_ACTION_OneStep', self._one_step),
            ('PGE_ACTION_Jump', self._jump),
            ('PGE_ACTION_Hand', self._hands_action),
            ('PGE_MESSAGE_ChangeHandAction', self._change_hands_action),
            ('PGE_ACTION_Trip', self._trip_action),
            ('PGE_ACTION_HandsClapped', self._clap),
            ('PGE_MESSAGE_DisableClap', self._disable_clap_msg),
            ('PGE_MESSAGE_EnableClap', self._enable_clap_msg),
            ('PGE_MESSAGE_InCollideRangeValueChanged', self._in_collide_range),
            ('PGE_MESSAGE_PlayerWalkedOnSurfaceWithId', self._walked_on_surface),
            ('PGE_MESSAGE_MovePlayerToPosition', self._move_to),
            ('PGE_MESSAGE_PlaySound', self._play_sound_msg),
            ('PGE_MESSAGE_ApplyBpmConstraint', self._bpm_constraint),
            ('PGE_ACTION_Shuffle', self._shuffle),
            ('PGE_MESSAGE_ApplyProximityRadiusToPlayer', self._proximity),
            ('PGE_MESSAGE_StartedSoundWithPriority', self._started_sound_with_priority),
            ('PGE_MESSAGE_Vibrate', self._vibrate_msg),
            ('PGE_MESSAGE_AgentEnteredOrExitedShootRange', self._agent_entered_or_exited_shoot_range),
            ('PGE_MESSAGE_ResetUnderwaterTimer', lambda *_: self.reset_underwater_duration()),
            ('PGE_MESSAGE_FollowPathWithName', self._follow_path_with_name),
            ('PGE_MESSAGE_MakePlayerFollowPathWithName', self._make_player_follow_path_with_name),
            ('PGE_MESSAGE_StopFollowingPath', self._stop_following_path),
            ('PGE_MESSAGE_ShutDownLevel', lambda *_: self.stop_following_path()),
        ):
            bus.subscribe(name, handler)

    # ------------------------------------------------------------ building
    def apply(self, obj) -> None:
        """The Player object's data (loadPlayer:)."""
        a = obj.applied
        self.add_triggers(obj.triggers)
        if 'pixelsPerStep' in a:
            self.pixels_per_step = ns_float(a['pixelsPerStep'])
        if 'footstepsGain' in a:
            self.footsteps_gain = ns_float(a['footstepsGain'])
        if 'clapSound' in a:
            self.clap_sound = str(a['clapSound'])
        if 'jumpSound' in a:
            self.jump_sound = str(a['jumpSound'])
        if 'leftHandAction' in a:
            self.left_hand_action = str(a['leftHandAction'])
        if 'rightHandAction' in a:
            self.right_hand_action = str(a['rightHandAction'])
        if 'emptyLeftHandSound' in a:
            self.empty_left_hand_sound = str(a['emptyLeftHandSound'])
        if 'emptyRightHandSound' in a:
            self.empty_right_hand_sound = str(a['emptyRightHandSound'])
        if 'reloadTime' in a:
            self.reload_time = ns_float(a['reloadTime'])
        if 'shootSound' in a:
            self.shoot_sound = str(a['shootSound'])
        if 'underwaterMaxDuration' in a:
            self.underwater_max_duration = ns_float(a['underwaterMaxDuration'])
        if 'gaggingSound' in a:
            self.gagging_sound = str(a['gaggingSound'])
        if 'drowningSound' in a:
            self.drowning_sound = str(a['drowningSound'])
        if 'stepSpeed' in a:
            self.step_speed = ns_float(a['stepSpeed'])
        if 'pathSpeed' in a:
            self.path_speed = ns_float(a['pathSpeed'])
        if 'beatSound' in a:
            self.beat_sound = str(a['beatSound'])
        if 'constantSpeed' in a:
            self.constant_speed = ns_float(a['constantSpeed'])
        if 'wetGain' in a:
            self.wet_gain = ns_float(a['wetGain'])
        if 'dryGain' in a:
            self.dry_gain = ns_float(a['dryGain'])
        if 'startAngle' in a:
            self.set_start_angle(ns_float(a['startAngle']))

    # ------------------------------------------------------------ helpers
    def _level_name(self) -> str:
        return getattr(self.level, 'name', '') if self.level is not None else ''

    def _highest_priority(self) -> int:
        return self.level.highest_priority_playing_sound() if self.level is not None else 0

    def get_state_dictionary(self) -> Params:
        """`getStateDictionnary` (0x10002c84c)."""
        return {
            'position': self.position,
            'speed': self.speed,
            'lastFoot': self.last_foot,
            'orientation': self.player_angle,
            'orientationVector': self.orientation_vector,
            'state': self.state,
            'stateTextValue': STATE_NAMES[self.state] if 0 <= self.state < len(STATE_NAMES) else '',
            'justStepped': self.just_stepped,
        }

    def setup_reverb_parameters(self, sound) -> None:
        setup_reverb(sound, self.dry_gain, self.wet_gain)

    # ------------------------------------------------------------ rotation
    def set_start_angle(self, degrees: float) -> None:
        """`setStartAngle:` posts RotatePlayerToFixedAngle, degrees * pi / 180."""
        self.start_angle = float(degrees)
        self.bus.post('PGE_ACTION_RotatePlayerToFixedAngle',
                      {'value': float(_F32(float(_F32(degrees)) * math.pi / 180.0))})

    def compute_new_orientation_vector(self) -> None:
        x = math.cos(self.player_angle)
        y = math.sin(self.player_angle)
        n = float(np.float32(x * x + y * y))
        if n > 0:
            n = math.sqrt(n)
            x, y = x / n, y / n
        self.orientation_vector = (x, y)

    def _after_rotation(self) -> None:
        self.compute_new_orientation_vector()
        if abs(float(_F32(self.last_hrtf_angle) - _F32(self.player_angle))) > HRTF_UPDATE_ANGLE:
            self.last_hrtf_angle = self.player_angle
            self.bus.post('PGE_MESSAGE_PlayerDidRotateToFixedAngle',
                          self.get_state_dictionary())

    def rotate_from_angle(self, delta: float) -> None:
        """`rotatePlayerFromAngle:` (0x10002c31c): one wrap, not a modulo."""
        a = float(_F32(delta) + _F32(self.player_angle))
        if a < 0:
            a = float(_F32(a + 2 * math.pi))
        elif a > 2 * math.pi:
            a = float(_F32(a - 2 * math.pi))
        self.player_angle = a
        self._after_rotation()

    def rotate_to_fixed(self, angle: float) -> None:
        """`rotatePlayerToFixedRotation:` (0x10002c5c0)."""
        a = float(_F32(angle))
        if a < 0:
            a = float(_F32(a + 2 * math.pi))
        elif a > 2 * math.pi:
            a = float(_F32(a - 2 * math.pi))
        self.player_angle = a
        self._after_rotation()

    def _rotate_from(self, _n, params: Params) -> None:
        self.rotate_from_angle(ns_float(params.get('value', params.get('angle', 0))))

    def _rotate_to(self, _n, params: Params) -> None:
        self.rotate_to_fixed(ns_float(params.get('value', params.get('angle', 0))))

    @property
    def bearing_degrees(self) -> float:
        return math.degrees(self.player_angle)

    # ------------------------------------------------------------- stepping
    def change_state(self, state: int) -> None:
        """`changeState:` (0x10002cb9c)."""
        self.state = int(state)
        if self.state == STATE_STILL:
            self.walk_bpm = 0.0
            self.walk_times.clear()
        self.bus.post('PGE_MESSAGE_PlayerStateDidChange', self.get_state_dictionary())

    def reset_bpm(self) -> None:
        self.walk_times.clear()

    def set_trip_bpm(self, value: float) -> None:
        """`setTripBPM:` (0x10002bfb0): only when different and unconstrained."""
        if _F32(self.trip_bpm) == _F32(value):
            return
        if self.bpm_constraint != 0:
            return
        self.trip_bpm = float(value)
        self.reset_bpm()

    def update_bpm_counter(self, now: float) -> None:
        """`updateBPMCounter` (0x10002bd04), including its divide-by-count."""
        self.walk_times.append(float(now))
        while len(self.walk_times) >= 6:
            self.walk_times.pop(0)
        n = min(len(self.walk_times) - 1, 5)
        total = _F32(0.0)
        for i in range(max(n, 0)):
            total = _F32(float(total) + (self.walk_times[i + 1] - self.walk_times[i]))
        avg = _F32(total / _F32(len(self.walk_times)))
        self.walk_bpm = float(_F32(60.0) / avg) if avg != 0 else math.inf
        threshold = _F32(SPEED_THRESHOLD_BPM - self.bpm_constraint)
        if len(self.walk_times) < 3:
            # REQUESTED (the tester, 2026-09-26): the first step after a stop
            # measures no interval (infinite tempo) and the second divides one
            # interval by two, so the next two steps always sounded like
            # running.  Walking until three steps are known, as checkStepBPM
            # already has it; the tempo itself, and so tripping, is untouched.
            self.speed = 'footwalk'
            return
        self.speed = 'footwalk' if _F32(self.walk_bpm) < threshold else 'footrun'

    def check_step_bpm(self) -> bool:
        """`checkStepBPM` (0x10002b980) - always YES."""
        if self.trip_bpm == 0 or self.run_bpm == 0:
            return True
        if len(self.walk_times) < 3:
            self.change_state(STATE_WALKING)
            self.walk_bpm = EARLY_WALK_BPM
            return True
        if _F32(self.walk_bpm) >= _F32(self.trip_bpm):
            if self.state != STATE_TRIPPED:
                self.trip()
        elif _F32(self.walk_bpm) > _F32(self.run_bpm):
            if self.state != STATE_RUNNING:
                self.bus.post('PGE_MESSAGE_PlayerStartsToRun', {})
                self.change_state(STATE_RUNNING)
        elif self.state != STATE_WALKING:
            self.change_state(STATE_WALKING)
        return True

    def move_forward_one_step(self, foot: str) -> None:
        """`moveForwardOneStep:` (0x10002b160)."""
        if self.state == 4:
            return                                    # nothing sets 4 in PS2
        if self.proximity_radius != 0:
            self.bus.post('PGE_MESSAGE_AlertAllEnemies',
                          {'to': 'position', 'radius': '%f' % self.proximity_radius})
        self.bus.cancel((id(self), 'changeState', 0))
        self.check_step_bpm()
        px, py = self.position
        ox, oy = self.orientation_vector
        step = float(_F32(self.pixels_per_step))
        nx, ny = px + ox * step, py + oy * step
        self.last_foot = foot
        if self.level is not None and not self.level.can_player_move_to_position(nx, ny):
            self.player_did_collide_a_wall(None)
            return
        self.next_step_position = (nx, ny)
        self.next_step_orientation = self.orientation_vector
        self.just_stepped = True
        if self.speed == '':
            self.speed = 'footwalk'
        surface = self.level.surface_for_position(nx, ny) if self.level is not None else None
        if surface is not None and surface.footsteps_prefix is not None:
            self.footsteps_prefix = surface.footsteps_prefix
        p = self.footsteps_prefix if self.footsteps_prefix else None
        ptxt = p if p is not None else '(null)'
        sound = None
        if self.bank is not None:
            sound = self.bank.any_sound_with_prefix('%s_%s' % (self.speed, ptxt))
            if sound is None:
                sound = self.bank.any_sound_with_prefix('footwalk_%s' % ptxt)
        if sound is not None:
            self.setup_reverb_parameters(sound)
            gain = surface.footsteps_gain if surface is not None else 0.0
            sound.gain = gain if gain > 0 else self.footsteps_gain
            play(sound)
        self.update_bpm_counter(self.bus.now)

    def _one_step(self, _n, params: Params) -> None:
        self.move_forward_one_step(str(params.get('lastFoot', '')))

    def update(self, dt: float) -> None:
        """`-[PGEPlayer update:]` (0x10003024c), dt 0.1."""
        self.reload_timer = float(_F32(self.reload_timer) + _F32(dt))
        if self.has_path:
            # every other update, twice the step: pathSpeed px/s in 0.2 s moves
            self.rail_update += 1
            if self.rail_update == 2:
                self.rail_update = 0
                px, py = self.position
                ddx, ddy = self.next_path_direction
                sp = float(_F32(self.path_speed))
                dx = ddx * sp
                self.position = (px + dt * (dx + dx), py + dt * ((ddy + ddy) * sp))
                wx, wy = self.wanted_patrol_point
                px, py = self.position
                sq = _F32((wx - px) * (wx - px) + (wy - py) * (wy - py))
                if sq == 0 or sq > _F32(self.squared_distance_from_next_patrol_point):
                    self.squared_distance_from_next_patrol_point = math.inf
                    self.find_next_patrol_point()
                else:
                    self.squared_distance_from_next_patrol_point = float(sq)
                self.send_did_move_message()
        elif self.constant_speed != 0:
            px, py = self.position
            ox, oy = self.orientation_vector
            self.position = (px + ox * self.constant_speed * dt,
                             py + oy * self.constant_speed * dt)
            self.send_did_move_message()
        else:
            nx, ny = self.next_step_position
            if nx != 0 and ny != 0:
                px, py = self.position
                if (nx - px) ** 2 + (ny - py) ** 2 > 1.0:
                    ox, oy = self.next_step_orientation
                    sp = float(_F32(self.step_speed))
                    self.position = (px + ox * sp * dt, py + oy * sp * dt)
                    self.send_did_move_message()
        self.update_delays(dt)                  # super update: last

    def send_did_move_message(self) -> None:
        """`sendDidMoveMessage` (0x10002c1d8)."""
        self.bus.post('PGE_MESSAGE_PlayerMovedToPosition', self.get_state_dictionary())

    def move_player_to_position(self, x: float, y: float) -> None:
        self.position = (float(x), float(y))
        self.send_did_move_message()

    def _move_to(self, _n, params: Params) -> None:
        pos = params.get('position')
        if isinstance(pos, (tuple, list)) and len(pos) >= 2:
            self.move_player_to_position(pos[0], pos[1])

    def _walked_on_surface(self, _n, params: Params) -> None:
        self.current_surface_id = ns_int(params.get('id', 0))

    def _bpm_constraint(self, _n, params: Params) -> None:
        """`applyBPMConstraint:` - setTripBPM: first, then the constraint."""
        v = ns_float(params.get('value', 0))
        self.set_trip_bpm(v)
        self.bpm_constraint = v

    def _proximity(self, _n, params: Params) -> None:
        self.proximity_radius = ns_float(params.get('value', 0))

    # ------------------------------------------------------------ tripping
    def trip(self) -> None:
        """`trip:` (0x10002ccc4)."""
        self.reset_bpm()
        self.change_state(STATE_TRIPPED)
        self.bus.post('PGE_MESSAGE_PlayerDidTrip', {})
        token = (id(self), 'changeState', 0)
        self.bus.cancel(token)
        self.bus.call_after(TRIP_RECOVERY, lambda: self.change_state(STATE_STILL), token)
        prefix = self.footsteps_prefix if self.footsteps_prefix is not None else '(null)'
        # REQUESTED (decision 19): two floors whose trip sounds the game has
        # under another name, so the original's lookup finds nothing
        name = 'trip_%s' % TRIP_ALIASES.get(prefix, prefix)
        sound = self.bank.any_sound_containing(name) if self.bank is not None else None
        if sound is not None:
            sound.gain = self.footsteps_gain
            sound.spatialized = False
            play(sound)
        self.trigger('OnTrip')
        if self.level is not None:
            s = self.level.surface_for_position(*self.position)
            if s is not None:
                s.trigger_on_trip()
        old = self.progress.trip_times if self.progress is not None else 0
        if self.progress is not None:
            self.progress.trip_times = old + 1
        if PER_LEVEL_WARNINGS:
            old = self.level_trip_times
            self.level_trip_times += 1
        if (old <= WARNING_TIMES and self._warns_here()
                and self._highest_priority() <= 0):
            if self.voice_over_sound is not None and self.voice_over_sound.playing:
                self.voice_over_sound.stop()
            self.voice_over_priority = 1
            self.voice_over_sound = self.bank.any_sound_containing('global_warning_trip') \
                if self.bank is not None else None
            if self.voice_over_sound is not None:
                self.voice_over_sound.spatialized = False
                play(self.voice_over_sound)
                self.voice_over_sound.wet_gain = 0.0
        self.bus.call_after(TRIP_ALERT_DELAY,
                            lambda: self.bus.post('PGE_MESSAGE_AlertAllEnemies', {'to': 'position'}))

    def _trip_action(self, _n, _p) -> None:
        self.trip()

    # --------------------------------------------------------------- walls
    def player_did_collide_a_wall(self, point) -> None:
        """`playerDidCollideAWall:` (0x10002ab8c); point None is CGPointZero."""
        sound = None
        if self.bank is not None:
            hw = getattr(self.level, 'hit_wall_sound', None)
            if hw:
                sound = self.bank.sound(hw)
            if sound is None:
                sound = self.bank.any_sound_with_prefix('hitwall')
        if sound is not None:
            sound.send_to_reverb = True
            sound.wet_gain = 0.5
            if point is None or tuple(point) == (0.0, 0.0):
                sound.spatialized = False
            else:
                sound.spatialized = True
                sound.planar = (float(point[0]), float(point[1]))
            play(sound)
        self.trigger('OnHitWall')
        old = self.progress.wall_times if self.progress is not None else 0
        if self.progress is not None:
            self.progress.wall_times = old + 1
        if PER_LEVEL_WARNINGS:
            old = self.level_wall_times
            self.level_wall_times += 1
        if (old <= WARNING_TIMES and self._warns_here()
                and self._highest_priority() <= 0):
            vo = self.voice_over_sound
            if vo is not None and vo.playing:
                if 'global_warning_hitwall' not in (vo.name or ''):
                    return                        # 0x10002af2c: no vibration either
                vo.stop()
            self.voice_over_sound = self.bank.any_sound_containing('global_warning_hitwall') \
                if self.bank is not None else None
            if self.voice_over_sound is not None:
                self.voice_over_sound.spatialized = False
                self.voice_over_priority = 1
                play(self.voice_over_sound)
                self.voice_over_sound.wet_gain = 0.0
        self.vibrate()

    def _warns_here(self) -> bool:
        """Whether this level speaks the wall and trip lines: the original's
        levels up to 9, or with PER_LEVEL_WARNINGS the WARNING_LEVELS."""
        name = self._level_name()
        if PER_LEVEL_WARNINGS:
            return name in WARNING_LEVELS
        return level_number(name) <= WARNING_MAX_LEVEL

    def vibrate(self) -> None:
        """AudioServicesPlaySystemSound(0xfff): rumble on a pad (decision 6)."""
        if self.vibrate_fn is not None:
            self.vibrate_fn()

    def _vibrate_msg(self, _n, _p) -> None:
        self.vibrate()

    # --------------------------------------------------------------- hands
    def _change_hands_action(self, _n, params: Params) -> None:
        if params.get('leftHand') is not None:
            self.left_hand_action = str(params['leftHand'])
        if params.get('rightHand') is not None:
            self.right_hand_action = str(params['rightHand'])

    def _in_collide_range(self, _n, params: Params) -> None:
        """`inCollideRangeValueChanged:` - who is within reach."""
        who = params.get('senderName')
        if ns_bool(params.get('value', False)):
            self.objects_in_range.add(who)
        else:
            self.objects_in_range.discard(who)

    def _hands_action(self, _n, params: Params) -> None:
        """`handsActionMessageReceived:` (0x10002df34)."""
        if _F32(self.reload_timer) <= _F32(self.reload_time):
            return
        self.bus.dispatch_async(lambda: setattr(self, 'reload_timer', 0.0))
        hand = params.get('Hand')
        action = ''
        if hand == 'L':
            action = self.left_hand_action
            self.trigger('OnLeftHand')
        elif hand == 'R':
            action = self.right_hand_action
            self.trigger('OnRightHand')
        if action == 'shoot':
            self.shoot()
            return
        if action == 'throw':
            self.throw_something()
            return
        if action in ('stab', 'beat'):
            self.beat()
            return
        if not self._hand_reaches_something():
            self._waved('hands', hand)
        if self.objects_in_range:
            return
        sound_name = self.empty_left_hand_sound if hand == 'L' else \
            self.empty_right_hand_sound if hand == 'R' else None
        self.trigger('OnEmptyHand')
        if sound_name and self.bank is not None:
            s = self.bank.any_sound_with_prefix(sound_name)
            if s is not None:
                s.spatialized = False
                self.setup_reverb_parameters(s)
                play(s)

    # ---------------------------------------------------------------- paths
    def _follow_path_with_name(self, _n, params: Params) -> None:
        """`followPathWithName:` (0x100030908): only when the player sent it."""
        if params.get('senderName') == self.name:
            self.follow_path(params.get('name'))

    def _make_player_follow_path_with_name(self, _n, params: Params) -> None:
        """`makePlayerFollowPathWithName:` (0x100030b40)."""
        self.follow_path(params.get('name'))

    def follow_path(self, name) -> None:
        """`followPath:` (0x100030a5c).  The point count carries on from where
        an earlier path left it."""
        self.path = None
        if name and self.level is not None:
            self.path = self.level.path_with_name(str(name))
        if self.path is not None:
            self.has_path = True
            self.find_next_patrol_point()

    def find_next_patrol_point(self) -> None:
        """`-[PGEPlayer findNextPatrolPoint]` (0x100030600): the next point
        becomes the target; `OnPathEnd` fires when the last one does."""
        if self.path is None:
            return
        wx, wy = self.path.points[self.path_current_point % len(self.path.points)]
        self.wanted_patrol_point = (wx, wy)
        px, py = self.position
        dx, dy = wx - px, wy - py
        n = float(_F32(math.sqrt(dx * dx + dy * dy)))
        if n > 0:
            dx, dy = dx / n, dy / n
        self.next_path_direction = (dx, dy)
        self.squared_distance_from_next_patrol_point = float(_F32(_F32(n) * _F32(n)))
        self.path_current_point += 1
        if self.path_current_point >= len(self.path.points):
            self.trigger('OnPathEnd')
            self.path_current_point = 0

    def _stop_following_path(self, _n, params: Params) -> None:
        """`stopFollowingPath:` (0x100030760): no sender, or the player's own."""
        sender = params.get('senderName')
        if sender is not None and sender != self.name:
            return
        self.stop_following_path()

    def stop_following_path(self) -> None:
        """The stop itself - also what `shutDownLevel:` (0x10002f334) does.
        The state goes to 0 without a message, the facing is zeroed (so a step
        goes nowhere until the next turn) and the glide stops where it is."""
        self.state = STATE_STILL
        self.path = None
        self.orientation_vector = (0.0, 0.0)
        self.has_path = False
        self.next_step_position = self.position

    # ---------------------------------------------------------------- rifle
    def _agent_entered_or_exited_shoot_range(self, _n, params: Params) -> None:
        """`agentEnteredOrExitedShootRange:` (0x10002eff4)."""
        agent = params.get('agent')
        if agent is None:
            return
        if agent.is_in_shooting_range:
            if agent not in self.agents_in_shooting_range:
                self.agents_in_shooting_range.append(agent)
        elif agent in self.agents_in_shooting_range:
            self.agents_in_shooting_range.remove(agent)

    def nearest_agent_in_shooting_range(self):
        """`nearestAgentInShootingRange` (0x10002ee4c): the smallest squared
        distance, strictly - the first of equals wins."""
        best, best_d = None, _F32(math.inf)
        for a in self.agents_in_shooting_range:
            d = _F32(a.squared_distance_from_player)
            if d < best_d:
                best, best_d = a, d
        return best

    def shoot(self) -> None:
        """`shoot:` (0x10002eb10)."""
        self.shot_touched_a_target = False
        if self.shoot_sound is not None and self.bank is not None:
            s = self.bank.any_sound_containing(self.shoot_sound)
            if s is not None:
                s.spatialized = False
                s.send_to_reverb = True
                s.wet_gain = SHOOT_WET_GAIN
                play(s)
        self.trigger('OnShoot')
        targets = self.shot_targets()
        if targets:
            for a in targets:
                if a is targets[0]:
                    a.was_shot()
                else:
                    a.was_missed()
            if targets[0] in self.agents_in_shooting_range:     # the old list, kept tidy
                self.agents_in_shooting_range.remove(targets[0])
        else:
            self.trigger('OnShootMissed')
        self.bus.post('PGE_MESSAGE_PlayerDidShoot', {})

    def shot_targets(self) -> list:
        """REQUESTED (decision 22, from testers' reports): what the shot can
        hit - active, living monsters and penguins in the rifle's cone *now*
        (within their `shootRange`, cos above their `beatDotProd`), nearest
        first by the real distance.

        The original shoots at a list it keeps from enter / leave messages,
        which goes wrong three ways: an agent that switches off inside the
        cone never leaves it, so a monster reset and brought back behind you
        could take the shot; one that the shot did not kill (moving,
        invincible) is dropped while still in front of you, so no later shot
        reached it; and anything with a size - a memory, a sound, the camera -
        could take the shot meant for the monster behind it.  The penguin,
        which keeps no distance, was always the nearest.
        """
        lv = self.level
        if lv is None:
            return []
        px, py = self.position
        ox, oy = self.orientation_vector
        found = []
        for a in lv.agents:
            if a.kind not in ('enemy', 'follower') or not a.active or a.dead:
                continue
            if a.collide_radius <= 0:
                continue
            ax, ay = a.position
            if math.isnan(ax) or math.isnan(ay):
                continue
            dx = _F32(ax - px)
            dy = _F32(ay - py)
            dist = _F32(math.sqrt(float(_F32(dx * dx + dy * dy))))
            if dist == 0:
                continue
            dot = _F32(ox * float(_F32(dx / dist)) + oy * float(_F32(dy / dist)))
            if dot > _F32(a.beat_dot_prod) and dist < _F32(a.shoot_range):
                found.append((float(dist), a))
        found.sort(key=lambda t: t[0])
        return [a for _, a in found]

    # ------------------------------------------------------------- waving
    def _hand_reaches_something(self) -> bool:
        """Is anything within reach that a hand does something to - a hand
        trigger, a memory to smash?  (ps2_1's hand_detector reaches the whole
        room and, its triggers gone, does nothing.)"""
        lv = self.level
        if lv is None:
            return bool(self.objects_in_range)
        for name in self.objects_in_range:
            a = lv.agent(name)
            if a is None or not a.active:
                continue
            if a.has_trigger('OnLeftHand') or a.has_trigger('OnRightHand'):
                return True
            if getattr(a, 'collect_with_left_hand', False) or getattr(a, 'collect_with_right_hand', False):
                return True
        return False

    def _waved(self, kind: str, hand) -> None:
        """Decision 21: count a hand press or swing that did nothing; enough of
        them, close together (the hands left and right in turn), and the level's
        line for it - a take not the last one, when nothing else is being said."""
        cfg = WAVING.get(self._level_name())
        if cfg is None or cfg[0] != kind:
            return
        _kind, prefix, needed = cfg
        now = self.bus.now
        line = self._wave_line
        if line is not None and line.playing:
            return                                   # not while it is being said
        w = self._wave
        if w and (now - w[-1][0] > WAVE_GAP[kind] or (kind == 'hands' and w[-1][1] == hand)):
            w.clear()
        w.append((now, hand))
        if len(w) < needed:
            return
        w.clear()
        if self.bank is None or self._highest_priority() > 0:
            return
        if self.voice_over_sound is not None and self.voice_over_sound.playing:
            return
        names = sorted(n for n in self.bank.specs if n.startswith(prefix)) \
            if hasattr(self.bank, 'specs') else []
        if len(names) > 1 and self._wave_last in names:
            names.remove(self._wave_last)
        if not names:
            return
        name = names[self.rand() % len(names)]
        s = self.bank.sound(name)
        if s is None:
            return
        s.spatialized = False
        s.wet_gain = 0.0
        s.send_to_reverb = False
        play(s)
        self._wave_line = s
        self._wave_last = name
        hook = getattr(self.level, 'on_line_ended', None) if self.level is not None else None
        if hook is not None and getattr(self.level, 'monitors', None) is not None:
            def monitor(pos, dur, s=s):
                if pos >= dur:
                    hook(s.name)
                    return True
                return False
            self.level.monitors.add(s, monitor, self)

    # ----------------------------------------------------------------- beat
    def beat(self) -> None:
        """`beat:` (0x10002f0d4) - the knife, the extinguisher.

        Every agent hears `PlayerDidBeat` at once, and one in its beating range
        marks the beat as having touched something.  On the next pass of the
        run loop, if nothing was touched and there is a `beatSound`: that sound
        (by its exact name) plays flat, into the reverb at 0.5, and the player
        fires `OnBeatMissed`.  A hit makes no sound here: the agent's beaten
        sound is the hit.
        """
        self.shot_touched_a_target = False
        self.bus.post('PGE_MESSAGE_PlayerDidBeat', {})
        self.bus.dispatch_async(self._after_beat)

    def _after_beat(self) -> None:
        if not self.shot_touched_a_target:
            self._waved('knife', None)
        if self.shot_touched_a_target or not self.beat_sound:
            return
        s = self.bank.sound(self.beat_sound) if self.bank is not None else None
        if s is not None:
            s.spatialized = False
            s.send_to_reverb = True
            s.wet_gain = BEAT_WET_GAIN
            play(s)
        self.trigger('OnBeatMissed')

    # ---------------------------------------------------------------- throw
    def throw_something(self) -> None:
        """`throwSomething` (0x10002e778): a pebble lands one step ahead when
        that floor is lethal (over the edge), else two steps ahead; that floor
        hears `OnPebble` and the landing is its `throw_<footsteps>` sound (the
        wall sound on a floor with no footsteps of its own)."""
        step = float(_F32(self.pixels_per_step))
        px, py = self.position
        ox, oy = self.orientation_vector
        sx, sy = ox * step, oy * step
        lv = self.level
        near = lv.surface_for_position(px + sx, py + sy) if lv is not None else None
        far = lv.surface_for_position(px + (sx + sx), py + (sy + sy)) if lv is not None else None
        target = near if (near is not None and near.is_lethal) else far
        if target is not None:
            target.trigger_on_pebble()
        prefix = target.footsteps_prefix if target is not None else None
        sound = None
        if self.bank is not None:
            if prefix:
                sound = self.bank.any_sound_containing('throw_%s' % prefix)
            else:
                hw = getattr(lv, 'hit_wall_sound', None)
                sound = self.bank.sound(hw) if hw else None
        self.bus.post('PGE_MESSAGE_PlayerDidThrow', {})
        if sound is not None:
            sound.send_to_reverb = True
            play(sound)

    # ------------------------------------------------------------ underwater
    def increase_underwater_duration(self, dt: float) -> None:
        """`increaseUnderwaterDuration:` (0x10002fd38), 0.05 every level tick."""
        if not self.is_underwater:
            return
        dur = _F32(_F32(self.underwater_duration) + _F32(dt))
        self.underwater_duration = float(dur)
        mx = _F32(self.underwater_max_duration)
        if float(dur) > float(mx) * GAGGING_SHARE and dur < mx and not self.gagging:
            self.trigger('OnGagging')
            self.start_gagging()
        if _F32(self.underwater_duration) > mx and not self.drowning:
            self.drown()
            self.drowning = True

    def reset_underwater_duration(self) -> None:
        """`resetUnderwaterDuration:` (0x10002fe5c)."""
        self.underwater_duration = 0.0
        self.stop_gagging()

    def start_gagging(self) -> None:
        """`startGagging` (0x10002fe88): the gagging sound, flat, looping."""
        s = None
        if self.bank is not None and self.gagging_sound:
            s = self.bank.sound(self.gagging_sound)
        self.gagging_s3d = s
        if s is not None:
            s.spatialized = False
            play(s, True)
        self.gagging = True

    def stop_gagging(self) -> None:
        """`stopGagging` (0x10002ff68)."""
        if self.gagging_s3d is not None:
            self.gagging_s3d.stop()
        self.gagging_s3d = None
        self.gagging = False

    def drown(self) -> None:
        """`drown` (0x10002ffb8): the level shuts down, the drowning sound
        plays flat, and at its end the level restarts - cause "drown"."""
        self.stop_gagging()
        self.bus.post('PGE_MESSAGE_DisableWalk', {})
        self.bus.post('PGE_MESSAGE_DisableHands', {})
        self.bus.post('PGE_MESSAGE_ShutDownLevel', {})
        s = None
        if self.bank is not None and self.drowning_sound:
            s = self.bank.any_sound_containing(self.drowning_sound)
        self.gagging_s3d = s
        if s is None:
            return                               # add3DSoundMonitor: to nil - stuck
        s.spatialized = False
        play(s)

        def monitor(pos, dur):
            if pos >= dur:
                self.bus.dispatch_async(lambda: self.restart_level('drown'))
                return True
            return False
        self.level.monitors.add(s, monitor, self)

    def restart_level(self, cause: str) -> None:
        """`restartLevel:` (0x100030c10): this level again, with the cause."""
        self.bus.post('PGE_MESSAGE_LoadLevelWithName',
                      {'name': self._level_name(), 'deathCause': cause})

    # ---------------------------------------------------------------- clap
    def _clap(self, _n, _p) -> None:
        """`clap:` (0x10002db44)."""
        if self.disable_clap:
            return
        if self.clap_sound and self.bank is not None:
            s = self.bank.any_sound_with_prefix(self.clap_sound)
            if s is not None:
                s.spatialized = False
                self.setup_reverb_parameters(s)
                play(s)
        self.trigger('OnClap')
        self.update_clap_counter()

    def update_clap_counter(self) -> None:
        """`updateClapCounter` (0x10002dca0): 4 kept, >= 3 at < 0.3 s -> OnClapTooMuch."""
        self.clap_times.append(self.bus.now)
        while len(self.clap_times) >= 5:
            self.clap_times.pop(0)
        n = len(self.clap_times) - 1
        total = _F32(0.0)
        for i in range(max(n, 0)):
            total = _F32(float(total) + (self.clap_times[i + 1] - self.clap_times[i]))
        # divided by the count, not the number of gaps - as updateBPMCounter
        if len(self.clap_times) >= 3 and float(total / _F32(len(self.clap_times))) < 0.3:
            self.trigger('OnClapTooMuch')
            self.clap_times.clear()

    def _disable_clap_msg(self, _n, _p) -> None:
        self.disable_clap = True

    def _enable_clap_msg(self, _n, _p) -> None:
        self.disable_clap = False

    def _jump(self, _n, _p) -> None:
        """`jump`: the jump sound only (surfaces do the rest)."""
        if self.jump_sound and self.bank is not None:
            s = self.bank.any_sound_with_prefix(self.jump_sound)
            if s is not None:
                s.spatialized = False
                self.setup_reverb_parameters(s)
                play(s)

    def _shuffle(self, _n, _p) -> None:
        """PGE_ACTION_Shuffle - `shuffle` is empty in PS2 (0x10002c318)."""

    # ----------------------------------------------------------- PlaySound
    def _play_sound_msg(self, _n, params: Params) -> None:
        """`playSound:` (0x10002f4f8), bugs included."""
        name = params.get('soundName')
        if name is None:
            return
        prio = ns_int(params.get('soundPriority', 0))
        if prio > 0:
            if prio <= self._highest_priority():
                return
            self.bus.post('PGE_MESSAGE_StartedSoundWithPriority',
                          {'name': self.name, 'priority': prio})
        if self.voice_over_sound is not None and self.voice_over_sound.playing:
            self.voice_over_sound.stop()
        self.voice_over_priority = ns_int(params['priority']) if 'priority' in params else 1
        sound = self.bank.any_sound_with_prefix(str(name)) if self.bank is not None else None
        self.voice_over_sound = sound
        if sound is None:
            return
        sound.spatialized = False
        where = self._placed_sender(params, str(name))
        if where is not None:
            # REQUESTED (decision 17, 2026-09-25): the original plays every
            # PlaySound flat; a sound effect sent by something with a place in
            # the room - the door you break, the bear you knife - comes from it.
            x, y = where
            sound.spatialized = True
            sound.planar = (float(_F32(x)), float(_F32(y)), 0.0)
        if 'gain' in params:
            sound.gain = ns_float(params['gain'])
        loop = ns_bool(name) if 'loop' in params else False       # reads soundName
        if 'dryGain' in params:
            sound.wet_gain = ns_float(params['dryGain'])            # setWetGain: - the bug
        else:
            sound.dry_gain = self.dry_gain
        sound.wet_gain = ns_float(params['wetGain']) if 'wetGain' in params else self.wet_gain
        sound.send_to_reverb = sound.wet_gain > 0
        sound.reverb_mix = dict(REVERB)
        play(sound, loop)
        # PORT-SIDE: the PC version of a tutorial line after it (decision 8);
        # the original's PlaySound keeps no monitor.
        hook = getattr(self.level, 'on_line_ended', None) if self.level is not None else None
        if hook is not None and not loop and getattr(self.level, 'monitors', None) is not None:
            def monitor(pos, dur, s=sound):
                if pos >= dur:
                    hook(s.name)
                    return True
                return False
            self.level.monitors.add(sound, monitor, self)

    def _placed_sender(self, params: Params, name: str):
        """Decision 17: where a PlaySound sound effect comes from, if its sender
        has a place - an enemy, a penguin, a collectible you can hear, a
        spatialised sound.  Speech, and anything a floor, the room, the player
        or a silent detector sends, stays flat.

        The place is the one the trigger carries, where the sender stood when
        it fired: ps2_15's penguins are sent home (`ResetAgentWithName`) just
        before their knife sound is sent."""
        sender = params.get('senderName')
        if not sender or 'SPEECH' in name.upper() or self.level is None:
            return None
        if any(name.startswith(n) for n in IN_YOUR_HANDS):
            return None
        a = self.level.agent(str(sender))
        if a is None or (a.kind == 'sound' and not a.spatialized):
            return None
        if a.kind == 'collectible' and not (a.loop_sound or a.intro_sound):
            # a silent detector (ps2_7's hand_release, reach 1000, parked
            # far off): nothing to hear it from - its scrape stays with you
            return None
        from .enemy import cg_point_from_string    # noqa: PLC0415 (enemy imports player)
        x, y = cg_point_from_string(params['position']) if 'position' in params else a.position
        if math.isnan(x) or math.isnan(y):
            return None
        return (x, y)

    def _started_sound_with_priority(self, _n, params: Params) -> None:
        """`startedSoundWithPriority:` - a louder line silences the warnings."""
        if ns_int(params.get('priority', 0)) >= self.voice_over_priority:
            if self.voice_over_sound is not None and self.voice_over_sound.playing:
                self.voice_over_sound.stop()

    # --------------------------------------------------------------- load
    def _level_inited(self, _n, params: Params) -> None:
        """`levelInitedMessageReceived:` - OnLoad."""
        self.trigger('OnLoad')

    def pause(self) -> None:
        """`pause` (0x10002fc04)."""
        self.paused = True
        if self.gagging_s3d is not None and self.gagging_s3d.playing:
            self.gagging_s3d.pause()

    def resume(self) -> None:
        """`resume` (0x10002fc6c): the gagging goes on only while it should."""
        self.paused = False
        if not self.is_underwater:
            return
        dur = _F32(self.underwater_duration)
        mx = _F32(self.underwater_max_duration)
        if float(dur) > float(mx) * GAGGING_SHARE and dur < mx and self.gagging_s3d is not None:
            self.gagging_s3d.resume()
