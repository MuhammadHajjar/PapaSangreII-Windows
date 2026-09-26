# PS1 engine versus PS2 engine, class by class

The PS1 port (`..\PapaSangre`) was recovered from Papa Engine **1_1_020** (2016
re-release). Papa Sangre II runs **1_1_013** (July 2014) - an *older* build of
the same engine. This file says, for every gameplay class, what is the same, what
is different, and what has not been read yet. The mechanical, method-by-method
comparison it rests on is `docs/ENGINE_DIFF.md` (`tools/bindiff.py`), which
normalises away addresses, register allocation, `nop` padding and the two
compilers' different selector-loading idioms, so that "changed" there means the
code does something different.

Totals over all PGE/S3D classes: **463** methods identical, **104** identical
references in the same order (codegen only), **300** changed, **722** new in PS2,
**206** only in PS1.

Reading depth used below:

* **read** - control flow read in the listing, addresses given.
* **calls** - its call sequence, arguments and constants read (`tools/sig.py`),
  not every branch. Good enough to say *what* it does; not good enough to port.
* **unread** - not looked at yet.

**Rule for the port: a method is only ported from PS1 code if it is "same" or
"same refs" in ENGINE_DIFF.md. Everything else is re-recovered from PS2.**

---

## Audio: S3DEngine, S3DSound, S3DPlayList, S3DPlayListModel, S3DRepo, S3DEngineDispatcher

Almost unchanged. S3DSound: 99 same, 22 same refs, **2 changed** (`cleanup`,
`play:fadein:`). S3DEngine: 36 + 37, 8 changed (`init`, `staticPlayLists`,
`stopAll`, logging). S3DPlayList: 30 + 10, 6 changed. The PS1 port's audio
engine is the right base.

Differences found (read): **`-[PGEngine init]` sets `maxSpatialGain` 2.0**
(PS1 leaves S3DEngine's 100); **`distanceScale` 0.016** (PS1 0.008,
`-[PGELevel initSoundEngine]`); `setReverbRoomSize:` clamps to [0.01, 2.3]
(same code in PS1 - the PS1 port records [2.2, 2.3], a misreading, now a
separate task). Unread: the 6 S3DPlayList changes, `play:fadein:`, `cleanup`,
`staticPlayLists`.

## PGEObjectWithTriggers - triggers

* `triggerWithType:` - **changed, read**. Same count / afterCount / parameters
  as PS1; new `minDelay`/`maxDelay` random delay; delayed statements go into
  the object's own `dicoWithDelayArray` instead of `performSelector:afterDelay:`.
* `update:` - **new, calls**. Counts delays down by the tick, enqueues on zero.
* `clearDicoWithDelayArray`, `hasTriggerWithType:`, `randFloatBetween:and:` -
  new, calls.
* Consequence: delays pause with their owner and die with it.

## PGELevel

* `createObjectFromDict:` - **changed, calls + constants** (2306 instructions).
  Per-type explicit trigger lists; `_2` suffixes; `On`-prefix withheld from
  setters; `active` applied from a delayed block; Room reverb; circles; default
  tripBPM Room 280 / Surface 350 (as PS1). Position transform not yet re-read.
* `loadLevelAgents:` / `loadLevelStructure:` / `loadPlayer:` - changed, calls.
  **No `ToolBar` layer skip** (PS1 has one).
* `createDictFromTriggerDescription:` - changed, calls. + minDelay/maxDelay;
  - CacheSound.
* `update` - **changed, read**. 20 Hz; floors, level and player updated too.
* `shutDownLevel:` - changed, calls. Non-sender agents get
  `deactivateWithNoCallback` (**no `OnDeactivate`** - PS1's `deactivate` fired
  it, which is what re-armed ps1_23's cage) and lose their delayed triggers;
  floors are deactivated; then DisableHands / Walk / Rotation.
* `computePlayerMovedToPosition:justStepped:` - new, calls. Replaces PS1's
  surface search: `surfaceForPosition:`, OnStep / OnExit / OnEnter, copies
  tripBPM / runBPM / shuffleSound / isUnderwater / footstepsPrefix onto the
  player, posts `PlayerWalkedOnSurfaceWithId`.
* `canPlayerMoveToPosition:`, `surfaceForPosition:`, `wallNormalVector:`,
  `changeReverbSettings:`, `highestPriorityPlayingSound`, `deactivateAllAgents`,
  `surfaceWasActivated` - new, calls.
* `pause:` - changed, calls: posts a VoiceOver announcement "Pause menu".
* Gone from PS2: `solveDillemas`, `playerDidCollideAWall:` (moved to the
  player), `playerWasActive`.
* Unread: `init` details, `displayLevelImage` (visual), `setInactivitySounds:`,
  `changeInactivitySoundList:`, `pathWithName:`, `resume:`, `clearLevelData`.

## PGESurface

76 new methods; only the three trigger helpers carried over, and they changed.
New behaviour (calls): lethal surfaces and `kill`, deadly/safe cycling,
stillLimit, lethalAfter, follower timing, walled, underwater, jump counting,
activation by name with counters, its own positioned sound, pause/unpause.
`initWithRectangle:surfaceId:z:` became `...:isCircle:`. **All of it needs a
full read** - the surface is where most of PS2's level design lives.

## PGEGameAgent

33 changed, 79 new, 24 same. New (calls): hands, clap, shake, beat and shoot
ranges (`checkRanges`, `beatRadius` 30, `beatDotProd` 0.92), device
orientation gating and activation counters (`tryToActivateAgent`),
headphone unplugging (`audioRouteChanged:`), fading (`fadeOutSound:`), sound
priority, reset to initial position, `PauseAgents`/`UnpauseAgents` with
`pauseSound`, `notOn4` (skip on iPhone 4 - no effect on PC).
Changed defaults (**read**, `init` 0x1000214b4): `collideRadius` **10** (the PS1
port uses 20), `speed` 10, gain / wet / dry 1, `activationCounter` 1.
Changed and unread in logic: `update:`, `checkCollisionsWithPlayer`,
`setActive:`, `activate`, `deactivate*`, `findNextPatrolPoint`,
`followPathWithName:`, `playerMovedToPosition:`, `updateSpatializedSound`,
`setIsInShootingRange:`. **None of the PS1 agent code is reusable unread.**

## PGEEnemy

A **different state machine**. PS1's `update:` switched over 13 states; PS2's
switches over **10** (jump table at 0x10001ec30, decoded):

| state | entry | what it does (calls) |
|---|---|---|
| 0 | 0x10001dfb8 | still: `stillSound` |
| 1 | 0x10001e00c | patrol: `patrolSpeed`, `patrolSound` |
| 2 | 0x10001e07c | alerted to player: `awareSound`, `chaseSpeed`, then 3 after a delay |
| 3 | 0x10001e0b8 | chase: `chaseSpeed`, `chaseSound`, steer at the player |
| 4 | 0x10001e138 | alerted to a position (`hasWantedPosition` latch as PS1) |
| 5 | 0x10001e1a8 | go to position: `chaseSound`, `chaseSpeed`, stop when no longer closing |
| 6 | 0x10001e2fc | at the player's last position: `notThereSound`, `OnPlayerLastPosition`, speed 0, next state after the sound |
| 7 | 0x10001e44c | attack: speed 0, `attackSound` |
| 8 | 0x10001e4e0 | alerted to an agent: `awareSound`, `chaseSpeed` |
| 9 | 0x10001e614 | back to the initial position: `patrolSound`, `patrolSpeed`, arrive within 10 |

Plus 10 (waiting for its `introSound`) and -1 (deactivated). New: `introSound`
on activation, a `proximitySound` whose gain follows distance
(`adjustProximitySoundGain`, a `pow` curve), `wasBeaten` / `wasShot` with death
sounds and `OnStab` / `OnShotSoundEnd` / `OnBeatenSoundEnd`, `invincibleWhenMoving`,
`sendToInitialPosition:`. Defaults (`init`): speed 10, chaseSpeed 15,
patrolSpeed 10, shotSound `agony_SPA`, awareSound `hey_SPA`, beatenSound
`stab_and_death`. `alertEnemy:` (calls) knows `to=player` (2), `position` (4),
`agent` (8), fires `OnChase`. **Status: jump table decoded, bodies at calls
depth. Every state needs a full read before porting.**

## PGEFollower (new) - read

See GAME_STRUCTURE.md section 12. `update:` and `checkCollisionsWithPlayer`
read in full; `activate`, `playSound:looping:`, `wasShot`, `wasBeaten`,
`sendAwayFromPlayer:`, `resetAgentWithName:` at calls depth.

## PGEFireworks (new) - calls

Only used by the test map `fireworks.json`. N/A for the game.

## PGECollectible

8 changed, 27 new. New (calls): collect with a hand or by shaking, collect at
the end of the loop unless `ignoreLoop`, skipping (`onDoubleTap` ->
`OnSkip`, or `OnSoundEnd` and the next collectible), `unpausable`,
`collectGain`, `soundPriority`. Changed: `playIntroSound`, `startLoop`,
`playCollectSound` (807 instructions, unread), `collidesWithPlayer`.

## PGESound

`createSpatializedSound` (976 instructions, calls): random pick from
`soundList`, sound priority, **the VoiceOver `blind_` variant**, Papa-picture
variants, fade-in to `finalGain`, `preloadEndMusic` / `PlayEndMusic`, the skip
button, `OnSoundEnd`. Rails in `playerMovedToPosition:`. New
`playSound:looping:`.

## PGEDilemma

6 changed (states renumbered to 101-104). **No shipped PS2 level has a
`Dilemma` object**, and `solveDillemas` is gone. N/A for PS2 unless the audit
of every layer finds one.

## PGEPlayer

22 changed, 72 new, 29 same. Read or at calls depth: hands and actions, shoot,
beat (and stab), throw, clap and the clap counter (read), jump (sound only - PS1's
`startToJump`/`updateJump`/`landFromJump` are gone), underwater / gagging /
drowning (read), wall collision now on the player with a positioned wall sound
and a `global_warning_hitwall` narration, trip with `trip_<prefix>` and a
`global_warning_trip` narration, `PlaySound` (prefix lookup, priority, gain,
loop, dry/wet), the player following a path (ps2_12's train), `update:` at 10 Hz.
**`shuffle` is empty.** Unread in full: `moveForwardOneStep:` (520),
`trip:` (496), `init` (787), `playerDidCollideAWall:`, `update:`, rotation.

## PGEMoveInterpretor

11 changed, 3 same refs, 13 same. Read at calls depth: feet as PS1 but the
2-second re-check is a cancellable `performSelector` in a main-queue block;
`handButtonPressed:` posts `PGE_ACTION_Hand`; `handsClapped:` and `jump:` gated
on hands / jump being allowed and on player state. **`updateFeetView:` and
`updateHandsView:` need a full read** - the alternation rule lives there.

## PGEngine

Changed `loadLevelWithName:` (**read** - win/lose decided here). New: death
narration selection, end music, menu atmosphere fades, camera roll, device
model, stats. Unread: `goBackToHub`, `reloadCurrentLevel`, fades.

## PGEGameProgress, PGEGameTracker, PGEGameParameters

New: skip tickets (calls), fail counts, achievements (`checkAchievementsForlevel:`
unread - 1096 instructions), memories lost, end-sound history, headset detection.
Gone: PS1's skippable-sound history and dilemma status.

## Input view controllers

`PGEStepsViewController` (19 same, 24 changed, 29 new) and its three subclasses,
`PGEShakeDelegate`, `PGEGameplayViewController`: read at calls depth for what
they post (GAME_STRUCTURE.md section 7). Not ported as screens; their
thresholds (shake 1.3 g, orientation 0.05 / 0.45) matter only for deciding what a
key stands for.

## Menus

`PGEViewController`, `PGEWinViewController`, `PGELoseViewController`,
`PGELevelSkipperViewController`, `PGEPopupViewController`,
`PGESettingsViewController`, `AccessibleAllLevelsViewController`: calls depth,
for their strings and the flow between them (GAME_STRUCTURE.md sections 8-10).
