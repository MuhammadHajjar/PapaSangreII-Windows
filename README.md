# Papa Sangre II - Windows and macOS port

A faithful port of *Papa Sangre II* (Somethin' Else, iOS, 2013) to Windows and
macOS:
the audio-only horror sequel, played entirely by listening. All 22 levels, the
combat, the puzzles and the camera; keyboard and controller; screen-reader
output; and the original's own HRTF.

The engine is not a re-imagining. It is the original's logic, recovered from
the arm64 binary and its data: the same maps, the same playlists, the same
walking arithmetic, the same monster and penguin state machines, the same
achievement rules. `docs/BUILD_ORDER.md` is the journal of how each piece was
recovered and every decision taken on the way; `docs/DIVERGENCES.md` lists
everything that had to differ and why; `GAME_STRUCTURE.md` is the recovered
structure of the game itself; `docs/notes/` holds the working notes per
milestone.

## Playing

Download the newest release, unzip it anywhere, and run
`Play Papa Sangre II.exe` from the "Papa Sangre II" folder. There is no
installer. Keep the `_internal` folder beside the exe: it is the game's
libraries. Headphones are a must; the whole game is binaural.

Your progress and settings are written to a `config` folder next to the exe
(or to `%LOCALAPPDATA%\Papa Sangre II` when the game cannot write there, for
example when it was started from inside the zip).

On a Mac, unzip `PapaSangreII-Mac.zip` and open `Play Papa Sangre II.app`
from the "Papa Sangre II" folder (the first time, right-click it and choose
Open: the app is not notarised). Speech is VoiceOver. Progress and settings
are in `~/Library/Application Support/Papa Sangre II/config`.

On Windows the game updates itself. When the main menu opens it looks for a newer
release on GitHub, and the main menu's **Check for updates** asks straight
away. It asks one thing, Update now or Not now. Update now downloads only the
files that changed, then the game closes, puts them in place and starts again
by itself; Not now asks again next time. Your progress is kept. The check at
start can be switched off in Settings. The Mac build does not update itself
yet: download the new zip from the releases page.

## Controls

Keyboard, all rebindable in Settings, Keys:

| | |
|---|---|
| A / D | left foot, right foot. Alternate them to walk; the same foot twice trips you |
| A and D together | jump |
| Q / E | left hand, right hand |
| Q and E together | clap |
| Left / Right arrow | turn |
| Up / Down arrow | hold the phone upright / on its side |
| Ctrl | shake the phone |
| U | unplug the headphones |
| Enter | select, and skip narration when the record player says you can |
| Up / Down arrow | move through a menu; Left / Right change a setting |
| Escape | pause menu, and back out of a menu |
| Page up / Page down | volume |

Controller, rebindable in Settings, Controller buttons:

| | |
|---|---|
| Left / Right trigger | left foot, right foot |
| Left / Right shoulder | left hand, right hand |
| Left stick | turn |
| D-pad up / down | hold the phone upright / on its side. Also up and down in a menu |
| D-pad left / right | volume. Also left and right in a menu |
| Y | shake the phone |
| X | unplug the headphones |
| A | select, and skip narration |
| B, or Back | back |
| Start | pause menu |

Nothing on the keyboard or the pad quits the game: that is Alt+F4 on Windows,
Cmd+Q on the Mac, or Quit in a menu.

## Building

Everything the game runs on is in here: the audio, the Tiled map exports, the
S3D playlists, the level list, the About screen's texts and the HRTF table.
Clone it and build, there is nothing else to find.

    python tools/build_exes.py play   the game, into Run/ (exe, _internal, changelog)
    python tools/build_exes.py        the game and the diagnostic tools
    python tools/pack_release.py      the release zip, into dist/

Each builds for the platform it runs on. On a Mac the game is
`Play Papa Sangre II.app`, the same folder build as a bundle, and the release
zip is `PapaSangreII-Mac.zip`; build it on a Mac and put it on the same
release as the Windows zip.

The game is a folder build (PyInstaller one-dir): the exe starts in under two
seconds, and every sound, level and playlist travels inside the exe as one
encrypted pack, embedded as a Windows resource, so there are no loose game
files and no path long enough to trouble Windows. A Mac executable has no
resources, so there the same pack sits inside the .app as `gamedata.pak`.

The HRTF is not committed in its built form: `build/` is generated. The
committed `tools/embedded_hrtf.dat` is the original IRCAM 1050 set, carved out
of the binary by `tools/extract_hrtf.py`, and `build_exes.py` rebuilds
`build/hrtf/papa_ircam_1050.mhr` from it on a fresh clone with
`vendor/makemhr/makemhr.exe` (from OpenAL Soft's binary release), or on a Mac
`vendor/makemhr-mac/makemhr`. The Mac's OpenAL Soft (`vendor/openal-mac`) and
makemhr are the same 1.25.2, built for Apple silicon by
`tools/build_openal_mac.sh` and committed; run it again to build for an Intel
Mac.

The original's arm64 binary is here too, at `reference/PapaSangreII_arm64`.
Nothing needs it to build or play, but it is the source of truth for the
reverse engineering, and the scripts read it:

    python tools/psdis.py .           the whole-binary disassembly, into tools/dis/
    python tools/classdump.py         the Objective-C classes and ivars
    python tools/fn.py "selector"     one function out of the disassembly

`psdis.py` is worth running before you touch the engine. The port was written
against that disassembly, and the journal and the code cite it by address
throughout, so being able to look one up is the difference between reading
the notes and checking them.

## Running from source

Python 3.12+, `pygame-ce`, `numpy`, `av`, `pyobjc-framework-cocoa` on the
Mac, and OpenAL Soft (`vendor/openal`, `vendor/openal-mac`). Speech goes
through the NVDA controller client when NVDA is running, SAPI 5 otherwise; on
the Mac, through VoiceOver.

    python apps/play.py               the game
    python apps/play.py ps2_14        straight into one level
    python -m pytest                  the tests
    python tools/verify_updater.py    the updater, end to end, offline

## Versions

A version is the day it was made, and "number 2", "number 3" when a day has
more than one: `2026-09-26 number 3`. It lives in `papasangre2/__init__.py`,
`VERSION` and the newest heading of `changelog.txt`, and a test keeps the
three the same. The release tag is the version without spaces,
`2026-09-26-5`. Every release's Windows zip has the same name,
`PapaSangreII-Windows.zip`, so
https://github.com/MuhammadHajjar/PapaSangreII-Windows/releases/latest/download/PapaSangreII-Windows.zip
always downloads the newest, and it is what the game looks for when it
updates itself. The only other zip a release may carry is the Mac's,
`PapaSangreII-Mac.zip`, which the updater never takes for its own. `changelog.txt` ships beside
the exe.

## Layout

    apps/           the executables: the game, and the diagnostic tools
    papasangre2/
        assets/     playlists, Tiled maps, the level list, the nib texts, the data pack
        audio/      OpenAL binding, the S3D engine equivalent, the reverb, the sound bank
        core/       message bus, the run loop, triggers
        input/      rebindable key map and controller map, the foot and hand interpreter
        world/      level, surfaces, the requested lines
        entities/   player, sound agent, collectible, enemy, follower
        save/       progress, the tracker, achievements
        shell/      the menus
        update/     the self-updater
        accessibility/  speech
    requested/      the two sounds made for the port (a knifed penguin, a trip on glass)
    tests/          403 tests, pytest
    tools/          build, packaging, reverse-engineering and audit scripts
    docs/           the journal, the divergences, the notes

## Credits

*Papa Sangre II* was created by **Somethin' Else**, published by Playground,
with the Papa Engine. This port is not affiliated with them.

Windows port by **Muhammad Hajjar**. Thanks to **Seth Gamer** for testing
every level against his memory of the original and reporting what differed;
the port owes much of its accuracy to him.

## Licence

The port's own code is MIT, see `LICENSE`. That covers the code in this
repository and nothing else: the original game's audio, maps, script and
trademarks belong to their owners and are here only so the port can be built
and played.
