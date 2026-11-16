
import sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter

Image.MAX_IMAGE_PIXELS = None
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "ui"


def load(src, name):
    return Image.open(Path(src) / name).convert("RGBA")


def save(im, name, width=None, jpg=False):
    if width and im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    OUT.mkdir(exist_ok=True)
    if jpg:
        bg = Image.new("RGB", im.size, (0, 0, 0)); bg.paste(im, mask=im.split()[3])
        bg.save(OUT / f"{name}.jpg", quality=86)
    else:
        im.save(OUT / f"{name}.png", optimize=True)


def _box(arr, r):
    H, W = arr.shape[:2]
    pad = np.pad(arr, ((r + 1, r), (r + 1, r), (0, 0)), mode="edge")
    c = pad.cumsum(0).cumsum(1)
    return c[2 * r + 1:2 * r + 1 + H, 2 * r + 1:2 * r + 1 + W] - c[:H, 2 * r + 1:2 * r + 1 + W] \
        - c[2 * r + 1:2 * r + 1 + H, :W] + c[:H, :W]


def erase_white(im, region, exclude=(), dilate=11, thr=195):
    """Hapus piksel putih (teks) di region (x0,y0,x1,y1 pecahan), isi dari piksel sekitar yang bersih."""
    a = np.array(im).astype(float)
    H, W = a.shape[:2]
    fr = lambda r: [int(r[0] * W), int(r[1] * H), int(r[2] * W), int(r[3] * H)]
    x0, y0, x1, y1 = fr(region)
    white = (a[:, :, :3].min(2) > thr) & (a[:, :, 3] > 200)
    m = np.zeros((H, W), bool)
    m[y0:y1, x0:x1] = white[y0:y1, x0:x1]
    for e in exclude:
        ex0, ey0, ex1, ey1 = fr(e); m[ey0:ey1, ex0:ex1] = False
    m = np.array(Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(dilate | 1))) > 0
    for e in exclude:
        ex0, ey0, ex1, ey1 = fr(e); m[ey0:ey1, ex0:ex1] = False
    out = a.copy()
    valid = (~m).astype(float)[:, :, None]
    todo = m.copy()
    r = max(3, dilate // 2)
    for _ in range(40):
        if not todo.any():
            break
        num = _box(out[:, :, :3] * valid, r)
        den = _box(valid, r)
        ok = todo & (den[:, :, 0] > 0.15)
        out[:, :, :3] = np.where(ok[:, :, None], num / np.maximum(den, 1e-6), out[:, :, :3])
        valid[ok] = 1.0
        todo &= ~ok
        r = min(r + 2, 40)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


def main(src):
    src = Path(src)
    # latar belakang
    for n, o in (("bg start.png", "bg_start"), ("bg setting.png", "bg_setting"), ("bg.png", "bg")):
        save(load(src, n), o, 1600, jpg=True)
    save(load(src, "Sawit #U2028Slayer.png"), "title", 800)

    # tombol menu
    sheet = load(src, "Frame 2610449.png")
    A = np.array(sheet)[:, :, 3].max(1) > 0
    segs, s = [], None
    for i, v in enumerate(A):
        if v and s is None: s = i
        if not v and s is not None:
            segs.append((s, i - 1)); s = None
    segs = [g for g in segs if g[1] - g[0] > 20]
    for (a, b), n in zip(segs, ("btn_start", "btn_settings", "btn_stats", "btn_quit")):
        c = sheet.crop((0, a, sheet.width, b + 1))
        c = c.crop(c.getbbox())
        save(c, n, 420)

    # panel
    sp = load(src, "Settings panel.png")
    W, H = sp.size
    arr = np.array(sp)
    for cy in (0.298, 0.415):
        y0, y1 = int((cy - 0.045) * H), int((cy + 0.045) * H)
        x0, x1 = int(0.345 * W), int(0.445 * W)
        for y in range(y0, y1):
            arr[y, x0:x1] = arr[y, int(0.33 * W)]
    save(Image.fromarray(arr), "settings_panel", 1000)
    save(load(src, "paused.png"), "paused_panel", 560)

    # papan info karhutla
    boards = ["Papan.png", "info.png", "info1.png"] + [f"Group {i}.png" for i in range(6, 12)]
    for i, n in enumerate(boards, 1):
        save(load(src, n), f"info_{i}", 640)

    # papan skor tanpa teks bawaan
    bd = load(src, "Papan skor.png")
    bd = erase_white(bd, (0.15, 0.0, 0.90, 0.60), exclude=[(0.385, 0.365, 0.503, 0.49)], dilate=21)
    save(bd, "board_score", 620)

    # pil HUD
    sc = erase_white(load(src, "Score.png"), (0.05, 0.1, 0.95, 0.9), dilate=9)
    save(sc, "pill_score", 420)
    sw = erase_white(load(src, "sawit collect.png"), (0.30, 0.1, 0.97, 0.9), dilate=9)
    save(sw, "pill_sawit", 420)
    save(load(src, "Algo A_.png"), "pill_algo_astar", 420)
    save(load(src, "Algo GBFS.png"), "pill_algo_gbfs", 420)

    # ikon dan lain-lain
    for n, o in (("ikon back.png", "icon_back"), ("ikon pause.png", "icon_pause"), ("ikon settings.png", "icon_settings"),
                ("ikon silang.png", "icon_close"), ("kepala.png", "icon_head"), ("water.png", "water_bar"),
                ("frame minimap.png", "frame_minimap"), ("MENANG.png", "banner_win"), ("KALAH.png", "banner_lose"),
                ("sawit collect.png", "pill_sawit_full")):
        save(load(src, n), o, 640 if o in ("water_bar", "frame_minimap", "banner_win", "banner_lose") else 160)
    print("UI selesai ->", OUT)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
