"""The sound monitors - `-[S3DEngineDispatcher dispatch_pump]`.

The original fires its monitors from a pump that re-arms itself with
`dispatch_after(9,999,999 ns)`: every 10 ms, on the main thread.  A PGESound's
fade-in steps its gain once per fire (the step is computed for 10 ms), the end
music is started 0.2 s before a sound's end, and a non-looping sound's end is
reported through a main-queue block.

A monitor is `fn(position, duration) -> stop`; returning True removes it.  An
end callback (`add3DSoundEndCallback:`) runs each time a looping sound wraps.
A sound stopped on purpose (`stop`) reports no end: the original's skip and
deactivate paths fire their own triggers, and the data relies on the end
trigger not following a skip (ps2_Intro's Intro0 has both).
"""

from __future__ import annotations

PERIOD = 0.01


class _Monitor:
    __slots__ = ('sound', 'fn', 'owner', 'last_pos', 'loop_cb')

    def __init__(self, sound, fn, owner, loop_cb=None):
        self.sound = sound
        self.fn = fn
        self.owner = owner
        self.last_pos = 0.0
        self.loop_cb = loop_cb


class MonitorPump:
    """Runs every sound monitor at 100 Hz of game time."""

    def __init__(self) -> None:
        self.monitors: list[_Monitor] = []
        self._acc = 0.0

    def add(self, sound, fn, owner=None) -> None:
        """`add3DSoundMonitor:` - one per sound; a new one replaces the old."""
        self.monitors = [m for m in self.monitors if m.sound is not sound or m.loop_cb]
        self.monitors.append(_Monitor(sound, fn, owner))

    def add_end_callback(self, sound, fn, owner=None) -> None:
        """`add3DSoundEndCallback:` - called at every loop end."""
        self.monitors = [m for m in self.monitors if m.sound is not sound or not m.loop_cb]
        self.monitors.append(_Monitor(sound, None, owner, loop_cb=fn))

    def remove_sound(self, sound) -> None:
        self.monitors = [m for m in self.monitors if m.sound is not sound]

    def remove_owner(self, owner) -> None:
        self.monitors = [m for m in self.monitors if m.owner is not owner]

    def clear(self) -> None:
        self.monitors.clear()
        self._acc = 0.0

    def advance(self, dt: float) -> int:
        """Fire the pump as many times as `dt` covers."""
        self._acc += dt
        n = 0
        while self._acc >= PERIOD - 1e-9:
            self._acc -= PERIOD
            self.fire()
            n += 1
        return n

    def fire(self) -> None:
        for m in list(self.monitors):
            if m not in self.monitors:
                continue
            s = m.sound
            if m.loop_cb is not None:
                if s.playing:
                    pos = s.offset
                    if pos + 1e-6 < m.last_pos:
                        m.loop_cb()
                    m.last_pos = pos
                continue
            if s.playing:
                pos = s.offset
                m.last_pos = pos
                if m.fn(pos, s.duration):
                    self._drop(m)
            elif getattr(s, 'ended', False):
                stop = m.fn(s.duration, s.duration)
                self._drop(m)
                del stop
            elif not getattr(s, 'paused', False):
                self._drop(m)             # stopped on purpose: no end

    def _drop(self, m) -> None:
        if m in self.monitors:
            self.monitors.remove(m)
