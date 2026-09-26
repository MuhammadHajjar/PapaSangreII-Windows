"""Which recorded lines does nothing ever play?

Every speech file in the app bundle (a name with "SPEECH" in it) against every
name the 22 levels' data can reach - soundLists, sound keys, PlaySound and
PlaySpatialSound statements, inactivity lists - with the original's lookup
rules (an exact name, or any name starting with it; the VoiceOver `blind_`
take), plus the names the engine builds itself (deaths, trips, walls...).
What is left was recorded and never heard.

    python tools/unused_speech.py            -> a list, grouped by folder
"""

from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from papasangre2.assets.tiled import level_path   # noqa: E402
from papasangre2.util import paths                # noqa: E402

LEVELS = ['ps2_Intro'] + ['ps2_%s' % n for n in (
    '1', '2', '3', '4', '5', '5a', '6', '7', '8', '9', '10', '11a', '11b',
    '12', '13', '14', '15', '16', '17', '18', '18b')]

#: names the engine makes up itself (see the player, the game and the tutorial)
ENGINE = ['global_warning_trip', 'global_warning_hitwall', 'global_warning_walk_away',
          'blind_ps2_skip_tuto', 'ps2_skip_tuto']


def tokens(level: str) -> set[str]:
    """Every string the level's objects carry, split the way the data splits them."""
    doc = json.load(open(level_path(paths.game_bundle(), level), encoding='utf-8'))
    out: set[str] = set()

    def add(v):
        if not isinstance(v, str):
            return
        for stmt in v.split('|'):
            for part in re.split(r'[;:]', stmt):
                val = part.split('=', 1)[1] if '=' in part else part
                for t in val.split('&'):
                    t = t.strip()
                    if t:
                        out.add(t)

    for layer in doc.get('layers', []):
        for o in layer.get('objects', []) or []:
            props = o.get('properties', {})
            if isinstance(props, list):
                props = {p['name']: p.get('value') for p in props}
            for k, v in props.items():
                add(v)
            add(o.get('name'))
        props = doc.get('properties', {})
        if isinstance(props, dict):
            for v in props.values():
                add(v)
    return out


def speech_files() -> dict[str, str]:
    """stem -> path relative to sounds/"""
    base = os.path.join(paths.game_bundle(), 'sounds')
    out = {}
    for dp, _d, fs in os.walk(base):
        for f in fs:
            stem = os.path.splitext(f)[0]
            if 'speech' in stem.lower():
                out[stem] = os.path.relpath(os.path.join(dp, f), base).replace(os.sep, '/')
    return out


def reached(stem: str, refs: set[str]) -> bool:
    for r in refs:
        if stem.startswith(r) or stem.startswith('blind_' + r):
            return True
    return False


def requested_refs() -> set[str]:
    """The names Muhammad's additions play (papasangre2/world/requested.py and
    the waving lines in the player)."""
    from papasangre2.entities.player import WAVING       # noqa: PLC0415
    from papasangre2.world import requested as R          # noqa: PLC0415
    out: set[str] = set()
    for agents in R.AGENTS.values():
        for _k, _n, _x, _y, props, pairs in agents:
            out |= set(str(props.get('soundList', '')).split('&'))
            out |= {s.split('soundName=')[1].split(';')[0] for _t, s in pairs if 'soundName=' in s}
    for pairs in R.TRIGGERS.values():
        out |= {s.split('soundName=')[1].split(';')[0] for _t, s in pairs if 'soundName=' in s}
    out |= set(R.EXTRA_TAKES.values()) | set(R.RENAMES.values())
    out |= {v for v in R.INACTIVITY.values() if v}
    out |= {prefix for _kind, prefix, _n in WAVING.values()}
    return {r for r in out if r}


def unused(with_requested: bool = True) -> list[str]:
    refs: set[str] = set(ENGINE)
    for lv in LEVELS:
        refs |= {t for t in tokens(lv) if len(t) > 3}
    if with_requested:
        refs |= requested_refs()
    return sorted(s for s in speech_files() if not reached(s, refs))


def main() -> int:
    files = speech_files()
    unused_lines = unused('--original' not in sys.argv)
    trans = {}
    tpath = os.path.join(ROOT, 'build', 'transcripts', 'medium.en.json')
    if os.path.exists(tpath):
        for k, v in json.load(open(tpath, encoding='utf-8')).items():
            trans[os.path.splitext(os.path.basename(k))[0]] = v.get('text', '').strip()
    by_dir: dict[str, list[str]] = {}
    for s in unused_lines:
        by_dir.setdefault(os.path.dirname(files[s]), []).append(s)
    print(f'{len(files)} speech files, {len(unused_lines)} never played\n')
    for d in sorted(by_dir):
        print(f'== {d}')
        for s in by_dir[d]:
            print(f'   {s}: {trans.get(s, "")[:160]}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
