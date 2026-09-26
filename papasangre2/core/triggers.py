"""`PGEObjectWithTriggers` as Papa Sangre II has it.

`-[PGEObjectWithTriggers triggerWithType:]` (0x100028268), for every trigger
whose type matches, compared upper-cased on both sides:

* `count`, when present: the trigger may fire only while `[count intValue] > 0`,
  and `count` is decremented **every** time the type fires, whether or not the
  trigger then fires (0x1000285e0-0x100028654);
* `afterCount`, when present: the trigger is held back while
  `[afterCount intValue] >= 1`, and `afterCount` is likewise decremented every
  time.  So `afterCount=N` first fires on the **(N+1)th** time - not the Nth
  (0x1000286c4 `cmp w21, #1; cset lt`);
* the parameters gain `senderName` and `position` (`NSStringFromCGPoint`);
* the delay is `afterDelay` if it is non-zero, otherwise, when both
  `minDelay` and `maxDelay` are non-zero, `min + (max - min) * rand() / 2^31`
  (0x100028cc4);
* with a delay above zero the statement goes into this object's own list of
  delayed triggers (`PGEDicoWithDelay`), otherwise it is enqueued on the idle
  queue as in PS1.

**Delays belong to the object** (PS2).  `-[PGEObjectWithTriggers update:]`
(0x100029088) subtracts the tick from each pending delay and enqueues the
ones that fell *below* zero - a delay of exactly 0.0 after subtraction waits
one more tick.  So a delay advances only while its owner's `update:` runs, and
`clearDicoWithDelayArray` throws them away (deactivation by name, dealloc,
level shutdown).  Which owners count down, and when, is each class's business:
agents always (the base `update:` runs before anything else), surfaces only
while active and not paused, the level through its own surface update.

Delays are kept in float32, as the original's `float delay` is, so a 1.0 s
delay at a 0.05 s tick fires exactly when the original's does.
"""

from __future__ import annotations

import random
from typing import Any

import numpy as np

from ..assets.tiled import Trigger, message_name, ns_float, ns_int
from .messages import MessageBus, Params

RAND_SCALE = np.float32(4.65661287e-10)          # 1 / 2^31, 0x100028370


def _pos_string(p: tuple[float, float]) -> str:
    """`NSStringFromCGPoint`: "{x, y}" with %g-style numbers."""
    return '{%s, %s}' % (_g(p[0]), _g(p[1]))


def _g(v: float) -> str:
    s = '%.17g' % v
    if 'e' not in s and '.' in s:
        s = s.rstrip('0').rstrip('.')
    return s


class _Delayed:
    __slots__ = ('trigger', 'delay')

    def __init__(self, trigger: Trigger, delay: np.float32):
        self.trigger = trigger
        self.delay = delay


class TriggerHost:
    """Mixin for anything in a level that owns triggers."""

    def __init__(self, bus: MessageBus, name: str = '',
                 position: tuple[float, float] = (0.0, 0.0),
                 rng: random.Random | None = None) -> None:
        self.bus = bus
        self.name = name
        self.position = position
        self.triggers: list[Trigger] = []
        #: Mutable per-trigger state: the original rewrites `count` and
        #: `afterCount` inside the trigger dictionary itself.
        self._count: list[int | None] = []
        self._after: list[int | None] = []
        self.delayed: list[_Delayed] = []           # dicoWithDelayArray
        self.rng = rng or random.Random()

    # ------------------------------------------------------------------
    def add_trigger(self, t: Trigger) -> None:
        self.triggers.append(t.clone())
        self._count.append(ns_int(t.count) if t.count is not None else None)
        self._after.append(ns_int(t.after_count) if t.after_count is not None else None)

    def add_triggers(self, ts) -> None:
        for t in ts:
            self.add_trigger(t)

    def has_trigger(self, trigger_type: str) -> bool:
        """`hasTriggerWithType:` - case-insensitive, like firing."""
        want = trigger_type.upper()
        return any(t.trigger_type.upper() == want for t in self.triggers)

    # ------------------------------------------------------------------
    def rand(self) -> int:
        """C `rand()`: 0 .. RAND_MAX (2^31 - 1 on iOS)."""
        return self.rng.randrange(0, 2 ** 31)

    def trigger(self, trigger_type: str) -> int:
        """`triggerWithType:`. Returns how many statements fired."""
        want = trigger_type.upper()
        fired = 0
        for i, t in enumerate(self.triggers):
            if t.trigger_type.upper() != want:
                continue
            ok = True
            c = self._count[i]
            if c is not None:
                ok = c > 0
                self._count[i] = c - 1
            a = self._after[i]
            if a is not None:
                ok = ok and a < 1
                self._after[i] = a - 1
            if not ok:
                continue
            params: Params = dict(t.parameters)
            params['senderName'] = self.name
            params['position'] = _pos_string(self.position)
            name = message_name(t.notification_name)
            delay = np.float32(ns_float(t.after_delay)) if t.after_delay is not None else np.float32(0)
            if delay == 0:
                lo = np.float32(ns_float(t.min_delay)) if t.min_delay is not None else np.float32(0)
                if lo != 0:
                    hi = np.float32(ns_float(t.max_delay)) if t.max_delay is not None else np.float32(0)
                    if hi != 0:
                        r = np.float32(self.rand()) * RAND_SCALE
                        delay = np.float32(lo + (hi - lo) * r)
            if delay > 0:
                fired_t = Trigger(t.trigger_type, name, params, raw=t.raw, key=t.key)
                self.delayed.append(_Delayed(fired_t, delay))
            else:
                self.bus.enqueue(name, params)
            fired += 1
        return fired

    # ------------------------------------------------------------------
    def update_delays(self, dt: float) -> int:
        """`-[PGEObjectWithTriggers update:]`: count down, enqueue the expired."""
        if not self.delayed:
            return 0
        step = np.float32(dt)
        due = []
        for d in self.delayed:
            d.delay = np.float32(d.delay - step)
            if d.delay < 0:
                due.append(d)
        for d in due:
            self.bus.enqueue(d.trigger.notification_name, dict(d.trigger.parameters))
        if due:
            self.delayed = [d for d in self.delayed if d not in due]
        return len(due)

    def clear_delays(self) -> int:
        """`clearDicoWithDelayArray`."""
        n = len(self.delayed)
        self.delayed = []
        return n

    def __repr__(self) -> str:
        return f'<{type(self).__name__} {self.name!r} @{self.position}>'


def addressed_to(params: Params, name: str, key: str = 'name') -> bool:
    """Is a broadcast message addressed to the object called ``name``?"""
    target = params.get(key)
    return bool(target) and target == name
