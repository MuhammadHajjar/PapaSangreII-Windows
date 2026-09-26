"""Content check: every level, as the original engine would read it.

Loads the 23 shipped maps and the 19 developer test maps with the port's
loader (the same rules as `createObjectFromDict:`), then checks everything the
data refers to - messages, agents, levels, paths, sounds - and sorts every
oddity into a category with a reason.  The milestone gate is that nothing is
left **unexplained**: each oddity is either a named, reasoned entry in the
tables below or falls under a rule that the original itself applies (a
malformed statement is dropped, a missing sound plays nothing, ...).

Writes docs/CONTENT_CHECK.md; `Check game content.exe` runs it.
"""

from __future__ import annotations

import os
import plistlib
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from ..util import paths
from .observed import OBSERVED
from .sexp import include_stem, parse_playlist
from .tiled import LevelData, load_level, message_name, ns_bool


def bundle_dir() -> str:
    return paths.game_bundle()


LEVEL_DIR = 'papasangre2'
TEST_DIR = 'Experiments'

#: Keys the original logs as "Cannot find %@ on %@" and ignores, with why.
KNOWN_IGNORED = {
    ('Room', 'reverbRoomSize'): 'read directly by createObjectFromDict: (0x10003d0f0), not a setter',
    ('Room', 'reverbDampening'): 'read directly by createObjectFromDict: (0x10003d938), not a setter',
    ('Room', 'reverbVolume'): 'read directly by createObjectFromDict: (0x10003d9f4), not a setter',
    ('Surface', 'reverbRoomSize'): 'reverb is per Room only; a Surface has no setter',
    ('Surface', 'reverbDampening'): 'reverb is per Room only; a Surface has no setter',
    ('Surface', 'reverbVolume'): 'reverb is per Room only; a Surface has no setter',
    ('Surface', 'inactivitySounds'): 'a Room property; a Surface has no setter',
    ('Surface', 'mutlipleOnEnter'): 'misspelling of multipleOnEnter - the surface keeps its once-only OnEnter',
    ('Surface', 'footstepsfootstepsPrefix'): 'doubled word - the surface keeps the footsteps it inherits',
    ('Surface', 'onKill'): 'lower-case "on": not a trigger, and there is no setOnKill:',
    ('Collectible', 'spatialized'): 'no setter on PGECollectible: its sounds are spatialised by code',
    ('Collectible', 'looping'): 'no setter on PGECollectible',
    ('Collectible', 'collideRange'): 'misspelling of collideRadius',
    ('Sound', 'collideRange'): 'misspelling of collideRadius',
    ('Sound', 'ignoreLoop'): 'a Collectible property; PGESound has no setter',
    ('Sound', 'deathCause'): 'a Surface property; PGESound has no setter',
    ('Sound', 'patrolSpeed'): 'a Monster property; PGESound has no setter',
    ('Sound', 'invincibleWhenMoving'): 'a Monster property; PGESound has no setter',
    ('Monster', 'defaultSound'): 'the PS1 enemy key; PS2 enemies use stillSound / patrolSound',
    ('Monster', 'deathCause'): 'not a Monster property; a death cause travels in LoadLevelWithName',
    ('Monster', 'onDeactivate'): 'lower-case "on": not a trigger, and there is no setOnDeactivate:',
    ('Monster', 'spatialized'): 'no setter on PGEEnemy (test maps only)',
    ('Player', 'handsAction'): 'no setter on PGEPlayer (test maps only; the real keys are leftHandAction / rightHandAction)',
    ('Player', 'speed'): 'no setter on PGEPlayer (test maps only)',
}

#: `On...` keys that are not a trigger for their type: dropped by the loader.
KNOWN_DROPPED_TRIGGERS = {
    ('Room', 'OnLeftHand'): 'a Room has no hand triggers in PS2 - the prompt-hands line ps2_1 puts on its Room never plays',
    ('Room', 'OnRightHand'): 'a Room has no hand triggers in PS2 - the prompt-hands line ps2_1 puts on its Room never plays',
    ('Room', 'OnLoadLevel'): 'not a trigger name for any type',
    ('Surface', 'OnSoundEnd'): 'a Surface has no OnSoundEnd trigger in PS2',
    ('Sound', 'OnXrail'): 'meant as the rail flag onXrail; with a capital O it is neither a trigger nor a property, so ps2_Intro wrong_way_warning stays where it was placed',
    ('Sound', 'OnYrail'): 'meant as the rail flag onYrail; see OnXrail',
    ('Monster', 'OnDeactive'): 'misspelling of OnDeactivate (test map only)',
}

#: Message names the levels fire that no class observes: they reach nobody.
KNOWN_UNOBSERVED = {
    'PGE_MESSAGE_': 'an empty statement - two "|" in a row, or a trailing "|" - posts a bare PGE_MESSAGE_ to nobody',
    'PGE_MESSAGE_DeactiveAgentWithName': 'misspelling of DeactivateAgentWithName',
    'PGE_MESSAGE_DisableClap;afterDelay=2': '";" where ":" belongs: with no colon the whole statement is the message name',
    'PGE_MESSAGE_ShutDownLevel;afterDelay=1': '";" where ":" belongs: with no colon the whole statement is the message name',
    'PGE_MESSAGE_RemoveFullScreenImage;afterDelay=3': '";" where ":" belongs (and the message is visual anyway)',
    'PGE_MESSAGE_tripwire_decline_rescue': 'a bare sound name written where a message belongs',
}

#: Object types createObjectFromDict: builds nothing for.
KNOWN_UNBUILT = {
    '': 'untyped object - an editor annotation; createObjectFromDict: has no branch for it',
}

#: message -> (parameter naming the receiver, what a missing name means).
#: Each read from its handler: most compare `params[name]` with their own name,
#: so no name matches nobody; two treat no name as "every one of us".
AGENT_MESSAGES = {
    'PGE_MESSAGE_ActivateAgentWithName': ('name', 'none'),         # 0x100022ce8
    'PGE_MESSAGE_DeactivateAgentWithName': ('name', 'none'),       # 0x100023340; "*" = all
    'PGE_MESSAGE_FadeOutAgentWithName': ('name', 'none'),          # 0x100023c44
    'PGE_MESSAGE_ResetAgentWithName': ('name', 'none'),            # 0x100023644
    'PGE_MESSAGE_DeallocAgentWithName': ('name', 'none'),          # 0x100042bd8
    'PGE_MESSAGE_SendAgentAwayFromPlayer': ('name', 'all'),        # 0x100064eac: every follower
    'PGE_MESSAGE_SendAgentToInitialPosition': ('name', 'all'),     # 0x10001fda0: every monster
    'PGE_MESSAGE_PlaySpatialSoundOnAgentWithName': ('agentName', 'none'),   # 0x1000263fc
    'PGE_MESSAGE_SetLethalForSurfaceWithName': ('name', 'none'),   # 0x100045364
}

SOUND_KEYS = {
    'soundList', 'introSound', 'loopSound', 'collectSound', 'chaseSound', 'patrolSound',
    'stillSound', 'awareSound', 'notThereSound', 'attackSound', 'shotSound', 'beatenSound',
    'beatRangeSound', 'proximitySound', 'scaredSound', 'pauseSound', 'deathSound',
    'followerAlertSound', 'sound', 'clapSound', 'shootSound', 'beatSound', 'jumpSound',
    'drowningSound', 'gaggingSound', 'inactivitySounds', 'hitWallSound', 'tripSound',
    'shuffleSound', 'litSound', 'goOffSound', 'aboutToGoSound',
}
SOUND_PARAMS = {('PGE_MESSAGE_PlaySound', 'soundName'),
                ('PGE_MESSAGE_PlaySpatialSoundOnAgentWithName', 'soundName'),
                ('PGE_MESSAGE_ChangeInactivitySoundList', 'soundList')}


@dataclass
class Finding:
    level: str
    category: str
    where: str
    detail: str
    reason: str = ''          # empty = unexplained


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    levels: dict[str, LevelData] = field(default_factory=dict)
    shipped: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)

    @property
    def unexplained(self) -> list[Finding]:
        return [f for f in self.findings if not f.reason]


# ----------------------------------------------------------------- playlists
class Playlists:
    def __init__(self, bundle: str):
        self.bundle = bundle
        self.pls = {}
        d = os.path.join(bundle, 'meta', 'S3DPlayListModel')
        for f in os.listdir(d):
            if f.endswith('.sexp'):
                with open(os.path.join(d, f), encoding='utf-8', errors='replace') as fh:
                    self.pls[f.split('.S3DPlayListModel')[0]] = parse_playlist(fh.read(), f)
        self._pool = {}

    def closure(self, name: str) -> list[str]:
        out: list[str] = []

        def walk(n):
            if n in out or n not in self.pls:
                return
            out.append(n)
            for inc in self.pls[n].includes:
                walk(include_stem(inc))
        walk(name)
        return out

    def pool(self, level: str) -> dict[str, str]:
        if level not in self._pool:
            p = {}
            for n in self.closure(level):
                for s in self.pls[n].sounds:
                    p.setdefault(s.name, s.bundle_path)
            self._pool[level] = p
        return self._pool[level]

    def resolve(self, level: str, raw: str) -> tuple[list[str], str]:
        """exact name, else prefix; returns (bundle paths, how)."""
        pool = self.pool(level)
        if raw in pool:
            return [pool[raw]], 'exact'
        hit = [pool[n] for n in sorted(pool) if n.startswith(raw)]
        return hit, ('prefix' if hit else 'none')


# ----------------------------------------------------------------- the check
SOUND_INDEX = 'sounds_index.txt'


def sound_files(bundle: str) -> set[str]:
    """Every audio file in the bundle, as `sounds/...` paths.

    The check only needs the names.  A frozen `Check game content.exe` carries
    `sounds_index.txt` (written by `write_sound_index` at build time) instead
    of the 85 MB tree; from source the tree itself is walked.
    """
    tree = os.path.join(bundle, 'sounds')
    index = os.path.join(bundle, SOUND_INDEX)
    if not os.path.isdir(tree) and os.path.exists(index):
        with open(index, encoding='utf-8') as fh:
            return {ln.strip() for ln in fh if ln.strip()}
    out = set()
    for root, _, fs in os.walk(tree):
        for f in fs:
            if f.endswith(('.m4a', '.mp3')):
                out.add(os.path.relpath(os.path.join(root, f), bundle).replace(os.sep, '/'))
    return out


def write_sound_index(bundle: str, path: str) -> int:
    names = sorted(sound_files(bundle))
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(names) + '\n')
    return len(names)


def run(bundle: str | None = None) -> Report:
    bundle = bundle or bundle_dir()
    rep = Report()
    pls = Playlists(bundle)
    audio = sound_files(bundle)
    stems = {os.path.splitext(os.path.basename(a))[0] for a in audio}

    for sub in (LEVEL_DIR, TEST_DIR):
        d = os.path.join(bundle, 'levels', sub)
        for f in sorted(os.listdir(d)):
            if not f.endswith('.json'):
                continue
            name = f[:-5]
            data = load_level(os.path.join(d, f), name)
            key = name if sub == LEVEL_DIR else 'test:' + name
            rep.levels[key] = data
            (rep.shipped if sub == LEVEL_DIR else rep.tests).append(key)

    with open(os.path.join(bundle, 'levels', 'papasangre2_hubList.plist'), 'rb') as fh:
        hub = plistlib.load(fh)
    in_hub = {v['fileName'] for v in hub.values()}
    loaded = set()

    for key, data in rep.levels.items():
        lv = data.name
        cut = key == 'ps2_11'
        agent_names = {a.name for a in data.agents}
        surface_names = {f.name for f in data.floors if f.name}
        path_names = {p.name for p in data.paths}

        def add(cat, where, detail, reason=''):
            if cut and not reason:
                reason = 'ps2_11 is a cut level: in no menu and loaded by no level (BUILD_ORDER.md decision 3)'
            rep.findings.append(Finding(key, cat, where, detail, reason))

        for o in data.objects + data.unbuilt:
            label = '%s %s' % (o.type or '(untyped)', o.name or '')
            for k in o.ignored:
                add('ignored key', label, k, KNOWN_IGNORED.get((o.type, k), ''))
            for k in o.dropped_keys:
                add('dropped trigger key', label, k, KNOWN_DROPPED_TRIGGERS.get((o.type, k), ''))
            for m in o.malformed:
                add('malformed statement', label, m,
                    'a pair without "=": createDictFromTriggerDescription: returns nil and the '
                    'whole statement is dropped (0x10003f448)')
        for o in data.unbuilt:
            add('unbuilt object', '%s %s' % (o.type or '(untyped)', o.name), o.layer,
                KNOWN_UNBUILT.get(o.type, ''))

        for o in data.objects:
            label = '%s %s' % (o.type, o.name)
            for t in o.triggers:
                msg = message_name(t.notification_name)
                if msg not in OBSERVED:
                    add('message with no observer', label, msg,
                        KNOWN_UNOBSERVED.get(msg, ''))
                    continue
                if msg == 'PGE_MESSAGE_LoadLevelWithName':
                    target = t.parameters.get('name', '')
                    loaded.add(target)
                    if not os.path.exists(os.path.join(bundle, 'levels', LEVEL_DIR, target + '.json')):
                        add('unknown level', label, target,
                            'a test map chaining to another test map in levels/Experiments; the test '
                            'maps are not playable levels of the game' if key.startswith('test:') else '')
                if msg in ('PGE_MESSAGE_FollowPathWithName', 'PGE_MESSAGE_MakePlayerFollowPathWithName'):
                    pn = t.parameters.get('name', '')
                    if pn not in path_names:
                        add('unknown path', label, '%s name=%s' % (msg, pn),
                            'no such path: pathWithName: returns nil and nothing follows it')
                spec = AGENT_MESSAGES.get(msg)
                if spec:
                    pk, missing = spec
                    target = t.parameters.get(pk)
                    if target is None:
                        if missing == 'none':
                            add('agent message without a name', label, msg,
                                'no "%s" parameter: every receiver compares its own name '
                                'against nil and none matches' % pk)
                    elif (target not in agent_names and target not in surface_names
                          and not (target == '*' and msg == 'PGE_MESSAGE_DeactivateAgentWithName')):
                        add('unknown agent', label, '%s %s=%s' % (msg, pk, target),
                            'broadcast to a name nothing in the level has: nothing happens')
                for (m, p) in SOUND_PARAMS:
                    if msg == m and p in t.parameters:
                        for part in t.parameters[p].split('&'):
                            _check_sound(add, pls, stems, lv, label + ' ' + msg, part)
            for k in SOUND_KEYS:
                if k in o.applied and isinstance(o.applied[k], str):
                    for part in o.applied[k].split('&'):
                        _check_sound(add, pls, stems, lv, label + '.' + k, part)

    # levels nobody reaches
    for name in rep.shipped:
        if name not in in_hub and name not in loaded:
            rep.findings.append(Finding(name, 'unreachable level', name, 'in no menu, loaded by no level',
                                        'cut level (BUILD_ORDER.md decision 3)'))
    return rep


def _check_sound(add, pls: Playlists, stems: set[str], level: str, where: str, raw: str) -> None:
    raw = raw.strip()
    if not raw:
        return
    hits, how = pls.resolve(level, raw)
    if hits:
        return
    anywhere = any(s == raw or s.startswith(raw) for s in stems)
    if anywhere:
        add('sound not in the level\'s playlists', where, raw,
            'the file ships, but no playlist this level loads declares it: the lookup finds '
            'nothing and the sound is silent if the engine ever asks for it')
    else:
        add('sound that does not exist', where, raw,
            'no such file anywhere in the app: silent in the original')


# ----------------------------------------------------------------- report
def write_report(rep: Report, path: str) -> None:
    by_cat = defaultdict(list)
    for f in rep.findings:
        by_cat[f.category].append(f)
    L = ['# Content check\n',
         'Generated by `papasangre2/assets/audit.py` (`Check game content.exe`). Every level '
         'read with the port\'s loader, which follows `createObjectFromDict:`; everything the '
         'data refers to checked. An oddity with a reason is behaviour the original has too '
         '(it is reproduced, not fixed); one **without** a reason is a gap in the port\'s '
         'understanding and fails the check.\n',
         '| | count |', '|---|---|',
         '| shipped levels | %d |' % len(rep.shipped),
         '| developer test maps | %d |' % len(rep.tests),
         '| findings | %d |' % len(rep.findings),
         '| **unexplained** | **%d** |' % len(rep.unexplained), '']
    for cat, fs in sorted(by_cat.items()):
        L.append('## %s (%d)\n' % (cat, len(fs)))
        reasons = Counter(f.reason for f in fs)
        for reason, n in reasons.most_common():
            L.append('**%s** - %d\n' % (reason or 'UNEXPLAINED', n))
            rows = [f for f in fs if f.reason == reason]
            for f in rows[:400]:
                L.append('* %s - %s: `%s`' % (f.level, f.where, f.detail))
            if len(rows) > 400:
                L.append('* ... %d more' % (len(rows) - 400))
            L.append('')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(L))
