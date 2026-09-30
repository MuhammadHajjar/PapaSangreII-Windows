"""Build the standalone, double-clickable applications, for the platform it runs on.

Everything the project hands over is an exe - no terminal, no Python, no paths
to type.  Each app in ``apps/`` is frozen by PyInstaller into a one-file exe in
``Run/``, carrying its own OpenAL Soft, the NVDA controller client, the
recovered HRTF and whatever game data it needs (on the Mac the same, without
the ``.exe``, and with no NVDA client: speech there is VoiceOver):

    Check game content.exe      the level data, playlists and a sound index
    Verify spatial audio.exe    nothing but the HRTF
    Listen to spatial audio.exe two of the game's sounds
    Play Papa Sangre II.exe     every level, every sound, the About texts

The game itself is a folder build (REQUESTED 2026-09-25): the exe with its
libraries in ``_internal`` beside it, so nothing is unpacked to a temporary
folder at each start, and all the game data - sounds, levels, playlists - in
one encrypted pack embedded in the exe as a Windows resource
(``papasangre2/assets/pack.py``).  It goes into ``Run/`` as the exe and its
``_internal`` folder, next to the player's ``config``.  The three tools stay
one-file exes.

On the Mac the game is ``Play Papa Sangre II.app``, the same folder build
wrapped as a bundle, with the pack as ``gamedata.pak`` inside it (a Mac
executable has no resources to embed it in).  It goes into ``Run/`` beside
``changelog.txt``.  The Mac's OpenAL Soft and makemhr are committed in
``vendor/openal-mac`` and ``vendor/makemhr-mac`` (``tools/build_openal_mac.sh``
rebuilds them).

Run:  python tools/build_exes.py            (all apps)
      python tools/build_exes.py content    (one app, by key)
"""

from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from papasangre2.util import host                               # noqa: E402

APPS = os.path.join(ROOT, 'apps')
#: Where the exes go.  PS2_DIST puts them elsewhere - for building while the
#: game in Run is being played (Windows will not replace a running exe).
RUN = os.environ.get('PS2_DIST') or os.path.join(ROOT, 'Run')
WORK = os.path.join(ROOT, 'build', 'pyinstaller')
BUNDLE = os.path.join(ROOT, 'reference', 'Payload', 'Papa Sangre II.app')
HRTF_DIR = os.path.join(ROOT, 'build', 'hrtf')
HRTF = os.path.join(HRTF_DIR, 'papa_ircam_1050.mhr')
if host.MAC:
    OPENAL = os.path.join(ROOT, 'vendor', 'openal-mac', 'libopenal.dylib')
    MAKEMHR = os.path.join(ROOT, 'vendor', 'makemhr-mac', 'makemhr')
else:
    OPENAL = os.path.join(ROOT, 'vendor', 'openal', 'soft_oal.dll')
    MAKEMHR = os.path.join(ROOT, 'vendor', 'makemhr', 'makemhr.exe')
NVDA_DIR = os.path.join(ROOT, 'vendor', 'nvda')

#: PyInstaller's src;dest separator: ';' on Windows, ':' everywhere else.
SEP = ';' if host.WINDOWS else ':'

#: The game, as the player receives it.
GAME_NAME = 'Play Papa Sangre II'
#: What the game is on disk: the exe, or on the Mac the .app bundle.
GAME_FILE = GAME_NAME + ('.app' if host.MAC else '.exe')
#: The Mac bundle's reverse-DNS identity (PyInstaller's default is the bare
#: app name, spaces and all), which LaunchServices and Spotlight key on.
BUNDLE_ID = 'com.papasangre2.port'
#: The game data pack, embedded in the game's exe.
PACK = os.path.join(ROOT, 'build', 'gamedata.pak')
GAME_DIST = os.path.join(ROOT, 'build', 'dist_game')
#: Shipped beside the game's exe (the players' list of changes).
CHANGELOG = os.path.join(ROOT, 'changelog.txt')


def version() -> str:
    """The port's version, from ``VERSION`` at the repository root."""
    try:
        with open(os.path.join(ROOT, 'VERSION'), encoding='utf-8') as fh:
            return fh.read().strip() or '0.0.0'
    except OSError:
        return '0.0.0'


def bundle_version() -> str:
    """The version as a Mac bundle wants it: dotted integers.

    '2026-09-26 number 5' -> '2026.9.26.5'; a day's first build is number 1.
    """
    from papasangre2.update.version import parse                  # noqa: PLC0415
    parts = parse(version())
    if len(parts) < 3:
        return '0.0.0'
    return '.'.join(str(n) for n in parts[:3] + (parts[3] if len(parts) > 3 else 1,))


def prepare_hrtf() -> str:
    """Make sure the built HRTF exists, building it if it does not.

    ``papa_ircam_1050.mhr`` lives in ``build/`` and is therefore not committed:
    it is produced from the committed ``tools/embedded_hrtf.dat`` (the IRCAM
    1050 set carved out of the PS2 binary; byte-identical to PS1's) by
    ``tools/extract_hrtf.py`` followed by OpenAL Soft's ``makemhr``.
    """
    if os.path.exists(HRTF):
        return HRTF
    os.makedirs(HRTF_DIR, exist_ok=True)
    print('    building HRTF (first build on this machine)...')
    seed = os.path.join(ROOT, 'tools', 'embedded_hrtf.dat')
    if not os.path.exists(seed):
        raise SystemExit(f'missing the HRTF source data: {seed}')
    subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'extract_hrtf.py')],
                   cwd=ROOT, check=True)
    if not os.path.exists(MAKEMHR):
        raise SystemExit(f'missing makemhr: {MAKEMHR} (Windows: ships in the openal-soft '
                         'binary zip; Mac: tools/build_openal_mac.sh builds it)')
    # -e off: no diffuse-field equalisation.  The original convolves the raw
    # IRCAM responses; makemhr's default equalises them, which changes the
    # interaural level differences (measured: 15 dB at 90 degrees instead of
    # 10).  With -e off the output is byte-for-byte the .mhr the PS1 port ships.
    subprocess.run([MAKEMHR, '-i', os.path.join(HRTF_DIR, 'papa_ircam_1050.def'),
                    '-o', HRTF, '-e', 'off'], cwd=HRTF_DIR, check=True)
    if not os.path.exists(HRTF):
        raise SystemExit(f'makemhr did not produce {HRTF}')
    print(f'    {HRTF}')
    return HRTF


def staged_entries(staging: str) -> list[tuple[str, str]]:
    """Turn a staging directory into a handful of ``--add-data`` entries.

    One entry per file blows past the command-line length limit once a build
    carries the whole audio tree, so whole directories are passed instead.
    """
    data: list[tuple[str, str]] = []
    for name in sorted(os.listdir(staging)):
        full = os.path.join(staging, name)
        data.append((full, f'gamedata/{name}' if os.path.isdir(full) else 'gamedata'))
    return data


def game_audio(*rel: str) -> tuple[str, str]:
    """(source, dest-inside-bundle) for one file from the original bundle."""
    src = os.path.join(BUNDLE, *rel)
    dest = 'gamedata/' + '/'.join(rel[:-1])
    return src, dest


def _fresh(name: str) -> str:
    staging = os.path.join(ROOT, 'build', name)
    if os.path.isdir(staging):
        shutil.rmtree(staging)
    os.makedirs(staging)
    return staging


def prepare_content_data() -> list[tuple[str, str]]:
    """Stage what the content checker reads: levels, playlists, a sound index.

    The checker needs to know which audio files exist, not their contents, so
    an index of names travels instead of the 85 MB tree.
    """
    from papasangre2.assets.audit import write_sound_index         # noqa: PLC0415

    staging = _fresh('contentdata')
    shutil.copytree(os.path.join(BUNDLE, 'levels'), os.path.join(staging, 'levels'))
    shutil.copytree(os.path.join(BUNDLE, 'meta'), os.path.join(staging, 'meta'))
    n = write_sound_index(BUNDLE, os.path.join(staging, 'sounds_index.txt'))
    print(f'    staged levels and playlists ({n} sound files indexed)')
    return staged_entries(staging)


def prepare_game_data() -> list[tuple[str, str]]:
    """Stage everything the game loads: levels, playlists and the sound tree."""
    staging = _fresh('gamedata')
    for sub in ('levels', 'meta', 'sounds'):
        shutil.copytree(os.path.join(BUNDLE, sub), os.path.join(staging, sub))
    # the About screen's texts are read from the original's own nib
    shutil.copy2(os.path.join(BUNDLE, 'CreditsViewController.nib'), staging)
    # the sounds Muhammad made for the port (papasangre2/assets/requested.py)
    shutil.copytree(os.path.join(ROOT, 'requested', 'sounds'),
                    os.path.join(staging, 'requested_sounds'))
    size = sum(os.path.getsize(os.path.join(dp, f))
               for dp, _d, fs in os.walk(staging) for f in fs)
    print(f'    staged the game data, {size / 1e6:.0f} MB')
    from papasangre2.assets.pack import write_pack               # noqa: PLC0415
    n = write_pack(staging, PACK)
    print(f'    packed and encrypted {n} files, {os.path.getsize(PACK) / 1e6:.0f} MB')
    return staged_entries(staging)


#: key -> (script, exe name, extra data files as (src, dest) pairs)
TARGETS: dict[str, tuple[str, str, list[tuple[str, str]]]] = {
    'content': ('check_content.py', 'Check game content', []),
    'verify': ('verify_spatial.py', 'Verify spatial audio', []),
    'listen': ('listen_spatial.py', 'Listen to spatial audio', [
        game_audio('sounds', 'Collectibles', 'music_collectibles_loops', 'music5',
                   'music5_collectible_1_SPA_UOS.m4a'),
        game_audio('sounds', 'Enemies', 'mindlouse', 'mindlouse_patrol_SPA.m4a'),
    ]),
    'play': ('play.py', GAME_NAME, []),
}


def build(key: str) -> str:
    script, exe_name, extra = TARGETS[key]
    if key == 'content':
        extra = prepare_content_data()
    elif key == 'play':
        prepare_game_data()
        extra = []
    script_path = os.path.join(APPS, script)
    if not os.path.exists(script_path):
        raise SystemExit(f'missing app script: {script_path}')
    if not os.path.exists(OPENAL):
        raise SystemExit(f'missing OpenAL Soft: {OPENAL}')
    hrtf = prepare_hrtf()

    data: list[tuple[str, str]] = [(hrtf, 'hrtf')]
    # Speech on the Mac is VoiceOver, part of the system; the pyobjc bridge to
    # it is inside the frozen Python.  Only Windows carries a speech DLL.
    if host.WINDOWS:
        for name in ('nvdaControllerClient64.dll', 'nvdaControllerClient32.dll'):
            p = os.path.join(NVDA_DIR, name)
            if os.path.exists(p):
                data.append((p, 'nvda'))
    for src, dest in extra:
        if not os.path.exists(src):
            raise SystemExit(f'missing bundled data: {src}')
        data.append((src, dest))

    # The game is built windowed: a console beside a released game is noise,
    # and everything that matters is spoken.  The diagnostic tools keep their
    # console, which is the whole point of them.  On the Mac --windowed is
    # also what makes PyInstaller produce a .app bundle.
    game = exe_name == GAME_NAME
    windowed = game
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--noconfirm', '--clean',
        '--onedir' if game else '--onefile',
        '--windowed' if windowed else '--console',
        '--name', exe_name,
        '--distpath', GAME_DIST if game else RUN,
        '--workpath', WORK,
        '--specpath', WORK,
        '--add-binary', f'{OPENAL}{SEP}.',
        '--hidden-import', 'papasangre2',
        '--paths', ROOT,
    ]
    for src, dest in data:
        cmd += ['--add-data', f'{src}{SEP}{dest}']
    if game and host.MAC:
        # beside the frozen modules, where pack.auto_mount looks for it
        cmd += ['--add-data', f'{PACK}{SEP}.', '--osx-bundle-identifier', BUNDLE_ID]
    elif game:
        cmd += ['--resource', f'{PACK},PS2PACK,GAMEDATA,0']
    if host.MAC:
        # pyobjc resolves its frameworks lazily enough that the analyser cannot
        # always see them; the VoiceOver bridge needs both inside the build.
        cmd += ['--hidden-import', 'Foundation', '--hidden-import', 'AppKit']
    cmd.append(script_path)

    kind = GAME_FILE[len(GAME_NAME):] if game else ('.exe' if host.WINDOWS else '')
    print(f'\n=== building {exe_name}{kind} ===', flush=True)
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stdout.write(proc.stdout[-4000:])
        sys.stderr.write(proc.stderr[-4000:])
        raise SystemExit(f'PyInstaller failed for {exe_name}')
    if game and host.MAC:
        out = install_mac_game(exe_name)
    elif game:
        shutil.copy2(CHANGELOG, os.path.join(GAME_DIST, exe_name, 'changelog.txt'))
        out = install_game(exe_name)
    else:
        out = os.path.join(RUN, exe_name + ('.exe' if host.WINDOWS else ''))
    size = (sum(os.lstat(os.path.join(dp, f)).st_size       # lstat: a bundle's links once
                for dp, _d, fs in os.walk(out) for f in fs)
            if os.path.isdir(out) else os.path.getsize(out))
    print(f'    {out}  ({size / 1e6:.0f} MB, {time.perf_counter() - t0:.0f}s)')
    return out


def install_game(exe_name: str) -> str:
    """Put the folder build into RUN: the exe and its _internal folder, next to
    whatever is there (the player's config stays)."""
    built = os.path.join(GAME_DIST, exe_name)
    exe = os.path.join(RUN, exe_name + '.exe')
    internal = os.path.join(RUN, '_internal')
    try:
        if os.path.exists(exe):
            os.replace(exe, exe + '.old')             # fails at once if it is running
    except OSError:
        raise SystemExit(f'{exe} is running - close the game and build again '
                         f'(or set PS2_DIST to build elsewhere)')
    if os.path.isdir(internal):
        shutil.rmtree(internal)
    shutil.copytree(os.path.join(built, '_internal'), internal)
    shutil.copy2(os.path.join(built, exe_name + '.exe'), exe)
    shutil.copy2(os.path.join(built, 'changelog.txt'), os.path.join(RUN, 'changelog.txt'))
    if os.path.exists(exe + '.old'):
        os.remove(exe + '.old')
    return exe


def _finalize_mac_app(bundle: str) -> None:
    """Stamp the version on the bundle and seal it again.

    PyInstaller writes ``0.0.0`` for both version keys.  Changing Info.plist
    breaks the ad-hoc signature PyInstaller sealed the bundle with, and a Mac
    refuses a downloaded app whose seal is broken ("damaged"), so the bundle
    is signed again, ad hoc, afterwards.
    """
    info = os.path.join(bundle, 'Contents', 'Info.plist')
    if not os.path.isfile(info):
        raise SystemExit(f'not a .app bundle: {bundle}')
    with open(info, 'rb') as fh:
        plist = plistlib.load(fh)
    plist['CFBundleIdentifier'] = BUNDLE_ID
    plist['CFBundleShortVersionString'] = bundle_version()
    plist['CFBundleVersion'] = bundle_version()
    plist['CFBundleGetInfoString'] = f'Papa Sangre II, {version()}'
    plist['NSHumanReadableCopyright'] = 'Papa Sangre II by Somethin\' Else; the port is MIT'
    with open(info, 'wb') as fh:
        plistlib.dump(plist, fh, sort_keys=True)
    subprocess.run(['codesign', '--force', '--deep', '--sign', '-', bundle],
                   check=True, capture_output=True)


def install_mac_game(exe_name: str) -> str:
    """Put the .app into RUN beside the changelog (the player's data is in
    ~/Library/Application Support, so nothing in RUN is theirs to keep)."""
    built = os.path.join(GAME_DIST, exe_name + '.app')
    _finalize_mac_app(built)
    app = os.path.join(RUN, exe_name + '.app')
    if os.path.isdir(app):
        shutil.rmtree(app)
    # symlinks=True: the bundle's Frameworks point into Resources
    shutil.copytree(built, app, symlinks=True)
    shutil.copy2(CHANGELOG, os.path.join(RUN, 'changelog.txt'))
    return app


def main() -> int:
    keys = sys.argv[1:] or [k for k in TARGETS
                            if os.path.exists(os.path.join(APPS, TARGETS[k][0]))]
    unknown = [k for k in keys if k not in TARGETS]
    if unknown:
        raise SystemExit(f'unknown target(s) {unknown}; choose from {list(TARGETS)}')
    os.makedirs(RUN, exist_ok=True)
    built = [build(k) for k in keys]
    print('\nBuilt:')
    for b in built:
        print('  ', b)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
