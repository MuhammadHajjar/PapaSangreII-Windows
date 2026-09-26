"""Sounds made for the port at the owner's request (REQUESTED) - not in the original app.

They live in ``requested/sounds/`` in the source tree and travel inside the
frozen game as ``gamedata/requested_sounds/``.  Each is added to every level's
bank under its own name, so the code that plays one asks for it by name and
falls back to the original's sound when it is not there.
"""

from __future__ import annotations

import os

from ..util import paths
from . import pack

#: name -> (file, spatialized).  The names start "requested_" so no lookup by
#: prefix the level data makes (``penguin_death`` ...) can land on one.
SOUNDS = {
    # decision 18 (2026-09-25): a penguin killed with the knife - the
    # original's penguin death with a stab in it
    'requested_penguin_death_stab': ('penguin_death_stab.wav', True),
    # decision 19 (2026-09-25): a trip on glass, which the original has none
    # for - candidate 1 of tools/make_glass_trip.py (the game's glass scuff, a
    # bodyfall from Muhammad's library with broken glass under it, the glass
    # settling), the one he chose; stereo like the glass steps.  Found by the
    # player's trip lookup (anySoundContaining: "trip_glass").
    'requested_trip_glass': ('trip_glass.wav', False),
}

PENGUIN_STAB_DEATH = 'requested_penguin_death_stab'


def sound_path(file: str) -> str | None:
    for base in (paths.game_audio('requested_sounds'),
                 paths.resource('requested', 'sounds')):
        p = os.path.join(base, file)
        if pack.isfile(p):
            return p
    return None


def add_to(bank) -> int:
    """Declare every requested sound in a level's bank; returns how many."""
    if bank is None or not hasattr(bank, 'add_file'):
        return 0
    n = 0
    for name, (file, spatialized) in SOUNDS.items():
        p = sound_path(file)
        if p is not None and bank.add_file(name, p, spatialized):
            n += 1
    return n
