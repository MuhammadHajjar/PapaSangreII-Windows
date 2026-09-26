"""PS2's level loader, against `createObjectFromDict:` (0x10003c35c) and friends,
and against the 42 maps that ship in the app."""

import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from papasangre2.assets.tiled import (load_level, ns_bool, ns_float,     # noqa: E402
                                      ns_int, setter_for)

APP = os.path.join(ROOT, 'reference', 'Payload', 'Papa Sangre II.app')
SHIPPED = sorted(glob.glob(os.path.join(APP, 'levels', 'papasangre2', '*.json')))
TEST_MAPS = sorted(glob.glob(os.path.join(APP, 'levels', 'Experiments', '*.json')))


def lvl(name):
    return load_level(os.path.join(APP, 'levels', 'papasangre2', name + '.json'))


# ---------------------------------------------------------------- KVC
def test_nsstring_conversions():
    assert ns_bool('YES') and ns_bool('yes') and ns_bool('true') and ns_bool('1')
    assert not ns_bool('NO') and not ns_bool('0') and not ns_bool('') and not ns_bool('false')
    assert ns_bool('007')                     # leading zeros skipped, then 7
    assert ns_float('0.5') == 0.5 and ns_float(' 12abc') == 12.0 and ns_float('x') == 0.0
    assert ns_int('3') == 3 and ns_int('3.9') == 3 and ns_int('YES') == 0


def test_setter_names_capitalise_the_first_letter():
    assert setter_for('collideRadius') == 'setCollideRadius:'
    assert setter_for('CollideRadius') == 'setCollideRadius:'
    assert setter_for('onXrail') == 'setOnXrail:'


# ---------------------------------------------------------------- all maps
def test_every_shipped_and_test_map_loads():
    assert len(SHIPPED) == 23 and len(TEST_MAPS) == 19
    for p in SHIPPED + TEST_MAPS:
        d = load_level(p)
        assert d.room is not None, p
        assert d.player is not None, p


def test_every_layer_is_loaded():
    # ps2_14 has a layer literally called "no longer used"; PS2 builds it anyway
    d = lvl('ps2_14')
    layers = {o.layer for o in d.objects}
    assert 'no longer used' in layers


# ---------------------------------------------------------------- placement
def test_agents_and_player_sit_ten_right_and_ten_up_from_their_point():
    import json
    doc = json.load(open(os.path.join(APP, 'levels', 'papasangre2', 'ps2_1.json')))
    room = [o for L in doc['layers'] for o in L['objects'] if o['type'] == 'Room'][0]
    mid = (room['x'] + room['width'] / 2, room['y'] + room['height'] / 2)
    pl = [o for L in doc['layers'] for o in L['objects'] if o['type'] == 'Player'][0]
    d = lvl('ps2_1')
    assert (d.player.x, d.player.y) == (pl['x'] + 10 - mid[0], -((pl['y'] - 10) - mid[1]))


def test_surface_rectangles_flip_to_world_space():
    import json
    doc = json.load(open(os.path.join(APP, 'levels', 'papasangre2', 'ps2_1.json')))
    room = [o for L in doc['layers'] for o in L['objects'] if o['type'] == 'Room'][0]
    mid = (room['x'] + room['width'] / 2, room['y'] + room['height'] / 2)
    s = [o for L in doc['layers'] for o in L['objects'] if o['type'] == 'Surface'][0]
    d = lvl('ps2_1')
    assert d.floors[0].rect == (s['x'] - mid[0], -(s['y'] - mid[1]) - s['height'],
                                s['width'], s['height'])
    # the level itself is floorArray[0] with id 0; surfaces number from 1
    assert d.floors[0].surface_id == 1


# ---------------------------------------------------------------- defaults
def test_trip_and_run_defaults_differ_between_room_and_surface():
    d = lvl('ps2_1')
    assert (d.room.get('runBPM'), d.room.get('tripBPM')) == (180.0, 280.0)
    plain = [f for f in d.floors if 'tripBPM' not in f.raw]
    assert plain and all(f.get('tripBPM') == 350.0 and f.get('runBPM') == 180.0 for f in plain)


def test_room_reverb_comes_from_the_level_with_defaults():
    assert lvl('ps2_1').reverb == (1.7, 70.0, 1.0)
    assert lvl('ps2_13').reverb == (0.5, 0.0, 8.0)
    # ps2_16 names no reverbDampening: default 50 (0x10003d9d4)
    assert lvl('ps2_16').reverb == (0.5, 50.0, 0.5)


def test_surfaces_start_switched_on_unless_the_data_says_otherwise():
    d = lvl('ps2_7')
    for f in d.floors:
        want = ns_bool(f.raw.get('active', f.raw.get('Active', 'YES')))
        assert f.get('active') == want


def test_unnamed_agents_get_default_names():
    for p in SHIPPED:
        d = load_level(p)
        for i, a in enumerate(d.agents):
            assert a.agent_id == i
            assert a.name, a                 # never empty: default_agent_<n>


# ---------------------------------------------------------------- properties
def test_capitalised_keys_still_reach_their_setter():
    # "CollideRadius" (3 collectibles) and "Active" (40 surfaces) apply via KVC
    hits = 0
    for p in SHIPPED:
        d = load_level(p)
        for o in d.agents + d.floors:
            for k in ('CollideRadius', 'Active', 'ActivationCounter', 'Skippable'):
                if k in o.raw:
                    assert k not in o.ignored
                    assert (k[0].lower() + k[1:]) in o.applied
                    hits += 1
    assert hits >= 40


def test_typos_and_foreign_keys_are_ignored_as_the_original_ignores_them():
    ignored = set()
    for p in SHIPPED:
        d = load_level(p)
        for o in d.objects:
            ignored.update((o.type, k) for k in o.ignored)
    assert ('Surface', 'mutlipleOnEnter') in ignored
    assert ('Surface', 'footstepsfootstepsPrefix') in ignored
    assert ('Monster', 'deathCause') in ignored
    assert ('Monster', 'defaultSound') in ignored
    # and the real key is not
    assert ('Surface', 'multipleOnEnter') not in ignored


def test_lower_case_on_keys_are_properties_when_a_setter_exists():
    # PGESound has setOnXrail: - "onXrail" is a property, not a trigger
    d = lvl('ps2_Intro')
    rails = [a for a in d.agents if 'onXrail' in a.raw or 'onYrail' in a.raw]
    assert rails and all(('onXrail' in a.applied) or ('onYrail' in a.applied) for a in rails)


def test_ps2_11_is_in_the_folder_but_nothing_loads_it():
    import json
    targets = set()
    for p in SHIPPED:
        if p.endswith('ps2_11.json'):
            continue
        d = load_level(p)
        for o in d.objects:
            for t in o.triggers:
                if t.notification_name.endswith('LoadLevelWithName'):
                    targets.add(t.parameters.get('name'))
    assert 'ps2_11' not in targets
    hub = os.path.join(APP, 'levels', 'papasangre2_hubList.plist')
    import plistlib
    assert 'ps2_11' not in {v['fileName'] for v in plistlib.load(open(hub, 'rb')).values()}
