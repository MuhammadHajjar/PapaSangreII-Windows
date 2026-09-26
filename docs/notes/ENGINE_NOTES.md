# Papa Sangre II engine - working notes

Raw reading notes, class by class, written while reading `tools/dis/all.txt`
(PS2, engine 1_1_013_2014_07_22_R) against `tools/dis/ps1_all.txt` (PS1 2016
re-release, engine 1_1_020_2015_08_04_R). Addresses are PS2 unless marked PS1.
These feed GAME_STRUCTURE.md and ENGINE_DIFF.md; they are not the final word.

**PS2's engine is OLDER than the one the PS1 port was recovered from** (1.1.013,
July 2014, Xcode 6.3 / iOS 8.3 SDK, versus 1.1.020, Aug 2015, Xcode 7.2). So a
PS1 behaviour can be a later addition PS2 never had, not only the other way round.

## Toolchain notes

* The PS2 binary is a fat armv7+arm64 file; the arm64 slice is extracted to
  `reference/PapaSangreII_arm64` (cryptid 0 - decrypted).
* **psdis.py bug fixed**: the PS1 copy read `reloff`/`nreloc` as the section
  `flags`/`reserved1`, so every GOT and lazy-pointer slot was named from
  indirect-symbol index 0 onwards - wrong names on `ldr xN, [got]` comments
  (e.g. `__NSConcreteStackBlock` shown as `__ZdaPv`). Stub calls were right,
  because `__stubs` genuinely starts at index 0. Both disassemblies are
  regenerated with the fix; the PS1 project's own `tools/dis` is untouched.
* The binary is stripped: block bodies (`dispatch_after`, `dispatch_async`
  callbacks) have no symbol and no IMP entry. `psdis.py blocks` finds every
  `adr`/`adrp+add` into `__text` from a PGE/S3D method and dumps it as
  `BLOCK_0x...` into `dis/blocks.txt` (169 blocks, 32 local helpers).
* `calls.py` resolves every `objc_msgSend` to selector + args, following
  register moves, selector-slot addresses (`SELREF`) and stack spills.

## PGEngine - level transitions (0x100047100 `loadLevelWithName:`)

PS1 special-cased the literal names `win`/`lose`, and no PS1 level used them.
PS2 decides win/lose itself:

```
lockControls
if object[@"prompt"]:            outcome = prompt               (0x1000471c8)
elif level == nil:               outcome = nil
elif ![level.name isEqual: object[name]]:                         (0x100047290)
    playerDidCompleteLevel:(level.name); playerDidUnlockLevel:(object[name])
    outcome = @"win"
else (same level named again):   outcome = @"lose"               (0x100047304)

if outcome == win:  checkAchievementsForlevel:(level.name)
                    post PGE_MESSAGE_PresentWinVC {name: object[name], nextLevel...}
                    tracker sendStatsWithOutcome:@"Won"; updateStatsAndAchievements
elif outcome == lose: deathCause = object[@"deathCause"] ?: @""
                    post PGE_MESSAGE_PresentLoseVC {name, deathCause...}
                    tracker "Lost"; updateStatsAndAchievements
else:               loadLevelWithStringName: object[name]
```

So **every** `LoadLevelWithName:name=<same level>` in the data is a death and
every `LoadLevelWithName:name=<other level>` is a win, and neither loads the
level directly - the Win / Lose view controller does, when the player picks.
The original *has* an after-level screen. `deathCause` is a trigger parameter
(`smoke`, `monster`, `explode`, `run` in the data). See PGEWinViewController /
PGELoseViewController (to read) and `endOfLevelSoundsForDeathCause:`,
`playFailSoundForLevel:deathCause:`, `unplayedEndOfLevelSoundForLevel:deathCause:`.

Level chain from the data (every `LoadLevelWithName` target):
Intro->1->2->3->4->5->5a->6->7->8->9->10->11a->11b->13->12->14->15->16->17->18->18b.
**Nothing loads `ps2_11`** (and the hub list does not list it). It is a cut
level: its own exits go to 11a / 11b.

## PGELevel - loading

* JSON from `levels/<product>/<name>.json`; playlist activated by name.
* **No layer is skipped.** PS1 (1.1.020) skips layers named `ToolBar`
  (3 references to @"ToolBar" in PS1); PS2 has none. Every object in every
  layer is built - including ps2_14's layer called "no longer used".
* Three passes as in PS1: `loadLevelStructure:` (Room), `loadLevelAgents:`
  (everything but Room/Player), `loadPlayer:` (Player); then
  `PGE_MESSAGE_LevelInited`, `setIsInGameplay:YES`, `FadeOutMenuAtmos`,
  `RemoveFullScreenImage`.
* `loadPlayer:` posts `PGE_MESSAGE_SetControlSettingsToDefault`, then
  `MovePlayerToPosition {position}`, then `setCurrentLevel:` on progress.

### createObjectFromDict: (0x10003c35c, 2306 instructions)

Triggers are no longer "any key starting with On". Each type has an explicit
list, parsed by `parseTriggersForNames:propertiesDict:receiver:`:

| type | trigger names |
|---|---|
| every agent (Sound, Collectible, Monster, Follower, Fireworks) | OnRouteChange OnShake OnStep OnStab OnHitWall OnClapTooMuch OnClap OnCollide OnShootMissed OnShoot OnActivate OnDeactivate OnEnteringShootRange OnPathEnd OnRightHand OnLeftHand OnLoad |
| + Fireworks | OnSoundEnd OnExplosion OnGoOff |
| + Collectible | OnCollect OnSkip OnSoundEnd |
| + Sound | OnSkip OnSoundEnd |
| + Monster | OnBeatenSoundEnd OnShotSoundEnd OnBeatMissed OnChase OnPlayerLastPosition |
| + Follower | OnProximity |
| Player | OnShake OnPathEnd OnGagging OnHitWall OnClapTooMuch OnClap OnLoad OnTrip OnShoot OnRightHand OnLeftHand OnBeatMissed OnShootMissed OnEmptyHand |
| Room, Surface | OnStillLimit OnTrip OnDeadlyNo OnDeadlyYes OnExit OnPebble OnActivate OnDeactivate OnStep OnEnter OnJumpTooMuch OnJump OnKill |

`parseTriggersForNames:` (0x10003e77c): for each name N, every property key
equal to N **or beginning `N_`** is a trigger of type N (`OnActivate_2` ->
`OnActivate`: the suffix is how Tiled carries two triggers of one type). Value
split on `|`, each statement through `createDictFromTriggerDescription:`.
Case-sensitive.

Consequences for the shipped data (to verify one by one in the audit):
* A trigger key not in its type's list is **dropped**: Room `OnLeftHand`,
  `OnRightHand`, `OnLoadLevel`; Surface `OnSoundEnd`; Sound `OnXrail`/`OnYrail`
  (capital O).
* Every key with prefix `On` (case-sensitive) is withheld from the setters.
* Every other key: first letter upper-cased, `set<Key>:`; if the object
  responds it is applied via `setValuesForKeysWithDictionary:`, otherwise logged
  red "Cannot find %@ on %@". So `CollideRadius`, `Active`,
  `ActivationCounter`, `Skippable` (capitalised in the data) DO apply;
  `onXrail`, `onYrail`, `onInactiveRail` (lower-case o) are properties, not
  triggers, if the class has the setter (check PGESound); `mutlipleOnEnter`
  (32x) and `footstepsfootstepsPrefix` (7x) are typos that match nothing.
* `active` is applied **after a delay** by a dispatch_after block
  (BLOCK_0x10003e674): `setActive:[active boolValue]` if present, else
  `setActive:NO`. (Delay value: read the dispatch_time argument.)
* Room: `tripBPM`/`runBPM` defaults as PS1 (to confirm the constants);
  `reverbRoomSize` / `reverbDampening` / `reverbVolume` from the Room applied to
  the engine, defaults 1.5 / ? / 1.0 when absent (0x10003d91c, 0x10003da90).
  **Per-level reverb exists in PS2** (PS1 had one reverb for the whole game).
* Room `inactivitySounds` posts `ChangeInactivitySoundList`.
* Surfaces: `initWithRectangle:surfaceId:z:isCircle:` - **circular surfaces**
  (`isCircle`) are new.
* Unnamed agents get `default_agent_%i`.
* An agent is placed with `popAtPosition:` and a `-10.0` constant (height?).

### Trigger statement grammar (createDictFromTriggerDescription:, 0x10003ee18)

Same as PS1 (split `:`, then `;`, then `=`; `count`, `afterCount`,
`afterDelay` consumed) plus **`minDelay` / `maxDelay`** consumed. PS1's
`soundName` -> `PPAE_MESSAGE_CacheSound` side effect is **absent** in PS2.
Missing `=` still logs "Trigger definition error".

### Trigger firing (PGEObjectWithTriggers)

* `triggerWithType:` (0x100028268): case-insensitive type match
  (`uppercaseString` both sides), `count` / `afterCount` as PS1, parameters get
  `senderName` + `position`, name through `messageNameFromString:`,
  `checkIfExists:andHasCorrectParameters:` (debug check). Then:
  * `afterDelay`, or `minDelay`+`maxDelay` (delay = random between them, `rand`)
    -> a `PGEDicoWithDelay {dict, delay}` appended to `dicoWithDelayArray`;
  * otherwise enqueue (`NSPostWhenIdle`) as PS1.
* **Delays are counted down by `-[PGEObjectWithTriggers update:]`**
  (0x100029088), per frame, by the object's own update, then enqueued. PS1 used
  `performSelector:afterDelay:`. Consequences: a delayed trigger only advances
  while its owner is being updated (pause freezes it), and it is **cancelled** by
  `clearDicoWithDelayArray`, which `deactivateAgentWithName:`,
  `-[PGESurface deactivateWithName:]`, `deallocAgentWithName:` and
  `shutDownLevel:` all call.
* `hasTriggerWithType:` is new (used for `OnSkip`).

## PGEMoveInterpretor / PGEPlayer - first observations

* `-[PGEPlayer shuffle]` is **one instruction** (`ret`) in PS2. The "stand still
  for 2 s and hear a shuffle" of PS1 does not exist. `footButtonReleased:`'s
  2 s re-check is `performSelector:updateFeetView: afterDelay:2.0` inside a
  main-queue block, with `cancelPreviousPerformRequests` first (PS1:
  `dispatch_after`, never cancelled).
* `handButtonPressed:` posts `PGE_ACTION_Hand` (PS1: `PGE_ACTION_Shoot` /
  `PGE_ACTION_Beat`).
* `handsClapped:` posts `PGE_ACTION_HandsClapped`, gated on
  `playerCanUseHands` and `playerState`.
* PGEPlayer observes: Jump, Hand, ChangeHandAction, Swim, Trip, HandsClapped,
  DisableClap, EnableClap, InCollideRangeValueChanged,
  PlayerWalkedOnSurfaceWithId, MovePlayerToPosition, PGE_INPUT_Swim, PlaySound,
  ApplyBpmConstraint, Shuffle, ApplyProximityRadiusToPlayer,
  ResetUnderwaterTimer, FollowPathWithName, MakePlayerFollowPathWithName,
  StopFollowingPath, AgentEnteredOrExitedShootRange, StartedSoundWithPriority,
  Vibrate, ShutDownLevel.

## PGEngine init

`maxSpatialGain` 2.0 (PS1 notes say 100 - check PS1's PGEngine init),
reverb dampening 5, volume 1, room size from a literal (read it).
`setProductName:@"PapaSangre2"`, `setPlayListMetaPath:@"meta"`.

## Later in the same session

Everything below was written up properly in GAME_STRUCTURE.md,
docs/ENGINE_DIFFERENCES.md and docs/BUILD_ORDER.md; recorded here only as the
trail of what was checked.

* `-[PGEngine init]` sets `maxSpatialGain` 2.0; PS1's does not (S3DEngine's 100
  stands). `distanceScale` 0.016 (PS1 0.008).
* psdis.py now annotates `adrp` + `ldr sN/dN` literal loads as floats. Before
  that they printed as raw 8-byte values - which is how the PS1 port read two
  constants wrong: Surface default tripBPM (350, not 280) and the reverb room
  size floor (0.01, not 2.2). Both handed to a separate task.
* PS2 embeds the byte-identical IRCAM 1050 HRTF blob (file offset 0x1b8b64).
* Enemy jump table at 0x10001ec30: 10 entries (states 0-9).
* PGEFollower update:/checkCollisionsWithPlayer read in full: 201/202/203 with
  small/large radius hysteresis; 203 flees along the negated direction.
* updateClapCounter: keeps 4, needs >= 3, average gap < 0.3 s -> OnClapTooMuch.
* increaseUnderwaterDuration: gag at > 0.75 x max, drown at > max.
* stab and beat share the beat: branch (0x10002e164).
* throwSomething tests the ground 1 and 2 strides ahead.
* PGEGameAgent init: collideRadius 10 (PS1 20).
* ps2_11: empty playlist, not in the hub, loaded by nothing -> cut.
* Dilemma: no PS2 level has one; solveDillemas is gone.
