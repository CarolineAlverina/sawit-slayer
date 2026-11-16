import sys, tempfile, zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import convert_models as cm
import build_ui

ROOT = Path(__file__).resolve().parent.parent


def unpack(src):
    src = Path(src)
    if src.is_dir():
        base = src
    else:
        base = Path(tempfile.mkdtemp(prefix="sawit_"))
        zipfile.ZipFile(src).extractall(base)
    for z in list(base.rglob("*.zip")):
        d = z.with_suffix("")
        if not d.exists():
            d.mkdir()
            zipfile.ZipFile(z).extractall(d)
    return base


def find(root, name):
    hits = sorted(Path(root).rglob(name))
    if not hits:
        raise SystemExit(f"File tidak ditemukan: {name}")
    return hits[0]


def main(src):
    P = unpack(src)
    kn = find(P, "tree_palmTall.glb").parent
    out = ROOT
    cm.convert(find(P, "firefighter.glb"), "firefighter", out, height=1.7, rot=(0, 180, 0),
            anims={"idle": ("holding-right", True), "walk": ("walk", True), "attack": ("attack-melee-right", False)},
            nframes=8, attach=dict(file=find(P, "weapon-sword.glb"), joint="arm-right"))
    cm.convert(find(P, "garten_of_banban__hellish_banban.glb"), "hellish_banban", out, height=2.2, rot=(0, 180, 0),
            anims={"run": ("Running", True), "idle": ("Idle", True)}, nframes=6, target_tris=9000)
    cm.convert(find(P, "garten_of_banban__baby_banban.glb"), "baby_banban", out, height=1.5, rot=(0, 180, 0),
            anims={"run": ("BabyBanbanRun", True), "walk": ("HappyWalk", True)}, nframes=6, target_tris=6000)
    cm.convert(find(P, "Drop water*.glb"), "water_drop", out, height=0.8)
    cm.convert(kn / "tree_palmDetailedTall.glb", "palm", out, height=1.7)
    cm.convert(kn / "tree_default.glb", "tree_a", out, height=3.4)
    cm.convert(kn / "tree_oak.glb", "tree_b", out, height=3.2)
    cm.convert(kn / "rock_largeA.glb", "rock", out, height=1.4)
    cm.convert(kn / "stump_round.glb", "stump", out, height=0.9)
    build_ui.main(find(P, "bg.png").parent)
    print("Selesai.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
