"""Compact reading view of methods: ivars touched, calls in order, constants.

    python sig.py REGEX [--ps1]      methods whose name matches REGEX

For each method: every ivar it names (with the instruction that used the
offset), every resolved call with its string/selector/number arguments,
branch-free float constants, and the same for any block it owns.  Noise
(retain/release/autorelease, enumeration plumbing) is dropped.  This is a
reading aid for triage; exact control flow still needs the full listing
(`fn.sh` / summ.py).
"""
import re
import sys
from pathlib import Path

from calls import load, walk

HERE = Path(__file__).resolve().parent
NOISE = re.compile(r'CALL:_objc_(retain|release|autorelease|storeStrong|loadWeak|initWeak|destroyWeak|copyWeak|'
                   r'retainAutoreleasedReturnValue|autoreleaseReturnValue|retainAutorelease|'
                   r'enumerationMutation)|CALL:__Unwind|CALL:___stack_chk|countByEnumeratingWithState|'
                   r'CALL:__Block_object')


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    ps1 = '--ps1' in sys.argv
    paths = ((HERE / 'dis' / 'ps1_all.txt', HERE / 'dis' / 'ps1_blocks.txt') if ps1
             else (HERE / 'dis' / 'all.txt', HERE / 'dis' / 'blocks.txt'))
    funcs = load(paths)
    pat = re.compile(args[0])
    for fn, lines in funcs.items():
        if not pat.search(fn):
            continue
        print('\n##', fn, '(%d ins)' % len(lines))
        ivars = []
        consts = []
        for addr, mn, ops, cmt in lines:
            m = re.search(r'IVAR (\S+?)=\d+', cmt or '')
            if m:
                ivars.append(m.group(1).split('.', 1)[1])
            m = re.search(r'(float|double) (\S+)', cmt or '')
            if m:
                consts.append('%s@%s' % (m.group(2), addr[-5:]))
            if mn == 'fmov' and re.search(r'#[-\d.e]+$', ops):
                consts.append('%s@%s' % (ops.split('#')[-1], addr[-5:]))
        if ivars:
            seen = []
            for v in ivars:
                if v not in seen:
                    seen.append(v)
            print('  ivars:', ', '.join(seen))
        if consts:
            print('  consts:', ' '.join(consts))
        for addr, sel, a, f, callee in walk(lines):
            if NOISE.search(sel):
                continue
            s = sel.replace('SEL:', '')
            argtxt = ' '.join(x for x in a if x)
            ftxt = ' '.join('f=' + x for x in f if x)
            print('  %s %s %s %s' % (addr[-5:], s, argtxt, ftxt))


if __name__ == '__main__':
    main()
