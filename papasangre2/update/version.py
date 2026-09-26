"""PORT ADDITION: which build this is, and which of two builds is newer.

The version is a date, and "number N" when a day has more than one build:
``2026-09-26``, ``2026-09-26 number 2``.  It is written in
``papasangre2/__init__.py`` (and ``VERSION``, and the newest heading of
``changelog.txt`` - a test holds the three together), so a frozen build
carries it compiled in: nothing beside the exe can be edited or deleted to
change what the game thinks it is.

A release's tag is the same thing without spaces - ``2026-09-26-2`` - because
a git tag cannot hold one.  Comparison reads only the digits, so the two
spellings compare alike, and a version without a number is the day's first:
``2026-09-26`` is older than ``2026-09-26 number 2``.  A version holding no
digits is unknown, and an unknown version is never offered an update.
"""

from __future__ import annotations

from .. import __version__


def current() -> str:
    """This build's version."""
    return str(__version__ or '').strip()


def parse(version: str) -> tuple:
    """'2026-09-26 number 2' and '2026-09-26-2' both -> (2026, 9, 26, 2)."""
    digits, number, seen = [], 0, False
    for ch in str(version or ''):
        if ch.isdigit():
            number, seen = number * 10 + int(ch), True
        elif seen:
            digits.append(number)
            number, seen = 0, False
    if seen:
        digits.append(number)
    return tuple(digits)


def is_newer(remote: str, local: str) -> bool:
    """Is ``remote`` a later build than ``local``?  Unknown compares as not newer."""
    a, b = parse(remote), parse(local)
    if len(a) < 3 or len(b) < 3:
        return False
    width = max(len(a), len(b))
    return a + (0,) * (width - len(a)) > b + (0,) * (width - len(b))


def tag(version: str | None = None) -> str:
    """The release tag for a version: '2026-09-26 number 2' -> '2026-09-26-2'."""
    parts = parse(current() if version is None else version)
    if len(parts) < 3:
        return ''
    out = '%04d-%02d-%02d' % parts[:3]
    return out + ('-%d' % parts[3] if len(parts) > 3 else '')


def text(version: str | None = None) -> str:
    """What a screen reader says: '2026-09-26 number 2' for either spelling."""
    parts = parse(current() if version is None else version)
    if len(parts) < 3:
        return 'unknown'
    out = '%04d-%02d-%02d' % parts[:3]
    return out + (' number %d' % parts[3] if len(parts) > 3 else '')
