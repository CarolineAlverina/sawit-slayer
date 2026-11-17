TOP = [
    "#####################",
    "#.........#.........#",
    "#.##.####.#.####.##.#",
    "#o#...............#o#",
    "#.#.##.#######.##.#.#",
    "#...#...........#...#",
    "###.#.####.####.#.###",
]
MID = "#.....#..FFFF.#.....#"
RAW = TOP + [MID] + TOP[::-1]
PLAYER_START = (9, 13)

COLS, ROWS = len(RAW[0]), len(RAW)
WALLS, PALMS, WATERS, FIRE_SPAWNS = set(), set(), set(), []
for _y, _row in enumerate(RAW):
    for _x, _ch in enumerate(_row):
        c = (_x, _y)
        if _ch == "#":
            WALLS.add(c)
        elif _ch == "o":
            WATERS.add(c)
        elif _ch == "F":
            FIRE_SPAWNS.append(c)
        elif _ch == ".":
            PALMS.add(c)
PALMS.discard(PLAYER_START)

WALK = [[(x, y) not in WALLS for x in range(COLS)] for y in range(ROWS)]
