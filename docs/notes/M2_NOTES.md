# M2 recovery notes - what the Intro needs

Working notes, read from `tools/dis/all.txt` (PS2 arm64). Each item says where.
Folded into GAME_STRUCTURE.md when M2 is done.

## PGEMoveInterpretor (feet, hands, clap, jump)

Same shape as PS1 (bindiff: footButtonPressed:, lockControls, rotate, swim,
enable/disable same); what differs:

* `setSettingsToDefault` (0x100005cf8): walk 1, rotate 1, jump 0, hands 1,
  swim 0, playerState 0; then updateFeetView:"N", updateHandsView:"N".
  `init` calls lockControls (all 0).
* `footButtonReleased:` (0x100006abc): gate playerCanWalk, playerState != 3,
  feetViewDict[foot] != "off". Same-foot trip branch as PS1 (dates compared,
  |interval| < 1.0 -> PGE_ACTION_Trip, skips stamp/step) - unreachable behind
  the "off" gate. Else stamp foot date, post PGE_ACTION_OneStep {lastFoot},
  lastFootButtonPressed = foot, updateFeetView:foot, then a main-queue block
  (0x1000070d4): **cancelPreviousPerformRequests updateFeetView: "N" and "N+1"**,
  then performSelector updateFeetView:"N" after 0.1 and after 2.0. So only the
  LAST step's pair is pending (PS1 used dispatch_after, never cancelled).
* `updateFeetView:` (0x10000612c): !walk -> off/off; arg "2" -> jump/jump;
  arg "0" -> on/on; state 3 -> off/off; else per foot as PS1 (gap clamped 100,
  last foot < 2 s -> off; last foot 2..99 -> post PGE_ACTION_Shuffle and
  lastFootButtonPressed = "N"; -> on). Posts PGE_MESSAGE_UpdateFeetView.
* `playerStateDidChange:` (0x100005d90): if state changed: updateFeetView:"N"
  **with the old state still stored**, then store, then updateHandsView:"N".
  If new state == 3: both foot dates = now.
* `jump:` (0x100007b70): gate state != 3 and playerCanJump. Both foot dates =
  nil, updateFeetView:"2", block: cancel updateFeetView:"0", perform it after
  0.2 s. Post PGE_ACTION_Jump.
* `handButtonPressed:` (0x1000076f4): gate hands && state != 3. Stamp hand
  date, post PGE_ACTION_Hand {Hand: L|R}, cancel+perform updateHandsView:"N"
  after 0.1.
* `handsClapped:` (0x1000079e0): gate hands && state != 3. Both hand dates =
  now, updateHandsView:"2", cancel+perform updateHandsView:"0" after 0.1, post
  PGE_ACTION_HandsClapped (object nil).
* `enableHands` also sets handsAction = 1.

## PGEPlayer

* `init` (0x100029c18): lastPlayerHRTFupdate = +inf, position 0, angle 0,
  orientation (1,0), **pixelsPerStep 5.0**, footstepsGain 0.5, walkBPM 0,
  tripBPM 10000 (setter), runBPM 180, lastFoot "", speed "", beatSound
  "stab_missed", **_pathSpeed 10, stepSpeed 25**, name "player",
  bpm_constaint 0, left/rightHandAction "", wetGain 0.5, dryGain 1.0.
* `moveForwardOneStep:` (0x10002b160):
  1. state == 4 -> return (nothing in PS2 ever sets 4: startToSwim sets 6 and
     is unreachable; dead guard).
  2. proximityRadius != 0 -> post PGE_MESSAGE_AlertAllEnemies
     {to: "position", radius: "%f"} - note: no position in the dict (M3).
  3. cancelPreviousPerformRequests changeState: @0 (cancels trip recovery).
  4. checkStepBPM (always returns YES).
  5. new = position + orientationVector * pixelsPerStep; lastFoot = obj.lastFoot.
  6. level && ![level canPlayerMoveToPosition:new] -> playerDidCollideAWall:
     CGPointZero, return.
  7. nextStepPosition = new, nextStepOrientation = orientation,
     justStepped = YES (never reset anywhere).
  8. speed "" -> "footwalk".
  9. surface = [level surfaceForPosition:next]; if its footstepsPrefix non-nil
     -> player.footstepsPrefix = it. p = footstepsPrefix unless nil/"" (nil).
  10. sound = anySoundWihPrefix "<speed>_<p>" ("footwalk_gravel"), else
      anySoundWihPrefix "footwalk_<p>". (nil p formats as "(null)".)
  11. setupReverbParameters:sound.
  12. surface.footstepsGain > 0 ? that : player.footstepsGain -> sound.gain.
  13. play; updateBPMCounter.
  **Position is not moved here**: `update:` glides it.
* `update:` (0x10003024c, dt 0.1): reloadTimer += dt. hasPath -> rails (M?).
  constantSpeed != 0 -> position += orientation*constantSpeed*dt, send.
  Else if nextStepPosition.x != 0 **and** .y != 0 and |next-pos|^2 > 1:
  position += nextStepOrientation * stepSpeed * dt; sendDidMoveMessage.
  super update: last.
* `updateBPMCounter` (0x10002bd04): as PS1 (keep < 6, sum of the first
  min(n-1,5) gaps / count, 60/avg -> walkBPM); speed = walkBPM < 200 -
  bpm_constaint ? "footwalk" : "footrun".
* `checkStepBPM` (0x10002b980): tripBPM == 0 or runBPM == 0 -> YES. count < 3
  -> changeState:@1, walkBPM = 30. walkBPM >= tripBPM -> state != 3 -> trip:nil.
  walkBPM > runBPM -> state != 2 -> post PlayerStartsToRun, changeState:@2.
  else state != 1 -> changeState:@1. Always YES.
  (PS1 differs: the count<3 arm here also sets walkBPM 30; the run arm here
  does not.)
* `setTripBPM:` (0x10002bfb0): only if different and bpm_constaint == 0:
  store, resetBPM.
* `applyBPMConstraint:` value -> setTripBPM: value, bpm_constaint = value.
* `changeState:` state = n; n == 0 -> walkBPM 0, walkTimes cleared; post
  PlayerStateDidChange with getStateDictionnary.
* `trip:` (0x10002ccc4): resetBPM; changeState:@3; post PlayerDidTrip (nil);
  cancel+perform changeState:@0 after 2.0; sound = anySoundContaining
  "trip_<footstepsPrefix>" (red log if none); gain = footstepsGain,
  unspatialised, play; OnTrip; [level surfaceForPosition:position]
  triggerOnTrip; tripTimes = old+1 (saved); if old <= 1 and level number
  ("ps2_<n>" split "_", [1].intValue; "Intro" -> 0) <= 9 and level's
  highestPriorityPlayingSound <= 0: stop voiceOverSound if playing,
  voiceOverPriority = 1, voiceOverSound = anySoundContaining
  "global_warning_trip", unspatialised, play, wetGain 0. Then dispatch_after
  0.3 s -> post PGE_MESSAGE_AlertAllEnemies {to: "position"} (block at
  0x10002d338: objects [@"position"], keys [@"to"] - no coordinates).
* `playerDidCollideAWall:` (0x10002ab8c): sound = S3DSound:level.hitWallSound
  if set, else anySoundWihPrefix "hitwall"; sendToReverb, wetGain 0.5; point
  == CGPointZero -> unspatialised, else spatialised at point; play:NO;
  OnHitWall; wallTimes = old+1; if old <= 1 and level number <= 9 and
  highestPriority <= 0: if voiceOverSound playing and its key does not
  contain "global_warning_hitwall" -> return **without vibrating**; if it
  does contain it -> stop it; voiceOverSound = anySoundContaining
  "global_warning_hitwall", unspatialised, priority 1, play, wetGain 0.
  Vibrate (0xfff) - rumble on a pad (decision 6).
* `rotatePlayerFromAngle:` angle += delta, single wrap; computeNewOrientation
  (also engine setHeadOrientation:); post PlayerDidRotateToFixedAngle only if
  |lastPlayerHRTFupdate - angle| > 0.0872665 (5 degrees), then store.
  Same for rotatePlayerToFixedRotation:.
* `setStartAngle:` posts PGE_ACTION_RotatePlayerToFixedAngle degrees*pi/180.
* `sendDidMoveMessage`: engine setHeadPosition:, post PlayerMovedToPosition.
* `clap:` (0x10002db44): disableClap -> return. clapSound -> anySoundWihPrefix,
  unspatialised, setupReverbParameters, play. OnClap (even with no sound).
  updateClapCounter.
* `handsActionMessageReceived:` (0x10002df34): reloadTimer <= reloadTime ->
  ignore (then reloadTimer = 0 at the end on the handled path). L ->
  action = leftHandAction, OnLeftHand; R -> rightHandAction, OnRightHand.
  shoot / stab|beat / throw; else if objectsInRange empty: empty hand sound
  (emptyLeft/RightHandSound), OnEmptyHand, play unspatialised with reverb.
* `playSound:` (0x10002f4f8, PGE_MESSAGE_PlaySound): soundName nil -> nothing.
  soundPriority > 0: if <= level.highestPriorityPlayingSound -> nothing; else
  post StartedSoundWithPriority {name: player, priority}. Stop voiceOverSound
  if playing. voiceOverPriority = priority param (or 1 if absent).
  voiceOverSound = anySoundWihPrefix soundName (whole string - no '&' split,
  no "_a" rule: those were PS1). Unspatialised. gain param -> gain. loop =
  soundName.boolValue (bug: reads soundName, not loop). dryGain param ->
  **setWetGain:** (bug) else setDryGain:player.dryGain. wetGain param ->
  setWetGain: else player.wetGain. sendToReverb = wetGain > 0; autoReverbMix
  YES, min/max reverb distance 1/100, wet send 0.05/0.3. play:loop.
* `startedSoundWithPriority:` priority >= voiceOverPriority -> stop
  voiceOverSound if playing.
* `setupReverbParameters:` sound.dryGain = player.dryGain, wetGain =
  player.wetGain, sendToReverb = wetGain > 0, autoReverbMix YES, 1/100,
  0.05/0.3.
* `levelInitedMessageReceived:` currentLevel = obj; OnLoad.

## PGELevel

* `init` (0x100039ee4): **floorArray = [self]** - the level is its own first
  surface, so `surfaceForPosition:` always finds at least the room inside the
  room rectangle; inactivityTime +inf; lastActivity now; update timer 0.05;
  isInfinite NO; hitWallSound "hitwall"; playerIsOnSurface NO; stepTriggerOdds
  100; setActive:YES. A new PGELevel is alloc'd per load (loadLevelWithString
  Name: / reloadCurrentLevel), so this holds for every level.
* `update` ticks floorArray (self included) with update:0.05 **and then calls
  [self update:0.05] again** - the room's PGESurface update: runs twice a tick,
  so the room's delayed triggers count down at double speed. (Reproduced; the
  Intro room has no delayed triggers.)
* `surfaceForPosition:` (0x10003fedc): among floorArray in order, rect contains
  point (CGRectContainsPoint: half-open), z strictly greater than the best so
  far (ties: first wins), active, and for circles sqrt(dx^2+dy^2) (float) <
  w/2 from the rect centre.
* `canPlayerMoveToPosition:` (0x1000402f4): outside room rect -> NO. current =
  the last floor with playerIsOnSurface; target = surfaceForPosition:. Same
  surfaceId -> YES; else current.isWalled or target.isWalled -> NO; else YES.
* `computePlayerMovedToPosition:justStepped:` (0x1000406dc): current/target as
  above. Same id: justStepped -> target triggerOnStep; prefix = target prefix
  if any. Different (or no current): current setPlayerIsOnSurface:NO +
  triggerOnExit; if !target.playerIsOnSurface -> target triggerOnEnter:js;
  target playerIsOnSurface YES; prefix; tripBPM > 0 -> player setTripBPM:;
  runBPM > 0 -> setRunBPM:; player shuffleSound = target's or ""; underwater
  copy (+ reset duration when not). Then player footstepsPrefix = prefix, post
  PlayerWalkedOnSurfaceWithId {id, name}.
* `playerMovedToPosition:` -> compute with the dict's justStepped;
  `surfaceWasActivated` -> compute with the player's position, justStepped NO.

## PGESurface

* init: gain 1, stepTriggerOdds 100, activationCounter 1, playerIsOnSurface
  NO, deathGain 1, **_active YES**. Observes Activate/DeactivateAgentWithName,
  SetLethalForSurfaceWithName, PlayerMovedToPosition, FollowerIsClose/Far,
  PGE_ACTION_Jump, Pause/UnpauseAgents.
* createObjectFromDict: setActive:YES before properties, then the `active`
  key applies immediately through KVC. (Agents instead get the 0.05 s block:
  setActive:[active boolValue], or setActive:NO when the key is absent.)
* `setActive:` stores; YES -> post SurfaceWasActivated, checkLethal, sound ->
  initialiseSound.
* `activateWithName:` name match -> activationCounter -= 1; <= 0 ->
  setActive:YES, stillTimer 0, OnActivate.
* `deactivateWithName:` name match, or "*" (with optional type) -> clean ->
  clearDicoWithDelayArray; deactivate (setActive:NO, stop spatialSound,
  OnDeactivate). playerIsOnSurface is left as it was.
* `triggerOnEnter:js` entered && !multipleOnEnter -> nothing; else entered YES,
  playerIsOnSurface YES, OnEnter, js -> triggerOnStep, checkLethal.
* `triggerOnExit` exited && !multipleOnEnter -> nothing; else exited YES,
  playerIsOnSurface NO, OnExit.
* `triggerOnStep` arc4random() % 100 < stepTriggerOdds -> OnStep; stillTimer 0;
  checkLethal. `triggerOnTrip` -> OnTrip.
* `update:` !active -> return (no super); paused -> followerTimer 0, return;
  follower / deadly / still / lethalAfter timers (not in the Intro); super
  update: last.

## PGEGameAgent

* init: collideRadius 10, speed 10, wetGain 1, dryGain 1, gain 1, beatDotProd
  0.92, name "unnamed agent", beatRadius 30; ~25 observers.
* `setActive:b` (0x1000227bc): old = _active; _active = b. old NO and b YES ->
  dispatch_async(main){activate}. old YES and b NO -> deactivate. Always
  sendActivityChangedMessage.
* `activate`: forceStopCallback NO, setActive:YES (no-op), playlist =
  engine playListWithName:playlistName, OnActivate, checkCollisionsWithPlayer.
* `activateAgentWithName:` name match -> tryToActivateAgent: activationCounter
  -= 1; requiresLandscape/PortraitPicture -> wait for the orientation;
  else counter <= 0 -> setActive:YES, checkCollisionsWithPlayer, checkRanges.
* `deactivateAgentWithName:` name match or "*" (type must equal agentType
  when given) -> setActive:NO; clean -> clearDicoWithDelayArray.
* `deactivate` = deactivateWithNoCallback (forceStopCallback YES, stop sound,
  sound nil, _active NO, ..., InCollideRangeValueChanged NO if in range) +
  OnDeactivate.
* `update:` super first (delays), paused -> return; path following while
  active or followPathWhenInactive; speed > 0 moves along orientation.
* `playerMovedToPosition:` store player pos; active: pos != (0,0) ->
  checkCollisionsWithPlayer; updateSpatializedSound; checkRanges;
  justStepped -> OnStep.

## PGESound

* init: gain 1, finalGain 1, observes PGE_INPUT_DoubleTap (onDoubleTap),
  unpausable.
* `createSpatializedSound` (0x10003341c): no sounds -> return. name =
  sounds[rand() % count]. soundPriority >= 1: <= level.highestPriority ->
  **triggerOnSoundEnd at once** (the line is dropped); else post
  StartedSoundWithPriority {name, priority}. preloadEndMusic -> post
  PreloadEndMusic. Stop the old sound. "18_SPEECH_papa_picture_retreat_"
  prefix -> picturesTaken variant. **VoiceOver running -> anySoundWihPrefix
  "blind_<name>"** first; else/none -> S3DSound:name, else anySoundWihPrefix
  name. ("randomAnimal" key special case.) setupReverbParameters, spatialized
  -> updateSpatializedSound, gain, play:looping. fadeInTime > 0 and gain !=
  finalGain -> step = (finalGain-gain)*0.01/fadeInTime per monitor call,
  needsFadeIn. add3DSoundMonitor: forceStopCallback -> nothing; end music at
  duration-0.2 when preloadEndMusic; fade step until within 0.01; non-looping
  at end -> dispatch_async triggerOnSoundEnd. skippable && active -> post
  ShowSkipButton.
* **The monitor pump is every 10 ms** (`-[S3DEngineDispatcher dispatch_pump]`,
  dispatch_after 9,999,999 ns, re-armed after each fire).
* `onDoubleTap` (PGE_INPUT_DoubleTap): skippable && active && playing ->
  RemoveSkipButton, stop, OnSkip if it has one, else triggerOnSoundEnd.
* `triggerOnSoundEnd`: skippable -> RemoveSkipButton; OnSoundEnd.
* `deactivate`: skippable -> RemoveSkipButton; super deactivate.
* `playerMovedToPosition:` rails: onXrail -> x follows the player's x motion,
  onYrail -> y (while active, or inactive with onInactiveRail); then super.

## PGEStepsViewController

* `showSkipButton`: shows the button; **VoiceOver running -> 1.0 s later
  playUiSoundWithName "skipButtonAppeared"** (the skip ping).
* `skipButtonPressed:` posts PGE_INPUT_DoubleTap, hides the button, UI sound
  "click_button".

## PGEngine and the view controllers (the shell)

* `loadLevelWithName:` (0x100047100): lockControls; name == current -> lose
  (PresentLoseVC {name, deathCause}); other -> win (playerDidCompleteLevel:,
  playerDidUnlockLevel:, checkAchievementsForlevel:, PresentWinVC {nextLevel}).
* `loadLevelWithStringName:` / `reloadCurrentLevel`: clearLevelData, a new
  PGELevel (so the level is floorArray[0] every time).
* `actuallyLoadDataFromJsonFile`: 2 s gap when the playlist changes; load;
  post LevelInited; 5 s later FadeOutMenuAtmos + RemoveFullScreenImage.
* UI sounds (`playUiSoundWithName:`, ps2_menu playlist): none within 0.1 s of
  the last, none over itself. click_button on choosing, back_button on
  leaving, skipButtonAppeared (the ping), papa_engine_splash_UOS (splash),
  start_level_button (only the sighted hub selector), whoosh (unused).
* Menu atmosphere: `playMenuAtmos` = menu_death_atmos looping, fadeIn 3 s to
  0.5; `FadeOutMenuAtmos` -> fadeOut 2 s, stop, then the menu playlist is
  deactivated 0.1 s later. End music: `<level>_end_music_loop` (fallback
  ps2_2's) at 0.4 as the menu atmos.
* Level list (VoiceOver): "Play Level %i: %@" / "Level %i: %@; locked", then
  "Main menu" (back_button). Choosing a row posts
  InitGameplayEngineAndLaunchLevelWithName - no UI sound.
* Select Level: if no headset, alert "Wear headphones" / "You must use
  headphones to play Papa Sangre II, otherwise you will not be able to locate
  objects using 3D sound. Please connect headphones before continuing."
  (Cancel / OK).
* Nib labels: main menu Select Level / Settings / Achievements / More games /
  About; pause Continue game / Restart Level / Settings / Quit game + the
  objective text; win Continue / Play this again / Main Menu (+ success text,
  achievement); lose "You are still dead" / Play this again / Main Menu /
  Skip this level / Talk to Papa; settings Gyro / Swipe / Tilt / Back.
* About (CreditsViewController.nib): the credits text and the headphones /
  how-to-play notice; the splash's accessibility label "Developed by
  Somethin' Else".

## The Intro's narration (transcribed, faster-whisper medium.en)

* ps2_skip_tuto (sighted) and blind_INTRO_SPEECH_bird_flock are 0.57 s of
  silence: only VoiceOver players hear the skip explanation, and they are not
  told "don't open them" (their training_0 has no "close your eyes").
* blind_ps2_skip_tuto: "When you hear this sound, you can skip what's
  currently being played by pressing the skip button at the bottom center of
  the screen. To pause, press the button at the top center. Your feet are at
  the bottom left and right, while your hands are at the top left and right.
  If your feet or hands don't make a noise, they are temporarily disabled. If
  you are using swipe mode, swipe anywhere on the screen to change direction."
* INTRO_intro_UOS is a 29 s scene with no speech.
* Full list: build/transcripts/intro.medium.en.json; the lines that name a
  control are in papasangre2/tutorial.py.

## Reverb (S3DSound / S3DEngine / csl::Freeverb)

* Graph, `-[S3DSound setupSpatialized]` 0x10012d000: SpatialSource ->
  Spatializer(kBinaural) -> gainControl (Mixer, 2 ch). sendToReverb NO:
  gainControl -> masterMixer, dryGain unused. YES: FanOut(gainControl, 2) ->
  dryMixer at dryGain, wetMixer at wetGain. setupPlain is the same with a
  Panner. Ends with setPlanarInternalInternal.
* `-[S3DSound setPlanarInternalInternal]` 0x10012a3fc: needs a spatialSource;
  normalizeToHeadPosition -> source position; planarNeedsUpdating = NO; if
  autoReverbMix: d = |planar - headPosition| (3D, world px); t = 0 if d < min,
  1 if d > max, else (d-min)/(max-min); wet = minWet + t*(maxWet-minWet);
  setDryGain: 1-wet; setWetGain: wet. Called from setPlanar: (via dispatch)
  and from the dispatcher for every tracked sound when the head moves.
* setDryGain:/setWetGain: store, and only if sendToReverb re-scale the
  FanOut's input on the dry / wet mixer. setSendToReverb:/setAutoReverbMix:
  just store.
* `-[PGEPlayer setupReverbParameters:]` 0x10002a934 and
  `-[PGEGameAgent setupReverbParameters:]` 0x100021df4: dryGain, wetGain,
  sendToReverb = wetGain > 0, autoReverbMix YES, 1 / 100, 0.05 / 0.3. The
  agent's also copies gain, stream and unloadOnStop (port fixed: gain was
  not copied).
* `-[S3DEngine init]`: masterMixer <- dryMixer; unless `disableReverb`
  (called by `-[PGEngine init]` only when `+isOldDevice`),
  Stereoverb(wetMixer) at room 2.2, dampening 2, wet 0, dry 0 -> masterMixer,
  no extra gain. PGEngine then sets 2.1 / 5 / 1.
* Stereoverb 0x100116510: Splitter -> two identical Freeverbs -> Joiner.
  Freeverb 0x100115fec/0x100115cec: 6 combs (1116 1188 1277 1356 1422 1491),
  3 allpasses (556 441 341, feedback 0.5), fixedgain 0.015. setRoomSize
  0x100116970: size*0.28+0.3. setDampening 0x1001169fc: d*0.01*0.4.
  setWetLevel 0x100116a88: as given. nextBuffer 0x100116314: the loop in
  freeverb.py, then out*wet + in*dry (vDSP).
