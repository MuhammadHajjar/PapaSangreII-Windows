"""A headless run of a level: fake sounds that end, real durations, real data.

Used by the tests and by `tools/run_level.py`.  A `FakeSound` plays for the
duration of its file (read from the file's header, so the timing is the real
game's), loops if asked, and reports `ended` when it runs out; a `FakeBank`
declares exactly the sounds the level's playlists declare.  `Sim` owns the
clock and drives everything the way the game loop does: the 10 ms monitor
pump, the 0.05 s level tick, and the bus.
"""

from __future__ import annotations

import os
import random

from .assets.sexp import include_stem, parse_playlist
from .assets.tiled import level_path, load_level
from .core.messages import MessageBus
from .input.device import Phone
from .input.interpreter import MoveInterpretor
from .util import paths
from .save.progress import InMemoryProgress
from .save.tracker import GameTracker
from .assets import requested
from .world import requested as requested_lines
from .world.level import Level, TICK

_DURATIONS: dict[str, float] = {}


def file_duration(path: str) -> float:
    """Seconds of audio in a file, from its container header."""
    if path in _DURATIONS:
        return _DURATIONS[path]
    d = 1.0
    try:
        import av
        with av.open(path) as c:
            if c.duration:
                d = c.duration / 1_000_000.0
            else:
                st = c.streams.audio[0]
                d = float(st.duration * st.time_base)
    except Exception:                                         # noqa: BLE001
        pass
    _DURATIONS[path] = d
    return d


class FakeSound:
    """Stands in for an OpenAL Sound; plays against the sim clock."""

    def __init__(self, sim, name: str, path: str, spatialized: bool) -> None:
        self.sim = sim
        self.name = name
        self.path = path
        self.duration = file_duration(path) if path else 1.0
        self.spatialized = spatialized
        self.gain = 1.0
        self.dry_gain = 1.0
        self.wet_gain = 0.0
        self.send_to_reverb = False
        self.reverb_mix = None
        self.looping = False
        self.planar = (0.0, 0.0, 0.0)
        self._start = None
        self._paused_at = None
        self._started = False
        self.plays = 0

    def play(self) -> None:
        self._start = self.sim.now
        self._paused_at = None
        self._started = True
        self.plays += 1
        self.sim.log.append((self.sim.now, 'play', self.name))

    def stop(self) -> None:
        if self._started and self.playing:
            self.sim.log.append((self.sim.now, 'stop', self.name))
        self._start = None
        self._started = False

    def pause(self) -> None:
        if self.playing:
            self._paused_at = self.sim.now

    def resume(self) -> None:
        if self._paused_at is not None and self._start is not None:
            self._start += self.sim.now - self._paused_at
            self._paused_at = None

    @property
    def paused(self) -> bool:
        return self._paused_at is not None

    @property
    def playing(self) -> bool:
        if self._start is None or self._paused_at is not None:
            return False
        return self.looping or (self.sim.now - self._start) < self.duration

    @property
    def ended(self) -> bool:
        return self._started and not self.playing and not self.paused

    @property
    def offset(self) -> float:
        if self._start is None:
            return 0.0
        t = (self._paused_at if self._paused_at is not None else self.sim.now) - self._start
        if self.looping and self.duration > 0:
            return t % self.duration
        return min(t, self.duration)


class FakeBank:
    """The level's playlists, with fake sounds."""

    def __init__(self, sim, bundle: str, level: str, rng: random.Random) -> None:
        self.sim = sim
        self.bundle = bundle
        self.rng = rng
        self.specs: dict[str, tuple[str, bool]] = {}
        self._cache: dict[str, FakeSound] = {}
        meta = os.path.join(bundle, 'meta', 'S3DPlayListModel')
        self._load(meta, level, set())

    def _load(self, meta: str, stem: str, seen: set) -> None:
        if stem in seen:
            return
        seen.add(stem)
        f = os.path.join(meta, stem + '.S3DPlayListModel#0.sexp')
        if not os.path.exists(f):
            return
        pl = parse_playlist(open(f, encoding='utf-8', errors='replace').read(), os.path.basename(f))
        for d in pl.sounds:
            if d.name:
                path = os.path.join(self.bundle, d.bundle_path)
                if os.path.exists(path):
                    self.specs.setdefault(d.name, (path, d.spatialized))
        for inc in pl.includes:
            self._load(meta, include_stem(inc), seen)

    def add_file(self, name: str, path: str, spatialized: bool = True) -> bool:
        if not os.path.exists(path):
            return False
        self.specs[name] = (path, spatialized)
        self._cache.pop(name, None)
        return True

    def has(self, name: str) -> bool:
        return bool(name) and name in self.specs

    def ensure(self, name: str, rel_path: str, spatialized: bool = True) -> bool:
        if name in self.specs:
            return True
        path = os.path.join(self.bundle, *rel_path.split('/'))
        if not os.path.exists(path):
            return False
        self.specs[name] = (path, spatialized)
        return True

    def sound(self, name: str):
        if not name or name not in self.specs:
            return None
        s = self._cache.get(name)
        if s is None:
            path, spat = self.specs[name]
            s = self._cache[name] = FakeSound(self.sim, name, path, spat)
        return s

    def names_in_order(self, prefix: str) -> list[str]:
        return [n for n in self.specs if n.startswith(prefix)]

    def any_sound_with_prefix(self, prefix: str):
        names = sorted(n for n in self.specs if n.startswith(prefix))
        return self.sound(self.rng.choice(names)) if names else None

    def any_sound_containing(self, needle: str):
        names = sorted(n for n in self.specs if needle in n)
        return self.sound(self.rng.choice(names)) if names else None

    def live_sounds(self):
        return list(self._cache.values())

    def stop_all(self) -> None:
        for s in self._cache.values():
            s.stop()


class Progress(InMemoryProgress):
    """The save, in memory (tripTimes, wallTimes, achievements...)."""


class Sim:
    """Drive one level headless.  `step(dt)` advances game time."""

    def __init__(self, level_name: str = 'ps2_Intro', voice_over: bool = True,
                 seed: int = 1, bundle: str | None = None) -> None:
        self.bundle = bundle or paths.game_bundle()
        self.rng = random.Random(seed)
        self.bus = MessageBus()
        self.now = 0.0
        self.log: list[tuple[float, str, str]] = []
        self.interpreter = MoveInterpretor(self.bus)
        self.phone = Phone(self.bus)
        self.progress = Progress()
        self.tracker = GameTracker(self.bus)
        self.bank = FakeBank(self, self.bundle, level_name, self.rng)
        requested.add_to(self.bank)
        requested_lines.ensure_sounds(self.bank, level_name)
        data = load_level(level_path(self.bundle, level_name), level_name)
        self.level = Level(self.bus, data, bank=self.bank, voice_over=voice_over,
                           progress=self.progress, rng=self.rng)
        self.level.tracker = self.tracker
        self.messages: list[tuple[float, str, dict]] = []
        self.bus.subscribe(None, lambda n, p: self.messages.append((self.now, n, dict(p))))
        with self.bus.scope(self.level.scope_key):
            self.level.load()
        self._tick_acc = 0.0
        self.bus.update(self.now)

    @property
    def player(self):
        return self.level.player

    def step(self, dt: float = 0.01) -> None:
        """Advance `dt` seconds in 10 ms steps."""
        n = max(1, int(round(dt / 0.01)))
        for _ in range(n):
            self.now = round(self.now + 0.01, 6)
            self.bus.now = self.now
            self.level.monitors.advance(0.01)
            self._tick_acc += 0.01
            while self._tick_acc >= TICK - 1e-9:
                self._tick_acc -= TICK
                self.level.tick()
            self.bus.update(self.now)

    def run_until(self, pred, limit: float = 600.0, dt: float = 0.01) -> bool:
        end = self.now + limit
        while self.now < end:
            if pred():
                return True
            self.step(dt)
        return pred()

    # ---------------------------------------------------------- input
    def foot(self, foot: str) -> bool:
        self.interpreter.foot_pressed(foot)
        ok = self.interpreter.foot_released(foot)
        self.bus.update(self.now)
        return ok

    def hand(self, hand: str) -> bool:
        ok = self.interpreter.hand_pressed(hand)
        self.bus.update(self.now)
        return ok

    def clap(self) -> bool:
        ok = self.interpreter.hands_clapped()
        self.bus.update(self.now)
        return ok

    def turn(self, radians: float) -> bool:
        ok = self.interpreter.rotate_by(radians)
        self.bus.update(self.now)
        return ok

    def rotate(self, orientation) -> None:
        self.phone.rotate(orientation)
        self.bus.update(self.now)

    def shake(self) -> None:
        self.bus.post('PGE_ACTION_Shake', {})
        self.bus.update(self.now)

    def skip(self) -> None:
        self.bus.post('PGE_INPUT_DoubleTap', {})
        self.bus.update(self.now)

    # ---------------------------------------------------------- info
    def playing(self) -> list[str]:
        return sorted(s.name for s in self.bank.live_sounds() if s.playing)

    def played(self) -> list[str]:
        return [n for _, what, n in self.log if what == 'play']

    def sent(self, name: str) -> list[dict]:
        return [p for _, n, p in self.messages if n == name]
