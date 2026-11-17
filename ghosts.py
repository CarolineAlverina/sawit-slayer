"""Logika target 4 monster ala Pac-Man + data warna/tabel."""
import math
from level import COLS, ROWS, WALLS
_WALLS = set(WALLS)
_WALK = {(x, y) for y in range(ROWS) for x in range(COLS)
         if (x, y) not in _WALLS}
SCATTER = (0, ROWS - 1)            # pojok yang dituju Clyde saat terlalu dekat
GHOSTS = [
    dict(name="Blinky", nick="Shadow",  col=(1.00, 0.15, 0.15)),   # merah
    dict(name="Pinky",  nick="Speedy",  col=(1.00, 0.55, 0.80)),   # pink
    dict(name="Inky",   nick="Bashful", col=(0.20, 0.85, 1.00)),   # biru muda
    dict(name="Clyde",  nick="Pokey",   col=(1.00, 0.60, 0.10)),   # oranye
]

GHOST_INFO = [
    ("Blinky", "Shadow",  "Pac-Man's current tile.",
     "Most aggressive; directly chases."),
    ("Pinky", "Speedy",   "4 tiles ahead of Pac-Man's facing direction.",
     "Ambushes; may overshoot due to overflow errors."),
    ("Inky", "Bashful",   "Vector from Blinky to a point 2 tiles ahead of Pac-Man, doubled.",
     "Erratic; depends on Blinky's position."),
    ("Clyde", "Pokey",    "Pac-Man's tile if >8 tiles away; Scatter corner if <8 tiles away.",
     "Opportunistic; flees when too close."),
]


def snap(t):
    """Target bisa jatuh di dinding / luar peta -> geser ke sel jalan terdekat."""
    x = min(max(int(round(t[0])), 0), COLS - 1)
    y = min(max(int(round(t[1])), 0), ROWS - 1)
    if (x, y) in _WALK:
        return (x, y)
    return min(_WALK, key=lambda c: abs(c[0] - x) + abs(c[1] - y))


CHASE_RANGE = 5          # <= 5 sel: kejar langsung, abaikan logika karakter


def ghost_target(idx, g):
    """Sel tujuan monster ke-idx. g = objek Core."""
    pc = tuple(g.player_cell())
    mc = tuple(g.fires[idx].m.cell)

    # Jarak jalan di labirin; cadangan: jarak Manhattan
    d = g.distmap(pc).get(mc)
    if d is None:
        d = abs(pc[0] - mc[0]) + abs(pc[1] - mc[1])
    if d <= CHASE_RANGE:
        return pc                                  # dekat: kejar langsung

    # Jauh: pakai logika karakter masing-masing
    px, py = (int(round(v)) for v in g.player.pos())
    fx, fy = g.face
    kind = GHOSTS[idx % 4]["name"]

    if kind == "Blinky":
        t = (px, py)
    elif kind == "Pinky":
        t = (px + 4 * fx, py + 4 * fy)
        if (fx, fy) == (0, -1):
            t = (t[0] - 4, t[1])
    elif kind == "Inky":
        bx, by = g.fires[0].m.pos()
        pv = (px + 2 * fx, py + 2 * fy)
        t = (2 * pv[0] - bx, 2 * pv[1] - by)
    else:                                          # Clyde
        mx, my = g.fires[idx].m.pos()
        t = (px, py) if math.hypot(px - mx, py - my) > 8 else SCATTER
    return snap(t)
