"""Inventory of every audio file in Papa Sangre II and everything that can play it.

    python inventory.py      -> docs/SOUND_INVENTORY.md and docs/sound_inventory.csv

Sources of a reference, each resolved the way the engine resolves it:

* level data - every property and trigger parameter that names a sound, looked
  up in that level's playlist closure (the level playlist plus its nested
  includes).  Exact name first (`S3DSound:`), then prefix
  (`anySoundWihPrefix:`), which is what most engine paths fall back to;
  a prefix that matches several sounds is flagged, because the engine picks
  one at random.
* footstep banks - `footstepsPrefix` p gives `footwalk_p`, `footrun_p`,
  `trip_p` and `throw_p` (moveForwardOneStep:, trip:, throwSomething).
* the binary - literal sound names and the format strings that build them
  (`%@_end_music_loop`, `%@_fail_%@`, `lost_memory_%i_UOS`, ...), each
  expanded over the 23 shipped levels and the death causes in the data.

A file nobody reaches is listed as such; it is not proof nothing plays it -
it is the list to go and check by hand.
"""
import csv
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
APP = ROOT / 'reference' / 'Payload' / 'Papa Sangre II.app'
sys.path.insert(0, str(ROOT))
from papasangre2.assets.sexp import parse_playlist, include_stem  # noqa: E402

# property keys that hold sound names (found by matching every value in the
# 42 maps against the audio files; agent-name keys that merely collide with a
# sound prefix are excluded)
SOUND_PROPS = {
    'soundList', 'introSound', 'loopSound', 'collectSound', 'chaseSound',
    'patrolSound', 'stillSound', 'awareSound', 'notThereSound', 'attackSound',
    'shotSound', 'beatenSound', 'beatRangeSound', 'proximitySound',
    'scaredSound', 'pauseSound', 'deathSound', 'followerAlertSound', 'sound',
    'clapSound', 'shootSound', 'beatSound', 'jumpSound', 'drowningSound',
    'gaggingSound', 'inactivitySounds', 'hitWallSound', 'tripSound',
    'shuffleSound', 'defaultSound', 'litSound', 'goOffSound', 'aboutToGoSound',
    'emptyLeftHandSound', 'emptyRightHandSound',
}
SOUND_PARAMS = {('PlaySound', 'soundName'), ('PlaySpatialSoundOnAgentWithName', 'soundName'),
                ('ChangeInactivitySoundList', 'soundList')}

# names and patterns built in code (addresses in GAME_STRUCTURE.md / notes)
BINARY_LITERALS = {
    'hitwall': '-[PGELevel init] setHitWallSound: / -[PGEPlayer playerDidCollideAWall:] anySoundWihPrefix:',
    'global_warning_hitwall': '-[PGEPlayer playerDidCollideAWall:] anySoundContaining:',
    'global_warning_trip': '-[PGEPlayer trip:]',
    'stab_missed': '-[PGEPlayer init] setBeatSound: (default)',
    'agony_SPA': '-[PGEEnemy init] setShotSound: (default)',
    'hey_SPA': '-[PGEEnemy init] setAwareSound: (default)',
    'stab_and_death': '-[PGEEnemy init] setBeatenSound: (default)',
    'menu_death_atmos': '-[PGEngine playMenuAtmos] / playMenuDeathAtmos',
    'papa_engine_splash_UOS': '-[PGEViewController] splash',
    'click_button': '-[PGEngine playUiSoundWithName:] callers',
    'back_button': '-[PGEngine playUiSoundWithName:] callers',
    'skipButtonAppeared': '-[PGEStepsViewController showSkipButton]',
    'start_level_button': '-[PGEHubSelectorViewControllerViewController]',
    '18_SPEECH_papa_picture_retreat_': '-[PGESound createSpatializedSound] prefix + picturesTaken',
    '4_papa_': '-[PGEEnemy wasBeaten] name prefix + picturesTaken',
}
DEATH_CAUSES = set()


def audio_files():
    files = {}
    for root, _, fs in os.walk(APP / 'sounds'):
        for f in fs:
            if f.endswith(('.m4a', '.mp3', '.wav', '.caf')):
                p = Path(root) / f
                rel = p.relative_to(APP).as_posix()
                files[rel] = p.stem
    return files


def load_playlists():
    pls = {}
    for f in (APP / 'meta' / 'S3DPlayListModel').glob('*.sexp'):
        pl = parse_playlist(f.read_text(encoding='utf-8', errors='replace'), f.name)
        pls[f.name.split('.S3DPlayListModel')[0]] = pl
    return pls


def closure(pls, name, seen=None):
    seen = seen if seen is not None else []
    if name in seen or name not in pls:
        return seen
    seen.append(name)
    for inc in pls[name].includes:
        closure(pls, include_stem(inc), seen)
    return seen


def main():
    files = audio_files()
    by_stem = defaultdict(list)
    for rel, stem in files.items():
        by_stem[stem].append(rel)
    pls = load_playlists()

    # declarations: playlist -> {sound name: bundle path}
    declared_in = defaultdict(set)       # file rel path -> playlists
    decl_missing = []                    # (playlist, name, path) that has no file
    for pname, pl in pls.items():
        for s in pl.sounds:
            rel = s.bundle_path
            if rel in files:
                declared_in[rel].add(pname)
            else:
                decl_missing.append((pname, s.name, rel))

    def names_in(level):
        """sound name -> file, over the level playlist closure."""
        out = {}
        for p in closure(pls, level):
            for s in pls[p].sounds:
                out.setdefault(s.name, s.bundle_path)
        return out

    refs = defaultdict(list)             # file -> [(scope, where, how)]
    problems = []                        # unresolved / ambiguous

    def resolve(level, scope, where, raw, how_hint='prefix'):
        pool = names_in(level)
        raw = raw.strip()
        if not raw:
            return
        if raw in pool:
            hit = [raw]
            tag = 'exact'
        else:
            hit = sorted(n for n in pool if n.startswith(raw))
            tag = 'prefix' if len(hit) == 1 else 'prefix x%d (random)' % len(hit)
        if hit:
            for n in hit:
                if pool[n] in files:
                    refs[pool[n]].append((scope, where, tag))
                else:
                    problems.append((scope, level, where, n,
                                     'declared as `%s`, which does not exist' % pool[n]))
            return
        # not in the level's playlists: does a file exist anywhere?
        anywhere = [rel for st, rels in by_stem.items() if st == raw or st.startswith(raw) for rel in rels]
        problems.append((scope, level, where, raw,
                         'file exists but not in this level\'s playlists: ' + ', '.join(anywhere[:3])
                         if anywhere else 'no such sound'))

    level_files = sorted((APP / 'levels').glob('*/*.json'))
    shipped = {f.stem for f in (APP / 'levels' / 'papasangre2').glob('*.json')}
    for f in level_files:
        lv = f.stem
        scope = 'level' if f.parent.name == 'papasangre2' else 'experiment'
        d = json.loads(f.read_text(encoding='utf-8'))
        for L in d['layers']:
            for o in L.get('objects') or []:
                props = o.get('properties') or {}
                oname = o.get('name') or o.get('type') or '?'
                for k, v in props.items():
                    where = '%s:%s.%s' % (lv, oname, k)
                    if k in SOUND_PROPS:
                        for part in re.split(r'[&]', str(v)):
                            resolve(lv, scope, where, part)
                    elif k == 'footstepsPrefix' and v:
                        pool = names_in(lv)
                        for pat in ('footwalk_%s', 'footrun_%s', 'trip_%s', 'throw_%s'):
                            key = pat % v
                            hit = [n for n in pool if n.startswith(key)]
                            for n in hit:
                                if pool[n] in files:
                                    refs[pool[n]].append((scope, where, pat.split('%')[0] + '*'))
                                else:
                                    problems.append((scope, lv, where, n, 'declared as `%s`, which does not exist' % pool[n]))
                            if not hit and pat.startswith('footwalk'):
                                problems.append((scope, lv, where, key, 'no footwalk bank for this prefix'))
                    elif k.startswith('On'):
                        for st in str(v).split('|'):
                            parts = st.split(':', 1)
                            if len(parts) != 2:
                                continue
                            msg = parts[0].strip().replace('PGE_MESSAGE_', '')
                            for kv in parts[1].split(';'):
                                if '=' not in kv:
                                    continue
                                pk, pv = [x.strip() for x in kv.split('=', 1)]
                                if pk == 'deathCause':
                                    DEATH_CAUSES.add(pv)
                                if (msg, pk) in SOUND_PARAMS:
                                    for part in pv.split('&'):
                                        resolve(lv, scope, where + '>' + msg, part)
                    if k == 'deathCause' and v:
                        DEATH_CAUSES.add(str(v))

    # the menu playlist and code-built names
    menu = names_in('ps2_menu')
    for name, rel in menu.items():
        for lv in shipped:
            if name.startswith(lv + '_fail') or name == lv + '_end_music_loop':
                refs[rel].append(('binary', 'PGEngine end/fail sound for ' + lv,
                                  '%@_fail[_%@] / %@_end_music_loop'))
        if re.match(r'lost_memory_\d+_UOS$', name):
            refs[rel].append(('binary', 'PGEngine playFailSoundForLevel:', 'lost_memory_%i_UOS'))
    for lit, where in BINARY_LITERALS.items():
        for st, rels in by_stem.items():
            if st == lit or (lit.endswith('_') and st.startswith(lit)) or st.startswith(lit + '_'):
                for rel in rels:
                    refs[rel].append(('binary', where, 'literal'))
    for st, rels in by_stem.items():
        if st.startswith('blind_'):
            for rel in rels:
                refs[rel].append(('binary', '-[PGESound createSpatializedSound] blind_%@ when VoiceOver runs', 'blind_%@'))

    live_pls = set()
    for lv in list(shipped) + ['ps2_menu']:
        live_pls.update(closure(pls, lv))
    decl_missing_live = [d for d in decl_missing if d[0] in live_pls]
    for name, rel in menu.items():
        if rel not in files:
            decl_missing_live.append(('ps2_menu', name, rel))

    # ---- report
    shipped_files = {r for r, xs in refs.items() if r in files and any(s in ('level', 'binary') for s, _, _ in xs)}
    exp_only = {r for r, xs in refs.items() if r in files and r not in shipped_files}
    unref = [r for r in files if r not in refs]
    out = ['# Papa Sangre II - sound inventory\n',
           'Generated by `tools/inventory.py`. Every audio file in the app, where it is '
           'declared, and what can play it. This is the checklist: a file is **ported** '
           'only when the port plays it from the same trigger.\n',
           '## Totals\n',
           '| | files |', '|---|---|',
           '| audio files in `sounds/` | %d (%d m4a, %d mp3) |' % (
               len(files), sum(1 for r in files if r.endswith('.m4a')), sum(1 for r in files if r.endswith('.mp3'))),
           '| declared by at least one playlist | %d |' % len(declared_in),
           '| reachable from a shipped level or from code | %d |' % len(shipped_files),
           '| reachable only from developer test maps | %d |' % len(exp_only),
           '| referenced by nothing found yet | %d |' % len(unref),
           '| playlist declarations naming a file that does not exist (all 200 playlists) | %d |' % len(decl_missing),
           '| ... of which in a playlist a shipped level or the menu loads | %d |' % len(sorted(set(decl_missing_live))),
           '| unresolved references in shipped level data | %d |' % sum(1 for p in problems if p[0] == 'level'),
           '| unresolved references in test maps | %d |' % sum(1 for p in problems if p[0] != 'level'),
           '',
           'Death causes seen in the data: %s\n' % ', '.join(sorted(DEATH_CAUSES)),
           '## Referenced by nothing found yet\n',
           'Each of these needs a reason: dead content, an unread code path, or a '
           'lookup rule this script does not model.\n']
    for r in sorted(unref):
        out.append('* `%s` - declared in: %s' % (r, ', '.join(sorted(declared_in.get(r, []))) or 'no playlist'))
    out.append('\n## Shipped-level references that do not resolve\n')
    out.append('In the original each of these plays nothing. They are candidates for the '
               '"original data defect" list; each must be checked against the lookup the '
               'engine really uses for that key before it is called one.\n')
    out.append('| level | where | name | why |')
    out.append('|---|---|---|---|')
    for p in sorted(set(problems)):
        if p[0] == 'level':
            out.append('| %s | `%s` | `%s` | %s |' % p[1:])
    out.append('\n## Declarations in live playlists with no file\n')
    for p in sorted(set(decl_missing_live)):
        out.append('* `%s` declares `%s` -> `%s`' % p)
    out.append('\n## Test-map references that do not resolve\n')
    out.append('Developer maps, not shipped; listed for completeness.\n')
    for p in sorted(set(problems)):
        if p[0] != 'level':
            out.append('* %s `%s` `%s`: %s' % p[1:])
    out.append('\n## Every file\n')
    out.append('| file | playlists | shipped levels / code | test maps only |')
    out.append('|---|---|---|---|')
    rows = []
    for r in sorted(files):
        xs = refs.get(r, [])
        live = sorted({'%s (%s)' % (w, h) for s, w, h in xs if s in ('level', 'binary')})
        exp = sorted({'%s' % w for s, w, h in xs if s == 'experiment'})
        pl = sorted(declared_in.get(r, []))
        out.append('| `%s` | %s | %s | %s |' % (
            r, ', '.join(pl[:6]) + (' +%d' % (len(pl) - 6) if len(pl) > 6 else ''),
            '<br>'.join(live[:8]) + (' <br>+%d more' % (len(live) - 8) if len(live) > 8 else ''),
            ', '.join(exp[:4]) + (' +%d' % (len(exp) - 4) if len(exp) > 4 else '')))
        rows.append([r, ';'.join(pl), ';'.join(live), ';'.join(exp)])
    (ROOT / 'docs' / 'SOUND_INVENTORY.md').write_text('\n'.join(out), encoding='utf-8')
    with open(ROOT / 'docs' / 'sound_inventory.csv', 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(['file', 'playlists', 'shipped_or_code_refs', 'test_map_refs'])
        w.writerows(rows)
    print('files', len(files), 'declared', len(declared_in), 'shipped/code', len(shipped_files),
          'test-only', len(exp_only), 'unreferenced', len(unref), 'decl-missing', len(decl_missing),
          'problems', len(problems))


if __name__ == '__main__':
    main()
