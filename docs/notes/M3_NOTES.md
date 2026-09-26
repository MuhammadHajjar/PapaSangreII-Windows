# M3 recovery notes - the museum (ps2_1 to ps2_4)

Everything below is from Papa Sangre II's arm64 slice (engine 1_1_013),
read in full; addresses are the implementations.  PGEEnemy differs from the
first game's (update: 38 % similar), so none of it comes from the PS1 port.

## What the four levels use

One new agent type, `Monster` -> `PGEEnemy` (1 or 2 per level).  Messages:
`AlertAllEnemies:to=position` (clap, trip, noisy floors, taking a memory from
a case), `SendAgentToInitialPosition` (no name), `PauseAgents` /
`UnpauseAgents` (ps2_1's warning), `FollowPathWithName` (ps2_4), and the
death: louse OnCollide -> `fail_sound` -> `ShutDownLevel` + louse_death ->
`LoadLevelWithName` of the same level.  No hand actions (`leftHandAction` and
`rightHandAction` are empty), so `wasShot` / `wasBeaten` are not reachable
here (they come with the air rifle, M4).

## PGEEnemy

* `init` 0x10001dc40: pathCurrentPoint 0, speed 10, chaseSpeed 15,
  patrolSpeed 10, state 0, playerPosition (0,0), agentType 200, shotSound
  agony_SPA, awareSound hey_SPA, beatenSound stab_and_death; observes
  AlertAllEnemies -> alertEnemy:, SendAgentToInitialPosition ->
  sendToInitialPosition:; squaredDistanceFromGoal inf, delayedAlerted NO,
  waitingForIntroToFinish NO.
* `update:` 0x10001debc: [super update:] (delays, path, movement), then only
  if active, not dead, not paused: checkCollisionsWithPlayer; x20 = state;
  jump table 0x10001ec30 for 0..9 (anything above: nothing); at the end
  state_atPreviousFrame = x20 and, with a proximity sound and a non-zero
  radius, adjustProximitySoundGain.  s8 = dt until a branch overwrites it.
  * 0: playSound: stillSound; setSpeed 0.
  * 1: setSpeed patrolSpeed; playSound:looping: patrolSound YES.
  * 2: prev 2 -> nothing; prev 3 -> setState 3; else (0x10001ea84)
    waitingForIntroToFinish -> delayedAlerted YES; else d = awareSound once,
    setSpeed chaseSpeed, perform changeStateTo:@3 after d, d > 0 ->
    changeStateTo:@10, chasingTime 0.
  * 3: setSpeed chaseSpeed; playSound: chaseSound; findDirectionToPlayer;
    chasingTime += dt.
  * 4: hasWantedPosition -> findDirectionToPlayer, changeStateTo:@5; else d =
    awareSound once, perform changeStateTo:@5 after d, d > 0 -> @10,
    findDirectionToPlayer.  Both then (0x10001e8dc): wantedPosition =
    playerPosition; prev != 4 -> squaredDistanceFromGoal = |pos-wanted|^2,
    chasingTime 0, hasWantedPosition YES, setSpeed chaseSpeed.
  * 5: playSound: chaseSound; setSpeed chaseSpeed; sq = |pos-wanted|^2 (double,
    to float); sq > goal (b.le skips, so NaN changes too) -> changeStateTo:@6;
    goal = sq; chasingTime += dt.
  * 6: prev != 6: d = notThereSound once; perform changeStateTo:@0 after d;
    perform triggerWithType:@"OnPlayerLastPosition" after d; d > 0 -> @10.
    Always: setSpeed 0; hasWantedPosition NO.
  * 7: setSpeed 0; attackSound -> playSound:; chasingTime += dt.
  * 8: prev != 8: d = awareSound once; setSpeed chaseSpeed; perform @5 after
    d; d > 0 -> @10; chasingTime 0.
  * 9: prev != 9: goal inf; findDirectionTo: initialPosition.  Always:
    playSound: patrolSound; setSpeed patrolSpeed; sq = |pos-initial|^2;
    `fcmp sq, goal; fccmp sq, 10, #8, le; b.pl skip`: sq > goal (or NaN) or
    sq < 10 -> changeStateTo:@0; goal = sq.
* `changeStateTo:` 0x10001ec58: setState: n.intValue.  Nothing cancels the
  performSelector requests (PGELevel shutDownLevel: cancels only its floors').
* `activate` 0x10001edcc: currentSound ""; state_atPreviousFrame -1;
  introSound -> waitingForIntroToFinish YES, playSound:looping: intro NO,
  __block saved = state, setState 10, add3DSoundMonitor on [self sound]: at
  current >= duration, stop and dispatch_async { activateDelayedSound;
  superActivate; setState saved }.  No intro: waiting NO, [super activate].
* `activateDelayedSound` 0x10001f2a4: waiting NO; delayedAlerted -> NO,
  awareSound once, chaseSpeed, perform @3 after d, d > 0 -> @10, chasingTime 0.
  The block then sets the saved state, so the next update's still/patrol
  sound cuts the aware sound off; the chase still starts when d runs out.
* `deactivate` 0x10001ecc0: stop the sound if playing; setState -1; [super
  deactivate]; state_atPreviousFrame -1.
* `alertEnemy:` 0x10001f800: not active, or state 2 or 3 -> nothing.  radius:
  |playerPosition - position|^2 (floats) > r^2 -> withinRadius NO, nothing.
  name present and not ours -> nothing.  to player -> @2 + OnChase; position
  -> @4 + OnChase; agent -> @8, position -> wantedPosition =
  CGPointFromString, findDirectionTo:, OnChase.
* `sendToInitialPosition:` 0x10001fd3c: a name that is not ours -> nothing;
  otherwise (no name = every enemy) changeStateTo:@9.
* `collidesWithPlayer` 0x10001f654: state 7 or dead -> nothing; setSpeed 0;
  @7; [super collidesWithPlayer] (OnCollide).
* `findDirectionTo:` 0x10001f740: ov = (target - pos) / |target - pos| - **no
  zero guard** (0/0 = NaN); goal = n^2; returns n / chaseSpeed.
  `-[PGEGameAgent findDirectionToPlayer]` 0x100025590 has the guard (n == 0
  -> ov 0) and returns n / chaseSpeed.
* `playSound:` = playSound:looping: YES.  `playSound:looping:` 0x100020bd8:
  same name as currentSound and still playing -> its duration; lazy
  playlist; nil name -> 0; stop the sound; sound = anySoundWihPrefix:;
  updateSpatializedSound; currentSound = name; setupReverbParameters; play:
  loop; return duration.
* `isStill` 0x10001fff8: state 0, 6, 0x68 (104 - set by nothing) or 10.
* `setProximitySound:` 0x10001f43c: stop the old; S3DSound: name from the
  playlist; unspatialised, gain 0, `setupReverbParameters` (on self.sound, not
  on it), play: YES.  `adjustProximitySoundGain` 0x10001f554: sq < r^2 ->
  gain = (1 - sq/r^2)^4 (pow), else 0.
* `activateEnemy:` - posted by nothing in PS2.  `sendDidMoveMessage` -
  checkRanges only.  `dealloc` - deactivateWithNoCallback, stop the proximity
  sound, remove the two observers.

## PGEGameAgent pieces

* `pauseAgents` 0x1000272e4: unpausable -> nothing; paused YES;
  soundWasPlaying = sound.playing; sound pause (rate 0); pauseSound ->
  pauseS3D = anySoundWihPrefix:, spatialised, planar = sound.planar, play:
  YES.  `unpauseAgents` 0x1000274e8: paused NO; active and soundWasPlaying
  -> [sound play] (= play:NO: from the top, not looping); pauseS3D playing
  -> stop.  The playlist hands out one shared S3DSound per name, so a louse
  whose pause sound is its still sound gets that sound stopped on unpause
  (its update restarts it).
* `pause` / `resume` (the game's pause) keep soundWasPaused /
  pauseSoundWasPaused; the port's Game.pause holds every bank sound.
* `followPathWithName:` 0x100025de8: senderName must be ours; already on a
  path of that name -> nothing; else path by name; set -> hasPath, state 1,
  findNextPatrolPoint.
* `S3DSound play` 0x10012eb30 = play:NO; `pause`/`resume` = setPlayRate 0/1.

## PGELevel shutDownLevel: (0x100041da8), the part M2 lacked

After the agents and floors and the inactivity sound: inactivitySoundsArray
removeAllObjects, then post PGE_MESSAGE_DisableHands, DisableWalk,
DisableRotation.

## The death (loadLevelWithName: 0x100047100, presentLoseVC: 0x10005e430)

* Same level: PresentLoseVC {nextLevel: name, deathCause: cause or ""},
  sendStats (N/A), updateStatsAndAchievements.
* presentLoseVC: presents PGELoseViewController (viewDidLoad -> checkFails ->
  `failedLevel:` = "<level>_failed" integer + 1; skip button - removed,
  decision 4), then `playFailSoundForLevel:` n = the "_" part intValue.
* `playFailSoundForLevel:deathCause:` 0x100048e90: name =
  `unplayedEndOfLevelSoundForLevel:deathCause:`; n <= 5 and no name ->
  memoriesLost += 1, >= 26 -> 1, name = lost_memory_%i_UOS; else a name ->
  justPlayedLevelEndSound:.  Then ps2_menu S3DSound:name, atmosVoiceOver,
  atmosSounds addObject, gain 1, play:NO, add3DSoundEndCallback: ->
  dispatch_after 0.7 s -> playMenuDeathAtmos.
* `unplayedEndOfLevelSoundForLevel:deathCause:` 0x100049398: the list from
  `endOfLevelSoundsForDeathCause:` (ps2_menu sounds whose key has the prefix
  "<level>_fail_<cause>", or "<level>_fail" without a cause, in playlist
  order) minus those `hasPlayedLevelEndSound:` ("<sound>_played"); the first
  left; none left and n >= 5 -> a random played one; else nil.
* `playMenuDeathAtmos` = playAtmosWithName: + fadeInMenuAtmos:3.
  `playAtmosWithName:` 0x1000485f8 ignores its argument: stopMenuAtmos (stop
  and forget every atmos sound), menu_death_atmos into atmosSounds, gain 0.5,
  play looping; fadeInMenuAtmos: then ramps from 0.
* Narrations exist for ps2_1 (a, b, c), 6, 7, 8, 9, 10, 11b, 12 to 18; none
  for 2 to 5, which lose a memory straight away.

## Achievements

* `PGEGameTracker` 0x100016af4 (singleton): LevelInited -> levelWasLoaded:
  -> resetTracker:(name != last name) - every counter to 0, attempt 1 or +1;
  PlayerMovedToPosition -> nbSteps +1; PlayerDidCollideAWall, PlayerDidTrip,
  PGE_ACTION_HandsClapped, RotatePlayerFromAngle (|rad| * 180 / pi),
  PlayerDidShoot, PlayerDidThrow, AgentDidDie, PlayerDidBeat,
  FollowerDidDie, AlertAllEnemies.  incrementCollectibles from
  -[PGECollectible collect] and endOfLoop.
* `checkAchievementsForlevel:` 0x100037284 (on a win only), per level:
  ps2_1 nbTrips == 0 -> level_1; ps2_2 nbClaps > 9 -> level_2; ps2_3
  collectiblesCollected == 5 -> level_3; ps2_4 nbClaps == 0 -> level_4; the
  act1 percentage (20/40/60/80) every time.  Tail: synchronize.
* `setPercentage:forAchievementWithName:` 0x100038c94: Game Center, and at
  100 a bool under the achievement's own id.  `achievementCompleted:`: Game
  Center, else that bool.
* `updateStatsAndAchievements` (win and loss): totalSteps += nbSteps.
  `setTotalSteps:`: 10000steps = total / 10000, 1000000steps = total /
  84390 (sic).  `setMemoriesLost:`: memoryLost = n / 24.
* Texts: the hub list's per-level `achievement` {id, title,
  achievedDescription, unachievedDescription}; the win screen
  (`initAchievementView`) shows the title and the achieved or unachieved
  description.  The act/steps/kill/memory/superBullet achievements have no
  text in the app - their titles were on Game Center.
