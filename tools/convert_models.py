
import io, json, math, struct
from pathlib import Path
from urllib.parse import unquote
import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
LIGHT = np.array([0.35, 0.8, -0.5]); LIGHT /= np.linalg.norm(LIGHT)


# GLB dasar
class GLB:
    def __init__(self, path):
        self.path = Path(path)
        b = self.path.read_bytes()
        off, self.js, self.bn = 12, None, b""
        while off < len(b):
            cl, ct = struct.unpack("<II", b[off:off + 8])
            d = b[off + 8:off + 8 + cl]
            if ct == 0x4E4F534A: self.js = json.loads(d)
            elif ct == 0x004E4942: self.bn = d
            off += 8 + cl
        js = self.js
        self.nodes = js["nodes"]
        self.parent = {}
        for i, n in enumerate(self.nodes):
            for c in n.get("children", []):
                self.parent[c] = i
        self.roots = js["scenes"][js.get("scene", 0)]["nodes"]

    def accessor(self, idx):
        js = self.js
        a = js["accessors"][idx]
        bv = js["bufferViews"][a["bufferView"]]
        ncomp = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}[a["type"]]
        dt = {5126: np.float32, 5123: np.uint16, 5125: np.uint32, 5121: np.uint8, 5120: np.int8, 5122: np.int16}[a["componentType"]]
        isz = np.dtype(dt).itemsize
        stride = bv.get("byteStride") or isz * ncomp
        start = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        cnt = a["count"]
        raw = np.frombuffer(self.bn, dtype=np.uint8, count=stride * (cnt - 1) + isz * ncomp, offset=start)
        out = np.lib.stride_tricks.as_strided(raw, shape=(cnt, isz * ncomp), strides=(stride, 1)).copy()
        arr = out.view(dt).reshape(cnt, ncomp)
        if a.get("normalized") and dt != np.float32:
            arr = arr / float(np.iinfo(dt).max)
        return arr

    def image(self, img_idx, tex_size):
        im = self.js["images"][img_idx]
        if "bufferView" in im:
            bv = self.js["bufferViews"][im["bufferView"]]
            data = self.bn[bv.get("byteOffset", 0):bv.get("byteOffset", 0) + bv["byteLength"]]
            img = Image.open(io.BytesIO(data))
        else:
            p = self.path.parent / unquote(im["uri"])
            img = Image.open(p)
        img = img.convert("RGBA")
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255)) 
        img = Image.alpha_composite(bg, img).convert("RGB")
        img.thumbnail((tex_size, tex_size))
        return img

    #transformasi node
    def local_trs(self, i):
        n = self.nodes[i]
        if "matrix" in n:
            M = np.array(n["matrix"], float).reshape(4, 4).T
            return ("M", M)
        return (np.array(n.get("translation", [0, 0, 0]), float),
                np.array(n.get("rotation", [0, 0, 0, 1]), float),
                np.array(n.get("scale", [1, 1, 1]), float))

    @staticmethod
    def trs_matrix(t, q, s):
        x, y, z, w = q / np.linalg.norm(q)
        R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                      [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                      [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
        M = np.eye(4); M[:3, :3] = R * s; M[:3, 3] = t
        return M

    def globals(self, pose=None):
        """Matriks global semua node. pose: {node: (t, q, s)} menimpa transformasi lokal."""
        pose = pose or {}
        G = {}

        def rec(i, parent):
            if i in pose: loc = self.trs_matrix(*pose[i])
            else:
                l = self.local_trs(i)
                loc = l[1] if isinstance(l[0], str) else self.trs_matrix(*l)
            G[i] = parent @ loc
            for c in self.nodes[i].get("children", []):
                rec(c, G[i])

        for r in self.roots:
            rec(r, np.eye(4))
        return G

    # animasi
    def anim_index(self, key):
        for i, a in enumerate(self.js.get("animations", [])):
            if key.lower() in (a.get("name") or "").lower():
                return i
        raise KeyError(f"animasi '{key}' tidak ada di {self.path.name}")

    def anim_duration(self, ai):
        a = self.js["animations"][ai]
        return max(float(self.accessor(s["input"]).max()) for s in a["samplers"])

    def sample(self, ai, t):
        a = self.js["animations"][ai]
        pose = {}
        for ch in a["channels"]:
            node, path = ch["target"]["node"], ch["target"]["path"]
            if path not in ("translation", "rotation", "scale"):
                continue
            sm = a["samplers"][ch["sampler"]]
            times = self.accessor(sm["input"]).reshape(-1)
            vals = self.accessor(sm["output"]).astype(float)
            if sm.get("interpolation") == "CUBICSPLINE":
                vals = vals[1::3]
            if node not in pose:
                l = self.local_trs(node)
                pose[node] = [np.zeros(3), np.array([0, 0, 0, 1.]), np.ones(3)] if isinstance(l[0], str) else list(l)
            tt = min(max(t, times[0]), times[-1])
            k = int(np.searchsorted(times, tt, side="right") - 1)
            k = min(max(k, 0), len(times) - 2) if len(times) > 1 else 0
            if len(times) == 1:
                v = vals[0]
            else:
                f = (tt - times[k]) / max(times[k + 1] - times[k], 1e-9)
                if sm.get("interpolation") == "STEP": f = 0.0
                a0, a1 = vals[k], vals[k + 1]
                if path == "rotation":
                    if np.dot(a0, a1) < 0: a1 = -a1
                    v = a0 * (1 - f) + a1 * f                       # nlerp (cukup untuk frame berdekatan)
                    v = v / np.linalg.norm(v)
                else:
                    v = a0 * (1 - f) + a1 * f
            pose[node][{"translation": 0, "rotation": 1, "scale": 2}[path]] = v
        return {n: tuple(v) for n, v in pose.items()}


# simplifikasi
def cluster_decimate(P, T, target):
    """Vertex clustering. Mengembalikan (index vertex perwakilan, segitiga baru)."""
    if len(T) <= target:
        return np.arange(len(P)), T
    lo, hi = P.min(0), P.max(0)
    span = float((hi - lo).max())
    best = None
    a, b = span / 400, span / 3
    for _ in range(18):
        s = (a + b) / 2
        key = np.floor((P - lo) / s).astype(np.int64)
        _, inv = np.unique(key[:, 0] * 1000003 * 1000003 + key[:, 1] * 1000003 + key[:, 2], return_inverse=True)
        t2 = inv[T]
        ok = (t2[:, 0] != t2[:, 1]) & (t2[:, 1] != t2[:, 2]) & (t2[:, 0] != t2[:, 2])
        n = int(ok.sum())
        best = (inv, t2[ok])
        if n > target: a = s
        else: b = s
    inv, t2 = best
    nclu = inv.max() + 1
    cen = np.zeros((nclu, 3)); cnt = np.zeros(nclu)
    np.add.at(cen, inv, P); np.add.at(cnt, inv, 1)
    cen /= cnt[:, None]
    d = np.linalg.norm(P - cen[inv], axis=1)
    order = np.lexsort((d, inv))
    first = np.ones(len(order), bool); first[1:] = inv[order][1:] != inv[order][:-1]
    rep = order[first]
    t2 = np.unique(np.sort(t2, axis=1), axis=0) if False else t2
    return rep, t2


# konversi
def rot_matrix(rx=0, ry=0, rz=0):
    def R(a, ax):
        c, s = math.cos(math.radians(a)), math.sin(math.radians(a))
        return {"x": np.array([[1, 0, 0], [0, c, -s], [0, s, c]]),
                "y": np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]]),
                "z": np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])}[ax]
    return R(rz, "z") @ R(ry, "y") @ R(rx, "x")


def collect_prims(g, target_tris=None):
    """Kumpulkan primitive (posisi rest, uv, normal, warna, joints, weights, indeks, material)."""
    js, prims = g.js, []
    rest = g.globals()
    total_tris = 0
    raw = []
    for ni, n in enumerate(g.nodes):
        if "mesh" not in n or ni not in rest:
            continue
        for pr in js["meshes"][n["mesh"]]["primitives"]:
            if pr.get("mode", 4) != 4:
                continue
            raw.append((ni, n, pr))
            total_tris += g.accessor(pr["indices"]).size // 3 if "indices" in pr else 0
    for ni, n, pr in raw:
        at = pr["attributes"]
        pos = g.accessor(at["POSITION"]).astype(float)
        nor = g.accessor(at["NORMAL"]).astype(float) if "NORMAL" in at else np.tile([0, 1, 0.], (len(pos), 1))
        uv = g.accessor(at["TEXCOORD_0"]).astype(float) if "TEXCOORD_0" in at else np.zeros((len(pos), 2))
        uv[:, 1] = 1 - uv[:, 1]
        idx = g.accessor(pr["indices"]).reshape(-1).astype(np.int64) if "indices" in pr else np.arange(len(pos))
        tri = idx.reshape(-1, 3)
        skinned = "skin" in n and "JOINTS_0" in at
        joints = g.accessor(at["JOINTS_0"]).astype(np.int64) if skinned else None
        weights = g.accessor(at["WEIGHTS_0"]).astype(float) if skinned else None
        mat = js["materials"][pr["material"]] if "material" in pr else {}
        pbr = mat.get("pbrMetallicRoughness", {})
        col = np.array(pbr.get("baseColorFactor", [1, 1, 1, 1]), float)
        tex = None
        if "baseColorTexture" in pbr:
            tex = js["textures"][pbr["baseColorTexture"]["index"]]["source"]
        if not skinned:
            M = rest[ni]
            pos = (M[:3, :3] @ pos.T).T + M[:3, 3]
            nor = (np.linalg.inv(M[:3, :3]).T @ nor.T).T
            if np.linalg.det(M[:3, :3]) < 0:
                tri = tri[:, ::-1]
        if target_tris and total_tris > target_tris:
            share = max(200, int(target_tris * len(tri) / total_tris))
            rep, tri = cluster_decimate(pos, tri, share)
            pos, nor, uv = pos[rep], nor[rep], uv[rep]
            if skinned: joints, weights = joints[rep], weights[rep]
        nor = nor / np.maximum(np.linalg.norm(nor, axis=1, keepdims=True), 1e-9)
        prims.append(dict(node=ni, skinned=skinned, pos=pos, nor=nor, uv=uv, tri=tri, joints=joints,
                        weights=weights, color=col, tex=tex, mat=pr.get("material", -1),
                        skin=n.get("skin")))
    return prims


def skin_positions(g, prim, G):
    sk = g.js["skins"][prim["skin"]]
    ibm = g.accessor(sk["inverseBindMatrices"]).reshape(-1, 4, 4).transpose(0, 2, 1)   # kolom-mayor -> baris
    M = np.stack([G[j] @ ibm[k] for k, j in enumerate(sk["joints"])])
    hom = np.hstack([prim["pos"], np.ones((len(prim["pos"]), 1))])
    out = np.zeros((len(hom), 3))
    for k in range(4):
        w = prim["weights"][:, k:k + 1]
        Mk = M[prim["joints"][:, k]]
        out += w * np.einsum("nij,nj->ni", Mk[:, :3, :], hom)
    return out


def convert(path, name, out, height, rot=(0, 0, 0), anims=None, target_tris=None, nframes=8,
            tex_size=512, bake=True, attach=None, face_flip=True):
    """anims: {"nama_game": ("kunci_nama_animasi_glb", loop?)}"""
    g = GLB(path)
    prims = collect_prims(g, target_tris)
    rest = g.globals()
    R = rot_matrix(*rot)

    frames_pose = [None]
    anim_meta = {}
    if anims:
        frames_pose = []
        for gname, (key, loop) in anims.items():
            ai = g.anim_index(key)
            dur = g.anim_duration(ai)
            n = nframes
            ts = [dur * i / n for i in range(n)] if loop else [dur * i / max(n - 1, 1) for i in range(n)]
            anim_meta[gname] = [len(frames_pose), n, round(dur, 3), bool(loop)]
            frames_pose += [(ai, t) for t in ts]

    def pose_G(fp):
        return rest if fp is None else g.globals(g.sample(*fp))

    Gs = [pose_G(fp) for fp in frames_pose]

    # posisi per frame per primitive
    for p in prims:
        p["frames"] = []
        for G in Gs:
            p["frames"].append(skin_positions(g, p, G) if p["skinned"] else p["pos"])

    # lampiran (pedang) pada joint
    if attach:
        sg = GLB(attach["file"])
        sp = collect_prims(sg)
        arm = next(i for i, n in enumerate(g.nodes) if n.get("name") == attach["joint"])
        # titik tangan: ujung bawah vertex yang terikat dominan pada joint lengan
        pts = []
        for p in prims:
            if p["skinned"]:
                sk = g.js["skins"][p["skin"]]
                jn = np.array(sk["joints"])[p["joints"][np.arange(len(p["pos"])), p["weights"].argmax(1)]]
                sel = jn == arm
                if sel.any(): pts.append(p["pos"][sel])
        pts = np.vstack(pts)
        lowest = pts[pts[:, 1] <= np.percentile(pts[:, 1], 15)]
        hand_rest = lowest.mean(0)
        hand_local = np.linalg.inv(rest[arm]) @ np.append(hand_rest, 1)
        O = np.eye(4)
        O[:3, :3] = rot_matrix(*attach.get("rot", (0, 0, 0))) * attach.get("scale", 1.0)
        O[:3, 3] = hand_local[:3] + np.array(attach.get("offset", (0, 0, 0)))
        for q in sp:
            q["skinned"] = False
            q["frames"] = []
            for G in Gs:
                Mq = G[arm] @ O
                q["frames"].append((Mq[:3, :3] @ q["pos"].T).T + Mq[:3, 3])
            q["nor_static"] = q["nor"]
        prims += [dict(q, node=-1, skin=None, from_attach=True, gsrc=sg) for q in sp]

    # normalisasi memakai bounding box pose diam (frame 0) dari primitive utama
    main = [p for p in prims if not p.get("from_attach")]
    allp = np.vstack([p["frames"][0] for p in main]) @ R.T
    lo, hi = allp.min(0), allp.max(0)
    s = height / (hi[1] - lo[1])
    c0 = np.array([(lo[0] + hi[0]) / 2, lo[1], (lo[2] + hi[2]) / 2])

    def norm(P):
        P = (P @ R.T - c0) * s
        P[:, 2] *= -1
        return P

    (out / "models").mkdir(parents=True, exist_ok=True)
    (out / "textures").mkdir(parents=True, exist_ok=True)
    parts, tex_cache = {}, {}
    for p in prims:
        src = p.get("gsrc", g)
        tkey = (id(src), p["tex"], tuple(np.round(p["color"], 3)))
        part = parts.setdefault(tkey, dict(P=[], U=[], C=[], T=[], F=[], tex=None, base=0))
        if p["tex"] is not None and part["tex"] is None:
            fn = f"{name}_{len(tex_cache)}.png"
            src.image(p["tex"], tex_size).save(out / "textures" / fn)
            tex_cache[tkey] = fn
            part["tex"] = fn
        n0 = part["base"]
        nv = len(p["pos"])
        part["F"].append([norm(f.copy()) for f in p["frames"]])
        part["U"].append(p["uv"])
        nrm = (p["nor"] @ R.T)
        nrm[:, 2] *= -1
        lam = np.clip(nrm @ LIGHT, 0, 1)
        shade = (0.62 + 0.38 * lam)[:, None] if bake else np.ones((nv, 1))
        base_col = np.ones(3) if p["tex"] is not None else p["color"][:3]
        part["C"].append(np.hstack([base_col * shade, np.ones((nv, 1))]))
        part["T"].append(p["tri"] + n0)
        part["base"] += nv
    jparts = []
    allv = []
    for key, pt in parts.items():
        nf = len(pt["F"][0])
        frames = [np.vstack([pt["F"][k][fi] for k in range(len(pt["F"]))]) for fi in range(nf)]
        allv.append(frames[0])
        jparts.append(dict(texture=pt["tex"],
                        uvs=np.round(np.vstack(pt["U"]), 4).tolist(),
                        colors=np.round(np.clip(np.vstack(pt["C"]), 0, 1), 3).tolist(),
                        triangles=np.vstack(pt["T"]).reshape(-1).astype(int).tolist(),
                        frames=[np.round(f, 4).reshape(-1).tolist() for f in frames]))
    V = np.vstack(allv)
    data = dict(parts=jparts, anims=anim_meta, size=np.round(V.max(0) - V.min(0), 3).tolist())
    (out / "models" / f"{name}.json").write_text(json.dumps(data, separators=(",", ":")))
    ntri = sum(len(jp["triangles"]) // 3 for jp in jparts)
    print(f"{name}: {len(jparts)} bagian, {ntri} segitiga, {len(frames_pose)} frame, ukuran {data['size']}")
    return data
