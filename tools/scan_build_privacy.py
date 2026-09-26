"""Look through a built game for anything personal before it is shared.

Every loose file, every entry of the exe's own archive, and every compiled
module inside it (their strings and file names) is searched for the owner's
name, e-mail and folder paths.  Prints each hit; no output but the counts
means clean.

    python tools/scan_build_privacy.py "build/dist_game/Play Papa Sangre II"
"""

from __future__ import annotations

import marshal
import os
import sys
import tempfile

from PyInstaller.archive.readers import CArchiveReader, ZlibArchiveReader

#: this machine's user name, home folder and checkout, and anything listed in
#: the PRIVACY_NEEDLES environment variable (separated by ;)
_MINE = [os.environ.get('USERNAME', ''), os.path.expanduser('~'),
         os.path.dirname(os.path.dirname(os.path.abspath(__file__)))]
_MINE += os.environ.get('PRIVACY_NEEDLES', '').split(';')
NEEDLES = sorted({n.encode('utf-8') for n in _MINE if len(n) > 3} | {b'\\Users\\', b'/Users/'})


def hits(data: bytes) -> list[str]:
    return [n.decode() for n in NEEDLES if n in data]


def main() -> int:
    root = sys.argv[1]
    exe = next(os.path.join(root, f) for f in os.listdir(root) if f.endswith('.exe'))
    found = 0
    files = 0
    for dp, _d, fs in os.walk(root):
        for f in fs:
            p = os.path.join(dp, f)
            files += 1
            h = hits(open(p, 'rb').read())
            if h:
                found += 1
                print('file', os.path.relpath(p, root), h)
    ca = CArchiveReader(exe)
    mods = 0
    for name in ca.toc:
        data = ca.extract(name)
        if isinstance(data, (bytes, bytearray)):
            h = hits(bytes(data))
            if h:
                found += 1
                print('exe', name, h)
        if name.upper().startswith('PYZ'):
            tmp = os.path.join(tempfile.gettempdir(), 'ps2_pyz_scan.pyz')
            with open(tmp, 'wb') as fh:
                fh.write(ca.extract(name))
            z = ZlibArchiveReader(tmp)
            for mod in z.toc:
                try:
                    code = z.extract(mod)
                except Exception:                                  # noqa: BLE001
                    continue
                mods += 1
                blob = code if isinstance(code, (bytes, bytearray)) else marshal.dumps(code)
                h = hits(bytes(blob))
                if h:
                    found += 1
                    print('module', mod, h)
            os.remove(tmp)
    print(f'{files} files, {len(ca.toc)} archive entries, {mods} modules: {found} with personal strings')
    return 1 if found else 0


if __name__ == '__main__':
    raise SystemExit(main())
