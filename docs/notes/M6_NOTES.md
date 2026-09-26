# M6 recovery notes - ps2_11a, 11b, 13, 12

From Papa Sangre II's arm64 slice (engine 1_1_013), read in full; addresses
are the implementations.

## What the four levels use

Almost everything was in already.  New: the player on a path
(`MakePlayerFollowPathWithName`, `pathSpeed` - ps2_12's train),
`DeallocAgentWithName` (ps2_11b's animals), the `randomAnimal` sounds, the
player's own `OnShoot` (ps2_11b: every squirt alerts the forgotten men), and
data misspellings the content check already names (`DeactiveAgentWithName`,
`DisableClap;afterDelay=2`).

* **ps2_11a**: the hat on the gramophone's man, turned over and put on by hand;
  the fountain gives the water pistol.
* **ps2_11b** (the zoo): 26 forgotten men, the water pistol in the left hand,
  memories in a chain, animals on paths playing `randomAnimal` and freed with
  `DeallocAgentWithName` as the level moves on.
* **ps2_13** (the sunken submarine): the room is not underwater, its floors
  are (`underwaterMaxDuration` 25); bubbles of air (`ResetUnderwaterTimer`,
  breathing pockets), memories in glass cases, an easter egg, the needle and a
  shake at the end.
* **ps2_12** (the pier train): board the waiting train (its `OnCollide`
  starts the ride), shoot the ducks that chase it, memories on the track, the
  needle and a shake at the end.

`PGE_INPUT_Swim` (and `swim:` / `startToSwim`) is never posted and no level
enables swimming: ps2_13's "swimming" is its footsteps only.

## The player on a path

* `makePlayerFollowPathWithName:` 0x100030b40 -> `followPath:name`.
  `followPathWithName:` 0x100030908 only when `senderName` is the player's.
* `followPath:` 0x100030a5c: path = the level's path of that name (nil if
  none); with one, hasPath YES and `findNextPatrolPoint`.  The point count is
  not reset: a second start carries on from where the first left it.
* `findNextPatrolPoint` 0x100030600: target = point[count]; direction to it,
  normalised by its float32 length; squared distance kept; count + 1, and at
  the end `OnPathEnd` (`triggerOnPathEnd` 0x100030bf8) and back to 0 - so the
  trigger fires when the last point becomes the target, and the ride turns
  back to the first point after it.
* `update:` 0x10003024c with hasPath: every other call (`railUpdate`),
  position += direction x pathSpeed x 2 x dt (so pathSpeed px/s); then, as the
  agents do, a new target when the squared distance to this one is 0 or has
  grown; `sendDidMoveMessage`.  Walking does nothing meanwhile (the glide
  branch is not run).
* `stopFollowingPath:` 0x100030760: with no sender or the player's own:
  state 0 (no message), path nil, **orientationVector (0, 0)**, hasPath NO,
  nextStepPosition = position.  `shutDownLevel:` 0x10002f334 calls it with nil,
  so every shutdown stops the player's glide and zeroes the facing.

## Agents freed

`-[PGELevel deallocAgentWithName:]` 0x100042a38: every agent of the name gets
`cancelPreviousPerformRequestsWithTarget:`, `deactivateWithNoCallback` and
`clearDicoWithDelayArray`; the last of them is removed from the agent array,
which held the last reference - so it is freed, and its `dealloc` removes its
observers.

## The zoo's animals

`-[PGESound createSpatializedSound]` 0x1000339e4: when the sound found has a
key containing "randomAnimal" and it is already playing (another animal agent
drew the same one), `OnSoundEnd` fires at once and the agent keeps no sound -
it skips its turn, and its data re-activates it a few seconds later.

## Achievements

ps2_11b nbEnemiesKilled > 20 and nbShoots == nbEnemiesKilled -> level_11b and
`checkSuperBullet`, act2 100; ps2_13 collectiblesCollected == 13 -> level_13,
act3 30; ps2_12 nbEnemiesKilled > 19 and nbShoots == nbEnemiesKilled ->
level_12 and `checkSuperBullet`, act3 15.  ps2_11a has no branch.

## Played

`play_level_11a`, `play_level_11b` (soaks any forgotten man within 70 px),
`play_level_13` (the level's order, the next bubble first when the air runs
low, the egg only with air to spare), `play_level_12` (boards the train,
shoots the ducks).  All finish on every seed tried; `tests/test_m6.py`.
