"""Decision 14 (a memory shaken loose takes seven Ctrl presses, each one a
whoosh) and the PC instructions switch in Settings (2026-09-25)."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from papasangre2.entities.collectible import SHAKES_TO_COLLECT   # noqa: E402
from papasangre2.sim import Sim                                   # noqa: E402
from papasangre2.util.settings import Settings                    # noqa: E402
from test_game import make_game                                   # noqa: E402


def _shakeable(sim):
    m = sim.level.agent('intro2_collectible')
    sim.bus.post('PGE_MESSAGE_MovePlayerToPosition', {'position': m.position})
    sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': 'intro2_collectible'})
    sim.run_until(lambda: m.active and m.in_collide_range, limit=5)
    return m


def test_a_memory_takes_seven_shakes_each_a_whoosh():
    sim = Sim('ps2_5a')
    whooshes = []
    sim.level.play_whoosh = lambda: whooshes.append(sim.now)
    m = _shakeable(sim)
    assert SHAKES_TO_COLLECT == 7
    for _ in range(6):
        sim.shake()
    assert not m.collected and len(whooshes) == 6
    sim.shake()
    assert m.collected and len(whooshes) == 7
    sim.shake()                                    # nothing left to shake
    assert len(whooshes) == 7


def test_no_whoosh_with_nothing_to_shake():
    sim = Sim('ps2_5a')
    whooshes = []
    sim.level.play_whoosh = lambda: whooshes.append(sim.now)
    sim.step(0.5)
    for _ in range(3):
        sim.shake()
    assert whooshes == []


def test_the_shakes_start_again_when_the_memory_does():
    sim = Sim('ps2_5a')
    sim.level.play_whoosh = lambda: None
    m = _shakeable(sim)
    for _ in range(4):
        sim.shake()
    m.deactivate()
    assert m.shakes == 0


def test_the_game_plays_its_own_whoosh(tmp_path):
    g = make_game(tmp_path)
    g.play_whoosh()
    s = g.menu_bank.sound('whoosh')
    assert s is not None and s.playing and not s.spatialized


def test_pc_instructions_is_a_setting_on_by_default(tmp_path):
    s = Settings(str(tmp_path / 'settings.json'))
    assert s.pc_instructions
    s.toggle('pcInstructions')
    assert not Settings(str(tmp_path / 'settings.json')).pc_instructions


def test_pc_instructions_off_says_nothing_after_a_line(tmp_path):
    g = make_game(tmp_path)
    g._line_ended('INTRO_SPEECH_training_6_SPA_UOS')
    assert g.said == ['press Q and E together']
    g.settings.toggle('pcInstructions')
    g._line_ended('INTRO_SPEECH_training_6_SPA_UOS')
    assert g.said == ['press Q and E together']


def test_the_settings_menu_has_the_switch(tmp_path):
    from papasangre2.shell.menu import settings_menu
    s = Settings(str(tmp_path / 'settings.json'))
    labels = [i.label for i in settings_menu(s).items]
    assert any(label.startswith('PC instructions') for label in labels)


def test_the_shake_sound_is_a_setting_on_by_default(tmp_path):
    # REQUESTED 2026-09-26: some players will want the whoosh, some will not
    from papasangre2.shell.menu import settings_menu
    g = make_game(tmp_path)
    assert g.settings.shake_whoosh
    labels = [i.label for i in settings_menu(g.settings).items]
    assert 'Shake sound, on' in labels
    g.settings.toggle('shakeWhoosh')
    s = g.menu_bank.sound('whoosh')
    s.stop()
    g.play_whoosh()
    assert not s.playing
    assert not Settings(g.settings.path).shake_whoosh           # kept for next time
    g.settings.toggle('shakeWhoosh')
    g.play_whoosh()
    assert s.playing
