# M8 recovery notes - ps2_18, 18b, the end

From Papa Sangre II's arm64 slice (engine 1_1_013), read in full; addresses
are the implementations.

## What the two levels use

* **ps2_18** (Papa): the water pistol (left hand) against three waves of
  everything met so far, one memory per wave (walked into); the camera in
  the right hand once Papa comes - the player's `beat`, `beatSound`
  `18_camera_photo_taken`, Papa's `beatRadius` 45.  Three pictures
  (`picturesTaken`, M7) end it: `papa_defeated` and `level_shutter` count to
  three, then `LoadLevelWithName ps2_18b`.  The "keep moving" floors
  (`stillLimit` 8, 49 for the first) say "keep moving" once you have stood
  still that long; they do not kill.
* **ps2_18b** (the way home): the intro asks you to unplug your headphones;
  `route_change_detector` (`requiresUnplug`) starts the music a second after
  you do and the shaking instruction four seconds after (the intro's own
  timers do it anyway after 20 and 23 s); `instruction_shake`'s
  `OnShake ... afterCount=7` releases `after_shake` on the eighth shake (or
  20 s after the instruction, whatever you do); its end is `ShutDownLevel` and
  `PresentAdiosVC`.

Everything else was already in: the camera is M7's beat, Papa's pictures M7's
`4_papa_` rule, `stillLimit` M4's surface update, `afterCount` M2's triggers,
`DeactivateAgentWithName name=*;type=200` M3's.

## Unplugging

`-[PGEGameAgent audioRouteChanged:]` 0x100023fe8, observing
`PGE_MESSAGE_AudioRouteChanged`: an agent that `requiresUnplug`, active, when
the headset is no longer plugged in, drops `requiresUnplug`, sets the iPod
music player to full volume (the ending is meant to come out of the phone's
speaker) and fires `OnRouteChange`.  Nothing else reads `requiresUnplug`.
`-[PGEViewController audioRouteChanged]` 0x100061848 only shows or hides the
"plug your headphones" picture and dismisses its alert.

The port's U key (decision 1) posts the route change as an unplugging; the
sound stays in your headphones.

## The end

`-[PGEViewController presentAdiosVC]` 0x10005e73c: out of gameplay
(`setIsInGameplay:NO`), and `PGEAdiosViewController` presented.  It is a
`PGEWinViewController` with its own nib: the end-game sky, two clouds, one
button - Main Menu (`quitButtonTouched:` 0x1000635b8: `QuitGameMode`,
`ResetGameplayEngine`, the `back_button` sound).  No text, no achievement,
no next level; `loadLevelWithName:` is never called, so ps2_18b is not marked
completed.  What plays is the end music `after_shake` asked for
(`preloadEndMusic`): `ps2_18b_end_music_loop`.

## Achievements

ps2_18: act3 100 (submitted before the check), and nbBeats == 3 -> level_18.
Every `PlayerDidBeat` counts - the camera's, the one `camera_sound_maker`
posts when you press the right hand with Papa away, and the one
`camera_out_of_range` posts after a picture from too far - so it is three
pictures, all of them hits.

## Played

`play_level_18` (soaks what comes within 110 px, walks into each memory, faces
Papa and takes the picture inside 45 px) and `play_level_18b` (unplugs when
asked, shakes eight times) finish on every seed tried.  `tests/test_m8.py`.
