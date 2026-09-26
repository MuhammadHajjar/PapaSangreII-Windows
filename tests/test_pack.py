"""The game data pack (REQUESTED 2026-09-25): the cipher, the pack, and the
game reading levels, playlists and sounds out of it exactly as off the disk."""

import os
import shutil
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from papasangre2.assets import pack                                 # noqa: E402
from papasangre2.util import paths                                  # noqa: E402
from papasangre2.util.chacha import crypt, keystream                # noqa: E402

BUNDLE = paths.game_bundle()
SOUND = 'sounds/menu/end_musics/ps2_18b_end_music_loop.m4a'
LEVEL = 'levels/papasangre2/ps2_18b.json'


def test_chacha20_is_rfc_8439():
    key = bytes(range(32))
    pt = (b"Ladies and Gentlemen of the class of '99: If I could offer you only one "
          b"tip for the future, sunscreen would be it.")
    ct = crypt(key, bytes.fromhex('000000000000004a00000000'), pt, 1)
    assert ct.hex().startswith('6e2e359a2568f98041ba0728dd0d6981e97e7aec1d4360c20a27afccfd9fae0b')
    assert ct.hex().endswith('5af90bbf74a35be6b40b8eedf2785e42874d')
    block = keystream(key, bytes.fromhex('000000090000004a00000000'), 64, 1).tobytes()
    assert block.hex().startswith('10f1e7e4d13b5915500fdd1fa32071c4c7d1f4c733c068030422aa9ac3d46c4e')
    assert crypt(key, bytes(12), crypt(key, bytes(12), pt)) == pt


@pytest.fixture
def mounted(tmp_path):
    """A small bundle packed and mounted where the frozen game would find it."""
    src = tmp_path / 'src'
    for rel in (SOUND, LEVEL, 'levels/papasangre2_hubList.plist',
                'meta/S3DPlayListModel/ps2_18b.S3DPlayListModel#0.sexp'):
        dst = src / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(os.path.join(BUNDLE, rel), dst)
    pak = tmp_path / 'gamedata.pak'
    assert pack.write_pack(str(src), str(pak)) == 4
    root = str(tmp_path / 'gamedata')            # does not exist: only the pack does
    pack.mount(pack.Pack(pak.read_bytes()), root)
    yield root, pak
    pack.mount(None, None)


def test_nothing_readable_is_left_in_the_pack(mounted):
    _, pak = mounted
    raw = pak.read_bytes()
    original = open(os.path.join(BUNDLE, SOUND), 'rb').read()
    assert b'ftyp' not in raw[8:]                    # the m4a signature
    assert b'"layers"' not in raw and b'PlayListModel' not in raw
    assert original[:4096] not in raw


def test_levels_and_playlists_read_from_the_pack(mounted):
    from papasangre2.assets.tiled import load_level
    root, _ = mounted
    a = load_level(os.path.join(root, LEVEL), 'ps2_18b')
    b = load_level(os.path.join(BUNDLE, LEVEL), 'ps2_18b')
    assert [o.name for o in a.agents] == [o.name for o in b.agents]
    meta = os.path.join(root, 'meta', 'S3DPlayListModel')
    assert pack.glob(os.path.join(meta, 'ps2_18b.S3DPlayListModel*.sexp'))
    assert pack.isfile(os.path.join(root, *LEVEL.upper().split('/')))   # case-blind
    assert pack.exists(os.path.join(root, 'sounds', 'menu'))           # a folder
    assert not pack.isfile(os.path.join(root, 'sounds', 'nothing.m4a'))


def test_a_sound_decodes_from_the_pack_bit_for_bit(mounted):
    from papasangre2.audio.loader import decode
    root, _ = mounted
    a = decode(os.path.join(root, SOUND))
    b = decode(os.path.join(BUNDLE, SOUND))
    assert a.sample_rate == b.sample_rate and np.array_equal(a.samples, b.samples)


def test_the_hub_list_reads_from_the_pack(mounted):
    from papasangre2.assets.hublist import load_hub_list
    root, _ = mounted
    got = [e.file_name for e in load_hub_list(root)]
    assert got and got == [e.file_name for e in load_hub_list(BUNDLE)]


def test_paths_outside_the_pack_are_the_disk(mounted):
    here = os.path.abspath(__file__)
    assert pack.isfile(here)
    assert pack.read_bytes(here) == open(here, 'rb').read()
