"""Play a level in the simulator the way a person would: turn, walk, clap.

Only what a player can do goes through here - foot, hand, clap, turn and skip,
through the move interpretor with its gates - so a level the autopilot
finishes is a level a person can finish.  Used by the tests and by
`tools/run_level.py`.
"""

from __future__ import annotations

import math

from .sim import Sim

STEP_GAP = 0.40          # 150 steps a minute: a steady walk, under every run limit


class Autopilot:
    def __init__(self, sim: Sim) -> None:
        self.sim = sim
        self.foot = 'L'
        self.steps = 0

    # ------------------------------------------------------------ looking
    def bearing_to(self, x: float, y: float) -> float:
        px, py = self.sim.player.position
        return math.atan2(y - py, x - px)

    def face(self, x: float, y: float, rate: float = math.radians(90)) -> bool:
        """Turn towards (x, y) at `rate` rad/s; True when facing it."""
        want = self.bearing_to(x, y)
        for _ in range(400):
            cur = self.sim.player.player_angle
            d = (want - cur + math.pi) % (2 * math.pi) - math.pi
            if abs(d) < math.radians(2):
                return True
            step = max(-rate * 0.05, min(rate * 0.05, d))
            if not self.sim.turn(step):
                self.sim.step(0.05)
                continue
            self.sim.step(0.05)
        return False

    # ------------------------------------------------------------ walking
    def distance_to(self, x: float, y: float) -> float:
        px, py = self.sim.player.position
        return math.hypot(x - px, y - py)

    def step_once(self) -> bool:
        ok = self.sim.foot(self.foot)
        if ok:
            self.steps += 1
            self.foot = 'R' if self.foot == 'L' else 'L'
        self.sim.step(STEP_GAP)
        return ok

    def walk_to(self, x: float, y: float, within: float = 6.0, limit: int = 400,
                until=None) -> bool:
        """Walk until within `within` px of (x, y), or until `until()` is true."""
        for _ in range(limit):
            if self.distance_to(x, y) <= within or (until is not None and until()):
                return True
            self.face(x, y)
            if until is not None and until():        # things change while turning
                return True
            self.step_once()
        return self.distance_to(x, y) <= within

    def wait_for(self, pred, limit: float = 300.0) -> bool:
        return self.sim.run_until(pred, limit=limit)

    def active(self, name: str) -> bool:
        a = self.sim.level.agent(name)
        return bool(a is not None and a.active)

    def agent_pos(self, name: str):
        return self.sim.level.agent(name).position


def intro_opening(sim: Sim, done: list | None = None, skip: bool = False) -> Autopilot:
    """ps2_Intro up to the first memory: listen, turn, face the voice."""
    ap = Autopilot(sim)
    done = done if done is not None else []
    mi = sim.interpreter

    def note(s):
        done.append('%7.2f %s' % (sim.now, s))

    # the opening: nothing to do but listen (or skip what can be skipped)
    ap.wait_for(lambda: mi.player_can_rotate, limit=400)
    note('can turn')
    # find the record player and the fountain, then turn back to the voice
    ap.face(*ap.agent_pos('gramophone_loop'))
    sim.step(1.0)
    ap.face(*ap.agent_pos('fountain'))
    sim.step(1.0)
    note('faced the record player and the fountain')
    ap.wait_for(lambda: ap.active('detector1'), limit=60)
    for d in [a for a in sim.level.agents if a.name == 'detector1']:
        ap.face(*d.position)
        sim.step(0.5)
        if ap.active('intro1') or not ap.active('detector1'):
            break
    note('faced the voice')
    ap.wait_for(lambda: ap.active('intro1'), limit=10)
    if skip:
        sim.step(2.0)
        sim.skip()
    ap.wait_for(lambda: ap.active('memory1active'), limit=200)
    ap.face(*ap.agent_pos('memory1'))
    note('faced the first memory')
    return ap


def play_intro(sim: Sim, skip: bool = False) -> list[str]:
    """Play ps2_Intro to the door.  Returns a log of what was done."""
    done: list[str] = []
    mi = sim.interpreter

    def note(s):
        done.append('%7.2f %s' % (sim.now, s))

    ap = intro_opening(sim, done, skip)
    ap.wait_for(lambda: mi.player_can_walk, limit=120)
    note('can walk')
    ap.walk_to(*ap.agent_pos('memory1'), until=lambda: sim.level.agent('memory1').collected)
    note('collected memory 1' if sim.level.agent('memory1').collected else 'MISSED memory 1')
    for name in ('memory2', 'memory3'):
        ap.wait_for(lambda n=name: ap.active(n) and mi.player_can_walk, limit=200)
        ap.walk_to(*ap.agent_pos(name), until=lambda n=name: sim.level.agent(n).collected)
        note(('collected ' if sim.level.agent(name).collected else 'MISSED ') + name)
    ap.wait_for(lambda: ap.active('memory4') and mi.player_can_walk, limit=200)
    ap.walk_to(*ap.agent_pos('memory4'), until=lambda: sim.level.agent('memory4').collected)
    note(('collected ' if sim.level.agent('memory4').collected else 'MISSED ') + 'memory4')
    ap.wait_for(lambda: mi.player_can_use_hands and ap.active('no_clap_prompt'), limit=200)
    sim.clap()
    note('clapped')
    ap.wait_for(lambda: ap.active('memory5') and mi.player_can_walk, limit=200)
    ap.walk_to(*ap.agent_pos('memory5'), until=lambda: sim.level.agent('memory5').collected)
    note(('collected ' if sim.level.agent('memory5').collected else 'MISSED ') + 'memory5')
    ap.wait_for(lambda: ap.active('intro9'), limit=200)
    ap.walk_to(*ap.agent_pos('intro9'), within=15, until=lambda: not ap.active('intro9'))
    note('reached the door')
    ap.wait_for(lambda: ap.active('door_open_detector') and mi.player_can_use_hands, limit=200)
    sim.hand('R')
    note('pressed the right hand')
    ap.wait_for(lambda: bool(sim.sent('PGE_MESSAGE_LoadLevelWithName')), limit=120)
    note('LoadLevelWithName ' + str(sim.sent('PGE_MESSAGE_LoadLevelWithName')[-1].get('name')))
    return done


def play_collect_level(sim: Sim, clap_prompt: str = 'no_clap_prompt', rounds: int = 40) -> str:
    """A museum level (ps2_1 to ps2_4): clap when asked, then go for whichever
    collectible is out - onto it, or up to it and a hand for one in a glass
    case - until the door.  Returns 'won', 'died' or 'stuck'."""
    from .entities.collectible import Collectible   # noqa: PLC0415
    ap = Autopilot(sim)
    mi = sim.interpreter
    level = sim.level.name

    def outcome():
        for _, n, p in sim.messages:
            if n == 'PGE_MESSAGE_LoadLevelWithName':
                return 'died' if p.get('name') == level else 'won'
        return None

    def pending():
        return [a for a in sim.level.agents
                if isinstance(a, Collectible) and a.active and not a.collected]

    def prompt_up():
        return any(a.name == clap_prompt and a.active for a in sim.level.agents)

    clapped = False
    for _ in range(rounds):
        if outcome():
            break
        ap.wait_for(lambda: (mi.player_can_walk and pending()) or outcome()
                    or (mi.player_can_use_hands and prompt_up()), limit=240)
        if prompt_up() and not clapped and mi.player_can_use_hands:
            sim.clap()
            clapped = True
            continue
        todo = pending()
        if not todo:
            continue
        c = todo[0]
        if c.collect_with_left_hand or c.collect_with_right_hand:
            ap.walk_to(*c.position, within=max(3.0, c.collide_radius - 4),
                       until=lambda: c.in_collide_range or outcome())
            ap.wait_for(lambda: (mi.player_can_use_hands and c.in_collide_range) or outcome(),
                        limit=60)
            for _ in range(5):
                if c.collected or outcome():
                    break
                sim.hand('L')
                sim.step(1.0)
        else:
            ap.walk_to(*c.position, until=lambda: c.collected or outcome())
    sim.run_until(lambda: outcome() is not None, limit=60)
    return outcome() or 'stuck'


# ---------------------------------------------------------------- M4: routes
def _std(rect):
    rx, ry, rw, rh = rect
    if rw < 0:
        rx, rw = rx + rw, -rw
    if rh < 0:
        ry, rh = ry + rh, -rh
    return rx, ry, rw, rh


def hazards(level, margin: float = 8.0, also=None) -> list:
    """The floors a player keeps off: active lethal ones (or ones with a death
    sound and a sound of their own - a fire that turns lethal), and walls."""
    out = []
    for f in level.floors[1:]:
        if not f.active:
            continue
        deadly = f.is_lethal or (f.death_sound is not None and f.sound is not None)
        if deadly or f.is_walled or (also is not None and also(f)):
            rx, ry, rw, rh = _std(f.rect)
            out.append((rx - margin, ry - margin, rw + 2 * margin, rh + 2 * margin))
    return out


def _inside(rects, x, y) -> bool:
    for rx, ry, rw, rh in rects:
        if rx <= x < rx + rw and ry <= y < ry + rh:
            return True
    return False


def _clear(rects, a, b, step: float = 2.0) -> bool:
    n = max(1, int(math.hypot(b[0] - a[0], b[1] - a[1]) / step))
    for i in range(n + 1):
        t = i / n
        if _inside(rects, a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t):
            return False
    return True


def plan_route(level, start, goal, rects, cell: float = 4.0) -> list:
    """A* over a grid of the room, round the rectangles; the corners only."""
    import heapq
    if _clear(rects, start, goal):
        return [goal]
    rx, ry, rw, rh = _std(level.rect)
    nx, ny = int(rw // cell) + 1, int(rh // cell) + 1

    def cell_of(p):
        return (min(nx - 1, max(0, int((p[0] - rx) // cell))),
                min(ny - 1, max(0, int((p[1] - ry) // cell))))

    def centre(c):
        return (rx + (c[0] + 0.5) * cell, ry + (c[1] + 0.5) * cell)

    s, g = cell_of(start), cell_of(goal)
    openq = [(0.0, s)]
    came = {s: None}
    cost = {s: 0.0}
    while openq:
        _, c = heapq.heappop(openq)
        if c == g:
            break
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if not dx and not dy:
                    continue
                n = (c[0] + dx, c[1] + dy)
                if not (0 <= n[0] < nx and 0 <= n[1] < ny):
                    continue
                if n != g and _inside(rects, *centre(n)):
                    continue
                nc = cost[c] + math.hypot(dx, dy)
                if nc < cost.get(n, math.inf):
                    cost[n] = nc
                    came[n] = c
                    h = math.hypot(g[0] - n[0], g[1] - n[1])
                    heapq.heappush(openq, (nc + h, n))
    if g not in came:
        return [goal]
    cells = []
    c = g
    while c is not None:
        cells.append(centre(c))
        c = came[c]
    cells.reverse()
    cells[-1] = goal
    # keep only the turns that line of sight needs
    out, here = [], start
    i = 0
    while i < len(cells):
        j = len(cells) - 1
        while j > i and not _clear(rects, here, cells[j]):
            j -= 1
        if (j == i and i + 1 < len(cells)
                and math.hypot(cells[i][0] - here[0], cells[i][1] - here[1]) < cell):
            j = i + 1                # standing in this cell: on to the next
        out.append(cells[j])
        here = cells[j]
        i = j + 1
    return out


def go_to(ap: Autopilot, x: float, y: float, within: float = 6.0, until=None,
          margin: float = 8.0, also=None, limit: int = 30, extra=None) -> bool:
    """Walk to (x, y) round the hazards, re-planning at every corner;
    `extra()` gives more rectangles to keep out of (moving things)."""
    for _ in range(limit):
        if ap.distance_to(x, y) <= within or (until is not None and until()):
            return True
        rects = hazards(ap.sim.level, margin, also)
        if extra is not None:
            rects = rects + [r for r in extra() if not _inside([r], *ap.sim.player.position)]
        route = plan_route(ap.sim.level, ap.sim.player.position, (x, y), rects)
        while len(route) > 1 and ap.distance_to(*route[0]) < 3.0:
            route.pop(0)
        wx, wy = route[0]
        last = len(route) == 1
        ap.walk_to(wx, wy, within=within if last else 3.0, limit=60,
                   until=until if last else (lambda: until is not None and until()))
    return ap.distance_to(x, y) <= within


def waiting_to_be_faced(sim: Sim) -> bool:
    return any(a.active and a.has_trigger('OnEnteringShootRange') and not a.is_in_shooting_range
               and a.collide_radius > 0 for a in sim.level.agents)


def face_what_is_waited_for(ap: Autopilot) -> bool:
    """A level that has stopped your feet until you face something: turn to
    the active agent whose `OnEnteringShootRange` it is waiting on."""
    for a in ap.sim.level.agents:
        if a.active and a.has_trigger('OnEnteringShootRange') and not a.is_in_shooting_range:
            if a.collide_radius > 0:
                ap.face(*a.position)
                ap.sim.step(0.2)
                return True
    return False


def outcome_of(sim: Sim):
    level = sim.level.name
    for _, n, p in sim.messages:
        if n == 'PGE_MESSAGE_LoadLevelWithName':
            return 'died' if p.get('name') == level else 'won'
        if n == 'PGE_MESSAGE_PresentAdiosVC':
            return 'end'                     # ps2_18b: the end of the game
    return None


def play_level_5(sim: Sim, rounds: int = 60) -> str:
    """ps2_5: the pools.  Every memory by a route round the live pools; the
    glass cases by hand; turn to the bubbles when told to."""
    from .entities.collectible import Collectible   # noqa: PLC0415
    ap = Autopilot(sim)
    mi = sim.interpreter

    def pending():
        return [a for a in sim.level.agents
                if isinstance(a, Collectible) and a.active and not a.collected]

    for _ in range(rounds):
        if outcome_of(sim):
            break
        ap.wait_for(lambda: (mi.player_can_walk and pending()) or outcome_of(sim)
                    or (not mi.player_can_walk and waiting_to_be_faced(sim)), limit=240)
        if not mi.player_can_walk and waiting_to_be_faced(sim):
            face_what_is_waited_for(ap)
            continue
        todo = pending()
        if not todo:
            continue
        c = todo[0]
        if c.collect_with_left_hand or c.collect_with_right_hand:
            go_to(ap, *c.position, within=max(3.0, c.collide_radius - 4),
                  until=lambda: c.in_collide_range or outcome_of(sim))
            ap.wait_for(lambda: (mi.player_can_use_hands and c.in_collide_range) or outcome_of(sim),
                        limit=60)
            for _ in range(5):
                if c.collected or outcome_of(sim):
                    break
                sim.hand('L')
                sim.step(1.0)
        else:
            go_to(ap, *c.position, until=lambda: c.collected or outcome_of(sim))
    sim.run_until(lambda: outcome_of(sim) is not None, limit=60)
    return outcome_of(sim) or 'stuck'



def play_level_5a(sim: Sim, orientation: str = 'landscape') -> str:
    """ps2_5a "Hometime": come to Papa, hold the phone up the way he wants,
    shake it, walk to the gramophone and drop the needle."""
    ap = Autopilot(sim)
    mi = sim.interpreter
    lv = sim.level

    def agent(name):
        return lv.agent(name)

    def done():
        return outcome_of(sim)

    come = agent('introA_come_here_prompt')
    ap.wait_for(lambda: (mi.player_can_walk and come.active) or done(), limit=120)
    go_to(ap, *come.position, until=lambda: come.in_collide_range or not come.active or done())
    ap.wait_for(lambda: agent('hold_it_up_prompt').active or done(), limit=120)
    sim.step(1.0)
    sim.rotate(orientation)
    shake = agent('intro2_collectible')
    ap.wait_for(lambda: (shake.active and shake.in_collide_range) or done(), limit=120)
    sim.step(0.5)
    for _ in range(7):                       # decision 14: seven shakes
        sim.shake()
        sim.step(0.2)
    machine = agent('machine')
    ap.wait_for(lambda: (mi.player_can_walk and machine.active) or done(), limit=180)
    go_to(ap, *machine.position, within=max(3.0, machine.collide_radius - 4),
          until=lambda: machine.in_collide_range or done())
    needle = agent('drop_the_needle_prompt')
    ap.wait_for(lambda: (needle.active and mi.player_can_use_hands) or done(), limit=120)
    sim.hand('L')
    sim.run_until(lambda: done() is not None, limit=120)
    return done() or 'stuck'


def play_level_6(sim: Sim, limit: float = 600.0) -> str:
    """ps2_6, the pier: walk to the shooting stand, shoot every duck (turning
    to whichever live one is nearest), then run for the door."""
    from .entities.enemy import Enemy   # noqa: PLC0415
    ap = Autopilot(sim)
    mi = sim.interpreter
    lv = sim.level
    p = sim.player

    def done():
        return outcome_of(sim)

    stand = lv.agent('fair_stand')
    ap.wait_for(lambda: (mi.player_can_walk and stand.active) or done(), limit=120)
    go_to(ap, *stand.position, until=lambda: stand.collected or not stand.active or done())
    ap.wait_for(lambda: p.left_hand_action == 'shoot' or done(), limit=120)
    end = sim.now + limit
    while not done() and sim.now < end:
        if p.left_hand_action != 'shoot':
            break
        ducks = [a for a in lv.agents if isinstance(a, Enemy) and a.active and not a.dead]
        if not ducks:
            sim.step(0.1)
            continue
        d = min(ducks, key=lambda a: ap.distance_to(*a.position))
        ap.face(*d.position, rate=math.radians(360))
        if d.is_in_shooting_range and mi.player_can_use_hands and p.reload_timer > p.reload_time:
            sim.hand('L')
        sim.step(0.05)
    door = lv.agent('door')
    ap.wait_for(lambda: (door.active and mi.player_can_walk) or done(), limit=60)
    go_to(ap, *door.position, until=lambda: door.collected or done())
    sim.run_until(lambda: done() is not None, limit=60)
    return done() or 'stuck'


def play_level_7(sim: Sim, limit: float = 600.0) -> str:
    """ps2_7, the burning house: face the cat so it runs, follow it round the
    fire walls, take each memory it leads to, climb out of the holes with
    both hands, and run through the smoke to the door."""
    from .entities.collectible import Collectible   # noqa: PLC0415
    ap = Autopilot(sim)
    mi = sim.interpreter
    lv = sim.level
    p = sim.player

    def done():
        return outcome_of(sim)

    cats = [lv.agent(n) for n in ('cat1', 'cat2', 'cat3', 'cat4')]
    cat1 = cats[0]
    ap.wait_for(lambda: (mi.player_can_walk and cat1.active) or done(), limit=120)
    while not done() and cat1.active and not cat1.has_path:
        if ap.distance_to(*cat1.position) > 45:
            go_to(ap, *cat1.position, within=45, until=lambda: cat1.has_path or done())
        ap.face(*cat1.position)
        sim.step(0.2)
    end = sim.now + limit
    hand = 'L'
    while not done() and sim.now < end:
        holes = [a for a in lv.agents if a.name.startswith('hand_release') and a.active]
        if holes and not mi.player_can_walk:
            if mi.player_can_use_hands and p.reload_timer > p.reload_time:
                sim.hand(hand)
                hand = 'R' if hand == 'L' else 'L'
            sim.step(0.1)
            continue
        if not mi.player_can_walk:
            sim.step(0.1)
            continue
        goal = [a for a in lv.agents if isinstance(a, Collectible) and a.active
                and not a.collected and not a.name.startswith(('hand_release', 'detector'))]
        if goal:
            g = goal[0]
            if ap.distance_to(*g.position) <= max(3.0, g.collide_radius - 4):
                sim.step(0.2)
                continue
            go_to(ap, *g.position, within=max(3.0, g.collide_radius - 4),
                  until=lambda: g.collected or not g.active or done()
                  or not mi.player_can_walk, limit=4)
            continue
        live = [c for c in cats if c.active]
        if live:
            c = live[-1]
            if ap.distance_to(*c.position) <= 10:
                sim.step(0.2)                    # with the cat: wait for it to move
                continue
            go_to(ap, *c.position, within=10,
                  until=lambda: done() or not mi.player_can_walk
                  or any(isinstance(a, Collectible) and a.active and not a.collected
                         and not a.name.startswith(('hand_release', 'detector'))
                         for a in lv.agents), limit=2)
            continue
        sim.step(0.1)
    sim.run_until(lambda: done() is not None, limit=60)
    return done() or 'stuck'


def play_level_8(sim: Sim, rounds: int = 80, clap_after: float = 2.0) -> str:
    """ps2_8, the ice: every memory in turn; when the penguin has stood close
    for `clap_after` seconds, clap it away before the ice gives."""
    from .entities.collectible import Collectible   # noqa: PLC0415
    ap = Autopilot(sim)
    mi = sim.interpreter
    lv = sim.level
    penguin = lv.agent('penguin')
    close_since = [None]

    def watch():
        if penguin is not None and penguin.active and penguin.state == 202:
            if close_since[0] is None:
                close_since[0] = sim.now
            elif sim.now - close_since[0] >= clap_after and mi.player_can_use_hands:
                sim.clap()
                close_since[0] = None
        else:
            close_since[0] = None
        return False

    def pending():
        return [a for a in lv.agents
                if isinstance(a, Collectible) and a.active and not a.collected]

    for _ in range(rounds):
        if outcome_of(sim):
            break
        ap.wait_for(lambda: watch() or (mi.player_can_walk and pending()) or outcome_of(sim),
                    limit=240)
        todo = pending()
        if not todo:
            continue
        c = todo[0]
        go_to(ap, *c.position, within=max(3.0, c.collide_radius - 4),
              until=lambda: watch() or c.collected or not c.active or outcome_of(sim), limit=4)
    sim.run_until(lambda: watch() or outcome_of(sim) is not None, limit=60)
    return outcome_of(sim) or 'stuck'


def _steam_ahead(sim: Sim, ahead: float = 12.0):
    """The active deadly/safe floor the next steps would enter, if any."""
    p = sim.player
    px, py = p.position
    ox, oy = p.orientation_vector
    for f in sim.level.floors[1:]:
        if f.deadly_time == 0 or f.safe_time == 0:
            continue
        if not f.active and f.exited:
            continue                      # passed already, and switched off behind you
        rx, ry, rw, rh = _std(f.rect)
        for d in (3.0, ahead / 2, ahead):
            x, y = px + ox * d, py + oy * d
            if rx - 3 <= x < rx + rw + 3 and ry - 3 <= y < ry + rh + 3:
                return f
    return None


def walk_timing_steam(ap: Autopilot, x: float, y: float, within: float = 6.0,
                      until=None, limit: int = 600) -> bool:
    """Walk straight to (x, y), holding back from a steam vent until it has
    just gone off, then crossing - what the Geiger counter is for."""
    sim = ap.sim
    waited = {}
    for _ in range(limit):
        if ap.distance_to(x, y) <= within or (until is not None and until()):
            return True
        ap.face(x, y)
        f = _steam_ahead(sim)
        if f is not None and not f.active:
            # a vent not started yet: its explosion is coming - wait for it
            waited[id(f)] = waited.get(id(f), 0.0) + 0.05
            if waited[id(f)] < 8.0:
                sim.step(0.05)
                continue
            f = None
        if f is not None and not f.player_is_on_surface:
            _, _, w, h = _std(f.rect)
            ox, oy = sim.player.orientation_vector
            across = abs(ox) * w + abs(oy) * h              # its width along the way
            crossing = (across + 6.0) / 12.5 + 0.2          # 12.5 px/s walking
            left = f.safe_time - f.safe_timer
            if f.is_lethal or left < crossing:
                sim.step(0.05)
                continue
        ap.step_once()
    return ap.distance_to(x, y) <= within


def play_level_9(sim: Sim, limit: float = 600.0) -> str:
    """ps2_9, the submarine: the sirens one after another down the corridor,
    through each steam vent while it is off; free the trapped man with the
    left hand; follow his beacon; the door."""
    from .entities.collectible import Collectible   # noqa: PLC0415
    ap = Autopilot(sim)
    mi = sim.interpreter
    lv = sim.level
    man = lv.agent('man_trapped')
    end = sim.now + limit
    while not outcome_of(sim) and sim.now < end:
        if not mi.player_can_walk:
            if man.active and man.in_collide_range and mi.player_can_use_hands:
                sim.hand('L')
            sim.step(0.1)
            continue
        if man.active:
            if not man.in_collide_range:
                walk_timing_steam(ap, man.position[0], man.position[1] - 12, within=4,
                                  until=lambda: man.in_collide_range or not man.active, limit=80)
            elif mi.player_can_use_hands:
                sim.hand('L')
                sim.step(0.5)
            else:
                sim.step(0.1)
            continue
        goal = [a for a in lv.agents if isinstance(a, Collectible) and a.active and not a.collected]
        if goal:
            g = goal[0]
            gx, gy = g.position
            px, py = sim.player.position
            d = math.hypot(gx - px, gy - py)
            reach = max(3.0, g.collide_radius - 4)
            # wait at the edge of its reach - unless that is inside a vent
            if d > reach:
                sx, sy = gx - (gx - px) / d * reach, gy - (gy - py) / d * reach
            else:
                sx, sy = px, py
            if any(f.active and f.deadly_time and _inside([_std(f.rect)], sx, sy)
                   for f in lv.floors[1:]):
                sx, sy, reach = gx, gy, 3.0
            if ap.distance_to(sx, sy) <= max(3.0, reach if (sx, sy) == (gx, gy) else 3.0):
                sim.step(0.2)
                continue
            walk_timing_steam(ap, sx, sy, within=3.0,
                              until=lambda: g.collected or not g.active or outcome_of(sim)
                              or not mi.player_can_walk, limit=80)
            continue
        beacon = next((a for a in (lv.agent('beacon'), lv.agent('beacon2')) if a.active), None)
        if beacon is not None and ap.distance_to(*beacon.position) > 10:
            walk_timing_steam(ap, *beacon.position, within=10,
                              until=lambda: not beacon.active or outcome_of(sim)
                              or not mi.player_can_walk, limit=20)
            continue
        sim.step(0.2)
    sim.run_until(lambda: outcome_of(sim) is not None, limit=60)
    return outcome_of(sim) or 'stuck'


def play_level_10(sim: Sim, limit: float = 600.0, margin: float = 3.0) -> str:
    """ps2_10, the abyss: each answering machine in turn and the picture, by
    a route that keeps off the edge; then the door."""
    from .entities.collectible import Collectible   # noqa: PLC0415
    ap = Autopilot(sim)
    mi = sim.interpreter
    lv = sim.level
    order = ('ansaphone1', 'ansaphone2', 'picture', 'ansaphone3', 'door')
    end = sim.now + limit
    while not outcome_of(sim) and sim.now < end:
        if not mi.player_can_walk:
            sim.step(0.1)
            continue
        goal = [lv.agent(n) for n in order
                if lv.agent(n).active and not lv.agent(n).collected]
        if not goal:
            sim.step(0.2)
            continue
        g = goal[0]
        reach = max(3.0, g.collide_radius - 4)
        if ap.distance_to(*g.position) <= reach:
            sim.step(0.2)
            continue
        go_to(ap, *g.position, within=reach, margin=margin,
              until=lambda: g.collected or not g.active or outcome_of(sim)
              or not mi.player_can_walk, limit=6)
    sim.run_until(lambda: outcome_of(sim) is not None, limit=60)
    return outcome_of(sim) or 'stuck'


# ------------------------------------------------------------------ M6
def shoot_nearest(ap: Autopilot, within: float = 160.0) -> bool:
    """Turn to the nearest live, active enemy within `within` px and fire
    when it is in the cone and the gun has reloaded.  True if one was there."""
    from .entities.enemy import Enemy   # noqa: PLC0415
    sim = ap.sim
    p = sim.player
    live = [a for a in sim.level.agents if isinstance(a, Enemy) and a.active and not a.dead
            and ap.distance_to(*a.position) <= within]
    if not live or p.left_hand_action != 'shoot':
        return False
    e = min(live, key=lambda a: ap.distance_to(*a.position))
    ap.face(*e.position, rate=math.radians(360))
    if e.is_in_shooting_range and sim.interpreter.player_can_use_hands \
            and p.reload_timer > p.reload_time:
        sim.hand('L')
    return True


def _collect(ap: Autopilot, c, until=None, margin: float = 8.0) -> None:
    """Up to a collectible (and a hand for one that wants it)."""
    sim, mi = ap.sim, ap.sim.interpreter
    reach = max(3.0, c.collide_radius - 4)
    if c.collect_with_left_hand or c.collect_with_right_hand:
        if not c.in_collide_range:
            go_to(ap, *c.position, within=min(reach, 12.0), margin=margin,
                  until=lambda: c.in_collide_range or not c.active or outcome_of(sim)
                  or (until is not None and until()), limit=4)
        if c.in_collide_range and mi.player_can_use_hands and \
                sim.player.reload_timer > sim.player.reload_time:
            sim.hand('L')
            sim.step(0.3)
        else:
            sim.step(0.1)
        return
    if c.collect_with_shake:
        if c.in_collide_range:
            sim.shake()
        sim.step(0.3)
        return
    if ap.distance_to(*c.position) <= reach:
        sim.step(0.2)
        return
    go_to(ap, *c.position, within=reach, margin=margin,
          until=lambda: c.collected or not c.active or outcome_of(sim)
          or (until is not None and until()), limit=4)


def _pending(sim: Sim, skip=()):
    from .entities.collectible import Collectible   # noqa: PLC0415
    return [a for a in sim.level.agents if isinstance(a, Collectible) and a.active
            and not a.collected and a.name not in skip]


def play_level_11a(sim: Sim, limit: float = 600.0) -> str:
    """ps2_11a: come to him, turn the hat over, put it on, walk to the fountain."""
    ap = Autopilot(sim)
    mi = sim.interpreter
    fountain = sim.level.agent('fountain')
    end = sim.now + limit
    while not outcome_of(sim) and sim.now < end:
        todo = _pending(sim)
        if todo and (mi.player_can_walk or todo[0].in_collide_range):
            _collect(ap, todo[0])
            continue
        if mi.player_can_walk and sim.level.agent('come_to_fountain_prompt').active \
                and not fountain.in_collide_range:
            go_to(ap, *fountain.position, within=20,
                  until=lambda: fountain.in_collide_range or outcome_of(sim), limit=6)
            continue
        sim.step(0.2)
    sim.run_until(lambda: outcome_of(sim) is not None, limit=60)
    return outcome_of(sim) or 'stuck'


def play_level_11b(sim: Sim, limit: float = 900.0) -> str:
    """ps2_11b, the zoo: every memory in turn, soaking any forgotten man that
    comes close; the gramophone by hand."""
    ap = Autopilot(sim)
    mi = sim.interpreter
    end = sim.now + limit
    while not outcome_of(sim) and sim.now < end:
        if shoot_nearest(ap, within=70.0):
            sim.step(0.05)
            continue
        todo = _pending(sim)
        if todo and (mi.player_can_walk or todo[0].in_collide_range):
            _collect(ap, todo[0], until=lambda: shoot_needed(ap))
            continue
        sim.step(0.1)
    sim.run_until(lambda: outcome_of(sim) is not None, limit=60)
    return outcome_of(sim) or 'stuck'


def shoot_needed(ap: Autopilot, within: float = 70.0) -> bool:
    from .entities.enemy import Enemy   # noqa: PLC0415
    return ap.sim.player.left_hand_action == 'shoot' and any(
        isinstance(a, Enemy) and a.active and not a.dead and ap.distance_to(*a.position) <= within
        for a in ap.sim.level.agents)


def play_level_13(sim: Sim, limit: float = 900.0) -> str:
    """ps2_13, under the sea: each bubble of air and each memory in its case,
    the easter egg on the way, then the needle and the shake."""
    ap = Autopilot(sim)
    mi = sim.interpreter
    end = sim.now + limit
    while not outcome_of(sim) and sim.now < end:
        todo = _pending(sim)
        air = sim.player.underwater_duration
        # the level's own order; the next bubble first when the air is going;
        # the easter egg only when nothing else is out and there is air to spare
        if air > 12.0:
            todo.sort(key=lambda a: not a.name.startswith('note'))
        if todo and todo[0].name == 'easter_egg' and (len(todo) > 1 or air > 6.0):
            todo = todo[1:] if len(todo) > 1 else []
        if todo and (mi.player_can_walk or todo[0].in_collide_range):
            _collect(ap, todo[0], margin=6.0)
            continue
        sim.step(0.1)
    sim.run_until(lambda: outcome_of(sim) is not None, limit=60)
    return outcome_of(sim) or 'stuck'


def play_level_12(sim: Sim, limit: float = 900.0) -> str:
    """ps2_12, the train: board it, shoot every duck that comes for you on
    the way up, then lift the needle and shake."""
    ap = Autopilot(sim)
    mi = sim.interpreter
    start = sim.level.agent('train_start')
    end = sim.now + limit
    while not outcome_of(sim) and sim.now < end:
        if not sim.player.has_path and start.active:
            if mi.player_can_walk:
                go_to(ap, *start.position, within=5,
                      until=lambda: start.in_collide_range or not start.active, limit=6)
            else:
                sim.step(0.1)
            continue
        if shoot_nearest(ap, within=120.0):
            sim.step(0.05)
            continue
        todo = [c for c in _pending(sim) if c.name in ('pre_door', 'door')]
        if todo:
            _collect(ap, todo[0])
            continue
        sim.step(0.1)
    sim.run_until(lambda: outcome_of(sim) is not None, limit=60)
    return outcome_of(sim) or 'stuck'


# ------------------------------------------------------------------ M7
def _live(a) -> bool:
    """Active, alive and somewhere (an enemy sent home from home is not)."""
    return a.active and not a.dead and not math.isnan(a.position[0])


def _stand_near(ap: Autopilot, x: float, y: float, r: float, margin: float = 8.0):
    """A free spot `r` px from (x, y), the nearest to the player."""
    rects = hazards(ap.sim.level, margin)
    best = None
    for k in range(24):
        t = 2 * math.pi * k / 24
        c = (x + r * math.cos(t), y + r * math.sin(t))
        if _inside(rects, *c):
            continue
        d = ap.distance_to(*c)
        if best is None or d < best[0]:
            best = (d, c)
    return best[1] if best else (x, y)


def _seg(c, a, b) -> float:
    """Distance from c to the segment a-b."""
    ax, ay = a
    dx, dy = b[0] - ax, b[1] - ay
    n = dx * dx + dy * dy
    t = 0.0 if n == 0 else max(0.0, min(1.0, ((c[0] - ax) * dx + (c[1] - ay) * dy) / n))
    return math.hypot(c[0] - (ax + t * dx), c[1] - (ay + t * dy))


def _floor(sim: Sim, name: str):
    return next(f for f in sim.level.floors if f.name == name)


def play_level_14(sim: Sim, limit: float = 900.0) -> str:
    """ps2_14, the burning house: put out each fire door with the extinguisher
    (left hand) and smash the memory behind it; shake the extinguisher where
    you are told to and face the fire; the fireworks and the oil can the same
    way; then the hall, the last memory, the needle and the shake."""
    from .entities.enemy import Enemy   # noqa: PLC0415
    ap = Autopilot(sim)
    mi = sim.interpreter
    p = sim.player
    faced: set = set()
    end = sim.now + limit
    while not outcome_of(sim) and sim.now < end:
        # the house coming down behind you (it chases from its first sound
        # on): straight for the last memory, nothing else
        boom, last = sim.level.agent('explosions'), sim.level.agent('memory5')
        if (boom is not None and boom.active and last is not None and last.active
                and not last.collected and mi.player_can_walk):
            _collect(ap, last)
            continue
        fires = [a for a in sim.level.agents if isinstance(a, Enemy) and _live(a)
                 and a.has_trigger('OnStab') and a.chase_speed == 0]
        if fires and mi.player_can_walk:
            e = min(fires, key=lambda a: ap.distance_to(*a.position))
            if ap.distance_to(*e.position) > 24:
                go_to(ap, *_stand_near(ap, *e.position, 18), within=4,
                      until=lambda: outcome_of(sim) or not mi.player_can_walk, limit=4)
                continue
            ap.face(*e.position, rate=math.radians(360))
            if e.is_in_beating_range and mi.player_can_use_hands \
                    and p.reload_timer > p.reload_time and p.left_hand_action == 'beat':
                sim.hand('L')
            sim.step(0.1)
            continue
        if any(a.active and a.has_trigger('OnShake') and a.in_collide_range
               for a in sim.level.agents):
            sim.shake()
            sim.step(0.3)
            continue
        for a in sim.level.agents:
            if a.active and a.is_in_shooting_range:
                faced.add(a.name)
        waited = [a for a in sim.level.agents if a.active and a.has_trigger('OnEnteringShootRange')
                  and not a.is_in_shooting_range and a.collide_radius > 0 and a.name not in faced]
        if waited:
            a = min(waited, key=lambda a: ap.distance_to(*a.position))
            reach = min(a.shoot_range - 8, 26)
            if ap.distance_to(*a.position) > reach + 4 and mi.player_can_walk:
                go_to(ap, *_stand_near(ap, *a.position, reach), within=4,
                      until=lambda: outcome_of(sim) or not mi.player_can_walk, limit=4)
                continue
            ap.face(*a.position, rate=math.radians(360))
            sim.step(0.2)
            continue
        todo = _pending(sim)
        if not todo and ap.active('memory4') and mi.player_can_walk:
            # the last memory's music, ahead of you on the way to the hall
            go_to(ap, 148, -112, within=6,
                  until=lambda: outcome_of(sim) or not ap.active('memory4'), limit=4)
            continue
        if todo and (mi.player_can_walk or todo[0].in_collide_range):
            _collect(ap, todo[0])
            continue
        sim.step(0.1)
    sim.run_until(lambda: outcome_of(sim) is not None, limit=60)
    return outcome_of(sim) or 'stuck'


def play_level_15(sim: Sim, limit: float = 1200.0) -> str:
    """ps2_15, the ice: creep up on each polar bear while it stands still and
    knife it (right hand); keep away from one that moves, and step back from
    each kill, which the others heard; clap a penguin off; at the music, jump
    three times quickly to break the ice; the needle and the shake."""
    from .entities.enemy import Enemy   # noqa: PLC0415
    from .entities.follower import CLOSE, Follower   # noqa: PLC0415
    ap = Autopilot(sim)
    mi = sim.interpreter
    p = sim.player
    jump_floor = _floor(sim, 'surface_jump')
    music = sim.level.agent('forgetfulman9')

    def penguin_close():
        return any(isinstance(f, Follower) and f.active and f.state == CLOSE
                   for f in sim.level.agents)

    def away_from(x, y, d):
        px, py = p.position
        dx, dy = px - x, py - y
        n = math.hypot(dx, dy) or 1.0
        rx, ry, rw, rh = sim.level.rect
        tx = min(max(px + d * dx / n, rx + 110), rx + rw - 110)
        ty = min(max(py + d * dy / n, ry + 110), ry + rh - 110)
        ap.walk_to(tx, ty, within=4, limit=max(3, int(d / 5)))

    end = sim.now + limit
    while not outcome_of(sim) and sim.now < end:
        if penguin_close() and mi.player_can_use_hands:
            sim.clap()
            sim.step(0.3)
            continue
        bears = [a for a in sim.level.agents if isinstance(a, Enemy) and _live(a)]
        moving = [a for a in bears if not a.is_still() and ap.distance_to(*a.position) < 50]
        if moving and mi.player_can_walk:
            m = min(moving, key=lambda a: ap.distance_to(*a.position))
            away_from(*m.position, 25)
            continue
        still = [a for a in bears if a.is_still()]
        if still and mi.player_can_walk:
            e = min(still, key=lambda a: ap.distance_to(*a.position))
            if ap.distance_to(*e.position) > 22:
                def danger(e=e):
                    return outcome_of(sim) or not e.is_still() or penguin_close() or any(
                        isinstance(a, Enemy) and _live(a) and not a.is_still()
                        and ap.distance_to(*a.position) < 50 for a in sim.level.agents)
                go_to(ap, *e.position, within=22, margin=4, until=danger, limit=2)
                continue
            ap.face(*e.position, rate=math.radians(360))
            if e.is_in_beating_range and e.is_still() and mi.player_can_use_hands \
                    and p.reload_timer > p.reload_time:
                sim.hand('R')
                sim.step(0.1)
                if e.dead:
                    away_from(*e.position, 30)
                continue
            sim.step(0.1)
            continue
        if music.active and not music.in_collide_range and mi.player_can_walk:
            go_to(ap, *music.position, within=10, margin=4,
                  until=lambda: outcome_of(sim) or music.in_collide_range or penguin_close(),
                  limit=4)
            continue
        if mi.player_can_jump and jump_floor.active:
            for _ in range(3):
                mi.jump()
                sim.bus.update(sim.now)
                sim.step(0.3)
            sim.step(1.0)
            continue
        todo = _pending(sim)
        if todo and (mi.player_can_walk or todo[0].in_collide_range):
            _collect(ap, todo[0], margin=4)
            continue
        sim.step(0.1)
    sim.run_until(lambda: outcome_of(sim) is not None, limit=60)
    return outcome_of(sim) or 'stuck'


def play_level_16(sim: Sim, limit: float = 900.0) -> str:
    """ps2_16, the glass floor: walk only in the thunder (you hear it fade, so
    no step starts as it ends), and only while the snufflehawks are settled;
    smash a memory as a thunder begins with none of them near, then slip
    away from the spot they were told about, clear of their ways there and
    home; the last one against the countdown; the needle and the button."""
    from .entities.enemy import Enemy   # noqa: PLC0415
    ap = Autopilot(sim)
    mi = sim.interpreter
    p = sim.player
    glass = _floor(sim, 'surface1')
    thunder = sim.level.agent('thunder_on')
    st = {'quiet_since': None, 'spot': None, 'to': None, 'count_since': None}

    def quiet():
        if glass.active:
            return False
        s = thunder.sound
        if thunder.active and s is not None and s.playing:
            return s.duration - s.offset > 1.0
        return True

    def hogs():
        return [a for a in sim.level.agents if isinstance(a, Enemy) and _live(a)]

    def settled():
        return all(h.state in (0, 6) for h in hogs())

    def near(r=22):
        return [h for h in hogs() if ap.distance_to(*h.position) < r and h.state not in (0, 10)]

    def hurry():
        if not ap.active('countdown'):
            st['count_since'] = None
            return False
        if st['count_since'] is None:
            st['count_since'] = sim.now
        return sim.now - st['count_since'] > 16.0

    def ways(a, b, out):
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        for i in range(1, int(d // 12) + 1):
            t = i * 12 / d
            out.append((a[0] + (b[0] - a[0]) * t - 18, a[1] + (b[1] - a[1]) * t - 18, 36, 36))

    def hog_boxes():
        out = []
        for h in hogs():
            hx, hy = h.position
            out.append((hx - 22, hy - 22, 44, 44))
            if h.state in (4, 5, 8) or (h.state == 10 and h.has_wanted_position):
                ways(h.position, h.wanted_position, out)
                gx, gy = h.wanted_position
                out.append((gx - 22, gy - 22, 44, 44))
            if h.state == 9 and h.initial_position is not None:
                ways(h.position, h.initial_position, out)
        return out

    def flee_target(spot):
        walls = hazards(sim.level, 6)
        rx, ry, rw, rh = sim.level.rect
        best = None
        for k in range(16):
            t = 2 * math.pi * k / 16
            c = (spot[0] + 45 * math.cos(t), spot[1] + 45 * math.sin(t))
            if not (rx + 15 < c[0] < rx + rw - 15 and ry + 15 < c[1] < ry + rh - 15):
                continue
            if _inside(walls, *c) or _inside(hog_boxes(), *c):
                continue
            ds = [999.0]
            for h in hogs():
                ds.append(_seg(c, h.position, spot))
                if h.initial_position is not None:
                    ds.append(_seg(c, spot, h.initial_position))
            if best is None or min(ds) > best[0]:
                best = (min(ds), c)
        return best[1] if best else None

    end = sim.now + limit
    while not outcome_of(sim) and sim.now < end:
        if quiet():
            if st['quiet_since'] is None:
                st['quiet_since'] = sim.now
        else:
            st['quiet_since'] = None
        todo = _pending(sim)
        if todo and todo[0].name in ('pre_door', 'door'):
            _collect(ap, todo[0])
            continue
        close = near()
        spot = st['spot']
        if spot is not None and ap.distance_to(*spot) < 35 and (quiet() or close) \
                and mi.player_can_walk:
            if st['to'] is None:
                st['to'] = flee_target(spot)
            if st['to'] is None:
                st['spot'] = None
                continue
            go_to(ap, *st['to'], within=4, margin=6, limit=2, extra=hog_boxes,
                  until=lambda: outcome_of(sim) or not (quiet() or near()))
            if ap.distance_to(*spot) >= 35:
                st['spot'] = None
            continue
        if close and mi.player_can_walk:
            h = min(close, key=lambda h: ap.distance_to(*h.position))
            px, py = p.position
            ox, oy = h.orientation_vector
            ax, ay = -oy, ox                      # step aside, across its way
            if (px - h.position[0]) * ax + (py - h.position[1]) * ay < 0:
                ax, ay = -ax, -ay
            ap.walk_to(px + 15 * ax, py + 15 * ay, within=4, limit=3)
            continue
        if todo and (mi.player_can_walk or todo[0].in_collide_range):
            c = todo[0]
            rush = hurry()
            if c.in_collide_range:
                fresh = st['quiet_since'] is not None and sim.now - st['quiet_since'] < 1.0
                clear = all(ap.distance_to(*h.position) > 70 for h in hogs())
                if ((fresh and clear) or rush) and mi.player_can_use_hands \
                        and p.reload_timer > p.reload_time:
                    sim.hand('L')
                    sim.step(0.2)
                    st['spot'], st['to'] = p.position, None
                else:
                    sim.step(0.05)
                continue
            if (not quiet() or not settled()) and not rush:
                sim.step(0.05)
                continue
            go_to(ap, *c.position, within=min(12.0, c.collide_radius - 4), margin=6,
                  limit=2, extra=hog_boxes,
                  until=lambda: c.in_collide_range or outcome_of(sim) or near()
                  or (not hurry() and (not quiet() or not settled())))
            continue
        sim.step(0.05)
    sim.run_until(lambda: outcome_of(sim) is not None, limit=60)
    return outcome_of(sim) or 'stuck'


def _on_vent(sim: Sim) -> bool:
    return any(f.deadly_time and f.player_is_on_surface for f in sim.level.floors[1:])


def play_level_17(sim: Sim, limit: float = 900.0) -> str:
    """ps2_17, the broken memories: the answering machines along the abyss,
    shooting each duck that comes; then the submarine's sirens, through each
    steam vent while it is off (never stopping in one), shooting what comes
    for you; the door comes by itself."""
    from .entities.enemy import Enemy   # noqa: PLC0415
    from .entities.follower import CLOSE, Follower   # noqa: PLC0415
    ap = Autopilot(sim)
    mi = sim.interpreter
    p = sim.player
    order = ('ansaphone1', 'ansaphone2', 'siren1', 'siren2', 'siren3', 'siren4')

    def threats(within=90.0):
        return [a for a in sim.level.agents if isinstance(a, (Enemy, Follower)) and _live(a)
                and ap.distance_to(*a.position) <= within]

    end = sim.now + limit
    while not outcome_of(sim) and sim.now < end:
        if mi.player_can_use_hands and p.right_hand_action != 'beat' and any(
                isinstance(f, Follower) and f.active and f.state == CLOSE for f in sim.level.agents):
            sim.clap()
            sim.step(0.3)
            continue
        t = threats() if (p.left_hand_action == 'shoot' and not _on_vent(sim)) else []
        if t:
            e = min(t, key=lambda a: ap.distance_to(*a.position))
            ap.face(*e.position, rate=math.radians(360))
            if e.is_in_shooting_range and mi.player_can_use_hands and p.reload_timer > p.reload_time:
                sim.hand('L')
            sim.step(0.05)
            continue
        if not mi.player_can_walk:
            sim.step(0.1)
            continue
        goal = [sim.level.agent(n) for n in order
                if sim.level.agent(n).active and not sim.level.agent(n).collected]
        if not goal:
            sim.step(0.2)
            continue
        g = goal[0]
        reach = max(3.0, g.collide_radius - 4)
        gx, gy = g.position
        px, py = p.position
        d = math.hypot(gx - px, gy - py)
        # wait at the edge of its reach - unless that is inside a vent
        sx, sy = (gx - (gx - px) / d * reach, gy - (gy - py) / d * reach) if d > reach else (px, py)
        if _on_vent(sim) or any(f.deadly_time and _inside([_std(f.rect)], sx, sy)
                                for f in sim.level.floors[1:]):
            sx, sy = gx, gy
        if ap.distance_to(sx, sy) <= 3.0:
            sim.step(0.2)
            continue

        def stop(g=g):
            return (g.collected or not g.active or outcome_of(sim) or not mi.player_can_walk
                    or (not _on_vent(sim) and p.left_hand_action == 'shoot' and bool(threats())))
        if g.name.startswith('siren'):
            walk_timing_steam(ap, sx, sy, within=3.0, until=stop, limit=20)
        else:
            go_to(ap, *g.position, within=reach, margin=3, until=stop, limit=4)
    sim.run_until(lambda: outcome_of(sim) is not None, limit=90)
    return outcome_of(sim) or 'stuck'


# ------------------------------------------------------------------ M8
def play_level_18(sim: Sim, limit: float = 900.0) -> str:
    """ps2_18, Papa: soak whatever comes near with the water pistol (left
    hand) and pick up each memory; when Papa comes, face him and take his
    picture (the camera, right hand) as soon as he is within its reach - three
    times, never a wasted shot (that is the level's achievement)."""
    from .entities.enemy import Enemy   # noqa: PLC0415
    ap = Autopilot(sim)
    mi = sim.interpreter
    p = sim.player

    def papa():
        return [a for a in sim.level.agents if a.name.startswith('4_papa_') and _live(a)]

    def near(within=110.0):
        return [a for a in sim.level.agents if isinstance(a, Enemy) and _live(a)
                and not a.name.startswith('4_papa_') and ap.distance_to(*a.position) < within]

    end = sim.now + limit
    while not outcome_of(sim) and sim.now < end:
        if papa() and mi.player_can_use_hands and p.right_hand_action == 'beat':
            e = papa()[0]
            ap.face(*e.position, rate=math.radians(360))
            if e.is_in_beating_range and p.reload_timer > p.reload_time:
                sim.hand('R')
            sim.step(0.05)
            continue
        t = near()
        if t and p.left_hand_action == 'shoot' and mi.player_can_use_hands:
            e = min(t, key=lambda a: ap.distance_to(*a.position))
            ap.face(*e.position, rate=math.radians(360))
            if e.is_in_shooting_range and p.reload_timer > p.reload_time:
                sim.hand('L')
            sim.step(0.05)
            continue
        todo = _pending(sim)
        if todo and mi.player_can_walk:
            _collect(ap, todo[0], until=lambda: bool(near()) or bool(papa()))
            continue
        sim.step(0.1)
    sim.run_until(lambda: outcome_of(sim) is not None, limit=60)
    return outcome_of(sim) or 'stuck'


def play_level_18b(sim: Sim, limit: float = 300.0, shakes: int = 16) -> str:
    """ps2_18b, the way home: unplug the headphones when told to, then shake
    the record (the owner's 16 shakes: `afterCount=15` lets the 16th through)."""
    lv = sim.level
    unplugged = shaken = False
    end = sim.now + limit
    while not outcome_of(sim) and sim.now < end:
        if not unplugged and lv.agent('prompt_unplug').active:
            sim.bus.post('PGE_MESSAGE_AudioRouteChanged', {'unplugged': True})
            sim.bus.update(sim.now)
            unplugged = True
        if not shaken and lv.agent('instruction_shake').active:
            for _ in range(shakes):
                sim.shake()
                sim.step(0.3)
            shaken = True
        sim.step(0.1)
    return outcome_of(sim) or 'stuck'
