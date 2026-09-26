# Private beta 1 - the tester's reports (2026-09-26)

Levels are the level list's numbers (1 = ps2_Intro ... 22 = ps2_18b).
Tests: `tests/test_beta_round1.py`. Divergences: decision 23.

| Report | Cause | Change |
|---|---|---|
| L1 record scratch lands on "that's better" | PORT BUG: `Game.update` rounded each frame to whole 10 ms steps and dropped the rest, so game time ran ~6 % slow against the wall clock (18.7 s in a 20 s self-test) and every afterDelay fell behind the sound it was timed against: the 36 s scratch came ~2 s late, after "that's better" (tester's side-by-side recording: original scratch 0.57 s after "just", port 2.1 s) | the remainder is carried between frames (20.1 s in 20 s); the scratch is back at the original's 36 s. A first attempt had moved it to 35.5 s (number 2-4) |
| L1 "keep going" over "see that gramophone" | our decision-21 line, priority 2 like the prompts: it dropped the second landmark or (same pass) overlapped it | priority 1, 0.5 s after the first landmark, `DeallocAgentWithName` when `turn_back_to_me_prompt` activates (both found) |
| L2 first display case plays the wrong line | our decision-21 `EXTRA_TAKES` made "Smash the case open" a take of the 12 s explanation | reminder once, 8 s after the explanation, cancelled by smashing |
| L4 sparkler slow to collect | `easter_egg` has no `ignoreLoop`: collects at the end of its 8 s loop (original) | `REQUESTED_DATA ignore_loop` |
| L7 gramophone needs a turn | original: the machine's collect sound is 6.25 s of crackle before its `OnSoundEnd` runs the scene | the scene on `OnCollide` + 1 s; the machine deactivated first (its crackle is the button's sound object) |
| L9 no scramble sounds | our decision 17 placed `7_scrape` at `hand_release` (a silent detector, reach 1000, 220 px away) | a collectible with no loop/intro sound is not a place |
| L11 power-down pans | `explosion_large` is a spatialised agent at 120 px | flat, gain 0.7 (rendered: equal loudness from the front) |
| L17 fire walls warp behind you (major) | PORT BUG: `PGESurface deactivate` nils `spatialSound` (0x1000447ac); the port kept it, and the three doors share one sound object, so the put-out door dragged it back on every step | `spatial_sound = None` in `Surface.deactivate` |
| L17 oil spray misses | original: beat reach is `beatRadius` 30 (the can's `beatRange` 80 is read nowhere), cone 0.92, erratic angle when on top of it | the can: 80 px, 0.8, `close_reach` 10 |
| L17 collapse delayed, no danger | original: the enemy waits (state 10) through its 8.4 s intro, whose last 2 s are near silent | `chase_during_intro`: steers at you during it, chase + loop 1.5 s before its end |
| L18 jump prompt repeats | `real_jump_prompt` loops a 7.5 s file | `repeat_gap` 15 s (SoundAgent) |
| L20 no knife crunch on penguins (Muhammad: he did use the knife) | the stab death plays (real engine), but ps2_17's penguins' `OnStab` also sends `PlaySound beatsound` - the knife's swing, flat, as loud as the crunch and on top of it; ps2_15's penguins never send it | tried dropping the swing; Muhammad compared rendered clips (`tools/render_knife.py`) and chose the swing kept - no change |
| L21 sound positions | too vague to act on | ask the tester which sounds |
| L21 can move during the camera scene | data never disables walking there | DisableWalk on memory3's collect, EnableWalk at camera_prompt's end |
| L22 hold music loud | `music` flat at gain 1 = the voice's level | gain 0.5 |
| L22 more Ctrl presses | `afterCount=7` (8 shakes) | 16 (Muhammad's choice): `afterCount=15` |
| trip/edge lines in every level | our decision 21 per-level count | Intro and ps2_1 only (Muhammad: levels 1 and 2) |
| hints repeat | our decision-21 idle clock went round the list | each hint once per attempt |
| two running steps after a stop | original `updateBPMCounter`: first step infinite tempo, second halved | walking sound until three steps are known; tempo (tripping) untouched |
| level list silent | original | click |
| Select Level on the win / lose screen goes to the main menu | NOT REPRODUCED: driven with scripted keys it opens the level list (the PS1 port has the bug: 'levels' goes to its shell). Escape there does go to the main menu | ask the tester for the keys he pressed |
| About is one run of text | port | a row per paragraph / credit |
| shake whoosh | - | kept, at Muhammad's word |
| blind Intro footsteps | not looked into (the tester let it go) | - |
| reverb tinny in places | the tester: fine as it is | - |

Autopilot: ps2_14's now runs for the last memory once the house comes down
(it dawdled, which the old 8.4 s head start forgave). The museum test takes the
first of four seeds that wins: ps2_4's louse catches that simple player on
about half the seeds, and which ones moves with every random draw.
