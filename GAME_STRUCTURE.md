# Papa Sangre II - recovered game structure

Everything here comes from the shipped iOS bundle in `reference/` (extracted from
`C:\Users\Muhammad\Downloads\ps2.zip`, which is never modified): the Objective-C
class metadata, the arm64 disassembly, and the bundle's data files. Addresses are
in the PS2 arm64 slice unless marked PS1.

* **[R]** recovered - read directly from the binary or the data.
* **[I]** inferred - deduced, still to be confirmed by reading the code named.
* **[U]** unread - known to exist, not yet read. Nothing marked [U] may be ported
  until it is read.

Companion files:

* `docs/ENGINE_DIFFERENCES.md` - PS1 engine versus PS2, class by class, in words.
* `docs/ENGINE_DIFF.md` - the same, method by method, generated (`tools/bindiff.py`).
* `docs/MESSAGE_MAP.md` - every engine message: who fires it, who observes it.
* `docs/SOUND_INVENTORY.md` + `docs/sound_inventory.csv` - all 1169 audio files.
* `docs/notes/ENGINE_NOTES.md` - raw reading notes.

---

## 1. The application

| Fact | Value |
|---|---|
| Title | Papa Sangre II (Somethin' Else, published by Playground) |
| Bundle id | `com.ernesto.papa2`, version 1.0 |
| Binary | fat Mach-O, armv7 + **arm64**; arm64 slice (3.98 MB) extracted to `reference/PapaSangreII_arm64`; `cryptid 0` (decrypted) |
| Built with | Xcode 6.3.1, iOS 8.3 SDK, min iOS 7.0 |
| Engine | Papa Engine **1_1_013_2014_07_22_R** |
| Audio | same S3D / CSL stack as PS1 (`S3DEngine`, `S3DSound`, `S3DPlayList`, `csl::`) |
| Product name | `PapaSangre2` (`-[PGEngine init]` 0x100046ccc) |

**The engine is older than PS1's.** The PS1 port was recovered from the 2016
re-release, engine 1_1_020 (Aug 2015, Xcode 7.2). PS2 is 1_1_013 (July 2014).
So a behaviour can differ because PS1 gained it later, not only because PS2
added something. Every PS1 reading has to be re-checked, not assumed.

Of 242 classes, the PGE/S3D ones are the engine. Seven PGE classes are new
against PS1 (`PGEFollower`, `PGEFireworks`, `PGEDicoWithDelay`,
`PGESettingsViewController`, `PGELevelSkipperViewController`,
`PGEPopupViewController`, `PGELandscapeViewController`) and ten PS1 classes are
absent (`PGESummoner`, `PGENPC`, `PGEAlarm`, `PGEBeatable`, `PGEForgetfulMan`,
`PGETagPlayer`, `PGEPosition`, `PGEPlayerListener`,
`PGEDualStickViewController`, `PGEStepsWithHeightViewController`). **[R]**

`PGEForgetfulMan` is gone, but the forgetful men are not: in PS2 they are plain
`Monster` objects using `_forgetfulman*` sound banks (ps2_11b, ps2_15). The
level loader still lists the type names `Summoner`, `Position`, `NPC`,
`Beatable`, `TagPlayer`, `ForgetfulMan` in `isThisTypeAnAgent:` (0x10003c200),
but no shipped level uses any of them. **[R]**

## 2. Data

| Path | Count | Role |
|---|---|---|
| `levels/papasangre2/*.json` | 23 | the game's Tiled exports |
| `levels/Experiments/*.json` | 19 | developer test maps (see section 13) |
| `levels/papasangre2_hubList.plist` | 22 entries | menu order, titles, objectives, achievements |
| `levels/Experiments_hubList.plist` | 14 entries | the test maps' own menu |
| `meta/S3DPlayListModel/*.sexp` | 200 | playlists (several stale: `Intro`, `ps2_Intro.orig`, `*python`) |
| `sounds/**` | 1169 audio | 1091 `.m4a`, 78 `.mp3` (the mp3s are real game sounds, e.g. all stone footsteps) |
| `sounds/**/*.subplaylist` | 256 | empty marker files used by the developers' `generate_playlist.py` |
| `messagesList.plist` | 1 | editor schema of messages (there is no `objectsList.plist` in PS2) |

`sounds/generate_playlist.py` (shipped by mistake) documents the file-name
convention: `_SPA` = spatialised, `_UOS` = unload on stop, `_PRE` = preload. A
`.subplaylist` file next to sounds makes the generator emit a nested
`(playlist ...)` include. **[R]**

Also shipped by mistake: `sounds/NigelTest.rtf` ("This is Nigel's file that
he's going to push to S3"), `sounds/placeholder_script.mp3`, a README from the
Audio Defence cross-promotion (Daniel J. Finnegan, 22/10/2014). None of it is
game content.

## 3. Levels and hub

The hub list is a **flat list of 22 entries, ordered by `positionInMenu`**. It
has no act or chapter field. Only `ps2_Intro` is `unlocked` in the file; the rest
unlock through `PGEGameProgress`. **[R]**

| # | file | title | objective (`text1`) |
|---|---|---|---|
| 1 | ps2_Intro | You are dead | Collect the fragments of memory. |
| 2 | ps2_1 | Mind the Lice | ...without being heard by the mindlouse. |
| 3 | ps2_2 | Mindlice and Mindlice | ...without being heard by the mindlice. |
| 4 | ps2_3 | Fire and Lice | ...Move off noisey floors quickly. |
| 5 | ps2_4 | Mottled Death and Marbles | ...(text2) Clap to attract the mindlouse away from the door |
| 6 | ps2_5 | Are you being Preserved? | ...without falling in the bubbling pools of preserving fluid. |
| 7 | ps2_5a | Hometime | Follow the instructions to get back to the World of the Living. |
| 8 | ps2_6 | Ducks (You Are Still Dead) | Get to the duck stand. / Shoot the ducks using the air rifle in your left hand. |
| 9 | ps2_7 | Cat out of Hell | Get through the burning house... Follow the good cat - not the bad cat. |
| 10 | ps2_8 | Penguin Classics | Rescue the dog from the ice... Clap when a penguin gets too close... Follow the bird. |
| 11 | ps2_9 | Subatomic Conciousness | Release the trapped man... use the geiger counter... |
| 12 | ps2_10 | Dial 1 for Abyss | ...by throwing the glass in your right hand... |
| 13 | ps2_11a | Death becomes you | Someone's in trouble... / Go to the fountain to collect the water pistol. |
| 14 | ps2_11b | Papa's Zoo | Retrieve the memories. Shoot the Forgotten Men... |
| 15 | ps2_13 | Soul Diving | Swim to the bubbles to stay alive. Smash the memories as you go. |
| 16 | ps2_12 | Rolling Shot | Get to the train. / Shoot the ducks... |
| 17 | ps2_14 | Extinguish | ...throwing sand ahead of you. Use the extinguisher... |
| 18 | ps2_15 | Ice Hunt | Kill the polar bears with the dagger in your right hand... Clap to scare off the penguins... |
| 19 | ps2_16 | Thunderhogs | ...only moving under cover of thunder. |
| 20 | ps2_17 | Husks | Make your way through the husks of the memories you've destroyed. |
| 21 | ps2_18 | Paparazzi | ...Shoot Papa's forces... DON'T stop running. / ...take his photo with the camera in your right hand. |
| 22 | ps2_18b | Unplugged | You're almost free to go back to the World of the Living... |

Note the menu order: **ps2_13 comes before ps2_12**, and the level data agrees
(11b -> 13 -> 12 -> 14).

Each entry may also carry `text2`/`text3` (later objectives, see `SetPauseText`
in section 8), `successText` (win screen), `twitter_death_text`,
`menu_background` / `menu_image` (art), `achievement {id, title,
achievedDescription, unachievedDescription, ...}` (18 levels), `cannotSkip`
(ps2_18 only), `nextLevel`. **[R]**

### The chain, from the data

Every `LoadLevelWithName` in the 23 maps:

```
Intro -> 1 -> 2 -> 3 -> 4 -> 5 -> 5a -> 6 -> 7 -> 8 -> 9 -> 10 -> 11a -> 11b
      -> 13 -> 12 -> 14 -> 15 -> 16 -> 17 -> 18 -> 18b -> PresentAdiosVC (the end)
```

Plus one `LoadLevelWithName` naming the level itself in every level that can
kill you (that is the death path, section 8). **[R]**

### ps2_11 is a cut level

`ps2_11.json` ships, but **nothing loads it**: no `LoadLevelWithName` in any
map names it, and the hub list does not list it. Its playlist
`ps2_11.S3DPlayListModel#0.sexp` is **empty** - no sounds, no includes - so
243 of its sound references resolve to nothing. It is an abandoned draft of
11a/11b (its own exits lead to them). **[R]** Proposed verdict: N/A, cut
content, not reachable in the shipped game. *Your call* - see the questions.

## 4. Coordinates and the tick

Same transform as PS1 (room centred on the origin, Y negated) - to be re-read in
PS2's `createObjectFromDict:` before it is relied on **[I]**.

**The tick is 20 Hz, not 10.** `-[PGELevel init]` schedules `update` every
**0.05 s** (0x10003a0c4; PS1: 0.1 s at 0x10002c50c). Each tick
(`-[PGELevel update]`, 0x10003f5d8) **[R]**:

1. if the level is waiting for its intro speech, keep waiting; otherwise finish
   loading (`actuallyLoadDataFromJsonFile`);
2. the inactivity nag (as PS1);
3. every agent `update:0.05`;
4. **every surface `update:0.05`** (surfaces have timers in PS2, section 7);
5. the **player** `update:0.1` on every **other** tick (10 Hz);
6. `increaseUnderwaterDuration:0.05` on the player;
7. the level's own `update:0.05` - its **delayed triggers** (section 6);
8. the tracker's elapsed time.

## 5. Level loading

Three passes as PS1 - Room, then every other object, then the Player - then
`PGE_MESSAGE_LevelInited`, `FadeOutMenuAtmos`, `RemoveFullScreenImage`.
`loadPlayer:` posts `SetControlSettingsToDefault` and `MovePlayerToPosition`.
**[R]**

* **No layer is skipped.** PS1's newer loader drops layers named `ToolBar`; PS2
  has no such check (0 references to "ToolBar"). Every object in every layer is
  built - ps2_14's layer literally called "no longer used" included. **[R]**
* **Triggers are an explicit list per type** (`createObjectFromDict:`,
  0x10003c35c), not "any key starting On":

  | type | trigger names |
  |---|---|
  | every agent | OnRouteChange OnShake OnStep OnStab OnHitWall OnClapTooMuch OnClap OnCollide OnShootMissed OnShoot OnActivate OnDeactivate OnEnteringShootRange OnPathEnd OnRightHand OnLeftHand OnLoad |
  | + Collectible | OnCollect OnSkip OnSoundEnd |
  | + Sound | OnSkip OnSoundEnd |
  | + Monster | OnBeatenSoundEnd OnShotSoundEnd OnBeatMissed OnChase OnPlayerLastPosition |
  | + Follower | OnProximity |
  | + Fireworks | OnSoundEnd OnExplosion OnGoOff |
  | Player | OnShake OnPathEnd OnGagging OnHitWall OnClapTooMuch OnClap OnLoad OnTrip OnShoot OnRightHand OnLeftHand OnBeatMissed OnShootMissed OnEmptyHand |
  | Room, Surface | OnStillLimit OnTrip OnDeadlyNo OnDeadlyYes OnExit OnPebble OnActivate OnDeactivate OnStep OnEnter OnJumpTooMuch OnJump OnKill |

  A key equal to a listed name **or starting `<name>_`** is a trigger of that
  type (`parseTriggersForNames:propertiesDict:receiver:`, 0x10003e77c) - that is
  how `OnActivate_2`, `OnEnter_2` carry a second trigger. A trigger key not in
  its type's list is dropped: the data has Room `OnLeftHand` / `OnRightHand` /
  `OnLoadLevel`, a Surface `OnSoundEnd`, and Sound `OnXrail` / `OnYrail`, all
  of which the original ignores. **[R]**
* Every other key goes to `set<Key>:` with its first letter upper-cased, if the
  object responds (logged red "Cannot find %@ on %@" otherwise). So the data's
  `CollideRadius`, `Active`, `ActivationCounter`, `Skippable` do apply, and
  `mutlipleOnEnter` (32x) and `footstepsfootstepsPrefix` (7x) are typos that do
  nothing. `onXrail` / `onYrail` / `onInactiveRail` (lower-case) are
  **properties** of `PGESound`, not triggers. **[R]**
* **`active` is applied late**, from a `dispatch_after` block (0x10003e674).
  **[R]** (delay value [U])
* Defaults when the data names none: Room `runBPM` 180 / `tripBPM` **280**,
  Surface `runBPM` 180 / `tripBPM` **350** (0x10003d090, 0x10003d0d4,
  0x10003e098, 0x10003e0e4). PS1 has the same pair. **[R]**
* Surfaces may be **circles** (`isCircle`). **[R]**
* Unnamed agents are called `default_agent_%i`. **[R]**

## 6. Triggers and messages

Statement grammar as PS1 (`Msg:key=val;key=val`, statements split on `|`),
plus two consumed keys: **`minDelay` / `maxDelay`** - a random delay between
them. PS1's `soundName` -> `PPAE_MESSAGE_CacheSound` side effect is absent.
(`createDictFromTriggerDescription:`, 0x10003ee18.) **[R]**

**Delayed triggers are owned by the object, not the run loop.** A delayed
statement becomes a `PGEDicoWithDelay {dict, delay}` on the sender
(`triggerWithType:`, 0x100028268); the sender's `update:` counts it down by the
tick and enqueues it when it reaches zero (0x100029088). So a delay **freezes
while its owner is paused**, and it is **cancelled** when the owner is
deactivated by name, deallocated, or the level shuts down
(`clearDicoWithDelayArray`). PS1 used `performSelector:afterDelay:`. **[R]**

Every message the levels fire, and who observes it: `docs/MESSAGE_MAP.md`.
Five statements in the data name no observer and do nothing in the original:
`DeactiveAgentWithName` (ps2_11b, misspelt), `DisableClap;afterDelay=2`
(ps2_12, `;` where `:` belongs), `ShutDownLevel;afterDelay=1` (ps2_18),
`RemoveFullScreenImage;afterDelay=3` (ps2_18b, visual anyway), a bare `YES`
(ps2_Intro), and a bare sound name `tripwire_decline_rescue` (ps2_14). **[R]**

## 7. What PS2 plays with - the mechanics PS1 never switched on

### The input model

The touchscreen sends these, and the engine turns them into actions
(`docs/MESSAGE_MAP.md`, `PGE_INPUT_*` and `PGE_ACTION_*`) **[R]**:

| touch / sensor | message | handled by | action |
|---|---|---|---|
| foot pad | `PGE_INPUT_FootButtonReleased {Foot}` (from `stepOn:`) | `footButtonReleased:` | `PGE_ACTION_OneStep` / `Trip` |
| hand button | `PGE_INPUT_HandButtonPressed {Hand: L/R}` | `handButtonPressed:` | `PGE_ACTION_Hand` |
| two-finger tap | both fingers on the upper part, one each side (the two hands) -> `PGE_INPUT_HandsClapped`; both on the lower half, one each side (the two feet) -> `PGE_INPUT_Jump` (`handClapDetected:`, 0x10000fdac) | `handsClapped:` / `jump:` | `PGE_ACTION_HandsClapped` / `PGE_ACTION_Jump` |
| shaking the phone | accelerometer over 1.3 g, with hysteresis (`accelerometer:didAccelerate:`, 0x100011fc0) | - | **`PGE_ACTION_Shake` directly** (no gating) |
| holding it portrait / landscape | `PGE_INPUT_RotateDevice {orientation}` | `userDidRotateDevice:` | lets a waiting agent activate |
| swipe / gyro / tilt (control scheme) | `PGE_INPUT_RotateFromAngle` | `rotatePlayerFromAngle:` | turning |
| double tap / skip button | `PGE_INPUT_DoubleTap` | `onDoubleTap` on Sound / Collectible | skip narration |
| headphones unplugged | `audioRouteChanged:` | agents with `requiresUnplug` | `OnRouteChange` |

Notes:

* **Nothing posts `PGE_INPUT_FootButtonPressed`.** The foot pad posts only
  "released", on touch, so a PS2 step lands the moment you touch - the
  key-down behaviour the PS1 port had to add as a REQUESTED change is simply
  what PS2 does. **[R]** (which UIControl event the pad uses [U], nib)
* The two-finger recogniser holds single touches back until it fails and
  cancels them when it succeeds (`setDelaysTouchesBegan:YES`,
  `setCancelsTouchesInView:YES`, `initGestureRecognition` 0x10000f7f8): a clap
  is not also two hand presses, a jump is not also two steps. **[R]**
* **`PGE_INPUT_Shake`** (the system shake gesture) is posted and observed by
  nothing. The shake that matters is the accelerometer one. **[R]**
* **Nothing posts `PGE_INPUT_Swim`**, so `PGE_ACTION_Swim` / `swim:` is
  unreachable; "Soul Diving" is walking on `isUnderwater` surfaces. **[R]**
* **`-[PGEPlayer shuffle]` is empty** (one instruction). The two-second
  shuffle sound of PS1 does not exist in PS2, although `updateFeetView:` still
  posts `PGE_ACTION_Shuffle`. **[R]**
* The "tilt" of the brief is the portrait / landscape orientation: an agent with
  `requiresPortraitPicture` or `requiresLandscapePicture` will not activate until
  the phone is turned that way (`tryToActivateAgent`, `userDidRotateDevice:`).
  **[R]**

### Hands

`PGE_ACTION_Hand {Hand}` reaches the player and every agent in range. The
player (`handsActionMessageReceived:`, 0x10002df5c) **[R]**:

* respects a **reload timer** (`reloadTime`);
* fires its own `OnLeftHand` / `OnRightHand`;
* does the hand's **action**, a string set per level (`leftHandAction` /
  `rightHandAction`, changed mid-level by `ChangeHandAction`):
  `shoot` -> `shoot:`, `beat` **or `stab`** -> `beat:` (the two names take the
  same branch, 0x10002e164), `throw` -> `throwSomething`;
* with no action, fires `OnEmptyHand` and plays the empty-hand sound.

Agents (`-[PGEGameAgent handsActionMessageReceived:]`) fire their own
`OnLeftHand` / `OnRightHand` when the player is inside their collide range.
Collectibles with `collectWithLeftHand` / `collectWithRightHand` are **picked up
only with that hand** while you stand in range. **[R]**

* **shoot** (air rifle, water pistol): shoot sound, player `OnShoot`, the
  **nearest agent in the player's shooting cone** is shot (`wasShot`) or the shot
  misses (`OnShootMissed`). **[R]**
* **beat** (dagger, extinguisher, camera): `PlayerDidBeat`; agents in beating
  range (`beatRadius` 30, `beatDotProd` 0.92 by default) are beaten
  (`wasBeaten` -> `OnStab`); otherwise the beat sound and `OnBeatMissed`. In
  ps2_18 the camera is `rightHand=beat` and each beaten Papa counts a photo
  (`picturesTaken`, `4_papa_` sounds). **[R]**
* **throw** (glass, sand): looks at the ground one and two strides ahead
  (`throwSomething`, 0x10002e778); a lethal surface there fires its `OnPebble`;
  the sound is `throw_<that surface's footsteps prefix>` (by substring), or the
  wall sound when there is no surface; posts `PlayerDidThrow`. That is how you
  "feel" the abyss. **[R]** (which of the two strides wins [I])

### Clap

`PGE_ACTION_HandsClapped` -> `-[PGEPlayer clap:]`: unless clapping is disabled
(`DisableClap` / `EnableClap`), plays `clapSound`, fires the player's `OnClap`,
and counts claps (`updateClapCounter`, 0x10002dca0): the last four clap times
are kept, and once there are three or more whose average gap is under **0.3 s**
the player fires `OnClapTooMuch` and the count starts again (the average divides
by the number of claps, not gaps - the BPM counter's quirk [I]). Every agent
also fires its own `OnClap`. Levels use it to
alert monsters (`OnClap: AlertAllEnemies`) and to scare penguins
(`SendAgentAwayFromPlayer`). **[R]**

### Shake

`PGE_ACTION_Shake` -> agents fire `OnShake` when you are within their collide
radius; collectibles with `collectWithShake` are collected by shaking in range
(and after 20 s in range regardless [I], `-[PGECollectible update:]`). **[R]**

### Jump

`PGE_ACTION_Jump` -> player `jumpSound`; surfaces fire `OnJump` and, for jumps
too close together, `OnJumpTooMuch`. Only ps2_15 enables jumping. **[R]**

### Underwater

A surface with `isUnderwater` starts the player's underwater clock; at 75 % of
`underwaterMaxDuration` the player fires `OnGagging` and loops the gagging
sound; at 100 % the player **drowns** (drowning sound, level shut down, reload
with cause `drown`). `ResetUnderwaterTimer` (the bubbles) refills it. **[R]**

### Surfaces that kill, cycle and watch

* `isLethal` + `deathSound` / `deathCause`: stepping on it kills you
  (`kill` -> `OnKill`, death sound, shut down, reload with the cause).
* `deadlyTime` / `safeTime`: the surface alternates deadly and safe, firing
  `OnDeadlyYes` / `OnDeadlyNo` (the submarine's steam blasts).
* `stillLimit`: standing still on it too long fires `OnStillLimit`
  ("DON'T stop running", ps2_18). `lethalAfter` [U].
* `followerTime` / `followerAlertSound`: a follower (penguin) close to you for
  that long cracks the ice - warning sound, then death unless
  `followerNotDeadly`.
* `isWalled`: the player cannot step onto it (`canPlayerMoveToPosition:`).
* A surface can carry its own `sound`, positioned along the surface relative to
  the player (`computeNewPlayerPosition:`) - fire walls. **[R]**

### Rails, vibration, camera roll, headphones, VoiceOver

* `onXrail` / `onYrail`: a sound that follows the player along one axis;
  `onInactiveRail` also while inactive (`-[PGESound playerMovedToPosition:]`).
  **[R]**
* `Vibrate` (ps2_5a, ps2_11a - a phone buzzing in the story): the iPhone's
  vibration motor, no sound. **[R]**
* `SaveImageInCameraRoll` (ps2_18): saves Papa's portrait PNG to the photo
  library. No sound. **[R]**
* `requiresUnplug` (ps2_18b "Unplugged", 3 sounds): the sound waits until the
  headphones are unplugged, then fires `OnRouteChange`. **[R]**
* **VoiceOver changes the game.** When VoiceOver is running, a sound named `X`
  is played as `blind_X` if that exists (`createSpatializedSound`, 0x100033818);
  three do, all in the Intro training. VoiceOver also selects the accessible
  level list and other UI paths. **[R]**

### Where the data switches them on

Counts per level (from the maps; `L=`/`R=` is the hand action at load, `chg`
the `ChangeHandAction` values used later):

| level | hands | clap | shake | orientation | other |
|---|---|---|---|---|---|
| Intro | Enable 2 / Disable 4, hand-collect 2 | OnClap 1 | | | rails 4, rotation on/off |
| 1 | hand-collect 2, OnHand 6 | OnClap | | | walled 1 |
| 2 | hand-collect 4, OnHand 6 | OnClap | | | walled 2 |
| 3 | enabled | OnClap | | | |
| 4 | enabled | OnClap ("clap to attract the mindlouse") | | | |
| 5 | hand-collect 4 | OnClap | | | lethal pools 4, walled 2 |
| 5a | OnHand 2 | | collect-by-shake 1 | **landscape 1, portrait 1** | vibrate 3, rails 6 |
| 6 | `leftHand=shoot` (air rifle), 18 OnShoot | **EnableClap** | | | |
| 7 | OnHand 4 | | | | lethal 6, rails 10, underwater 2 |
| 8 | | OnClap -> scare penguin | | | Follower 1, ice |
| 9 | OnHand 1 | | | | steam cycles 7, walled 4 |
| 10 | `R=throw` (glass) | | | | lethal abyss 11, OnPebble 11 |
| 11a | `leftHand=shoot` later (water pistol), hand-collect 4 | | | | vibrate 10 |
| 11b | `L=shoot`, 24 OnShoot | OnClap | | | |
| 13 | hand-collect 12, OnHand 10 | | collect-by-shake 1 | | underwater, ResetUnderwaterTimer 13 |
| 12 | `leftHand=shoot`, 17 OnShoot | (`DisableClap` malformed) | collect-by-shake 1 | | player follows a path, rails 7 |
| 14 | `L=beat` (extinguisher), `R=throw` (sand), 12 ChangeHandAction | | **OnShake 5**, collect-by-shake 1 | | lethal 11, OnStab 5 |
| 15 | `R=beat` (dagger), OnStab 12, OnShoot 11 | OnClap | collect-by-shake 1 | | **EnableJump**, Follower 4 |
| 16 | hand-collect 12, OnHand 10 | OnClap | | | walled 4, thunder |
| 17 | `L=shoot`, `R=throw`, later `rightHand=beat` | OnClap | | | Follower 2, steam 5, OnPebble 6 |
| 18 | `L=shoot`, later `rightHand=beat` (camera), OnShoot 45 | OnClap | | | stillLimit 6, rails 24, camera roll |
| 18b | | | **OnShake 1** | | **requiresUnplug 3** |

Every level but 13 names a `clapSound`; clapping is available by default and
only ps2_6 / ps2_12 touch the switch. **[R]**

## 8. Winning, dying, and the screens in between

`-[PGEngine loadLevelWithName:]` (0x100047100) decides the outcome itself **[R]**:

* a `LoadLevelWithName` naming **another** level is a **win**: the current level
  is completed, the named one unlocked, achievements checked, and the **Win
  screen** is shown (`PGE_MESSAGE_PresentWinVC {name, nextLevel}`);
* naming the **same** level is a **death**: the **Lose screen** is shown with
  the trigger's `deathCause` (`PresentLoseVC`);
* only from those screens is the next level (or the retry) actually loaded.

So the original **has** an after-level menu. The Win screen shows
`successText`, the achievement, share buttons, back to hub, continue. The Lose
screen offers **play again**, **quit**, and **skip** (section 9). **[R]** The
port uses the PS1 port's after-level menu instead, keeping these screens'
sounds (BUILD_ORDER.md decision 4).

On death, `playFailSoundForLevel:deathCause:` plays a narration from the menu
playlist: `<level>_fail_<cause>` or `<level>_fail`, preferring ones not yet
heard (`hasPlayedLevelEndSound:`), plus `lost_memory_<n>_UOS` counting the
memories you have lost, then the menu death atmosphere. On a win,
`<level>_end_music_loop` plays under the win screen (`playEndMusicForCurrentLevel`,
preloaded by sounds carrying `preloadEndMusic`). **[R]** (exact order and timing
[U])

`SetPauseText:name=text1|text2` makes the pause screen show that level's hub-list
objective - the in-game hint. **[R]**

Death causes in the data: banging, cat, ceiling, explode, forgetfulman, ice,
monster, music, run, smoke, surface, wall (plus `drown` from code).

## 9. Progress, skip tickets, achievements

`PGEGameProgress` (NSUserDefaults) keeps what PS1's did plus **[R]**:

* **skip tickets** - in the original (a Skip button on every death screen,
  two tickets), **not ported: removed at Muhammad's request** (BUILD_ORDER.md
  decision 4). `failedLevel:` still counts deaths per level
  (`<level>_failed`); what reads that count is [U].
* **achievements**: 18, defined in the hub list, checked per level by
  `checkAchievementsForlevel:` (1096 instructions, [U]) against counters the
  engine keeps - trips, wall hits, claps, kills, penguin kills, steps, time,
  photos. Reported to Game Center.
* `memoriesLost`, `totalKills`, `totalSteps`, `tripTimes`, `wallTimes`, last
  level played, per-level end-sound history.

## 10. Menus in the original

| screen | what it does |
|---|---|
| main (`PGEViewController`) | splash with `papa_engine_splash_UOS`; "Wear headphones" warning; Continue; Level selection (**`AccessibleAllLevelsViewController` when VoiceOver is on**, the picture hub otherwise); Settings; Credits; More Games |
| accessible level list | `"Play Level %i: %@"` / `"Level %i: %@; locked"` from the hub list (same as PS1) |
| settings | the turning control scheme: gyro, swipe or tilt ("You have selected gyro mode.") |
| pause | resume, restart, quit, and the level's pause text; posts a VoiceOver announcement "Pause menu" |
| win / lose / level skipper | section 8 and 9 (the port: PS1-style after-level menu, no skipper) |
| credits, adios (end of game) | as PS1 |

## 11. Audio

* **Per-level reverb.** The Room sets `reverbRoomSize` / `reverbDampening` /
  `reverbVolume`, and `ChangeReverbSettings` changes them mid-level (11 levels).
  The setter clamps room size to **[0.01, 2.3]**, dampening to [0, 100], volume
  to [0, 8]. `-[PGEngine init]` starts from 2.1 / 5 / 1. PS1 had one reverb for
  the whole game. **[R]**

  | levels | size / damp / vol |
  |---|---|
  | Intro, 5a, 6, 12, 18b | 1.5 / 100 / 0.2 |
  | 1-5 (the museum) | 1.7 / 70 / 1 |
  | 7, 14 | 2.3 / 100 / 0 |
  | 8, 11, 11a, 11b, 15, 18 | 2.3 / 100 / 0.2 |
  | 9 (submarine) | 1.1 / 100 / 2 |
  | 10, 17 | 1.8 / 75 / 0.4 |
  | 13 (underwater) | 0.5 / 0 / 8 |
  | 16 | 0.5 / - / 0.5 |

* `distanceScale` **0.016** (PS1 0.008), `maxSpatialGain` **2** (PS1 100)
  (`-[PGELevel initSoundEngine]`, `-[PGEngine init]`). **[R]**
* Every agent sound uses the automatic reverb mix: min distance 1, max 100, wet
  send 0.05 -> 0.3 (`setupReverbParameters:`). **[R]**
* New per-sound features: `fadeInTime` / `finalGain`, `soundPriority` (a
  higher-priority sound stops lower ones, `StartedSoundWithPriority`),
  `stream`, `planar` spatialisation, `FadeOutAgentWithName`,
  `PauseAgents` / `UnpauseAgents` with per-agent `pauseSound`, `unpausable`.
  **[R]** (the audio-side meaning of `planar` [U])
* Footsteps are `footwalk_<prefix>_*` and `footrun_<prefix>_*`; trips are
  `trip_<prefix>_*` - **PS2's `trip:` does use the surface's prefix**
  (`stringWithFormat:@"trip_%@"`, 0x10002ce28), unlike PS1's. Throws are
  `throw_<prefix>`. **[R]**

## 12. The two new gameplay classes

### PGEFollower - the penguins

Used by ps2_8 (1), ps2_15 (4), ps2_17 (2), all named `penguin*`. **[R]**

* States 201 (following), 202 (close), 203 (sent away), 10 (waiting for its
  intro sound) (`update:` 0x100064144, `checkCollisionsWithPlayer` 0x100065058).
* 201: walks straight at you at `chaseSpeed` with `chaseSound`; its collide
  radius is `smallRadius` (default 30). Inside it -> 202 and `FollowerIsClose`.
* 202: on entry fires `OnProximity`; stops, plays `proximitySound`, collide
  radius becomes `largeRadius` (default 60), so you must get 60 away, not 30,
  before it is "far" again -> 201 and `FollowerIsFar`. The ice surfaces time how
  long the penguin stays close (section 7).
* 203, from `SendAgentAwayFromPlayer {name, duration}` (the levels' answer to a
  clap): `scaredSound`, runs directly away from you (the direction to the
  player, negated) at `chaseSpeed` until `duration` has passed, then 201.
* Can be shot or stabbed (`shotSound` / `beatenSound`), counted for the "Penguin
  Hater" achievement.

### PGEFireworks - only in a test map

A lit firework (`litSound`) that you must take with a hand before `litTime`
runs out; `aboutToGoSound` at `aboutToGoOffTime`, then `goOffSound`,
`OnGoOff`, `OnExplosion`. **Used only by `levels/Experiments/fireworks.json`** -
no shipped level has a `Fireworks` object. The hub text "the hidden sparkler"
(ps2_3) is an ordinary collectible. **[R]** Proposed verdict: N/A.

## 13. The developer test maps

`levels/Experiments/` holds 19 maps with their own hub list: door_opening,
enemies, enemies_behaviour, factory, fireworks, hub_demo (3), icefield,
masterclass, reckoner, room1_1, shoot_on_path, submarine,
submarine_underwater, surfaces, throw, walk_and_shoot, wall_collide. They are
documentation of each mechanic in isolation and will be the port's unit-test
fixtures. They are not part of the game and are not in any menu.

## 14. Sounds

`docs/SOUND_INVENTORY.md`. Headline: 1169 files, 1167 declared by a playlist,
**1103 reachable** from shipped level data or from code, 4 only from test maps,
**62 reached by nothing found yet** (each needs a reason - mostly unused
variants such as `forgetfulman3_patrol_SPA`, and three `hint` narrations). The
unresolved references in shipped data are dominated by the cut ps2_11 (243) and
by the levels loading trimmed `_light` playlists that omit sounds their monsters
never reach in practice; each one is silent in the original if reached.
