"""The menus, spoken, in Papa Sangre II's own words.

Every label that exists in the original is the original's - the accessibility
labels in its nibs, which is what VoiceOver read out:

=====================  ======================================================
main menu              "Select Level", "Settings", "Achievements", "About"
                       (PGEViewController.nib); "More games" is an App Store
                       link and is left out
level list             "Play Level %i: %@" / "Level %i: %@; locked" and
                       "Main menu" (AccessibleAllLevelsViewController)
pause                  "Continue game", "Restart Level", "Settings", "Quit
                       game" (PGEStepsAndSwipeViewController.nib), with the
                       level's objective (`SetPauseText`) read first
after a level          the win screen's "Continue", "Play this again", "Main
                       Menu" (PGEWinViewController.nib), after the level's
                       success text
settings               "Settings", "Back" (PGESettingsViewController.nib);
                       the control schemes Gyro / Swipe / Tilt mean nothing
                       on a keyboard and are not offered
=====================  ======================================================

Added for a PC, each recorded in DIVERGENCES.md: Continue (carried over from
the Papa Sangre port: straight to the furthest level unlocked), Select Level
and Settings on the after-level screen (decision 5), Quit, and in Settings the
volume, turning speed, the three REQUESTED switches, keys and controller
buttons.

Nothing is drawn.  A menu is a list you move through with up and down, choose
with Enter or A, and leave with Escape or B; left and right change a setting.
"""

from __future__ import annotations

from ..assets.hublist import load_hub_list
from ..util.settings import MAX_TURN_RATE, MIN_TURN_RATE


#: Actions whose button plays ``back_button`` in the original (Main Menu,
#: Quit, the level list's Main menu, Settings' and About's back).
BACK_ACTIONS = ('back', 'main', 'quit')
#: ``MenuItem.sound`` default: decide from the action.
AUTO = 'auto'


class MenuItem:
    """One row: what to say, and what choosing it does.

    ``sound`` is the UI sound its button plays, as the original's handlers do
    (``playUiSoundWithName:``): ``'click_button'``, ``'back_button'``, None
    for a button that makes no sound, or AUTO - back for the actions in
    BACK_ACTIONS, click for the rest.
    """

    __slots__ = ('label', 'action', 'value', 'enabled', 'adjust', 'sound')

    def __init__(self, label: str, action: str, value=None,
                 enabled: bool = True, adjust=None, sound=AUTO) -> None:
        self.label = label
        self.action = action
        self.value = value
        self.enabled = enabled
        self.adjust = adjust          # callable(delta) -> new spoken label
        self.sound = sound

    def ui_sound(self) -> str | None:
        if self.sound != AUTO:
            return self.sound
        return 'back_button' if self.action in BACK_ACTIONS else 'click_button'


class Menu:
    """A spoken list.  ``choose`` returns ``(action, value)`` or None."""

    def __init__(self, title: str, items: list[MenuItem], intro: str = '',
                 cancel: MenuItem | None = None, cancellable: bool = True) -> None:
        self.title = title
        self.items = items
        self.intro = intro            # read once, before the first row
        self.index = 0
        #: What Escape does: the row it stands for (default: a Back with the
        #: back sound), or nothing at all when not ``cancellable``.
        self.cancellable = cancellable
        self.cancel = cancel if cancel is not None else MenuItem('Back', 'back')

    @property
    def current(self) -> MenuItem | None:
        if not self.items:
            return None
        return self.items[self.index % len(self.items)]

    def move(self, delta: int) -> str:
        if not self.items:
            return ''
        self.index = (self.index + delta) % len(self.items)
        return self.speak_current()

    def speak_current(self) -> str:
        item = self.current
        if item is None:
            return f'{self.title}. Empty.'
        return item.label

    def announce(self) -> str:
        """Said on entering the menu: its name, any text, then the row."""
        parts = [self.title]
        if self.intro:
            parts.append(self.intro)
        parts.append(self.speak_current())
        return '. '.join(p.rstrip('.') for p in parts if p) + '.'

    def choose(self):
        item = self.current
        if item is None:
            return None
        if not item.enabled:
            return ('blocked', item)
        if item.adjust is not None and item.action == 'toggle':
            item.label = item.adjust(+1)
            return ('toggled', item)
        return (item.action, item.value)

    def adjust_current(self, delta: float) -> str | None:
        """Left/right on a setting row.  None when the row is not one."""
        item = self.current
        if item is None or item.adjust is None:
            return None
        item.label = item.adjust(delta)
        return item.label


# ---------------------------------------------------------------- builders
def main_menu(progress=None, first_level: str = 'ps2_Intro', titles=None) -> Menu:
    titles = titles or {}
    last = progress.last_unlocked_level if progress is not None else first_level
    started = bool(progress is not None and progress.values.get('lastLevelUnlocked'))
    resume = (f'Continue, {titles.get(last, last)}' if started else 'Start the game')
    return Menu('Papa Sangre II', [
        MenuItem(resume, 'continue', last if started else first_level),
        MenuItem('Select Level', 'levels'),
        MenuItem('Settings', 'settings'),
        MenuItem('Achievements', 'achievements'),
        MenuItem('About', 'about'),
        MenuItem('Check for updates', 'updates'),
        MenuItem('Quit', 'quit'),
    ], cancellable=False)             # nothing to go back to


def level_menu(bundle_dir: str, progress=None) -> Menu:
    """`AccessibleAllLevelsViewController`: the hub list, then Main menu."""
    items = []
    for entry in load_hub_list(bundle_dir):
        # `tableView:didSelectRowAtIndexPath:` posts the launch and plays no
        # UI sound (start_level_button belongs to the sighted hub selector).
        # REQUESTED (the tester, 2026-09-26): the click, as every other button.
        items.append(MenuItem(entry.spoken(progress), 'play', entry.file_name,
                              enabled=entry.is_unlocked(progress), sound='click_button'))
    items.append(MenuItem('Main menu', 'back'))
    return Menu('Select Level', items)


def _onoff(v: bool) -> str:
    return 'on' if v else 'off'


def settings_menu(settings, engine=None) -> Menu:
    """Settings.  Left and right change the row you are on; Enter flips a switch."""

    def volume_label() -> str:
        if engine is None:
            return 'Sound volume, unavailable'
        return f'Sound volume, {engine.master_volume_db:+.0f} decibels'

    def turn_label() -> str:
        return f'Turning speed, {settings.turn_rate:.0f} degrees per second'

    def adjust_volume(delta: float) -> str:
        if engine is None:
            return volume_label()
        before = engine.master_volume_db
        engine.adjust_master_volume(2.0 * delta)
        if abs(engine.master_volume_db - before) < 0.01:
            return volume_label() + (', maximum' if delta > 0 else ', minimum')
        return volume_label()

    def adjust_turn(delta: float) -> str:
        settings.adjust('turnRateDegreesPerSecond', 15.0 * delta)
        if settings.turn_rate <= MIN_TURN_RATE:
            return turn_label() + ', slowest'
        if settings.turn_rate >= MAX_TURN_RATE:
            return turn_label() + ', fastest'
        return turn_label()

    def switch(key: str, label: str):
        def text() -> str:
            return f'{label}, {_onoff(settings.get(key))}'

        def flip(_delta: float) -> str:
            settings.toggle(key)
            return text()
        return text, flip

    blind_t, blind_f = switch('blindIntro', 'Blind intro')
    ping_t, ping_f = switch('skipPing', 'Skip ping')
    expl_t, expl_f = switch('skipExplanation', 'Skip explanation')
    pc_t, pc_f = switch('pcInstructions', 'PC instructions')
    wh_t, wh_f = switch('shakeWhoosh', 'Shake sound')
    up_t, up_f = switch('checkUpdates', 'Check for updates at start')
    return Menu('Settings', [
        MenuItem(volume_label(), 'adjust', adjust=adjust_volume),
        MenuItem(turn_label(), 'adjust', adjust=adjust_turn),
        MenuItem(blind_t(), 'toggle', adjust=blind_f),
        MenuItem(ping_t(), 'toggle', adjust=ping_f),
        MenuItem(expl_t(), 'toggle', adjust=expl_f),
        MenuItem(pc_t(), 'toggle', adjust=pc_f),
        MenuItem(wh_t(), 'toggle', adjust=wh_f),
        MenuItem(up_t(), 'toggle', adjust=up_f),
        MenuItem('Keys', 'keys'),
        MenuItem('Controller buttons', 'buttons'),
        MenuItem('Back', 'back'),
    ])


#: What the key menu offers, in the order it reads them out.  Clapping and
#: jumping have no row of their own: they are both hands, and both feet,
#: pressed together, so they move with whatever those are bound to.
REBINDABLE = (
    ('foot_left', 'Left foot'),
    ('foot_right', 'Right foot'),
    ('hand_left', 'Left hand'),
    ('hand_right', 'Right hand'),
    ('turn_left', 'Turn left'),
    ('turn_right', 'Turn right'),
    ('phone_upright', 'Hold the phone upright'),
    ('phone_sideways', 'Hold the phone on its side'),
    ('shake', 'Shake the phone'),
    ('unplug_headphones', 'Unplug the headphones'),
    ('skip', 'Skip'),
    ('pause', 'Pause'),
    ('confirm', 'Select'),
    ('cancel', 'Back'),
    ('menu_up', 'Menu up'),
    ('menu_down', 'Menu down'),
    ('menu_left', 'Menu left'),
    ('menu_right', 'Menu right'),
    ('volume_up', 'Volume up'),
    ('volume_down', 'Volume down'),
)


def keys_menu(keymap) -> Menu:
    items = []
    for action, label in REBINDABLE:
        keys = keymap.keys_for(action)
        said = ' or '.join(keys) if keys else 'unbound'
        items.append(MenuItem(f'{label}: {said}', 'rebind', action))
    items.append(MenuItem('Restore all keys to their defaults', 'reset_keys'))
    items.append(MenuItem('Back', 'back'))
    return Menu('Keys', items)


#: The pad's list.  Turning is missing on purpose: it is the left stick.
PAD_REBINDABLE = tuple(r for r in REBINDABLE if r[0] not in ('turn_left', 'turn_right'))


def pad_menu(padmap) -> Menu:
    items = []
    for action, label in PAD_REBINDABLE:
        items.append(MenuItem(f'{label}: {padmap.describe(action)}',
                              'rebind_button', action))
    items.append(MenuItem('Restore all buttons to their defaults', 'reset_buttons'))
    items.append(MenuItem('Back', 'back'))
    return Menu('Controller buttons', items)


def pause_menu(objective: str = '') -> Menu:
    """The pause screen: the objective, then its four buttons, then Quit."""
    return Menu('Pause', [
        MenuItem('Continue game', 'resume'),
        MenuItem('Restart Level', 'restart'),
        MenuItem('Settings', 'settings'),
        MenuItem('Quit game', 'main'),
        MenuItem('Quit to Windows', 'quit'),
    ], intro=objective, cancel=MenuItem('Continue game', 'resume'))  # Escape = resumeGame:


def level_complete_menu(next_level: str | None, success_text: str = '',
                        achievement: str = '') -> Menu:
    """The win screen: the success text, any achievement, then the choices.

    The achievement is also a row (REQUESTED, 2026-09-24), after Continue, so
    its state can be read again: the original shows it as a badge that is on
    or off (`success_achievement_on` / `_off`) beside the achieved or the
    unachieved description.
    """
    items = []
    if next_level:
        items.append(MenuItem('Continue', 'next', next_level))
    if achievement:
        items.append(MenuItem(achievement, 'info', sound=None))
    # `-[PGEWinViewController playAgainButtonTouched:]` plays no UI sound
    # (the lose screen's does).
    items.append(MenuItem('Play this again', 'replay', sound=None))
    items.append(MenuItem('Select Level', 'levels'))
    items.append(MenuItem('Main Menu', 'main'))
    items.append(MenuItem('Quit', 'quit'))
    intro = ' '.join(t for t in (success_text, achievement) if t)
    return Menu('Level complete', items, intro=intro)


#: The achievements Game Center kept and the game never names (their titles
#: were on Apple's servers).  -[PGEGameProgress ...]
GAME_CENTER_ONLY = ('act1', 'act2', 'act3', 'memoryLost', '10000steps', '1000000steps',
                    'kill25', 'kil100', 'kill500', 'superBullet')
#: PORT-SIDE: their spoken names, made from the identifiers (the original's
#: titles are lost with Game Center).
GAME_CENTER_NAMES = {
    'act1': 'Act 1', 'act2': 'Act 2', 'act3': 'Act 3', 'memoryLost': 'Lost memories',
    '10000steps': '10,000 steps', '1000000steps': 'A million steps',
    'kill25': '25 kills', 'kil100': '100 kills', 'kill500': '500 kills',
    'superBullet': 'Super bullet',
}


def one_line(text: str) -> str:
    return ' '.join(str(text).split())


def achievement_text(entry, progress) -> str:
    """`-[PGEWinViewController initAchievementView]` (0x100061fc0): the level's
    achievement title, its badge on or off, and the achieved or the
    unachieved description (the game's own words for each)."""
    ach = getattr(entry, 'achievement', None) or {}
    ident = str(ach.get('id', ''))
    if not ident:
        return ''
    done = bool(progress is not None and progress.achievement_completed(ident))
    desc = ach.get('achievedDescription' if done else 'unachievedDescription', '')
    state = 'achieved' if done else 'not achieved'
    return one_line(f"Achievement: {ach.get('title', ident)}, {state}. {desc}")


def game_center_help(ident: str, entries) -> str:
    """REQUESTED (2026-09-26): how a Game Center achievement is earned, in a
    player's words, from what the port recovered of the original's rules
    (save/achievements.py, save/progress.py, core/game.py).  Levels are named
    by their number and title in the level list."""
    from ..save.achievements import LEVEL_CHECKS   # noqa: PLC0415
    number = {e.file_name: i for i, e in enumerate(entries, 1)}
    title = {e.file_name: one_line(e.title) for e in entries}
    ach = {str((e.achievement or {}).get('id', '')): (e.file_name, one_line(
        (e.achievement or {}).get('title', ''))) for e in entries}

    def level(fn):
        return f'level {number.get(fn, "?")}, {title.get(fn, fn)}'

    if ident in ('act1', 'act2', 'act3'):
        levels = [fn for fn, (_t, _a, act, _p) in LEVEL_CHECKS.items() if act == ident]
        nums = sorted(number[fn] for fn in levels if fn in number)
        last = next(fn for fn, (_t, _a, act, p) in LEVEL_CHECKS.items()
                    if act == ident and p >= 100)
        said = level(last)
        return (f'Finish levels {nums[0]} to {nums[-1]}. It goes up as you finish them, '
                f'and it is yours when you finish {said}' + ('' if said[-1] in '.?!' else '.'))
    if ident == 'memoryLost':
        return ('Hear 24 of your lost memories. When you die in levels '
                f'{number.get("ps2_1")} to {number.get("ps2_4")}, from {title.get("ps2_1")} to '
                f'{title.get("ps2_4")}, and you have already heard everything the narrator '
                'says about that death, you hear one of your lost memories instead.')
    if ident == '10000steps':
        return 'Walk about 5,000 steps, counted over all your games, finished or not.'
    if ident == '1000000steps':
        return ('Despite its name, it is done at about 42,000 steps, counted over all your '
                'games, finished or not.')
    if ident in ('kill25', 'kil100', 'kill500'):
        n = {'kill25': 25, 'kil100': 100, 'kill500': 500}[ident]
        return (f'Take down {n} in total, over all your games. Every monster, duck, penguin '
                'or polar bear you shoot or knife counts, and so does every fire you put out '
                'with the extinguisher.')
    if ident == 'superBullet':
        parts = []
        for a in ('level_6', 'level_11b', 'level_12'):
            fn, t = ach.get(a, ('', a))
            parts.append(f'{t} in level {number.get(fn, "?")}')
        return ('Earn all three achievements for never wasting a shot: ' + ', '.join(parts[:-1])
                + f', and {parts[-1]}. Each one is a third of it.')
    return ''


def achievements_menu(entries, progress) -> Menu:
    """REQUESTED (decision 4): the achievements, spoken.  The level ones by
    their titles and descriptions from the hub list; the Game Center ones by
    a name made from the identifier, with the percentage the game last
    reported - and Enter on one says how it is earned (REQUESTED, 2026-09-26)."""
    items = []
    for e in entries:
        ach = getattr(e, 'achievement', None) or {}
        ident = str(ach.get('id', ''))
        if not ident:
            continue
        done = bool(progress is not None and progress.achievement_completed(ident))
        desc = ach.get('achievedDescription' if done else 'unachievedDescription', '')
        state = 'achieved' if done else 'not achieved'
        items.append(MenuItem(one_line(f"{ach.get('title', ident)}, {state}. {desc}"),
                              'info', sound=None))
    for ident in GAME_CENTER_ONLY:
        pct = progress.game_center_percent(ident) if progress is not None else 0.0
        state = 'achieved' if pct >= 100.0 else f'not achieved, {pct:.0f} percent'
        items.append(MenuItem(f'{GAME_CENTER_NAMES[ident]}, {state}', 'explain',
                              game_center_help(ident, entries), sound=None))
    items.append(MenuItem('Main menu', 'back'))
    return Menu('Achievements', items)


def about_rows(text: str) -> list[str]:
    """One screen's text as rows to read one at a time: a paragraph each, and
    a credit block (the role, then its names, one per line) as "role: names"."""
    rows = []
    for para in str(text).replace('\r', '').split('\n\n'):
        lines = [ln.strip() for ln in para.split('\n') if ln.strip()]
        if not lines:
            continue
        if len(lines) == 1:
            rows.append(lines[0])
        else:
            head = lines[0].rstrip(':')
            rows.append(f"{head}: {', '.join(lines[1:])}")
    return rows


def about_menu(texts, pc_note: str = '', version: str = '') -> Menu:
    """`CreditsViewController`, read a row at a time (REQUESTED, the tester,
    2026-09-26 - read through in one go, the credits were a jumble): the
    headphones notice, the credits, the PC word, then Main Menu.  The port's
    version comes first when given."""
    items = []
    if version:
        items.append(MenuItem(f'Version {version}', 'info', sound=None))
    for t in texts:
        items.extend(MenuItem(r, 'info', sound=None) for r in about_rows(t))
    if pc_note:
        items.append(MenuItem(one_line(pc_note), 'info', sound=None))
    items.append(MenuItem('Main Menu', 'back'))
    return Menu('About', items)


def update_offer_menu(message: str) -> Menu:
    """PORT ADDITION: a newer version is on GitHub.  Two choices and no more
    (the owner, 2026-09-26): Update now downloads it and restarts into it with
    nothing further to answer; Not now (and Escape) asks again next start."""
    return Menu('Update available', [
        MenuItem('Update now', 'yes'),
        MenuItem('Not now', 'no', sound='back_button'),
    ], intro=message, cancel=MenuItem('Not now', 'no'))


def update_ready_menu(message: str) -> Menu:
    """PORT ADDITION: an update downloaded earlier and not yet put in (the game
    closed before it could restart).  The same two choices."""
    return Menu('Update ready', [
        MenuItem('Update now', 'restart'),
        MenuItem('Not now', 'later', sound='back_button'),
    ], intro=message, cancel=MenuItem('Not now', 'later'))


def adios_menu() -> Menu:
    """`PGEAdiosViewController` - the end of the game (ps2_18b).  Its nib is the
    end-game sky, clouds and one button, Main Menu (`quitButtonTouched:`, the
    back sound); the port's Quit follows it, as on the other screens.  The
    screen has no words of its own: its spoken title is the port's."""
    return Menu('The end', [
        MenuItem('Main Menu', 'main'),
        MenuItem('Quit', 'quit'),
    ])


def level_failed_menu() -> Menu:
    """The lose screen: "You are still dead" (the skip button is gone, decision 5)."""
    return Menu('You are still dead', [
        MenuItem('Play this again', 'replay'),
        MenuItem('Select Level', 'levels'),
        MenuItem('Main Menu', 'main'),
        MenuItem('Quit', 'quit'),
    ])
