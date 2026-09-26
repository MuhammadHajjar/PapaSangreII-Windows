"""Condensed full listing of one method: every branch, compare, call, ivar, constant."""
import re, sys
pat = re.compile(sys.argv[1])
src = sys.argv[2] if len(sys.argv) > 2 else 'dis/all.txt'
keep = re.compile(r'SEL |IVAR |@"|float|double|-> (?!_objc_(retain|release|autorelease|storeStrong|retainAutoreleasedReturnValue))|\b(cmp|cmn|fcmp|fcsel|csel|cset|b\.\w+|cbz|cbnz|tbz|tbnz|ret|fadd|fsub|fmul|fdiv|fcvt\w*|scvtf|fabs|fneg|fmov|add|sub)\b|^\S+\s+b\s')
p = False
for l in open(src, encoding='utf-8', errors='replace'):
    if l.startswith('====='):
        p = bool(pat.search(l))
        if p: print(l.strip())
        continue
    if not p or ' nop ' in l or 'x29, x29' in l or 'sp, sp' in l or 'x29, sp' in l: continue
    if keep.search(l):
        m = re.match(r'0x1000(\w+)\s+(\S+)\s+(.*)', l.rstrip())
        if m: print(m.group(1), m.group(2), re.sub(r'\s+', ' ', m.group(3))[:100])
