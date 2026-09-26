# M7 recovery notes - ps2_14, 15, 16, 17

From Papa Sangre II's arm64 slice (engine 1_1_013), read in full; addresses
are the implementations.

## What the four levels use

* **ps2_14** (the burning house): the extinguisher is a `beat` hand
  (`beatSound` 14_extinguisher_short); each fire door has a speed-0 `Monster`
  whose `OnStab` puts it out; one door and the fireworks want the extinguisher
  shaken first (`OnShake` on a sound agent, five shakes through an
  `activationCounter` of 5, the extinguisher's own shake sound - an agent, so
  shakes quicker than it play it once), then
  faced (`OnEnteringShootRange`); the oil cans are beaten too (`OnBeatMissed`
  plays "aim at the oil"); the rescue of Mr. Fletcher is optional (the seventh
  collectible, `achievement_collectible`).
* **ps2_15** (the ice): the knife in the right hand (`beat`); eight polar bears
  that can be knifed only while still (`invincibleWhenMoving`), each kill
  alerting the rest to where it happened; penguins (`activationCounter` 5 and
  7) that are knifed or clapped away; the last music under the ice, broken by
  jumping three times quickly (`OnJumpTooMuch`).
* **ps2_16** (the glass floor): nothing new - the glass (`surface1`, whose
  `OnStep` alerts every hog) is switched off while the thunder plays.
* **ps2_17** (the broken memories): ps2_10's abyss, ps2_6's ducks, ps2_9's
  steam, ps2_8's penguins and ps2_15's bears in one; the right hand becomes a
  knife in the submarine.

## The beat

* `-[PGEPlayer handsActionMessageReceived:]` 0x10002df34: `stab` and `beat`
  both call `beat:`.
* `beat:` 0x10002f0d4: `shotTouchedATarget` NO; post `PGE_MESSAGE_PlayerDidBeat`
  (the tracker's `nbBeats`); then on the next pass of the main queue: if nothing
  was touched and `beatSound` is set, that sound (`S3DSound:`, the exact name)
  plays flat, `sendToReverb` YES, `wetGain` 0.5, and the player fires
  `OnBeatMissed` (a missing sound still fires it; no `beatSound`, neither).
* `-[PGEGameAgent playerDidBeat:]` 0x100024f30: an active agent in its beating
  range gets `wasBeaten` and sets the player's `shotTouchedATarget` YES; every
  other active agent gets `wasMissed` (so `OnShootMissed`) and fires
  `OnBeatMissed`.
* `checkRanges` 0x10002487c: in the shooting cone (cos > `beatDotProd`, within
  `shootRange`) and nearer than `beatRadius` (init 30) -> beating range, through
  `setIsInBeatingRange:` 0x100025124, which plays `beatRangeSound` at gain 0.5,
  not looping, not placed, on the way in only, for an active, living agent.
* `beatRange` (data on ps2_14, 15, 17) is a property nothing reads.
* `-[PGEGameAgent wasBeaten]` 0x1000253c8: `totalKills` + 1.

## Beaten

* `-[PGEEnemy wasBeaten]` 0x100020474: dead, or `invincibleWhenMoving` and not
  `isStill`: nothing (there is no `invincible` check, unlike `wasShot`).  Else
  super, `OnStab`, speed 0, its sound stops; the beaten sound becomes its sound
  (for a name beginning `4_papa_`, the level's `picturesTaken` + 1 and the sound
  is `beatenSound` followed by that count - ps2_18); spatialised,
  `setupReverbParameters`, placed where it stands, played once; dead,
  `AgentDidDie`; when it ends `onBeatenSoundEnd` (`OnBeatenSoundEnd`) then
  `deactivate`, or `deactivate` at once for a zero duration.
* `-[PGEFollower wasBeaten]` 0x100065734 / `wasShot` 0x100065300: dead: nothing.
  Super (`totalKills`; a shot also fires `OnShoot`), speed 0, its sound stops,
  `FollowerDidDie`, `OnStab` for a beating, `-[PGEGameTracker
  incrementPenguinKills]` 0x100017328 (`nbPenguinsKilled` and `nbEnemiesKilled`
  both + 1 - with `FollowerDidDie`'s own `incrementKills`, a penguin is two
  enemies).  Its beaten / shot sound, spatialised, at the planar position of
  its own sound (placed before playing for a beating, after for a shot); dead;
  deactivates when it ends.  No sound name: deactivates at once, not dead.
* `resetAgentWithName:` sets `dead` NO (the port had a separate flag).
* `-[PGEFollower update:]` has no dead check: a dying penguin keeps following
  until its sound ends.

## Shaken

`-[PGEGameAgent shakeDetected:]` 0x10002411c, observing `PGE_ACTION_Shake`:
not while the level is paused; active, and `squaredDistanceFromPlayer` below
`collideRadius` squared -> `OnShake`.  The squared distance is the one the last
collision check kept.  Collectibles still do their own `shakeMessageReceived:`.

## Jumping

* `-[PGEMoveInterpretor jump:]` (M2) posts `PGE_ACTION_Jump` when jumping is
  enabled (`EnableJump`, ps2_15's music).
* `-[PGEPlayer jump]` 0x10002da08: the `jumpSound`, flat, with the reverb.
* `-[PGESurface playerJumped]` 0x100045414 (every floor, and `-[PGELevel init]`
  observes it for the room too): only the floor the player is on - `OnJump`,
  then `updateJump` 0x10004547c: the time added, the oldest dropped while five
  or more are kept; with three or more, the gaps summed and divided by the
  count (not the gaps) under 0.5 -> `OnJumpTooMuch` and the list emptied.  The
  player's clap counter over again, with 0.5 for 0.3.

## Papa's pictures (ps2_18, found here)

`-[PGESound createSpatializedSound]` 0x10003371c: a sound whose name begins
`18_SPEECH_papa_picture_retreat_` plays the one for the pictures taken so far
(name + count, by prefix) - no VoiceOver take, no animal rule.

## Achievements

`checkAchievementsForlevel:`: the act percentage is submitted whether or not
the level's achievement is earned.  ps2_14 collectibles == 7 -> level_14, act3
45; ps2_15 nbPenguinsKilled > 9 -> level_15, act3 60; ps2_16 enemiesAlerted < 5
-> level_16, act3 75; ps2_17 timeElapsed not above 240 -> level_17, act3 90.

## An enemy sent home from home (ps2_15)

`sendToInitialPosition:` 0x10001fd3c without a name sends every enemy home;
state 9 always starts with `findDirectionTo:` 0x10001f740 on the initial
position, which has no zero guard.  An enemy standing exactly at home gets a
direction of NaN, and the next update moves it (speed is the patrol speed
until state 0 sets it to 0) to NaN: it can no longer collide, be faced or be
knifed.  In ps2_15, bears 3, 5, 6 and 8 send everyone home 5 s after searching
where a kill was, while the bear activated after the previous kill usually
still stands at home - and `forgetfulman9` needs all eight kills.  Played
faithfully, the level could not be finished (autopilot, every seed).
Decision 16 (Muhammad, 2026-09-25): an enemy sent where it already stands
gets no direction and stays - every enemy, so ps2_16's hogs too.

## Played

`play_level_14` (fires put out from a free spot beside them, shakes, faces,
the hall), `play_level_15` (still bears only, away from moving ones and from
each kill, a clap for a close penguin, three quick jumps at the music),
`play_level_16` (walks only in the thunder, with time for the step to land;
smashes as a thunder starts with no hog within 70 px; slips away from the
spot, clear of the hogs' ways there and home), `play_level_17` (shoots what
comes, never stops in a vent, waits for a siren outside the vents) - all win
on the 8 seeds tried.  `tests/test_m7.py`.
