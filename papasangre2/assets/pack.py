"""The game data pack: the app bundle's files in one encrypted file.

REQUESTED (2026-09-25): the game ships as a folder - the exe beside its
libraries, so nothing is unpacked to a temporary folder at every start - with
the sounds, levels and playlists encrypted inside the exe itself rather than
lying loose.  ``tools/build_exes.py`` writes the pack and embeds it in the exe
as a Windows resource (type ``PS2PACK``, name ``GAMEDATA``); Windows maps it
with the exe, so reading a file is a slice of memory and a decryption.  A Mac
executable has no resources, so there the pack travels as ``gamedata.pak``
inside the .app bundle and is memory-mapped the same way.

The pack::

    b'PS2PACK1' | u32 table size | 12-byte table nonce | table | files
    table = ChaCha20(JSON {path: [offset, size, nonce hex]})
    file  = ChaCha20(bytes), each with its own nonce

The key lives in the program, as every game's must: this keeps the sounds
from being browsed or copied out of the folder, not from a determined
programmer.

Everything that reads game data goes through ``read_bytes`` / ``exists`` /
``glob`` here.  With a pack mounted, a path under its root is served from the
pack; anything else (and everything when running from source) is the disk.
"""

from __future__ import annotations

import ctypes
import fnmatch
import hashlib
import io
import json
import mmap
import os
import struct
import sys

from ..util.chacha import crypt

MAGIC = b'PS2PACK1'
RESOURCE_TYPE = 'PS2PACK'
RESOURCE_NAME = 'GAMEDATA'
FILE_NAME = 'gamedata.pak'
_KEY = hashlib.blake2b(b'Papa Sangre II - the port - game data pack - 2026',
                       digest_size=32, person=b'ps2-port').digest()


# --------------------------------------------------------------- writing
def write_pack(src_dir: str, out_path: str) -> int:
    """Pack every file under `src_dir`; returns how many."""
    entries = []
    for dp, _dirs, files in os.walk(src_dir):
        for f in files:
            full = os.path.join(dp, f)
            entries.append((os.path.relpath(full, src_dir).replace(os.sep, '/'), full))
    entries.sort()
    table: dict[str, list] = {}
    blobs = []
    offset = 0
    for rel, full in entries:
        data = open(full, 'rb').read()
        nonce = hashlib.blake2b(rel.encode('utf-8'), digest_size=12, key=_KEY).digest()
        blobs.append(crypt(_KEY, nonce, data))
        table[rel] = [offset, len(data), nonce.hex()]
        offset += len(data)
    raw = json.dumps(table, separators=(',', ':')).encode('utf-8')
    tnonce = hashlib.blake2b(b'table', digest_size=12, key=_KEY).digest()
    with open(out_path, 'wb') as fh:
        fh.write(MAGIC + struct.pack('<I', len(raw)) + tnonce + crypt(_KEY, tnonce, raw))
        for b in blobs:
            fh.write(b)
    return len(entries)


# --------------------------------------------------------------- reading
class Pack:
    def __init__(self, buf) -> None:
        mv = memoryview(buf).cast('B')
        if bytes(mv[:8]) != MAGIC:
            raise ValueError('not a game data pack')
        (size,) = struct.unpack('<I', bytes(mv[8:12]))
        tnonce = bytes(mv[12:24])
        self._table = json.loads(crypt(_KEY, tnonce, mv[24:24 + size]).decode('utf-8'))
        self._data = mv[24 + size:]
        # case-blind, as the disk is on Windows (the data was written for it)
        self._lower = {rel.lower(): rel for rel in self._table}
        self._dirs = {''}
        for rel in self._lower:
            parts = rel.split('/')
            for i in range(1, len(parts)):
                self._dirs.add('/'.join(parts[:i]))

    def __len__(self) -> int:
        return len(self._table)

    def names(self):
        return self._table.keys()

    def has(self, rel: str) -> bool:
        return rel.lower() in self._lower

    def is_dir(self, rel: str) -> bool:
        return rel.rstrip('/').lower() in self._dirs

    def read(self, rel: str) -> bytes:
        off, size, nonce = self._table[self._lower[rel.lower()]]
        return crypt(_KEY, bytes.fromhex(nonce), self._data[off:off + size])


def _exe_resource():
    """The pack embedded in the running exe, or None."""
    if sys.platform != 'win32' or not getattr(sys, 'frozen', False):
        return None
    k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    k32.GetModuleHandleW.restype = ctypes.c_void_p
    k32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
    k32.FindResourceW.restype = ctypes.c_void_p
    k32.FindResourceW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p]
    k32.SizeofResource.restype = ctypes.c_uint32
    k32.SizeofResource.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    k32.LoadResource.restype = ctypes.c_void_p
    k32.LoadResource.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    k32.LockResource.restype = ctypes.c_void_p
    k32.LockResource.argtypes = [ctypes.c_void_p]
    mod = k32.GetModuleHandleW(None)
    res = k32.FindResourceW(mod, RESOURCE_NAME, RESOURCE_TYPE)
    if not res:
        return None
    size = k32.SizeofResource(mod, res)
    ptr = k32.LockResource(k32.LoadResource(mod, res))
    if not ptr or not size:
        return None
    return (ctypes.c_ubyte * size).from_address(ptr)


# ------------------------------------------------------ the file system
_pack: Pack | None = None
_root: str | None = None


def mount(pack: Pack | None, root: str | None) -> None:
    """Serve paths under `root` from `pack` (None, None to unmount)."""
    global _pack, _root
    _pack = pack
    _root = os.path.normcase(os.path.abspath(root)) if root else None


def mounted() -> bool:
    return _pack is not None


def auto_mount(root: str) -> bool:
    """Mount the pack in the exe (or a gamedata.pak beside it) at `root`."""
    if _pack is not None:
        return True
    buf = _exe_resource()
    if buf is None:
        for base in (os.path.dirname(root), os.path.dirname(sys.executable)):
            p = os.path.join(base, FILE_NAME)
            if os.path.isfile(p):
                with open(p, 'rb') as fh:
                    buf = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
                break
    if buf is None:
        return False
    mount(Pack(buf), root)
    return True


def _rel(path: str) -> str | None:
    if _pack is None or _root is None:
        return None
    p = os.path.normcase(os.path.abspath(path))
    if p == _root:
        return ''
    if not p.startswith(_root + os.sep):
        return None
    return os.path.relpath(os.path.abspath(path), os.path.abspath(_root)).replace(os.sep, '/')


def read_bytes(path: str) -> bytes:
    rel = _rel(path)
    if rel is None:
        with open(path, 'rb') as fh:
            return fh.read()
    if not _pack.has(rel):
        raise FileNotFoundError(path)
    return _pack.read(rel)


def read_text(path: str, errors: str = 'strict') -> str:
    return read_bytes(path).decode('utf-8', errors=errors)


def exists(path: str) -> bool:
    rel = _rel(path)
    if rel is None:
        return os.path.exists(path)
    return _pack.has(rel) or _pack.is_dir(rel)


def isfile(path: str) -> bool:
    rel = _rel(path)
    if rel is None:
        return os.path.isfile(path)
    return _pack.has(rel)


def glob(pattern: str) -> list[str]:
    """Files matching `pattern` (fnmatch within one directory, like glob)."""
    rel = _rel(os.path.dirname(pattern))
    if rel is None:
        import glob as _glob
        return _glob.glob(pattern)
    base = os.path.dirname(pattern)
    want = os.path.basename(pattern)
    prefix = (rel + '/' if rel else '').lower()
    want = want.lower()
    out = []
    for name in _pack.names():
        low = name.lower()
        if low.startswith(prefix) and '/' not in low[len(prefix):]:
            if fnmatch.fnmatchcase(low[len(prefix):], want):
                out.append(os.path.join(base, name[len(prefix):]))
    return sorted(out)


def open_binary(path: str):
    """Something PyAV can open: the path itself on disk, a buffer from the pack."""
    if _rel(path) is None:
        return path
    return io.BytesIO(read_bytes(path))
