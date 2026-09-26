"""Regression tests for the audio layer (Phase C).

The listener transform is checked against the arithmetic recovered from
``-[S3DEngine normalizeToHeadPosition:]``, and the whole binaural chain is
checked by rendering through OpenAL Soft's loopback device and measuring the
result — so a broken HRTF, a flipped axis or a lost .mhr fails the suite
instead of quietly sounding wrong.
"""

import math
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from papasangre2.audio.engine import (                         # noqa: E402
    COINCIDENT_OFFSET, DISTANCE_SCALE, MASTER_GAIN, MAX_SPATIAL_GAIN,
    csl_to_openal, normalize_to_head)
from papasangre2.audio.loader import decode                    # noqa: E402

BUNDLE = os.path.join(ROOT, 'reference', 'Payload', 'Papa Sangre II.app')
# Papa Sangre II sounds standing in for the PS1 ones these tests were written
# with, each chosen for the same property:
STEREO_SPA = ('sounds', 'Collectibles', 'music_collectibles_loops', 'music5',
              'music5_collectible_1_SPA_UOS.m4a')              # spatialised, stereo on disk
MONO_SPA = ('sounds', 'Enemies', 'mindlouse', 'mindlouse_chase_SPA.m4a')   # a monster loop, mono
AMBIENCE = ('sounds', '10_atmos', '10_atmos.m4a')                # wide stereo bed, not spatialised
HITWALL = ('sounds', 'hitwall')
HRTF_MHR = os.path.join(ROOT, 'build', 'hrtf', 'papa_ircam_1050.mhr')


# ------------------------------------------------------- recovered constants
def test_recovered_constants():
    # -[PGELevel initSoundEngine] and -[PGEngine init] in the PS2 binary
    assert DISTANCE_SCALE == 0.016
    assert MAX_SPATIAL_GAIN == 2.0
    assert MASTER_GAIN == 1.0


# ------------------------------------------------------- listener transform
def test_source_at_head_is_nudged_aside():
    """normalizeToHeadPosition guards against a coincident source."""
    out = normalize_to_head(10.0, 10.0, 0.0, 10.0, 10.0, 0.0, 0.0)
    assert out[1] == COINCIDENT_OFFSET * DISTANCE_SCALE
    assert out[0] == 0.0


def test_forward_is_plus_x_in_csl_space():
    # listener at the origin facing 0 degrees, source 100 px along +x
    out = normalize_to_head(100.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    assert abs(out[0] - 100.0 * DISTANCE_SCALE) < 1e-9
    assert abs(out[1]) < 1e-9


def test_left_is_plus_y_in_csl_space():
    out = normalize_to_head(0.0, 100.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    assert abs(out[0]) < 1e-6
    assert abs(out[1] - 100.0 * DISTANCE_SCALE) < 1e-9


def test_turning_rotates_the_world_the_other_way():
    """Facing 90 degrees, a source at world +y is straight ahead."""
    out = normalize_to_head(0.0, 100.0, 0.0, 0.0, 0.0, 0.0, 90.0)
    assert abs(out[0] - 100.0 * DISTANCE_SCALE) < 1e-6   # now forward
    assert abs(out[1]) < 1e-6


def test_distance_scale_is_applied():
    out = normalize_to_head(125.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    assert abs(out[0] - 125.0 * 0.016) < 1e-9   # 125 px == 2 units at PS2's 0.016


def test_axis_mapping_to_openal():
    # CSL +X forward -> OpenAL -Z ; CSL +Y left -> OpenAL -X ; +Z up -> +Y
    assert csl_to_openal(1.0, 0.0, 0.0) == (0.0, 0.0, -1.0)
    assert csl_to_openal(0.0, 1.0, 0.0) == (-1.0, 0.0, 0.0)
    assert csl_to_openal(0.0, 0.0, 1.0) == (0.0, 1.0, 0.0)


# ------------------------------------------------------- asset decoding
def test_decoded_audio_matches_the_original_bit_for_bit():
    """The port must not alter the shipped audio in any way."""
    import subprocess
    rel = os.path.join(*STEREO_SPA)
    path = os.path.join(BUNDLE, rel)
    pcm = decode(path)
    ref = subprocess.run(
        ['ffmpeg', '-v', 'error', '-i', path, '-f', 's16le', '-acodec',
         'pcm_s16le', '-'], capture_output=True, check=True).stdout
    got = pcm.samples.reshape(-1)
    exp = np.frombuffer(ref, dtype='<i2')
    assert got.shape == exp.shape
    assert np.array_equal(got, exp)
    assert pcm.sample_rate == 44100
    assert abs(pcm.duration - 89024 / 44100) < 0.001      # every decoded frame, none dropped


def test_monster_loops_are_mono_so_they_can_be_spatialised():
    pcm = decode(os.path.join(BUNDLE, *MONO_SPA))
    assert pcm.channels == 1


# ------------------------------------------------------- rendered output
def test_recovered_hrtf_was_built():
    assert os.path.exists(HRTF_MHR), (
        'run tools/extract_hrtf.py then makemhr to build the HRTF')


def test_rendered_binaural_cues_are_physically_correct():
    """End-to-end: render through OpenAL and measure what comes out.

    Catches a lost .mhr, a flipped axis, swapped ears, or HRTF being bypassed.
    """
    from papasangre2.audio.measure import LoopbackRenderer, check, sweep
    r = LoopbackRenderer()
    try:
        assert r.hrtf_status == 'enabled', f'HRTF status {r.hrtf_status}'
        assert 'papa_ircam_1050' in r.available, (
            f'the recovered HRTF is not installed; OpenAL offered {r.available}')
        rows = sweep(r)
        failures = check(rows)
        assert not failures, '; '.join(failures)
        lateral = max(abs(itd) for b, itd, _ in rows if b in (90.0, 270.0))
        # A human head gives roughly 0.6-0.8 ms of interaural delay at 90 deg.
        assert 0.5 < lateral / r.rate * 1000 < 1.0, (
            f'peak lateral ITD {lateral / r.rate * 1000:.2f} ms is not head-sized')
    finally:
        r.close()


# ---------------------------------------- real assets, not synthetic signals
#
# The synthetic-click sweep above passed while the game's own positioned audio
# played completely flat, because most of it ships as stereo and OpenAL only
# spatialises mono sources.  These tests use the actual shipped files.

SPATIAL_SAMPLES = [
    ('/'.join(STEREO_SPA), 2),                    # stereo on disk, tonal
    ('sounds/house_burning/7_glass_smash_SPA.m4a', 2),   # stereo, transient
    ('/'.join(MONO_SPA), 1),                      # already mono
]


def test_spatialised_assets_are_forced_to_mono():
    """A stereo buffer bypasses HRTF entirely, so this must never regress."""
    from papasangre2.audio.loader import decode as dec
    for rel, expect_src in SPATIAL_SAMPLES:
        path = os.path.join(BUNDLE, *rel.split('/'))
        assert dec(path).channels == expect_src, rel
        assert dec(path, mono=True).channels == 1, rel


def test_mono_downmix_preserves_length_and_level():
    from papasangre2.audio.loader import decode as dec
    path = os.path.join(BUNDLE, *STEREO_SPA)
    stereo = dec(path)
    mono = dec(path, mono=True)
    assert mono.frames == stereo.frames
    a = stereo.samples.astype(np.float64).mean(axis=1)
    b = mono.samples.astype(np.float64).reshape(-1)
    assert np.max(np.abs(a - b)) <= 1.0        # rounding only


def test_real_game_audio_is_actually_spatialised():
    """Render the shipped assets and confirm the direction reaches the ears.

    Regression guard for the stereo-buffer bug: before the fix, the door gave
    identical interaural cues at 90 and 270 degrees - its position was ignored.
    """
    from ctypes import c_uint
    import math as _math
    from papasangre2.audio import openal as OA
    from papasangre2.audio.engine import (DISTANCE_SCALE, csl_to_openal,
                                         normalize_to_head)
    from papasangre2.audio.loader import decode as dec
    from papasangre2.audio.measure import LoopbackRenderer, interaural

    r = LoopbackRenderer()
    try:
        assert r.hrtf_status == 'enabled'
        al = r.al
        # Transient material: an interaural *delay* is measured by
        # cross-correlation, which a steady musical tone makes ambiguous (the
        # correlation peaks once per period), so tonal or ringing sounds are
        # left to the channel tests.
        for rel in ('sounds/house_burning/7_glass_smash_SPA.m4a',
                    '/'.join(MONO_SPA)):
            path = os.path.join(BUNDLE, *rel.split('/'))
            pcm = dec(path, mono=True)
            buf = (c_uint * 1)()
            al.alGenBuffers(1, buf)
            raw = pcm.tobytes()
            al.alBufferData(buf[0], OA.AL_FORMAT_MONO16, raw, len(raw),
                            pcm.sample_rate)
            al.check('buffer')
            got = {}
            for bearing in (90, 270):
                src = (c_uint * 1)()
                al.alGenSources(1, src)
                s = src[0]
                al.alSourcei(s, OA.AL_BUFFER, buf[0])
                al.alSourcei(s, OA.AL_SOURCE_RELATIVE, OA.AL_TRUE)
                al.alSourcef(s, OA.AL_ROLLOFF_FACTOR, 0.0)
                rad = _math.radians(bearing)
                c = normalize_to_head(250 * _math.cos(rad), 250 * _math.sin(rad),
                                      0, 0, 0, 0, 0.0, DISTANCE_SCALE)
                al.alSource3f(s, OA.AL_POSITION, *csl_to_openal(*c))
                al.alSourcePlay(s)
                out = OA.render_samples(al, r.device, 22050, 2)
                data = np.ctypeslib.as_array(out).reshape(-1, 2).copy()
                got[bearing] = interaural(data)
                al.alSourceStop(s)
                al.alDeleteSources(1, src)

            itd90, ild90 = got[90]
            itd270, ild270 = got[270]
            assert itd90 > 10, f'{rel}: left bearing ITD only {itd90}'
            assert itd270 < -10, f'{rel}: right bearing ITD only {itd270}'
            assert ild90 > ild270, f'{rel}: level does not follow direction'
            # the decisive one: the two bearings must not render the same
            assert abs(itd90 - itd270) > 20, (
                f'{rel}: 90 and 270 degrees render almost identically '
                f'({itd90} vs {itd270}) - the source position is being ignored')
    finally:
        r.close()


# ------------------------------------- un-spatialised sound bypasses HRTF
def test_unspatialised_sound_passes_through_untouched():
    """The original never puts flat sound through a head-related filter.

    ``-[S3DSound setupPlain]`` builds an ordinary csl::Panner; only
    ``setupSpatialized`` builds the binaural one.  OpenAL Soft with HRTF on
    virtualises everything unless a source is marked AL_DIRECT_CHANNELS_SOFT,
    and that virtualisation squashed the game's wide stereo ambience from an
    inter-channel correlation of 0.011 to 0.879, flattened the deliberate
    left/right lean of the footstep samples, and cost up to 10 dB.
    """
    from ctypes import c_uint
    from papasangre2.audio import openal as OA
    from papasangre2.audio.loader import decode as dec
    from papasangre2.audio.measure import LoopbackRenderer

    def stats(a):
        L, R = a[:, 0], a[:, 1]
        import math as _m
        bal = (10 * _m.log10(max((L ** 2).mean(), 1e-20))
               - 10 * _m.log10(max((R ** 2).mean(), 1e-20)))
        corr = float(np.corrcoef(L, R)[0, 1]) if L.std() > 0 and R.std() > 0 else 1.0
        return bal, corr

    r = LoopbackRenderer()
    try:
        al = r.al
        assert al.alIsExtensionPresent(b'AL_SOFT_direct_channels'),             'AL_SOFT_direct_channels is required to keep flat sound out of the HRTF'
        mode = (OA.AL_REMIX_UNMATCHED_SOFT
                if al.alIsExtensionPresent(b'AL_SOFT_direct_channels_remix')
                else OA.AL_TRUE)
        for rel in (AMBIENCE,):
            pcm = dec(os.path.join(BUNDLE, *rel))
            assert pcm.channels == 2
            n = pcm.frames
            src = pcm.samples.astype(np.float64) / 32768.0
            buf = (c_uint * 1)()
            al.alGenBuffers(1, buf)
            raw = pcm.tobytes()
            al.alBufferData(buf[0], OA.AL_FORMAT_STEREO16, raw, len(raw),
                            pcm.sample_rate)
            s = (c_uint * 1)()
            al.alGenSources(1, s)
            sid = s[0]
            al.alSourcei(sid, OA.AL_BUFFER, buf[0])
            al.alSourcei(sid, OA.AL_SOURCE_RELATIVE, OA.AL_TRUE)
            al.alSourcef(sid, OA.AL_ROLLOFF_FACTOR, 0.0)
            al.alSource3f(sid, OA.AL_POSITION, 0.0, 0.0, 0.0)
            al.alSourcei(sid, OA.AL_DIRECT_CHANNELS_SOFT, mode)
            al.alSourcePlay(sid)
            out = OA.render_samples(al, r.device, n, 2)
            d = np.ctypeslib.as_array(out).reshape(-1, 2).copy()
            al.alSourceStop(sid)
            al.alDeleteSources(1, s)

            sb, sc = stats(src)
            ob, oc = stats(d)
            name = rel[-1]
            assert abs(ob - sb) < 0.2, f'{name}: balance moved {sb:+.2f} -> {ob:+.2f}'
            assert abs(oc - sc) < 0.05, f'{name}: width changed {sc:.3f} -> {oc:.3f}'
    finally:
        r.close()


def test_spatialised_sources_are_not_direct_channelled():
    """3D sound must still reach the HRTF."""
    from papasangre2.audio.engine import AudioEngine, SoundSpec
    from papasangre2.audio import openal as OA
    eng = AudioEngine()
    eng.open()
    try:
        flat = eng.load(SoundSpec('flat', os.path.join(
            BUNDLE, *AMBIENCE), spatialized=False))
        spatial = eng.load(SoundSpec('spatial', os.path.join(
            BUNDLE, *STEREO_SPA),
            spatialized=True))
        flat.play()
        spatial.play()
        from ctypes import c_int, byref
        v = c_int(0)
        eng.al.alGetSourcei(flat.source, OA.AL_DIRECT_CHANNELS_SOFT, byref(v))
        assert v.value != OA.AL_FALSE, 'flat sound should bypass the HRTF'
        eng.al.alGetSourcei(spatial.source, OA.AL_DIRECT_CHANNELS_SOFT, byref(v))
        assert v.value == OA.AL_FALSE, 'spatial sound must go through the HRTF'
        flat.stop()
        spatial.stop()
    finally:
        eng.close()


# ------------------------------------------------------- per-level reverb
def test_reverb_starts_where_pgengine_init_leaves_it():
    """2.1 / 5 / 1 from -[PGEngine init]; a level then sets its own."""
    from papasangre2.audio.engine import (REVERB_DAMPENING, REVERB_ROOM_SIZE,
                                          REVERB_VOLUME)
    assert (REVERB_ROOM_SIZE, REVERB_DAMPENING, REVERB_VOLUME) == (2.1, 5.0, 1.0)


def test_reverb_setters_clamp_like_s3dengine():
    """setReverbRoomSize: clamps to [0.01, 2.3] (0x100125c3c / 0x100125c64)."""
    from papasangre2.audio.engine import reverb_params
    assert reverb_params(9.0, 50, 1) == reverb_params(2.3, 50, 1)       # room size capped
    assert reverb_params(1.5, 150, 1) == reverb_params(1.5, 100, 1)     # dampening capped
    assert reverb_params(1.5, 0, 20) == reverb_params(1.5, 0, 8)        # volume capped at 8
    assert reverb_params(1.5, 100, 0)['GAIN'] == 0.0


def test_a_different_level_reverb_really_changes_the_tail():
    """Not just that the call succeeds - that the tail actually differs."""
    from papasangre2.audio.engine import AudioEngine, SoundSpec
    import glob
    snd = sorted(glob.glob(os.path.join(BUNDLE, *HITWALL, '*.m4a')))[0]

    def tail(settings):
        eng = AudioEngine()
        eng.open(loopback=True)
        try:
            if eng.reverb_slot is None:
                return None
            assert eng.set_reverb(*settings)
            s = eng.load(SoundSpec('t', snd, spatialized=True))
            s.send_to_reverb = True
            s.wet_gain = 1.0
            s.planar = (0.0, 40.0)
            s.play()
            frames, energy = 0, 0.0
            while frames < 44100 * 2:
                buf = eng.render(2048)
                if frames >= 22050:          # after the sound itself is done
                    energy += sum(v * v for v in buf)
                frames += len(buf) // 2
            return energy
        finally:
            eng.close()

    long_room = tail((2.3, 70.0, 1.0))        # ps2_7-like, loud room
    if long_room is None:
        return                                # no EFX on this machine
    quiet = tail((1.5, 100.0, 0.2))           # ps2_Intro: volume 0.2
    assert quiet < long_room * 0.5, 'a level asking for less reverb must get less'


if __name__ == '__main__':
    fns = [v for k, v in sorted(globals().items()) if k.startswith('test_')]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f'  PASS  {fn.__name__}')
        except Exception as e:                                   # noqa: BLE001
            failed += 1
            print(f'  FAIL  {fn.__name__}: {e}')
    print(f'\n{len(fns) - failed}/{len(fns)} passed')
    raise SystemExit(1 if failed else 0)


def _flat_render(name: str, spatialized_in_playlist: bool, seconds: float = 2.0):
    import glob
    from papasangre2.audio.engine import AudioEngine, SoundSpec
    from papasangre2.util import paths
    path = glob.glob(os.path.join(paths.game_bundle(), 'sounds', '**', name + '.*'),
                     recursive=True)[0]
    e = AudioEngine(want_reverb=False)
    e.open(loopback=True)
    try:
        s = e.load(SoundSpec(name, path, spatialized=spatialized_in_playlist))
        s.spatialized = False
        s.play()
        out = np.asarray(e.render(int(44100 * seconds))).reshape(-1, 2)
        s.stop()
        return out, decode(path), e.master_gain * e.master_volume
    finally:
        e.close()


def test_a_flat_mono_voice_is_half_level_in_each_ear_and_no_hrtf():
    """setupPlain: a one-channel file goes through csl::Panner at its centre -
    0.5 to each ear - and never through the binaural spatialiser (Muhammad:
    the hat voice and the skip ping sounded 3D)."""
    out, pcm, master = _flat_render('5a_SPEECH_intro1_SPA_UOS', True)
    assert pcm.channels == 1
    L, R = out[:, 0], out[:, 1]
    assert np.allclose(L, R, atol=1e-6)
    n = min(len(L), len(pcm.samples))
    ref = pcm.samples[:n, 0].astype(np.float64) / 32768.0
    gain = np.sqrt(np.mean(L[:n] ** 2)) / np.sqrt(np.mean(ref ** 2))
    assert abs(20 * math.log10(gain) - 20 * math.log10(0.5 * master)) < 0.2


def test_a_flat_stereo_file_plays_as_it_is():
    """setupPlain leaves a two-channel file alone: each ear gets its own
    channel, untouched but for the master volume (and OpenAL's start-up lag)."""
    out, pcm, master = _flat_render('INTRO_SPEECH_training_10a_UOS', False)
    assert pcm.channels == 2
    src = pcm.samples.astype(np.float64) / 32768.0
    n = 60000
    lag = max(range(0, 2000), key=lambda k: float(np.dot(out[k:k + n, 0], src[:n, 0])))
    for ch in (0, 1):
        x, y = out[lag:lag + n, ch], src[:n, ch]
        assert np.corrcoef(x, y)[0, 1] > 0.9999
        gain = np.sqrt(np.mean(x ** 2)) / np.sqrt(np.mean(y ** 2))
        assert abs(20 * math.log10(gain) - 20 * math.log10(master)) < 0.05


def test_a_hit_sent_from_a_door_is_heard_from_the_door():
    """Decision 17: ps2_14's extinguisher hit on the banging door (a stereo,
    flat file in the playlist) played where the door is: rendered from either
    side of the head, the ears must tell the two apart."""
    import glob
    from papasangre2.audio.engine import AudioEngine, SoundSpec
    from papasangre2.audio.measure import interaural
    from papasangre2.util import paths
    name = '14_break_door_with_extinguisher_a'
    path = glob.glob(os.path.join(paths.game_bundle(), 'sounds', '**', name + '.*'),
                     recursive=True)[0]
    e = AudioEngine(want_reverb=False)
    e.open(loopback=True)
    try:
        e.set_listener((0.0, 0.0), 0.0)
        ild = {}
        for side, where in (('a', (0.0, 40.0)), ('b', (0.0, -40.0))):
            s = e.load(SoundSpec(name, path, spatialized=False))
            s.spatialized = True
            s.planar = where
            s.play()
            out = np.asarray(e.render(44100)).reshape(-1, 2)
            s.stop()
            ild[side] = interaural(out)[1]
        assert abs(ild['a'] - ild['b']) > 6.0, ild
        assert (ild['a'] > 0) != (ild['b'] > 0), ild
    finally:
        e.close()


def test_muhammads_penguin_death_is_heard_from_the_penguin():
    """Decision 18: the requested WAV (stereo) decodes, is folded to one channel
    for the spatialiser and is placed: left and right render differently."""
    from papasangre2.assets import requested
    from papasangre2.audio.engine import AudioEngine, SoundSpec
    from papasangre2.audio.measure import interaural
    file, spatialized = requested.SOUNDS[requested.PENGUIN_STAB_DEATH]
    path = requested.sound_path(file)
    assert path is not None and spatialized
    e = AudioEngine(want_reverb=False)
    e.open(loopback=True)
    try:
        e.set_listener((0.0, 0.0), 0.0)
        ild = {}
        for side, where in (('a', (0.0, 40.0)), ('b', (0.0, -40.0))):
            s = e.load(SoundSpec(requested.PENGUIN_STAB_DEATH, path, spatialized=True))
            s.planar = where
            s.play()
            out = np.asarray(e.render(44100)).reshape(-1, 2)
            s.stop()
            assert np.sqrt(np.mean(out ** 2)) > 1e-3          # it is heard
            ild[side] = interaural(out)[1]
        assert abs(ild['a'] - ild['b']) > 6.0, ild
    finally:
        e.close()
