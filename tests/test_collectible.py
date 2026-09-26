"""`PGECollectible`'s own versions of the agent's methods - each one the port
had missed until Muhammad's report of a memory falling silent (M3)."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from papasangre2.sim import Sim                                   # noqa: E402


def test_a_memory_that_names_only_a_gain_collects_at_it():
    """-[PGECollectible setGain:]: the collect gain follows the gain while 1."""
    assert Sim('ps2_1').level.agent('memory1').collect_gain == 0.7
    assert Sim('ps2_4').level.agent('memory1').collect_gain == 0.5      # both named
    assert Sim('ps2_Intro').level.agent('memory1').collect_gain == 0.55
    assert Sim('ps2_3').level.agent('easter_egg').collect_gain == 1.0   # gain 1.0


def test_the_collect_sound_plays_at_that_gain():
    sim = Sim('ps2_2')
    m = sim.level.agent('memory1')
    sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': 'memory1'})
    sim.run_until(lambda: m.sound is not None and m.sound.name == m.loop_sound, limit=10)
    m.position = sim.player.position
    sim.run_until(lambda: m.sound is not None and m.sound.name == m.collect_sound, limit=5)
    assert m.sound.gain == 0.7


def test_deactivating_forgets_it_was_collected():
    sim = Sim('ps2_2')
    m = sim.level.agent('memory1')
    m.collected = True
    assert m.sound_priority == m._own_priority
    m.set_active(True)
    sim.step(0.05)
    m.deactivate()
    assert m.collected is False and m.sound_priority == 0


def test_collect_agent_with_name():
    sim = Sim('ps2_2')
    m = sim.level.agent('memory1')
    sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': 'memory1'})
    sim.step(0.1)
    sim.bus.post('PGE_MESSAGE_CollectAgentWithName', {'name': 'memory1'})
    assert m.collected                             # ignoreLoop: at once


def test_a_shake_collectible_left_in_reach_collects_itself_after_20_s():
    sim = Sim('ps2_2')
    m = sim.level.agent('memory1')
    m.collect_with_shake = True
    m.position = sim.player.position               # really in reach
    sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': 'memory1'})
    sim.step(0.1)
    assert m.in_collide_range and not m.collected  # a shake one waits to be shaken
    sim.run_until(lambda: m.collected, limit=19.5)
    assert not m.collected
    sim.run_until(lambda: m.collected, limit=1.0)
    assert m.collected


def test_a_cancel_wet_gain_door_plays_its_cutscene_dry():
    """-[PGECollectible playCollectSound] sets the *collectible's* wet gain to 0
    and then setupReverbParameters puts it on the sound (Muhammad: the exits
    had reverb they never had)."""
    sim = Sim('ps2_1')
    door = sim.level.agent('door')
    assert door.cancel_wet_gain
    sim.bus.post('PGE_MESSAGE_ActivateAgentWithName', {'name': 'door'})
    sim.run_until(lambda: door.sound is not None and door.sound.name.startswith('buzzer_loop'),
                  limit=20)
    sim.bus.post('PGE_MESSAGE_MovePlayerToPosition', {'position': door.position})
    sim.run_until(lambda: door.sound is not None and door.sound.name == door.collect_sound,
                  limit=5)
    assert door.sound.name == '1_end_UOS'
    assert door.sound.wet_gain == 0.0 and not door.sound.send_to_reverb


def test_a_door_without_cancel_wet_gain_keeps_its_reverb():
    """ps2_9's (the submarine's) exit has no cancelWetGain: it keeps the room."""
    from papasangre2.world.level import Level   # noqa: F401
    sim = Sim('ps2_9')
    door = sim.level.agent('door')
    assert not door.cancel_wet_gain
    assert door.wet_gain > 0
