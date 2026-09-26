"""`PGEGameTracker` - the per-level counters the achievements read.

A singleton in the original that listens for the whole run (0x100016af4):

=================================  =========================================
``PGE_MESSAGE_LevelInited``        ``levelWasLoaded:`` - every load resets the
                                   counters; ``attempt`` is 1 for a new level,
                                   +1 for the same one again
``PGE_MESSAGE_PlayerMovedToPosition``  nbSteps +1 (every position update, not
                                   every footstep)
``PGE_MESSAGE_PlayerDidCollideAWall``  nbWallCollisions +1
``PGE_MESSAGE_PlayerDidTrip``      nbTrips +1
``PGE_ACTION_HandsClapped``        nbClaps +1 (every clap the controls post,
                                   even one the player then ignores)
``PGE_ACTION_RotatePlayerFromAngle``  totalRotation += |degrees|
``PGE_MESSAGE_PlayerDidShoot``     nbShoots +1
``PGE_MESSAGE_PlayerDidThrow``     nbThrows +1
``PGE_MESSAGE_AgentDidDie``        nbEnemiesKilled +1
``PGE_MESSAGE_FollowerDidDie``     nbEnemiesKilled +1 (the same selector)
``PGE_MESSAGE_PlayerDidBeat``      nbBeats +1
``PGE_MESSAGE_AlertAllEnemies``    enemiesAlerted +1
=================================  =========================================

``incrementCollectibles`` is called directly by ``-[PGECollectible collect]``
and ``endOfLoop``.  The Flurry analytics calls are N/A.
"""

from __future__ import annotations

import math

from ..core.messages import MessageBus, Params


class GameTracker:
    def __init__(self, bus: MessageBus) -> None:
        self.bus = bus
        self.level_name = ''
        self.levels_played = 0
        self.attempt = 0
        self.last_position = (0.0, 0.0)
        self._zero()
        for name, handler in (
            ('PGE_MESSAGE_LevelInited', self._level_was_loaded),
            ('PGE_MESSAGE_PlayerMovedToPosition', self._increment_step),
            ('PGE_MESSAGE_PlayerDidCollideAWall', lambda *_: self._inc('nb_wall_collisions')),
            ('PGE_MESSAGE_PlayerDidTrip', lambda *_: self._inc('nb_trips')),
            ('PGE_ACTION_HandsClapped', lambda *_: self._inc('nb_claps')),
            ('PGE_ACTION_RotatePlayerFromAngle', self._increment_rotation),
            ('PGE_MESSAGE_PlayerDidShoot', lambda *_: self._inc('nb_shoots')),
            ('PGE_MESSAGE_PlayerDidThrow', lambda *_: self._inc('nb_throws')),
            ('PGE_MESSAGE_AgentDidDie', lambda *_: self._inc('nb_enemies_killed')),
            ('PGE_MESSAGE_FollowerDidDie', lambda *_: self._inc('nb_enemies_killed')),
            ('PGE_MESSAGE_PlayerDidBeat', lambda *_: self._inc('nb_beats')),
            ('PGE_MESSAGE_AlertAllEnemies', lambda *_: self._inc('enemies_alerted')),
        ):
            bus.subscribe(name, handler)

    def _zero(self) -> None:
        self.nb_steps = 0
        self.collectibles_collected = 0
        self.nb_trips = 0
        self.nb_shoots = 0
        self.nb_throws = 0
        self.nb_enemies_killed = 0
        self.nb_penguins_killed = 0
        self.enemies_alerted = 0
        self.time_elapsed = 0.0
        self.saved_dilemma = False
        self.total_rotation = 0.0
        self.nb_wall_collisions = 0
        self.nb_beats = 0
        self.nb_claps = 0

    def _inc(self, attr: str) -> None:
        setattr(self, attr, getattr(self, attr) + 1)

    def increment_penguin_kills(self) -> None:
        """`incrementPenguinKills` (0x100017328): a penguin, and an enemy."""
        self.nb_penguins_killed += 1
        self.nb_enemies_killed += 1

    def reset_tracker(self, new_level: bool) -> None:
        """`resetTracker:` (0x100016f6c)."""
        self._zero()
        self.attempt = 1 if new_level else self.attempt + 1

    def _level_was_loaded(self, _n, params: Params) -> None:
        """`levelWasLoaded:` (0x10001736c)."""
        level = params.get('level')
        name = getattr(level, 'name', '') if level is not None else ''
        self.reset_tracker(name != self.level_name)
        self.level_name = name
        self.levels_played += 1

    def _increment_step(self, _n, params: Params) -> None:
        pos = params.get('position')
        if pos is not None:
            self.last_position = (float(pos[0]), float(pos[1]))
        self.nb_steps += 1

    def _increment_rotation(self, _n, params: Params) -> None:
        v = params.get('value', 0.0)
        try:
            v = float(v)
        except (TypeError, ValueError):
            v = 0.0
        self.total_rotation += abs(v * 180.0 / math.pi)

    def increment_collectibles(self) -> None:
        self.collectibles_collected += 1
