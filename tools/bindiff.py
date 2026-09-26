"""Method-by-method comparison of the Papa Sangre 1 and Papa Sangre II engines.

Both binaries are dumped with psdis.py into dis/all.txt.  Each Objective-C
method body is normalised so that things that legitimately differ between two
builds of the same source - absolute addresses, page offsets, ivar offsets,
branch targets - compare equal, while anything that changes behaviour - a
selector, an ivar name, a string, a float constant, an immediate, the order or
kind of instructions - does not.

    python bindiff.py              summary table for the PGE / S3D classes
    python bindiff.py -v SEL       normalised side-by-side diff of one method

Output: docs/ENGINE_DIFF.md (written by --report).
"""
import difflib
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
PS1 = HERE / 'dis' / 'ps1_all.txt'   # regenerated here with the fixed psdis.py
PS2 = HERE / 'dis' / 'all.txt'

HEAD = re.compile(r'^===== ([+-])\[(\S+) (.+?)\]  \((0x[0-9a-f]+)\) =====')
LINE = re.compile(r'^(0x[0-9a-f]+)  (\S+)\s+(.*?)\s*(?:; (.*))?$')


def load(path):
    funcs = {}
    cur = None
    for raw in open(path, encoding='utf-8', errors='replace'):
        raw = raw.rstrip('\n')
        m = HEAD.match(raw)
        if m:
            kind, cls, sel, addr = m.groups()
            cur = (kind, cls, sel)
            funcs[cur] = dict(addr=int(addr, 16), lines=[])
            continue
        if cur is None:
            continue
        m = LINE.match(raw)
        if m:
            funcs[cur]['lines'].append(m.groups())
    return funcs


def _fold(lines):
    """Remove codegen differences between Xcode 6.3 (PS2) and 7.2 (PS1):
    `nop` padding after adrp, and selectors loaded as `add xN, SELREF` then
    `ldr xM, [xN]` instead of one `ldr xM, [page]` - fold those into the
    single-load form.  Block literal addresses are not meaningful either."""
    out = []
    pending = {}
    for addr, mn, ops, cmt in lines:
        cmt = cmt or ''
        if mn == 'nop':
            continue
        m = re.search(r'SELREF "([^"]+)"', cmt)
        if m and mn == 'add':
            pending[ops.split(',')[0].strip()] = m.group(1)
            continue
        if mn == 'ldr' and not cmt:
            m2 = re.match(r'(\w+), \[(\w+)\]$', ops)
            if m2 and m2.group(2) in pending:
                out.append((addr, 'ldr', '%s, [x8, #OFF]' % m2.group(1), 'SEL "%s"' % pending.pop(m2.group(2))))
                continue
        if mn == 'adr':
            ops = re.sub(r'#0x[0-9a-f]+', '#BLOCK', ops)
        out.append((addr, mn, ops, cmt))
    return out


def normalise(fn):
    """Return a list of comparable tokens, one per instruction."""
    base = fn['addr']
    out = []
    for addr, mn, ops, cmt in _fold(fn['lines']):
        cmt = cmt or ''
        # symbolic comments carry the meaning; strip the numbers inside them
        cmt = re.sub(r'(IVAR \S+?)=\d+', r'\1', cmt)
        cmt = re.sub(r'\[0x[0-9a-f]+\]=0x[0-9a-f]+', '[mem]', cmt)
        if cmt.startswith('0x') or cmt.startswith('-> 0x'):
            cmt = ''
        o = ops
        if mn in ('adrp',):
            o = re.sub(r'#0x[0-9a-f]+', '#PAGE', o)
        elif mn == 'add' and cmt:
            o = re.sub(r'#0x[0-9a-f]+$', '#OFF', o)
        elif mn in ('ldr', 'ldrsw', 'str') and cmt:
            o = re.sub(r'#0x[0-9a-f]+\]', '#OFF]', o)
        if mn in ('b', 'bl') or mn.startswith('b.') or mn in ('cbz', 'cbnz', 'tbz', 'tbnz'):
            # relative branch targets: keep only direction (internal) or callee
            def rel(m):
                t = int(m.group(1), 16)
                return '#REL%+d' % (t - base) if not cmt else '#CALL'
            o = re.sub(r'#(0x[0-9a-f]+)', rel, o)
            if not cmt and mn in ('b', 'bl'):
                o = '#LOCAL'
            elif not cmt:
                o = re.sub(r'#REL[+-]\d+', '#LOCAL', o)
        if mn == 'ldr' and re.search(r'#0x[0-9a-f]+$', o) and ('float' in cmt or 'double' in cmt):
            o = re.sub(r'#0x[0-9a-f]+$', '#LIT', o)
        out.append('%s %s%s' % (mn, o, ('   ; ' + cmt) if cmt else ''))
    return out


def semseq(fn):
    """Ordered sequence of everything that carries meaning: selectors, ivars,
    strings, callees, float constants and immediates in arithmetic/compares.
    Two bodies with the same sequence differ only in register allocation and
    instruction scheduling."""
    seq = []
    for _, mn, ops, cmt in _fold(fn['lines']):
        cmt = cmt or ''
        for pat in (r'SEL "([^"]+)"', r'IVAR (\S+?)=', r'@"([^"]*)"', r'-> (_\S+|[+-]\[.*\])',
                    r'(float \S+)', r'(double \S+)', r'CLASS (\S+)', r'^"(.*)"$'):
            for m in re.finditer(pat, cmt):
                v = m.group(1)
                if v.startswith('_objc_retain') or v.startswith('_objc_release') or v in (
                        '_objc_autoreleaseReturnValue', '_objc_retainAutoreleasedReturnValue',
                        '_objc_storeStrong', '_objc_retainAutorelease', '_objc_autorelease'):
                    continue
                seq.append(v)
        if mn == 'fmov' and '#' in ops and re.search(r'#[-\d.e]+$', ops):
            seq.append('fmov ' + ops.split('#')[-1])
        if mn in ('cmp', 'cmn', 'fcmp', 'mov', 'movz', 'movk', 'orr') and re.search(r'#(0x[0-9a-f]+|-?\d+)$', ops) and not cmt:
            seq.append(mn + ' ' + ops.split('#')[-1])
    return seq


def classes_of_interest(funcs):
    return sorted({c for (_, c, _) in funcs if c.startswith(('PGE', 'S3D'))})


def compare():
    f1 = load(PS1)
    f2 = load(PS2)
    rows = []
    for cls in sorted(set(classes_of_interest(f1)) | set(classes_of_interest(f2))):
        m1 = {(k, s): f for (k, c, s), f in f1.items() if c == cls}
        m2 = {(k, s): f for (k, c, s), f in f2.items() if c == cls}
        for key in sorted(set(m1) | set(m2), key=lambda x: x[1]):
            a, b = m1.get(key), m2.get(key)
            if a and not b:
                rows.append((cls, key, 'PS1 only', 0.0, len(a['lines']), 0, a, b))
            elif b and not a:
                rows.append((cls, key, 'PS2 only', 0.0, 0, len(b['lines']), a, b))
            else:
                na, nb = normalise(a), normalise(b)
                if na == nb:
                    rows.append((cls, key, 'same', 1.0, len(na), len(nb), a, b))
                elif semseq(a) == semseq(b):
                    rows.append((cls, key, 'same refs', 1.0, len(na), len(nb), a, b))
                else:
                    r = difflib.SequenceMatcher(None, na, nb, autojunk=False).ratio()
                    rows.append((cls, key, 'changed', r, len(na), len(nb), a, b))
    return f1, f2, rows


def semantic_delta(a, b):
    """Selectors / ivars / strings / floats referenced by one side and not the other."""
    def refs(fn):
        s = set()
        for _, mn, ops, cmt in fn['lines']:
            if not cmt:
                continue
            for pat in (r'SEL "([^"]+)"', r'IVAR (\S+?)=', r'@"([^"]*)"', r'-> (\S+)',
                        r'(float \S+)', r'(double \S+)', r'(#\S+)$', r'CLASS (\S+)'):
                for m in re.finditer(pat, cmt):
                    s.add(m.group(1))
        return s
    ra, rb = refs(a), refs(b)
    return sorted(ra - rb), sorted(rb - ra)


def report(path):
    f1, f2, rows = compare()
    by_cls = defaultdict(list)
    for r in rows:
        by_cls[r[0]].append(r)
    L = []
    L.append('# Engine diff: Papa Sangre 1 (engine 1.1.020) vs Papa Sangre II (1.1.013)\n')
    L.append('Generated by `tools/bindiff.py --report`. Do not edit by hand.\n')
    L.append('Every Objective-C method of every `PGE*` / `S3D*` class in either binary, '
             'normalised (addresses, page offsets, ivar offsets and branch targets '
             'removed; selectors, ivar names, strings, float constants and immediates '
             'kept) and compared.\n')
    L.append('* **same** - normalised bodies identical. The PS1 port\'s reading holds.')
    L.append('* **changed** - bodies differ. Similarity ratio given; the refs columns '
             'list the selectors / ivars / strings / constants only one side uses. '
             'Every one of these must be read before PS1 code is trusted for it.')
    L.append('* **same refs** - every selector, ivar, string, callee, float constant and '
             'compared/moved immediate appears in the same order; only register '
             'allocation or scheduling differs (PS2 was built with Xcode 6.3, PS1 with 7.2). '
             'Treated as unchanged, but a data-flow change that reuses the same '
             'references in the same order would hide here.')
    L.append('* **PS1 only** / **PS2 only** - the method exists in one engine.\n')
    tot = defaultdict(int)
    for r in rows:
        tot[r[2]] += 1
    L.append('Totals: ' + ', '.join('%s %d' % kv for kv in sorted(tot.items())) + '\n')
    L.append('## Per-class summary\n')
    L.append('| class | same | same refs | changed | PS1 only | PS2 only |')
    L.append('|---|---|---|---|---|---|')
    for cls, rs in sorted(by_cls.items()):
        c = defaultdict(int)
        for r in rs:
            c[r[2]] += 1
        L.append('| %s | %d | %d | %d | %d | %d |' % (cls, c['same'], c['same refs'], c['changed'], c['PS1 only'], c['PS2 only']))
    L.append('')
    for cls, rs in sorted(by_cls.items()):
        interesting = [r for r in rs if r[2] not in ('same', 'same refs')]
        if not interesting:
            continue
        L.append('## %s\n' % cls)
        same = [r for r in rs if r[2] == 'same']
        if same:
            L.append('Unchanged (%d): %s\n' % (len(same), ', '.join('`%s%s`' % (r[1][0], r[1][1]) for r in same)))
        L.append('| method | verdict | ratio | PS1 ins | PS2 ins | PS1 addr | PS2 addr | only in PS1 | only in PS2 |')
        L.append('|---|---|---|---|---|---|---|---|---|')
        for cls_, key, verdict, ratio, n1, n2, a, b in interesting:
            d1 = d2 = ''
            if a and b and verdict == 'changed':
                x, y = semantic_delta(a, b)
                d1 = ', '.join('`%s`' % s for s in x[:12]) + (' ...' if len(x) > 12 else '')
                d2 = ', '.join('`%s`' % s for s in y[:12]) + (' ...' if len(y) > 12 else '')
            L.append('| `%s%s` | %s | %s | %d | %d | %s | %s | %s | %s |' % (
                key[0], key[1], verdict, ('%.2f' % ratio) if verdict == 'changed' else '',
                n1, n2, ('0x%x' % a['addr']) if a else '', ('0x%x' % b['addr']) if b else '',
                d1.replace('|', '\\|'), d2.replace('|', '\\|')))
        L.append('')
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text('\n'.join(L), encoding='utf-8')
    print('wrote', path, dict(tot))


def show(selpat):
    f1 = load(PS1)
    f2 = load(PS2)
    for key in sorted(set(f1) | set(f2)):
        if not re.search(selpat, '%s[%s %s]' % key):
            continue
        a, b = f1.get(key), f2.get(key)
        print('#####', '%s[%s %s]' % key)
        na = normalise(a) if a else []
        nb = normalise(b) if b else []
        for line in difflib.unified_diff(na, nb, 'PS1', 'PS2', lineterm='', n=2):
            print(line)


if __name__ == '__main__':
    if len(sys.argv) > 2 and sys.argv[1] == '-v':
        show(sys.argv[2])
    else:
        report(HERE.parent / 'docs' / 'ENGINE_DIFF.md')
