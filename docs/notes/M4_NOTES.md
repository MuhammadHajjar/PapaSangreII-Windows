# M4 recovery notes - ps2_5, 5a, 6, 7

From Papa Sangre II's arm64 slice (engine 1_1_013), read in full; addresses
are the implementations.

## What the four levels use

* **ps2_5** (the pools): `isLethal` surfaces with a looping `sound` and a
  `deathSound`, `OnKill -> ShutDownLevel`; glass cases (hand collection), a
  mind louse, `OnEnteringShootRange` on a `detector` (face the bubbles).
* **ps2_5a** ("Hometime"): `requiresLandscapePicture` / `requiresPortraitPicture`,
  `Vibrate`, `collectWithShake`, sounds on rails (`onXrail`, `onYrail`,
  `onInactiveRail`), a gramophone `button` with hand triggers, `PlayEndMusic`.
* **ps2_6** (the pier): `ChangeHandAction:leftHand=shoot`, `shootSound`
  "gunshot", `reloadTime` 1, ducks (`Monster`) with `OnShoot`, one with
  `activationCounter` 10, `patrolSpeed`, paths, `OnPathEnd`, `EnableClap`.
* **ps2_7** (the burning house): fire walls (lethal, positioned sounds,
  `unpausable` on two), ceiling traps switched by
  `SetLethalForSurfaceWithName`, `PauseAgents` / `UnpauseAgents`, holes you
  climb out of by hand (`activationCounter` 7 and 9 on surfaces), cats on
  paths, and the smoke: two `isUnderwater` surfaces, `underwaterMaxDuration`
  20, `gaggingSound`, `drowningSound`, `OnGagging`.

## PGESurface, the lethal half

* `initWithRectangle:surfaceId:z:isCircle:` 0x100043114 also observes
  `SetLethalForSurfaceWithName`, `PlayerMovedToPosition`, `FollowerIsClose` /
  `FollowerIsFar`, `PGE_ACTION_Jump`, `PauseAgents`, `UnpauseAgents`, and sets
  deathGain 1.  `-[PGELevel init]` is not this initialiser, so the room has
  none of them.
* `setActive:` 0x1000447d8: YES posts `SurfaceWasActivated`, `checkLethal`, and
  with a `sound` `initialiseSound`.
* `deactivate` 0x100044750: `setActive:NO`, its sound stopped if playing,
  `OnDeactivate`.
* `triggerOnEnter:` 0x1000448cc ends with `checkLethal` (after the early
  return for a second entry).
* `setIsLethal:` 0x100044af4 -> `checkLethal` 0x100044b10: lethal and the
  player on it -> `kill`.
* `kill` 0x100044b74: once (`killed`); `OnKill`; with `followerNotDeadly`
  that is all (and `killed` stays NO); else DisableWalk, DisableHands,
  `killed`, its sound stopped, `playDeathSound`.
* `playDeathSound` 0x100044cd0: no level name or no `deathSound` -> nothing
  more; `anySoundWihPrefix:deathSound` into `lethalSound`; none -> ShutDownLevel
  and `restartLevel` at once; else flat, gain `deathGain`, `play:NO`, and at its
  end (monitor `pos >= dur`, main-queue block) ShutDownLevel + `restartLevel`.
* `restartLevel` 0x100045120: `LoadLevelWithName {name: levelName,
  deathCause: deathCause or "surface"}`.
* `setSound:` 0x100043dcc: a main-queue block, `initialiseSound` if active.
* `initialiseSound` 0x100043f3c: `notOn4` and an "iPhone 4" -> nothing;
  `S3DSound:sound` from the level's playlist, gain = the surface's gain,
  spatialised, planar at the rectangle's centre; if active `play:YES` and
  `computeNewPlayerPosition:lastPlayerPos`.  No stop of the old one.
* `playerMovedToPosition:` 0x1000441a0 stores `lastPlayerPos`;
  `computeNewPlayerPosition:` 0x1000442a4 clamps the player's point into the
  rectangle inset by 15 px (x: `ox+15 > px ? ox+15 : min(ox+15+(w-30), px)`,
  y the same), float32, `setPlanar:`; `sendDidMoveMessage` is empty.
* `update:` 0x1000437fc: inactive -> nothing; paused -> followerTimer 0.  The
  follower alert (on it, follower close, followerTime > 0: alert sound flat
  once while the timer is 0, timer += dt; else past 0.2 s the timer resets
  and the alert stops); timer past followerTime and not killed -> alert
  stopped, `kill`.  The deadly/safe cycle when both times are set: lethal ->
  deadlyTimer += dt, past deadlyTime -> both timers 0, `setIsLethal:NO`,
  `OnDeadlyNo`; else safeTimer += dt, past safeTime -> `setIsLethal:YES`,
  `OnDeadlyYes`.  On it: stillTimer += dt; `OnStillLimit` once as it passes
  stillLimit (`t > limit && t < limit + dt`); past a non-zero lethalAfter and
  not killed -> `kill`.  Then the delays.
* `setSafeTime:` 0x100043d78: safeTimer = safeTime - 0.1 (float32).
* `pauseAgents` 0x100045708 / `unpauseAgents` 0x10004580c: nothing when
  unpausable; paused YES/NO, followerTimer 0; pause: the alert stopped, the
  sound and the death sound paused if playing; unpause: the alert stopped, the
  sound and the death sound `resume`.
* `playerJumped` / `updateJump` (OnJump, OnJumpTooMuch over the last five
  jump times): M7, when a level jumps.

## S3DSound details this needed

* `pause` 0x10012eb08 / `resume` 0x10012eb1c are `setPlayRate:0` / `1`.  A
  paused sound still reports `playing`; `resume` does not restart one that
  was stopped.
* `setupPlain` 0x10012c6b4: a two-channel file goes straight to the output;
  a one-channel file through a `csl::Panner` at position 0, whose law
  (0x100117c94) is `left = in * (0.5 - pos/2)`, `right = in * (0.5 + pos/2)` -
  half level in each ear.

## PGEPlayer

* `increaseUnderwaterDuration:` 0x10002fd38, from every level tick with
  0.05: underwater only; duration += dt; past 0.75 x max and under max and not
  gagging -> `OnGagging`, `startGagging`; past max and not drowning -> `drown`,
  drowning YES.
* `resetUnderwaterDuration:` 0x10002fe5c: 0 and `stopGagging`.  Called by
  `computePlayerMovedToPosition:justStepped:` when the player steps onto a
  floor that is not underwater, and by `PGE_MESSAGE_ResetUnderwaterTimer`.
* `startGagging` 0x10002fe88: `S3DSound:gaggingSound`, flat, `play:YES`.
  `stopGagging` 0x10002ff68: stop, nil, gagging NO.
* `drown` 0x10002ffb8: stopGagging; DisableWalk, DisableHands, ShutDownLevel;
  `anySoundContaining:drowningSound`, flat, `play:NO`; at its end
  `restartLevel:@"drown"` 0x100030c10 (LoadLevelWithName with the playlist's
  name and that cause - the smoke's own deathCause is never used).
* `pause` / `resume` 0x10002fc04 / 0x10002fc6c: the gagging sound paused, and
  resumed only while the duration is between 0.75 x max and max.
* No defaults: underwaterMaxDuration 0, no gagging / drowning / shoot sound.
* `handsActionMessageReceived:` 0x10002df34, the weapons: after the reload
  check and the hand trigger, "shoot" -> `shoot:`; "stab" and "beat" ->
  `beat:`; "throw" -> `throwSomething` (M5/M7); then nothing else.
* `shoot:` 0x10002eb10: shotTouchedATarget NO; `anySoundContaining:shootSound`
  flat, send to reverb, wet 0.5, `play`; the player's `OnShoot`;
  `nearestAgentInShootingRange` 0x10002ee4c (least squaredDistanceFromPlayer,
  strictly); every agent in `agentsInShootingRange` -> `wasShot` if it is the
  nearest, else `wasMissed`, then the nearest leaves the set; an empty set ->
  the player's `OnShootMissed`; `PlayerDidShoot`.
* `agentEnteredOrExitedShootRange:` 0x10002eff4 keeps the set from each
  agent's `isInShootingRange`.  Only `checkRanges` writes that (and needs
  collideRadius > 0), and an inactive agent never posts its leaving, so a
  deactivated agent can stay in the set.

## PGEGameAgent / PGEEnemy shot at

* `-[PGEGameAgent wasShot]` 0x100025444: totalKills + 1 in the save (any
  agent), `triggerOnShoot` (OnShoot if active).  `wasMissed` 0x1000254d8 ->
  `OnShootMissed` if active.
* `-[PGEEnemy wasShot]` 0x100020070: dead -> nothing; invincibleWhenMoving and
  not still -> nothing; super; invincible -> stop there; speed 0;
  `anySoundWihPrefix:shotSound` spatialised at its position, `play:NO`; its
  sound stopped and cleared; dead YES; `AgentDidDie`; at the shot sound's end
  (or at once if it has no duration) `onShotSoundEnd` (0x100020b60,
  `OnShotSoundEnd`) and `deactivate`.
* `-[PGEGameProgress setTotalKills:]` 0x100036efc reports kill25, kil100 (sic)
  and kill500 as n/25, n/100, n/500 x 100.

## Holding the phone

* `tryToActivateAgent` 0x100022d54: counter - 1; with either requirement it
  observes `PGE_INPUT_RotateDevice` (`userDidRotateDevice:`) and posts
  `PGE_INPUT_CheckDeviceRotation`, and stops there.
* `userDidRotateDevice:` 0x100022ef8: "portrait" and requiresPortraitPicture,
  or "landscape" and requiresLandscapePicture -> the requirement cleared for
  good and `tryToActivateAgent` again 0.8 s later (dispatch_after 800,000,000).
* `deactivateAgentWithName:` stops observing when a requirement is set.
* `-[PGEStepsAndSwipeViewController checkDeviceRotation:]` 0x10000bcd0 sets
  `needToCheckRotation` (never cleared); `accelerometer:didAccelerate:`
  0x10000b678 then posts RotateDevice portrait or landscape on every sample
  the phone is held upright or on its side (filtered x/y against 0.05 and
  0.45), nothing when it lies flat.

## PGECollectible, corrected

* `playCollectSound` 0x10001b37c with `cancelWetGain` calls `[self
  setWetGain:0]` - the collectible's own wet gain - and then `[self
  setupReverbParameters]` (0x100021d8c, which is `setupReverbParameters:
  self.sound`), so the collect sound plays dry.  M2 had read it as the
  sound's wet gain, overwritten; Muhammad heard reverb on the exits that the
  original never had.  The doors without it (ps2_8, ps2_9 the submarine,
  ps2_16, and the cut ps2_11) keep the room's reverb.

## Level clock and achievements

* `-[PGELevel update]` ends with `[player increaseUnderwaterDuration:0.05]`,
  `[self update:0.05]`, and `PGEGameTracker.timeElapsed += 0.05`.
* `checkAchievementsForlevel:`: ps2_5 timeElapsed <= 90 -> level_5, act1 100;
  ps2_5a no branch; ps2_6 nbShoots < 22 and nbShoots == nbEnemiesKilled ->
  level_6 and `checkSuperBullet`, act2 15; ps2_7 timeElapsed <= 140 ->
  level_7, act2 30.  `checkSuperBullet` 0x1000384e8: 33 x level_6 + 33 x
  level_12 + 34 x level_11b.
* `-[PGEWinViewController initAchievementView]` 0x100061fc0: the title, and the
  achieved description with the `success_achievement_on` badge or the
  unachieved one with `success_achievement_off`.

## Played

`papasangre2/autopilot.py`: `play_level_5` (routes round the live pools,
turning to what the level waits to be faced), `play_level_5a`, `play_level_6`
(shoots the nearest live duck), `play_level_7` (follows the cats, climbs out
of both holes).  All four finish on every seed tried; `tests/test_m4.py`.
