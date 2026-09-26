"""``PGEGameProgress`` - what the game remembers between runs.

A singleton over ``NSUserDefaults`` in the original.  There is no
``NSUserDefaults`` here, so the port writes a JSON file next to the executable,
but it keeps the original's **key names**, including their oddities, so the
saved state is a faithful record of what the engine tracks:

===========================  ==================================================
``<level>_completed``        bool - the level has been finished
``<level>_locked``           bool - **true means unlocked.**  The key reads
                             backwards; ``isLevelUnlocked:`` returns the value
                             as-is, so the name is simply wrong in the original
``lastLevelUnlocked``        string - written **only the first time** a level is
                             unlocked, so it records how far you have got rather
                             than the last level you happened to unlock again
``lastPLaylist``             string - the playlist in use.  The capital L is the
                             original's typo and is kept: change it and a save
                             written by the original would not be read back
``<sound name>``             bool - this narration has been heard once and may
                             now be skipped
``<dilemma id>``             bool - the choice made at that dilemma
===========================  ==================================================

``lastUnlockedLevel`` falls back to the first level of whichever game is
running: ``ps2_Intro`` for Papa Sangre II (``ps1_1`` / ``nightJar_1`` are the
same method's other branches).

Papa Sangre II adds ``tripTimes`` and ``wallTimes`` (the player's spoken
warnings play only for the first two of each in the whole game), ``<level>
_played`` / ``_failed``, ``lastLevelPlayed`` and the achievement keys.
"""

from __future__ import annotations

import json
import os
import shutil

from ..util import paths

#: -[PGEGameProgress lastUnlockedLevel] switches on PGEGameParameters.appName.
FIRST_LEVEL = {'Papa Sangre II': 'ps2_Intro', 'Papa Sangre': 'ps1_1',
               'The Nightjar': 'nightJar_1'}
DEFAULT_APP = 'Papa Sangre II'

LAST_UNLOCKED_KEY = 'lastLevelUnlocked'
LAST_PLAYLIST_KEY = 'lastPLaylist'          # the typo is the original's


class GameProgress:
    """Persistent progression, mirroring the original's defaults keys."""

    def __init__(self, path: str | None = None,
                 app_name: str = DEFAULT_APP) -> None:
        self.path = path or os.path.join(paths.config_dir(), 'progress.json')
        self.app_name = app_name
        self.values: dict[str, object] = {}
        self.load()

    # ------------------------------------------------------------ storage
    def load(self) -> 'GameProgress':
        """Read the save, falling back to the last known-good copy.

        An unreadable save used to mean an empty one, which is a whole
        playthrough gone for a file that may only be half written.  The backup
        is tried first instead, and only when neither can be read does the
        progress start over.

        A readable save is still topped up from the backup, because a save
        damaged by the bug 1.0.4 had can be missing keys the backup still
        holds - see :meth:`_adopt`.  Players were repairing that by hand, swapping
        ``progress.json.bak`` in for ``progress.json``; the game does it.
        """
        for candidate in (self.path, self.path + '.bak'):
            stored = self._read(candidate)
            if stored is None:
                continue          # a corrupt save must never stop the game
            self.values = stored
            if candidate == self.path:
                self._adopt(self._read(self.path + '.bak'))
            return self
        self.values = {}
        return self

    def synchronize(self) -> None:
        """``[NSUserDefaults synchronize]`` - write it out now.

        Written beside the save and moved into place, because opening the real
        file for writing truncates it first: anything that stopped the process
        in that window - and until 1.0.1 finishing the game stopped it right
        after a write - left a half-written save behind.  The previous file is
        kept as ``.bak`` so there is always one good copy on disk.

        Whatever the file already holds and this copy has never seen is taken
        in first, so a write can only ever add to the save - see
        :meth:`_adopt`.
        """
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            self._adopt(self._read(self.path))
            tmp = self.path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as fh:
                json.dump(self.values, fh, indent=2, sort_keys=True)
                fh.flush()
                os.fsync(fh.fileno())
            if os.path.exists(self.path):
                shutil.copyfile(self.path, self.path + '.bak')
            os.replace(tmp, self.path)
        except OSError:
            pass                  # a read-only install must still be playable

    @staticmethod
    def _read(path: str) -> dict | None:
        """The save at ``path``, or None if it is not there or not readable."""
        try:
            with open(path, encoding='utf-8') as fh:
                stored = json.load(fh)
        except (OSError, ValueError):
            return None
        return stored if isinstance(stored, dict) else None

    def _adopt(self, stored: dict | None) -> None:
        """Take in keys this copy has not seen.  What it holds always wins.

        Nothing is ever removed from the save - every key is written once and
        then only ever set again - so no other copy of it can hold anything
        this one is entitled to drop.  Reported after 1.0.4: "the levels
        aren't unlocked", with the unlocks sitting in ``progress.json.bak``
        and gone from ``progress.json``.  Two copies of the save were live at
        once and each rewrote the file with its own keys, so whichever wrote
        last threw the other's away.  They cannot now, and neither can a
        second copy of the game running beside this one.
        """
        for key, value in (stored or {}).items():
            self.values.setdefault(key, value)

    def _set(self, key: str, value) -> None:
        self.values[key] = value
        self.synchronize()

    def _bool(self, key: str) -> bool:
        return bool(self.values.get(key, False))

    # --------------------------------------------------------- completion
    def player_did_complete_level(self, name: str) -> None:
        self._set(f'{name}_completed', True)

    def is_level_completed(self, name: str) -> bool:
        return self._bool(f'{name}_completed')

    # ------------------------------------------------------------ unlocks
    def player_did_unlock_level(self, name: str) -> None:
        """``-[PGEGameProgress playerDidUnlockLevel:]``

        ``lastLevelUnlocked`` is written only when the level was not already
        unlocked, so replaying an early level does not wind your progress back.
        """
        if not self._bool(f'{name}_locked'):
            self.values[LAST_UNLOCKED_KEY] = name
        self._set(f'{name}_locked', True)

    def is_level_unlocked(self, name: str) -> bool:
        return self._bool(f'{name}_locked')

    @property
    def last_unlocked_level(self) -> str:
        stored = self.values.get(LAST_UNLOCKED_KEY)
        if isinstance(stored, str) and stored:
            return stored
        return FIRST_LEVEL.get(self.app_name, FIRST_LEVEL[DEFAULT_APP])

    # ---------------------------------------------------------- playlists
    def save_last_playlist(self, name: str) -> None:
        self._set(LAST_PLAYLIST_KEY, name)

    def get_last_playlist(self) -> str:
        stored = self.values.get(LAST_PLAYLIST_KEY)
        return stored if isinstance(stored, str) else ''

    # ------------------------------------------------- skippable narration
    def save_skippable_sound(self, key: str) -> None:
        """Heard once, so the player may skip it from now on."""
        if key:
            self._set(key, True)

    def can_skip_sound(self, key: str) -> bool:
        return self._bool(key)

    # ----------------------------------------------------------- dilemmas
    def save_dilemma_status(self, value: bool, dilemma_id: str) -> None:
        self._set(str(dilemma_id), bool(value))

    def get_dilemma_status(self, dilemma_id: str) -> bool:
        return self._bool(str(dilemma_id))

    # ------------------------------------------------ counters (PS2)
    @property
    def trip_times(self) -> int:
        return int(self.values.get('tripTimes', 0) or 0)

    @trip_times.setter
    def trip_times(self, n: int) -> None:
        self._set('tripTimes', int(n))

    @property
    def wall_times(self) -> int:
        return int(self.values.get('wallTimes', 0) or 0)

    @wall_times.setter
    def wall_times(self, n: int) -> None:
        self._set('wallTimes', int(n))

    def player_did_play_level(self, name: str) -> None:
        self.values['lastLevelPlayed'] = name
        self._set(f'{name}_played', True)

    def failed_level(self, name: str) -> int:
        """`failedLevel:` (0x1000391ac), from the lose screen's `checkFails`:
        how many times this level has killed you."""
        prev = self.values.get(f'{name}_failed', 0)
        try:
            n = int(prev) + 1 if prev else 1
        except (TypeError, ValueError):
            n = 1
        self._set(f'{name}_failed', n)
        return n

    # ------------------------------------------------ deaths and memories
    @property
    def memories_lost(self) -> int:
        return int(self.values.get('memoriesLost', 0) or 0)

    @memories_lost.setter
    def memories_lost(self, n: int) -> None:
        """`setMemoriesLost:` (0x100035204) - and the memoryLost achievement."""
        self.values['memoriesLost'] = int(n)
        self.submit_achievement('memoryLost', float(int(n)) / 24.0 * 100.0)

    def has_played_level_end_sound(self, name: str) -> bool:
        """`hasPlayedLevelEndSound:` - key ``<sound>_played``."""
        return self._bool(f'{name}_played')

    def just_played_level_end_sound(self, name: str) -> None:
        self._set(f'{name}_played', True)

    # -------------------------------------------------------- achievements
    @property
    def total_steps(self) -> int:
        return int(self.values.get('totalSteps', 0) or 0)

    @total_steps.setter
    def total_steps(self, n: int) -> None:
        """`setTotalSteps:` (0x1000370b0) - and the two step achievements."""
        self.values['totalSteps'] = int(n)
        self.submit_achievement('10000steps', float(int(n)) / 10000.0 * 100.0)
        self.submit_achievement('1000000steps', float(int(n)) / 84390.0 * 100.0)

    @property
    def total_kills(self) -> int:
        return int(self.values.get('totalKills', 0) or 0)

    @total_kills.setter
    def total_kills(self, n: int) -> None:
        """`setTotalKills:` (0x100036efc) - and kill25 / kil100 / kill500
        (the middle one misspelt in the original), in float32."""
        import numpy as np
        self._set('totalKills', int(n))
        f = np.float32(int(n))
        for ident, div in (('kill25', 25.0), ('kil100', 100.0), ('kill500', 500.0)):
            self.submit_achievement(ident, float(np.float32(np.float32(f / np.float32(div))
                                                            * np.float32(100.0))))

    def submit_achievement(self, identifier: str, percent: float) -> None:
        """What Game Center was told: the last percentage, capped at 100."""
        gc = dict(self.values.get('gameCenter') or {})
        if float(gc.get(identifier, 0.0)) >= 100.0:
            return                  # GameCenterManager: an earned one stays earned
        gc[identifier] = min(100.0, float(percent))
        self._set('gameCenter', gc)

    def game_center_percent(self, identifier: str) -> float:
        return float((self.values.get('gameCenter') or {}).get(identifier, 0.0))

    def set_percentage_for_achievement(self, percent: int, name: str) -> None:
        """`setPercentage:forAchievementWithName:` (0x100038c94)."""
        self.submit_achievement(name, float(percent))
        if int(percent) == 100:
            self._set(name, True)

    def achievement_completed(self, name: str) -> bool:
        """`achievementCompleted:` - Game Center first, then the stored bool."""
        return self._bool(name) or self.game_center_percent(name) >= 100.0

    def __repr__(self) -> str:
        return f'<GameProgress {len(self.values)} keys at {self.path!r}>'


class InMemoryProgress(GameProgress):
    """The same save, kept in memory only - for the simulator and the tests."""

    def __init__(self, app_name: str = DEFAULT_APP) -> None:
        self.path = ''
        self.app_name = app_name
        self.values = {}

    def load(self) -> 'GameProgress':
        return self

    def synchronize(self) -> None:
        pass
