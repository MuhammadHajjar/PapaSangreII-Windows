"""Check that the port reads every piece of Papa Sangre II's content the way the
original engine would.

Loads the 23 shipped maps and the 19 developer test maps with the port's
loader (`papasangre2.assets.tiled`, which follows `createObjectFromDict:`),
then checks everything the data refers to: messages, agents, levels, paths and
sounds.  Every oddity is sorted into a category with a reason - a reason means
the original behaves that way too and the port reproduces it; no reason means a
gap in the port's understanding, and the check fails.

Writes `CONTENT_CHECK.md` next to the executable.

Built as ``Check game content.exe``.
"""

from __future__ import annotations

import os
import sys
from collections import Counter

if __package__ in (None, ''):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from papasangre2.assets import audit                            # noqa: E402
from papasangre2.util import console, paths                     # noqa: E402


def main(rep) -> int:
    rep.show('Papa Sangre II - game content check')
    rep.show('=' * 46)
    bundle = audit.bundle_dir()
    rep.show(f'game data      : {bundle}')
    if not os.path.isdir(os.path.join(bundle, 'levels')):
        rep.say('The game data is missing, so there is nothing to check.')
        return 1
    rep.show()

    rep.say('Checking. This takes a few seconds.')
    r = audit.run(bundle)

    rep.show(f'shipped levels       : {len(r.shipped)}')
    rep.show(f'developer test maps  : {len(r.tests)}')
    rep.show(f'findings             : {len(r.findings)}')
    rep.show()
    for cat, n in sorted(Counter(f.category for f in r.findings).items()):
        bad = sum(1 for f in r.findings if f.category == cat and not f.reason)
        rep.show(f'  {cat:<40} {n:>5}' + (f'   {bad} UNEXPLAINED' if bad else ''))
    rep.show()

    # next to the exe; from source, the committed copy in docs/
    if paths.FROZEN:
        out = os.path.join(paths.writable_root(), 'CONTENT_CHECK.md')
    else:
        out = os.path.join(paths.resource_root(), 'docs', 'CONTENT_CHECK.md')
    audit.write_report(r, out)
    rep.show(f'report written to {out}')
    rep.show()

    bad = r.unexplained
    if bad:
        for f in bad[:40]:
            rep.show(f'  UNEXPLAINED  {f.level}  {f.category}  {f.where}: {f.detail}')
        if len(bad) > 40:
            rep.show(f'  ... {len(bad) - 40} more in the report')
        rep.say(f'Content check failed: {len(bad)} findings have no explanation. '
                'See the report.')
        return 1
    rep.say(f'Content check passed. {len(r.shipped)} levels and {len(r.tests)} test '
            f'maps read; {len(r.findings)} oddities, every one explained.')
    return 0


if __name__ == '__main__':
    raise SystemExit(console.run(main))
