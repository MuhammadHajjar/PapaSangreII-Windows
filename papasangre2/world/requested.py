"""The owner's requested additions to the level data (decision 21, 2026-09-25).

Lines the original recorded and never lets you hear - found by
``tools/unused_speech.py`` or reported by a tester - wired in the way the
level's own data wires its lines: agents, triggers and sound lists written in
the game's trigger language, applied to the loaded level before it is built.
The behaviours that data cannot express (the hand and knife waving, the idle
hints' clock, the wall and trip lines per level) are in the player and the
level; this is the data half.  Each entry says why.
"""

from __future__ import annotations

from ..assets.tiled import LevelData, LevelObject, parse_trigger_statement

#: New agents, by level: (type, name, x, y, properties, [(trigger, statement)]).
AGENTS: dict[str, list] = {
    'ps2_Intro': [
        # "Face the music. Holding the glass thing in front of you, turn your
        # body to face it." - the reminder for the second turning lesson, as
        # Intro0a_prompt is for the first: a while after intro1a, until you
        # face the memory.
        ('Sound', 'intro1a_timer', 70.0, -38.0,
         {'active': False, 'collideRadius': 0.0},
         [('OnActivate', 'ActivateAgentWithName:name=intro1a_prompt;afterDelay=8')]),
        ('Sound', 'intro1a_prompt', 70.0, -38.0,
         {'active': False, 'gain': 1.8, 'looping': True, 'skippable': False,
          'soundList': 'INTRO_SPEECH_training_1a_prompt_SPA_UOS', 'spatialized': True}, []),
        # "Good. Keep going." - half a second after the first "see the fountain
        # / gramophone" of the 360-degree turn, when there is more to turn.
        # Priority 1, under the prompts' 2: it never starts over one of them,
        # and the second one cuts it short rather than being dropped for it
        # (the tester heard the two together).  Reaching the second landmark
        # (turn_back_to_me_prompt's second activation) removes it for good.
        ('Sound', 'keep_going', 72.0, -36.0,
         {'active': False, 'gain': 1.8, 'looping': False, 'skippable': False,
          'soundList': 'INTRO_SPEECH_training_thats_it_SPA_UOS', 'soundPriority': 1,
          'spatialized': True}, []),
    ],
    'ps2_1': [
        # "Smash the case open with your hand." - once, 8 s after the display
        # case's long explanation, if the case is still whole.  (It had been an
        # alternative take OF that explanation, so half the time the case was
        # never explained - the tester's report.)
        ('Sound', 'open_case_timer', -176.0, -6.0,
         {'active': False, 'collideRadius': 0.0},
         [('OnActivate', 'ActivateAgentWithName:name=open_case_prompt;afterDelay=8')]),
        ('Sound', 'open_case_prompt', -176.0, -6.0,
         {'active': False, 'collideRadius': 0.0, 'looping': False, 'skippable': False,
          'soundList': '1_SPEECH_open_case', 'soundPriority': 2, 'spatialized': False,
          'wetGain': 0.0},
         [('OnSoundEnd', 'DeactivateAgentWithName:name=open_case_prompt')]),
    ],
    'ps2_7': [
        # "Press your right and left hands to pull yourself out of the hole." -
        # a reminder in the first hole, 5 s after the fall warning, unless you
        # have started climbing (a hand press stops the timer).
        ('Sound', 'pull_timer', -255.0, -73.0,
         {'active': False, 'collideRadius': 0.0},
         [('OnActivate', 'ActivateAgentWithName:name=pull_prompt;afterDelay=5')]),
        ('Sound', 'pull_prompt', -255.0, -73.0,
         {'active': False, 'collideRadius': 0.0, 'gain': 1.3, 'looping': False,
          'skippable': False, 'soundList': '7_SPEECH_prompt_pull_yourself_out',
          'soundPriority': 3, 'spatialized': False},
         [('OnSoundEnd', 'DeactivateAgentWithName:name=pull_prompt')]),
    ],
}

#: More triggers on existing objects: (level, object) -> [(trigger, statement)].
TRIGGERS: dict[tuple[str, str], list] = {
    ('ps2_Intro', 'intro1a'): [
        ('OnSoundEnd', 'ActivateAgentWithName:name=intro1a_timer')],
    ('ps2_Intro', 'memory1active'): [
        ('OnEnteringShootRange', 'DeactivateAgentWithName:name=intro1a_timer;clean=YES'),
        ('OnEnteringShootRange', 'DeactivateAgentWithName:name=intro1a_prompt')],
    ('ps2_Intro', 'see_fountain_prompt'): [
        ('OnSoundEnd', 'ActivateAgentWithName:name=keep_going;count=1;afterDelay=0.5')],
    ('ps2_Intro', 'see_gramophone_prompt'): [
        ('OnSoundEnd', 'ActivateAgentWithName:name=keep_going;count=1;afterDelay=0.5')],
    ('ps2_Intro', 'turn_back_to_me_prompt'): [
        ('OnActivate', 'DeallocAgentWithName:name=keep_going')],
    ('ps2_1', 'smash_instructions'): [
        ('OnSoundEnd', 'ActivateAgentWithName:name=open_case_timer;count=1')],
    # Reaching the gramophone player in ps2_5a stopped "come over here" and
    # then left 6 s of crackle (its collect sound) before the scene went on -
    # the tester turned about, thinking he had to set it off.  The scene now
    # goes on a second after you arrive: the machine goes quiet first, as its
    # crackle is the same sound the button then plays (see DROP_TRIGGERS).
    ('ps2_5a', 'machine'): [
        ('OnCollide', 'DeactivateAgentWithName:name=machine;afterDelay=1'),
        ('OnCollide', 'PGE_MESSAGE_DisableWalk:afterDelay=1'),
        ('OnCollide', 'PGE_MESSAGE_DisableHands:afterDelay=1'),
        ('OnCollide', 'ActivateAgentWithName:name=button;afterDelay=1')],
    ('ps2_1', 'memory3'): [
        ('OnLeftHand', 'DeactivateAgentWithName:name=open_case_timer;clean=YES'),
        ('OnRightHand', 'DeactivateAgentWithName:name=open_case_timer;clean=YES'),
        ('OnLeftHand', 'DeactivateAgentWithName:name=open_case_prompt'),
        ('OnRightHand', 'DeactivateAgentWithName:name=open_case_prompt')],
    ('ps2_7', 'floor_fall_warning'): [
        ('OnSoundEnd', 'ActivateAgentWithName:name=pull_timer')],
    ('ps2_7', 'hand_release1'): [
        ('OnLeftHand', 'DeactivateAgentWithName:name=pull_timer;clean=YES'),
        ('OnRightHand', 'DeactivateAgentWithName:name=pull_timer;clean=YES'),
        ('OnLeftHand', 'DeactivateAgentWithName:name=pull_prompt'),
        ('OnRightHand', 'DeactivateAgentWithName:name=pull_prompt')],
    # The tester: your feet stay still while the camera tumbles out and you
    # are told how to use it (the data leaves walking on through the scene).
    # A dropped or skipped camera line ends it too, so it cannot trap you.
    ('ps2_18', 'memory3'): [
        ('OnCollect', 'PGE_MESSAGE_DisableWalk')],
    ('ps2_18', 'camera_prompt'): [
        ('OnSoundEnd', 'PGE_MESSAGE_EnableWalk')],
    # "Quick, move!" - after the first two memories are smashed, as the third
    # has its "Last one, quick!" (16_SPEECH_oncollect_final, a second after).
    ('ps2_16', 'memory1'): [
        ('OnLeftHand', 'PlaySound:soundName=16_SPEECH_oncollect_1;afterDelay=1'),
        ('OnRightHand', 'PlaySound:soundName=16_SPEECH_oncollect_1;afterDelay=1')],
    ('ps2_16', 'memory2'): [
        ('OnLeftHand', 'PlaySound:soundName=16_SPEECH_oncollect_1;afterDelay=1'),
        ('OnRightHand', 'PlaySound:soundName=16_SPEECH_oncollect_1;afterDelay=1')],
}

#: Triggers taken off: ps2_1's own "stop waving your hands" (the third press,
#: once) gives way to the waving rule in the player (6 alternate presses).
#: An entry is a trigger type (all of its statements) or (type, statement).
DROP_TRIGGERS: dict[tuple[str, str], tuple] = {
    ('ps2_1', 'hand_detector'): ('OnLeftHand', 'OnRightHand'),
    ('ps2_5a', 'machine'): ('OnSoundEnd',),        # moved to OnCollide, see TRIGGERS
}

#: A trigger changed: (level, object) -> [(trigger, statement as the data
#: writes it, field, new value)] - `after_delay` or `after_count`, as the
#: data's afterDelay / afterCount.
CHANGED_TRIGGERS: dict[tuple[str, str], list] = {
    # (The Intro's record scratch was moved here to 35.5 s for a while; the
    # original's 36 s was right all along - the port's game clock ran slow,
    # core/game.py Game.update, and made every delay late.)
    # The hold music takes 16 shakes, not 8 (afterCount=15 lets the 16th
    # through): the tester found 8 Ctrl presses over too quickly, and the
    # owner chose 16.
    ('ps2_18b', 'instruction_shake'): [
        ('OnShake', 'ActivateAgentWithName:name=after_shake;afterCount=7',
         'after_count', '15')],
}

#: Other takes of a line, added to the agent's sound list (one is drawn each time).
EXTRA_TAKES: dict[tuple[str, str], str] = {
    ('ps2_14', 'use_extinguisher_to_collect_2'): '14_SPEECH_smash_it_UOS',   # "Smash it!"
    ('ps2_14', 'use_extinguisher_to_collect_3'): '14_SPEECH_smash_it_UOS',
    ('ps2_18', 'keep_moving'): '18_SPEECH__keep_moving',            # the second set of three takes
}

#: A sound name the data spells wrongly: (level, wrong) -> right.  ps2_14's
#: "Watch out! / Careful! / Watch it!" for coming near a burning wall again
#: (the long warning is once only): the data asks for 14__SPEECH_..., the files
#: are 14_SPEECH__...
RENAMES: dict[tuple[str, str], str] = {
    ('ps2_14', '14__SPEECH_warning_short'): '14_SPEECH__warning_short',
}

#: Idle hints (the level's `inactivitySounds`) for levels whose data has none
#: though the line was recorded for them.  ps2_14's data names level 7's hint
#: (the cat, the burning house) - a copy from level 7, and not loaded there -
#: so it has none.
INACTIVITY: dict[str, str | None] = {
    'ps2_9': '9_SPEECH_hint',
    'ps2_10': '10_SPEECH_hint',
    'ps2_14': None,
}

#: Lines a level names but its playlists do not load: name -> file in the
#: bundle, loaded into that level's bank.
ENSURE: dict[str, dict[str, str]] = {
    'ps2_18': {'11b_SPEECH_hint_shooting': 'sounds/ps2_11b/11b_SPEECH_hint_shooting.m4a'},
    'ps2_5a': {'INTRO_SPEECH_prompt_no_walk_SPA_UOS':
               'sounds/ps2_Intro/INTRO_SPEECH_prompt_no_walk_SPA_UOS.m4a'},
    'ps2_11a': {'INTRO_SPEECH_prompt_no_walk_SPA_UOS':
                'sounds/ps2_Intro/INTRO_SPEECH_prompt_no_walk_SPA_UOS.m4a'},
}


def _triggers(pairs) -> list:
    out = []
    for ttype, stmt in pairs:
        t = parse_trigger_statement(ttype, stmt)
        if t is not None:
            t.key = ttype
            out.append(t)
    return out


def apply(data: LevelData) -> None:
    """Change a freshly loaded level's data (once)."""
    if getattr(data, '_requested', False):
        return
    data._requested = True
    lv = data.name
    by_name = {o.name: o for o in data.agents}
    next_id = max([o.agent_id for o in data.agents] + [0]) + 1
    for kind, name, x, y, props, pairs in AGENTS.get(lv, ()):
        obj = LevelObject(type=kind, cls='PGESound', name=name, layer='requested',
                          x=x, y=y, raw=dict(props), applied=dict(props),
                          triggers=_triggers(pairs), agent_id=next_id)
        next_id += 1
        data.agents.append(obj)
        by_name[name] = obj
    for (level, name), pairs in TRIGGERS.items():
        if level == lv and name in by_name:
            by_name[name].triggers.extend(_triggers(pairs))
    for (level, name), drops in DROP_TRIGGERS.items():
        if level == lv and name in by_name:
            o = by_name[name]
            o.triggers = [t for t in o.triggers
                          if t.trigger_type not in drops and (t.trigger_type, t.raw) not in drops]
    for (level, name), changes in CHANGED_TRIGGERS.items():
        if level == lv and name in by_name:
            for ttype, raw, field, value in changes:
                for t in by_name[name].triggers:
                    if t.trigger_type == ttype and t.raw == raw:
                        setattr(t, field, value)
    for (level, name), take in EXTRA_TAKES.items():
        if level == lv and name in by_name:
            o = by_name[name]
            o.applied['soundList'] = '%s&%s' % (o.applied.get('soundList', ''), take)
    for (level, wrong), right in RENAMES.items():
        if level != lv:
            continue
        for o in data.objects:
            for t in o.triggers:
                if t.parameters.get('soundName') == wrong:
                    t.parameters['soundName'] = right
    if lv in INACTIVITY:
        data.inactivity_sound_list = INACTIVITY[lv]


def ensure_sounds(bank, level: str) -> int:
    """Load the lines `ENSURE` names into this level's bank."""
    n = 0
    for name, rel in ENSURE.get(level, {}).items():
        if bank is not None and hasattr(bank, 'ensure') and bank.ensure(name, rel, spatialized=False):
            n += 1
    return n
