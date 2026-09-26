"""Render a knifed penguin as the game plays it - the real engine on a loopback
device, silent - to a WAV, for when the sim cannot show what the player hears.

    python tools/render_knife.py ps2_17 penguin out.wav [swing]

swing puts back the knife swing ps2_17's penguins sent before decision 23.
"""
import math
import os
import sys
import tempfile
import wave

os.environ['APPDATA'] = tempfile.mkdtemp()          # never touch real saves
os.environ['LOCALAPPDATA'] = tempfile.mkdtemp()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np                                               # noqa: E402
from papasangre2.audio.bank import SoundBank                     # noqa: E402
from papasangre2.audio.engine import AudioEngine                 # noqa: E402
from papasangre2.core.game import Game                           # noqa: E402
from papasangre2.save.progress import InMemoryProgress           # noqa: E402
from papasangre2.util import paths                               # noqa: E402
from papasangre2.world import requested                          # noqa: E402

level, name, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
keep_swing = len(sys.argv) > 4 and sys.argv[4] == 'swing'
if keep_swing:
    requested.DROP_TRIGGERS = {k: v for k, v in requested.DROP_TRIGGERS.items() if k[0] != 'ps2_17'}


class S:
    blind_intro = True
    skip_explanation = True
    pc_instructions = False
    skip_ping = False


eng = AudioEngine()
eng.open(loopback=True)
base = paths.game_bundle()


def bank(n):
    b = SoundBank(eng, base)
    b.load_playlist(n)
    return b


g = Game(base, InMemoryProgress(), S(), bank, engine=eng)
out = []


def step(sec):
    for _ in range(int(round(sec / 0.01))):
        g.update(0.01)
        out.append(np.asarray(eng.render(441)).reshape(-1, 2))


g.load(level)
lv = g.level
p = lv.player
g.bus.post('PGE_MESSAGE_EnableHands', {})
g.bus.post('PGE_MESSAGE_EnableWalk', {})
g.bus.post('PGE_MESSAGE_ChangeHandAction', {'rightHand': 'beat'})
if level == 'ps2_17':
    g.bus.post('PGE_MESSAGE_MovePlayerToPosition', {'position': (-60.0, 0.0)})
g.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': name})
step(0.5)
pen = lv.agent(name)
t_end = g.now + 120
while g.now < t_end:
    dx, dy = pen.position[0] - p.position[0], pen.position[1] - p.position[1]
    ox, oy = p.orientation_vector
    diff = (math.atan2(dy, dx) - math.atan2(oy, ox) + math.pi) % (2 * math.pi) - math.pi
    if abs(diff) > 0.05:
        g.interpreter.rotate_by(diff)
    if pen.active and pen.is_in_beating_range and p.reload_timer > p.reload_time:
        break
    step(0.05)
step(0.5)                               # half a second of the penguin, then the knife
n0 = len(out) - 50
g.interpreter.hand_pressed('R')
g.bus.update(g.now)
step(2.5)
clip = np.concatenate(out[n0:])
peak = float(np.abs(clip).max())
pcm = (np.clip(clip, -1, 1) * 32767).astype('<i2')
with wave.open(out_path, 'wb') as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(44100)
    w.writeframes(pcm.tobytes())
print(os.path.basename(out_path), 'peak', round(peak, 3), 'dist', round(math.hypot(dx, dy), 1))
g.unload()
eng.close()
