"""Resolve every objc_msgSend in the disassembly to (selector, string/selector args).

The compiler hoists selectors and constants into callee-saved registers and
reuses them, so a call site often carries no SEL comment of its own.  This
walks each method linearly, tracking what each register was last loaded with
(selector, CFString, class, float constant or small integer), follows plain
register moves, and clobbers x0-x18 / d0-d7 at every call.  Straight-line
tracking only: a value set on one side of a branch leaks into the other.  It
is a finding aid, not a proof - read the listing before relying on a row.

    python calls.py            -> dis/calls.txt
    python calls.py -q SEL     print call sites of selectors matching SEL
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / 'dis' / 'all.txt'
HEAD = re.compile(r'^===== ([+-]\[.+?\]|(?:BLOCK|FUNC)_0x[0-9a-f]+)  \((0x[0-9a-f]+)\)(?: from (.*?))? =====')
LINE = re.compile(r'^(0x[0-9a-f]+)  (\S+)\s+(.*?)\s*(?:; (.*))?$')

MSGSEND = ('_objc_msgSend', '_objc_msgSendSuper2', '_objc_msgSend_stret')


def _slot(ops):
    m = re.search(r'\[(sp|x29)(?:, #(-?0x[0-9a-f]+|-?\d+))?\]', ops)
    if not m:
        return None
    return '%s%s' % (m.group(1), m.group(2) or '0')


def walk(lines):
    regs = {}
    slots = {}          # stack spill slots: 'sp0x108' -> value
    out = []
    for addr, mn, ops, cmt in lines:
        cmt = cmt or ''
        parts = [p.strip() for p in ops.split(',')]
        dst = parts[0] if parts else ''
        if dst.startswith('w'):
            dst = 'x' + dst[1:]
        m = re.search(r'SELREF "([^"]+)"', cmt)
        if m:
            regs[dst] = 'SELREF:' + m.group(1)
            continue
        if mn in ('str', 'stur') and len(parts) >= 2:
            sl = _slot(ops)
            src = parts[0] if not parts[0].startswith('w') else 'x' + parts[0][1:]
            if sl:
                slots[sl] = regs.get(src)
            continue
        if mn == 'stp' and len(parts) >= 3:
            m2 = re.search(r'\[(sp|x29), #(-?0x[0-9a-f]+|-?\d+)\]$', ops)
            if m2 and not ops.endswith('!'):
                base, off = m2.group(1), int(m2.group(2), 16) if 'x' in m2.group(2) else int(m2.group(2))
                slots['%s%s' % (base, hex(off) if off >= 0 else '-' + hex(-off))] = regs.get(parts[0])
                slots['%s%s' % (base, hex(off + 8) if off + 8 >= 0 else '-' + hex(-(off + 8)))] = regs.get(parts[1])
            continue
        if mn in ('ldr', 'ldur') and len(parts) >= 2 and not cmt:
            m2 = re.match(r'\[(x\d+)(?:, #0)?\]$', ', '.join(parts[1:]))
            if m2 and (regs.get(m2.group(1)) or '').startswith('SELREF:'):
                regs[dst] = 'SEL:' + regs[m2.group(1)][7:]
                continue
            sl = _slot(ops)
            if sl:
                regs[dst] = slots.get(sl)
                continue
        m = re.search(r'SEL "([^"]+)"', cmt)
        if m and mn.startswith('ldr'):
            regs[dst] = 'SEL:' + m.group(1)
            continue
        m = re.search(r'@"([^"]*)"', cmt)
        if m and mn in ('add', 'ldr', 'adr'):
            regs[dst] = '@"%s"' % m.group(1)
            continue
        m = re.search(r'CLASS (\S+)', cmt)
        if m:
            regs[dst] = 'CLASS:' + m.group(1)
            continue
        m = re.search(r'(float|double) (\S+)', cmt)
        if m:
            regs[dst] = m.group(2)
            continue
        if mn == 'fmov' and re.search(r'#[-\d.e]+$', ops):
            regs[dst] = ops.split('#')[-1]
            continue
        if mn in ('mov', 'movz', 'orr') and len(parts) >= 2:
            src = parts[-1]
            if src.startswith('w'):
                src = 'x' + src[1:]
            if src.startswith('#'):
                regs[dst] = src
            elif src in ('xzr', 'wzr'):
                regs[dst] = '#0'
            else:
                regs[dst] = regs.get(src)
            continue
        if mn == 'fmov' and len(parts) == 2:
            regs[dst] = regs.get(parts[1])
            continue
        if mn in ('bl', 'b') and '->' in cmt:
            callee = cmt.split('->', 1)[1].strip()
            if callee in MSGSEND:
                sel = regs.get('x1') or '?'
                args = [regs.get('x%d' % i) for i in range(2, 6)]
                fargs = [regs.get('d%d' % i) or regs.get('s%d' % i) for i in range(0, 3)]
                out.append((addr, sel, args, fargs, callee))
            else:
                out.append((addr, 'CALL:' + callee, [regs.get('x0'), regs.get('x1'), regs.get('x2')],
                            [regs.get('d0') or regs.get('s0')], callee))
            for i in range(0, 19):
                regs.pop('x%d' % i, None)
            for i in range(0, 8):
                regs.pop('d%d' % i, None)
                regs.pop('s%d' % i, None)
            continue
        # any other write to dst invalidates it
        if dst and re.match(r'^[xwsd]\d+$', dst) and mn not in ('str', 'strb', 'stp', 'stur', 'cmp', 'cmn', 'fcmp', 'tst', 'cbz', 'cbnz', 'tbz', 'tbnz'):
            regs.pop(dst, None)
    return out


def load(paths=None):
    funcs = {}
    cur = None
    for path in paths or (SRC, HERE / 'dis' / 'blocks.txt'):
      for raw in open(path, encoding='utf-8', errors='replace'):
        m = HEAD.match(raw)
        if m:
            cur = m.group(1)
            if m.group(3):
                cur += ' {in %s}' % m.group(3).split(';')[0]
            funcs[cur] = []
            continue
        if cur:
            m = LINE.match(raw.rstrip('\n'))
            if m:
                funcs[cur].append(m.groups())
    return funcs


def fmt(fn, row):
    addr, sel, args, fargs, callee = row
    a = ' '.join(x for x in (args or []) if x)
    f = ' '.join('f=' + x for x in (fargs or []) if x)
    return '%s %s %s | %s %s' % (addr, fn, sel.replace('SEL:', ''), a, f)


if __name__ == '__main__':
    funcs = load()
    if len(sys.argv) > 2 and sys.argv[1] == '-q':
        pat = re.compile(sys.argv[2])
        for fn, lines in funcs.items():
            for row in walk(lines):
                if pat.search(row[1]):
                    print(fmt(fn, row))
    else:
        with open(HERE / 'dis' / 'calls.txt', 'w', encoding='utf-8') as f:
            for fn, lines in funcs.items():
                for row in walk(lines):
                    f.write(fmt(fn, row) + '\n')
        print('wrote dis/calls.txt')
