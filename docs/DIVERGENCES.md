# Divergences from the original

Every way the port knowingly differs from Papa Sangre II 1.1 on iOS, under
the heading that says why. **INVENTED must stay empty**: nothing here is a
guess presented as a recovery. When the binary and Muhammad's memory of the
game disagree, work stops and he is asked.

## INVENTED

(nothing)

## MISSING - could not be recovered

* **The two-finger tap's wait.** UIKit decides how long a single touch is held
  back before a two-finger tap is ruled out (`setDelaysTouchesBegan:YES`); that
  interval is inside UIKit, not the game, and is not in the binary. The port's
  chord window is PORT-SIDE below.

* **The titles of the Game Center achievements.** act1, act2, act3,
  memoryLost, 10000steps, 1000000steps, kill25, kil100, kill500 and
  superBullet exist in the binary only as identifiers; their titles and
  descriptions lived on Apple's servers. The level achievements are not
  affected (their texts are in the hub list). The port's Achievements menu
  says the others by identifier - see PORT-SIDE.

## N/A - has no meaning on a PC

* Game Center, the social sharing, Fiksu, the "more games" and advertisement
  screens, the app's own rating prompt (decision 5).
* Saving the ending's picture to the camera roll (decision 6).
* The phone's vibration: on a keyboard nothing; on a controller, rumble
  (decision 6). Applies to the shake feedback and the wall hit alike.
* `PGE_INPUT_RotateDevice` is a key (Up = upright, Down = on its side) since
  there is no accelerometer; `requiresPortraitPicture` /
  `requiresLandscapePicture` levels read that key.  The original's
  accelerometer repeats the orientation on every sample once anything has
  asked (`CheckDeviceRotation`); the port says it once when asked and once
  per key press, which reaches the same agents.
* Unplugging the headphones is a key (U); `requiresUnplug` levels read it.
  The sound stays in your headphones: the original also turns the iPod music
  player up to full so the ending comes out of the phone's speaker, and asks
  you to push the silent switch - neither exists here.  The "plug your
  headphones" picture the original shows after unplugging is not shown.
* The "Wear headphones" alert on Select Level appears in the original only when
  iOS reports no headset (`isHeadsetPluggedIn`); a PC cannot tell, so it never
  appears. The About screen's headphones notice is still read.
* The control schemes (Gyro, Swipe, Tilt) in Settings: turning is keys or the
  left stick here, so there is no scheme to choose.
* "More games" on the main menu and the Facebook / Twitter / Game Center
  buttons on the win, lose and achievement screens.

* The lose screen's "Talk to Papa" (a Twitter post) and its skip button (skip
  tickets, removed - REQUESTED); the analytics (Flurry) the tracker feeds.
* The old-device path (`+isOldDevice`: no reverb, and agents marked `notOn4`
  left out): the port behaves as the newer phones did.

## PORT-SIDE - the port's own mechanism for an original behaviour

* **Chord window, 50 ms** (`papasangre2/input/chords.py`): the first key of a
  hand or foot pair waits that long for its partner; together they are one
  clap or one jump, alone the press goes through when the window closes. Tuned
  by playing; the original's value is MISSING above.
* **Tick:** the original's NSTimer fires every 0.05 s on the main run loop; the
  port steps a fixed 0.05 s accumulator from the pygame loop. Same order of
  updates, same dt.
* **Content check sound index:** `Check game content.exe` carries the sound
  file names instead of the 85 MB tree. Tooling only; the game carries the
  tree.
* **Reverb unit:** the original's reverb is CSL's Freeverb, recovered exactly
  (`papasangre2/audio/freeverb.py`: six combs, three allpasses, feedback
  `size*0.28+0.3`, the volume as the wet level). OpenAL's EFX reverb is fitted
  to it, not copied: decay at 1 kHz and 5 kHz from the Freeverb's comb loops,
  loudness from its energy times one measured constant (`EFX_ENERGY_MATCH`,
  `tools/measure_reverb.py fit`). Measured against the recovered reverb on the
  same input, in every room the game uses: decay within 15 % at 1 kHz and
  5 kHz, level within 0.2 dB on average. What EFX cannot do:
  - **Direction.** OpenAL sends a sound to the reverb *before* the HRTF, the
    original after it, so in the original a sound's echo gets louder and
    quieter with its direct sound as you turn; in the port it stays put. The
    echo is about 3 dB quieter than the original for sounds ahead of you and
    about 3 dB louder for sounds beside or behind you.
  - **Stereo image.** The original reverberates each ear separately, so a
    sound on your right leaves its echo mostly on the right; EFX's echo is
    diffuse.
  - **Texture.** Six combs ring more than EFX's dense tail; not reproducible
    with EFX.
* **Per-sound send (faithful, noted here for the mechanism):** `autoReverbMix`
  is reproduced exactly (0.05 wet at 1 px or closer, 0.3 at 100 px or
  further, dry = 1 - wet, re-mixed on every move). The original splits dry
  from wet after the panner, so the send is attenuated with distance like the
  direct sound; OpenAL's own send roll-off is set to match and its
  "initial decay" fade is switched off. Measured: the echo-to-direct ratio is
  within 0.5 dB of the original's shape from 1 px to 400 px.

* **Load timing of agents' `active`.** The loader re-applies each agent's
  `active` from a block 0.05 s after it builds it. On a device the load takes
  longer than that, so the blocks run before any trigger the load fired (a
  level's opening line would otherwise be cut off 50 ms in, and it is not).
  The port runs them as main-queue blocks queued during the load, which lands
  them in the same place.
* **Rumble length.** The vibration is `AudioServicesPlaySystemSound(0xfff)`,
  which has no length in the binary; a controller rumbles for 0.4 s, the
  length of the standard iPhone buzz.
* **Menu atmosphere fades** step every 10 ms instead of the original's 0.05 s
  timer; the ramp and its length are the same.
* **Feet and hands wait 50 ms for their partner** (the chord window above)
  before a lone press goes through.
* **About** reads the original's two texts (the headphones notice and the
  credits) from `CreditsViewController.nib`, then says how the PC controls map
  (decision 8: the notice describes the touch controls).

* **Escape in menus.** The original has no Escape key; its screens have
  buttons. Escape in the port presses the screen's own way out, with that
  button's sound: on the pause screen it is Continue game (click, as
  `resumeGame:`), on every other screen Back / Main Menu (back_button), and on
  the main menu, which has nothing to go back to, it does nothing.
* **UI sound spacing** is wall-clock time, as the original's NSDate
  (`playUiSoundWithName:`, 0.1 s); it was on the game clock until 2026-09-24,
  which froze in menus and swallowed every click after the first.

* **The after-level screen's clock.** The death narration, the 0.7 s wait
  after it and the death atmosphere's fade run on real time in the original
  (an S3D end callback, `dispatch_after`, an NSTimer). The port keeps a menu
  clock that runs in levels and on the after-level screen alike, so they
  happen while you are choosing what to do next.
* **Game Center achievements by identifier** (see MISSING): the Achievements
  menu reads "act1, 40 percent" and so on, the last percentage the game
  reported; a level achievement reads its hub-list title and description.
* **The end screen is called "The end"**: the original's Adios screen has no
  words, only the end-game sky and a Main Menu button; the port speaks a
  title and adds Quit, as on the other screens.

* **A position that is not a number** stays where it was in the audio
  engine; OpenAL must not be given one.  The one known source, an enemy sent
  home while already there (`findDirectionTo:` has no zero guard), is fixed
  by decision 16; the guard stays as a safety net.

* **Key order for a collectible's gain.** `-[PGECollectible setGain:]` also
  sets the collect gain while that is still 1, so the result depends on the
  order the level's keys are applied - NSDictionary order in the original,
  which the file does not record. The port applies them in file order. Only
  ps2_13's easter_egg (gain 0.5, collectGain 1.0) comes out differently
  either way.

* **`agentsInShootingRange` is an NSMutableSet**, enumerated in hash order;
  the port keeps arrival order.  Only the order of the missed agents'
  `OnShootMissed` can differ.
* **A PlaySound line's PC version** (decision 8): the port watches for the end
  of a `PGE_MESSAGE_PlaySound` line to say its PC version (ps2_9's "open the
  hatch with your left hand"); the original keeps no monitor on it.
* **Playing a paused sound again** plays it at normal speed; whether S3D's
  `play:` resets a play rate of 0 was not read (no M4 level does it).

## FAITHFUL BUT ODD - reproduced on purpose

* **The room ticks twice.** The level is the first entry of its own floor
  list and also updates itself once more, so a Room's delayed triggers count
  down at double speed (`-[PGELevel init]` 0x100039ff0, `update` 0x10003f90c).
* **The inactivity nag never plays.** Rooms name `inactivitySounds`, but the
  interval starts at infinity and no level sends `ChangeInactivityTime`.
* **Walking speed reads high for the first steps.** `updateBPMCounter` divides
  the gaps by the number of steps, not of gaps, so the first steps of a level
  use the running footsteps; a steady walk settles on walking.
* **The same foot twice does nothing for two seconds**; the same-foot trip
  branch behind that gate cannot be reached (as PS1).
* **A skippable line only skips while the skip button is up**, and the skip
  input reaches every skippable line playing at that moment.
* The skip ping plays 1 s after the skip button appears even if the line has
  ended by then (the original's `dispatch_after` is never cancelled).
* `PGE_MESSAGE_PlaySound` reads its `loop` from `soundName` and applies a
  `dryGain` parameter as the wet gain; `PlaySpatialSoundOnAgentWithName` reads
  `loop` from `soundName` too. No shipped level passes those keys.

* Every data defect in `docs/CONTENT_CHECK.md` with a reason: malformed
  trigger statements dropped whole, keys the engine has no setter for,
  messages nobody observes, sounds no playlist declares (silent), agent
  messages that reach nobody, unknown paths, the test maps chaining to each
  other. The port does what the original does with each.
* `ps2_11` ships in the bundle but is in no menu and loaded by no level: cut in
  the original, so not offered here either (decision 3).
* `SendAgentToInitialPosition` and `SendAgentAwayFromPlayer` with no name reach
  **every** monster and follower; the other agent messages with no name reach
  nobody.

* **Menu sounds follow each button's own handler.** Choosing a level from the
  accessible list is silent (`tableView:didSelectRowAtIndexPath:`; the
  start_level_button sound belongs to the sighted hub picker, which the port
  does not have). The win screen's "Play this again" is silent
  (`-[PGEWinViewController playAgainButtonTouched:]` plays nothing) while the
  lose screen's clicks. Opening the pause screen is silent; its Continue,
  Restart Level and Settings click and Quit game plays back_button.

* **ps2_4's patrolling louse stops patrolling after its first chase.** When
  it gives up (`OnPlayerLastPosition`) the data asks it to follow path1 again,
  but `followPathWithName:` ignores a request for the path it is already on,
  so it stays where it gave up, still (state 0), until something alerts it.
* **One louse losing you sends every louse home.** `SendAgentToInitialPosition`
  in the data names nobody, and `sendToInitialPosition:` takes no name to mean
  everyone (ps2_2 has two).
* **An alert heard during a louse's appearing sound** plays its aware sound
  when the intro ends, but the same moment restores the state it had before
  (still), whose sound cuts the aware sound off; the chase still starts when
  the aware sound would have ended.
* **After a pause of the agents, a louse's sound starts again from the top,
  not looping** (`unpauseAgents` calls `-[S3DSound play]`, which is `play:NO`).
  When its pause sound is its still sound - one shared instance - unpausing
  stops it instead, and its next update starts it again.
* **`isStill` also counts state 104**, which nothing sets.
* **The 1000000steps achievement divides by 84,390**, not a million
  (`setTotalSteps:`), and **memoryLost is complete at 24** lost memories while
  the recordings run to 25 before starting again.
* **Levels 2 to 5 lose a memory on every death**: they have no death
  narrations, and levels up to 5 fall back on the lost memories.

* **Anything in the rifle's cone can be shot** (M4): every active agent with
  a collide radius, within 450 px and 23 degrees, is in the shooting range -
  ps2_6's ambience and its narration agents included.  When one of those is
  the nearest it takes the shot (a kill in the save's total, `OnShoot` if it
  has one) and the duck behind it is missed.
* **ps2_7's `detector` never fires**: its collide radius is 0, and
  `checkRanges` needs one above 0, so its glass smash is never heard.
* **Drowning is always cause "drown"**; the smoke surface's own `deathCause`
  "smoke" is never used (`restartLevel:@"drown"`).
* **A ceiling trap stays lethal** once its beam has fallen: walking back onto
  it later kills.
* **A second activation of a floor restarts its sound** without stopping the
  first (the playlist hands back the same sound), as `initialiseSound` does.
* **The penguin goes quiet after a pause** (M5): `-[PGEFollower
  playSound:looping:]` returns at once for the name it played last, whether
  that sound still plays or not, and `UnpauseAgents` plays it once through; so
  after ps2_8's speeches pause it, its footsteps stop until its state changes.
* **A clap only scares a penguin that is already close**; one further off is
  left following (`sendAwayFromPlayer:` acts in state 202 only).  While it
  walks away it posts `FollowerIsFar` every tick.
* **The penguin keeps no distance for the rifle**: its own collision check
  never sets `squaredDistanceFromPlayer`, so in a cone with it any shot takes
  it as the nearest (M6 levels).
* **Every shutdown stops you and zeroes your facing** (M6): `shutDownLevel:`
  stops the player's path and glide and sets the orientation to (0, 0), so a
  step goes nowhere until the next turn.  ps2_12's train, riding a
  two-point path, turns back down at the top and runs until the level shuts.
* **A second start of the player's path carries on its count**: in ps2_12,
  boarding twice would send the train to the wrong end first.
* **An animal already calling is not played twice** (ps2_11b): the agent that
  drew it skips its turn.
* **Swimming is never used**: nothing posts `PGE_INPUT_Swim` and no level
  enables it; ps2_13's "swimming" is its footsteps.
* **A pebble lands 5 to 10 px ahead**: the abyss is heard only from right at
  its edge (`throwSomething`).
* **A missed beat is missed by everything** (M7): every active agent out of
  reach gets `wasMissed` - its `OnShootMissed` - and `OnBeatMissed`, the fires
  and ambiences of ps2_14 included; only the player's own `OnBeatMissed` and
  the miss sound need nothing to have been touched.
* **`beatRange` does nothing**: ps2_14's oil can (80), the bears (40) and the
  rest set a property no code reads; a beat reaches `beatRadius`, 30 px, which
  no level sets.
* **The bears' "in knife range" sound is silent**: `polarbear_proximity_SPA`
  (and its polarbear2 kin) is in no playlist, so `setIsInBeatingRange:` plays
  nothing (content check).
* **A penguin counts twice as an enemy** (`FollowerDidDie` and
  `incrementPenguinKills` both add one), and **a dying penguin keeps following
  you** until its death sound ends (`-[PGEFollower update:]` has no dead check).
  One with no death sound for how it died vanishes without being marked dead.
* **Quick shakes make one extinguisher shake sound** (ps2_14): the sound is a
  level agent, and activating it again while it plays does nothing.
* **ps2_15's `PlaySound:soundName=jumpSound`** names a sound that does not
  exist; the jump is heard from the player's own `jumpSound`.
* **A jump counts only on the floor you stand on**, and each floor keeps its
  own last four jump times.
* **The last record takes eight shakes** (ps2_18b): `afterCount=7` lets the
  eighth through - or the 20 s timer after the instruction, whatever you do.
* **A wasted picture of Papa costs two beats**: the camera's own, and the
  `PlayerDidBeat` that `camera_out_of_range` posts - and pressing the right
  hand while Papa is away posts one too (`camera_sound_maker`).  The level's
  achievement is exactly three.
* **"Keep moving" is said once per stand**, after 8 s still on the floor
  (`stillLimit`); standing on does not kill.
* **The end of the game marks nothing**: ps2_18b ends in `PresentAdiosVC`, not
  a level load, so it is never recorded as completed.
* **A death with no narration of its cause** says nothing on levels above 5
  (ps2_7's fire walls without a `deathCause` die as "surface", which has no
  recording); a death with no cause at all can play any of the level's
  narrations, since the lookup is by prefix.

## REQUESTED - Muhammad's decisions

* Clap = Q and E together, jump = A and D together (decision 1), the
  touchscreen layout on keys; controller: triggers = feet, shoulders = hands,
  left stick turns, d-pad up/down = orientation, d-pad left/right = volume,
  Y shake, X unplug, A select/skip, B/Back back, Start pause (decision 4).
* Skip tickets removed entirely; the after-level screen is the PS1 port's
  (continue / replay / choose level / main menu) with PS2's end music and death
  narration (decision 5, 2026-09-23).
* Achievements kept, spoken, in the save (decision 5).
* Settings toggles (decision 9): **Blind intro** (the VoiceOver-on `blind_`
  training lines; default on), **Skip ping** (`skipButtonAppeared`; default
  on), **Skip explanation** (the record player's "when you hear this sound you
  can skip" line; default on).
* Every tutorial line that names a touch control plays as recorded, then the
  screen reader speaks the PC equivalent, naming the current binding
  (decision 8, 2026-09-23). The list, from a transcription of every Intro
  line, is in `papasangre2/tutorial.py`; a looping prompt gets its PC line
  once, after its first pass; a skipped line gets none.
* Main menu: **Continue** (to the furthest level unlocked, as the PS1 port
  has it) and **Quit** are added; the rest are the original's labels.
* Settings adds sound volume, turning speed, the three switches above, keys
  and controller buttons (all carried over from the PS1 port but the
  switches).
* The pause screen adds **Quit to Windows** below the original's four.
* **The skip explanation is always the spoken take** (decision 11,
  2026-09-24). With Blind intro off the original plays `ps2_skip_tuto`, 0.57 s
  of silence, so sighted players were never told about the skip sound. With
  Skip explanation on, the port plays `blind_ps2_skip_tuto` instead (then its
  PC line); every other Intro line stays sighted.

* **Achievements menu** (decision 4): the level achievements with their
  titles and achieved or unachieved descriptions, then the Game Center ones by
  name and percentage - the names are the port's, made from the identifiers
  ("Act 1", "25 kills"; the titles were on Apple's servers), and Enter on one
  says how it is earned, from the recovered rules (2026-09-26, Muhammad); the win screen speaks the level's achievement,
  as the original's win screen shows it.
* **The phone starts flat** (decision 12, 2026-09-24) - neither upright nor
  on its side - so ps2_5a's "hold it up" waits for Up or Down.  On a phone it
  was however the player held it (usually upright, which drew "hold it the
  other way" first).
* **ps2_5a's shake memory reaches 1000 px** (decision 13, 2026-09-24), as
  every other shake target does; the shipped 10 px could leave the player
  locked just out of reach (`Level.REQUESTED_DATA`).
* **Seven shakes to shake a memory loose, each a whoosh** (decision 14,
  2026-09-25): the original takes the first shake; the whoosh is the game's
  own, unused `whoosh` button sound, and plays only for a shake the memory
  takes (`SHAKES_TO_COLLECT`, `Level.play_whoosh`).
* **PC instructions can be switched off** in Settings (decision 15), and so
  can decision 14's shake whoosh (Settings, "Shake sound", on by default -
  2026-09-26, Muhammad: some players will like it, some will not).
  ps2_18b's record, shaken with no sound of its own, whooshes for each of the
  shakes it counts (decision 14, `SHAKE_WHOOSH`) - sixteen since decision 23.
* **The game updates itself from its GitHub releases** (2026-09-26, Muhammad:
  "like we did in Audio Defence").  At start (Settings, "Check for updates at
  start", on by default) and from the main menu's Check for updates, the
  newest release is compared with this build's date version; the question is
  Update now or Not now, nothing else (Not now asks again next start); Update
  now downloads
  only the files whose CRC-32 differs (the release zip's own index, read with
  byte ranges), stages them in `%LOCALAPPDATA%\Papa Sangre II\updates`, and
  a PowerShell hand-off swaps them in after the game quits and starts it
  again - retrying a locked file, and putting the old files back if it cannot
  finish.  `config` is never written; files are only deleted from
  `_internal`.  `papasangre2/update/`, proved by `tools/verify_updater.py`.
* **The game ships as a folder, its data encrypted inside the exe** (decision
  20, 2026-09-25).  The original is an iOS app; the port was one exe that
  unpacked everything (about 220 MB) to a temporary folder at every start -
  about 5 s, against 1.9 s now.  The exe sits beside its libraries
  (`_internal`), and every sound, level and playlist travels in one pack
  encrypted with ChaCha20 and embedded in the exe as a Windows resource
  (`assets/pack.py`), read from memory - no loose game files, and no path long
  enough to trip Windows' 260-character limit.  The key is in the program, as
  any game's must be: it keeps the sounds from being browsed or copied, not
  from a determined programmer.
* **An enemy sent where it already stands stays there** (decision 16,
  2026-09-25).  The original's `findDirectionTo:` has no zero guard: an enemy
  standing exactly at home when every enemy is sent home got a direction of
  0/0 and was lost at NaN - unreachable, unkillable.  In ps2_15 that stranded
  a polar bear that had not moved yet each time another gave up searching, and
  the level needs all eight: played faithfully it could not be finished.  The
  same fix keeps ps2_16's hogs from vanishing that way.
* **A sound effect an object plays with PlaySound comes from that object**
  (decision 17, 2026-09-25).  The original plays every `PlaySound` flat
  (`-[PGEPlayer playSound:]`, `setSpatialized: NO`).  When the sender is an
  enemy, a penguin, a collectible or a spatialised sound, and the sound is not
  speech (no "SPEECH" in its name), it is placed where the sender stood when
  its trigger fired (ps2_15 sends a stabbed penguin home just before its knife
  sound): ps2_14's extinguisher hits on Mr. Fletcher's door, the knife hit
  (`beatsound`) on ps2_15/17's bears and penguins, Papa's hit.  A collectible
  with no sound of its own is a detector, not a place, and stays flat: ps2_7's
  hand-holds reach 1000 px from far off, and placed there the climbing scrape
  was lost (decision 23).  Speech, anything a floor, the room or the player sends, and
  what you hold - ps2_18's camera click, heard on your side while Papa's hit
  comes from him, and the knife's swing (`beatsound`, 2026-09-26, a tester's
  report) while the bear's or penguin's death comes from it - stay flat.
* **The shot hits what is in front of you** (decision 22, 2026-09-26, from
  testers' reports).  The original aims at a list kept from enter / leave
  messages: an agent that switched off in the cone stayed on it (a monster
  reset and brought back behind you could take a shot), one the shot failed
  to kill (moving, invincible) was dropped while still in front of you (no
  later shot reached it), anything with a size - a memory, a sound, the
  camera - could take the shot meant for the monster behind it, and the
  penguin, keeping no distance, was always nearest.  Now: the nearest active,
  living monster or penguin in the cone at the moment you fire.
* **Every recorded line can be heard** (decision 21, 2026-09-26).  Of 328
  recorded lines, 16 are never played in the original and the idle hints never
  fire; all are wired in (`world/requested.py`, `tools/unused_speech.py`):
  - the idle hints: after 30 s without a step, while you may walk and nobody
    is talking (the original's clock stays at +inf), each once per attempt
    (decision 23); levels 9 and 10 get the hints recorded for them, level 18
    its (level 11b's) shooting hint, level 14 none (its data names level 7's);
  - the wall and trip lines count per level (the first two of each) in the
    Intro and ps2_1 only (decision 23) - the original counts over the whole
    game, so they were over after the Intro;
  - ps2_1 "stop waving your hands": six empty presses, left and right in turn
    (the original's once-only third press is gone); ps2_15 "stop waving that
    knife around": four swings at nothing;
  - ps2_14 "Watch out! / Careful! / Watch it!" coming near a burning wall
    again (the data misspells the name); ps2_16 "Quick, move!" after the first
    two memories; ps2_7 "Press your right and left hands..." if you stay in
    the first hole; the Intro's "Face the music..." reminder and "Good. Keep
    going." in the turn;
  - ps2_1's "Smash the case open with your hand" once, 8 s after the case's
    explanation if the case is still whole (it had been another take of that
    explanation, so half the time the case went unexplained - decision 23);
  - other takes of a line join it: ps2_14's "Smash it!", ps2_18's second set
    of "keep moving".
* **The Intro's museum music comes from the door** (2026-09-27, the owner and
  the tester): `door_closed` has no `spatialized` key and PGESound's default is
  NO (`-[PGESound init]` 0x10003296c sets none), so the original played it in
  your head.  Placed at the door, gain 36 under a ceiling of 5 after distance
  (`max_gain`, OpenAL's AL_MAX_GAIN, 1 for every other sound), so it carries
  across the garden.  And "Face the music..." (decision 21's reminder) is said
  once, not looped.
* **The first private beta's reports** (decision 23, 2026-09-26, the
  tester's list; he asked to keep the shake whoosh):
  - the Intro's record scratch: moved to 35.5 s for a while, back at the
    original's 36 s since the real cause was found - the port's game clock
    ran about 6 % slow against the sound (a port bug, fixed in
    `Game.update`), so every delay came late; "Good. Keep going." never talks over
    "See the stone fountain / that gramophone" (priority 1 under their 2, and
    gone once both are found);
  - ps2_3's sparkler is picked up when you reach it (`ignoreLoop`, as every
    memory), not at the end of its 8 s loop;
  - ps2_5a: reaching the gramophone player goes on to "You'd better put the hat
    back on" a second later, not after 6 s of crackle (the tester turned about,
    thinking he had to set it off);
  - ps2_9's large explosion (the submarine's power going) plays flat at gain
    0.7, what it was heard at from 120 px (rendered);
  - ps2_14's oil can can be sprayed from 80 px (its data's `beatRange`, which
    the original reads nowhere - 30 px), in a 37-degree cone (ps2_14's second
    door's 0.8) and from right on top of it whatever the angle; the collapsing
    house comes after you from its first sound (it stood still for all 8.4 s
    of it) and its loop takes over 1.5 s before that sound ends;
  - ps2_15's "Jump! Use both feet" waits 15 s between passes (it looped back
    to back);
  - ps2_18: your feet stay still from picking up the camera to the end of "Ah,
    you found the camera..." (a dropped or skipped line ends it too);
  - ps2_18b's hold music at gain 0.5 (it was as loud as the voice over it) and
    sixteen shakes to destroy it (the data's `afterCount=7` took eight; the
    owner chose 16);
  - the first two steps after a stop walk: `updateBPMCounter` measures no
    interval on the first step (infinite tempo) and halves the one on the
    second, so the original always ran them.  The tempo that decides tripping
    is untouched;
  - the level list clicks when you choose a level (silent in the original);
  - About reads a row at a time - each paragraph, and each credit as "role:
    names" - with Main Menu last, instead of one long run of text.
* **A penguin killed with the knife dies with Muhammad's own sound**
  (decision 18, 2026-09-25): his penguin death with a stab in it
  (`requested/sounds/penguin_death_stab.wav`), placed at the penguin, instead
  of the original's (the same file for all four penguins).  A shot penguin
  (ps2_17's rifle) keeps the original's.
* **Tripping on glass makes a sound** (decision 19, 2026-09-25).  The original
  has no glass trip (its glass footsteps are walking and running only), so a
  trip on glass - ps2_1, 2, 5 and the hogs' ps2_16 - was silent (the hogs still
  heard it).  Muhammad chose one of six built in the shape of the game's other
  trips: the game's glass scuff, a bodyfall from his library with broken glass
  crunching under it and a game glass step, then the glass settling
  (`tools/make_glass_trip.py`, candidate 1; `requested/sounds/trip_glass.wav`,
  stereo like the glass steps).  One take, so every glass trip is the same.  Two trips the original has under
  another name are hooked up too: the Intro's squelchy gravel
  (`trip_gravel_squelch_*`) and ps2_3's cracker floor (`trip_stone_*`).
* **The win screen keeps the achievement as a row** (2026-09-24): after
  Continue, "Achievement: title, achieved / not achieved" and the game's own
  achieved or unachieved description - the original's on/off badge, spoken.
