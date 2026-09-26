"""The achievements, as `PGEGameProgress` and `PGEngine` award them.

Game Center is N/A; what it was told is kept in the save (``gameCenter``: the
last percentage reported for each identifier) so the port can say it.  The
level achievements are also stored as the original stores them, a bool under
their own identifier once they reach 100 (``setPercentage:forAchievementWithName:``
0x100038c94).

``checkAchievementsForlevel:`` (0x100037284), called by ``loadLevelWithName:``
only on a win, one branch per level.  Recovered so far (M3, M4):

========  ================================  ==============  ==========
level     condition (the tracker)           achievement     act
========  ================================  ==============  ==========
ps2_1     nbTrips == 0                      level_1         act1 20
ps2_2     nbClaps > 9                       level_2         act1 40
ps2_3     collectiblesCollected == 5        level_3         act1 60
ps2_4     nbClaps == 0                      level_4         act1 80
ps2_5     timeElapsed <= 90 (float32)       level_5         act1 100
ps2_5a    (no branch)                       -               -
ps2_6     nbShoots < 22 and nbShoots ==     level_6, then   act2 15
          nbEnemiesKilled                   superBullet
ps2_7     timeElapsed <= 140                level_7         act2 30
ps2_8     nbClaps == 0                      level_8         act2 45
ps2_9     timeElapsed <= 130                level_9         act2 60
ps2_10    nbThrows < 21                     level_10        act2 75
ps2_11b   nbEnemiesKilled > 20 and          level_11b, then act2 100
          nbShoots == nbEnemiesKilled       superBullet
ps2_13    collectiblesCollected == 13       level_13        act3 30
ps2_12    nbEnemiesKilled > 19 and          level_12, then  act3 15
          nbShoots == nbEnemiesKilled       superBullet
========  ================================  ==============  ==========

The act percentage is reported on every win of that level, earned or not.
``timeElapsed`` is the level's clock: 0.05 s every level tick from the load,
the opening transition and speech included.

``checkSuperBullet`` (0x1000384e8) reports superBullet as 33 for level_6, 33
for level_12 and 34 for level_11b, added up over the ones completed.

``updateStatsAndAchievements`` (win and loss): totalSteps += the level's
nbSteps; ``setTotalSteps:`` reports 10000steps as totalSteps / 10000 and
1000000steps as totalSteps / **84390** - the second divisor is the original's
(it completes at 84,390 position updates, not a million).
``setMemoriesLost:`` reports memoryLost as memoriesLost / 24.
"""

from __future__ import annotations

import numpy as np

#: level -> (tracker test, achievement id, act id, act percentage)
LEVEL_CHECKS = {
    'ps2_1': (lambda t: t.nb_trips == 0, 'level_1', 'act1', 20.0),
    'ps2_2': (lambda t: t.nb_claps > 9, 'level_2', 'act1', 40.0),
    'ps2_3': (lambda t: t.collectibles_collected == 5, 'level_3', 'act1', 60.0),
    'ps2_4': (lambda t: t.nb_claps == 0, 'level_4', 'act1', 80.0),
    'ps2_5': (lambda t: not (np.float32(t.time_elapsed) > np.float32(90.0)), 'level_5', 'act1', 100.0),
    'ps2_6': (lambda t: t.nb_shoots < 22 and t.nb_shoots == t.nb_enemies_killed,
              'level_6', 'act2', 15.0),
    'ps2_7': (lambda t: not (np.float32(t.time_elapsed) > np.float32(140.0)), 'level_7', 'act2', 30.0),
    'ps2_8': (lambda t: t.nb_claps == 0, 'level_8', 'act2', 45.0),
    'ps2_9': (lambda t: not (np.float32(t.time_elapsed) > np.float32(130.0)), 'level_9', 'act2', 60.0),
    'ps2_10': (lambda t: t.nb_throws < 21, 'level_10', 'act2', 75.0),
    'ps2_11b': (lambda t: t.nb_enemies_killed > 20 and t.nb_shoots == t.nb_enemies_killed,
                'level_11b', 'act2', 100.0),
    'ps2_12': (lambda t: t.nb_enemies_killed > 19 and t.nb_shoots == t.nb_enemies_killed,
               'level_12', 'act3', 15.0),
    'ps2_13': (lambda t: t.collectibles_collected == 13, 'level_13', 'act3', 30.0),
    'ps2_14': (lambda t: t.collectibles_collected == 7, 'level_14', 'act3', 45.0),
    'ps2_15': (lambda t: t.nb_penguins_killed > 9, 'level_15', 'act3', 60.0),
    'ps2_16': (lambda t: t.enemies_alerted < 5, 'level_16', 'act3', 75.0),
    'ps2_17': (lambda t: not (np.float32(t.time_elapsed) > np.float32(240.0)), 'level_17', 'act3', 90.0),
    # act3 100 is submitted before the check here; the same in the end
    'ps2_18': (lambda t: t.nb_beats == 3, 'level_18', 'act3', 100.0),
}

#: the levels whose achievement also re-reports superBullet
SUPER_BULLET_LEVELS = ('ps2_6', 'ps2_11b', 'ps2_12')
SUPER_BULLET = (('level_6', 33), ('level_12', 33), ('level_11b', 34))

STEPS_10K = 10000.0
STEPS_1M_DIVISOR = 84390.0          # sic
MEMORIES_LOST_DIVISOR = 24.0


def check_achievements_for_level(progress, tracker, level: str) -> str | None:
    """`checkAchievementsForlevel:` - returns the level achievement earned, if any."""
    entry = LEVEL_CHECKS.get(level)
    earned = None
    if entry is not None:
        test, achievement, act, pct = entry
        if test(tracker):
            progress.set_percentage_for_achievement(100, achievement)
            earned = achievement
            if level in SUPER_BULLET_LEVELS:
                check_super_bullet(progress)
        progress.submit_achievement(act, pct)
    progress.synchronize()
    return earned


def check_super_bullet(progress) -> None:
    """`checkSuperBullet` (0x1000384e8)."""
    total = sum(n for name, n in SUPER_BULLET if progress.achievement_completed(name))
    progress.submit_achievement('superBullet', float(total))


def update_stats_and_achievements(progress, tracker) -> None:
    """`-[PGEngine updateStatsAndAchievements]`."""
    progress.total_steps = progress.total_steps + tracker.nb_steps
