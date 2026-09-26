"""Print a compiled iOS nib: every object, or just its strings.

    python tools/nib.py PGEMenuHubViewController
    python tools/nib.py --text PGEMenuHubViewController
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
APP = os.path.join(os.path.dirname(HERE), 'reference', 'Payload', 'Papa Sangre II.app')

from papasangre2.assets.nib import decode, owners, strings   # noqa: E402

def main(argv):
    text_only = '--text' in argv
    names = [a for a in argv[1:] if not a.startswith('--')]
    for name in names:
        path = name if os.path.exists(name) else os.path.join(APP, name + '.nib')
        objs = decode(path)
        print('=====', os.path.basename(path), len(objs), 'objects')
        own = owners(objs)
        if text_only:
            for idx, cls, k, s in strings(objs):
                via = ', '.join('%s#%d.%s' % (oc, oi, ok) for oi, oc, ok in own.get(idx, []))
                print('  %-40r <- %s' % (s, via))
            continue
        for idx, (cls, vals) in enumerate(objs):
            print('#%d %s' % (idx, cls))
            for k, v in vals:
                if isinstance(v, bytes) and len(v) > 60:
                    v = v[:60] + b'...'
                print('    %s = %r' % (k, v))


if __name__ == '__main__':
    main(sys.argv)
