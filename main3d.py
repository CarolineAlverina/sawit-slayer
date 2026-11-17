"""SAWIT SLAYER 3D - game edukasi karhutla (Ursina).

Pemain (pemadam berpedang) menebang pohon sawit di labirin hutan sambil dikejar
monster api (Hellish Banban). Monster mengejar memakai A* atau GBFS. Saat pemain
mengambil air, monster berubah menjadi Baby Banban dan bisa dikalahkan; sebuah
papan informasi tentang karhutla muncul.

Logika game: core.py | algoritma: pathfinding.py | denah: level.py
Jalankan:  python main3d.py
"""
from ursina import *          # noqa: F401,F403

import json                   # diimpor setelah ursina agar tidak tertimpa
import math
import random
from pathlib import Path
import textwrap

from ghosts import GHOSTS, GHOST_INFO
from core import DIFF_ORDER, WATER_TIME, Core
from level import COLS, ROWS, WALK, WALLS
from pathfinding import ALGOS, run_benchmark
from sound import SoundManager

BASE = Path(__file__).resolve().parent

# ------------------------------------------------------------ konfigurasi ----
CELL = 2.0                         # 1 sel labirin = 2 unit dunia
WALL_H = 2.2                       # tinggi dinding semak
POV_BACK, POV_UP, POV_PITCH = 11.8, 9.8, 30.0     # kamera di belakang pemadam
TOP_DIST, TOP_PITCH = 46.0, 62.0   # kamera dari atas
CAM_FOV = 60
# putar arah hadap pemadam bila terbalik (90 / 180 / -90)
YAW_OFFSET = 0
MONSTER_YAW_OFFSET = 0             # sama, untuk monster
ATTACK_TIME = 0.5                  # lama animasi tebas (detik)
CX, CZ = (COLS - 1) * CELL / 2, (ROWS - 1) * CELL / 2

GRASS = (0.17, 0.80, 0.68)
DIRT = (0.886, 0.514, 0.341)
PATH = (0.96, 0.82, 0.60)
FONT_MAIN = "fonts/ChauPhilomeneOne-Regular.ttf"
FONT_TABLE = "fonts/Montserrat-Bold.ttf"
CREAM = Vec4(0.94, 0.91, 0.56, 1)
CLEAR = color.clear

try:
    Text.default_font = FONT_MAIN
except Exception:
    pass


def rgb(r, g, b, a=255):
    return Vec4(r / 255, g / 255, b / 255, a / 255)


def W(gx, gy, y=0.0):
    """Koordinat grid -> dunia 3D (baris 0 di bagian utara / +z)."""
    return Vec3(gx * CELL, y, (ROWS - 1 - gy) * CELL)


def approach_angle(cur, target, k):
    d = (target - cur + 180) % 360 - 180
    return cur + d * k


def heading_yaw(dx, dy):
    return math.degrees(math.atan2(dx, -dy))


_tex = {}


def tex(rel):
    if rel not in _tex:
        p = BASE / rel
        _tex[rel] = Texture(p) if p.exists() else None
    return _tex[rel]


_sizes = {}


def img_size(rel):
    if rel not in _sizes:
        try:
            from PIL import Image
            with Image.open(BASE / rel) as im:
                _sizes[rel] = im.size
        except Exception:
            _sizes[rel] = (1, 1)
    return _sizes[rel]


class AppState:
    def __init__(self):
        self.state = "menu"        # menu | play | settings | stats | end
        self.overlay = None        # None | pause | info | settings
        self.settings_from = "menu"
        self.algo, self.diff = "A*", "Medium"
        self.cam = "pov"
        self.viz = False
        self.music, self.sound = True, True
        self.stats = {a: dict(n=0, nodes=0, plen=0, ms=0.0, fail=0)
                      for a in ALGOS}
        self.bench, self.bench_seed = None, 1
        self.info_order, self.info_pos = [], 0

    def record(self, res):
        s = self.stats[res.algo]
        s["n"] += 1
        s["nodes"] += res.nodes
        s["ms"] += res.ms
        if res.ok:
            s["plen"] += len(res.path) - 1
        else:
            s["fail"] += 1


S = AppState()
snd = SoundManager(S)          # musik + efek suara (lihat sound.py)
game = None
world = None
dyn = None
refs = {}

app = Ursina(title="Sawit Slayer 3D")
for _n in ("exit_button", "cog_button", "fps_counter"):
    try:
        getattr(window, _n).enabled = False
    except Exception:
        pass
try:
    window.size = Vec2(1280, 720)
except Exception:
    pass
window.color = rgb(205, 150, 110)
camera.fov = CAM_FOV
try:
    ASP = float(window.aspect_ratio)
except Exception:
    ASP = 16 / 9


# ------------------------------------------------------------ helper UI ----
def label(parent, text, x, y, size=1.0, col=None, font=None, origin=(0, 0), z=-0.02):
    try:
        t = Text(text=text, parent=parent, x=x, y=y, z=z, origin=origin, scale=size,
                 color=col or color.white, **({"font": font} if font else {}))
    except Exception:
        t = Text(text=text, parent=parent, x=x, y=y, z=z,
                 origin=origin, scale=size, color=col or color.white)
    return t


def img(parent, rel, x=0.0, y=0.0, w=None, h=None, z=0.0):
    iw, ih = img_size(rel)
    if h is None:
        h = w * ih / iw
    if w is None:
        w = h * iw / ih
    e = Entity(parent=parent, model="quad", texture=tex(
        rel), scale=(w, h), position=(x, y, z))
    return e, w, h


def clicked(fn):
    """Bungkus aksi tombol supaya berbunyi 'klik' saat ditekan."""
    def _run():
        snd.sfx("click")
        fn()
    return _run


def hit(parent, x, y, w, h, fn, z=-0.05):
    return Button(parent=parent, model="quad", color=CLEAR, highlight_color=Color(1, 1, 1, 0.2),
                  pressed_color=Vec4(1, 1, 1, 0.32), scale=(w, h), position=(x, y, z), on_click=clicked(fn))


def icon_button(parent, rel, x, y, size, fn, z=-0.05):
    return Button(parent=parent, model="quad", texture=tex(rel), color=color.white,
                  highlight_color=Color(0.85, 0.85, 0.85, 1), pressed_color=Color(0.7, 0.7, 0.7, 1),
                  scale=(size, size), position=(x, y, z), on_click=clicked(fn))


class Panel:
    """Gambar panel dengan koordinat pecahan (u dari kiri, v dari atas) -> koordinat UI."""

    def __init__(self, parent, rel, x, y, h):
        self.entity, self.w, self.h = img(parent, rel, x, y, h=h)
        self.x, self.y = x, y

    def pt(self, u, v):
        return self.x + (u - .5) * self.w, self.y + (.5 - v) * self.h

    def hit(self, parent, u, v, wf, hf, fn):
        x, y = self.pt(u, v)
        return hit(parent, x, y, wf * self.w, hf * self.h, fn)


# ---------------------------------------------------------- pustaka model ----
class ModelLib:
    """Memuat model JSON hasil tools/build_assets.py menjadi Mesh Ursina (satu template per frame)."""

    def __init__(self):
        self.cache, self.shared, self.tpl = {}, {}, {}

    def data(self, name):
        if name not in self.cache:
            self.cache[name] = json.loads(
                (BASE / "models" / f"{name}.json").read_text())
        return self.cache[name]

    def part_shared(self, name, p):
        key = (name, p)
        if key not in self.shared:
            pd = self.data(name)["parts"][p]
            self.shared[key] = dict(uvs=[Vec2(*u) for u in pd["uvs"]],
                                    colors=[Vec4(*c) for c in pd["colors"]],
                                    tris=pd["triangles"],
                                    tex=tex(f"textures/{pd['texture']}") if pd["texture"] else None)
        return self.shared[key]

    def build_mesh(self, name, p, f):
        pd = self.data(name)["parts"][p]
        sh = self.part_shared(name, p)
        v = pd["frames"][f]
        verts = [Vec3(v[i], v[i + 1], v[i + 2]) for i in range(0, len(v), 3)]
        return Mesh(vertices=verts, triangles=sh["tris"], uvs=sh["uvs"], colors=sh["colors"], mode="triangle")

    def template(self, name, p, f):
        key = (name, p, f)
        if key not in self.tpl:
            t = Entity(model=self.build_mesh(name, p, f))
            sh = self.part_shared(name, p)
            if sh["tex"] is not None:
                t.texture = sh["tex"]
            t.hide()
            self.tpl[key] = t
        return self.tpl[key]

    def preload(self, names):
        for n in names:
            d = self.data(n)
            for p in range(len(d["parts"])):
                for f in range(len(d["parts"][p]["frames"])):
                    self.template(n, p, f)


lib = ModelLib()


class Animated:
    """Instans model; frame animasi diganti dengan menampilkan/menyembunyikan salinan mesh."""

    def __init__(self, name, parent, scale=1.0, position=(0, 0, 0), static=False):
        d = lib.data(name)
        nparts, nframes = len(d["parts"]), len(d["parts"][0]["frames"])
        self.anims = d["anims"] or {"static": [0, nframes, 1.0, False]}
        first = next(iter(self.anims))
        idxs = [self.anims[first][0]] if static else range(
            nframes)   # static: 1 frame saja
        self.root = Entity(parent=parent, position=position)
        self.root.scale = scale
        self.frames = {}
        for f in idxs:
            row = []
            for p in range(nparts):
                holder = Entity(parent=self.root, add_to_scene_entities=False)
                try:
                    lib.template(name, p, f).model.copy_to(holder)
                except Exception:
                    holder.model = lib.build_mesh(name, p, f)
                    sh = lib.part_shared(name, p)
                    if sh["tex"] is not None:
                        holder.texture = sh["tex"]
                holder.hide()
                row.append(holder)
            self.frames[f] = row
        self.cur, self.t, self.shown, self.speed = None, 0.0, -1, 1.0
        self.play(first)
        self.root.setTwoSided(True)
        self.set_frame(self.anims[first][0])

    def set_frame(self, idx):
        if idx == self.shown:
            return
        if self.shown >= 0:
            for h in self.frames[self.shown]:
                h.hide()
        for h in self.frames[idx]:
            h.show()
        self.shown = idx

    def play(self, name, restart=False):
        if name in self.anims and (name != self.cur or restart):
            self.cur, self.t = name, 0.0

    @property
    def done(self):
        start, n, dur, loop = self.anims[self.cur]
        return (not loop) and self.t >= dur

    def duration(self, name):
        return self.anims[name][2]

    def update(self, dt):
        start, n, dur, loop = self.anims[self.cur]
        self.t += dt * self.speed
        ph = (self.t / dur) % 1.0 if loop else min(self.t / dur, 0.999)
        self.set_frame(start + int(ph * n))

    def show(self):
        self.root.show()

    def hide(self):
        self.root.hide()


# --------------------------------------------------------------- dunia 3D ----
def _quad(verts, uvs, cols, tris, pts, col, uv=((0, 0), (1, 0), (1, 1), (0, 1))):
    i = len(verts)
    verts.extend(pts)
    uvs.extend([Vec2(*u) for u in uv])
    cols.extend([Vec4(*col, 1)] * 4)
    tris.extend([i, i + 1, i + 2, i, i + 2, i + 3])


def make_wall_mesh():
    verts, uvs, cols, tris = [], [], [], []
    rnd = random.Random(11)
    lip = 0.4
    for (gx, gy) in sorted(WALLS):
        x0, x1 = gx * CELL - CELL / 2, gx * CELL + CELL / 2
        zc = (ROWS - 1 - gy) * CELL
        z0, z1 = zc - CELL / 2, zc + CELL / 2
        h = WALL_H
        def nb(dx, dy): return (gx + dx, gy + dy) in WALLS
        b = rnd.uniform(0.94, 1.04)
        g = tuple(min(1, c * b) for c in GRASS)
        _quad(verts, uvs, cols, tris, [Vec3(x0, h, z0), Vec3(
            x1, h, z0), Vec3(x1, h, z1), Vec3(x0, h, z1)], g)
        faces = []
        if not nb(0, 1):   # selatan (-z)
            faces.append(([(x0, z0), (x1, z0)], 0.86))
        if not nb(0, -1):  # utara (+z)
            faces.append(([(x1, z1), (x0, z1)], 0.64))
        if not nb(1, 0):   # timur (+x)
            faces.append(([(x1, z0), (x1, z1)], 0.76))
        if not nb(-1, 0):  # barat (-x)
            faces.append(([(x0, z1), (x0, z0)], 0.70))
        for (a, c), sh in faces:
            for y0, y1, base in ((0, h - lip, DIRT), (h - lip, h, GRASS)):
                _quad(verts, uvs, cols, tris,
                      [Vec3(a[0], y0, a[1]), Vec3(c[0], y0, c[1]),
                       Vec3(c[0], y1, c[1]), Vec3(a[0], y1, a[1])],
                      tuple(v * sh for v in base))
    return Mesh(vertices=verts, triangles=tris, uvs=uvs, colors=cols, mode="triangle")


def make_floor_mesh():
    verts, uvs, cols, tris = [], [], [], []
    for gy in range(ROWS):
        for gx in range(COLS):
            if (gx, gy) in WALLS:
                continue
            x0, x1 = gx * CELL - CELL / 2, gx * CELL + CELL / 2
            zc = (ROWS - 1 - gy) * CELL
            z0, z1 = zc - CELL / 2, zc + CELL / 2
            sh = 1.0 if (gx + gy) % 2 == 0 else 0.95
            _quad(verts, uvs, cols, tris, [Vec3(x0, 0, z0), Vec3(x1, 0, z0), Vec3(x1, 0, z1), Vec3(x0, 0, z1)],
                  tuple(c * sh for c in PATH))
    return Mesh(vertices=verts, triangles=tris, uvs=uvs, colors=cols, mode="triangle")


def destroy_tree(e):
    for c in list(e.children):
        destroy_tree(c)
    destroy(e)


def build_static_world():
    Entity(parent=world, model="plane", scale=(260, 1, 260),
           position=(CX, -0.05, CZ), color=Vec4(*GRASS, 1))
    Entity(parent=world, model=make_floor_mesh(), double_sided=True)
    Entity(parent=world, model=make_wall_mesh(), double_sided=True)
    rnd = random.Random(4)
    x_lo, x_hi, z_lo, z_hi = -CELL, COLS * CELL, -CELL, ROWS * CELL
    placed = 0
    while placed < 70:
        x, z = rnd.uniform(x_lo - 26, x_hi +
                           26), rnd.uniform(z_lo - 22, z_hi + 22)
        if x_lo - 3 < x < x_hi + 3 and z_lo - 3 < z < z_hi + 3:
            continue
        kind = rnd.random()
        if kind < 0.5:
            m = Animated("tree_a" if kind < 0.25 else "tree_b", world,
                         scale=rnd.uniform(0.9, 1.5), position=(x, 0, z), static=True)
        elif kind < 0.8:
            m = Animated("stump", world, scale=rnd.uniform(0.8, 1.3),
                         position=(x, 0, z), static=True)
        else:
            m = Animated("rock", world, scale=rnd.uniform(0.35, 0.6),
                         position=(x, 0, z), static=True)
        m.root.rotation_y = rnd.uniform(0, 360)
        placed += 1


def build_world():
    global world, dyn, refs
    if world is None:
        world = Entity()
        build_static_world()
    if dyn is not None:
        destroy_tree(dyn)
    dyn = Entity(parent=world)
    refs = dict(palm={}, water={}, fall=[], viz={}, tt=0.0,
                cam_yaw=0.0, attack=0.0, blink=False)

    rnd = random.Random(5)
    for c in game.palms:
        m = Animated("palm", dyn, scale=rnd.uniform(0.85, 1.1),
                     position=W(*c), static=True)
        m.root.rotation_y = rnd.uniform(0, 360)
        refs["palm"][c] = m
    for c in game.waters:
        refs["water"][c] = Animated(
            "water_drop", dyn, position=W(*c, 0.9), static=True)

    refs["mon"] = []
    for f in game.fires:
        h = Animated("hellish_banban", dyn, position=W(*f.spawn))
        b = Animated("baby_banban", dyn, position=W(*f.spawn))
        h.hide()
        b.hide()
        refs["mon"].append(dict(h=h, b=b, yaw=0.0))
    refs["player"] = Animated(
        "firefighter", dyn, position=W(*game.player.pos()))
    refs["player_yaw"] = 0.0


def burst(pos, col):
    """Percikan air saat monster dikalahkan."""
    for i in range(10):
        a = i / 10 * math.tau
        s = Entity(parent=world, model="sphere", color=col,
                   scale=0.25, position=pos + Vec3(0, 1.0, 0))
        s.animate_position(pos + Vec3(math.cos(a) * 1.6, 0.6 +
                           random.random() * 1.2, math.sin(a) * 1.6), duration=0.45)
        s.animate_scale(0, duration=0.5)
        destroy(s, delay=0.55)


def build_viz(res, idx):
    verts, cols, tris = [], [], []
    col = GHOSTS[idx % 4]["col"]
    off = idx * 0.004                         # cegah tumpang-tindih antar monster

    def quad(gx, gy, half, y, c):
        i = len(verts)
        cx, cz = gx * CELL, (ROWS - 1 - gy) * CELL
        hh = half * CELL
        verts.extend([Vec3(cx - hh, y, cz - hh), Vec3(cx + hh, y, cz - hh),
                     Vec3(cx + hh, y, cz + hh), Vec3(cx - hh, y, cz + hh)])
        cols.extend([c] * 4)
        tris.extend([i, i + 1, i + 2, i, i + 2, i + 3])

    for c in res.explored:
        quad(c[0], c[1], 0.42, 0.06 + off, Vec4(*col, 0.30))
    for c in res.path:
        quad(c[0], c[1], 0.11, 0.10 + off, Vec4(*col, 1))
    if res.path:
        quad(res.path[0][0], res.path[0][1], 0.22, 0.12 + off, Vec4(*col, 1))
        quad(res.path[-1][0], res.path[-1][1],
             0.22, 0.13 + off, Vec4(1, 1, 1, 1))
    if not verts:
        return None
    e = Entity(parent=world, model=Mesh(vertices=verts, triangles=tris,
               colors=cols, mode="triangle"), double_sided=True)
    e.setTransparency(True)
    return e


# ------------------------------------------------------------ pemuatan ----
_loading = Text(text="Memuat aset...", origin=(
    0, 0), scale=2.2, color=color.white)
try:
    app.step()
except Exception:
    pass
lib.preload(["firefighter", "hellish_banban", "baby_banban", "water_drop", "palm",
             "tree_a", "tree_b", "rock", "stump"])
destroy(_loading)

# ------------------------------------------------------------------ HUD ----
hud = Entity(parent=camera.ui, enabled=False)
lbl = {}

Entity(parent=hud, model="quad", color=Vec4(0, 0, 0, 0.93),
       scale=(ASP * 1.05, 0.10), position=(0, 0.45, 0.05))
Entity(parent=hud, model="quad", color=Vec4(0, 0, 0, 0.93),
       scale=(ASP * 1.05, 0.085), position=(0, -0.4575, 0.05))

icon_button(hud, "ui/icon_back.png", -ASP / 2 +
            0.06, 0.45, 0.075, lambda: go_menu())
_p, pw_, ph_ = img(hud, "ui/pill_score.png", -0.52, 0.45, h=0.078)
lbl["score"] = label(hud, "Skor: 0", -0.52, 0.45, 1.25, font=FONT_MAIN)
_p, pw_, ph_ = img(hud, "ui/pill_sawit.png", -0.20, 0.45, h=0.078)
lbl["sawit"] = label(hud, "Sawit: 0/0", -0.17, 0.45, 1.15, font=FONT_MAIN)
algo_pill, aw_, ah_ = img(hud, "ui/pill_algo_astar.png", 0.12, 0.45, h=0.078)
icon_button(hud, "ui/icon_pause.png", ASP / 2 - 0.15,
            0.45, 0.075, lambda: open_overlay("pause"))
icon_button(hud, "ui/icon_settings.png", ASP / 2 - 0.065, 0.45,
            0.075, lambda: open_overlay("settings", "play"))

life_icons = [img(hud, "ui/icon_head.png", -ASP / 2 + 0.07 +
                  i * 0.075, -0.4575, h=0.07)[0] for i in range(3)]
wb, wbw, wbh = img(hud, "ui/water_bar.png", -0.38, -0.4575, h=0.15)
BAR_U0, BAR_U1, BAR_V = 0.303, 0.99, 0.5
bar_x0 = wb.x + (BAR_U0 - .5) * wbw
bar_x1 = wb.x + (BAR_U1 - .5) * wbw
bar_h = 0.155 * wbh
water_cover = Entity(parent=hud, model="quad", color=rgb(30, 36, 52), scale=(0.001, bar_h), position=(bar_x1, wb.y, -0.03),
                     origin_x=0.5)
lbl["hint"] = label(hud, "W/A/S/D atau panah: gerak   TAB: algoritma   V: jalur   C: kamera",
                    0.30, -0.4575, 0.85, col=CREAM, font=FONT_TABLE)
msg = label(camera.ui, " ", 0.0, 0.31, 2.4, col=CREAM, font=FONT_MAIN, z=-0.5)
msg.enabled = False
msg_timer = [0.0]


def flash(text, secs=1.4, col=None):
    msg.text = text
    msg.color = col or CREAM
    msg.enabled = True
    msg_timer[0] = secs


# --- minimap (pojok kanan atas, di bawah header) ---
MM_CX, MM_CY, MM_W = 0.60, 0.245, 0.43
mm_root = Entity(parent=hud)
mm_frame, mmw, mmh = img(mm_root, "ui/frame_minimap.png",
                         MM_CX, MM_CY, w=MM_W, z=-0.04)
MM_CS = min(mmw * 0.94 / COLS, mmh * 0.91 / ROWS)

player_dot = Entity(parent=mm_root, model="circle", color=rgb(255, 230, 30),
                    scale=MM_CS * 1.0, position=(MM_CX, MM_CY, -0.09))
MM_OX, MM_OY = MM_CX - COLS * MM_CS / 2, MM_CY + ROWS * MM_CS / 2


def mm_pos(gx, gy):
    return MM_OX + (gx + .5) * MM_CS, MM_OY - (gy + .5) * MM_CS


def make_minimap_mesh():
    verts, cols, tris = [], [], []
    for gy in range(ROWS):
        for gx in range(COLS):
            x, y = MM_OX + gx * MM_CS, MM_OY - gy * MM_CS
            col = Vec4(0.12, 0.30, 0.95, 1) if (
                gx, gy) in WALLS else Vec4(0.04, 0.04, 0.10, 0.92)
            i = len(verts)
            verts.extend([Vec3(x, y - MM_CS, 0), Vec3(x + MM_CS,
                         y - MM_CS, 0), Vec3(x + MM_CS, y, 0), Vec3(x, y, 0)])
            cols.extend([col] * 4)
            tris.extend([i, i + 1, i + 2, i, i + 2, i + 3])
    return Mesh(vertices=verts, triangles=tris, colors=cols, mode="triangle")


Entity(parent=mm_root, model=make_minimap_mesh(), z=-0.02)
mm = dict(palm={}, water={}, fires=[], box=None)


def build_minimap_markers():
    if mm["box"] is not None:
        destroy_tree(mm["box"])
    box = Entity(parent=mm_root)
    mm["box"] = box
    mm["palm"], mm["water"], mm["fires"] = {}, {}, []
    for c in game.palms:
        x, y = mm_pos(*c)
        mm["palm"][c] = Entity(parent=box, model="quad", color=rgb(
            255, 160, 40), scale=MM_CS * 0.32, position=(x, y, -0.06))
    for c in game.waters:
        x, y = mm_pos(*c)
        mm["water"][c] = Entity(parent=box, model="circle", color=rgb(
            80, 200, 255), scale=MM_CS * 0.85, position=(x, y, -0.07))
    for f in game.fires:
        x, y = mm_pos(*f.m.pos())
        mm["fires"].append(Entity(parent=box, model="circle", color=rgb(
            235, 40, 40), scale=MM_CS * 0.9, position=(x, y, -0.08)))


def update_minimap():
    g = game
    for c, e in mm["palm"].items():
        e.enabled = c in g.palms
    for c, e in mm["water"].items():
        e.enabled = c in g.waters
    for i, (f, e) in enumerate(zip(g.fires, mm["fires"])):
        e.enabled = f.state == "active"
        x, y = mm_pos(*f.m.pos())
        e.position = (x, y, -0.08)
        e.color = rgb(90, 190, 255) if g.water > 0 else Vec4(
            *GHOSTS[i % 4]["col"], 1)
    px, py = g.player.pos()
    x, y = mm_pos(px, py)
    player_dot.position = (x, y, -0.09)


def apply_minimap_visibility():
    """Minimap hanya tampil saat kamera di belakang pemadam (pov)."""
    mm_root.enabled = (S.cam == "pov")


def update_hud():
    g = game
    apply_minimap_visibility()
    cut = g.total - len(g.palms)
    lbl["score"].text = f"Skor: {g.score}"
    lbl["sawit"].text = f"Sawit: {cut}/{g.total}"
    algo_pill.texture = tex(
        "ui/pill_algo_astar.png" if g.algo == "A*" else "ui/pill_algo_gbfs.png")
    for i, ic in enumerate(life_icons):
        ic.enabled = i < g.lives
    frac = 1.0 - (g.water / WATER_TIME)
    water_cover.scale_x = max(0.0005, (bar_x1 - bar_x0) * frac)
    update_minimap()


# ------------------------------------------------------------------ menu ----
menu = Entity(parent=camera.ui)
img(menu, "ui/bg_start.jpg", 0, 0, w=ASP, h=1.0, z=1)
MB = dict(w=0.13 * ASP, h=0.095)
for _v, _fn in ((0.476, lambda: start_game()), (0.611, lambda: open_settings_page()),
                (0.729, lambda: open_stats()), (0.850, lambda: application.quit())):
    hit(menu, (0.522 - .5) * ASP, .5 - _v, MB["w"], MB["h"], _fn)
label(menu, "Enter: mulai", 0.0, -0.475, 0.9, col=CREAM, font=FONT_TABLE)

# ------------------------------------------------------- halaman settings ----
settings_root = Entity(parent=camera.ui, enabled=False)
set_bg = img(settings_root, "ui/bg.jpg", 0, 0, w=ASP, h=1.0, z=2)[0]
set_dim = Entity(parent=settings_root, model="quad", color=Vec4(
    0, 0, 0, 0.6), scale=(ASP * 1.1, 1.1), position=(0, 0, 1), collider="box")
set_panel = Panel(settings_root, "ui/settings_panel.png", 0, -0.02, 0.66)
set_hl = {}


def hl_quad(u, v, wf, hf):
    x, y = set_panel.pt(u, v)
    return Entity(parent=settings_root, model="quad", color=Vec4(0.45, 1, 0.3, 0.38),
                  scale=(wf * set_panel.w, hf * set_panel.h), position=(x, y, -0.03))


for _k, (u, v, wf, hf) in {"A*": (.608, .387, .215, .115), "GBFS": (.840, .387, .215, .115),
                           "Easy": (.284, .774, .17, .08), "Medium": (.500, .774, .17, .08),
                           "Hard": (.717, .774, .17, .08)}.items():
    set_hl[_k] = hl_quad(u, v, wf, hf)
toggle_parts = {}
for _k, v in (("music", .298), ("sound", .415)):
    x, y = set_panel.pt(.397, v)
    tw, th = 0.082 * set_panel.w, 0.06 * set_panel.h
    border = Entity(parent=settings_root, model="quad",
                    color=color.black, scale=(tw, th), position=(x, y, -0.03))
    fill = Entity(parent=settings_root, model="quad", color=color.white, scale=(
        tw * .92, th * .78), position=(x, y, -0.035))
    knob = Entity(parent=settings_root, model="circle",
                  color=color.black, scale=th * .62, position=(x, y, -0.04))
    toggle_parts[_k] = (x, tw, knob)


def refresh_settings():
    for k in ALGOS:
        set_hl[k].enabled = S.algo == k
    for k in DIFF_ORDER:
        set_hl[k].enabled = S.diff == k
    for k, on in (("music", S.music), ("sound", S.sound)):
        x, tw, knob = toggle_parts[k]
        knob.x = x + (tw * .30 if on else -tw * .30)


def pick_algo(a):
    S.algo = a
    if game is not None:
        game.set_algo(a)
    refresh_settings()


def pick_diff(d):
    S.diff = d
    refresh_settings()
    if S.overlay == "settings" and game is not None:
        flash("Kesulitan berlaku di permainan berikutnya", 2.0)


def toggle_audio(k):
    if k == "music":
        S.music = not S.music
    else:
        S.sound = not S.sound
    refresh_settings()
    snd.sync()                       # musik langsung berhenti / menyala
    if k == "sound" and S.sound:
        snd.sfx("click")             # contoh bunyi saat Sound dinyalakan


set_panel.hit(settings_root, .608, .387, .215, .115, lambda: pick_algo("A*"))
set_panel.hit(settings_root, .840, .387, .215, .115, lambda: pick_algo("GBFS"))
for _d, _u in (("Easy", .284), ("Medium", .500), ("Hard", .717)):
    set_panel.hit(settings_root, _u, .774, .17, .08,
                  (lambda d=_d: pick_diff(d)))
set_panel.hit(settings_root, .397, .298, .12, .09,
              lambda: toggle_audio("music"))
set_panel.hit(settings_root, .397, .415, .12, .09,
              lambda: toggle_audio("sound"))
set_panel.hit(settings_root, .524, .938, .10, .075, lambda: close_settings())

# ---------------------------------------------------------- popup pause ----
pause_root = Entity(parent=camera.ui, enabled=False, z=-3)
Entity(parent=pause_root, model="quad", color=Vec4(0, 0, 0, 0.6),
       scale=(ASP * 1.1, 1.1), position=(0, 0, 1), collider="box")
pause_panel = Panel(pause_root, "ui/paused_panel.png", 0, -0.02, 0.74)
pause_panel.hit(pause_root, .498, .304, .40, .11, lambda: close_overlay())
pause_panel.hit(pause_root, .498, .456, .40, .11, lambda: start_game())
pause_panel.hit(pause_root, .498, .613, .40, .11,
                lambda: open_overlay("settings", "pause"))
pause_panel.hit(pause_root, .498, .772, .40, .11, lambda: go_menu())
pause_panel.hit(pause_root, .507, .937, .15, .10, lambda: close_overlay())

# ---------------------------------------------------------- popup info ----
info_root = Entity(parent=camera.ui, enabled=False, z=-3)
ghost_root = Entity(parent=camera.ui, enabled=False, z=-3)
Entity(parent=ghost_root, model="quad", color=Vec4(0, 0, 0, 0.6),
       scale=(ASP * 1.1, 1.1), position=(0, 0, 1), collider="box")
Entity(parent=ghost_root, model="quad", color=Vec4(0.05, 0.05, 0.1, 0.95),
       scale=(1.62, 0.62), position=(0, 0, 0.5))
label(ghost_root, "Karakter Monster", 0, 0.25, 1.5, col=CREAM, font=FONT_MAIN)
_gx = [-0.78, -0.63, -0.46, 0.12]
for _x, _h in zip(_gx, ["Ghost", "Name", "Target Logic", "Behavior"]):
    label(ghost_root, _h, _x, 0.17, 0.9, col=color.azure,
          font=FONT_TABLE, origin=(-.5, 0))
for _i, (_n, _nick, _tl, _bh) in enumerate(GHOST_INFO):
    _y = 0.07 - _i * 0.11
    _c = Vec4(*GHOSTS[_i]["col"], 1)
    label(ghost_root, _n, _gx[0], _y, 1.0, col=_c,
          font=FONT_TABLE, origin=(-.5, 0))
    label(ghost_root, _nick, _gx[1], _y, 0.85,
          font=FONT_TABLE, origin=(-.5, 0))
    label(ghost_root, textwrap.fill(_tl, 34),
          _gx[2], _y, 0.8, font=FONT_TABLE, origin=(-.5, 0))
    label(ghost_root, textwrap.fill(_bh, 30),
          _gx[3], _y, 0.8, font=FONT_TABLE, origin=(-.5, 0))
icon_button(ghost_root, "ui/icon_close.png", 0.78,
            0.27, 0.075, lambda: close_overlay())
Entity(parent=info_root, model="quad", color=Vec4(0, 0, 0, 0.55),
       scale=(ASP * 1.1, 1.1), position=(0, 0, 1), collider="box")
info_board = Entity(parent=info_root, model="quad", position=(0, -0.02, 0))
info_close = icon_button(info_root, "ui/icon_close.png",
                         0, 0, 0.075, lambda: close_overlay())
INFO_H = 0.70
label(info_root, "Tahukah kamu?", 0, 0.40, 1.5, col=CREAM, font=FONT_MAIN)


def show_info():
    if not S.info_order or S.info_pos >= len(S.info_order):
        S.info_order = list(range(1, 10))
        random.shuffle(S.info_order)
        S.info_pos = 0
    n = S.info_order[S.info_pos]
    S.info_pos += 1
    rel = f"ui/info_{n}.png"
    iw, ih = img_size(rel)
    w, h = INFO_H * iw / ih, INFO_H
    info_board.texture = tex(rel)
    info_board.scale = (w, h)
    info_close.position = (w * 0.42, -0.02 + h * 0.42, -0.05)


# ---------------------------------------------------------------- statistik ----
stats_root = Entity(parent=camera.ui, enabled=False)
img(stats_root, "ui/bg.jpg", 0, 0, w=ASP, h=1.0, z=2)
Entity(parent=stats_root, model="quad", color=Vec4(
    0.05, 0.05, 0.1, 0.82), scale=(1.6, 0.92), position=(0, -0.01, 1))
icon_button(stats_root, "ui/icon_back.png", -0.80,
            0.42, 0.075, lambda: set_state("menu"))
stats_items = []


def open_stats():
    for e in stats_items:
        destroy(e)
    stats_items.clear()
    S.bench = run_benchmark(WALK, S.bench_seed)

    def cell(text, x, y, col=None, size=0.9, font=FONT_TABLE):
        stats_items.append(label(stats_root, text, x, y, size,
                           col or color.white, font, origin=(-.5, 0)))

    cell("Perbandingan A* vs GBFS", -0.72, 0.42, CREAM, 2.0, FONT_MAIN)
    cell(
        "Statistik pencarian dari permainan (rata-rata per pencarian)   [C: reset]", -0.72, 0.345, CREAM, 0.95)
    xs = [-0.72, -0.47, -0.22, 0.03, 0.28, 0.53]
    for x, h in zip(xs, ["Algoritma", "Pencarian", "Node", "Panjang jalur", "Waktu (ms)", "Success"]):
        cell(h, x, 0.29, color.azure)
    y = 0.245
    for a in ALGOS:
        st = S.stats[a]
        n, ok = st["n"], st["n"] - st["fail"]
        vals = [a, n, f"{st['nodes'] / n:.1f}" if n else "-", f"{st['plen'] / ok:.1f}" if ok else "-",
                f"{st['ms'] / n:.4f}" if n else "-", f"{100 * ok / n:.0f}%" if n else "-"]
        for x, v in zip(xs, vals):
            cell(str(v), x, y)
        y -= .045
    cell(
        "Uji skenario (kondisi identik, 40 pasang start-goal)   [B: ulangi dengan seed baru]", -0.72, y - .015, CREAM, 0.95)
    y -= .07
    for x, h in zip(xs, ["Skenario", "Algoritma", "Path cost", "Nodes", "Waktu (ms)", "Success"]):
        cell(h, x, y, color.azure)
    y -= .04
    for r in S.bench:
        vals = [r["scenario"], r["algo"], f"{r['cost']:.2f}", f"{
            r['nodes']:.1f}", f"{r['ms']:.4f}", f"{r['success']:.0f}%"]
        for x, v in zip(xs, vals):
            cell(str(v), x, y, size=0.85)
        y -= .036
    cell("A* menjamin jalur terpendek; GBFS biasanya memeriksa lebih sedikit node tetapi jalurnya bisa lebih panjang.",
         -0.72, -0.45, color.light_gray, 0.8)
    set_state("stats")


# ----------------------------------------------------------- layar akhir ----
end_root = Entity(parent=camera.ui, enabled=False)
Entity(parent=end_root, model="quad", color=Vec4(0, 0, 0, 0.65),
       scale=(ASP * 1.1, 1.1), position=(0, 0, 1), collider="box")
end_board = Panel(end_root, "ui/board_score.png", 0, -0.10, 0.70)
end_banner = Entity(parent=end_root, model="quad", position=(0, 0.33, -0.1))
end_lbl = {}
_x, _y = end_board.pt(.505, .09)
end_lbl["k"] = label(end_root, "Skor:", _x, _y, 1.3, font=FONT_MAIN)
_x, _y = end_board.pt(.525, .215)
end_lbl["score"] = label(end_root, "0", _x, _y, 4.2, font=FONT_MAIN)
_x, _y = end_board.pt(.555, .42)
end_lbl["sawit"] = label(end_root, "0", _x, _y, 2.0, font=FONT_MAIN)
_x, _y = end_board.pt(.52, .535)
end_lbl["algo"] = label(end_root, "Algoritma: A*", _x, _y, 1.7, font=FONT_MAIN)
end_board.hit(end_root, .51, .69, .26, .085, lambda: start_game())
end_board.hit(end_root, .51, .79, .26, .085, lambda: go_menu())


def finish(kind):
    win = kind == "win"
    rel = "ui/banner_win.png" if win else "ui/banner_lose.png"
    iw, ih = img_size(rel)
    end_banner.texture = tex(rel)
    end_banner.scale = (0.36, 0.36 * ih / iw)
    end_root.y = -0.04
    end_lbl["score"].text = str(game.score)
    end_lbl["sawit"].text = str(game.total - len(game.palms))
    end_lbl["algo"].text = f"Algoritma: {game.algo}"
    set_state("end")
    snd.sfx(kind, delay=0.3 if win else 0.45)


# ---------------------------------------------------------------- alur state ----
def set_camera_top():
    p = math.radians(TOP_PITCH)
    camera.position = Vec3(CX, TOP_DIST * math.sin(p),
                           CZ - TOP_DIST * math.cos(p))
    camera.rotation = Vec3(TOP_PITCH, 0, 0)


def set_state(s):
    S.state = s
    S.overlay = None
    menu.enabled = s == "menu"
    hud.enabled = s in ("play", "end")
    settings_root.enabled = s == "settings"
    stats_root.enabled = s == "stats"
    end_root.enabled = s == "end"
    pause_root.enabled = info_root.enabled = ghost_root.enabled = False
    if world is not None:
        world.enabled = s in ("play", "end")
    camera.position = Vec3(0, 0, -20)
    camera.rotation = Vec3(0, 0, 0)
    window.color = rgb(205, 150, 110) if s in (
        "play", "end") else rgb(30, 20, 20)
    if s in ("play", "end"):
        if S.cam == "top":
            set_camera_top()
    if game is not None and s != "play":
        game.paused = True
    if s != "play":
        snd.set_music_pitch(1.0)
    if s == "play":
        snd.music("game")
    elif s == "end":
        snd.stop_music()             # diganti jingle menang / kalah
    else:
        snd.music("menu")


def open_settings_page():
    S.settings_from = "menu"
    set_bg.enabled = True
    set_dim.enabled = False
    refresh_settings()
    set_state("settings")


def open_overlay(name, came_from=None):
    if S.state != "play":
        return
    if name == "settings":
        S.settings_from = came_from or "play"
        pause_root.enabled = False if came_from != "pause" else pause_root.enabled
        set_bg.enabled = False
        set_dim.enabled = came_from != "pause"
        settings_root.enabled = True
        settings_root.z = -6
        refresh_settings()
    elif name == "pause":
        pause_root.enabled = True
    elif name == "info":
        show_info()
        info_root.enabled = True
    elif name == "ghost":
        ghost_root.enabled = True
    S.overlay = name
    game.paused = True


def close_settings():
    if S.state == "settings":                      # halaman dari menu
        set_state("menu")
        return
    settings_root.enabled = False
    settings_root.z = 0
    if S.settings_from == "pause":
        S.overlay = "pause"
        pause_root.enabled = True
    else:
        S.overlay = None
        game.paused = False


def close_overlay():
    if S.overlay == "settings":
        close_settings()
        return
    pause_root.enabled = False
    info_root.enabled = False
    S.overlay = None
    if game is not None:
        game.paused = False
    ghost_root.enabled = False


def go_menu():
    set_state("menu")


def start_game():
    global game
    if game is not None and refs.get("viz"):
        clear_all_viz()                  # hapus semua jalur dari permainan sebelumnya
    game = Core(S.algo, S.diff, record=S.record)
    build_world()
    print("entities:", len(scene.entities))
    build_minimap_markers()
    S.viz = False
    set_state("play")
    game.paused = False
    snd.sfx("start")
    flash("SIAP!", 1.4)


# -------------------------------------------------------------- input/update ----
KEYS = {"left arrow": "L", "a": "L", "right arrow": "R", "d": "R", "up arrow": "F", "w": "F",
        "down arrow": "B", "s": "B"}
ABS = {"L": (-1, 0), "R": (1, 0), "F": (0, -1), "B": (0, 1)}


def steer(code):
    if S.cam == "top":
        game.want_dir(ABS[code])
        return
    # kamera belakang: kontrol relatif terhadap arah hadap
    fx, fy = game.face
    d = {"F": (fx, fy), "B": (-fx, -fy), "L": (fy, -fx), "R": (-fy, fx)}[code]
    game.want_dir(d)


def input(key):
    st = S.state
    if st == "menu":
        if key in ("enter", "space"):
            start_game()
        elif key == "t":
            open_stats()
    elif st == "play":
        if S.overlay is not None:
            return
        if key in KEYS:
            steer(KEYS[key])
        elif key == "tab":
            pick_algo("GBFS" if game.algo == "A*" else "A*")
            flash(f"Algoritma: {game.algo}", 1.0,
                  color.azure if game.algo == "A*" else color.orange)
        elif key in ("1", "2"):
            pick_algo(ALGOS[int(key) - 1])
        elif key == "v":
            S.viz = not S.viz
            for v in refs["viz"].values():
                if v is not None:
                    v.enabled = S.viz
            if S.viz:
                for idx in game.last:
                    refresh_viz(idx)
        elif key == "c":
            S.cam = "top" if S.cam == "pov" else "pov"
            if S.cam == "top":
                set_camera_top()
    elif st == "end":
        if key == "enter":
            start_game()
    elif st == "stats":
        if key == "b":
            S.bench_seed += 1
            open_stats()
        elif key == "c":
            S.stats = {a: dict(n=0, nodes=0, plen=0, ms=0.0, fail=0)
                       for a in ALGOS}
            open_stats()
        elif key == "escape":
            set_state("menu")


def refresh_viz(idx):
    old = refs["viz"].get(idx)
    if old is not None:
        destroy(old)
    refs["viz"][idx] = None
    res = game.last.get(idx)
    f = game.fires[idx] if idx < len(game.fires) else None
    ok = (res and S.viz and f is not None
          and f.state == "active"                    # monster mati: tanpa jalur
          and game.water <= 0)                       # efek air aktif: tanpa jalur
    if ok:
        refs["viz"][idx] = build_viz(res, idx)


def handle_events():
    for kind, data in game.events:
        if kind == "palm":
            m = refs["palm"].pop(data, None)
            refs["attack"] = ATTACK_TIME
            refs["player"].play("attack", restart=True)
            snd.sfx("slash", pitch=random.uniform(0.95, 1.1))
            snd.sfx("palm", pitch=random.uniform(0.92, 1.08), delay=0.15)
            if m is not None:
                refs["fall"].append([m, 0.0])
        elif kind == "water":
            m = refs["water"].pop(data, None)
            if m is not None:
                destroy(m.root)
            snd.sfx("water")
            snd.sfx("info", delay=0.5)
            open_overlay("info")
        elif kind == "extinguish":
            idx, gp = data
            clear_viz(idx)
            burst(W(*gp), color.azure)
            snd.sfx("extinguish")
            flash("+200", 0.8, color.white)
        elif kind == "hit":
            flash("Kena monster!", 1.2, color.red)
            snd.sfx("hit")
        elif kind == "path":
            if S.viz:
                refresh_viz(data)
        elif kind in ("win", "lose"):
            finish(kind)
    game.events.clear()


def clear_viz(idx):
    old = refs["viz"].get(idx)
    if old is not None:
        destroy(old)
    refs["viz"][idx] = None
    if game is not None:
        # supaya tombol V tidak menggambar ulang jalur lama
        game.last.pop(idx, None)


def clear_all_viz():
    for k in list(refs["viz"]):
        clear_viz(k)


def sync_world(dt):
    g = game
    refs["tt"] += dt
    tt = refs["tt"]
    p, pa = g.player, refs["player"]
    px, py = p.pos()
    moving = not p.idle
    pos = W(px, py)
    pa.root.position = pos
    yaw_t = heading_yaw(*g.face) + YAW_OFFSET
    refs["player_yaw"] = approach_angle(
        refs["player_yaw"], yaw_t, min(1, 14 * dt))
    pa.root.rotation_y = refs["player_yaw"]
    if refs["attack"] > 0:
        refs["attack"] -= dt
        pa.play("attack")
    else:
        pa.play("walk" if moving else "idle")
    pa.speed = pa.duration(
        "attack") / ATTACK_TIME if refs["attack"] > 0 else (1.3 if moving else 1.0)
    if not g.paused:
        pa.update(dt)
    blink = g.invuln > 0 and int(tt * 10) % 2 == 0 and g.freeze <= 0
    if blink != refs["blink"]:
        refs["blink"] = blink
        pa.hide() if blink else pa.show()

    frightened = g.water > 0
    warn = frightened and g.water < 2.0 and int(tt * 6) % 2 == 0
    for i, (f, m) in enumerate(zip(g.fires, refs["mon"])):
        if f.state != "active":
            m["h"].hide()
            m["b"].hide()
            if refs["viz"].get(f.idx) is not None or f.idx in g.last:
                # monster mati -> jalurnya ikut hilang
                clear_viz(f.idx)
            continue
        use_baby = frightened and not warn
        cur, other = (m["b"], m["h"]) if use_baby else (m["h"], m["b"])
        other.hide()
        cur.show()
        # pasang ulang warna tiap frame (Baby Banban tidak diwarnai, Blinky tetap warna asli)
        if cur is m["h"] and i % 4 != 0:
            cur.root.setColorScale(*GHOSTS[i % 4]["col"], 1)
        else:
            cur.root.setColorScale(1, 1, 1, 1)
        fx, fy = f.m.pos()
        cur.root.position = W(fx, fy)
        m["yaw"] = approach_angle(m["yaw"], heading_yaw(
            *f.heading) + MONSTER_YAW_OFFSET, min(1, 10 * dt))
        cur.root.rotation_y = m["yaw"]
        cur.play("run")
        if not g.paused:
            cur.update(dt)

    for i, m in enumerate(refs["water"].values()):
        m.root.rotation_y += 120 * dt
        m.root.y = 0.9 + 0.15 * math.sin(tt * 3 + i)
    # animasi pohon sawit tumbang
    for item in list(refs["fall"]):
        item[1] += dt
        k = min(1.0, item[1] / 0.45)
        item[0].root.rotation_z = 85 * k
        item[0].root.scale = max(0.01, 1.0 - 0.6 * k)
        if k >= 1.0:
            destroy(item[0].root)
            refs["fall"].remove(item)

    if S.cam == "pov":
        refs["cam_yaw"] = approach_angle(
            refs["cam_yaw"], heading_yaw(*g.face), min(1, 4.5 * dt))
        s, c = math.sin(math.radians(refs["cam_yaw"])), math.cos(
            math.radians(refs["cam_yaw"]))
        camera.position = Vec3(pos.x - s * POV_BACK,
                               POV_UP, pos.z - c * POV_BACK)
        camera.rotation = Vec3(POV_PITCH, refs["cam_yaw"], 0)


def update():
    dt = time.dt
    if msg_timer[0] > 0 and not (S.overlay == "pause"):
        msg_timer[0] -= dt
        if msg_timer[0] <= 0:
            msg.enabled = False
    if S.state not in ("play", "end") or game is None:
        return
    if S.state == "play":
        game.update(dt)
        handle_events()
        snd.set_music_pitch(1.12 if game.water > 0 else 1.0)
    if S.state in ("play", "end"):
        sync_world(dt)
        update_hud()


if __name__ == "__main__":
    refresh_settings()
    set_state("menu")
    app.run()
