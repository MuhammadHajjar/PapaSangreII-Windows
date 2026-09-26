"""The PC equivalents of the tutorial lines (decision 8).

The training narration is recorded speech about a touchscreen, and it cannot
be re-recorded.  So each line that tells you *how* to do something with the
phone plays as recorded, and then the screen reader says how to do it here,
naming whatever the keys (and, with one connected, the controller buttons)
are bound to at that moment - a rebound key is spoken as rebound.

Which lines, and why - every line of ps2_Intro was transcribed
(`build/transcripts/intro.medium.en.json`, faster-whisper medium.en) and only
those that describe the phone or a physical movement get a PC version:

* `blind_ps2_skip_tuto` - the skip button, pause button, feet and hands on the
  screen, swiping to turn (VoiceOver take; the sighted take is silence);
* `INTRO_SPEECH_training_0a` - "Turn all the way around. Slowly. 360 degrees";
* `INTRO_SPEECH_training_0a_prompt` - "Hold the glass thing in front of you
  and turn your whole body right around until you're facing me again";
* `INTRO_SPEECH_training_1a` - "turn so it's in front of you";
* `INTRO_SPEECH_training_1a_prompt` - "Holding the glass thing in front of
  you, turn your body to face it" (in the bundle; no Intro object plays it);
* `INTRO_SPEECH_training_turn_to_face_me` - "Now, turn back to face me";
* `INTRO_SPEECH_prompt_no_walk` - "Use your thumbs to move your feet on the
  bottom left and right of the screen";
* `INTRO_SPEECH_training_6` - "until you clap your hands to scare us off";
* `INTRO_SPEECH_prompt_no_clap` - "Clap, by pressing the hands at the top
  left and right of the glass thing at the same time";
* `INTRO_SPEECH_training_10a` - "open the door, use your hand, either one";
* `INTRO_SPEECH_training_prompt_open_door` - "press either of the hands at
  the top left or right of the glass thing" (nothing in the Intro activates
  it).

The museum levels (ps2_1 to ps2_4), from the same transcription: ps2_1's
"Press the top corners of the glass thing to clap" and "You'll need to smash
it open with your hand" (and the unused "Smash the case open with your
hand"), and ps2_4's "When you're ready, clap your hands".

Levels 5 to 7 (`build/transcripts/medium.en.json`): ps2_5a's "Hold it up. As
if you're taking a picture", its looping "Hold it up as if you're taking a
picture" and "Hold it the other way" (both keys are named, so the player still
chooses how to hold it, as on the phone); "Now shake it as hard as you can";
"Start the record with your left or right hand"; ps2_6's "Air rifle in your
left hand"; and ps2_7's "Use your hands to climb back out" and "Use your
hands!" (plus the unused "Press your right and left hands to pull yourself
out").

Levels 8 to 10: ps2_8's "clap your hands to scare it off", "The penguin's too
close, clap, quick!" and "Your hands are free, so you can clap if you need
to"; ps2_9's "Open the hatch with your left hand" (a PlaySound line); ps2_10's
"throw the glass in your bag with your right hand".

Levels 11a to 13: ps2_11a's "put it on your head. Use a hand"; ps2_11b's
"the water pistol in your left hand"; ps2_12's "use the air rifle in your left
hand" and its "Shake it. Smash it." (the prompt and the release line); ps2_13's
"destroy it with your hands", "USE HAND!", "Use your hands!" at the needle and
its own "Shake it!" lines.  "Lift the needle" and "Put the needle on the
record" name no control and get nothing.

Lines that only say *what* to do - "Walk to the memory", "just clap", "Head
for that", ps2_1's "if you can hear me, clap", ps2_2's "break the glass" and
"smash this one too", the "stop waving your hands about" nags - name no
control and get nothing.  A looping prompt gets its PC
version once, after its first pass; a line that is skipped gets none.
"""

from __future__ import annotations

from .input.keymap import Action
from .input.padmap import button_label

_KEY_NAMES = {
    'return': 'Enter', 'keypad enter': 'keypad Enter', 'escape': 'Escape',
    'backspace': 'Backspace', 'space': 'Space', 'tab': 'Tab',
    'left': 'Left arrow', 'right': 'Right arrow', 'up': 'Up arrow',
    'down': 'Down arrow', 'left ctrl': 'Left Control', 'right ctrl': 'Right Control',
    'left shift': 'Left Shift', 'right shift': 'Right Shift',
    'left alt': 'Left Alt', 'right alt': 'Right Alt',
    'page up': 'Page Up', 'page down': 'Page Down',
}


def key_name(key: str) -> str:
    k = str(key).lower()
    if k in _KEY_NAMES:
        return _KEY_NAMES[k]
    if len(k) == 1:
        return k.upper()
    return k


def keys(keymap, action) -> str:
    ks = keymap.keys_for(action)
    if not ks:
        return 'an unbound key'
    return ' or '.join(key_name(k) for k in ks)


def buttons(padmap, action) -> str:
    bs = padmap.buttons_for(action)
    if not bs:
        return 'an unbound button'
    return ' or '.join(button_label(b) for b in bs)


def pc_lines(keymap, padmap=None, pad_connected=lambda: False) -> dict:
    """Sound name -> a function returning the words to say after it."""
    A = Action

    def k(a):
        return keys(keymap, a)

    def pad(text):
        """The controller's version, built only when one is connected."""
        if padmap is None or not pad_connected():
            return ''
        return ' On the controller: ' + (text() if callable(text) else text)

    def b(a):
        return buttons(padmap, a)

    def turning():
        return (f'On this computer, turn with {k(A.TURN_LEFT)} and {k(A.TURN_RIGHT)}; '
                'hold one down to keep turning.'
                + pad('push the left stick left or right.'))

    def walking():
        return (f'On this computer, your feet are {k(A.FOOT_LEFT)} and {k(A.FOOT_RIGHT)}. '
                'Press them one after the other to walk forward.'
                + pad(lambda: f'{b(A.FOOT_LEFT)} and {b(A.FOOT_RIGHT)}, one after the other.'))

    def clapping():
        return (f'On this computer, clap by pressing both hands, {k(A.HAND_LEFT)} and '
                f'{k(A.HAND_RIGHT)}, at the same time.'
                + pad(lambda: f'{b(A.HAND_LEFT)} and {b(A.HAND_RIGHT)} together.'))

    def one_hand():
        return (f'On this computer, your left hand is {k(A.HAND_LEFT)} and your right '
                f'hand is {k(A.HAND_RIGHT)}. Press either one.'
                + pad(lambda: f'{b(A.HAND_LEFT)} or {b(A.HAND_RIGHT)}.'))

    def holding():
        return (f'On this computer, {k(A.PHONE_UPRIGHT)} holds the phone upright and '
                f'{k(A.PHONE_SIDEWAYS)} holds it on its side.'
                + pad(lambda: f'{b(A.PHONE_UPRIGHT)} upright, {b(A.PHONE_SIDEWAYS)} on its side.'))

    def shaking():
        return (f'On this computer, shake it by pressing {k(A.SHAKE)} again and again.'
                + pad(lambda: f'{b(A.SHAKE)}, again and again.'))

    def rifle():
        return (f'On this computer, your left hand is {k(A.HAND_LEFT)}: it fires the rifle.'
                + pad(lambda: f'{b(A.HAND_LEFT)}.'))

    def left_hand():
        return (f'On this computer, your left hand is {k(A.HAND_LEFT)}.'
                + pad(lambda: f'{b(A.HAND_LEFT)}.'))

    def pistol():
        return (f'On this computer, your left hand is {k(A.HAND_LEFT)}: it fires the water pistol.'
                + pad(lambda: f'{b(A.HAND_LEFT)}.'))

    def throwing():
        return (f'On this computer, your right hand is {k(A.HAND_RIGHT)}: it throws the glass.'
                + pad(lambda: f'{b(A.HAND_RIGHT)}.'))

    def extinguisher():
        return (f'On this computer, your left hand is {k(A.HAND_LEFT)}: it holds the extinguisher.'
                + pad(lambda: f'{b(A.HAND_LEFT)}.'))

    def extinguisher_and_sand():
        return (f'On this computer, your left hand is {k(A.HAND_LEFT)}: the extinguisher. '
                f'Your right hand is {k(A.HAND_RIGHT)}: it throws the sand.'
                + pad(lambda: f'{b(A.HAND_LEFT)} and {b(A.HAND_RIGHT)}.'))

    def knife():
        return (f'On this computer, your right hand is {k(A.HAND_RIGHT)}: it holds the knife.'
                + pad(lambda: f'{b(A.HAND_RIGHT)}.'))

    def jumping():
        return (f'On this computer, jump by pressing both feet, {k(A.FOOT_LEFT)} and '
                f'{k(A.FOOT_RIGHT)}, at the same time.'
                + pad(lambda: f'{b(A.FOOT_LEFT)} and {b(A.FOOT_RIGHT)} together.'))

    def camera():
        return (f'On this computer, your right hand is {k(A.HAND_RIGHT)}: it takes the picture.'
                + pad(lambda: f'{b(A.HAND_RIGHT)}.'))

    def unplugging():
        return (f'On this computer, press {k(A.UNPLUG)} to unplug the headphones; keep them '
                'on to hear the rest. There is no silent switch to push.'
                + pad(lambda: f'{b(A.UNPLUG)}.'))

    def hands():
        return (f'On this computer, your hands are {k(A.HAND_LEFT)} and {k(A.HAND_RIGHT)}.'
                + pad(lambda: f'{b(A.HAND_LEFT)} and {b(A.HAND_RIGHT)}.'))

    def skip_explanation():
        return (f'On this computer: when you hear that sound, press {k(A.SKIP)} to skip. '
                f'{k(A.PAUSE)} pauses. Your feet are {k(A.FOOT_LEFT)} and '
                f'{k(A.FOOT_RIGHT)}, and your hands are {k(A.HAND_LEFT)} and '
                f'{k(A.HAND_RIGHT)}. If your feet or hands make no sound, they are '
                f'switched off for now. Turn with {k(A.TURN_LEFT)} and {k(A.TURN_RIGHT)}.'
                + pad(lambda: f'skip is {b(A.SKIP)}, pause is {b(A.PAUSE)}, your feet are '
                      f'{b(A.FOOT_LEFT)} and {b(A.FOOT_RIGHT)}, your hands '
                      f'{b(A.HAND_LEFT)} and {b(A.HAND_RIGHT)}, and the left stick turns.'))

    return {
        'blind_ps2_skip_tuto': skip_explanation,
        'INTRO_SPEECH_training_0a_SPA_UOS': turning,
        'INTRO_SPEECH_training_0a_prompt_SPA_UOS': turning,
        'INTRO_SPEECH_training_1a_SPA_UOS': turning,
        'INTRO_SPEECH_training_1a_prompt_SPA_UOS': turning,
        'INTRO_SPEECH_training_turn_to_face_me_SPA_UOS': turning,
        'INTRO_SPEECH_prompt_no_walk_SPA_UOS': walking,
        'INTRO_SPEECH_training_6_SPA_UOS': clapping,
        'INTRO_SPEECH_prompt_no_clap_SPA_UOS': clapping,
        'INTRO_SPEECH_training_10a_UOS': one_hand,
        'INTRO_SPEECH_training_prompt_open_door_UOS': one_hand,
        # the museum (ps2_1 to ps2_4)
        '1_SPEECH_prompt_no_clap_UOS': clapping,      # "press the top corners ... to clap"
        '1_SPEECH_precollect_3_UOS': one_hand,        # "smash it open with your hand"
        '1_SPEECH_open_case': one_hand,               # same; in the bundle, played by no level
        '4_SPEECH_oncollect_4_UOS': clapping,         # "when you're ready, clap your hands"
        # Hometime, the pier, the burning house (ps2_5a to ps2_7)
        '5a_SPEECH_intro1_SPA_UOS': holding,          # "hold it up, as if taking a picture"
        '5a_SPEECH_prompt_hold_it_up_SPA_UOS': holding,
        '5a_SPEECH_portrait_alert_SPA_UOS': holding,  # "hold it the other way"
        '5a_SPEECH_intro2_SPA_UOS': shaking,          # "shake it as hard as you can"
        '5a_SPEECH_prompt_drop_needle_UOS': one_hand,  # "with your left or right hand"
        '6_SPEECH_instructions_shoot_ducks_UOS': rifle,   # "air rifle in your left hand"
        '7_SPEECH_warning_floor_fall_UOS': hands,     # "use your hands to climb back out"
        '7_SPEECH_warning_floor_fall_short_UOS': hands,   # "use your hands!"
        '7_SPEECH_prompt_pull_yourself_out': hands,   # in the bundle, played by no level
        # the ice, the submarine, the abyss (ps2_8 to ps2_10)
        '8_SPEECH_warning_penguin_appear_UOS': clapping,  # "clap your hands to scare it off"
        '8_SPEECH_prompt_penguin_close_UOS': clapping,    # "clap, quick!"
        '8_SPEECH_oncollect_1_UOS': clapping,             # "you can clap if you need to"
        '9_submarine_SPEECH_instruction_trapped_man_UOS': left_hand,  # "with your left hand"
        '10_SPEECH_intro_UOS': throwing,                  # "throw the glass ... right hand"
        # the fountain, the zoo, the sea, the train (ps2_11a to ps2_12)
        '11_SPEECH_oncollect_turnOver_SPA_UOS': one_hand,  # "Use a hand."
        '11b_SPEECH_intro_UOS_PRE': pistol,               # "water pistol in your left hand"
        '12_SPEECH_duck_warning_1_UOS': rifle,            # "the air rifle in your left hand"
        '12_SPEECH_prompt_smash_record_UOS': shaking,     # "Shake it. Smash it."
        '12_SPEECH_white_room_destroy_UOS': shaking,      # "Smash the record. Shake it."
        '13_submarine_SPEECH_intro_UOS': one_hand,        # "destroy it with your hands"
        '13_submarine_SPEECH_precollect_long_UOS': one_hand,   # "USE HAND!"
        '13_submarine_SPEECH_prompt_lift_needle_UOS': one_hand,  # "Use your hands!"
        '13_submarine_SPEECH_prompt_smash_record_UOS': shaking,  # "Shake it!"
        '13_submarine_SPEECH_white_room_destroy_UOS': shaking,   # "... Shake it"
        # the burning house, the ice, the abyss floor (ps2_14 to ps2_16)
        '14_SPEECH_intro_UOS': extinguisher_and_sand,     # "left hand ... extinguisher; right hand ... sand"
        '14_SPEECH__extinguisher_1_UOS': extinguisher,    # "the extinguisher's in your left hand"
        '14_SPEECH__extinguisher_2_UOS': extinguisher,    # "Use the extinguisher!"
        '14_SPEECH__smash_memory_1_UOS': extinguisher,    # "Smash it! With the extinguisher!"
        '14_SPEECH_banging_instructions_UOS': extinguisher,  # "smashing through the door with the extinguisher"
        '14_SPEECH__shake_extinguisher_UOS': shaking,     # "Shake it to build up the pressure!"
        '14_SPEECH__shake_extinguisher_2_UOS': shaking,   # "Shake the extinguisher!"
        '14_SPEECH__prompt_smash_record_UOS': shaking,    # "Shake it! Destroy it!"
        '14_SPEECH__white_room_destroy_UOS': shaking,     # "Destroy the record. Shake it."
        '15_SPEECH_intro_once_moving_UOS': knife,         # "kill them with the knife, right hand"
        '15_SPEECH_hint': knife,                          # "the pen knife in your right hand"
        '15_SPEECH_warning_penguin_appear_1_UOS': clapping,  # "clap to scare them off"
        '15_SPEECH_prompt_under_ice_UOS': jumping,        # "You need to break through it. Jump."
        '15_SPEECH_prompt_jump_UOS': jumping,             # "Use both feet at the same time!"
        '15_SPEECH_prompt_smash_record_UOS': shaking,     # "Shake it. Set me free."
        '15_SPEECH_white_room_destroy_UOS': shaking,      # "Destroy the record. Shake it!"
        '16_SPEECH_prompt_lift_needle_UOS': one_hand,     # "Use either hand."
        '16_SPEECH_prompt_smash_record_UOS': one_hand,    # "Press the button. Use either hand."
        '16_SPEECH_white_room_destroy_UOS': one_hand,     # "Delete it. Press the button."
        # the idle hints, heard since decision 21
        '6_SPEECH_hint': rifle,                           # "Use your left hand to shoot the ducks."
        '7_SPEECH_hint': hands,                           # "use your hands to get out"
        '10_SPEECH_hint': throwing,                       # "Throw the glass ..."
        '11b_SPEECH_hint_shooting': pistol,               # "a water pistol in your left hand"
        # Papa, and the way home (ps2_18, 18b)
        '18_SPEECH_intro_announcer_UOS': pistol,          # "Use the water pistol."
        '18_SPEECH_prompt_camera_UOS': camera,            # "It's in your right hand."
        '18_SPEECH_announcer_pistol_correction_UOS': camera,  # "use the camera"
        '18b_SPEECH_intro_UOS': unplugging,               # "switch off silent mode. Unplug your headphones"
        '18b_SPEECH_prompt_unplug': unplugging,           # "Unplug your headphones. Take them off."
        '18b_SPEECH_instruction_shake': shaking,          # "Shake it! ... Keep shaking!"
        '18b_SPEECH_prompt_shake': shaking,               # "Shake it!"
    }


def pc_about(keymap) -> str:
    """After the About screen's notice, which describes the touch controls."""
    A = Action
    return (f'On this computer: walk by pressing your feet, {keys(keymap, A.FOOT_LEFT)} '
            f'and {keys(keymap, A.FOOT_RIGHT)}, one after the other. Use your hands with '
            f'{keys(keymap, A.HAND_LEFT)} and {keys(keymap, A.HAND_RIGHT)}; both together '
            f'clap, and both feet together jump. Turn with {keys(keymap, A.TURN_LEFT)} and '
            f'{keys(keymap, A.TURN_RIGHT)}. There are no Gyro, Swipe or Tilt modes: the keys '
            'do the turning. Every key can be changed in Settings.')
