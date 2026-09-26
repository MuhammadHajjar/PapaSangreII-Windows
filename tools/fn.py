"""fn.py <selector-regex> [file=all]  -> print matching functions from tools/dis/<file>.txt"""
import re
import sys
import os
HERE = os.path.dirname(os.path.abspath(__file__))
pat = re.compile(sys.argv[1])
name = sys.argv[2] if len(sys.argv) > 2 else 'all'
width = int(sys.argv[3]) if len(sys.argv) > 3 else 140
p = False
for ln in open(os.path.join(HERE, 'dis', name + '.txt'), encoding='utf-8', errors='replace'):
    if ln.startswith('===== '):
        p = bool(pat.search(ln))
    if p:
        sys.stdout.write(ln[:width].rstrip('\n') + '\n')
