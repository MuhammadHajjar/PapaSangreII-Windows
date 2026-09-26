"""The message bus - the port's ``NSNotificationCenter`` / ``NSNotificationQueue``.

Papa Engine is built entirely on broadcast messages.  A trigger does not look
up its target; it posts ``PGE_MESSAGE_ActivateAgentWithName`` with a ``name``
parameter, every agent in the level receives it, and each one decides for itself
whether the name matches.  That is why several triggers in the shipped data name
agents that do not exist and simply do nothing (GAME_STRUCTURE.md section 11) -
reproducing the broadcast reproduces those no-ops for free.

Three delivery paths, matching the original:

``post``
    Immediate, synchronous - ``postNotificationName:object:``.  Used by the
    engine itself (player moved, sound ended, state changed).

``enqueue``
    Deferred until the next drain - ``enqueueNotification:postingStyle:`` with
    ``NSPostWhenIdle`` (recovered: ``mov w3, #1`` before the call in
    ``-[PGEObjectWithTriggers triggerWithType:]``).  Every trigger statement
    without an ``afterDelay`` goes through here, so trigger effects land after
    the current update finishes rather than re-entering it.

``post_after``
    ``performSelector:withObject:afterDelay:`` - a trigger's ``afterDelay``.
    Cancellable by token, which the original relies on when it cancels a pending
    ``changeState:`` on every step.

Two more run-loop paths carry code rather than messages:

``dispatch_async``
    ``dispatch_async(dispatch_get_main_queue(), ^{...})`` - the block runs on
    the next pass of the run loop, **before** the idle notification queue
    (a main-queue block is a run-loop source; ``NSPostWhenIdle`` waits until
    the loop has nothing else to do).  PS2 uses it for agent activation and
    for sound-end callbacks.

``call_after``
    ``performSelector:withObject:afterDelay:`` / ``dispatch_after`` with a
    callable.  Cancellable by token like ``post_after``.

Note on coalescing: ``enqueueNotification:postingStyle:`` coalesces on name and
sender, but the sender here is a freshly built parameter dictionary each time,
so two enqueued messages are never identical objects and nothing is ever merged.
The port therefore delivers every enqueued message, in order.
"""

from __future__ import annotations

import contextlib
import itertools
from dataclasses import dataclass, field
from typing import Any, Callable

Params = dict[str, Any]
Handler = Callable[[str, Params], None]


@dataclass(order=True)
class _Delayed:
    due: float
    seq: int
    name: str | None = field(compare=False)
    params: Params = field(compare=False, default_factory=dict)
    token: Any = field(compare=False, default=None)
    cancelled: bool = field(compare=False, default=False)
    fn: Callable[[], None] | None = field(compare=False, default=None)


class MessageBus:
    """Broadcast bus with immediate, deferred and delayed delivery."""

    def __init__(self) -> None:
        self._subs: dict[str | None, list[Handler]] = {}
        self._queue: list[tuple[str, Params]] = []
        self._async: list[Callable[[], None]] = []
        self._delayed: list[_Delayed] = []
        self._seq = itertools.count()
        self.now = 0.0
        #: Every message delivered, for tests and the debug log.
        self.trace: list[tuple[float, str, Params]] = []
        self.trace_enabled = False
        #: Subscriptions made inside `scope(key)` are dropped together - a
        #: level's objects go when the level goes, as their dealloc did.
        self._scope = None
        self._scoped: dict[object, list[tuple[str | None, Handler]]] = {}

    # ---------------------------------------------------------------- subs
    def subscribe(self, name: str | None, handler: Handler) -> Handler:
        """Listen for one message name, or for all of them when ``name`` is None."""
        self._subs.setdefault(name, []).append(handler)
        if self._scope is not None:
            self._scoped.setdefault(self._scope, []).append((name, handler))
        return handler

    @contextlib.contextmanager
    def scope(self, key):
        """Tag every subscription made inside the block with ``key``."""
        old, self._scope = self._scope, key
        try:
            yield
        finally:
            self._scope = old

    def drop_scope(self, key) -> int:
        """Unsubscribe everything subscribed inside ``scope(key)``."""
        n = 0
        for name, handler in self._scoped.pop(key, []):
            lst = self._subs.get(name)
            if lst and handler in lst:
                lst.remove(handler)
                n += 1
        return n

    def unsubscribe(self, name: str | None, handler: Handler) -> None:
        lst = self._subs.get(name)
        if lst and handler in lst:
            lst.remove(handler)

    def unsubscribe_all(self, handler: Handler) -> None:
        for lst in self._subs.values():
            while handler in lst:
                lst.remove(handler)

    # ------------------------------------------------------------ delivery
    def post(self, name: str, params: Params | None = None) -> None:
        """Immediate, synchronous broadcast."""
        params = params if params is not None else {}
        if self.trace_enabled:
            self.trace.append((self.now, name, dict(params)))
        # Copy the handler lists: a handler may subscribe or unsubscribe.
        for handler in list(self._subs.get(name, ())):
            handler(name, params)
        for handler in list(self._subs.get(None, ())):
            handler(name, params)

    def enqueue(self, name: str, params: Params | None = None) -> None:
        """Deferred broadcast, delivered by the next :meth:`drain`."""
        self._queue.append((name, dict(params or {})))

    def post_after(self, delay: float, name: str,
                   params: Params | None = None, token: Any = None) -> _Delayed:
        """Broadcast after ``delay`` seconds of game time."""
        entry = _Delayed(self.now + max(0.0, delay), next(self._seq),
                         name, dict(params or {}), token)
        self._delayed.append(entry)
        return entry

    def dispatch_async(self, fn: Callable[[], None]) -> None:
        """A main-queue block: runs at the next drain, before the idle queue."""
        self._async.append(fn)

    def call_after(self, delay: float, fn: Callable[[], None],
                   token: Any = None) -> _Delayed:
        """Run ``fn`` after ``delay`` seconds of game time."""
        entry = _Delayed(self.now + max(0.0, delay), next(self._seq),
                         None, {}, token, fn=fn)
        self._delayed.append(entry)
        return entry

    # ------------------------------------------------------------- control
    @staticmethod
    def _refers_to(fn, obj) -> bool:
        """``fn`` is one of ``obj``'s methods, or a closure over ``obj``."""
        if getattr(fn, '__self__', None) is obj:
            return True
        for cell in getattr(fn, '__closure__', None) or ():
            try:
                if cell.cell_contents is obj:
                    return True
            except ValueError:
                pass
        return False

    def cancel_owner(self, obj) -> int:
        """``cancelPreviousPerformRequestsWithTarget:obj`` - every pending
        delayed call that belongs to ``obj``."""
        n = 0
        for e in self._delayed:
            if not e.cancelled and e.fn is not None and self._refers_to(e.fn, obj):
                e.cancelled = True
                n += 1
        return n

    def forget(self, obj) -> int:
        """Unsubscribe everything ``obj`` listens with - what its ``dealloc``
        does with the notification centre."""
        n = 0
        for lst in self._subs.values():
            keep = [h for h in lst if not self._refers_to(h, obj)]
            n += len(lst) - len(keep)
            lst[:] = keep
        return n

    def cancel(self, token: Any) -> int:
        """Cancel pending delayed messages carrying ``token``.

        Mirrors ``cancelPreviousPerformRequestsWithTarget:selector:object:``,
        which the player uses on every step to cancel its pending 'stopped
        moving' state change.
        """
        n = 0
        for e in self._delayed:
            if not e.cancelled and e.token is not None and e.token == token:
                e.cancelled = True
                n += 1
        return n

    def cancel_name(self, name: str) -> int:
        n = 0
        for e in self._delayed:
            if not e.cancelled and e.name == name:
                e.cancelled = True
                n += 1
        return n

    def clear(self) -> None:
        """Drop everything pending - used when a level shuts down."""
        self._queue.clear()
        self._async.clear()
        self._delayed.clear()

    # -------------------------------------------------------------- update
    def drain(self, limit: int = 10000) -> int:
        """Deliver everything enqueued, including anything they enqueue.

        The original's run loop keeps servicing the notification queue until it
        is empty before going idle, so a trigger that enqueues another trigger
        still resolves within the same idle pass.  ``limit`` only guards against
        a runaway cycle in malformed data.
        """
        delivered = 0
        while (self._queue or self._async) and delivered < limit:
            while self._async and delivered < limit:
                blocks, self._async = self._async, []
                for fn in blocks:
                    fn()
                    delivered += 1
            if self._queue:
                batch, self._queue = self._queue, []
                for name, params in batch:
                    self.post(name, params)
                    delivered += 1
        return delivered

    def update(self, now: float) -> int:
        """Advance to ``now``: fire due delayed messages, then drain the queue."""
        self.now = now
        if self._delayed:
            due = [e for e in self._delayed if not e.cancelled and e.due <= now]
            if due:
                due.sort()
                self._delayed = [e for e in self._delayed
                                 if not e.cancelled and e.due > now]
                for e in due:
                    if e.cancelled:          # cancelled by an earlier one here
                        continue
                    # Delayed messages are delivered **directly**, not queued:
                    # performSelector:afterDelay: calls its method inline.
                    if e.fn is not None:
                        e.fn()
                    else:
                        self.post(e.name, e.params)
            else:
                self._delayed = [e for e in self._delayed if not e.cancelled]
        return self.drain()

    # ---------------------------------------------------------------- info
    @property
    def pending(self) -> int:
        return len(self._queue) + len(self._async)

    @property
    def scheduled(self) -> int:
        return sum(1 for e in self._delayed if not e.cancelled)
