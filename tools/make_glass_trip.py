"""Build candidate glass trip sounds (decision 19).

The original has no trip sound for glass (``footsteps/glass`` holds only
walking and running steps), so a trip on glass is silent.  Muhammad asked for
one; the first takes, made from the game's glass steps alone, lacked a body
falling.  These layer, in the shape the game's other trips share (a catch or
scuff, the fall at about half a second, then things settling):

* the catch: one of the game's own glass steps, or a step onto glass debris;
* the fall: a bodyfall from Muhammad's library (`D:\\SFX libraries`), its
  impact on the half-second mark, with broken glass crunching under it and one
  of the game's glass running steps on top, so it matches the level's feet;
* the settle: glass debris trickling out.

Stereo 44.1 kHz, peak 0.97, loudness level with the game's trips.  He chose
candidate 1 (2026-09-25), which is ``requested/sounds/trip_glass.wav``.

    python tools/make_glass_trip.py OUTDIR      -> OUTDIR/Glass trip with bodyfall N.wav
"""

from __future__ import annotations

import os
import subprocess
import sys
import wave

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from papasangre2.util import paths            # noqa: E402

SR = 44100
LENGTH = 1.9
FALL_AT = 0.50
TARGET_RMS = 0.085                  # the game's trips: 0.08 - 0.1 at this peak
GLASS = os.path.join(paths.game_bundle(), 'sounds', 'footsteps', 'glass')
LIB = os.environ.get('SFX_LIBRARY', 'SFX libraries')      # a local sound effects library
BOOM = (LIB + '/BOOM Library Close Combat Bundle WAV DVDR-DISCOVER [oddsox]/'
        'BOOM.Library.Close.Combat.Bundle.WAV.DVDR-DISCOVER/dis-bmlcc/'
        'BOOM.Library.Close.Combat.WAV.DVDR-DISCOVER')
DS = BOOM + '/Close.Combat.Designed/CC-DS Body Fall '
CK = BOOM + '/Close.Combat.Construction.Kit/Close.Combat.CK.01.02/CC-CK Body Fall '
ADOBE = LIB + '/Adobe Audition Sound Effects/'
CAT = LIB + '/CatTools Sound FX Library - complete/bodyfalls/'

_cache: dict[str, np.ndarray] = {}


def load(path: str) -> np.ndarray:
    if path not in _cache:
        raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-f', 'f32le',
                              '-ac', '2', '-ar', str(SR), '-'],
                             capture_output=True, check=True).stdout
        _cache[path] = np.frombuffer(raw, '<f4').reshape(-1, 2).astype(np.float64)
    return _cache[path]


def game(name: str) -> str:
    return os.path.join(GLASS, name + '_PRE.m4a')


def piece(path: str, start: float, end: float) -> np.ndarray:
    x = load(path)[int(start * SR):int(end * SR)].copy()
    n = min(len(x), int(0.08 * SR))
    x[-n:] *= np.linspace(1, 0, n)[:, None]                     # no click at the cut
    k = min(len(x), int(0.004 * SR))
    x[:k] *= np.linspace(0, 1, k)[:, None]
    return x


def place(out: np.ndarray, x: np.ndarray, at: float, gain_db: float, pan: float = 0.0) -> None:
    """Mix x in at `at` s, at gain_db, panned -1 (left) .. 1 (right), equal power."""
    k = int(at * SR)
    if k < 0:
        x, k = x[-k:], 0
    x = x[: max(0, len(out) - k)] * 10 ** (gain_db / 20)
    lg = np.cos((pan + 1) * np.pi / 4) * np.sqrt(2)
    rg = np.sin((pan + 1) * np.pi / 4) * np.sqrt(2)
    out[k:k + len(x), 0] += x[:, 0] * lg
    out[k:k + len(x), 1] += x[:, 1] * rg


def peak_offset(x: np.ndarray) -> float:
    return float(np.argmax(np.abs(x).max(axis=1))) / SR


def hit(out, x, gain_db, pan=0.0, at=FALL_AT):
    """Place x so that its loudest moment lands on `at`."""
    place(out, x, at - peak_offset(x), gain_db, pan)


def finish(out: np.ndarray) -> np.ndarray:
    out = out * (0.97 / np.abs(out).max())
    y = out
    for drive in np.linspace(1.0, 4.0, 61):          # soft limiter, up to the target
        y = np.tanh(out * drive) / np.tanh(drive) * 0.97
        if np.sqrt(np.mean(y.mean(axis=1) ** 2)) >= TARGET_RMS:
            break
    n = int(0.3 * SR)
    y[-n:] *= np.linspace(1, 0, n)[:, None]
    return y


def candidate(n: int) -> np.ndarray:
    out = np.zeros((int(LENGTH * SR), 2))
    crunch = ADOBE + 'Crashes/Crash Glass Crunching On Pavement 01.wav'
    drop = ADOBE + 'Crashes/Crash Debris Glass Debris Dropping On Pavement Short 01.wav'
    impact = ADOBE + 'Crashes/Crashes Glass Debris Impact 07.wav'
    floor13 = ADOBE + 'Crashes/Crashes Glass Debris On Concrete Floor 13.wav'
    sprinkle = ADOBE + 'Crashes/Crash Glass Debris Sprinkling On Concrete 01.wav'
    debris_step = ADOBE + 'Foley Footsteps/Foley Footstep Single Step On Glass Debris 01.wav'
    wood = ADOBE + 'Crashes/Crash Glass And Wood Debris Crunching 01.wav'
    if n == 1:      # a hard fall onto broken glass
        place(out, piece(game('footwalk_glass_c'), 0.0, 0.25), 0.02, -14, -0.2)
        hit(out, piece(DS + 'Concrete Hard 01.wav', 0.195, 1.1), 0, 0.0)
        hit(out, piece(crunch, 0.0, 0.9), -5, 0.15)
        hit(out, piece(game('footrun_glass_a'), 0.0, 0.6), -8, -0.1)
        place(out, piece(sprinkle, 0.5, 1.4), FALL_AT + 0.22, -16, 0.3)
    elif n == 2:    # a stumble, then down on the glass
        place(out, piece(debris_step, 0.0, 0.6), 0.0, -12, 0.2)
        place(out, piece(game('footrun_glass_c'), 0.0, 0.4), 0.26, -9, -0.25)
        hit(out, piece(DS + 'Concrete Medium 01.wav', 2.68, 3.6), 0, 0.0)
        hit(out, piece(drop, 0.0, 0.9), -4, -0.1)
        place(out, piece(game('footwalk_glass_h'), 0.3, 1.0), FALL_AT + 0.25, -14, 0.25)
    elif n == 3:    # heavy, leather and bone
        place(out, piece(game('footwalk_glass_e'), 0.0, 0.22), 0.05, -14, 0.2)
        hit(out, piece(CK + 'Concrete Leather Heavy.wav', 3.53, 4.3), 0, 0.0)
        hit(out, piece(impact, 0.0, 0.8), -4, 0.2)
        hit(out, piece(game('footrun_glass_b'), 0.0, 0.6), -9, -0.15)
        place(out, piece(sprinkle, 1.2, 2.2), FALL_AT + 0.2, -15, -0.3)
    elif n == 4:    # a softer body, a lot of glass
        place(out, piece(debris_step, 0.1, 0.7), 0.0, -13, -0.2)
        hit(out, piece(DS + 'Generic Medium 02.wav', 2.285, 3.2), -1, 0.0)
        hit(out, piece(floor13, 0.4, 1.8), -3, 0.1)
        hit(out, piece(game('footrun_glass_d'), 0.0, 0.6), -9, 0.2)
    elif n == 5:    # a body on debris, with the game's glass
        place(out, piece(game('footwalk_glass_f'), 0.0, 0.28), 0.0, -13, 0.1)
        hit(out, piece(CAT + 'body falls on debris 1.wav', 0.0, 1.1), 0, 0.0)
        hit(out, piece(crunch, 0.0, 0.8), -6, -0.2)
        hit(out, piece(game('footrun_glass_g'), 0.0, 0.6), -8, 0.15)
        place(out, piece(sprinkle, 2.0, 2.8), FALL_AT + 0.3, -17, 0.2)
    elif n == 6:    # cloth and a crunch that runs on
        place(out, piece(game('footwalk_glass_a'), 0.0, 0.2), 0.03, -14, -0.1)
        place(out, piece(game('footrun_glass_h'), 0.0, 0.35), 0.28, -10, 0.2)
        hit(out, piece(CK + 'Generic Cloth Hard.wav', 4.145, 4.9), 0, 0.0)
        hit(out, piece(wood, 0.0, 1.2), -5, -0.15)
        hit(out, piece(game('footrun_glass_e'), 0.0, 0.6), -9, 0.1)
    return finish(out)


def write(path: str, x: np.ndarray) -> None:
    pcm = np.clip(np.round(x * 32767), -32768, 32767).astype('<i2')
    with wave.open(path, 'wb') as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def main() -> int:
    outdir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'build', 'glass_trips')
    os.makedirs(outdir, exist_ok=True)
    for n in range(1, 7):
        x = candidate(n)
        p = os.path.join(outdir, f'Glass trip with bodyfall {n}.wav')
        write(p, x)
        m = x.mean(axis=1)
        print(f'{os.path.basename(p)}  {len(m) / SR:.2f} s  peak {np.abs(x).max():.2f}  '
              f'rms {np.sqrt(np.mean(m ** 2)):.3f}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
