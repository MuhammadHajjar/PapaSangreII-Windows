"""Papa Sangre II - the port.

Runs the recovered engine on the original's own maps, sounds and scripts.
Opens with the Papa Engine sting, then a spoken main menu.  Up and down move,
Enter chooses, Escape goes back, left and right change a setting.  Escape
during play pauses; nothing on the keyboard quits the game but Quit.

Controls (all rebindable in Settings, or in config/keys.json):

  A / D          left foot / right foot - alternate them to walk
  A and D        together: jump
  Q / E          left hand / right hand
  Q and E        together: clap
  Left / Right   turn
  Up / Down      hold the phone upright / on its side
  Ctrl           shake the phone
  U              unplug the headphones
  Enter          skip, when the record player says you can
  Page up/down   volume
  Escape         pause

Built as ``Play Papa Sangre II.exe`` on Windows and ``Play Papa Sangre II.app``
on the Mac.  Headphones on.
"""

from __future__ import annotations

import math
import os
import sys
import time

if __package__ in (None, ''):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame                                                     # noqa: E402

from papasangre2 import __version__                               # noqa: E402
from papasangre2.assets import pack                               # noqa: E402
from papasangre2.assets.nib import text_views                     # noqa: E402
from papasangre2.audio.bank import SoundBank                      # noqa: E402
from papasangre2.audio.engine import AudioEngine                  # noqa: E402
from papasangre2.core.game import Game                            # noqa: E402
from papasangre2.input.chords import ChordResolver                # noqa: E402
from papasangre2.input.interpreter import LEFT, RIGHT             # noqa: E402
from papasangre2.input.keymap import Action, KeyMap               # noqa: E402
from papasangre2.input.padmap import PadMap, button_label          # noqa: E402
from papasangre2.input.pygame_source import PygameInput           # noqa: E402
from papasangre2.save import GameProgress                          # noqa: E402
from papasangre2.shell import (PAD_REBINDABLE, REBINDABLE,         # noqa: E402
                               about_menu, achievement_text, achievements_menu,
                               adios_menu, keys_menu, level_complete_menu,
                               level_failed_menu, level_menu, main_menu,
                               pad_menu, pause_menu, settings_menu,
                               update_offer_menu, update_ready_menu)
from papasangre2.tutorial import pc_lines, pc_about               # noqa: E402
from papasangre2.update import updater, version as build_version  # noqa: E402
from papasangre2.update.service import UpdateService               # noqa: E402
from papasangre2.util import console, host, paths, sysaudio       # noqa: E402
from papasangre2.util.settings import Settings                     # noqa: E402

FRAME_HZ = 100


class App:
    """Everything one sitting needs, passed around as one thing."""

    def __init__(self, rep) -> None:
        self.rep = rep
        self.base = paths.game_bundle()
        self.engine = AudioEngine()
        self.engine.open()
        if os.environ.get('PS2_SILENT'):
            # verification runs only (tools/verify_updater.py --frozen): the
            # game started again after an update, heard by nobody
            from papasangre2.audio import openal as OA
            self.engine.al.alListenerf(OA.AL_GAIN, 0.0)
        self.keymap = KeyMap.load()
        self.padmap = PadMap.load()
        self.settings = Settings()
        self.progress = GameProgress()
        self.src = PygameInput(self.keymap, title='Papa Sangre II', padmap=self.padmap)
        self.clock = pygame.time.Clock()
        self.chords = ChordResolver()
        menu_bank = SoundBank(self.engine, self.base)
        menu_bank.load_playlist('ps2_menu')

        def bank(name):
            b = SoundBank(self.engine, self.base)
            b.load_playlist(name)
            return b
        self.game = Game(self.base, self.progress, self.settings, bank,
                         menu_bank=menu_bank, say=self.say, rumble=self.src.pad.rumble,
                         engine=self.engine,
                         tutorial_lines=pc_lines(self.keymap, self.padmap,
                                                 lambda: self.src.pad.connected))
        self.titles = {n: e.title for n, e in self.game.hub.items()}
        #: the GitHub updater's worker; PS2_UPDATE_API points it elsewhere
        #: (tools/verify_updater.py, never a player)
        self.updates = UpdateService(os.environ.get('PS2_UPDATE_API') or None)
        self.update_started = False       # the start-up check, once a sitting
        self.update_offered = False
        self.restarting = False           # quitting so an update can go in

    def say(self, text: str) -> None:
        self.rep.say(text)

    # ------------------------------------------------------------ helpers
    def ui(self, name: str) -> None:
        self.game.play_ui_sound(name)

    def pump(self) -> list:
        """One frame: input, the menu audio's clock."""
        events = self.src.poll()
        dt = self.clock.tick(FRAME_HZ) / 1000.0
        g = self.game
        if g.level is None or g.level.paused_game or g.finished:
            g.menu_update(dt)
        return events


# ---------------------------------------------------------------- menus
def rebind(app, action, label) -> None:
    rep, keymap = app.rep, app.keymap
    rep.say(f'Press the key you want for {label}. Press escape to leave it as it is.')
    key = app.src.capture_key(10.0)
    if not key:
        rep.say(f'{label} is still {keymap.describe(action)}.')
        return
    taken = [a for a in keymap.actions_for(key) if a != action]
    keymap.bind(action, [key])
    try:
        keymap.save()
    except OSError:
        pass
    said = f'{label} is now {key}.'
    if taken:
        said += ' That key is also ' + ', '.join(dict(REBINDABLE).get(a, a) for a in taken) + '.'
    rep.say(said)
    app.game.tutorial_lines = pc_lines(app.keymap, app.padmap,
                                       lambda: app.src.pad.connected)


def rebind_button(app, action, label) -> None:
    rep, padmap = app.rep, app.padmap
    if not app.src.pad.connected:
        rep.say('No controller is connected, so there is nothing to press.')
        return
    rep.say(f'Press the controller button you want for {label}. '
            'Press escape on the keyboard to leave it as it is.')
    button = app.src.capture_button(10.0)
    if not button:
        rep.say(f'{label} is still {padmap.describe(action)}.')
        return
    padmap.bind(action, [button])
    try:
        padmap.save()
    except OSError:
        pass
    rep.say(f'{label} is now {button_label(button)}.')
    app.game.tutorial_lines = pc_lines(app.keymap, app.padmap,
                                       lambda: app.src.pad.connected)


def run_menu(app, menu, poll=None):
    """Speak a menu and walk through it.  Returns ``(action, value)``.

    ``poll()``, asked every frame, may end it with an ``(action, value)`` of
    its own - how the main menu hears that an update was found meanwhile."""
    rep = app.rep
    rep.show(f'  [{menu.title}]')
    rep.say(menu.announce())
    while True:
        if app.src.quit_requested:
            return ('quit', None)
        if poll is not None:
            outside = poll()
            if outside is not None:
                return outside
        chose_already = False
        for action, phase, _stamp in app.pump():
            if phase != 'down':
                continue
            if action == Action.MENU_UP.value:
                rep.say(menu.move(-1))
            elif action == Action.MENU_DOWN.value:
                rep.say(menu.move(+1))
            elif action in (Action.MENU_LEFT.value, Action.MENU_RIGHT.value):
                said = menu.adjust_current(-1 if action == Action.MENU_LEFT.value else +1)
                if said:
                    rep.say(said)
            elif action in (Action.CONFIRM.value, Action.SKIP.value):
                if chose_already:
                    continue
                chose_already = True
                item = menu.current
                chosen = menu.choose()
                if chosen is None:
                    continue
                if chosen[0] == 'blocked':
                    rep.say('That level is locked.')
                    continue
                if chosen[0] == 'toggled':
                    rep.say(chosen[1].label)
                    continue
                if chosen[0] == 'info':
                    rep.say(item.label if item is not None else '')
                    continue
                if chosen[0] == 'explain':
                    rep.say(chosen[1] or (item.label if item is not None else ''))
                    continue
                if chosen[0] == 'adjust':
                    continue
                if chosen[0] == 'rebind':
                    rebind(app, chosen[1], dict(REBINDABLE).get(chosen[1], chosen[1]))
                    menu.items = keys_menu(app.keymap).items
                    rep.say(menu.speak_current())
                    continue
                if chosen[0] == 'reset_keys':
                    app.keymap.reset()
                    app.keymap.save()
                    menu.items = keys_menu(app.keymap).items
                    rep.say('Every key is back to its default.')
                    continue
                if chosen[0] == 'rebind_button':
                    rebind_button(app, chosen[1], dict(PAD_REBINDABLE).get(chosen[1], chosen[1]))
                    menu.items = pad_menu(app.padmap).items
                    rep.say(menu.speak_current())
                    continue
                if chosen[0] == 'reset_buttons':
                    app.padmap.reset()
                    try:
                        app.padmap.save()
                    except OSError:
                        pass
                    menu.items = pad_menu(app.padmap).items
                    rep.say('Every controller button is back to its default.')
                    continue
                sound = item.ui_sound() if item is not None else None
                if sound:
                    app.ui(sound)
                return chosen
            elif action == Action.CANCEL.value:
                if not menu.cancellable:
                    continue
                sound = menu.cancel.ui_sound()
                if sound:
                    app.ui(sound)
                return (menu.cancel.action, menu.cancel.value)


def settings_loop(app) -> str:
    while True:
        act, _ = run_menu(app, settings_menu(app.settings, app.engine))
        if act == 'keys':
            run_menu(app, keys_menu(app.keymap))
        elif act == 'buttons':
            run_menu(app, pad_menu(app.padmap))
        else:
            return act


def about(app) -> None:
    """`CreditsViewController`: the headphones notice, the credits, then a PC
    word - a row at a time, up and down to read."""
    texts = []
    nib = os.path.join(app.base, 'CreditsViewController.nib')
    if pack.isfile(nib):
        try:
            texts = text_views(nib)
        except Exception:                                        # noqa: BLE001
            texts = []
    # the notice first, as it reads on screen
    run_menu(app, about_menu(list(reversed(texts)), pc_about(app.keymap), __version__))


# ---------------------------------------------------------------- updates
PROGRESS_EVERY = 3.0          # seconds between spoken download percentages


def _wait(app, seconds: float) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end and not app.src.quit_requested:
        app.pump()


def start_update_check(app) -> bool:
    """Once a sitting, when the main menu first opens: offer an update that
    was downloaded and put off, else look quietly for a new one.  Returns True
    when the game should quit so an update can go in."""
    if app.update_started:
        return False
    app.update_started = True
    allowed, _why = updater.can_update()
    if not allowed:
        return False
    try:
        updater.clean_up_staging()
        waiting, tag, remove = updater.pending_update()
    except OSError:
        waiting, tag, remove = None, '', []
    if waiting is not None:
        return ask_restart(app, waiting, remove,
                           f'Version {build_version.text(tag)} is downloaded and ready. '
                           'Updating closes the game, puts it in place and starts it again. '
                           'Your progress is kept.')
    if app.settings.check_updates:
        app.updates.check()
    return False


def poll_quiet_check(app):
    """The main menu's poll: a quiet check that found something worth offering."""
    if app.update_offered or not app.updates.busy:
        return None
    result = app.updates.poll()
    if result is None or result[0] != 'checked':
        return None
    _kind, release, _problem = result
    if release is None:
        return None
    return ('update_found', release)


def offer_update(app, release, asked: bool = False) -> bool:
    """Tell the player about a newer version and install it if they say so.
    Returns True when the game should quit so the update can go in."""
    app.update_offered = True
    allowed, why = updater.can_update()
    message = (f'Version {build_version.text(release.tag)} is available. '
               f'You have {build_version.text()}.')
    changes = ' '.join(release.changes().split())
    if len(changes) > 600:
        changes = changes[:600].rsplit(' ', 1)[0] + '...'
    if changes:
        message += ' What is new: ' + changes
    if not allowed:
        app.say(message + ' It cannot update itself here: ' + why + '.')
        return False
    act, _ = run_menu(app, update_offer_menu(message))
    if act == 'yes':
        return download_update(app, release)
    if act != 'quit':
        app.say('Not now. It will be offered again the next time you start the game.')
    return False


def download_update(app, release) -> bool:
    """The download: percentages every few seconds, Escape or Enter stops it."""
    rep, svc = app.rep, app.updates
    if not svc.install(release):
        app.say('An update is already being worked on. One moment.')
        return False
    rep.show('  [Downloading update]')
    app.say(f'Downloading version {build_version.text(release.tag)}. '
            'Press Escape to stop.')
    said_at, said = time.perf_counter(), -1
    stopping = False
    while True:
        if app.src.quit_requested:
            svc.cancel()
            return False
        for action, phase, _stamp in app.pump():
            if phase == 'down' and action in (Action.CANCEL.value, Action.CONFIRM.value,
                                              Action.PAUSE.value) and not stopping:
                stopping = True
                svc.cancel()
                app.say('Stopping the download.')
        result = svc.poll()
        if result is not None:
            break
        now = time.perf_counter()
        if not stopping and now - said_at >= PROGRESS_EVERY and svc.percent != said:
            said_at, said = now, svc.percent
            app.say(f'{said} percent')
    _kind, plan, problem = result
    if problem:
        app.say(f'The update did not work: {problem}.')
        return False
    if plan is None:
        app.say('Download stopped.' if stopping else 'Nothing needed downloading.')
        return False
    return install_update(app, plan.staging, plan.remove)


def ask_restart(app, staging, remove, message: str) -> bool:
    """An update downloaded earlier: Update now or Not now."""
    act, _ = run_menu(app, update_ready_menu(message))
    if act != 'restart':
        if act != 'quit':
            app.say('Not now. It will be offered again the next time you start the game.')
        return False
    return install_update(app, staging, remove)


def install_update(app, staging, remove) -> bool:
    """Hand the downloaded files over and quit; the game comes back updated."""
    try:
        updater.apply(staging, remove)
    except updater.UpdateError as exc:
        app.say(f'The update could not start: {exc}.')
        return False
    app.restarting = True
    return True


def check_now(app) -> bool:
    """Check for updates, from the main menu: answers either way."""
    allowed, why = updater.can_update()
    if not allowed:
        app.say(f'This copy cannot update itself: {why}. It is version {build_version.text()}.')
        return False
    svc = app.updates
    if not svc.busy:
        svc.check()
    app.say('Checking for updates.')
    result = None
    while result is None:
        if app.src.quit_requested:
            return False
        for action, phase, _stamp in app.pump():
            if phase == 'down' and action == Action.CANCEL.value:
                app.say('Stopped checking.')
                return False
        result = svc.poll()
        if result is not None and result[0] != 'checked':
            result = None
    _kind, release, problem = result
    if problem:
        app.say(f'Could not check for updates: {problem}.')
        return False
    if release is None:
        app.say(f'You have the newest version, {build_version.text()}.')
        return False
    return offer_update(app, release, asked=True)


def announce_update_done(app) -> None:
    """The first start after an update says so, once."""
    here, last = build_version.current(), app.settings.get('lastVersion')
    if last and build_version.is_newer(here, last):
        app.say(f'Updated to version {build_version.text(here)}.', )
    if last != here:
        app.settings.set('lastVersion', here)


def shell(app):
    """The menus around the game.  Returns a level name to play, or None."""
    app.game.play_menu_atmos()
    if start_update_check(app):
        return None
    while True:
        act, val = run_menu(app, main_menu(app.progress, titles=app.titles),
                            poll=lambda: poll_quiet_check(app))
        if act in ('quit',):
            return None
        if act == 'update_found':
            if offer_update(app, val):
                return None
            continue
        if act == 'updates':
            if check_now(app):
                return None
            continue
        if act == 'back':
            continue
        if act == 'continue':
            return val
        if act == 'levels':
            a2, v2 = run_menu(app, level_menu(app.base, app.progress))
            if a2 == 'quit':
                return None
            if a2 == 'play' and v2:
                return v2
        elif act == 'settings':
            if settings_loop(app) == 'quit':
                return None
        elif act == 'achievements':
            a2, _ = run_menu(app, achievements_menu(list(app.game.hub.values()), app.progress))
            if a2 == 'quit':
                return None
        elif act == 'about':
            about(app)


def splash(app) -> None:
    """`crossFadeSplashScreen`: the Papa Engine sting.  Any choosing key cuts it short."""
    app.say("Developed by Somethin' Else")
    app.ui('papa_engine_splash_UOS')
    s = app.game.menu_bank.sound('papa_engine_splash_UOS') if app.game.menu_bank else None
    t0 = time.perf_counter()
    while s is not None and s.playing and time.perf_counter() - t0 < 15:
        if app.src.quit_requested:
            break
        if any(ph == 'down' and a in (Action.CONFIRM.value, Action.SKIP.value,
                                      Action.CANCEL.value, Action.PAUSE.value)
               for a, ph, _ in app.pump()):
            break
    if s is not None:
        s.stop()


# ---------------------------------------------------------------- playing
def start_level(app, name: str) -> None:
    # The menu atmosphere (or a level's end music) carries on into the level
    # until FadeOutMenuAtmos fades it: 5 s after the load, or sooner when the
    # level asks - as the original does.
    app.progress.player_did_unlock_level(name)
    app.chords.clear()
    app.game.load(name)
    app.rep.show(f'--- {name}: {app.game.title(name)} ---')


def handle_action(app, action: str, now: float) -> None:
    """One resolved press: a foot, a hand, a clap, a jump, or anything else."""
    g, mi = app.game, app.game.interpreter
    g.bus.now = g.now
    if action in (Action.FOOT_LEFT.value, Action.FOOT_RIGHT.value):
        foot = LEFT if action == Action.FOOT_LEFT.value else RIGHT
        if mi.foot_pressed(foot):
            mi.foot_released(foot)
    elif action == 'jump':
        mi.jump()
    elif action in (Action.HAND_LEFT.value, Action.HAND_RIGHT.value):
        mi.hand_pressed(LEFT if action == Action.HAND_LEFT.value else RIGHT)
    elif action == 'clap':
        mi.hands_clapped()
    elif action == Action.SKIP.value:
        g.skip()
    elif action == Action.SHAKE.value:
        g.bus.post('PGE_ACTION_Shake', {})
    elif action == Action.PHONE_UPRIGHT.value:
        g.phone.rotate('portrait')
    elif action == Action.PHONE_SIDEWAYS.value:
        g.phone.rotate('landscape')
    elif action == Action.UNPLUG.value:
        g.bus.post('PGE_MESSAGE_AudioRouteChanged', {'unplugged': True})
    elif action == Action.VOLUME_UP.value:
        app.engine.adjust_master_volume(+2.0)
        app.say(f'Volume {app.engine.master_volume_db:+.0f} decibels.')
    elif action == Action.VOLUME_DOWN.value:
        app.engine.adjust_master_volume(-2.0)
        app.say(f'Volume {app.engine.master_volume_db:+.0f} decibels.')
    g.bus.update(g.now)


def after_level(app):
    """The after-level screen (decision 5).  Returns a level to play, or None."""
    g = app.game
    kind, name, other = g.outcome
    if kind == 'end':
        # the Adios screen: Main Menu (quitButtonTouched: QuitGameMode,
        # ResetGameplayEngine) - the end music plays on until the menu's atmos
        act, _ = run_menu(app, adios_menu())
        g.unload()
        return None if act == 'quit' else shell(app)
    if kind == 'win':
        e = g.hub.get(name)
        menu = level_complete_menu(other if g.has_level(other) else None,
                                   e.success_text if e else '',
                                   achievement_text(e, app.progress) if e else '')
    else:
        menu = level_failed_menu()
    while True:
        act, val = run_menu(app, menu)
        if act == 'next' and val:
            return val
        if act == 'replay':
            return name
        if act == 'levels':
            a2, v2 = run_menu(app, level_menu(app.base, app.progress))
            if a2 == 'play' and v2:
                return v2
            continue
        if act in ('main', 'back'):
            return shell(app)
        if act == 'quit':
            return None


def pause(app):
    """Escape: the pause screen.  Returns what to do next."""
    g = app.game
    g.pause()
    app.chords.clear()
    while True:
        act, _ = run_menu(app, pause_menu(g.pause_text))
        if act in ('resume', 'back'):
            g.resume()
            return ('resume', None)
        if act == 'restart':
            return ('play', g.level_name)
        if act == 'settings':
            if settings_loop(app) == 'quit':
                return ('quit', None)
            continue
        if act == 'main':
            g.unload()
            return ('play', shell(app))
        if act == 'quit':
            return ('quit', None)


def play(app, name: str) -> None:
    g = app.game
    start_level(app, name)
    while True:
        if app.src.quit_requested:
            return
        t = time.perf_counter()
        for action, phase, _stamp in app.src.poll():
            if phase == 'down' and action == Action.PAUSE.value:
                what, nxt = pause(app)
                if what == 'quit' or (what == 'play' and nxt is None):
                    return
                if what == 'play':
                    start_level(app, nxt)
                break
            for press in app.chords.feed(action, phase, t):
                handle_action(app, press.action, t)
        for press in app.chords.update(time.perf_counter()):
            handle_action(app, press.action, t)
        dt = app.clock.tick(FRAME_HZ) / 1000.0
        turn = 0.0
        rate = app.settings.turn_rate
        if app.src.is_held(Action.TURN_LEFT):
            turn += rate * dt
        if app.src.is_held(Action.TURN_RIGHT):
            turn -= rate * dt
        stick = app.src.turn_rate()
        if stick:
            turn -= stick * rate * dt
        if turn and g.level is not None and not g.level.paused_game:
            g.interpreter.rotate_by(math.radians(turn))
        g.update(min(dt, 0.1))
        if g.finished:
            nxt = after_level(app)
            if nxt is None:
                return
            start_level(app, nxt)


def selftest(app, level: str = 'ps2_Intro') -> int:
    """`--selftest [level]`: load a level on the real audio device, run 20 s, report.

    For checking a build from a clean folder without anyone at the keys.
    Writes selftest.txt next to the exe and exits.
    """
    g = app.game
    played = []
    # silent: the listener gain goes to zero for the run (nothing is saved),
    # so checking a build never plays the game aloud on someone's machine
    from papasangre2.audio import openal as OA
    app.engine.al.alListenerf(OA.AL_GAIN, 0.0)
    g.load(level)
    t_end = time.perf_counter() + 20.0
    while time.perf_counter() < t_end:
        app.src.poll()
        dt = app.clock.tick(FRAME_HZ) / 1000.0
        g.update(min(dt, 0.1))
        for s in g.bank.live_sounds():
            if s.playing and s.name not in played:
                played.append(s.name)
    lines = [f'device: {app.engine.device_name}',
             f'hrtf: {app.engine.hrtf_status} {app.engine.available_hrtfs}',
             f'speech: {app.rep.backend}',
             f'game time: {g.now:.1f} s',
             f'level: {g.level_name}, agents {len(g.level.agents)}',
             'enemies: ' + ', '.join(f'{a.name} ({type(a).__name__}, state {a.state})'
                                     for a in g.level.agents if a.kind == 'enemy'),
             'played: ' + ', '.join(played)]
    # the sounds Muhammad made for the port: declared, found and decoded
    from papasangre2.assets import requested
    got = [n for n in requested.SOUNDS if g.bank.has(n) and g.bank.sound(n) is not None]
    lines.append(f'requested sounds: {len(got)} of {len(requested.SOUNDS)} '
                 f'({", ".join(got)})')
    out = os.path.join(paths.writable_root(), 'selftest.txt')
    with open(out, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')
    ok = (bool(played) and app.engine.hrtf_status == 'enabled'
          and len(got) == len(requested.SOUNDS))
    app.game.unload()
    return 0 if ok else 1


def selftest_update(app) -> int:
    """`--selftest-update`: check, download and hand over an update with no
    questions, as Yes and Restart now would, then quit - for proving a built
    exe updates (tools/verify_updater.py --frozen).  Writes
    selftest-update.txt beside the save."""
    lines = [f'version: {build_version.current()}']
    ok, why = updater.can_update()
    lines.append(f'can update: {ok} {why}')
    code = 0
    if ok:
        try:
            release = updater.check(app.updates.check_url)
            lines.append(f'offered: {release.tag if release else None}')
            if release is not None:
                plan = updater.build_plan(release)
                updater.download(plan)
                lines.append(f'fetched: {len(plan.fetch or [])} files, {plan.downloaded} bytes, '
                             f'{plan.unchanged} unchanged, {len(plan.remove)} to remove')
                updater.apply(plan.staging, plan.remove)
                lines.append('handed over')
        except updater.UpdateError as exc:
            lines.append(f'problem: {exc}')
            code = 1
    with open(os.path.join(paths.writable_root(), 'selftest-update.txt'), 'w',
              encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')
    return code


def main(rep) -> int:
    if os.environ.get('PS2_SILENT'):
        rep.say = lambda *a, **k: None
    if '--selftest-update' in sys.argv:
        app = App(rep)
        code = selftest_update(app)
        app.src.close()
        app.engine.close()
        pygame.quit()
        return code
    if '--selftest' in sys.argv:
        app = App(rep)
        i = sys.argv.index('--selftest')
        level = sys.argv[i + 1] if len(sys.argv) > i + 1 else 'ps2_Intro'
        code = selftest(app, level)
        app.src.close()
        app.engine.close()
        pygame.quit()
        return code
    rep.show('Papa Sangre II - ' + host.PORT_NAME + ' port')
    rep.show('=' * 46)
    app = App(rep)
    rep.show(f'output device : {console.ascii_safe(app.engine.device_name)}')
    rep.show(f'HRTF          : {app.engine.hrtf_status} {app.engine.available_hrtfs}')
    for w in sysaudio.warnings_for(app.engine.device_name):
        rep.say('Warning. ' + w)
    if paths.running_from_throwaway():
        rep.say('You are running the game from inside the zip file, or from a folder it '
                'cannot write to. Your progress is being saved in your app data folder '
                'instead. To keep everything together, close the game and extract it to '
                'a folder of its own.')
    start = sys.argv[1] if len(sys.argv) > 1 else None
    if start is None:
        splash(app)
        announce_update_done(app)
        start = shell(app)
    if start is not None:
        play(app, start)
    if app.restarting:
        rep.say('Installing the update. The game will start again in a moment.')
        _wait(app, 1.5)
    else:
        rep.say('Goodbye.')
    app.game.unload()
    app.src.close()
    app.engine.close()
    pygame.quit()
    return 0


if __name__ == '__main__':
    raise SystemExit(console.run(main))
