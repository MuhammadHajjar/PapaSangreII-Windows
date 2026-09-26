"""Measure the port's reverb against the original's, on the same input.

    python tools/measure_reverb.py            the Intro's room
    python tools/measure_reverb.py all        every room the game uses
    python tools/measure_reverb.py fit        fit EFX_ENERGY_MATCH (all rooms,
                                              four directions, 50 px)

For each room and a spread of distances, one impulse is played through the
real engine (OpenAL Soft, loopback, the recovered HRTF) twice: once with only
the direct path, once with only the reverb send.  The original's reverb for the
same sound is computed from the direct render: each ear convolved with the
recovered Freeverb (``papasangre2.audio.freeverb``), scaled by the level's
volume and by the send the original would use at that distance
(``autoReverbMix``: 0.05 at 1 px or closer, 0.3 at 100 px or further, dry =
1 - wet).  The table gives the reverb-to-direct energy ratio of each, and the
decay times.

Nothing here writes into the repository or a real settings folder.
"""

from __future__ import annotations

import math
import os
import sys
import tempfile
import wave

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from papasangre2.util import paths                               # noqa: E402

_TMP = tempfile.mkdtemp(prefix='ps2_reverb_')
paths.writable_root = lambda: _TMP                               # never the repo
os.environ['LOCALAPPDATA'] = _TMP

from papasangre2.audio import freeverb as FV                     # noqa: E402
from papasangre2.audio import openal as OA                       # noqa: E402
from papasangre2.audio.engine import AudioEngine, SoundSpec      # noqa: E402

FS = 44100
#: (room size, dampening, volume) per level, from the levels' Room objects and
#: their ChangeReverbSettings actions.
ROOMS = {
    'ps2_Intro': (1.5, 100, 0.2),
    'ps2_1-5': (1.7, 70, 1.0),
    'ps2_7/8/11/15/18': (2.3, 100, 0.2),
    'ps2_9': (1.1, 100, 2.0),
    'ps2_10/17': (1.8, 75, 0.4),
    'ps2_12-16 change': (1.4, 70, 0.8),
    'ps2_13': (0.5, 0, 8.0),
    'ps2_16 change': (2.3, 75, 2.6),
}
DISTANCES = (1, 10, 50, 100, 200, 400)


def auto_mix(d: float) -> tuple[float, float]:
    """``-[S3DSound setPlanarInternalInternal]``: (dry, wet) at distance d px."""
    if d < 1.0:
        t = 0.0
    elif d > 100.0:
        t = 1.0
    else:
        t = (d - 1.0) / 99.0
    wet = 0.05 + t * (0.3 - 0.05)
    return 1.0 - wet, wet


def impulse_wav() -> str:
    path = os.path.join(_TMP, 'impulse.wav')
    data = np.zeros(FS // 10, dtype=np.int16)
    data[0] = 32767
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(FS)
        w.writeframes(data.tobytes())
    return path


#: ``-[PGEPlayer setupReverbParameters:]`` / the agents' version.
REVERB_MIX = dict(auto_mix=True, min_distance=1.0, max_distance=100.0,
                  min_wet_send=0.05, max_wet_send=0.3)


def render(eng: AudioEngine, snd: str, d: float, *, part: str, seconds: float,
           angle: float = 45.0) -> np.ndarray:
    """Play the impulse as the game would (send on, automatic mix), keeping only
    one ``part`` of the output: 'direct' or 'wet'."""
    s = eng.load(SoundSpec('impulse', snd, spatialized=True))
    ang = math.radians(angle)
    s.planar = (d * math.cos(ang), d * math.sin(ang))
    s.dry_gain, s.wet_gain = 1.0, 1.0
    s.send_to_reverb = True
    s.reverb_mix = dict(REVERB_MIX)
    s.play()
    src = s.source
    al = eng.al
    if part == 'direct':
        al.alSource3i(src, OA.AL_AUXILIARY_SEND_FILTER, 0, 0, OA.AL_FILTER_NULL)
    else:
        al.alSourcei(src, OA.AL_DIRECT_FILTER, eng._lowpass(0.0))
    n = int(seconds * FS)
    out = []
    got = 0
    while got < n:
        buf = np.asarray(eng.render(4096), dtype=np.float64).reshape(-1, 2)
        out.append(buf)
        got += len(buf)
    s.stop()
    return np.concatenate(out)[:n]


def band_decay(x: np.ndarray, lo_hz: float, hi_hz: float, fs: int = FS) -> float:
    """T60 of one frequency band, from short-frame energies (-5 to -35 dB)."""
    n, hop = 2048, 512
    win = np.hanning(n)
    fr = np.fft.rfftfreq(n, 1.0 / fs)
    sel = (fr >= lo_hz) & (fr < hi_hz)
    levels = []
    for i in range(0, len(x) - n, hop):
        sp = np.abs(np.fft.rfft(x[i:i + n] * win)) ** 2
        levels.append(10.0 * math.log10(float(np.sum(sp[sel])) + 1e-30))
    lv = np.array(levels)
    k = int(np.argmax(lv))
    peak = lv[k]
    tail = lv[k:]
    i0 = int(np.argmax(tail <= peak - 5.0))
    i1 = int(np.argmax(tail <= peak - 35.0))
    if i1 <= i0 + 1:
        return 0.0
    t = np.arange(i0, i1) * hop / fs
    slope = np.polyfit(t, tail[i0:i1], 1)[0]
    return -60.0 / slope if slope < 0 else float('inf')


def fresh(room) -> AudioEngine:
    eng = AudioEngine()
    eng.open(loopback=True)
    if eng.reverb_slot is None:
        raise SystemExit('no EFX reverb on this machine')
    eng.set_reverb(*room)
    return eng


def db(x: float) -> float:
    return 10.0 * math.log10(x) if x > 0 else -999.0


def measure(name: str, room, distances=DISTANCES, angles=(45.0,)) -> list[dict]:
    snd = impulse_wav()
    size, damp, vol = room
    ir = FV.impulse_response(size, damp, 1.0, seconds=8.0)
    t60 = FV.decay_time(ir)
    seconds = max(2.0, t60 * 1.6 + 0.5)
    rows = []
    for ang in angles:
        for d in distances:
            eng = fresh(room)
            try:
                dry = render(eng, snd, d, part='direct', seconds=seconds, angle=ang)
                wet = render(eng, snd, d, part='wet', seconds=seconds, angle=ang)
            finally:
                eng.close()
            dry_g, wet_g = auto_mix(d)
            unit = dry / dry_g                    # the binaural signal at gain 1
            e_dry = float(np.sum(dry ** 2))
            e_port = float(np.sum(wet ** 2))
            n = 1 << int(math.ceil(math.log2(len(unit) + len(ir))))
            h = np.fft.rfft(ir, n)
            orig = np.zeros_like(unit)
            for ch in range(2):
                orig[:, ch] = np.fft.irfft(np.fft.rfft(unit[:, ch], n) * h, n)[:len(unit)]
            orig *= vol * wet_g
            e_orig = float(np.sum(orig ** 2))
            om, pm = orig[:, 0] + orig[:, 1], wet[:, 0] + wet[:, 1]
            rows.append(dict(
                room=name, d=d, angle=ang,
                orig=db(e_orig / e_dry), port=db(e_port / e_dry),
                diff=db(e_port / e_dry) - db(e_orig / e_dry),
                t60_orig=band_decay(om, 700, 1400), t60_port=band_decay(pm, 700, 1400),
                hf_orig=band_decay(om, 4000, 6300), hf_port=band_decay(pm, 4000, 6300)))
    return rows


def main() -> int:
    args = sys.argv[1:]
    fit = 'fit' in args
    args = [a for a in args if a != 'fit']
    if args == ['all'] or (fit and not args):
        names = list(ROOMS)
    else:
        names = args or ['ps2_Intro']
    print(f'{"room":18} {"px":>4} {"deg":>4} {"original":>9} {"port":>9} {"port-orig":>9}'
          f' {"1k T60 o/p":>12} {"5k T60 o/p":>12}')
    diffs = []
    for name in names:
        angles = (0.0, 45.0, 90.0, 180.0) if fit else (45.0,)
        dists = (50,) if fit else DISTANCES
        for r in measure(name, ROOMS[name], dists, angles):
            diffs.append(r['diff'])
            print(f'{r["room"]:18} {r["d"]:>4} {r["angle"]:>4.0f} {r["orig"]:>8.1f}dB'
                  f' {r["port"]:>8.1f}dB {r["diff"]:>+8.1f}dB'
                  f' {r["t60_orig"]:>5.2f}/{r["t60_port"]:<5.2f}s'
                  f' {r["hf_orig"]:>5.2f}/{r["hf_port"]:<5.2f}s')
    if diffs:
        mean = sum(diffs) / len(diffs)
        print()
        print(f'port minus original: mean {mean:+.2f} dB, spread '
              f'{min(diffs):+.2f} .. {max(diffs):+.2f} dB over {len(diffs)} renders')
        if fit:
            from papasangre2.audio import engine as E
            print(f'EFX_ENERGY_MATCH = {E.EFX_ENERGY_MATCH * 10 ** (-mean / 20.0):.4f}'
                  f'   (was {E.EFX_ENERGY_MATCH})')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
