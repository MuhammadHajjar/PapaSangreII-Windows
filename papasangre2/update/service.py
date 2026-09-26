"""PORT ADDITION: the updater's network work on a worker thread.

The menus run on the main thread and poll this between frames; nothing here
speaks, plays a sound or touches a menu.  One job at a time: a check (is there
a newer release?) or an install (work out what changed, fetch it, stage it).
Every failure becomes a sentence in ``problem``; nothing escapes the thread.
"""

from __future__ import annotations

import threading

from . import updater
from .updater import UpdateError


class UpdateService:
    def __init__(self, check_url: str | None = None) -> None:
        self.check_url = check_url
        self.busy = False
        self.checked = False              # a check has finished this sitting
        self.release = None               # what the last check found
        self._lock = threading.Lock()
        self._result = None               # ('checked', release, problem) | ('installed', plan, problem)
        self._cancel = False
        self.done = 0
        self.total = 0

    # ---------------------------------------------------------------- jobs
    def check(self) -> bool:
        if self.busy:
            return False
        self.busy = True

        def work():
            found, problem = None, None
            try:
                found = updater.check(self.check_url)
            except UpdateError as exc:
                problem = str(exc)
            except Exception as exc:                          # noqa: BLE001 - never kill the game
                problem = 'something went wrong while checking (%s)' % exc
            updater.log('check result: %r %s' % (found, problem or ''))
            with self._lock:
                self._result = ('checked', found, problem)

        threading.Thread(target=work, name='update-check', daemon=True).start()
        return True

    def install(self, release) -> bool:
        if self.busy:
            return False
        self.busy = True
        self._cancel = False
        self.done, self.total = 0, max(1, int(release.asset_size or 1))

        def progress(done, total):
            self.done, self.total = done, max(1, total)

        def work():
            plan, problem = None, None
            try:
                plan = updater.build_plan(release, cancelled=lambda: self._cancel)
                self.total = max(1, plan.download_size)
                updater.download(plan, progress=progress, cancelled=lambda: self._cancel)
                if plan.nothing_to_do:
                    problem = 'this copy already has every file of that version'
                    plan = None
            except UpdateError as exc:
                problem = None if str(exc) == 'cancelled' else str(exc)
                plan = None
            except Exception as exc:                          # noqa: BLE001
                problem = 'something went wrong while downloading (%s)' % exc
                plan = None
            updater.log('install result: %s %s' % ('ready' if plan else 'none', problem or ''))
            with self._lock:
                self._result = ('installed', plan, problem)

        threading.Thread(target=work, name='update-download', daemon=True).start()
        return True

    def cancel(self) -> None:
        self._cancel = True

    # ---------------------------------------------------------------- polling
    def poll(self):
        """The finished job's result, once, or None while working (or idle)."""
        with self._lock:
            result, self._result = self._result, None
        if result is not None:
            self.busy = False
            if result[0] == 'checked':
                self.checked = True
                self.release = result[1]
        return result

    @property
    def percent(self) -> int:
        return int(100 * min(self.done, self.total) / max(1, self.total))
