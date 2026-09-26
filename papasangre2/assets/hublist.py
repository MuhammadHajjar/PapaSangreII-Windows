"""``levels/papasangre2_hubList.plist`` - the level menu, as the original shipped it.

``-[AccessibleAllLevelsViewController viewDidLoad]`` loads
``papasangre2_hubList.plist`` from the bundle's ``levels/`` directory and
builds its table from it, one row per entry, ordered by ``positionInMenu``.
Each row is spoken with one of the two formats in that class:

* ``"Play Level %i: %@"`` when the level is unlocked
* ``"Level %i: %@; locked"`` when it is not

and the name used is ``altName`` (in Papa Sangre II the same as ``title``).
The entries also carry the objectives ``text1`` / ``text2`` / ``text3`` that
``SetPauseText`` reads, the win screen's ``successText`` and the level's
``achievement``.

The plist's own ``unlocked`` flag is only the **starting** state: level 1 is
true and every other level is false.  What is actually unlocked at runtime
comes from ``PGEGameProgress``, which is why this module takes a progress
object rather than trusting the file.
"""

from __future__ import annotations

import os
import plistlib

from . import pack

#: Nothing is hidden: the 22 entries are exactly the playable levels.  ps2_11,
#: the cut level, is simply not in the file.
HIDDEN: tuple[str, ...] = ()


class LevelEntry:
    """One row of the level menu."""

    __slots__ = ('file_name', 'alt_name', 'title', 'position', 'unlocked_by_default',
                 'texts', 'success_text', 'achievement', 'next_level', 'cannot_skip')

    def __init__(self, file_name: str, alt_name: str, title: str,
                 position: int, unlocked_by_default: bool, texts=None,
                 success_text: str = '', achievement=None, next_level: str = '',
                 cannot_skip: bool = False) -> None:
        self.file_name = file_name
        self.alt_name = alt_name
        self.title = title
        self.position = position
        self.unlocked_by_default = unlocked_by_default
        #: text1, text2, text3 by name - what SetPauseText:name=textN shows
        self.texts: dict[str, str] = dict(texts or {})
        self.success_text = success_text
        self.achievement: dict = dict(achievement or {})
        self.next_level = next_level
        self.cannot_skip = cannot_skip

    def is_unlocked(self, progress=None) -> bool:
        """Level 1 always; anything else only once progress says so."""
        if self.unlocked_by_default:
            return True
        if progress is None:
            return False
        return bool(progress.is_level_unlocked(self.file_name))

    def spoken(self, progress=None) -> str:
        """Exactly the two formats in AccessibleAllLevelsViewController."""
        if self.is_unlocked(progress):
            return f'Play Level {self.position}: {self.alt_name}'
        return f'Level {self.position}: {self.alt_name}; locked'

    def __repr__(self) -> str:
        return f'<LevelEntry {self.position} {self.file_name} {self.alt_name!r}>'


def load_hub_list(bundle_dir: str, list_name: str = 'papasangre2') -> list[LevelEntry]:
    """Read ``levels/<list_name>_hubList.plist`` into menu order."""
    path = os.path.join(bundle_dir, 'levels', f'{list_name}_hubList.plist')
    try:
        raw = plistlib.loads(pack.read_bytes(path))
    except (OSError, ValueError, plistlib.InvalidFileException):
        return []
    entries = []
    for value in (raw or {}).values():
        if not isinstance(value, dict):
            continue
        file_name = str(value.get('fileName', '')).strip()
        if not file_name or file_name in HIDDEN:
            continue
        try:
            position = int(value.get('positionInMenu', 0))
        except (TypeError, ValueError):
            position = 0
        entries.append(LevelEntry(
            file_name=file_name,
            alt_name=str(value.get('altName', file_name)),
            title=str(value.get('title', '')),
            position=position,
            unlocked_by_default=bool(value.get('unlocked', False)),
            texts={k: str(v) for k, v in value.items() if k.startswith('text')},
            success_text=str(value.get('successText', '')),
            achievement=value.get('achievement') or {},
            next_level=str(value.get('nextLevel', '')),
            cannot_skip=bool(value.get('cannotSkip', False)),
        ))
    entries.sort(key=lambda e: (e.position, e.file_name))
    return entries
