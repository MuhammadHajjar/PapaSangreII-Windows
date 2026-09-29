"""The first private beta's reports (2026-09-26), each as its fix behaves."""

import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from papasangre2.sim import Sim                                   # noqa: E402


def _face(sim, x, y):
    from papasangre2.autopilot import Autopilot
    Autopilot(sim).face(x, y, rate=math.radians(720))


def _move_to(sim, x, y):
    sim.bus.post('PGE_MESSAGE_MovePlayerToPosition', {'position': (x, y)})
    sim.step(0.1)


def _plays(sim, needle):
    return [t for t, what, n in sim.log if what == 'play' and needle in n]


def _floor(sim, name):
    return next(f for f in sim.level.floors if f.name == name)


def _on(sim, name):
    sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': name})


# ------------------------------------------------------------------ Intro
def test_the_record_scratch_comes_after_let_me_just():
    # the original's 36 s: "let me just..." ends 35.56 s, "Hmm, that's better"
    # starts 36.76 s (the original, recorded: the scratch 0.57 s after "just")
    sim = Sim('ps2_Intro')
    _on(sim, 'gramophone_loop')
    sim.step(0.5)
    _on(sim, 'intro1')
    sim.step(40)
    start = _plays(sim, 'INTRO_SPEECH_training_1_SPA')[0]
    scratch = _plays(sim, 'needle_jerk')[0]
    assert 35.9 <= scratch - start <= 36.2


def test_game_time_keeps_pace_with_the_wall_clock(tmp_path):
    """Frames that are not whole 10 ms steps must not lose time: rounding
    each one made game time run 6 % slow, and every delay came late."""
    from test_game import make_game
    g = make_game(tmp_path)
    t0 = g.now
    for _ in range(1500):                     # 20 s of 13.33 ms frames
        g.update(0.01333)
    assert abs((g.now - t0) - 20.0) < 0.02
    for _ in range(1000):                     # and 10 s of 10.0 ms ones
        g.update(0.01)
    assert abs((g.now - t0) - 30.0) < 0.03


def _turn_lesson(rate_deg, direction):
    sim = Sim('ps2_Intro')
    for n in ('gramophone_loop', 'fountain', 'Intro0a'):
        _on(sim, n)
    a = sim.level.agent('Intro0a')
    sim.run_until(lambda: a.sound is not None and a.sound.plays and not a.sound.playing, limit=60)
    sim.step(1.0)
    t0 = sim.now
    while sim.now - t0 < 30:
        sim.turn(direction * math.radians(rate_deg) * 0.01)
        sim.step(0.01)
    return sim


def test_keep_going_never_talks_over_the_landmarks():
    for rate, way in ((20, 1), (20, -1), (45, 1), (45, -1), (90, 1)):
        sim = _turn_lesson(rate, way)
        spans = {}
        for t, what, n in sim.log:
            for key in ('thats_it', 'see_fountain', 'see_gramophone'):
                if key in n:
                    spans.setdefault(key, []).append((t, what))
        good = spans.get('thats_it', [])
        for key in ('see_fountain', 'see_gramophone'):
            for t, what in spans.get(key, []):
                if what != 'play':
                    continue
                # nothing of "keep going" is still sounding when a landmark starts
                on = [tt for tt, w in good if w == 'play' and tt < t]
                off = [tt for tt, w in good if w == 'stop' and tt <= t]
                if on:
                    s = sim.bank.sound('INTRO_SPEECH_training_thats_it_SPA_UOS')
                    assert len(off) >= len(on) or on[-1] + s.duration <= t, (rate, way, key)


def test_the_second_landmark_is_not_lost_to_keep_going():
    sim = _turn_lesson(45, 1)
    assert _plays(sim, 'see_fountain') and _plays(sim, 'see_gramophone')


# ------------------------------------------------------------------ ps2_1
def test_the_display_case_is_always_explained():
    for seed in range(6):
        sim = Sim('ps2_1', seed=seed)
        assert sim.level.agent('smash_instructions').sounds == ['1_SPEECH_precollect_3_UOS']


def test_smash_the_case_reminder_once_if_you_wait():
    sim = Sim('ps2_1')
    _on(sim, 'smash_instructions')
    sim.run_until(lambda: bool(_plays(sim, 'precollect_3')), limit=5)
    sim.step(12.0 + 7.0)
    assert not _plays(sim, '1_SPEECH_open_case')
    sim.step(2.0)
    assert len(_plays(sim, '1_SPEECH_open_case')) == 1
    sim.step(30.0)
    assert len(_plays(sim, '1_SPEECH_open_case')) == 1


def test_no_reminder_once_the_case_is_smashed():
    sim = Sim('ps2_1')
    sim.bus.post('PGE_MESSAGE_EnableHands', {})
    _on(sim, 'memory3')
    m = sim.level.agent('memory3')
    sim.run_until(lambda: m.active, limit=5)
    _move_to(sim, m.position[0] - 5, m.position[1])
    sim.run_until(lambda: bool(_plays(sim, 'precollect_3')), limit=5)
    sim.step(13.0)
    sim.hand('L')
    sim.step(15.0)
    assert not _plays(sim, '1_SPEECH_open_case')


# ------------------------------------------------------------------ ps2_3
def test_the_sparkler_is_picked_up_on_arrival():
    sim = Sim('ps2_3')
    egg = sim.level.agent('easter_egg')
    _on(sim, 'easter_egg')
    sim.run_until(lambda: egg.active, limit=5)
    sim.step(1.0)
    _move_to(sim, *egg.position)
    sim.step(0.2)
    assert egg.collected


# ------------------------------------------------------------------ ps2_5a
def test_the_gramophone_scene_goes_on_a_second_after_you_reach_it():
    sim = Sim('ps2_5a')
    machine = sim.level.agent('machine')
    _on(sim, 'machine')
    sim.run_until(lambda: machine.active, limit=5)
    sim.step(10.0)
    _move_to(sim, machine.position[0], machine.position[1] - 10)
    t0 = sim.now
    sim.step(2.0)
    hat = _plays(sim, 'put_hat_back_on')
    assert hat and hat[0] - t0 < 1.5
    assert sim.level.agent('button').active
    s = sim.bank.sound('gramophone_crackle_loop_SPA_UOS')
    assert s.playing                            # the button's, not cut by the machine
    sim.step(10.0)
    assert s.playing


# ------------------------------------------------------------------ ps2_7
def test_climbing_out_of_a_hole_scrapes_in_your_ears():
    sim = Sim('ps2_7')
    sim.bus.post('PGE_MESSAGE_EnableHands', {})
    sim.step(0.5)
    _move_to(sim, 50.0, 47.0)
    sim.step(6.0)
    sim.hand('L')
    sim.step(0.2)
    scrape = [n for t, w, n in sim.log if w == 'play' and n.startswith('7_scrape')]
    assert scrape
    assert not sim.bank.sound(scrape[0]).spatialized


# ------------------------------------------------------------------ ps2_9
def test_the_submarine_power_going_is_flat():
    sim = Sim('ps2_9')
    _on(sim, 'explosion_large')
    sim.step(0.2)
    s = sim.level.agent('explosion_large').sound
    assert s is not None and not s.spatialized and abs(s.gain - 0.7) < 1e-6


# ------------------------------------------------------------------ ps2_14
def test_the_second_fire_door_burns_where_it_is():
    sim = Sim('ps2_14')
    _on(sim, 'door_1_fire')
    sim.step(0.2)
    _on(sim, 'door_1_fire')
    sim.bus.post('PGE_MESSAGE_DeactivateAgentWithName', {'name': 'door_1_fire'})
    sim.step(0.1)
    _on(sim, 'door_2_fire')
    sim.step(0.2)
    d2 = _floor(sim, 'door_2_fire')
    for y in (-40, -20, 0, 20, 35):
        _move_to(sim, -50.0, float(y))
        sx, sy, _ = d2.spatial_sound.planar
        assert -70 <= sx <= -28 and 40 <= sy <= 60, (y, sx, sy)
    assert d2.spatial_sound.playing


def test_the_oil_can_can_be_sprayed_from_the_distance_its_data_gives():
    sim = Sim('ps2_14')
    can = sim.level.agent('can')
    _on(sim, 'can')
    sim.run_until(lambda: can.active, limit=5)
    _move_to(sim, can.position[0] - 60, can.position[1])
    _face(sim, can.position[0], can.position[1] + 25)        # 23 degrees off
    sim.step(0.2)
    assert can.is_in_beating_range
    _move_to(sim, can.position[0] - 2, can.position[1])       # on top of it
    _face(sim, can.position[0] - 50, can.position[1])        # facing away
    sim.step(0.2)
    assert can.is_in_beating_range


def _ready_to_walk(sim):
    sim.run_until(lambda: sim.interpreter.player_can_use_hands, limit=120)
    sim.bus.post('PGE_MESSAGE_EnableWalk', {})
    sim.bus.post('PGE_MESSAGE_EnableHands', {})
    sim.step(1.0)


def _died(sim, since):
    return [n for t, what, n in sim.log if t >= since and what == 'play' and 'ondeath' in n]


def test_the_oil_can_stays_out_once_it_is_put_out():
    # the owner's report (2026-09-29): sprayed from its north tripwire, the can
    # came back when he walked on over the tripwires he had not crossed yet -
    # its burst, no warning, then the explosion ran him down
    sim = Sim('ps2_14', seed=1)
    _ready_to_walk(sim)
    can = sim.level.agent('can')
    _move_to(sim, 71.0, 52.0)                                # north tripwire only
    sim.step(9.0)
    _face(sim, *can.position)
    sim.step(0.2)
    assert can.is_in_beating_range
    sim.hand('L')
    stab = sim.now
    sim.step(6.0)
    assert _plays(sim, '7_steam_put_out_firework') and _plays(sim, 'can_extinguished')
    assert not [n for t, w, n in sim.log if w == 'stop' and t < stab + 3.7
                and n.startswith('7_steam_put_out_firework')]   # the steam is heard out
    for x, y in ((70.0, 70.0), (70.0, 90.0), (70.0, 40.0), (70.0, 70.0)):
        _move_to(sim, x, y)                                  # the middle, the south wire...
        sim.step(20.0)
    assert [t for t in _plays(sim, '14_firework_intro') if t > stab] == []
    assert [t for t in _plays(sim, 'can_extinguisher') if t > stab] == []
    assert not _plays(sim, 'vat_of_oil_explosions') and not _died(sim, stab)


def test_the_oil_can_left_burning_still_blows_up():
    sim = Sim('ps2_14', seed=1)
    _ready_to_walk(sim)
    t0 = sim.now
    _move_to(sim, 71.0, 52.0)
    _move_to(sim, 70.0, 70.0)
    sim.step(30.0)
    assert _plays(sim, 'can_extinguisher') and _plays(sim, 'vat_of_oil_explosions')
    assert _died(sim, t0) == ['14_ondeath_explode_UOS']


def test_the_second_oil_fire_stays_out_once_it_is_put_out():
    sim = Sim('ps2_14', seed=1)
    _ready_to_walk(sim)
    _move_to(sim, 148.0, -70.0)                              # its middle tripwire
    sim.step(6.0)
    _face(sim, 127.0, -60.0)
    for _ in range(6):
        sim.shake()
        sim.step(0.4)
    out = sim.now
    sim.step(4.0)
    assert _plays(sim, '7_steam_put_out_firework') and _plays(sim, 'oncollect_go_to_exit')
    for x, y in ((130.0, -62.0), (148.0, -70.0), (164.0, -62.0), (148.0, -70.0)):
        _move_to(sim, x, y)                                  # west wire, east wire...
        sim.step(20.0)
    assert [t for t in _plays(sim, '14_firework') if t > out] == []
    assert [t for t in _plays(sim, 'shake_extinguisher_2') if t > out] == []
    assert not _plays(sim, 'vat_of_oil_explosions') and not _died(sim, out)


def test_the_house_comes_down_after_you_from_the_start():
    sim = Sim('ps2_14')
    sim.bus.post('PGE_MESSAGE_EnableWalk', {})
    _move_to(sim, 148.0, -112.0)
    e = sim.level.agent('explosions')
    home = e.position
    _on(sim, 'explosions')
    sim.step(3.0)
    assert e.state == 10 and e.position[1] < home[1] - 20      # moving in its intro
    sim.step(4.5)
    loop = _plays(sim, '14_collapse_loop')
    intro = _plays(sim, '14_explosion_intro')
    assert loop and loop[0] - intro[0] < 7.2                    # 1.5 s before its end


# ------------------------------------------------------------------ ps2_15
def test_the_jump_prompt_waits_between_repeats():
    sim = Sim('ps2_15')
    _on(sim, 'real_jump_prompt')
    sim.step(60.0)
    times = _plays(sim, '15_SPEECH_prompt_jump')
    assert len(times) == 3 and all(b - a > 20 for a, b in zip(times, times[1:]))


def test_the_jump_prompt_stops_when_it_is_put_away():
    sim = Sim('ps2_15')
    _on(sim, 'real_jump_prompt')
    sim.step(9.0)
    sim.bus.post('PGE_MESSAGE_DeactivateAgentWithName', {'name': 'real_jump_prompt'})
    sim.step(40.0)
    assert len(_plays(sim, '15_SPEECH_prompt_jump')) == 1


# ------------------------------------------------------------------ ps2_18
def test_feet_stay_still_while_the_camera_is_explained():
    sim = Sim('ps2_18')
    sim.bus.post('PGE_MESSAGE_EnableWalk', {})
    sim.step(0.1)
    m = sim.level.agent('memory3')
    _on(sim, 'memory3')
    sim.run_until(lambda: m.active, limit=5)
    m.collect()
    sim.step(0.5)
    assert not sim.interpreter.player_can_walk
    prompt = sim.level.agent('camera_prompt')
    sim.run_until(lambda: prompt.active, limit=10)
    sim.run_until(lambda: not prompt.active, limit=30)
    sim.step(0.2)
    assert sim.interpreter.player_can_walk


# ------------------------------------------------------------------ ps2_18b
def test_the_hold_music_sits_under_the_voice():
    sim = Sim('ps2_18b')
    _on(sim, 'music')
    sim.step(0.2)
    assert abs(sim.level.agent('music').sound.gain - 0.5) < 1e-6


# ------------------------------------------------------------------ misc
def test_an_idle_hint_plays_once():
    sim = Sim('ps2_1')
    assert sim.run_until(lambda: sim.interpreter.player_can_use_hands, limit=120)
    sim.clap()
    assert sim.run_until(lambda: sim.interpreter.player_can_walk, limit=120)
    sim.step(200.0)
    assert len(_plays(sim, '1_SPEECH_hint')) == 1


def test_the_first_steps_after_a_stop_walk():
    sim = Sim('ps2_1')
    sim.bus.post('PGE_MESSAGE_EnableWalk', {})
    sim.step(0.5)
    n0 = len(sim.log)
    for i in range(6):
        sim.foot('LR'[i % 2])
        sim.step(0.5)
    steps = [n for t, w, n in sim.log[n0:] if w == 'play' and n.startswith('foot')]
    assert len(steps) == 6 and all(n.startswith('footwalk') for n in steps)


def test_the_about_screen_reads_a_row_at_a_time():
    from papasangre2.shell import about_menu
    m = about_menu(['Writer\nNeil Bennun\n\nVoice Actors\nA\nB\n\nThanks to you'], 'PC word.')
    labels = [i.label for i in m.items]
    assert labels == ['Writer: Neil Bennun', 'Voice Actors: A, B', 'Thanks to you',
                      'PC word.', 'Main Menu']
    assert m.items[-1].action == 'back'



def test_a_knifed_penguin_in_level_20_keeps_the_swing_with_the_crunch():
    """Muhammad heard both (rendered, 2026-09-26) and kept ps2_17's swing: a
    knifed penguin there plays the stab death and the knife's swing."""
    sim = Sim('ps2_17')
    p = sim.player
    sim.bus.post('PGE_MESSAGE_EnableHands', {})
    sim.bus.post('PGE_MESSAGE_ChangeHandAction', {'rightHand': 'beat'})
    _on(sim, 'penguin')
    sim.step(3.0)
    pen = sim.level.agent('penguin')
    ox, oy = p.orientation_vector
    pen.position = (p.position[0] + 12 * ox, p.position[1] + 12 * oy)
    sim.step(0.3)
    n0 = len(sim.log)
    sim.hand('R')
    sim.step(2.0)
    played = [n for t, w, n in sim.log[n0:] if w == 'play']
    assert 'requested_penguin_death_stab' in played and 'beatsound' in played
    assert not pen.active and sim.level.agent('penguin2').active


# ------------------------------------------------------------ 2026-09-27
def test_the_museum_music_comes_from_the_door_and_carries():
    sim = Sim('ps2_Intro')
    _on(sim, 'door_closed')
    sim.step(2.0)
    door = sim.level.agent('door_closed')
    s = door.sound
    assert s is not None and s.spatialized
    assert tuple(s.planar[:2]) == tuple(door.position)
    assert s.max_gain == 5.0 and abs(s.gain - 36.0) < 0.5      # faded in to its final gain


def test_other_sounds_keep_the_usual_ceiling():
    sim = Sim('ps2_Intro')
    _on(sim, 'gramophone_loop')
    sim.step(0.5)
    assert sim.level.agent('gramophone_loop').sound.max_gain == 1.0


def test_face_the_music_is_said_once_however_long_you_wait():
    sim = Sim('ps2_Intro')
    _on(sim, 'intro1a')
    a = sim.level.agent('intro1a')
    sim.run_until(lambda: a.active and a.sound is not None, limit=5)
    sim.step(a.sound.duration + 90.0)
    assert len(_plays(sim, 'INTRO_SPEECH_training_1a_prompt')) == 1


def test_paparazzi_has_no_idle_hint_from_papas_zoo():
    sim = Sim('ps2_18')
    sim.bus.post('PGE_MESSAGE_EnableWalk', {})
    sim.step(120.0)
    assert not _plays(sim, '11b_SPEECH_hint_shooting')


def test_keep_moving_stops_once_the_last_memory_is_taken():
    sim = Sim('ps2_18')
    sim.bus.post('PGE_MESSAGE_EnableWalk', {})
    m = sim.level.agent('memory3')
    _on(sim, 'memory3')
    sim.run_until(lambda: m.active, limit=5)
    m.collect()
    sim.step(1.0)
    # stand still on a shout floor, where the data would still say it
    sim.bus.post('PGE_MESSAGE_MovePlayerToPosition', {'position': (-120.0, -140.0)})
    sim.step(0.2)
    n = len(_plays(sim, '18_SPEECH_keep_moving')) + len(_plays(sim, '18_SPEECH__keep_moving'))
    sim.step(40.0)
    after = len(_plays(sim, '18_SPEECH_keep_moving')) + len(_plays(sim, '18_SPEECH__keep_moving'))
    assert after == n


def test_keep_moving_still_nags_before_the_last_memory():
    sim = Sim('ps2_18')
    sim.bus.post('PGE_MESSAGE_EnableWalk', {})
    sim.bus.post('PGE_MESSAGE_MovePlayerToPosition', {'position': (-120.0, -140.0)})
    sim.step(0.2)
    sim.foot('L')
    sim.step(20.0)
    assert _plays(sim, '18_SPEECH_keep_moving') or _plays(sim, '18_SPEECH__keep_moving')


def test_a_nearly_earned_achievement_never_says_100_percent():
    from papasangre2.assets.hublist import load_hub_list
    from papasangre2.save.progress import InMemoryProgress
    from papasangre2.shell import achievements_menu
    from papasangre2.util import paths
    p = InMemoryProgress()
    p.total_kills = 498                                   # 99.6 percent of 500
    labels = [i.label for i in achievements_menu(load_hub_list(paths.game_bundle()), p).items]
    assert '500 kills, not achieved, 99 percent' in labels
    p.total_kills = 500
    labels = [i.label for i in achievements_menu(load_hub_list(paths.game_bundle()), p).items]
    assert '500 kills, achieved' in labels


def test_turning_can_be_put_on_controller_buttons():
    from papasangre2.input.padmap import PadMap
    from papasangre2.shell.menu import pad_menu
    pm = PadMap()
    labels = [i.label for i in pad_menu(pm).items]
    assert 'Turn left: unbound' in labels and 'Turn right: unbound' in labels
    pm.bind('turn_left', ['leftshoulder'])
    assert pm.actions_for('leftshoulder')[0] in ('turn_left', 'hand_left')
    assert 'turn_left' in pm.actions_for('leftshoulder')
