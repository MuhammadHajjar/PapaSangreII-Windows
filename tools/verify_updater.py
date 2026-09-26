"""Prove the updater end to end, offline: a real HTTP server, a real zip, the
real PowerShell hand-off, started by the same ``updater.apply`` the game uses.

Nothing touches GitHub or the installed game.  A temporary folder - with a
space and Arabic in its name, the case a .cmd hand-off gets wrong - stands in
for an install, a local server for the release, and a child Python process
for the running game: it checks, plans, downloads and calls ``apply``, then
exits the way the game does.  The hand-off must then:

1. put in only what changed, and fetch only that (the unchanged library is
   not downloaded);
2. delete the file the new build dropped, from ``_internal`` only;
3. leave the player's ``config`` alone, even though the release zip tries to
   write one, and write nothing outside the folder;
4. start the game again and clear its staging folder.

Then the same with a server that refuses byte ranges (the whole zip comes
down), with a file held locked for a few seconds after the game quits (the
hand-off must wait it out), and with one held locked for good (the hand-off
must give up, put the old files back and start the old game).

    python tools/verify_updater.py          exits non-zero on the first failure
"""

from __future__ import annotations

import ctypes
import http.server
import json
import os
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from papasangre2.update import updater  # noqa: E402

WORK = os.path.join(tempfile.gettempdir(), 'ps2-updater-check')
OLD, NEW = '2026-09-26 number 2', '2026-09-27'
NEW_TAG = '2026-09-27'
failures: list = []


def check(ok: bool, what: str) -> None:
    print('  %-60s %s' % (what, 'yes' if ok else 'NO'))
    if not ok:
        failures.append(what)


def write(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as fh:
        fh.write(data if isinstance(data, bytes) else data.encode('utf-8'))


def read(path: str) -> bytes:
    with open(path, 'rb') as fh:
        return fh.read()


# ============================================================ the server
class Handler(http.server.SimpleHTTPRequestHandler):
    api = b''
    ranges = True
    served = 0                      # bytes of the zip handed out

    def do_GET(self):
        if self.path.startswith('/api'):
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(self.api)))
            self.end_headers()
            self.wfile.write(self.api)
            return
        path = self.translate_path(self.path)
        if not os.path.isfile(path):
            self.send_error(404)
            return
        size = os.path.getsize(path)
        asked = self.headers.get('Range')
        if not asked or not Handler.ranges:
            self.send_response(200)
            self.send_header('Content-Length', str(size))
            self.end_headers()
            with open(path, 'rb') as fh:
                data = fh.read()
            Handler.served += len(data)
            self.wfile.write(data)
            return
        first, _, last = asked.split('=', 1)[1].partition('-')
        start, end = int(first), min(int(last) if last else size - 1, size - 1)
        if start >= size:
            self.send_error(416)
            return
        self.send_response(206)
        self.send_header('Content-Range', 'bytes %d-%d/%d' % (start, end, size))
        self.send_header('Content-Length', str(end - start + 1))
        self.end_headers()
        with open(path, 'rb') as fh:
            fh.seek(start)
            data = fh.read(end - start + 1)
        Handler.served += len(data)
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def serve(directory: str):
    handler = lambda *a, **k: Handler(*a, directory=directory, **k)    # noqa: E731
    socketserver.TCPServer.allow_reuse_address = True
    server = socketserver.ThreadingTCPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, 'http://127.0.0.1:%d' % server.server_address[1]


# ======================================================= the two builds
LIBRARY = os.urandom(3 << 20)          # the same in both builds: must not be downloaded


def make_install(install: str) -> None:
    shutil.rmtree(install, ignore_errors=True)
    write(os.path.join(install, updater.GAME_EXE), b'the build the player has' * 1000)
    write(os.path.join(install, '_internal', 'python312.dll'), LIBRARY)
    write(os.path.join(install, '_internal', 'stale.pyd'), b'a file the new build drops')
    write(os.path.join(install, 'changelog.txt'), b'Changes in Papa Sangre II\n\n2026-09-26\n')
    write(os.path.join(install, 'config', 'progress.json'), b'{"lastLevelUnlocked": "ps2_9"}')
    write(os.path.join(install, 'config', 'settings.json'), b'{"blindIntro": false}')
    # what the hand-off starts again: a script that says it ran
    write(os.path.join(install, 'restarted.cmd'),
          '@echo off\r\necho %date% %time% > "%~dp0restarted.txt"\r\n')


def make_release(serve_dir: str) -> str:
    os.makedirs(serve_dir, exist_ok=True)
    name = updater.ASSET_NAME
    path = os.path.join(serve_dir, name)
    top = 'Papa Sangre II/'
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(top + updater.GAME_EXE, b'the build on GitHub' * 2000 + os.urandom(200000))
        zf.writestr(top + '_internal/python312.dll', LIBRARY)
        zf.writestr(top + '_internal/fresh.pyd', b'a file the new build adds')
        zf.writestr(top + 'changelog.txt', b'Changes in Papa Sangre II\n\n2026-09-27\nNew.\n')
        zf.writestr(top + 'config/progress.json', b'{"a release must never": "write this"}')
        zf.writestr(top + '../outside.txt', b'nor this')
    return path


CHILD = r'''
import json, os, sys
sys.path.insert(0, {root!r})
from papasangre2.util import paths
from papasangre2.update import updater, version
paths.FROZEN = True
paths.running_from_throwaway = lambda: False
sys.executable = os.path.join({install!r}, updater.GAME_EXE)
version.current = lambda: {old!r}
updater.restart_target = lambda: os.path.join({install!r}, 'restarted.cmd')
out = {{}}
release = updater.check({api!r})
out['offered'] = release.tag if release else None
plan = updater.build_plan(release)
out['whole'] = plan.fetch is None
out['fetch'] = sorted(r for r, _e in plan.fetch) if plan.fetch is not None else None
out['remove'] = plan.remove
updater.download(plan)
out['staging'] = plan.staging
out['downloaded'] = plan.downloaded
out['pending'] = updater.pending_update()[1]
out['remove_after'] = plan.remove
print(json.dumps(out))
sys.stdout.flush()
updater.apply(plan.staging, plan.remove)
'''


def run_scenario(title: str, ranges: bool = True, lock_for: float = 0.0,
                 lock_file: str = 'changelog.txt') -> None:
    print('\n' + title)
    install = os.path.join(WORK, 'Papa Sangre II لعبة')
    local = os.path.join(WORK, 'localappdata')
    serve_dir = os.path.join(WORK, 'serve')
    shutil.rmtree(local, ignore_errors=True)
    make_install(install)
    zip_path = make_release(serve_dir)
    server, base = serve(serve_dir)
    Handler.ranges, Handler.served = ranges, 0
    name = os.path.basename(zip_path)
    Handler.api = json.dumps({
        'tag_name': NEW_TAG, 'name': 'Test release', 'html_url': base,
        'body': 'Changelog line one.\nLine two.\n\nKeys: A and D walk.',
        'assets': [{'name': name, 'browser_download_url': '%s/%s' % (base, name),
                    'size': os.path.getsize(zip_path)}]}).encode()
    env = dict(os.environ, LOCALAPPDATA=local)
    code = CHILD.format(root=ROOT, install=install, old=OLD, api=base + '/api')
    old_exe = read(os.path.join(install, updater.GAME_EXE))
    old_log = read(os.path.join(install, 'changelog.txt'))

    handle = None
    target = os.path.join(install, lock_file)
    child = subprocess.run([sys.executable, '-c', code], env=env, capture_output=True, text=True,
                           encoding='utf-8', timeout=120)
    if lock_for:
        # held with no sharing, as a virus scanner would, from the moment the game has gone
        handle = ctypes.windll.kernel32.CreateFileW(target, 0x80000000, 0, None, 3, 0x80, None)
        check(handle not in (0, -1), 'the file is held locked, as a scanner would')
    if child.returncode != 0:
        print(child.stdout, child.stderr)
    check(child.returncode == 0, 'the game side checked, downloaded and handed over')
    try:
        result = json.loads(child.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        result = {}
    check(result.get('offered') == NEW_TAG, 'the newer release was offered')
    if ranges:
        check(result.get('fetch') == [updater.GAME_EXE, '_internal/fresh.pyd', 'changelog.txt'],
              'only the changed files were planned')
        check(Handler.served < os.path.getsize(zip_path) // 2,
              'far less than the whole zip was downloaded (%d of %d bytes)'
              % (Handler.served, os.path.getsize(zip_path)))
    else:
        check(result.get('whole') is True, 'ranges refused: the whole zip came down')
    check(result.get('remove_after') == ['_internal/stale.pyd'], 'only the dropped library is removed')
    check(result.get('pending') == NEW_TAG, 'the staged update counts as waiting')

    marker = os.path.join(install, 'restarted.txt')
    if handle and lock_for < 30:
        threading.Timer(lock_for, ctypes.windll.kernel32.CloseHandle, (handle,)).start()
    deadline = time.time() + 90
    while time.time() < deadline and not os.path.exists(marker):
        time.sleep(0.2)
    check(os.path.exists(marker), 'the game was started again')
    if handle and lock_for >= 30:
        ctypes.windll.kernel32.CloseHandle(handle)
    time.sleep(1.5)                         # the script clears its staging folder last
    server.shutdown()

    exe = read(os.path.join(install, updater.GAME_EXE))
    config = read(os.path.join(install, 'config', 'progress.json'))
    check(config == b'{"lastLevelUnlocked": "ps2_9"}', "the player's save was not touched")
    check(read(os.path.join(install, 'config', 'settings.json')) == b'{"blindIntro": false}',
          "the player's settings were not touched")
    check(not os.path.exists(os.path.join(WORK, 'outside.txt')), 'nothing was written outside the folder')
    check(read(os.path.join(install, '_internal', 'python312.dll')) == LIBRARY, 'the library is intact')
    if lock_for > 30:
        check(exe == old_exe, 'it gave up: the old game was put back')
        check(read(os.path.join(install, 'changelog.txt')) == old_log, 'the old changelog is there')
        check(os.path.exists(os.path.join(install, '_internal', 'stale.pyd')),
              'nothing was removed from the old build')
    else:
        check(exe.startswith(b'the build on GitHub'), 'the new game is in place')
        check(b'2026-09-27' in read(os.path.join(install, 'changelog.txt')), 'the new changelog is in place')
        check(os.path.exists(os.path.join(install, '_internal', 'fresh.pyd')), 'the new library is in')
        check(not os.path.exists(os.path.join(install, '_internal', 'stale.pyd')), 'the dropped one is gone')
        check(not os.path.exists(result.get('staging', '') or os.path.join(local, 'nothing')),
              'the staging folder was cleared')
    logtext = ''
    log_path = os.path.join(local, 'Papa Sangre II', 'updates', 'update.log')
    if os.path.exists(log_path):
        logtext = read(log_path).decode('utf-8', 'replace')
    check(('putting the old files back' in logtext) if lock_for > 30 else ('installed' in logtext),
          'the hand-off wrote what it did to update.log')
    if lock_for and lock_for < 30:
        check('attempt 1 failed' in logtext, 'it waited out the locked file')


def main() -> int:
    if os.name != 'nt':
        print('the hand-off is Windows only')
        return 0
    shutil.rmtree(WORK, ignore_errors=True)
    run_scenario('A normal update, only the changed files fetched')
    run_scenario('A server that refuses byte ranges', ranges=False)
    run_scenario('A file held locked for 4 seconds after the game quits', lock_for=4.0)
    run_scenario('A file held locked for good: the update is rolled back', lock_for=60.0)
    shutil.rmtree(WORK, ignore_errors=True)
    print('\n%s' % ('ALL GOOD' if not failures else '%d FAILED: %s' % (len(failures), '; '.join(failures))))
    return 1 if failures else 0




# ============================================ a real built exe, updating itself
def frozen(old_dir: str, new_zip: str) -> int:
    """``--frozen OLD_DIR NEW_ZIP``: copy the built game in OLD_DIR to a test
    folder (outside %TEMP%, which the game treats as throwaway), serve NEW_ZIP
    as the newest release, and run the old exe with ``--selftest-update``,
    silently.  It must hand over, the hand-off must put the new build in and
    start it; the new game is then closed.  %LOCALAPPDATA% points at the test
    folder throughout, so nothing of the player's is touched."""
    base_dir = os.path.join(ROOT, 'build', 'update-e2e')
    install = os.path.join(base_dir, 'Papa Sangre II تجربة')
    local = os.path.join(base_dir, 'localappdata')
    serve_dir = os.path.join(base_dir, 'serve')
    shutil.rmtree(base_dir, ignore_errors=True)
    shutil.copytree(old_dir, install)
    write(os.path.join(install, 'config', 'progress.json'), b'{"lastLevelUnlocked": "ps2_9"}')
    os.makedirs(serve_dir)
    shutil.copy2(new_zip, serve_dir)
    name = os.path.basename(new_zip)
    from papasangre2.update import version as _v
    with zipfile.ZipFile(new_zip) as zf:
        head = zf.read('Papa Sangre II/changelog.txt').decode('utf-8').splitlines()[2]
    tag = _v.tag(head)
    server, base = serve(serve_dir)
    Handler.ranges, Handler.served = True, 0
    Handler.api = json.dumps({'tag_name': tag, 'name': 'Test', 'body': 'Test.',
                              'assets': [{'name': name, 'size': os.path.getsize(new_zip),
                                          'browser_download_url': '%s/%s' % (base, name)}]}).encode()
    env = dict(os.environ, LOCALAPPDATA=local, PS2_UPDATE_API=base + '/api', PS2_SILENT='1')
    exe = os.path.join(install, updater.GAME_EXE)
    print('\nA built game updating itself (%s -> %s)' % (os.path.basename(old_dir), tag))
    old_exe = read(exe)
    t0 = time.time()
    run = subprocess.run([exe, '--selftest-update'], env=env, timeout=180)
    report = read(os.path.join(install, 'selftest-update.txt')).decode('utf-8', 'replace')
    print('    ' + report.strip().replace('\n', '\n    '))
    check(run.returncode == 0 and 'handed over' in report, 'the old exe checked, downloaded and handed over')
    with zipfile.ZipFile(new_zip) as zf:
        new_exe = zf.read('Papa Sangre II/' + updater.GAME_EXE)
        new_log = zf.read('Papa Sangre II/changelog.txt')
    deadline = time.time() + 120
    while time.time() < deadline:
        try:
            if read(exe) == new_exe:
                break
        except OSError:
            pass
        time.sleep(0.5)
    check(read(exe) == new_exe and read(exe) != old_exe, 'the new exe is in place')
    check(read(os.path.join(install, 'changelog.txt')) == new_log, 'the new changelog is in place')
    check(read(os.path.join(install, 'config', 'progress.json')) == b'{"lastLevelUnlocked": "ps2_9"}',
          "the player's save was not touched")
    check(Handler.served < os.path.getsize(new_zip), 'less than the whole zip came down (%d of %d bytes)'
          % (Handler.served, os.path.getsize(new_zip)))
    # the game the hand-off started again: find it, then close it
    started = False
    for _ in range(60):
        out = subprocess.run(['powershell', '-NoProfile', '-Command',
                              "Get-Process | Where-Object { $_.Path -eq '%s' } | "
                              "Select-Object -ExpandProperty Id" % exe.replace("'", "''")],
                             capture_output=True, text=True).stdout.split()
        if out:
            started = True
            time.sleep(3.0)                          # let it get going, then close it
            for pid in out:
                subprocess.run(['taskkill', '/PID', pid, '/F'], capture_output=True)
            break
        time.sleep(0.5)
    check(started, 'the new game was started again by the hand-off')
    logtext = read(os.path.join(local, 'Papa Sangre II', 'updates', 'update.log')).decode('utf-8', 'replace')
    check('installed; starting the game' in logtext, 'update.log says it went in')
    print('    took %.0f s' % (time.time() - t0))
    server.shutdown()
    time.sleep(1.0)
    shutil.rmtree(base_dir, ignore_errors=True)
    print('\n%s' % ('ALL GOOD' if not failures else '%d FAILED: %s' % (len(failures), '; '.join(failures))))
    return 1 if failures else 0


if __name__ == '__main__':
    if len(sys.argv) == 4 and sys.argv[1] == '--frozen':
        raise SystemExit(frozen(sys.argv[2], sys.argv[3]))
    raise SystemExit(main())
