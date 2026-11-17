import math
import random

from level import FIRE_SPAWNS, PALMS, PLAYER_START, WALK, WATERS
from ghosts import ghost_target
from pathfinding import bfs_distances, search

PLAYER_SPEED = 5.0
WATER_TIME = 8.0
FLEE_SLOW = 0.65
START_LIVES = 3
PTS_PALM, PTS_WATER, PTS_FIRE = 10, 50, 200

DIFFS = {"Easy": dict(fires=4, speed=1.8),
         "Medium": dict(fires=4, speed=3.6),
         "Hard": dict(fires=4, speed=5.4)}
DIFF_ORDER = list(DIFFS)


class Mover:
    def __init__(self, cell):
        self.cell = self.prev = cell
        self.t = 1.0

    @property
    def idle(self):
        return self.t >= 1.0

    def start(self, nxt):
        self.prev, self.cell, self.t = self.cell, nxt, 0.0

    def step(self, dt, speed):
        if self.t < 1.0:
            self.t = min(1.0, self.t + dt * speed)

    def nearest(self):
        return self.cell if self.t >= 0.5 else self.prev

    def pos(self):
        """Posisi grid (float)."""
        return (self.prev[0] + (self.cell[0] - self.prev[0]) * self.t,
                self.prev[1] + (self.cell[1] - self.prev[1]) * self.t)


class Fire:
    def __init__(self, idx, spawn, release):
        self.idx, self.spawn = idx, spawn
        self.m = Mover(spawn)
        self.state = "wait"
        self.timer = release
        self.flee, self.flee_t = None, 0.0
        self.heading = (0, 1)


class Core:
    def __init__(self, algo, diff, record=None):
        self.algo, self.diff_name, self.diff = algo, diff, DIFFS[diff]
        self.record = record or (lambda res: None)
        self.palms, self.waters = set(PALMS), set(WATERS)
        self.total = len(PALMS)
        self.score, self.lives = 0, START_LIVES
        self.over = None
        self.paused = False
        self.time, self.water = 0.0, 0.0
        self.last, self.last_res = {}, None
        self.events = []
        self._dist = (None, None)
        self.reset_positions()

    def reset_positions(self):
        self.player = Mover(PLAYER_START)
        self.dir = self.want = (0, 0)
        self.face = (0, -1)
        self.fires = [Fire(i, FIRE_SPAWNS[i % len(FIRE_SPAWNS)], 1.0 + i * 1.5)
                      for i in range(self.diff["fires"])]
        self.freeze, self.invuln, self.water = 1.5, 2.0, 0.0
        self.last = {}
        self.events.append(("reset", None))

    def set_algo(self, algo):
        self.algo = algo

    def player_cell(self):
        return self.player.nearest()

    def distmap(self, cell):
        if self._dist[0] != cell:
            self._dist = (cell, bfs_distances(WALK, cell))
        return self._dist[1]

    def pick_flee(self, cell):
        dist = self.distmap(cell)
        far = max(dist.values())
        return random.choice([c for c, d in dist.items() if d >= far * 0.85])

    def want_dir(self, d):
        self.want = d

    def update(self, dt):
        if self.over or self.paused:
            return
        self.time += dt
        if self.freeze > 0:
            self.freeze -= dt
            return
        self.invuln = max(0.0, self.invuln - dt)
        if self.water > 0:
            self.water = max(0.0, self.water - dt)
        self.update_player(dt)
        for f in self.fires:
            self.update_fire(f, dt)
        self.check_collisions()
        if not self.palms and not self.over:
            self.over = "win"
            self.events.append(("win", None))

    def update_player(self, dt):
        p = self.player
        p.step(dt, PLAYER_SPEED)
        if p.idle:
            for d in (self.want, self.dir):
                if d != (0, 0):
                    n = (p.cell[0] + d[0], p.cell[1] + d[1])
                    if WALK[n[1]][n[0]]:
                        p.start(n)
                        self.dir = self.face = d
                        break
            else:
                self.dir = (0, 0)
        c = p.nearest()
        if c in self.palms:
            self.palms.discard(c)
            self.score += PTS_PALM
            self.events.append(("palm", c))
        if c in self.waters:
            self.waters.discard(c)
            self.score += PTS_WATER
            self.water = WATER_TIME
            for f in self.fires:
                f.flee = None
            self.events.append(("water", c))

    def update_fire(self, f, dt):
        if f.state in ("wait", "out"):
            f.timer -= dt
            if f.timer <= 0:
                f.state = "active"
            return
        speed = self.diff["speed"] * (FLEE_SLOW if self.water > 0 else 1.0)
        f.m.step(dt, speed)
        if f.m.idle:
            self.fire_think(f)

    def fire_think(self, f):
        pc = self.player_cell()
        if self.water > 0:
            if f.flee is None or self.time - f.flee_t > 2.0:
                f.flee, f.flee_t = self.pick_flee(pc), self.time
            goal = f.flee
            if goal == f.m.cell:
                f.flee = None
                return
        else:
            f.flee = None
            goal = ghost_target(f.idx, self)
            if goal == f.m.cell:
                return
        res = search(WALK, f.m.cell, goal, self.algo)
        self.record(res)
        self.last[f.idx] = res
        self.last_res = res
        self.events.append(("path", f.idx))
        if res.ok and len(res.path) > 1:
            nxt = res.path[1]
            f.heading = (nxt[0] - f.m.cell[0], nxt[1] - f.m.cell[1])
            f.m.start(nxt)

    def check_collisions(self):
        px, py = self.player.pos()
        for f in self.fires:
            if f.state != "active":
                continue
            fx, fy = f.m.pos()
            if math.hypot(px - fx, py - fy) < 0.6:
                if self.water > 0:
                    self.extinguish(f)
                elif self.invuln <= 0:
                    self.lose_life()
                    return

    def extinguish(self, f):
        self.score += PTS_FIRE
        self.events.append(("extinguish", (f.idx, f.m.pos())))
        f.state, f.timer, f.flee = "out", 5.0, None
        f.m = Mover(f.spawn)

    def lose_life(self):
        self.lives -= 1
        self.events.append(("hit", None))
        if self.lives <= 0:
            self.over = "lose"
            self.events.append(("lose", None))
        else:
            self.reset_positions()
