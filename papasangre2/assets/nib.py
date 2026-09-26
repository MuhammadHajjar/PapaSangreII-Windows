"""Decode a compiled iOS nib (the "NIBArchive" format) and print its text.

    python tools/nib.py PGEMenuHubViewController      -> every object, flattened
    python tools/nib.py --text PGEMenuHubViewController -> just the strings

The game reads the About screen's texts through `accessibility_texts`.

Format: "NIBArchive", two int32 (1, 9|10), then four (count, offset) pairs for
objects, keys, values and classes.  An object is (class, first value, value
count) as varints; a key is a varint length and bytes; a value is a varint key
index, a type byte and data; a class is a varint name length, a varint count
of extra int32s, the extras, and the name.
"""

from __future__ import annotations

import os
import struct
import sys

from . import pack



def _varint(b: bytes, i: int) -> tuple[int, int]:
    v = 0
    shift = 0
    while True:
        c = b[i]
        i += 1
        v |= (c & 0x7f) << shift
        if c & 0x80:
            return v, i
        shift += 7


def decode(path: str):
    b = pack.read_bytes(path)
    assert b[:10] == b'NIBArchive', path
    oc, oo, kc, ko, vc, vo, cc, co = struct.unpack('<8I', b[18:50])
    keys = []
    i = ko
    for _ in range(kc):
        n, i = _varint(b, i)
        keys.append(b[i:i + n].decode('utf-8', 'replace'))
        i += n
    classes = []
    i = co
    for _ in range(cc):
        n, i = _varint(b, i)
        extra, i = _varint(b, i)
        i += 4 * extra
        classes.append(b[i:i + n].rstrip(b'\0').decode('utf-8', 'replace'))
        i += n
    values = []
    i = vo
    for _ in range(vc):
        k, i = _varint(b, i)
        t = b[i]
        i += 1
        if t == 0:
            v = b[i]; i += 1
        elif t == 1:
            v = struct.unpack('<h', b[i:i + 2])[0]; i += 2
        elif t == 2:
            v = struct.unpack('<i', b[i:i + 4])[0]; i += 4
        elif t == 3:
            v = struct.unpack('<q', b[i:i + 8])[0]; i += 8
        elif t == 4:
            v = True
        elif t == 5:
            v = False
        elif t == 6:
            v = struct.unpack('<f', b[i:i + 4])[0]; i += 4
        elif t == 7:
            v = struct.unpack('<d', b[i:i + 8])[0]; i += 8
        elif t == 8:
            n, i = _varint(b, i)
            v = b[i:i + n]; i += n
        elif t == 9:
            v = None
        elif t == 10:
            v = ('@', struct.unpack('<I', b[i:i + 4])[0]); i += 4
        else:
            raise ValueError('value type %d at %d' % (t, i))
        values.append((keys[k], v))
    objects = []
    i = oo
    for _ in range(oc):
        c, i = _varint(b, i)
        first, i = _varint(b, i)
        n, i = _varint(b, i)
        objects.append((classes[c], values[first:first + n]))
    return objects


def strings(objects) -> list[tuple[int, str, str, str]]:
    """(object, class, key, text) for every NSString-ish value."""
    out = []
    for idx, (cls, vals) in enumerate(objects):
        if cls not in ('NSString', 'NSMutableString', 'NSLocalizableString'):
            continue
        for k, v in vals:
            if k == 'NS.bytes' and isinstance(v, bytes):
                try:
                    out.append((idx, cls, k, v.decode('utf-8')))
                except UnicodeDecodeError:
                    pass
    return out


def owners(objects):
    """Which key of which object points at each object."""
    own = {}
    for idx, (cls, vals) in enumerate(objects):
        for k, v in vals:
            if isinstance(v, tuple) and v and v[0] == '@':
                own.setdefault(v[1], []).append((idx, cls, k))
    return own



def text_views(path: str) -> list[str]:
    """The texts of every text view and label in a nib, in object order."""
    objs = decode(path)
    out = []
    for cls, vals in objs:
        if cls != 'UIClassSwapper' and cls not in ('UILabel', 'UITextView'):
            continue
        for k, v in vals:
            if k == 'UIText' and isinstance(v, tuple) and v[0] == '@':
                c2, v2 = objs[v[1]]
                for k2, b in v2:
                    if k2 == 'NS.bytes' and isinstance(b, bytes):
                        t = b.decode('utf-8', 'replace')
                        if t not in out:
                            out.append(t)
    return out
