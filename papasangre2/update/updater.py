"""PORT ADDITION: find, fetch and install a new build of the port from GitHub.

The iOS game was updated by the App Store; this is the Windows answer.  It is
the design the Audio Defence port ships, fitted to this game's folder.

**Progress cannot be lost.**  The player's settings and save are in
``config`` beside the exe (or in ``%LOCALAPPDATA%\\Papa Sangre II`` when the
game cannot write there).  An update only writes the files the release zip
carries - the exe, ``_internal`` and ``changelog.txt`` - and only ever deletes
inside ``_internal``, which a build owns completely.  ``config`` and anything
else a player keeps in the folder are never touched.

**Only what changed is downloaded.**  The release zip's own index carries a
CRC-32 per file; it is read over HTTP (``remotezip``) and compared with what
is installed, so a build that changes the exe alone downloads the exe alone.
If byte ranges are refused, the whole zip is fetched and the same comparison
made against it.

**The swap happens after the game has closed.**  A running program holds its
exe and DLLs, so the changed files are staged in
``%LOCALAPPDATA%\\Papa Sangre II\\updates``, the files they replace are backed
up beside them, and a small PowerShell script waits for the game to exit,
copies the files in (retrying for a while, in case an antivirus scanner is
holding one), checks each one arrived whole, and starts the game again.  If it
cannot finish, it puts the backup back and starts the old game.  PowerShell
rather than a .cmd because a folder name may hold non-ASCII characters.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
import zlib

from ..util import paths
from . import version
from .remotezip import RemoteZip, RemoteZipError, USER_AGENT

REPOSITORY = 'MuhammadHajjar/PapaSangreII-Windows'
LATEST_RELEASE = 'https://api.github.com/repos/%s/releases/latest' % REPOSITORY
RELEASES_PAGE = 'https://github.com/%s/releases' % REPOSITORY
#: the release zip's name, the same on every release, so one link always
#: gives the newest: .../releases/latest/download/PapaSangreII-Windows.zip
ASSET_NAME = 'PapaSangreII-Windows.zip'
#: what the first releases called it, with the version after a dash
ASSET_PREFIX = 'PapaSangreII-Windows-'
LATEST_DOWNLOAD = 'https://github.com/%s/releases/latest/download/%s' % (REPOSITORY, ASSET_NAME)
GAME_EXE = 'Play Papa Sangre II.exe'
TIMEOUT = 20
CHUNK = 1 << 20

#: the folders a build owns completely: the only places a file is ever deleted from
OWNED_DIRS = ('_internal/',)
#: never written, whatever a release zip holds
NEVER_WRITTEN = ('config/',)
#: written into a staging folder once all of it has arrived and been checked
READY_MARKER = 'ready.json'


class UpdateError(Exception):
    """Something the player should be told, in words they can act on."""


class Release:
    """GitHub's answer about the newest release."""

    def __init__(self, data: dict):
        self.tag = str(data.get('tag_name') or '')
        self.name = str(data.get('name') or self.tag)
        self.notes = str(data.get('body') or '').strip()
        self.url = str(data.get('html_url') or RELEASES_PAGE)
        self.asset_name = ''
        self.asset_url = ''
        self.asset_size = 0
        zips = [a for a in data.get('assets') or () if str(a.get('name', '')).lower().endswith('.zip')]
        ours = [a for a in zips if str(a.get('name', '')).lower() == ASSET_NAME.lower()] or \
            [a for a in zips if str(a.get('name', '')).lower().startswith(ASSET_PREFIX.lower())]
        pick = ours[0] if ours else (zips[0] if len(zips) == 1 else None)
        if pick is not None:
            self.asset_name = str(pick.get('name'))
            self.asset_url = str(pick.get('browser_download_url') or '')
            self.asset_size = int(pick.get('size') or 0)

    def changes(self) -> str:
        """The notes up to the first blank line: the changelog lines, not the keys after them."""
        return self.notes.replace('\r\n', '\n').split('\n\n', 1)[0].strip()

    def __repr__(self) -> str:
        return '<Release %s %s>' % (self.tag, self.asset_name or 'no zip')


class Plan:
    """What installing a release changes here."""

    def __init__(self, release: Release):
        self.release = release
        self.fetch: list | None = []        # (relative path, remote entry); None = fetch the whole zip
        self.remove: list = []              # files this build has in _internal and the new one lacks
        self.unchanged = 0
        self.staging = ''
        self.archive = None
        self.downloaded = 0

    @property
    def download_size(self) -> int:
        if self.fetch is None:
            return self.release.asset_size
        return sum(e.compressed_size for _r, e in self.fetch)

    @property
    def nothing_to_do(self) -> bool:
        return self.fetch is not None and not self.fetch and not self.remove


# ================================================================== where things are
def install_dir() -> str:
    return os.path.dirname(os.path.abspath(sys.executable))


def user_dir() -> str:
    """Where the update machinery keeps its files: never inside the game's folder."""
    base = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~')
    return os.path.join(base, 'Papa Sangre II')


def updates_dir() -> str:
    path = os.path.join(user_dir(), 'updates')
    os.makedirs(path, exist_ok=True)
    return path


def restart_target() -> str:
    """The exe to start again: the release's own, where the player has not renamed theirs."""
    named = os.path.join(install_dir(), GAME_EXE)
    return named if os.path.isfile(named) else os.path.abspath(sys.executable)


def log(message: str) -> None:
    """One line into updates/update.log - what went on, for a bug report."""
    try:
        path = os.path.join(updates_dir(), 'update.log')
        if os.path.isfile(path) and os.path.getsize(path) > 256 * 1024:
            os.replace(path, path + '.old')
        with open(path, 'a', encoding='utf-8') as fh:
            fh.write('%s %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), message))
    except OSError:
        pass


def can_update() -> tuple:
    """(allowed, why not, as a sentence ending the player's announcement)."""
    if not paths.FROZEN:
        return False, 'this is the source version, which updates with git'
    if sys.platform == 'darwin':
        return False, ('the Mac version does not update by itself yet. '
                       'Download the newest from the releases page on GitHub')
    if os.name != 'nt':
        return False, 'updating by itself only works on Windows'
    if paths.running_from_throwaway():
        return False, ('the game is running from inside the zip or from a temporary folder. '
                       'Extract it to a folder of its own first')
    try:
        probe = os.path.join(install_dir(), '.update-probe')
        with open(probe, 'w', encoding='utf-8') as fh:
            fh.write('')
        os.remove(probe)
    except OSError:
        return False, 'the game is in a folder it cannot write to. Move it out of Program Files'
    return True, ''


# ======================================================================= the check
def _api(url: str) -> dict:
    request = urllib.request.Request(url, headers={'Accept': 'application/vnd.github+json',
                                                   'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise UpdateError('there are no releases to update to yet') from exc
        if exc.code in (403, 429):
            raise UpdateError('GitHub is asking us to wait before checking again. Try later') from exc
        raise UpdateError('GitHub answered with error %d' % exc.code) from exc
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise UpdateError('could not reach GitHub. Check your internet connection') from exc
    except ValueError as exc:
        raise UpdateError('GitHub sent something we could not read') from exc


def check(url: str | None = None) -> Release | None:
    """The newest release when it is newer than this build, else None.  Worker thread."""
    release = Release(_api(url or LATEST_RELEASE))
    if not release.tag:
        raise UpdateError('the newest release has no version')
    here = version.current()
    if not version.is_newer(release.tag, here):
        log('checked: %s is the newest, this is %s' % (release.tag, here))
        return None
    if not release.asset_url:
        raise UpdateError('version %s has no zip to download' % version.text(release.tag))
    log('checked: %s is available, this is %s' % (release.tag, here))
    return release


# ======================================================================== the plan
def _crc(path: str) -> int | None:
    try:
        crc = 0
        with open(path, 'rb') as fh:
            while True:
                block = fh.read(CHUNK)
                if not block:
                    return crc
                crc = zlib.crc32(block, crc)
    except OSError:
        return None


def _strip_prefix(names) -> str:
    """A zip made to be extracted has one folder inside ('Papa Sangre II/')."""
    tops = {n.split('/', 1)[0] for n in names if '/' in n}
    if len(tops) == 1 and not any('/' not in n for n in names):
        return tops.pop() + '/'
    return ''


def _safe(relative: str) -> bool:
    """A member we may write: inside the folder, and not the player's own files."""
    parts = relative.split('/')
    if not relative or relative.startswith('/') or ':' in relative or '..' in parts:
        return False
    return not any(relative.lower().startswith(n) for n in NEVER_WRITTEN)


def _stale_files(root: str, wanted: set) -> list:
    stale = []
    for owned in OWNED_DIRS:
        base = os.path.join(root, owned.rstrip('/'))
        if not os.path.isdir(base):
            continue
        for dirpath, _dirs, files in os.walk(base):
            for name in files:
                rel = os.path.relpath(os.path.join(dirpath, name), root).replace(os.sep, '/')
                if rel not in wanted:
                    stale.append(rel)
    return sorted(stale)


def build_plan(release: Release, cancelled=None) -> Plan:
    """Compare the release's index with what is installed.  Worker thread."""
    plan = Plan(release)
    root = install_dir()
    try:
        archive = RemoteZip(release.asset_url, release.asset_size or None)
    except (RemoteZipError, urllib.error.URLError, OSError, TimeoutError) as exc:
        log('reading the index in pieces did not work (%s): the whole zip will come down' % exc)
        plan.fetch = None
        return plan
    members = archive.files()
    prefix = _strip_prefix(list(archive.entries))
    plan.archive = archive
    wanted = set()
    for name, entry in members.items():
        if cancelled is not None and cancelled():
            raise UpdateError('cancelled')
        rel = name[len(prefix):] if prefix and name.startswith(prefix) else name
        if not rel or rel.endswith('/'):
            continue
        if not _safe(rel):
            log('skipping %s: not a file an update may write' % rel)
            continue
        wanted.add(rel)
        if _crc(os.path.join(root, rel.replace('/', os.sep))) == entry.crc:
            plan.unchanged += 1
        else:
            plan.fetch.append((rel, entry))
    if GAME_EXE not in wanted:
        raise UpdateError('the download for version %s does not hold the game'
                          % version.text(release.tag))
    plan.remove = _stale_files(root, wanted)
    log('plan for %s: %d to fetch (%d bytes), %d unchanged, %d to remove' % (
        release.tag, len(plan.fetch), plan.download_size, plan.unchanged, len(plan.remove)))
    return plan


# ==================================================================== the download
def _stop(cancelled) -> None:
    if cancelled is not None and cancelled():
        raise UpdateError('cancelled')


def download(plan: Plan, progress=None, cancelled=None) -> str:
    """Fetch what the plan needs into a staging folder, check it, mark it ready.
    ``progress(done, total)``; ``cancelled()`` stops it.  Worker thread."""
    staging = os.path.join(updates_dir(), version.tag(plan.release.tag) or 'update')
    shutil.rmtree(staging, ignore_errors=True)
    payload = os.path.join(staging, 'payload')
    os.makedirs(payload, exist_ok=True)
    plan.staging = staging
    try:
        if plan.fetch is None:
            _download_whole_archive(plan, payload, progress, cancelled)
        else:
            _download_changed_members(plan, payload, progress, cancelled)
    except RemoteZipError as exc:
        shutil.rmtree(staging, ignore_errors=True)
        if str(exc) == 'cancelled':
            raise UpdateError('cancelled') from exc
        raise UpdateError('the download was damaged on the way. Try again') from exc
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        shutil.rmtree(staging, ignore_errors=True)
        raise UpdateError('the download stopped before it finished. Check your connection '
                          'and try again') from exc
    except UpdateError:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    if not plan.nothing_to_do:
        with open(os.path.join(staging, READY_MARKER), 'w', encoding='utf-8') as fh:
            json.dump({'tag': plan.release.tag, 'remove': plan.remove,
                       'files': payload_files(payload)}, fh)
    log('downloaded %s into %s' % (plan.release.tag, staging))
    return staging


def _download_changed_members(plan: Plan, payload: str, progress, cancelled) -> None:
    total = plan.download_size
    done = [0]

    def moved(n):
        done[0] += n
        if progress is not None:
            progress(done[0], total)

    for rel, entry in plan.fetch:
        _stop(cancelled)
        target = os.path.join(payload, rel.replace('/', os.sep))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        part = target + '.part'
        with open(part, 'wb') as out:
            plan.archive.read_into(entry, out, moved, cancelled)
        os.replace(part, target)
    plan.downloaded = done[0]


def _download_whole_archive(plan: Plan, payload: str, progress, cancelled) -> None:
    release = plan.release
    archive_path = os.path.join(os.path.dirname(payload), 'release.zip')
    request = urllib.request.Request(release.asset_url, headers={'User-Agent': USER_AGENT})
    done = 0
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response, open(archive_path, 'wb') as fh:
        total = int(response.headers.get('Content-Length') or 0) or release.asset_size
        while True:
            _stop(cancelled)
            block = response.read(CHUNK)
            if not block:
                break
            fh.write(block)
            done += len(block)
            if progress is not None:
                progress(done, total or done)
    plan.downloaded = done
    root = install_dir()
    try:
        zf = zipfile.ZipFile(archive_path)
    except zipfile.BadZipFile as exc:
        raise UpdateError('the download was damaged on the way. Try again') from exc
    with zf:
        prefix = _strip_prefix(zf.namelist())
        wanted = set()
        for info in zf.infolist():
            _stop(cancelled)
            if info.is_dir():
                continue
            rel = info.filename[len(prefix):] if prefix and info.filename.startswith(prefix) \
                else info.filename
            if not _safe(rel):
                continue
            wanted.add(rel)
            if _crc(os.path.join(root, rel.replace('/', os.sep))) == info.CRC:
                plan.unchanged += 1
                continue
            target = os.path.join(payload, rel.replace('/', os.sep))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with zf.open(info) as src, open(target, 'wb') as dst:     # zipfile checks the CRC
                shutil.copyfileobj(src, dst, CHUNK)
        if GAME_EXE not in wanted:
            raise UpdateError('the download does not hold the game')
        plan.remove = _stale_files(root, wanted)
    os.remove(archive_path)
    plan.fetch = []


# =========================================================== waiting, and tidying up
def payload_files(payload: str) -> list:
    out = []
    for dirpath, _dirs, files in os.walk(payload):
        for name in files:
            out.append(os.path.relpath(os.path.join(dirpath, name), payload).replace(os.sep, '/'))
    return sorted(out)


def pending_update():
    """An update downloaded and not yet put in place: (folder, tag, removals), or (None, '', [])."""
    best = (None, '', [])
    root = os.path.join(user_dir(), 'updates')
    if not os.path.isdir(root):
        return best
    here = version.current()
    for name in sorted(os.listdir(root)):
        folder = os.path.join(root, name)
        marker = os.path.join(folder, READY_MARKER)
        payload = os.path.join(folder, 'payload')
        if not os.path.isfile(marker) or not os.path.isdir(payload):
            continue
        try:
            with open(marker, encoding='utf-8') as fh:
                saved = json.load(fh)
        except (OSError, ValueError):
            continue
        tag = str(saved.get('tag') or '')
        listed = [str(f) for f in saved.get('files') or ()]
        if listed and payload_files(payload) != sorted(listed):
            continue                                 # something in it went missing
        if tag and version.is_newer(tag, here) and (not best[1] or version.is_newer(tag, best[1])):
            best = (folder, tag, [str(r) for r in saved.get('remove') or ()])
    return best


def clean_up_staging() -> None:
    """Throw away half-finished downloads and applied updates; keep one waiting."""
    root = os.path.join(user_dir(), 'updates')
    if not os.path.isdir(root):
        return
    keep, _tag, _remove = pending_update()
    for name in os.listdir(root):
        path = os.path.join(root, name)
        if os.path.isdir(path) and path != keep:
            shutil.rmtree(path, ignore_errors=True)


# ================================================================ handing over
def back_up(staging: str, remove) -> str:
    """Copy each file about to be replaced or removed, so a failed swap can be undone."""
    root = install_dir()
    backup = os.path.join(staging, 'backup')
    shutil.rmtree(backup, ignore_errors=True)
    for rel in payload_files(os.path.join(staging, 'payload')) + list(remove):
        source = os.path.join(root, rel.replace('/', os.sep))
        if not os.path.isfile(source):
            continue
        target = os.path.join(backup, rel.replace('/', os.sep))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(source, target)
    return backup


def _ps(text: str) -> str:
    """A PowerShell single-quoted string."""
    return "'%s'" % str(text).replace("'", "''")


def _ps_list(items) -> str:
    items = list(items)
    return '@(%s)' % ', '.join(_ps(i) for i in items) if items else '@()'


SCRIPT = """\
$ErrorActionPreference = 'Stop'
$pidToWait = {pid}
$install   = {install}
$payload   = {payload}
$backup    = {backup}
$staging   = {staging}
$exe       = {exe}
$logFile   = {log}
$files     = {files}
$removals  = {removals}

function Say([string]$text) {{
    try {{ Add-Content -LiteralPath $logFile -Value ((Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + ' hand-off: ' + $text) -Encoding UTF8 }} catch {{ }}
}}

Say 'waiting for the game to close'
for ($i = 0; $i -lt 900; $i++) {{
    if (-not (Get-Process -Id $pidToWait -ErrorAction SilentlyContinue)) {{ break }}
    Start-Sleep -Milliseconds 100
}}
Start-Sleep -Milliseconds 500

function Put-In {{
    foreach ($relative in $files) {{
        $from = Join-Path $payload $relative
        $to = Join-Path $install $relative
        $folder = Split-Path -Parent $to
        if (-not (Test-Path -LiteralPath $folder)) {{ New-Item -ItemType Directory -Path $folder -Force | Out-Null }}
        Copy-Item -LiteralPath $from -Destination $to -Force
        if ((Get-Item -LiteralPath $to).Length -ne (Get-Item -LiteralPath $from).Length) {{ throw ('incomplete: ' + $relative) }}
    }}
    foreach ($relative in $removals) {{
        $victim = Join-Path $install $relative
        if (Test-Path -LiteralPath $victim) {{ Remove-Item -LiteralPath $victim -Force }}
    }}
}}

$done = $false
for ($attempt = 1; $attempt -le 20 -and -not $done; $attempt++) {{
    try {{
        Put-In
        $done = $true
    }} catch {{
        Say ('attempt ' + $attempt + ' failed: ' + $_.Exception.Message)
        Start-Sleep -Seconds 1
    }}
}}

if (-not $done) {{
    Say 'could not put the update in; putting the old files back'
    foreach ($relative in ($files + $removals)) {{
        $saved = Join-Path $backup $relative
        if (Test-Path -LiteralPath $saved) {{
            try {{ Copy-Item -LiteralPath $saved -Destination (Join-Path $install $relative) -Force }} catch {{ }}
        }}
    }}
    Start-Process -FilePath $exe -WorkingDirectory $install
    exit 1
}}

Say 'installed; starting the game'
Start-Process -FilePath $exe -WorkingDirectory $install
Start-Sleep -Milliseconds 500
Remove-Item -LiteralPath $staging -Recurse -Force -ErrorAction SilentlyContinue
"""


def write_handoff(staging: str, remove) -> str:
    """The script that swaps the files in once the game has quit; returns its path."""
    payload = os.path.join(staging, 'payload')
    script = SCRIPT.format(
        pid=os.getpid(),
        install=_ps(install_dir()),
        payload=_ps(payload),
        backup=_ps(os.path.join(staging, 'backup')),
        staging=_ps(staging),
        exe=_ps(restart_target()),
        log=_ps(os.path.join(updates_dir(), 'update.log')),
        files=_ps_list(f.replace('/', '\\') for f in payload_files(payload)),
        removals=_ps_list(r.replace('/', '\\') for r in remove),
    )
    path = os.path.join(staging, 'apply.ps1')
    with open(path, 'w', encoding='utf-8-sig') as fh:      # the BOM tells PowerShell it is UTF-8
        fh.write(script)
    return path


def apply(staging: str, remove) -> None:
    """Back up, start the hand-off, and return; the caller quits the game straight after."""
    remove = list(remove)
    if not payload_files(os.path.join(staging, 'payload')):
        raise UpdateError('the downloaded update is empty. Check for updates again')
    try:
        back_up(staging, remove)
        script = write_handoff(staging, remove)
    except OSError as exc:
        raise UpdateError('the update could not be prepared: %s' % exc) from exc
    # CREATE_NO_WINDOW and nothing else.  DETACHED_PROCESS gives PowerShell no
    # console, and PowerShell with no console exits at once without running
    # the script - CreateProcess still succeeds, so the game would close and
    # never update.  (Learnt the hard way on the Audio Defence port.)  A child
    # outlives its parent on Windows anyway.
    creation = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    try:
        # not cwd=staging: the script deletes that folder at the end
        subprocess.Popen(['powershell', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                          '-WindowStyle', 'Hidden', '-File', script],
                         cwd=user_dir(), creationflags=creation, close_fds=True)
    except OSError as exc:
        raise UpdateError('the update could not be started: %s' % exc) from exc
    log('hand-off started for %s' % staging)


def size_text(byte_count: int) -> str:
    """'4.2 megabytes': what a screen reader should say, not '4.2 MB'."""
    if byte_count >= 1 << 20:
        return '%.1f megabytes' % (byte_count / float(1 << 20))
    if byte_count >= 1 << 10:
        return '%.0f kilobytes' % (byte_count / float(1 << 10))
    return '%d bytes' % byte_count
