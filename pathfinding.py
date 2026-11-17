import heapq
import itertools
import random
import time
from collections import deque, namedtuple

ALGOS = ("A*", "GBFS")
DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))

Result = namedtuple("Result", "path nodes ms explored ok algo")


def manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def neighbors(walk, cell):
    x, y = cell
    h, w = len(walk), len(walk[0])
    for dx, dy in DIRS:
        nx, ny = x + dx, y + dy
        if 0 <= nx < w and 0 <= ny < h and walk[ny][nx]:
            yield (nx, ny)


def search(walk, start, goal, algo="A*"):
    """Jalankan A* (f = g + h) atau GBFS (f = h)."""
    t0 = time.perf_counter()
    astar = algo == "A*"
    counter = itertools.count()
    h0 = manhattan(start, goal)
    heap = [(h0, h0, next(counter), start)]
    g = {start: 0}
    parent = {start: None}
    closed = set()
    explored = []
    found = False

    while heap:
        _, _, _, cur = heapq.heappop(heap)
        if cur in closed:
            continue
        closed.add(cur)
        explored.append(cur)
        if cur == goal:
            found = True
            break
        for nb in neighbors(walk, cur):
            if nb in closed:
                continue
            h = manhattan(nb, goal)
            if astar:
                ng = g[cur] + 1
                if ng < g.get(nb, 1 << 30):
                    g[nb] = ng
                    parent[nb] = cur
                    heapq.heappush(heap, (ng + h, h, next(counter), nb))
            else:
                if nb in parent:
                    continue
                parent[nb] = cur
                heapq.heappush(heap, (h, h, next(counter), nb))

    path = []
    if found:
        c = goal
        while c is not None:
            path.append(c)
            c = parent[c]
        path.reverse()
    ms = (time.perf_counter() - t0) * 1000.0
    return Result(path, len(explored), ms, explored, found, algo)


def bfs_distances(walk, start):
    dist = {start: 0}
    q = deque([start])
    while q:
        c = q.popleft()
        for nb in neighbors(walk, c):
            if nb not in dist:
                dist[nb] = dist[c] + 1
                q.append(nb)
    return dist


def make_scenarios(maze_walk, w=21, h=15):
    def empty():
        return [[0 < x < w - 1 and 0 < y < h - 1 for x in range(w)] for y in range(h)]

    s1 = empty()

    s2 = empty()
    for y in range(2, h - 2):
        s2[y][w // 2] = False

    s3 = empty()
    rnd = random.Random(7)
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            if rnd.random() < 0.22:
                s3[y][x] = False

    s4 = empty()
    for y in range(2, h - 2, 2):
        for x in range(1, w - 1):
            s4[y][x] = False
        gap = w - 2 if (y // 2) % 2 == 1 else 1
        s4[y][gap] = True

    return [
        ("Tanpa rintangan", s1),
        ("Jalur terhalang", s2),
        ("Banyak rintangan", s3),
        ("Jalur berliku", s4),
        ("Maze game", maze_walk),
    ]


def run_benchmark(maze_walk, seed=1, pairs=40):
    rows = []
    for name, grid in make_scenarios(maze_walk):
        cells = [(x, y) for y, r in enumerate(grid)
                 for x, v in enumerate(r) if v]
        rnd = random.Random(seed)
        tests = []
        while len(tests) < pairs:
            a, b = rnd.choice(cells), rnd.choice(cells)
            if a != b:
                tests.append((a, b))
        for algo in ALGOS:
            ok = cost = nodes = 0
            ms = 0.0
            for a, b in tests:
                r = search(grid, a, b, algo)
                nodes += r.nodes
                ms += r.ms
                if r.ok:
                    ok += 1
                    cost += len(r.path) - 1
            rows.append(dict(
                scenario=name, algo=algo,
                cost=cost / ok if ok else 0.0,
                nodes=nodes / pairs, ms=ms / pairs,
                success=100.0 * ok / pairs))
    return rows
