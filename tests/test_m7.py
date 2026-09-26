"""M7 (ps2_14, 15, 16, 17): the beat (knife, extinguisher), being beaten,
penguins shot and beaten, shaking agents, jumping, Papa's pictures, the level
14-17 achievements - each against what the binary does
(docs/notes/M7_NOTES.md)."""

import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from papasangre2.core.messages import MessageBus                 # noqa: E402
from papasangre2.save.achievements import check_achievements_for_level  # noqa: E402
from papasangre2.save.progress import InMemoryProgress           # noqa: E402
from papasangre2.save.tracker import GameTracker                 # noqa: E402
from papasangre2.sim import Sim                                   # noqa: E402


def _spy(host):
    fired = []
    host.trigger = lambda t, _o=host.trigger: (fired.append(t), _o(t))[1]
    return fired


def _move_to(sim, x, y):
    sim.bus.post('PGE_MESSAGE_MovePlayerToPosition', {'position': (x, y)})
    sim.step(0.1)


def _face(sim, x, y):
    from papasangre2.autopilot import Autopilot
    Autopilot(sim).face(x, y, rate=math.radians(720))


def _hands_on(sim):
    sim.run_until(lambda: sim.interpreter.player_can_use_hands, limit=120)
    sim.step(1.0)                                   # the reload time


# ------------------------------------------------------------------ beat
def test_a_missed_beat_plays_the_beat_sound_flat_and_fires_OnBeatMissed():
    sim = Sim('ps2_14')
    _hands_on(sim)
    p = sim.player
    fired = _spy(p)
    door = sim.level.agent('door_1_put_out_1')
    door_fired = _spy(door)
    assert p.left_hand_action == 'beat'
    sim.hand('L')
    sim.step(0.1)
    s = sim.bank.sound('14_extinguisher_short')
    assert '14_extinguisher_short' in sim.played()
    assert not s.spatialized and s.send_to_reverb and s.wet_gain == 0.5
    assert 'OnBeatMissed' in fired
    assert sim.sent('PGE_MESSAGE_PlayerDidBeat') and sim.tracker.nb_beats == 1
    # every active agent out of reach misses too
    assert 'OnBeatMissed' in door_fired and 'OnShootMissed' in door_fired


def test_a_beat_in_reach_puts_the_fire_out_and_makes_no_miss():
    sim = Sim('ps2_14')
    _hands_on(sim)
    door = sim.level.agent('door_1_put_out_1')
    _move_to(sim, door.position[0] - 20, door.position[1])
    _face(sim, *door.position)
    sim.step(0.1)
    assert door.is_in_beating_range
    fired = _spy(door)
    player_fired = _spy(sim.player)
    kills = sim.progress.total_kills
    n = len(sim.played())
    sim.hand('L')
    sim.step(0.1)
    assert 'OnStab' in fired and door.dead
    assert sim.progress.total_kills == kills + 1
    assert any(x.startswith('7_steam_put_out_fire') for x in sim.played()[n:])
    # a hit is not a miss (the extinguisher heard now is the data's extinguisher_loop)
    assert 'OnBeatMissed' not in player_fired and 'OnBeatMissed' not in fired
    assert door.sound.spatialized and door.sound.planar[:2] == door.position
    assert sim.sent('PGE_MESSAGE_AgentDidDie')
    sim.step(door.sound.duration + 0.5)
    assert not door.active and 'OnBeatenSoundEnd' in fired


def test_coming_into_the_beating_range_plays_its_sound_once():
    sim = Sim('ps2_15')
    bear = sim.level.agent('forgetfulman1')
    sim.run_until(lambda: bear.active, limit=60)
    sim.step(3.0)
    # the data's polarbear_proximity_SPA is in no playlist: nothing plays
    assert sim.bank.any_sound_with_prefix(bear.beat_range_sound) is None
    bear.beat_range_sound = 'polarbear_still_SPA'           # a stand-in that exists
    _move_to(sim, bear.position[0] - 40, bear.position[1])
    _face(sim, *bear.position)
    assert not bear.is_in_beating_range
    n = len(sim.played())
    _move_to(sim, bear.position[0] - 25, bear.position[1])
    _face(sim, *bear.position)
    assert bear.is_in_beating_range
    assert sim.played()[n:].count('polarbear_still_SPA') == 1
    assert sim.bank.sound('polarbear_still_SPA').gain == 0.5
    _move_to(sim, bear.position[0] - 24, bear.position[1])
    _face(sim, *bear.position)
    assert sim.played()[n:].count('polarbear_still_SPA') == 1   # still in it: not again


def test_a_moving_bear_cannot_be_knifed_and_a_still_one_can():
    sim = Sim('ps2_15')
    bear = sim.level.agent('forgetfulman1')
    sim.run_until(lambda: bear.active, limit=60)
    bear.state = 3
    bear.was_beaten()
    assert not bear.dead
    bear.state = 0
    fired = _spy(bear)
    bear.was_beaten()
    assert bear.dead and 'OnStab' in fired
    assert 'polarbear_shotsound' in ''.join(sim.played())


def test_papa_beaten_counts_a_picture_and_says_the_line_for_it():
    sim = Sim('ps2_18')
    papa = sim.level.agent('4_papa_1')
    papa.set_active(True)
    sim.step(0.1)
    papa.state = 0
    papa.was_beaten()
    assert sim.level.pictures_taken == 1
    assert papa.sound is not None and papa.sound.name.startswith('18_SPEECH_papa_picture_1')


def test_the_retreat_line_is_the_one_for_the_pictures_taken():
    sim = Sim('ps2_18')
    sim.level.pictures_taken = 2
    sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': '4_papa_2_retreat'})
    sim.step(0.2)
    assert '18_SPEECH_papa_picture_retreat_2_SPA_UOS' in sim.played()


# --------------------------------------------------------------- penguins
def _penguin(sim, name='penguin', times=1):
    for _ in range(times):
        sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': name})
    f = sim.level.agent(name)
    sim.run_until(lambda: f.active and f.sound is not None, limit=20)
    return f


def test_a_beaten_penguin_counts_as_a_penguin_and_twice_as_an_enemy():
    sim = Sim('ps2_15')
    f = _penguin(sim, times=5)                        # activationCounter 5
    fired = _spy(f)
    own = f.sound
    f.was_beaten()
    assert f.dead and 'OnStab' in fired
    assert sim.sent('PGE_MESSAGE_FollowerDidDie')
    assert sim.tracker.nb_penguins_killed == 1
    assert sim.tracker.nb_enemies_killed == 2          # FollowerDidDie + incrementPenguinKills
    # decision 18: Muhammad's penguin death with the stab in it
    s = sim.bank.sound('requested_penguin_death_stab')
    assert s.playing and s.spatialized and s.planar == own.planar
    assert not any(x.startswith('penguin_death') for x in sim.played())
    sim.step(s.duration + 0.5)
    assert not f.active


def test_a_shot_penguin_fires_its_OnShoot():
    sim = Sim('ps2_17')
    f = _penguin(sim)
    fired = _spy(f)
    f.was_shot()
    assert f.dead and 'OnShoot' in fired and 'OnStab' not in fired
    assert 'penguin_death' in ''.join(sim.played())
    assert sim.tracker.nb_penguins_killed == 1


def test_a_reset_penguin_is_alive_again():
    sim = Sim('ps2_17')
    f = _penguin(sim)
    f.was_shot()
    sim.bus.post('PGE_MESSAGE_ResetAgentWithName', {'name': 'penguin'})
    assert not f.dead and not f.active


# ------------------------------------------------------------------ shake
def test_a_shake_near_an_agent_fires_its_OnShake_and_the_firework_needs_five():
    sim = Sim('ps2_14')
    sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': 'firework_1'})
    fw = sim.level.agent('firework_1')
    sim.run_until(lambda: fw.active, limit=5)
    _move_to(sim, fw.position[0] + 150, fw.position[1])
    fired = _spy(fw)
    sim.shake()
    sim.step(0.1)
    assert 'OnShake' not in fired                      # out of its 100 px
    _move_to(sim, fw.position[0] + 50, fw.position[1])
    target = sim.level.agent('firework_target')
    for i in range(5):
        assert not target.active
        sim.shake()
        sim.step(0.3)
    assert fired.count('OnShake') == 5
    sim.step(0.2)
    assert target.active
    # extinguisher_shake is an agent: while its sound plays it is active, and
    # activating it again does nothing - quick shakes make one shake sound
    assert sum(1 for x in sim.played() if x.startswith('14_extinguisher_shake')) == 1


def test_no_shake_while_the_level_is_paused():
    sim = Sim('ps2_14')
    sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': 'firework_1'})
    fw = sim.level.agent('firework_1')
    sim.run_until(lambda: fw.active, limit=5)
    _move_to(sim, fw.position[0] + 50, fw.position[1])
    fired = _spy(fw)
    sim.level.paused_game = True
    sim.shake()
    assert 'OnShake' not in fired


# ------------------------------------------------------------------- jump
def _on_the_jump_floor(sim):
    sim.bus.post('PGE_MESSAGE_EnableJump', {})
    sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': 'surface_jump'})
    sim.step(0.2)
    floor = next(f for f in sim.level.floors if f.name == 'surface_jump')
    assert floor.player_is_on_surface
    return floor


def _jump(sim):
    ok = sim.interpreter.jump()
    sim.bus.update(sim.now)
    return ok


def test_three_quick_jumps_break_the_ice():
    sim = Sim('ps2_15')
    floor = _on_the_jump_floor(sim)
    fired = _spy(floor)
    for _ in range(3):
        assert _jump(sim)
        sim.step(0.3)
    assert fired.count('OnJump') == 3 and 'OnJumpTooMuch' in fired
    assert floor.jumps_time == []
    sim.step(0.2)
    assert sim.level.agent('white_room').active
    assert 'footwalk_ice_a' in ''.join(sim.played())    # the player's jumpSound


def test_slow_jumps_do_not():
    sim = Sim('ps2_15')
    floor = _on_the_jump_floor(sim)
    fired = _spy(floor)
    for _ in range(4):
        _jump(sim)
        sim.step(1.0)
    assert fired.count('OnJump') == 4 and 'OnJumpTooMuch' not in fired
    assert len(floor.jumps_time) == 4                   # four kept


def test_no_jump_until_it_is_enabled():
    sim = Sim('ps2_15')
    assert not _jump(sim)
    assert not sim.sent('PGE_ACTION_Jump')


# ----------------------------------------------------------- achievements
def _tracker(**kw):
    t = GameTracker(MessageBus())
    for k, v in kw.items():
        setattr(t, k, v)
    return t


def test_level_14_is_all_seven_collectibles_and_act3_either_way():
    p = InMemoryProgress()
    assert check_achievements_for_level(p, _tracker(collectibles_collected=7), 'ps2_14') == 'level_14'
    assert p.game_center_percent('act3') == 45.0
    q = InMemoryProgress()
    assert check_achievements_for_level(q, _tracker(collectibles_collected=6), 'ps2_14') is None
    assert q.game_center_percent('act3') == 45.0


def test_level_15_is_ten_penguins():
    assert check_achievements_for_level(InMemoryProgress(), _tracker(nb_penguins_killed=10),
                                        'ps2_15') == 'level_15'
    assert check_achievements_for_level(InMemoryProgress(), _tracker(nb_penguins_killed=9),
                                        'ps2_15') is None


def test_level_16_is_fewer_than_five_alerts():
    assert check_achievements_for_level(InMemoryProgress(), _tracker(enemies_alerted=4),
                                        'ps2_16') == 'level_16'
    assert check_achievements_for_level(InMemoryProgress(), _tracker(enemies_alerted=5),
                                        'ps2_16') is None


def test_level_17_is_four_minutes():
    p = InMemoryProgress()
    assert check_achievements_for_level(p, _tracker(time_elapsed=240.0), 'ps2_17') == 'level_17'
    assert p.game_center_percent('act3') == 90.0
    assert check_achievements_for_level(InMemoryProgress(), _tracker(time_elapsed=240.1),
                                        'ps2_17') is None


# ------------------------------------------------------ whole levels, played
def test_level_14_can_be_finished_with_the_extinguisher():
    from papasangre2.autopilot import play_level_14
    sim = Sim('ps2_14', seed=1)
    assert play_level_14(sim) == 'won'
    assert sim.sent('PGE_MESSAGE_PlayerDidBeat')


def test_a_bear_sent_home_from_home_stays_to_be_knifed():
    """Decision 16: in the original it would be lost at NaN and ps2_15 could
    not be finished."""
    sim = Sim('ps2_15')
    bear = sim.level.agent('forgetfulman7')
    sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': 'forgetfulman7'})
    sim.run_until(lambda: bear.active, limit=20)
    sim.step(6.0)                                     # its appearing sound
    assert bear.state == 0 and bear.position == bear.initial_position
    sim.bus.post('PGE_MESSAGE_SendAgentToInitialPosition', {'senderName': 'forgetfulman5'})
    sim.step(1.0)
    assert bear.position == bear.initial_position and bear.state == 0


def test_level_15_can_be_finished_by_jumping_through_the_ice():
    from papasangre2.autopilot import play_level_15
    sim = Sim('ps2_15', seed=1)
    assert play_level_15(sim) == 'won'
    assert sim.tracker.nb_enemies_killed >= 8
    assert any(n == 'PGE_ACTION_Jump' for _, n, _p in sim.messages)


def test_level_16_can_be_finished_in_the_thunder():
    from papasangre2.autopilot import play_level_16
    assert play_level_16(Sim('ps2_16', seed=1)) == 'won'


def test_level_17_can_be_finished():
    from papasangre2.autopilot import play_level_17
    sim = Sim('ps2_17', seed=1)
    assert play_level_17(sim) == 'won'
    assert sim.tracker.time_elapsed <= 240.0


# ------------------------------------------ decision 17: hits where they land
def test_hitting_the_banging_door_is_heard_at_the_door():
    """ps2_14: the extinguisher on Mr. Fletcher's door (the original: flat)."""
    sim = Sim('ps2_14')
    _hands_on(sim)
    sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': 'banging'})
    door = sim.level.agent('banging')
    sim.run_until(lambda: door.active, limit=5)
    sim.bus.post('PGE_MESSAGE_ChangeHandAction', {'leftHand': ''})
    _move_to(sim, door.position[0] - 20, door.position[1])
    assert door.in_collide_range
    sim.step(1.0)
    sim.hand('L')
    sim.step(0.1)
    hit = [x for x in sim.played() if x.startswith('14_break_door_with_extinguisher')]
    assert hit                                         # one of its five takes
    s = sim.bank.sound(hit[-1])
    assert s.spatialized and s.planar[:2] == door.position
    assert abs(s.gain - 0.65) < 1e-6


def test_the_knife_swing_is_heard_on_your_side():
    """Decision 21 (a tester's report): the swing is in your hand - flat -
    while the bear's death comes from the bear."""
    sim = Sim('ps2_15')
    bear = sim.level.agent('forgetfulman1')
    sim.run_until(lambda: bear.active, limit=60)
    bear.state = 0
    bear.was_beaten()
    sim.step(0.1)
    s = sim.bank.any_sound_with_prefix('beatsound')
    assert s is not None and not s.spatialized
    assert bear.sound is not None and bear.sound.spatialized


def test_speech_and_floor_sounds_stay_flat():
    sim = Sim('ps2_14')
    sim.bus.post('PGE_MESSAGE_PlaySound', {'soundName': '14_SPEECH_final_smash_it_UOS',
                                           'senderName': 'memory5'})
    assert not sim.bank.any_sound_with_prefix('14_SPEECH_final_smash_it_UOS').spatialized
    sim = Sim('ps2_17')
    sim.bus.post('PGE_MESSAGE_PlaySound', {'soundName': '10_pebble_fall',
                                           'senderName': 'close_zone_1'})
    assert not sim.bank.any_sound_with_prefix('10_pebble_fall').spatialized



# ------------------------------------------------ decisions 17 and 18, again
def test_a_sound_a_reset_agent_sends_is_placed_where_it_fired():
    """ps2_15 sends a stabbed penguin home before its OnShoot's PlaySound: a
    placed sound goes where the trigger fired (the camera and the knife are
    yours and stay flat; this checks the rule with a sound that is placed)."""
    sim = Sim('ps2_15')
    f = _penguin(sim, times=5)
    sim.step(8.0)
    where = f.position
    assert where != f.initial_position
    sim.bus.post('PGE_MESSAGE_PlaySound', {'soundName': 'penguin_squawk_SPA', 'senderName': 'penguin',
                                           'position': '{%r, %r}' % where})
    sim.bus.post('PGE_MESSAGE_ResetAgentWithName', {'name': 'penguin'})
    s = sim.bank.sound('penguin_squawk_SPA')
    assert s.spatialized
    assert abs(s.planar[0] - where[0]) < 0.01 and abs(s.planar[1] - where[1]) < 0.01


def test_a_shot_penguin_keeps_the_original_death():
    sim = Sim('ps2_17')
    f = _penguin(sim)
    f.was_shot()
    assert 'penguin_death_SPA' in sim.played()
    assert 'requested_penguin_death_stab' not in sim.played()


def test_the_camera_click_is_on_your_side_and_the_hit_on_papas():
    sim = Sim('ps2_18')
    sim.bus.post('PGE_MESSAGE_PlaySound', {'soundName': '18_camera_photo_taken',
                                           'senderName': '4_papa_1', 'position': '{132, -179}'})
    click = [x for x in sim.played() if x.startswith('18_camera_photo_taken')]
    assert click and not sim.bank.sound(click[-1]).spatialized
    papa = sim.level.agent('4_papa_1')
    papa.set_active(True)
    sim.step(0.1)
    papa.state = 0
    papa.was_beaten()
    assert papa.sound.spatialized and papa.sound.planar[:2] == papa.position


# ---------------------------------------------------- decision 19: trips
def _trip_sound(level, prefix):
    sim = Sim(level)
    sim.player.footsteps_prefix = prefix
    n = len(sim.played())
    sim.player.trip()
    return sim, [x for x in sim.played()[n:] if 'trip' in x and 'warning' not in x]


def test_a_trip_on_glass_is_heard():
    """The original has no glass trip; decision 19 built one from its steps."""
    sim, got = _trip_sound('ps2_16', 'glass')
    assert got == ['requested_trip_glass']
    s = sim.bank.sound(got[0])
    assert not s.spatialized and s.gain == sim.player.footsteps_gain


def test_the_two_misnamed_trips_are_hooked_up():
    _, got = _trip_sound('ps2_Intro', 'squelch_gravel')
    assert got and got[0].startswith('trip_gravel_squelch_')
    _, got = _trip_sound('ps2_3', 'cracker')
    assert got and got[0].startswith('trip_stone_')


def test_other_trips_are_the_originals():
    _, got = _trip_sound('ps2_8', 'ice')
    assert got and got[0].startswith('trip_ice_')
