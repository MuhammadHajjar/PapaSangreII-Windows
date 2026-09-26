# Proposed build order - for agreement before any gameplay code

Nothing below is started. Each milestone ends in something Muhammad can run and
judge, and each is a go / no-go gate: the next one does not begin while a
mechanic of the previous one is unresolved.

Every milestone follows the same discipline, from the brief and the PS1 journal:

1. Read **in full** every method the milestone needs (not the call listing), and
   decode any jump table before reasoning about a state machine.
2. For each field the behaviour depends on, find **every writer** (the
   offset-register trap included), not just `init`.
3. Keep return values (sound durations feed timers).
4. Count call sites of every sound name the milestone touches.
5. Tests: fake sounds that end, fake pads with axes, menus driven not just built,
   audio verified by rendering and measuring.
6. Run the real built exe in a clean folder before handing it over.
7. Every departure goes in DIVERGENCES.md under its honest heading.

## M1 - the engine base (no new gameplay)

Start from the PS1 port and keep what the diff says is unchanged:

* **Kept as is:** audio engine, OpenAL binding, the HRTF pipeline (PS2 embeds the
  **byte-identical** IRCAM 1050 set), playlist parser, speech (NVDA + SAPI),
  input plumbing, key and pad rebinding, menus shell, options, config beside the
  exe with the `%LOCALAPPDATA%` fallback, the single atomic save, build and
  release tooling.
* **Re-recovered for PS2 and replaced:** the level loader (every layer, explicit
  trigger lists per type, `_N` suffixes, the delayed `active`, per-type
  defaults, circles), the trigger runtime (delays owned by their object,
  `minDelay`/`maxDelay`), the 20 Hz tick with the 10 Hz player, per-level reverb
  and `ChangeReverbSettings`, `distanceScale` 0.016 and `maxSpatialGain` 2,
  footstep / trip / throw naming, agent defaults (collide radius 10).
* **New input actions**, rebindable, with pad equivalents: hands, clap, shake,
  device orientation, jump, skip, unplug headphones (keys: see decision 1).
* Tools: `Check game content.exe` over the 23 levels and 19 test maps, `Verify
  spatial audio.exe`.

**Gate:** all 42 maps load with zero unexplained keys, messages or sounds (every
exception is a data defect with an entry); the audio verification passes.

**Status 2026-09-23: built.** Loader, trigger runtime, 20 Hz clock, controls
with chords, per-level reverb, hub list, HRTF pipeline, content check (1026
findings, 0 unexplained - `docs/CONTENT_CHECK.md`), `Check game content.exe`,
`Verify spatial audio.exe`, `Listen to spatial audio.exe`; 93 tests. Carried
into M2: the reverb wet-send interpolation per agent sound, and footstep naming
(a full read of `moveForwardOneStep:`).

## M2 - ps2_Intro, "You are dead" (first playable level)

The tutorial teaches walking, turning, hands, collecting and clapping; it also
has rails and the VoiceOver-only `blind_` narration. Needs, read in full:
`PGEPlayer` movement (`moveForwardOneStep:`, `trip:`, rotation, wall collision),
`PGEMoveInterpretor` (`updateFeetView:`, `updateHandsView:`), `PGESound`
(`createSpatializedSound`, rails, skipping), `PGECollectible` (hand collection),
the walled / basic surface, the **win flow and the after-level menu**, and the main
menu with Continue / Choose level / Options / Credits / Quit.

**Gate:** you play the Intro end to end and it feels like the game.

**Status 2026-09-24: built.** The Intro plays end to end in `Play Papa Sangre
II.exe` (menus, splash, pause, after-level menu, the three REQUESTED toggles,
the tutorial's PC lines after each touch-control line). Carried items closed:
footstep naming (full `moveForwardOneStep:`), and the reverb - the original's
Freeverb recovered exactly, OpenAL's reverb fitted to it by measurement, and
the per-sound `autoReverbMix` send reproduced (see DIVERGENCES, Reverb).
Measured finding for later levels: the old PS1-style mapping would have been
13 to 29 dB wetter than the original in every room with dampening under 100
(ps2_1 to 5, 10, 12 to 17). Menu sounds audited button by button against
the original's handlers; their 0.1 s spacing moved to the wall clock (on the
game clock it swallowed every menu click after the first). 167 tests.

**Decision 10 (2026-09-24): the reverb is the measured original.** Muhammad
compared both builds on level 1 and chose it over the old, wetter mapping.

**Decision 11 (2026-09-24): the skip explanation is always the spoken take.**
With Blind intro off and Skip explanation on, `blind_ps2_skip_tuto` plays in
place of the silent sighted take; the rest of the Intro stays sighted.

**Decision 12 (2026-09-24): the phone starts flat.** Nothing counts as held
up until Up (upright) or Down (on its side) is pressed; ps2_5a's PC line names
both, so the player still chooses, and Up draws the original's scolding.

**Decision 13 (2026-09-24): ps2_5a's shake memory reaches 1000 px.** In the
data it has the default 10 (every other shake target in the game has 100 to
1000), so a player who reached Papa from his north-east side stopped about
11 px out with walking locked and could never shake it - the original has the
same trap.  Muhammad hit it ("Ctrl does nothing").

**Decision 14 (2026-09-25): a memory shaken loose takes seven Ctrl presses,
each a whoosh.**  The original collects a shake memory (ps2_5a's phone, the
records at the end of 12 to 15) on the first shake its accelerometer reports;
seven is the count the game itself asks for in its one multi-shake scene
(ps2_18b).  Each shake the memory takes plays the game's own `whoosh` (menu
buttons playlist; the original never plays it), and only then - Ctrl stays
silent with nothing to shake.  Shakes that sound by themselves (ps2_14's
extinguisher) are untouched.

**Decision 23 (2026-09-26): the first private beta's reports** (sethgamer's
list, all taken but the shake whoosh, which Muhammad kept).  Record scratch
timing, "keep going" never over the landmarks, the display case always
explained, sparkler and gramophone reached at once, the scrape heard, the
submarine's explosion flat, ps2_14's fire doors where they are (a port bug:
`deactivate` had kept the shared fire sound), the oil can's reach, the house
chasing from its first sound, the jump prompt's gap, the camera scene holds
your feet, the hold music quieter and 16 shakes (Muhammad's number), trip and
wall lines in the Intro and ps2_1 only, idle hints once, the first steps after
a stop walk, the level list's click, About a row at a time.  Details in
DIVERGENCES.md and docs/notes/BETA1_NOTES.md.

**Decision 22 (2026-09-26): the shot hits what is in front of you** (testers:
monsters that never died in the memories level, one that died behind you).
The nearest active, living monster or penguin in the cone when you fire.

**Decision 21 (2026-09-26): every recorded line can be heard** (a tester's
list, then `tools/unused_speech.py` over all 22 levels): the idle hints, the
wall and trip lines per level, the waving lines, the misspelt and unwired
lines and the other takes (`papasangre2/world/requested.py`).  The knife's
swing is yours (flat), as the camera's click is.

**Decision 20 (2026-09-25): the game is a folder, its data encrypted in the
exe.**  A friend's advice, measured first: the one-file exe unpacked about
220 MB to a temporary folder at every start (5 s before the game ran); the
folder build starts in 1.9 s and keeps nothing in temp.  Muhammad asked for the
sounds to stay inside the exe, encrypted: all game data is one ChaCha20 pack
embedded as a Windows resource (`papasangre2/assets/pack.py`,
`tools/build_exes.py`).  The release is the folder zipped: the exe and
`_internal`.

**Decision 19 (2026-09-25): trips on glass are heard.**  The original has no
glass trip sound.  The first takes, from the game's glass steps alone, lacked
a body falling; Muhammad chose one of six with a bodyfall from his library
(`tools/make_glass_trip.py`, candidate 1).  The Intro's squelchy gravel and
ps2_3's cracker floor get the trips the game files under other names.

**Decision 18 (2026-09-25): Muhammad's penguin death for the knife.**  A
stabbed penguin plays his `Penguin death.wav` (the original's with a stab);
shot penguins keep the original's.  Sounds he makes live in `requested/sounds/`
and ship inside the game (`papasangre2/assets/requested.py`).

**Decision 17 (2026-09-25): a sound effect an object plays comes from that
object.**  Muhammad heard the extinguisher hits on ps2_14's banging door in
both ears, flat; the original plays them flat (`PlaySound` is always flat).
He chose to place every non-speech `PlaySound` sent by something with a place
in the room where it stood when it fired (the knife on the bears and penguins
too) - but not what you hold: ps2_18's camera click stays on your side.

**Decision 16 (2026-09-25): an enemy sent where it already stands stays
there.**  The original loses it at NaN (no zero guard in `findDirectionTo:`),
which made ps2_15 impossible to finish - a stranded polar bear.  Muhammad
chose the fix, for every enemy (ps2_16's hogs too).

**Decision 15 (2026-09-25): PC instructions is a switch in Settings**, on by
default: the screen reader's PC version of each tutorial line (decision 8).

## M3 - the museum: ps2_1 to ps2_4

Mindlice are `Monster`s: the **whole PS2 enemy state machine** (10 states,
decoded jump table), `alertEnemy:`, proximity sound, clap alerts, noisy floors.
Plus the **death path**: the after-level menu after a death, the
`<level>_fail_<cause>` narration, lost memories, the menu death atmosphere, and
**achievements** for these levels (decision 4).

**Status 2026-09-24: built.** `PGEEnemy` recovered from PS2's own binary (the
ten-state jump table plus the waiting state 10, alerts, the intro sound, going
home, attacking, the proximity sound) - `papasangre2/entities/enemy.py`; the
agents' pause sound; the shutdown's lock-out; the death (the lose screen's
count, the per-level narrations in turn, the lost memories 1 to 25, the death
atmosphere 0.7 s after); the achievement tracker and the four museum
achievements, act1, memoryLost and the step totals, spoken on the win screen
and in an Achievements menu; the tutorial's PC lines for the museum. All four
levels play to the door in the simulator; the content check still explains
all 1026 oddities. Recovery notes: `docs/notes/M3_NOTES.md`. 203 tests.
Found on the way: M2 wrote `<level>_failed` as a flag at load - it is the lose
screen's death count.
Fixed after release to Muhammad (his report, menu level 3): a memory's loop
stopped when a louder line started. `-[PGECollectible soundPriority]` returns 0
until the collectible is collected; M2 had missed the override. Every other
override of the agent's methods was then checked against the class dump; three
more were missing and are in: the collect sound takes the memory's gain when it
names no collect gain (level 1's memories collected at full volume instead of
0.7), deactivating a collectible clears `collected`, and a shake collectible
left in reach collects itself after 20 s (plus `CollectAgentWithName`). 209 tests.

## M4 - ps2_5, 5a, 6, 7

Lethal pools and `kill`; 5a "Hometime" - device orientation, collect by shaking,
the vibrating phone, rails; 6 - the air rifle (`shoot`, shooting cone, ducks on
paths); 7 - the burning house (lethal surfaces switched by
`SetLethalForSurfaceWithName`, positioned surface sounds, cats on paths, and
two `isUnderwater` surfaces that are probably the smoke [I]).

Status (2026-09-24): built.  Recovery in docs/notes/M4_NOTES.md.  Lethal
floors with their positioned sounds, death sounds and causes; the deadly/safe
cycle, still limit and follower timer are in too (M5 uses them); drowning in
the smoke; the air rifle and the ducks' deaths; holding the phone (the agents
listen for it themselves, 0.8 s after it is held right); the level 5-7
achievements, superBullet and the kill counts; PC lines for the new tutorial
lines.  All four levels finish under the autopilot on every seed tried.  The
smoke surfaces are the underwater ones (confirmed: `drown` restarts with
"drown").

Fixed at the same time, from Muhammad's M3 play:
* flat sounds (the voice once the hat is on, the skip ping) went through the
  HRTF when their file was mono - OpenAL Soft never plays a mono buffer
  direct.  They now play as the original's `setupPlain` does: a stereo file
  as it is, a mono one at half level in each ear, never 3D;
* `cancelWetGain` was applied to the sound instead of the collectible, so the
  exit cutscenes had the room's reverb.  Only the doors without it (the
  submarine's among them) keep it;
* the win screen keeps the achievement as a row, achieved or not.
241 tests.

## M5 - ps2_8, 9, 10

Penguins (`PGEFollower`) and cracking ice; the submarine's deadly / safe steam
cycles; throwing glass over the abyss (`OnPebble`).

Status (2026-09-24): built.  Recovery in docs/notes/M5_NOTES.md.  The penguin
(`PGEFollower`, its three states, the clap that sends it away, the ice that
counts how long it stands close), throwing (`throwSomething`, `OnPebble`,
the landing sound), the level 8-10 achievements, PC lines for the new
tutorial lines (and for a line played by `PlaySound`).  The steam vents run on
the M4 surface cycle.  All three levels finish under the autopilot on every
seed tried.  259 tests.

## M6 - ps2_11a, 11b, 13, 12

Water pistol and the forgetful men; underwater, gagging and drowning with
`ResetUnderwaterTimer`; the train level with the player on a path.

Status (2026-09-24): built.  Recovery in docs/notes/M6_NOTES.md.  The player on
a path (the train), `DeallocAgentWithName`, the zoo's `randomAnimal` rule, the
player's stop on shutdown, the level 11b-13 achievements, PC lines for the new
tutorial lines.  The water pistol is the M4 rifle with its own sound; the
underwater level runs on the M4 clock.  All four levels finish under the
autopilot on every seed tried.  275 tests.

## M7 - ps2_14, 15, 16, 17

Extinguisher (beat) and sand (throw), shake triggers; the dagger, jumping and
the penguins; thunder cover; the husks.

Status (2026-09-25): built.  Recovery in docs/notes/M7_NOTES.md.  The beat
(knife, extinguisher) and its miss, the beating range, enemies and penguins
beaten, penguins shot, `OnShake` on any agent, jumping (`OnJump`,
`OnJumpTooMuch`), Papa's picture count (for M8), the level 14-17 achievements,
PC lines for the new tutorial lines.  All four levels finish under the
autopilot on every seed tried (8), ps2_15 thanks to decision 16.  305 tests.

Before M7, at Muhammad's request: the **PC instructions** switch in Settings
(decision 15) and **seven shakes, each a whoosh**, for a memory shaken loose
(decision 14).

## M8 - ps2_18, 18b, the end

The camera (`beat` on Papa, `picturesTaken`), `stillLimit` ("don't stop
running"), unplugging the headphones, the end of the game, credits.

Status (2026-09-25): built.  Recovery in docs/notes/M8_NOTES.md.  Unplugging
(`audioRouteChanged:`, `OnRouteChange`), the end of the game
(`PresentAdiosVC`: the Adios screen, Main Menu, the end music), the level 18
achievement, PC lines for Papa and the way home (the camera, unplugging,
shaking), decision 14's whoosh for the last record.  The camera, Papa's
pictures and "keep moving" were in from M4/M7.  The credits are the About
screen (M2).  Both levels finish under the autopilot on every seed tried.

## M9 - release

Windowed folder build (decision 20: the exe, `_internal`, the data encrypted in
the exe), the release zip holding that folder only, release notes.

Versions are dates (Muhammad, 2026-09-26): `2026-09-26`, and `2026-09-26 number
1`, `number 2` when a day has more than one.  The version lives in
`papasangre2/__init__.py`, `VERSION` and the newest heading of `changelog.txt`
(a test holds the three together); About reads it first.  The release tag is
the version without spaces (`2026-09-26-5`) and its zip is always
`PapaSangreII-Windows.zip` (from number 5; numbers 3 and 4 carried the tag in
the name), so `releases/latest/download/PapaSangreII-Windows.zip` is one link
that never changes - and the only zip on a release, which is also what builds
3 and 4 take when no name of theirs matches.  It is what the self-updater looks for
(`papasangre2/update/updater.py`; `tools/verify_updater.py` proves it
offline, through the real PowerShell hand-off).  `changelog.txt` ships
in every release beside the exe - players' words, one line per change, what
changed and never how (VGStorm's style).  `tools/pack_release.py` makes
`dist/Papa Sangre II <version>.zip`: one folder, "Papa Sangre II", holding the
exe, `_internal` and the changelog.

---

## Decisions needed from Muhammad

Recommended option first. Nothing in M1 that depends on these will be guessed.

1. **Keys the brief does not name - DECIDED 2026-09-23.**
   * **clap = Q and E together, jump = A and D together** (Muhammad: "in the
     actual game, you clap by pressing the 2 hands"). The binary agrees:
     `handClapDetected:` (0x10000fdac) takes a two-finger tap and posts
     `PGE_INPUT_HandsClapped` when both fingers are in the upper part of the
     screen (y under half the gesture view and within the top 0.3 of the view),
     one each side of the middle - the two hand buttons - and `PGE_INPUT_Jump`
     when both are in the lower half, one each side - the two feet.
   * skip narration = Enter; unplug headphones = U.
   * Up = hold the phone upright (portrait), Down = back on its side
     (landscape); orientation is a state, as in the original.
   * Consequence for M1: a press of one hand or one foot has to wait briefly to
     see whether its partner follows. The original does the same thing - its
     two-finger recogniser is created with `setDelaysTouchesBegan:YES` and
     `setCancelsTouchesInView:YES` (`initGestureRecognition`, 0x10000f7f8), so
     a single touch is held back until the recogniser gives up, and a
     recognised chord swallows both touches. UIKit's own wait cannot be read
     from the binary, so the port's window (start at about 50 ms, tuned by
     playing M2) is PORT-SIDE. Clap and jump follow whatever keys the hands and
     feet are bound to. A chord of the feet when jumping is disabled does
     nothing, as in the original (the interpreter drops it and the touches are
     cancelled).
   * **Controller - DECIDED 2026-09-23: left trigger = left foot, right
     trigger = right foot, both triggers together = jump** (replacing the PS1
     port's d-pad feet, which cannot be pressed together). The triggers are
     axes; the PS1 port's `padmap.py` already reads them as `lefttrigger` /
     `righttrigger`, so a "press" is the axis crossing a threshold and the chord
     window applies to it like any key.
   * **Controller hands - DECIDED 2026-09-23: left shoulder = left hand, right
     shoulder = right hand, both shoulders together = clap.** The PS1 port had
     volume on the shoulders, so volume moves.
   * **Rest of the pad - DECIDED 2026-09-23:** in play, d-pad up / down = phone
     upright / on its side, d-pad left / right = volume down / up (in menus the
     d-pad still navigates and adjusts); Y = shake; X = unplug the headphones;
     A select and skip, B back, Start pause. **Turning moves to the left
     stick** ("like most other games"; the PS1 port turned with the right),
     read as a rate with a dead zone as before; the right stick is unused.
2. **VoiceOver - DECIDED 2026-09-23: the port always behaves as if VoiceOver
   is on.** Every `UIAccessibilityIsVoiceOverRunning` branch takes its "on"
   side: `blind_` narration where it exists (three Intro sounds,
   `-[PGESound createSpatializedSound]` 0x100033818), the accessible level
   list, and the other VoiceOver paths (skip button, popups, settings, splash -
   each read when its milestone comes). Recorded as REQUESTED, since on an
   iPhone it depended on the player's settings.
3. **ps2_11 - DECIDED 2026-09-23: left out**, recorded in DIVERGENCES as N/A
   (cut content: in no menu, loaded by no level, empty playlist). The loader
   and content check still parse it, so a change in that verdict would show.
4. **Achievements - DECIDED 2026-09-23: ported**, spoken, kept in the one save
   file; Game Center, Twitter and Facebook N/A. The achievement tests
   (`-[PGEGameProgress checkAchievementsForlevel:]`, 1096 instructions) are read
   in full before they are built; the texts are the hub list's.
   **Skip tickets - DECIDED 2026-09-23: removed entirely, at Muhammad's
   request** ("I never saw them in the actual game and no fun to have such a
   feature"). The binary does have them (`PGELevelSkipperViewController`, the
   Lose screen's Skip button); the port builds none of it - no Skip option, no
   tickets, no `skippedLevels` in the save. REQUESTED in DIVERGENCES.
   **After-level screen - DECIDED 2026-09-23: like the PS1 port's**, not the
   original's Win / Lose view controllers: a spoken menu after each level with
   continue (after a win), replay, choose level and main menu. REQUESTED. What
   the original *plays* on those screens is kept, because it is content: the
   level's `<level>_end_music_loop` under a win, and the death narration
   (`<level>_fail[_<cause>]`, `lost_memory_<n>_UOS`) then `menu_death_atmos`
   under a death. The success text and any achievement earned are spoken.
5. **Vibration - DECIDED 2026-09-23: rumble the controller if one is connected,
   nothing on the keyboard.** `-[PGEPlayer vibrate:]` calls
   `AudioServicesPlaySystemSound(kSystemSoundID_Vibrate)` (0xfff) - no sound.
   The length and strength of one buzz are the phone's, not the game's, so the
   rumble's are PORT-SIDE; the timing of each buzz is the data's
   (`Vibrate:afterDelay=...` in ps2_5a and ps2_11a).
   **A second vibration site, found while checking:** `-[PGEPlayer
   playerDidCollideAWall:]` also calls it (0x10002afc8), so walking into a wall
   buzzes the phone - in most branches; one branch around the
   `global_warning_hitwall` narration skips it (0x10002af2c). Same rule
   applies: the controller rumbles on those wall hits. The exact branch
   conditions are read in M2 with the rest of wall collision.
6. **Camera roll - DECIDED 2026-09-23: left out**, N/A with evidence
   (`-[PGEngine savePhoto:]` 0x10004a4bc only calls
   `UIImageWriteToSavedPhotosAlbum` with a bundled PNG; no sound). Taking the
   photos - the camera in the right hand, `picturesTaken`, the `4_papa_` and
   `18_SPEECH_papa_picture_retreat_` sounds - is gameplay and is ported.
7. **The build order above.** Agree, or reorder.

8. **Tutorial lines must teach the PC controls - ASKED 2026-09-23** ("make
   sure every tutorial message, you get the pc equivalent with no mistake").
   The training narration is recorded speech about a touchscreen ("tap",
   "swipe", "shake the phone"), so each line that names a control needs its
   PC equivalent said - by the screen reader, right after the original line,
   naming the current binding (so a rebound key is still right). To do that
   without a mistake every training line has to be transcribed first, which
   means an offline speech recogniser over the Intro's narration and a check
   by ear; that is M2 work, listed there. REQUESTED. **DECIDED 2026-09-23:**
   play the original line, then speak the PC version after it.
9. **Settings toggles - ASKED 2026-09-23** (M2, with the Intro):
   * **Blind intro** - whether the Intro plays the `blind_` training lines the
     original plays with VoiceOver on (decision 2 made that the fixed
     behaviour; it becomes a toggle, on by default).
   * **Skip ping** - the `skipButtonAppeared` sound the original plays when a
     narration becomes skippable (`-[PGEStepsViewController showSkipButton]`);
     on by default, off silences it.
   * **Skip explanation** - the Intro's record-player line that explains the
     skip sound ("when you hear this sound, you can skip what is being
     played"); on by default, off leaves it out. Which sound agent that is
     will be identified when the Intro is transcribed.
   All three are REQUESTED and live in `config/settings.json` with the turning
   speed and volume.
