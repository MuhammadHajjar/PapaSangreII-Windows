"""The reverb: the recovered Freeverb, the per-sound dry/wet mix, and the
port's OpenAL reverb measured against the original's on the same input."""

import math
import os
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from papasangre2.audio import freeverb as FV                      # noqa: E402
from papasangre2.audio.engine import Sound, SoundSpec, reverb_params  # noqa: E402
from papasangre2.entities.player import REVERB                    # noqa: E402


# ----------------------------------------------------------- the Freeverb
def test_the_fast_model_is_the_recovered_loop_sample_for_sample():
    x = np.zeros(8000)
    x[0] = 1.0
    x[3000] = -0.5
    slow = FV.process(x, 1.7, 70, 1.0)
    h = FV.impulse_response(1.7, 70, 1.0)[:8000]
    fast = np.convolve(x, h)[:8000]
    assert np.max(np.abs(slow - fast)) < 1e-12


def test_the_recovered_constants():
    assert FV.coefficients(2.1, 5) == pytest.approx((2.1 * 0.28 + 0.3, 5 * 0.004))
    assert FV.coefficients(9.0, 150) == FV.coefficients(2.3, 100)     # the setters clamp
    assert len(FV.COMB_TUNING) == 6 and len(FV.ALLPASS_TUNING) == 3
    assert FV.FIXED_GAIN == 0.015


def test_nothing_comes_out_before_the_shortest_comb():
    h = FV.impulse_response(1.5, 100, 1.0)
    assert np.max(np.abs(h[:FV.COMB_TUNING[0]])) < 1e-12
    assert abs(h[FV.COMB_TUNING[0]]) > 1e-4


def test_dampening_shortens_the_treble_tail_not_the_bass():
    assert FV.loop_decay(1.5, 100, 5000) < 0.7 * FV.loop_decay(1.5, 100, 200)
    assert FV.loop_decay(1.5, 0, 5000) == pytest.approx(FV.loop_decay(1.5, 0, 200))


# ------------------------------------------------------- the EFX mapping
def test_the_efx_decay_follows_the_freeverb():
    p = reverb_params(1.5, 100, 0.2)
    assert p['DECAY_TIME'] == pytest.approx(FV.loop_decay(1.5, 100, 1000))
    assert p['DECAY_HFRATIO'] == pytest.approx(FV.loop_decay(1.5, 100, 5000)
                                               / FV.loop_decay(1.5, 100, 1000))
    assert p['GAINHF'] == 1.0                   # Freeverb does not filter its input
    assert p['REFLECTIONS_GAIN'] == 0.0


def test_loudness_past_the_efx_cap_goes_into_the_late_reverb():
    p = reverb_params(0.5, 0, 8.0)              # ps2_13, underwater
    assert p['GAIN'] == 1.0 and p['LATE_REVERB_GAIN'] > 1.0
    q = reverb_params(0.5, 0, 4.0)
    total_p = p['GAIN'] * p['LATE_REVERB_GAIN']
    total_q = q['GAIN'] * q['LATE_REVERB_GAIN']
    assert total_p == pytest.approx(2 * total_q)


# --------------------------------------------------- the per-sound mix
class StubEngine:
    reverb_slot = 1
    head_position = (0.0, 0.0, 0.0)
    head_orientation = 0.0


def sound(**kw):
    s = Sound(StubEngine(), SoundSpec('s', 'x', spatialized=True), 0, 1.0, 1)
    for k, v in kw.items():
        setattr(s, k, v)
    return s


@pytest.mark.parametrize('d, wet', [(0.5, 0.05), (1.0, 0.05), (50.5, 0.175),
                                    (100.0, 0.3), (400.0, 0.3)])
def test_auto_reverb_mix_follows_the_distance(d, wet):
    s = sound(send_to_reverb=True, dry_gain=1.0, wet_gain=0.5, reverb_mix=dict(REVERB))
    s._planar = (d, 0.0, 0.0)
    assert s._auto_mix()
    assert s.wet_gain == pytest.approx(wet)
    assert s.dry_gain == pytest.approx(1.0 - wet)


def test_the_distance_is_measured_in_three_dimensions():
    s = sound(reverb_mix=dict(REVERB))
    s._planar = (30.0, 40.0, 0.0)               # 50 px
    s._auto_mix()
    assert s.wet_gain == pytest.approx(0.05 + (49.0 / 99.0) * 0.25)


def test_no_send_means_the_dry_gain_plays_no_part():
    s = sound(gain=0.8, dry_gain=0.3, send_to_reverb=False)
    assert s._mix() == (0.8, 1.0, 0.0)


def test_with_a_send_the_louder_path_rides_on_the_source_gain():
    s = sound(gain=0.5, dry_gain=0.7, wet_gain=0.3, send_to_reverb=True)
    g, direct, send = s._mix()
    assert g == pytest.approx(0.35) and direct == 1.0 and send == pytest.approx(0.3 / 0.7)
    s = sound(gain=1.0, dry_gain=0.2, wet_gain=0.8, send_to_reverb=True)
    g, direct, send = s._mix()
    assert g == pytest.approx(0.8) and direct == pytest.approx(0.25) and send == 1.0


def test_an_unpositioned_sound_keeps_its_own_mix():
    """autoReverbMix only runs for a sound with a spatial source."""
    s = sound(send_to_reverb=True, dry_gain=1.0, wet_gain=0.5, reverb_mix=dict(REVERB))
    s._spatialized = False
    s._apply_position()                         # no source: nothing to do
    assert (s.dry_gain, s.wet_gain) == (1.0, 0.5)


# --------------------------------------- measured against the original
def _measure(room, distances, angles):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'measure_reverb', os.path.join(ROOT, 'tools', 'measure_reverb.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    try:
        return m.measure('t', room, distances, angles)
    except SystemExit:
        pytest.skip('no EFX reverb on this machine')


def test_the_ports_reverb_matches_the_original_in_level_and_decay():
    rows = _measure((1.7, 70, 1.0), (50,), (0.0, 90.0))          # ps2_1's room
    diffs = [r['diff'] for r in rows]
    assert all(abs(x) < 4.5 for x in diffs), diffs                # direction: PORT-SIDE
    assert abs(sum(diffs) / len(diffs)) < 1.5, diffs
    for r in rows:
        assert r['t60_port'] == pytest.approx(r['t60_orig'], rel=0.15)
        assert r['hf_port'] == pytest.approx(r['hf_orig'], rel=0.15)


def test_the_reverb_falls_off_with_distance_exactly_like_the_direct_sound():
    rows = _measure((1.5, 100, 0.2), (1, 100, 400), (45.0,))     # the Intro's room
    offsets = [r['diff'] for r in rows]
    assert max(offsets) - min(offsets) < 0.5, offsets
    assert rows[1]['orig'] - rows[0]['orig'] == pytest.approx(
        20 * math.log10((0.3 / 0.7) / (0.05 / 0.95)), abs=0.1)


# ---------------------------------------------- the agents' version
class _Snd:
    def __init__(self):
        self.gain = 0.123
        self.spatialized = False
        self.planar = (0.0, 0.0)
        self.played = False

    def play(self):
        self.played = True


def test_an_agents_sound_plays_at_the_agents_gain_unless_told_otherwise():
    """`-[PGEGameAgent setupReverbParameters:]` copies the agent's gain."""
    from types import SimpleNamespace
    from papasangre2.core.messages import MessageBus
    from papasangre2.entities.agent import GameAgent
    snd = _Snd()
    world = SimpleNamespace(bank=SimpleNamespace(any_sound_containing=lambda n: snd))
    a = GameAgent(MessageBus(), world)
    a.name, a.gain, a.wet_gain = 'dog', 0.6, 1.0
    a._play_spatial_sound_on_agent(None, {'agentName': 'dog', 'soundName': 'bark'})
    assert snd.played and snd.gain == 0.6 and snd.send_to_reverb
    assert snd.reverb_mix == REVERB
    a._play_spatial_sound_on_agent(None, {'agentName': 'dog', 'soundName': 'bark', 'gain': '0.2'})
    assert snd.gain == 0.2
