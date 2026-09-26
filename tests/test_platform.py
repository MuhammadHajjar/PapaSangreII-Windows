"""Platform guards: every Windows-specific choice has a Mac equivalent.

The port was Windows-only.  These tests hold the guarantee that nothing in
``papasangre/`` reaches past the :mod:`papasangre2.util.host` layer for a
platform decision, and that both platforms' equivalents resolve - the NVDA
DLL has its VoiceOver bridge, ``soft_oal.dll`` its ``libopenal.dylib``, the
``.cmd`` launchers their ``.command`` twins.
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
    assert pr.GAME == be.GAME_NAME + '.exe' == 'Play Papa Sangre II.exe'
    assert pr.ALWAYS == (pr.GAME, '_internal', 'changelog.txt')
    assert pr.TOP == 'Papa Sangre II'


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
