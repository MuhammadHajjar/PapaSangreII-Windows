"""The original's reverb, recovered exactly: CSL's ``Freeverb`` as Papa Sangre II
builds it.  A reference model, used to measure the port's reverb against.

Where it lives in the binary (engine 1_1_013, arm64):

====================================  =========================================
``csl::Stereoverb`` ctor 0x100116510  one Freeverb per channel of the wet mix
``csl::Freeverb`` ctor 0x100115fec    -> init 0x100115cec
``Freeverb::nextBuffer`` 0x100116314  the per-sample loop below
setRoomSize 0x100116970               feedback = size * 0.28 + 0.3
setDampening 0x1001169fc              damp1 = dampening * 0.01 * 0.4
setWetLevel 0x100116a88               wet = volume (stored as given)
setDryLevel 0x100116afc               dry = 0 (``-[S3DEngine init]``)
====================================  =========================================

This is *not* Jezar's Freeverb as usually shipped.  Only the first **six** of
the eight comb tunings and the first **three** of the four allpass tunings are
used (the tables at 0x1001b8850 / 0x1001b8870 hold all of them; the loops stop
at 6 and 3), the room offset is 0.3 instead of 0.7, and there is no
``scalewet``: the level's ``reverbVolume`` is the wet gain itself.  The right
channel's Freeverb is built identically to the left's - no stereo spread.

Per sample, for one channel (``nextBuffer``)::

    in  = x * 0.015                                  fixedgain, +0xcc
    acc = 0
    for each comb (delay D, feedback f, damp1, damp2 = 1 - damp1):
        out   = buf[i]
        store = out * damp2 + store * damp1
        buf[i] = in + store * f
        acc  += out
    for each allpass (delay D, feedback 0.5):
        b      = buf[i]
        buf[i] = acc + b * 0.5
        acc    = b - acc
    y = acc * wet + x * dry                          vDSP_vsmul + vDSP_vsma

The engine starts it at room 2.2, dampening 2, wet 0, dry 0, then
``-[PGEngine init]`` sets 2.1 / 5 / 1 and each level's Room its own values.
The setters clamp as ``engine.py`` records.

The delays are in samples at the engine's rate, 44100 Hz (``0xac44``).
"""

from __future__ import annotations

import math

import numpy as np

SAMPLE_RATE = 44100
COMB_TUNING = (1116, 1188, 1277, 1356, 1422, 1491)          # 6 of the 8
ALLPASS_TUNING = (556, 441, 341)                            # 3 of the 4
ALLPASS_FEEDBACK = 0.5
FIXED_GAIN = 0.015
ROOM_SCALE, ROOM_OFFSET = 0.28, 0.3
DAMP_SCALE = 0.01 * 0.4
#: The S3DEngine setters' clamps (``-[S3DEngine setReverbRoomSize:]`` etc.).
ROOM_SIZE_MAX = 2.3
DAMPENING_RANGE = (0.0, 100.0)
VOLUME_RANGE = (0.0, 8.0)


def coefficients(room_size: float, dampening: float) -> tuple[float, float]:
    """(comb feedback, damp1) for the S3D room size and dampening."""
    room_size = min(max(room_size, 0.0), ROOM_SIZE_MAX)
    dampening = min(max(dampening, DAMPENING_RANGE[0]), DAMPENING_RANGE[1])
    return room_size * ROOM_SCALE + ROOM_OFFSET, dampening * DAMP_SCALE


def process(x, room_size: float, dampening: float, volume: float = 1.0) -> np.ndarray:
    """Run the recovered loop sample by sample (slow; for checking the fast path)."""
    f, d1 = coefficients(room_size, dampening)
    d2 = 1.0 - d1
    combs = [[[0.0] * n, 0, 0.0, n] for n in COMB_TUNING]          # buf, idx, store, len
    alls = [[[0.0] * n, 0, n] for n in ALLPASS_TUNING]
    out = np.zeros(len(x))
    g = ALLPASS_FEEDBACK
    for k, xs in enumerate(np.asarray(x, dtype=float)):
        inp = xs * FIXED_GAIN
        acc = 0.0
        for c in combs:
            buf, i, store, n = c
            o = buf[i]
            store = o * d2 + store * d1
            buf[i] = inp + store * f
            c[1] = i + 1 if i + 1 < n else 0
            c[2] = store
            acc += o
        for a in alls:
            buf, i, n = a
            b = buf[i]
            buf[i] = acc + b * g
            acc = b - acc
            a[1] = i + 1 if i + 1 < n else 0
        out[k] = acc * volume
    return out


def transfer(room_size: float, dampening: float, n: int) -> np.ndarray:
    """The loop's frequency response on an ``n``-point rfft grid (volume 1)."""
    f, d1 = coefficients(room_size, dampening)
    d2 = 1.0 - d1
    w = 2.0 * np.pi * np.arange(n // 2 + 1) / n
    zi = np.exp(-1j * w)                                             # z^-1
    lp = d2 / (1.0 - d1 * zi)
    total = np.zeros_like(zi)
    for d in COMB_TUNING:
        zd = zi ** d
        total += zd / (1.0 - f * lp * zd)
    for d in ALLPASS_TUNING:
        zd = zi ** d
        total *= ((1.0 + ALLPASS_FEEDBACK) * zd - 1.0) / (1.0 - ALLPASS_FEEDBACK * zd)
    return FIXED_GAIN * total


def impulse_response(room_size: float, dampening: float, volume: float = 1.0,
                     seconds: float = 12.0) -> np.ndarray:
    """The exact impulse response, computed in the frequency domain.

    The grid is long enough (``seconds``) that the circular wrap is far below
    the -60 dB point for every room the game uses (the longest, size 2.3, is
    down 60 dB in under 4 s).
    """
    n = 1 << int(math.ceil(math.log2(seconds * SAMPLE_RATE)))
    return np.fft.irfft(transfer(room_size, dampening, n), n) * volume


def energy(ir: np.ndarray) -> float:
    return float(np.sum(np.square(ir)))


def decay_time(ir: np.ndarray, fs: int = SAMPLE_RATE, lo: float = -5.0,
               hi: float = -35.0) -> float:
    """T60 by Schroeder backward integration, fitted between ``lo`` and ``hi`` dB."""
    e = np.cumsum(np.square(ir)[::-1])[::-1]
    if e[0] <= 0:
        return 0.0
    edc = 10.0 * np.log10(np.maximum(e / e[0], 1e-30))
    i0 = int(np.argmax(edc <= lo))
    i1 = int(np.argmax(edc <= hi))
    if i1 <= i0:
        return 0.0
    t = np.arange(i0, i1) / fs
    slope = np.polyfit(t, edc[i0:i1], 1)[0]
    return -60.0 / slope if slope < 0 else float('inf')


def band(ir: np.ndarray, lo_hz: float, hi_hz: float, fs: int = SAMPLE_RATE) -> np.ndarray:
    """The part of ``ir`` between two frequencies (a brick-wall FFT band)."""
    spec = np.fft.rfft(ir)
    fr = np.fft.rfftfreq(len(ir), 1.0 / fs)
    spec[(fr < lo_hz) | (fr >= hi_hz)] = 0.0
    return np.fft.irfft(spec, len(ir))


def loop_decay(room_size: float, dampening: float, hz: float) -> float:
    """T60 at one frequency from the comb loop gains alone, averaged over the combs."""
    f, d1 = coefficients(room_size, dampening)
    w = 2.0 * math.pi * hz / SAMPLE_RATE
    mag = (1.0 - d1) / abs(1.0 - d1 * complex(math.cos(w), -math.sin(w)))
    g = f * mag
    if g <= 0 or g >= 1:
        return float('inf') if g >= 1 else 0.0
    ts = [-3.0 * d / (SAMPLE_RATE * math.log10(g)) for d in COMB_TUNING]
    return sum(ts) / len(ts)
