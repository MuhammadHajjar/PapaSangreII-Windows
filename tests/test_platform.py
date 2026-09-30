"""Platform guards: every Windows-specific choice has a Mac equivalent.

The port was Windows-only.  These tests hold the guarantee that nothing in
``papasangre/`` reaches past the :mod:`papasangre2.util.host` layer for a
platform decision, and that both platforms' equivalents resolve - the NVDA
DLL has its VoiceOver bridge, ``soft_oal.dll`` its ``libopenal.dylib``, the
exe and its embedded pack their .app with ``gamedata.pak`` inside.
"""

import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from papasangre2.util import host                              # noqa: E402

VENDOR_OPENAL_WIN = os.path.join(ROOT, 'vendor', 'openal', 'soft_oal.dll')
VENDOR_OPENAL_MAC = os.path.join(ROOT, 'vendor', 'openal-mac',
                                 'libopenal.dylib')
VENDOR_NVDA = os.path.join(ROOT, 'vendor', 'nvda',
                           'nvdaControllerClient64.dll')


# ------------------------------------------------------------ platform module
def test_platform_is_decided_once():
    assert host.PLATFORM in ('windows', 'mac', 'other')
    assert host.WINDOWS == (sys.platform == 'win32')
    assert host.MAC == (sys.platform == 'darwin')
    # exactly one of the two supported platforms, never both
    assert not (host.WINDOWS and host.MAC)


def test_the_port_names_itself_for_the_platform():
    assert host.PORT_NAME == ('Mac' if host.MAC else
                              'Windows' if host.WINDOWS else 'Other')


def test_quit_hint_is_the_platforms_window_close():
    assert host.quit_hint() == ('Cmd+Q' if host.MAC else
                                'Alt+F4' if host.WINDOWS else 'window close')


def test_speech_backend_order_follows_the_platform():
    if host.MAC:
        assert host.speech_backend_order() == ['voiceover', 'null']
    elif host.WINDOWS:
        assert host.speech_backend_order() == ['nvda', 'sapi', 'null']


def test_mono_setting_never_raises_anywhere():
    """Unknown platform or unreadable setting: None, not an exception."""
    value = host.mono_audio_setting()
    assert value in (True, False, None)


# ------------------------------------------------------------------- speech
def test_speech_factory_respects_the_platform():
    from papasangre2.accessibility import speech
    backend = speech.create()
    try:
        if host.MAC:
            assert backend.name in ('voiceover', 'null'), backend.name
        elif host.WINDOWS:
            assert backend.name in ('nvda', 'sapi', 'null'), backend.name
    finally:
        backend.close()


def test_forcing_a_backend_wins_over_the_platform():
    from papasangre2.accessibility import speech
    backend = speech.create(prefer='null')
    try:
        assert backend.name == 'null'
    finally:
        backend.close()


def test_voiceover_module_matches_the_csharp_interfaces():
    """VoiceOverOutput.cs -> voiceover.py, call for call."""
    from papasangre2.accessibility import voiceover
    for fn in ('is_supported', 'is_running', 'speak', 'cancel',
               'is_speaking', 'shutdown'):
        assert callable(getattr(voiceover, fn, None)), fn
    assert voiceover.is_supported() == host.MAC
    if not host.MAC:
        assert voiceover.speak('no-op off the mac') is False


def test_the_applescript_is_escaped_the_way_the_csharp_escapes_it():
    from papasangre2.accessibility.voiceover import _escape_applescript
    assert _escape_applescript('say "hello"') == 'say \\"hello\\"'
    assert _escape_applescript('back\\slash') == 'back\\\\slash'


# -------------------------------------------------------------------- paths
def test_openal_library_is_the_platforms_own_and_exists():
    from papasangre2.util import paths
    if host.MAC:
        assert os.path.basename(paths.openal_dll()) == 'libopenal.dylib'
    else:
        assert os.path.basename(paths.openal_dll()) == 'soft_oal.dll'
    assert os.path.exists(paths.openal_dll()), paths.openal_dll()


def test_both_platforms_libraries_are_vendored():
    """The Mac dylib and makemhr are committed beside the Windows ones."""
    for p in (VENDOR_OPENAL_WIN, VENDOR_OPENAL_MAC,
              os.path.join(ROOT, 'vendor', 'makemhr', 'makemhr.exe'),
              os.path.join(ROOT, 'vendor', 'makemhr-mac', 'makemhr')):
        assert os.path.exists(p), p


def test_mac_binaries_are_mach_o_for_this_machine():
    import subprocess
    for p in (VENDOR_OPENAL_MAC, os.path.join(ROOT, 'vendor', 'makemhr-mac', 'makemhr')):
        with open(p, 'rb') as fh:
            magic = fh.read(4)
        assert magic in (b'\xcf\xfa\xed\xfe', b'\xca\xfe\xba\xbe'), p   # Mach-O 64 / fat
        if host.MAC:
            out = subprocess.run(['file', p], capture_output=True, text=True).stdout
            assert os.uname().machine in out, out


# ------------------------------------------------------------------ openal
def test_alsoft_config_header_is_platform_neutral():
    from papasangre2.audio import openal as OA
    import inspect
    src = inspect.getsource(OA.write_alsoft_config)
    assert 'Windows port' not in src


def test_openal_load_sets_the_dyld_path_on_the_mac():
    from papasangre2.audio import openal as OA
    import inspect
    src = inspect.getsource(OA.OpenAL.__init__)
    if host.MAC:
        assert 'DYLD_FALLBACK_LIBRARY_PATH' in src
    else:
        assert 'add_dll_directory' in src


# ------------------------------------------------------------------ windows
def test_windows_only_imports_never_load_off_windows():
    """winreg / windll must sit behind a platform guard, not at import time.

    Only *module-level* imports count: a function-body import never runs
    unless its function is called, which is exactly how the guarded ones are
    written.
    """
    for rel in ('papasangre2/accessibility/speech.py',
                'papasangre2/util/sysaudio.py',
                'papasangre2/util/host.py'):
        tree = ast.parse(open(os.path.join(ROOT, rel),
                              encoding='utf-8').read())
        for node in tree.body:                      # module level only
            if isinstance(node, ast.Import):
                assert all(a.name != 'winreg' for a in node.names), rel
            elif isinstance(node, ast.ImportFrom):
                assert node.module != 'winreg', rel


def test_speech_module_names_the_mac_backend():
    from papasangre2.accessibility import speech
    assert hasattr(speech, 'VoiceOverSpeech')
    assert speech.VoiceOverSpeech.name == 'voiceover'


# ------------------------------------------------------------------ building
def test_every_build_target_names_a_script_and_an_exe():
    import tools.build_exes as be
    for key, (script, name, extra) in be.TARGETS.items():
        assert script.endswith('.py') and name
        for src, dest in extra:
            assert os.path.exists(src), (key, src)
            assert dest.startswith('gamedata/')
    # the two apps that exist so far are buildable now; the game arrives with M2
    for key in ('content', 'verify', 'listen'):
        assert os.path.exists(os.path.join(be.APPS, be.TARGETS[key][0]))


def test_the_release_is_the_game_its_libraries_and_the_changelog():
    # decision 20: the folder build; the changelog ships with every release
    import tools.build_exes as be
    import tools.pack_release as pr
    assert pr.GAME == be.GAME_FILE
    if host.MAC:
        assert pr.GAME == 'Play Papa Sangre II.app'
        assert pr.ALWAYS == (pr.GAME, 'changelog.txt')      # _internal is inside the .app
    else:
        assert pr.GAME == 'Play Papa Sangre II.exe'
        assert pr.ALWAYS == (pr.GAME, '_internal', 'changelog.txt')
    assert pr.TOP == 'Papa Sangre II'


def test_the_mac_zip_is_never_taken_for_the_windows_one():
    """Both zips can sit on one release: the updater only ever picks its own."""
    import tools.pack_release as pr
    from papasangre2.update import updater
    assert pr.MAC_ASSET_NAME != updater.ASSET_NAME
    assert not pr.MAC_ASSET_NAME.lower().startswith(updater.ASSET_PREFIX.lower())
    release = updater.Release({'tag_name': '2099-01-01', 'assets': [
        {'name': pr.MAC_ASSET_NAME, 'browser_download_url': 'https://x/mac.zip'},
        {'name': updater.ASSET_NAME, 'browser_download_url': 'https://x/win.zip'}]})
    assert release.asset_name == updater.ASSET_NAME


def test_build_script_uses_the_platform_separator_and_libraries():
    import tools.build_exes as be
    assert be.SEP == (';' if host.WINDOWS else ':')
    assert os.path.basename(be.OPENAL) == ('libopenal.dylib' if host.MAC else 'soft_oal.dll')
    assert os.path.exists(be.OPENAL) and os.path.exists(be.MAKEMHR)


def test_the_mac_bundle_identity():
    import tools.build_exes as be
    assert be.BUNDLE_ID.count('.') >= 2 and ' ' not in be.BUNDLE_ID
    assert all(part.isalnum() for part in be.BUNDLE_ID.split('.')), be.BUNDLE_ID
    # dotted integers, as a bundle wants: '2026-09-26 number 5' -> '2026.9.26.5'
    parts = be.bundle_version().split('.')
    assert len(parts) == 4 and all(p.isdigit() for p in parts), parts


def test_finalize_mac_app_stamps_identity_and_version(tmp_path):
    """The .app ships a sane bundle id and the real version, not 0.0.0, and
    stays signed (a broken seal is 'damaged' to a downloading Mac)."""
    import plistlib
    import tools.build_exes as be
    if not host.MAC:
        return
    bundle = tmp_path / 'Fake.app'
    (bundle / 'Contents' / 'MacOS').mkdir(parents=True)
    exe = bundle / 'Contents' / 'MacOS' / 'Fake'
    exe.write_bytes(open('/usr/bin/true', 'rb').read())
    exe.chmod(0o755)
    with open(bundle / 'Contents' / 'Info.plist', 'wb') as fh:
        plistlib.dump({'CFBundleExecutable': 'Fake', 'CFBundleIdentifier': 'Fake',
                       'CFBundleShortVersionString': '0.0.0', 'CFBundleVersion': '0.0.0'}, fh)
    be._finalize_mac_app(str(bundle))
    with open(bundle / 'Contents' / 'Info.plist', 'rb') as fh:
        plist = plistlib.load(fh)
    assert plist['CFBundleIdentifier'] == be.BUNDLE_ID
    assert plist['CFBundleShortVersionString'] == be.bundle_version()
    assert plist['CFBundleVersion'] == be.bundle_version()
    import subprocess
    assert subprocess.run(['codesign', '--verify', '--deep', '--strict', str(bundle)]).returncode == 0


def test_the_pack_mounts_from_a_file_beside_the_program(tmp_path, monkeypatch):
    """The Mac's way in: gamedata.pak beside the frozen modules, memory-mapped."""
    from papasangre2.assets import pack
    src = tmp_path / 'src' / 'sounds'
    src.mkdir(parents=True)
    (src / 'a.m4a').write_bytes(b'hello')
    frozen = tmp_path / 'frozen'
    frozen.mkdir()
    pack.write_pack(str(tmp_path / 'src'), str(frozen / pack.FILE_NAME))
    monkeypatch.setattr(pack, '_exe_resource', lambda: None)
    pack.mount(None, None)
    try:
        root = str(frozen / 'gamedata')
        assert pack.auto_mount(root)
        assert pack.read_bytes(os.path.join(root, 'sounds', 'A.m4a')) == b'hello'
    finally:
        pack.mount(None, None)


def test_the_pause_menu_quits_to_this_platform():
    from papasangre2.shell import pause_menu
    labels = [item.label for item in pause_menu().items]
    assert ('Quit to macOS' if host.MAC else 'Quit to Windows') in labels


def test_version_helper_reads_the_version_file():
    import tools.build_exes as be
    want = open(os.path.join(ROOT, 'VERSION'), encoding='utf-8').read().strip()
    assert be.version() == (want or '0.0.0')


def test_the_sound_index_stands_in_for_the_sound_tree(tmp_path):
    """A frozen content check carries names, not 85 MB of audio."""
    from papasangre2.assets import audit
    from papasangre2.util import paths
    bundle = paths.game_bundle()
    full = audit.sound_files(bundle)
    assert len(full) > 1000 and all(a.startswith('sounds/') for a in full)
    fake = tmp_path / 'bundle'
    fake.mkdir()
    n = audit.write_sound_index(bundle, str(fake / audit.SOUND_INDEX))
    assert n == len(full)
    assert audit.sound_files(str(fake)) == full
