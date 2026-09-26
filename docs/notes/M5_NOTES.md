# M5 recovery notes - ps2_8, 9, 10

From Papa Sangre II's arm64 slice (engine 1_1_013), read in full; addresses
are the implementations.

## What the three levels use

* **ps2_8** (the ice): a `Follower` (the penguin), `SendAgentAwayFromPlayer`
  on the player's clap, two ice floors with `followerTime` 5 and 4 and an
  alert sound, a polar bear (`Monster`), the player's `OnLoad` and
  `OnClapTooMuch`, `PlaySpatialSoundOnAgentWithName`, `PauseAgents`.
* **ps2_9** (the submarine): seven steam vents, each a surface with
  `deadlyTime` / `safeTime` switched on by a trigger just before it and off by
  its own `OnExit`, `OnDeadlyYes` / `OnDeadlyNo` swapping the steam sounds;
  sirens (collectibles) in a line; the trapped man's `OnLeftHand`; a beacon on
  a path; a whisper on rails.
* **ps2_10** (the abyss): `rightHandAction` "throw", lethal floors with
  `OnPebble`, gravel edges with `OnStep`, sounds with `activationCounter` 2
  and 3, the forgetful man on the one safe path.

Everything the surfaces needed was already in from M4; M5 adds the follower,
throwing, and the achievements.

## PGEFollower

* `init` 0x100063f64: smallRadius 30, largeRadius 60, speed 10, chaseSpeed 15,
  state 201, playerPosition (0, 0), agentType 200, inRadius NO, collideRadius
  = smallRadius; observes `SendAgentAwayFromPlayer`.
* `activate` 0x100064628: currentSound "", state_atPreviousFrame -1; with an
  intro sound: `playSound:intro looping:NO`, the state saved and 10 set, and
  when the intro ends (monitor, main-queue block) `superActivate` (the agent's
  own `activate`) and the saved state back.  Without one: the agent's
  `activate`.
* `update:` 0x100064144: the agent's update; active and not paused only:
  `checkCollisionsWithPlayer`, then by state -
  203 (sent away): radius small, speed chaseSpeed, `playSound:scaredSound`,
  `findDirectionToPlayer` and the direction reversed, moveAwayTimer += dt,
  past moveAwayTime -> 201;
  202 (close): `OnProximity` if it was not 202 last tick, radius large, speed 0,
  `playSound:proximitySound`;
  201 (following): radius small, speed chaseSpeed, `playSound:chaseSound`,
  `findDirectionToPlayer`.
  Then state_atPreviousFrame = the state read after the collision check.
* `checkCollisionsWithPlayer` 0x100065058 (float32 squared distance against
  the collide radius squared): 201 and inside -> 202, `FollowerIsClose`; 202
  and outside -> 201, `FollowerIsFar`; 203 and outside -> `FollowerIsFar`
  (every tick).  It keeps no squaredDistanceFromPlayer and sets no collide
  range: no `OnCollide`, never within the hands' reach.
* `playSound:looping:` 0x100064b8c: the same name as `currentSound` -> the
  current sound's duration and nothing else (whether it plays or not);
  otherwise `currentSound` = name, the old sound stopped, `S3DSound:name`
  (exact), placed, reverb, `play:looping`.
* `sendAwayFromPlayer:` 0x100064e3c: a name not its own -> nothing (no name
  means every follower); moveAwayTime = `duration` (10 without); only in state
  202: timer 0, state 203.
* `deactivate` 0x100064ac4: `FollowerIsFar`, then the agent's.
* `resetAgentWithName:` 0x1000644b8: inactive, back to its first position,
  state 201, not dead.
* `wasShot` / `wasBeaten`: with the weapons that meet it (M6/M7).
* `PGE_MESSAGE_FollowerDidDie` -> the tracker's `incrementKills`, the same as
  `AgentDidDie`.

## PGEPlayer throwSomething (0x10002e778)

One step ahead (orientation x pixelsPerStep) and two steps ahead; the floor
under the first if it is lethal, else under the second, fires `OnPebble`
(`-[PGESurface triggerOnPebble]` 0x100044ac4).  The landing sound is
`anySoundContaining:"throw_<that floor's footstepsPrefix>"`, or the level's
hit-wall sound when it has none; `PlayerDidThrow`; the sound goes to the
reverb and plays (position and gain as the playlist has them).  So a pebble
carries 5 to 10 px: the edge is heard only from right beside it.

## Achievements

`checkAchievementsForlevel:`: ps2_8 nbClaps == 0 -> level_8, act2 45; ps2_9
timeElapsed <= 130 -> level_9, act2 60; ps2_10 nbThrows < 21 -> level_10,
act2 75.

## Played

`play_level_8` (claps the penguin away after 2 s close), `play_level_9` (waits
for each vent to blow and go off, then crosses; never waits for a siren
inside a vent), `play_level_10` (routes round the abyss).  All finish on every
seed tried; `tests/test_m5.py`.
