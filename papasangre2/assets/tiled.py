"""Papa Sangre II's level loader: the Tiled JSON exports as the original reads them.

Reproduces `-[PGELevel actuallyLoadDataFromJsonFile]` and its helpers
(`loadLevelStructure:`, `loadLevelAgents:`, `loadPlayer:`,
`createObjectFromDict:` 0x10003c35c, `parseTriggersForNames:propertiesDict:
receiver:` 0x10003e77c, `createDictFromTriggerDescription:` 0x10003ee18) from the
PS2 arm64 binary.  The rules differ from Papa Sangre 1's in ways that matter;
each one is marked PS2 below.  See GAME_STRUCTURE.md section 5.

* **Every layer is loaded** (PS2).  The PS1 engine skipped layers named
  `ToolBar`; this one has no such test, so an object in a layer called "no
  longer used" is built like any other.
* Three passes, each over every layer in order: the `Room`; every other object
  except the `Player`; the `Player`.
* **Triggers are explicit per type** (PS2): a key counts as a trigger only if
  it is one of its type's names (TRIGGER_NAMES) or starts `<name>_`, which is
  how Tiled carries a second trigger of one type (`OnActivate_2`).  Any other
  key starting `On` is neither a trigger nor a property - it is dropped.
* **Every other key goes through KVC**: `set<Key>:` with the first letter
  upper-cased, applied only if the class answers `respondsToSelector:`
  (assets/schema.py, generated from the binary's own metadata), with KVC's
  string-to-scalar conversion (`floatValue`, `intValue`, `boolValue`).
* **Positions** (PS2): agents and the player sit at `(x + 10, y - 10)` of their
  Tiled point, *not* at the centre of their box, then the usual room-relative
  transform with Y negated: `(x + 10 - mid.x, -((y - 10) - mid.y))`
  (0x10003c9c8, 0x10003d7dc).  Surfaces keep a rectangle
  `(x - mid.x, -(y - mid.y) - h, w, h)`; path points are
  `(x + px - mid.x, -(y + py - mid.y))`; the room is `(-w/2, -h/2, w, h)` with
  `mid = (x + w/2, y + h/2)`.
* Defaults written when the data names none: Room runBPM 180 / tripBPM **280**,
  Surface runBPM 180 / tripBPM **350**; Room reverb room size 1.5, dampening
  50, volume 1.0.
* Agents: named `default_agent_<n>` when unnamed; `active` is applied by the
  properties like everything else, and applied again 0.05 s after load by a
  `dispatch_after` block (0x10003e674) - a no-op unless the first one was
  skipped.  Surfaces are created switched on (`setActive:YES`, 0x10003e178).

What the port cannot recover: the order of two trigger keys of one type
(`OnActivate` against `OnActivate_2`) is NSDictionary `allKeys` order, a hash
order.  The port keeps the order the keys appear in the JSON file (PORT-SIDE).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

from . import pack
from .schema import SETTERS, TYPE_CLASS

MESSAGE_PREFIX = 'PGE_MESSAGE_'

#: `-[PGELevel isThisTypeAnAgent:]` (0x10003c200).  Only five of them have a
#: class behind them in PS2; for the rest `createObjectFromDict:` builds
#: nothing (no shipped level uses them).
AGENT_TYPES = ('Collectible', 'Monster', 'Follower', 'Summoner', 'Position', 'NPC',
               'Sound', 'Beatable', 'TagPlayer', 'ForgetfulMan', 'Fireworks')

#: Trigger names per type, in the order `createObjectFromDict:` lists them.
_AGENT = ['OnLoad', 'OnLeftHand', 'OnRightHand', 'OnPathEnd', 'OnEnteringShootRange',
          'OnDeactivate', 'OnActivate', 'OnShoot', 'OnShootMissed', 'OnCollide',
          'OnClap', 'OnClapTooMuch', 'OnHitWall', 'OnStab', 'OnStep', 'OnShake',
          'OnRouteChange']
_FLOOR = ['OnKill', 'OnJump', 'OnJumpTooMuch', 'OnEnter', 'OnStep', 'OnDeactivate',
          'OnActivate', 'OnPebble', 'OnExit', 'OnDeadlyYes', 'OnDeadlyNo', 'OnTrip',
          'OnStillLimit']
TRIGGER_NAMES: dict[str, list[str]] = {
    'Fireworks':   _AGENT + ['OnGoOff', 'OnExplosion', 'OnSoundEnd'],
    'Collectible': _AGENT + ['OnSoundEnd', 'OnCollect', 'OnSkip'],
    'Sound':       _AGENT + ['OnSoundEnd', 'OnSkip'],
    'Monster':     _AGENT + ['OnPlayerLastPosition', 'OnChase', 'OnBeatMissed',
                             'OnShotSoundEnd', 'OnBeatenSoundEnd'],
    'Follower':    _AGENT + ['OnProximity'],
    'Player':      ['OnEmptyHand', 'OnShootMissed', 'OnBeatMissed', 'OnLeftHand',
                    'OnRightHand', 'OnShoot', 'OnTrip', 'OnLoad', 'OnClap',
                    'OnClapTooMuch', 'OnHitWall', 'OnGagging', 'OnPathEnd', 'OnShake'],
    'Room':        _FLOOR,
    'Surface':     _FLOOR,
}

ROOM_RUN_BPM, ROOM_TRIP_BPM = 180.0, 280.0          # 0x10003d090 / 0x10003d0d4
SURFACE_RUN_BPM, SURFACE_TRIP_BPM = 180.0, 350.0    # 0x10003e098 / 0x10003e0e4
ROOM_REVERB = (1.5, 50.0, 1.0)                      # 0x10003d918 / d9d4 / da8c
PLACE_OFFSET = 10.0                                 # 0x10003c9c8 / 0x10003d7dc
ACTIVE_DELAY = 0.05                                 # dispatch_time 50,000,000 ns


# ---------------------------------------------------------------- KVC values
_NUM = re.compile(r'^\s*([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)')
_INT = re.compile(r'^\s*([+-]?\d+)')


def ns_float(s: Any) -> float:
    """`-[NSString floatValue]`: the leading number, 0.0 when there is none."""
    if isinstance(s, (int, float)):
        return float(s)
    m = _NUM.match(str(s))
    return float(m.group(1)) if m else 0.0


def ns_int(s: Any) -> int:
    """`-[NSString intValue]`."""
    if isinstance(s, (int, float)):
        return int(s)
    m = _INT.match(str(s))
    return int(m.group(1)) if m else 0


def ns_bool(s: Any) -> bool:
    """`-[NSString boolValue]`: YES on a leading Y, y, T, t or digit 1-9,
    after whitespace, an optional sign and leading zeros."""
    if isinstance(s, bool):
        return s
    t = str(s).lstrip()
    if t[:1] in '+-':
        t = t[1:]
    t = t.lstrip('0')
    return bool(t) and (t[0] in 'YyTt' or t[0] in '123456789')


def kvc_value(type_code: str, raw: Any) -> Any:
    """What `setValue:forKey:` hands the setter for a string from the JSON."""
    if type_code in ('f', 'd'):
        return ns_float(raw)
    if type_code in ('i', 'I', 'q', 'Q', 's', 'l'):
        return ns_int(raw)
    if type_code in ('B', 'c'):
        return ns_bool(raw)
    return raw                        # objects: the NSString itself


def setter_for(key: str) -> str:
    """`[NSString stringWithFormat:@"set%@:", capitalised key]` (0x10003dd70)."""
    return 'set%s%s:' % (key[:1].upper(), key[1:])


def message_name(raw: str) -> str:
    """`-[PGEObjectWithTriggers messageNameFromString:]` (0x1000295f8)."""
    return raw if raw.startswith(MESSAGE_PREFIX) else MESSAGE_PREFIX + raw


# ------------------------------------------------------------------ triggers
@dataclass
class Trigger:
    """One statement, as `createDictFromTriggerDescription:` builds it.

    `count`, `after_count`, `after_delay`, `min_delay` and `max_delay` stay
    the strings the data gave: the original converts them only when the
    trigger fires (`intValue` / `floatValue` inside `triggerWithType:`).
    """
    trigger_type: str
    notification_name: str                # as written; normalised when fired
    parameters: dict[str, str] = field(default_factory=dict)
    count: str | None = None
    after_count: str | None = None
    after_delay: str | None = None
    min_delay: str | None = None
    max_delay: str | None = None
    raw: str = ''
    key: str = ''                         # the property key it came from

    def clone(self) -> 'Trigger':
        return Trigger(self.trigger_type, self.notification_name, dict(self.parameters),
                       self.count, self.after_count, self.after_delay, self.min_delay,
                       self.max_delay, self.raw, self.key)


_CONSUMED = {'count': 'count', 'afterCount': 'after_count', 'afterDelay': 'after_delay',
             'minDelay': 'min_delay', 'maxDelay': 'max_delay'}


def parse_trigger_statement(trigger_type: str, statement: str) -> Trigger | None:
    """`createDictFromTriggerDescription:` for one `|`-separated statement.

    Split on `:`.  Exactly two parts: the first is the message, the second
    `key=value` pairs split on `;`.  Any other number of parts: the message is
    the **first** part and there are no parameters (PS2 - 0x10003f340).  A
    pair that does not split into exactly two on `=` logs "Trigger definition
    error" and **the whole statement is dropped**: the method returns nil and
    `parseTriggersForNames:` skips it (0x10003f448, 0x10003ebd0).
    """
    parts = statement.split(':')
    t = Trigger(trigger_type=trigger_type, notification_name=parts[0], raw=statement)
    if len(parts) != 2:
        return t
    for pair in parts[1].split(';'):
        kv = pair.split('=')
        if len(kv) != 2:
            return None
        k, v = kv
        attr = _CONSUMED.get(k)
        if attr:
            setattr(t, attr, v)
        else:
            t.parameters[k] = v
    return t


def parse_triggers(obj_type: str, props: dict[str, Any]) -> tuple[list[Trigger], list[str]]:
    """`parseTriggersForNames:propertiesDict:receiver:`.

    Returns the triggers and the statements that were dropped as malformed
    (for the content check - the original only logs them).
    """
    out: list[Trigger] = []
    dropped: list[str] = []
    for name in TRIGGER_NAMES.get(obj_type, []):
        for key, value in props.items():
            if not (key == name or key.startswith(name + '_')):
                continue
            ttype = key.split('_')[0]
            for statement in str(value).split('|'):
                t = parse_trigger_statement(ttype, statement)
                if t is None:
                    dropped.append('%s: %s' % (key, statement))
                    continue
                t.key = key
                out.append(t)
    return out, dropped


def trigger_keys(obj_type: str, props: dict[str, Any]) -> set[str]:
    names = TRIGGER_NAMES.get(obj_type, [])
    return {k for k in props for n in names if k == n or k.startswith(n + '_')}


# ------------------------------------------------------------------- objects
@dataclass
class LevelObject:
    """One object `createObjectFromDict:` built (or refused to build)."""
    type: str
    cls: str | None                       # PGE class, None when nothing is built
    name: str
    layer: str
    x: float = 0.0                        # world position (agents, player)
    y: float = 0.0
    rect: tuple[float, float, float, float] | None = None      # surfaces
    z: int = 0
    surface_id: int = -1
    agent_id: int = -1
    is_circle: bool = False
    polyline: list[tuple[float, float]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)          # properties as in the JSON
    applied: dict[str, Any] = field(default_factory=dict)      # key -> converted value, in order
    ignored: list[str] = field(default_factory=list)           # keys with no setter
    dropped_keys: list[str] = field(default_factory=list)      # On... keys that are not triggers
    triggers: list[Trigger] = field(default_factory=list)
    malformed: list[str] = field(default_factory=list)

    def get(self, key: str, default: Any = None) -> Any:
        return self.applied.get(key, default)


@dataclass
class LevelData:
    name: str
    rect: tuple[float, float, float, float]
    mid: tuple[float, float]
    room: LevelObject
    reverb: tuple[float, float, float]
    player: LevelObject | None = None
    agents: list[LevelObject] = field(default_factory=list)
    floors: list[LevelObject] = field(default_factory=list)
    paths: list[LevelObject] = field(default_factory=list)
    unbuilt: list[LevelObject] = field(default_factory=list)   # types with no class
    #: `inactivitySounds` of the Room, posted at load as ChangeInactivitySoundList
    inactivity_sound_list: str | None = None

    @property
    def objects(self) -> list[LevelObject]:
        return [self.room] + self.paths + self.floors + self.agents + (
            [self.player] if self.player else [])

    def agent(self, name: str) -> LevelObject | None:
        for a in self.agents:
            if a.name == name:
                return a
        return None


def _f(d: dict, key: str) -> float:
    return ns_float(d.get(key, 0))


def apply_properties(obj: LevelObject) -> None:
    """The generic tail of `createObjectFromDict:` (0x10003dbc4-0x10003ded4).

    Keys starting `On` are skipped outright; the rest are applied when the
    class answers `set<Key>:`.  KVC is handed the *original* key, which
    resolves to the same setter (KVC capitalises it too).
    """
    setters = SETTERS.get(obj.cls or '', {})
    triggers = trigger_keys(obj.type, obj.raw)
    for key, value in obj.raw.items():
        if key.startswith('On'):
            if key not in triggers:
                obj.dropped_keys.append(key)
            continue
        entry = setters.get(setter_for(key))
        if entry is None:
            obj.ignored.append(key)
            continue
        obj.applied[_canonical(key)] = kvc_value(entry[0], value)


def _canonical(key: str) -> str:
    """The property a KVC key lands on: `CollideRadius` sets `collideRadius`."""
    return key[:1].lower() + key[1:]


def load_level(path: str, name: str | None = None) -> LevelData:
    doc = json.loads(pack.read_text(path))
    if name is None:
        name = os.path.splitext(os.path.basename(path))[0]
    layers = [l for l in doc.get('layers', []) if l.get('type', 'objectgroup') == 'objectgroup']

    def each(pred):
        for L in layers:
            for o in L.get('objects') or []:
                if pred(o):
                    yield L.get('name', ''), o

    # ---- pass 1: loadLevelStructure: - the Room ---------------------------
    rooms = list(each(lambda o: o.get('type') == 'Room'))
    if not rooms:
        raise ValueError(f'{name}: no Room object')
    layer, rd = rooms[-1]                     # every Room is processed; the last wins
    rw, rh = _f(rd, 'width'), _f(rd, 'height')
    rx, ry = _f(rd, 'x'), _f(rd, 'y')
    props = dict(rd.get('properties') or {})
    room = LevelObject('Room', 'PGELevel', name, layer, raw=props)
    room.rect = (-rw / 2.0, -rh / 2.0, rw, rh)
    mid = (rx + rw / 2.0, ry + rh / 2.0)
    room.applied['runBPM'] = ROOM_RUN_BPM
    room.applied['tripBPM'] = ROOM_TRIP_BPM
    if 'runBPM' in props:
        room.applied['runBPM'] = ns_float(props['runBPM'])
    if 'tripBPM' in props:
        room.applied['tripBPM'] = ns_float(props['tripBPM'])
    reverb = (ns_float(props['reverbRoomSize']) if 'reverbRoomSize' in props else ROOM_REVERB[0],
              ns_float(props['reverbDampening']) if 'reverbDampening' in props else ROOM_REVERB[1],
              ns_float(props['reverbVolume']) if 'reverbVolume' in props else ROOM_REVERB[2])
    room.triggers, room.malformed = parse_triggers('Room', props)
    apply_properties(room)
    data = LevelData(name=name, rect=room.rect, mid=mid, room=room, reverb=reverb,
                     inactivity_sound_list=props.get('inactivitySounds'))

    def place(o: dict) -> tuple[float, float]:
        return (_f(o, 'x') + PLACE_OFFSET - mid[0], -((_f(o, 'y') - PLACE_OFFSET) - mid[1]))

    # ---- pass 2: loadLevelAgents: - everything but Room and Player --------
    for layer, o in each(lambda o: o.get('type') not in ('Room', 'Player')):
        t = o.get('type') or ''
        props = dict(o.get('properties') or {})
        oname = o.get('name') or ''
        if t in AGENT_TYPES:
            cls = TYPE_CLASS.get(t)
            obj = LevelObject(t, cls, oname, layer, raw=props)
            if cls is None:
                data.unbuilt.append(obj)
                continue
            obj.agent_id = len(data.agents)
            obj.triggers, obj.malformed = parse_triggers(t, props)
            if not obj.name:
                obj.name = 'default_agent_%i' % len(data.agents)
            obj.x, obj.y = place(o)
            data.agents.append(obj)
            apply_properties(obj)
        elif t == 'Path':
            obj = LevelObject('Path', 'PGEPath', oname, layer, raw=props)
            ox, oy = _f(o, 'x'), _f(o, 'y')
            obj.polyline = [(ox + _f(p, 'x') - mid[0], -(oy + _f(p, 'y') - mid[1]))
                            for p in o.get('polyline') or []]
            data.paths.append(obj)
            apply_properties(obj)
        elif t == 'Surface':
            obj = LevelObject('Surface', 'PGESurface', '', layer, raw=props)
            x, y, w, h = _f(o, 'x'), _f(o, 'y'), _f(o, 'width'), _f(o, 'height')
            obj.rect = (x - mid[0], -(y - mid[1]) - h, w, h)
            # initWithRectangle:surfaceId:[floorArray count] (0x10003d408): the
            # level is floorArray[0] with id 0, so surfaces number from 1
            obj.surface_id = len(data.floors) + 1
            obj.z = ns_int(props.get('z', 0))
            obj.is_circle = ns_bool(props.get('isCircle', 'NO'))
            obj.triggers, obj.malformed = parse_triggers('Surface', props)
            obj.applied['runBPM'] = ns_float(props['runBPM']) if 'runBPM' in props else SURFACE_RUN_BPM
            obj.applied['tripBPM'] = ns_float(props['tripBPM']) if 'tripBPM' in props else SURFACE_TRIP_BPM
            if o.get('name'):
                obj.name = o['name']
            obj.applied['active'] = True           # setActive:YES before the properties
            data.floors.append(obj)
            apply_properties(obj)
        else:
            # untyped, or a type createObjectFromDict: has no branch for: nothing
            data.unbuilt.append(LevelObject(t, None, oname, layer, raw=props))

    # ---- pass 3: loadPlayer: ------------------------------------------------
    for layer, o in each(lambda o: o.get('type') == 'Player'):
        props = dict(o.get('properties') or {})
        p = LevelObject('Player', 'PGEPlayer', o.get('name') or '', layer, raw=props)
        p.x, p.y = place(o)
        p.triggers, p.malformed = parse_triggers('Player', props)
        apply_properties(p)
        data.player = p                      # every Player is built; the last is kept
    return data


def level_path(bundle: str, name: str, product: str = 'papasangre2') -> str:
    """`levels/<product>/<name>.json` (`actuallyLoadDataFromJsonFile`)."""
    return os.path.join(bundle, 'levels', product, name + '.json')
