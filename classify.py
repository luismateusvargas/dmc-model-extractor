"""Classify extracted OBJ meshes: real weapon geometry vs. Blender-primitive-
looking placeholders (discs, quads, boxes, tubes).

Why this exists: the DMC1/DMC2/DMC3 mesh scan pulls out every mesh in a file,
including ones the game never draws as geometry you would recognise -- hand /
back attachment helpers, flat effect and shadow planes, and degenerate scan
hits. Those come out of Blender looking like a default circle, plane, cube or
cylinder. This tool measures each mesh and says which bucket it falls in, so
the real weapons can be labelled without opening 233 files by hand.

    python classify.py [<obj dir> ...]            # default: out/*
    python classify.py --csv report.csv out/DMC1_weapons

No dependencies; stdlib only (matches the rest of the repo).
"""

import glob
import math
import os
import sys

# ---------------------------------------------------------------- obj reading


def read_obj(path):
    """-> [(name, verts, tris)]; verts are (x,y,z), tris index into verts."""
    objs = []
    stem = os.path.splitext(os.path.basename(path))[0]
    verts = []           # every vertex in the file, 1-based in OBJ
    cur = None           # (name, face list)
    groups = []

    def flush():
        if cur is not None:
            groups.append(cur)

    with open(path, "r", errors="replace") as fh:
        for line in fh:
            if line.startswith("v "):
                p = line.split()
                verts.append((float(p[1]), float(p[2]), float(p[3])))
            elif line[:2] in ("o ", "g "):
                flush()
                cur = (line[2:].strip() or stem, [])
            elif line.startswith("f "):
                if cur is None:
                    cur = (stem, [])
                idx = []
                for tok in line.split()[1:]:
                    i = int(tok.split("/")[0])
                    idx.append(i - 1 if i > 0 else len(verts) + i)
                for k in range(1, len(idx) - 1):
                    cur[1].append((idx[0], idx[k], idx[k + 1]))
    flush()

    for gname, faces in groups:
        # Weld by position. The converters emit one vertex per triangle corner
        # (the meshes come from strips), so raw counts are ~2x the real ones and
        # every mesh looks duplicate-heavy. Weld before measuring anything.
        pos, keep = [], {}
        remap = {}
        for i in {idx for t in faces for idx in t}:
            key = (round(verts[i][0], 3), round(verts[i][1], 3),
                   round(verts[i][2], 3))
            if key not in keep:
                keep[key] = len(pos)
                pos.append(verts[i])
            remap[i] = keep[key]
        tris = []
        seen = set()
        for a, b, c in faces:
            a, b, c = remap[a], remap[b], remap[c]
            if a == b or b == c or a == c:
                continue                      # collapsed by the weld
            key = tuple(sorted((a, b, c)))
            if key in seen:
                continue                      # duplicate face
            seen.add(key)
            tris.append((a, b, c))
        objs.append((gname, pos, tris))
    return objs


# ---------------------------------------------------------------- linear alg


def _eigen(m):
    """Symmetric 3x3 -> (eigenvalues, eigenvectors as rows), cyclic Jacobi.

    Must be a real decomposition, not power iteration with deflation: on a flat
    or cylindrical mesh two eigenvalues are equal, and deflation then converges
    twice onto the same axis, which silently reports a flat quad's thickness as
    its width (a 135 x 63 x 0 plane measured 135 x 63 x 63).
    """
    a = [row[:] for row in m]
    v = [[1.0 if i == j else 0.0 for j in range(3)] for i in range(3)]
    for _ in range(100):
        p, q, best = 0, 1, 0.0
        for i in range(3):
            for j in range(i + 1, 3):
                if abs(a[i][j]) > best:
                    p, q, best = i, j, abs(a[i][j])
        if best < 1e-14:
            break
        theta = 0.5 * math.atan2(2.0 * a[p][q], a[q][q] - a[p][p])
        c, s = math.cos(theta), math.sin(theta)
        for k in range(3):                       # A <- G^T A G
            akp, akq = a[k][p], a[k][q]
            a[k][p], a[k][q] = c * akp - s * akq, s * akp + c * akq
        for k in range(3):
            apk, aqk = a[p][k], a[q][k]
            a[p][k], a[q][k] = c * apk - s * aqk, s * apk + c * aqk
        for k in range(3):                       # V <- V G
            vkp, vkq = v[k][p], v[k][q]
            v[k][p], v[k][q] = c * vkp - s * vkq, s * vkp + c * vkq
    pairs = sorted(((a[i][i], [v[0][i], v[1][i], v[2][i]]) for i in range(3)),
                   key=lambda t: -t[0])
    return [p[0] for p in pairs], [p[1] for p in pairs]


def _axes(verts):
    """Principal axes (unit, descending extent), centroid-relative points, and
    the eigenvalues of the covariance."""
    n = len(verts)
    cx = sum(v[0] for v in verts) / n
    cy = sum(v[1] for v in verts) / n
    cz = sum(v[2] for v in verts) / n
    rel = [(v[0] - cx, v[1] - cy, v[2] - cz) for v in verts]
    cov = [[0.0] * 3 for _ in range(3)]
    for r in rel:
        for i in range(3):
            for j in range(3):
                cov[i][j] += r[i] * r[j]
    for i in range(3):
        for j in range(3):
            cov[i][j] /= n

    lam, vecs = _eigen(cov)
    return rel, vecs, lam


# ---------------------------------------------------------------- measurement


def measure(verts, tris):
    n = len(verts)
    m = {"verts": n, "tris": len(tris), "fan": 0.0}
    uniq = set((round(v[0], 3), round(v[1], 3), round(v[2], 3)) for v in verts)
    m["uniq"] = len(uniq)
    if n < 3:
        m.update(planar=1.0, extent=(0.0, 0.0, 0.0), circ=None, tube=None,
                 sphere=None, round=False, area=0.0)
        return m

    rel, ax, lam = _axes(verts)
    proj = [[sum(r[i] * a[i] for i in range(3)) for a in ax] for r in rel]
    ext = tuple(max(p[k] for p in proj) - min(p[k] for p in proj)
                for k in range(3))
    m["extent"] = ext
    # Flatness is thickness against the SHORTER in-plane extent, not the
    # longest one -- otherwise a long thin rod (688 x 13 x 13) reads as flat.
    m["planar"] = (ext[2] / ext[1]) if ext[1] > 1e-9 else 1.0

    # circularity in the dominant plane: spread of radius about the centroid
    r2 = [math.hypot(p[0], p[1]) for p in proj]
    mean = sum(r2) / n
    m["circ"] = (math.sqrt(sum((x - mean) ** 2 for x in r2) / n) / mean
                 if mean > 1e-9 else None)
    # tube-ness: spread of radius about the long axis
    r3 = [math.hypot(p[1], p[2]) for p in proj]
    mean3 = sum(r3) / n
    m["tube"] = (math.sqrt(sum((x - mean3) ** 2 for x in r3) / n) / mean3
                 if mean3 > 1e-9 else None)

    # sphere-ness: spread of the 3D radius about the centroid
    r1 = [math.sqrt(p[0] ** 2 + p[1] ** 2 + p[2] ** 2) for p in proj]
    mean1 = sum(r1) / n
    m["sphere"] = (math.sqrt(sum((x - mean1) ** 2 for x in r1) / n) / mean1
                   if mean1 > 1e-9 else None)
    # exact round dimensions mean the engine authored the volume, not an artist
    m["round"] = all(abs(e - round(e)) < 0.005 and e > 0.5 for e in ext)

    area = 0.0
    for a, b, c in tris:
        u = [verts[b][i] - verts[a][i] for i in range(3)]
        w = [verts[c][i] - verts[a][i] for i in range(3)]
        cr = (u[1] * w[2] - u[2] * w[1],
              u[2] * w[0] - u[0] * w[2],
              u[0] * w[1] - u[1] * w[0])
        area += 0.5 * math.sqrt(sum(x * x for x in cr))
    m["area"] = area

    # fan topology: one vertex touching every triangle == a Blender circle
    if tris:
        hits = {}
        for t in tris:
            for i in t:
                hits[i] = hits.get(i, 0) + 1
        m["fan"] = max(hits.values()) / float(len(tris))
    return m


PRIMITIVE = ("DISC", "QUAD", "PLANE", "TUBE", "BOX", "SPHERE", "DEGENERATE")


def classify(m):
    """-> (label, note). The PRIMITIVE labels are the suspicious ones."""
    label, note = _classify(m)
    if m.get("round") and label != "SPHERE":
        note = (note + "; " if note else "") + \
            "exact round dimensions -> engine volume"
    return label, note


def _classify(m):
    n, t = m["verts"], m["tris"]
    if n < 4 or t == 0 or m["area"] <= 1e-6:
        return "DEGENERATE", "no drawable area after welding"
    ex = m["extent"]
    boxy = ex[2] > 0.6 * ex[0]     # roughly as thick as it is long
    if (m["sphere"] is not None and m["sphere"] < 0.06 and n >= 20 and boxy):
        return "SPHERE", "constant radius in 3D -> reads as a Blender sphere"
    # A constant radius WITHOUT equal extents is a ring, not a ball: all the
    # vertices sit on one circle with nothing in the middle.
    if (m["circ"] is not None and m["circ"] < 0.10 and n >= 12
            and m["planar"] < 0.25 and m["fan"] < 0.5):
        return "DISC", "hollow ring of vertices -> reads as a Blender circle"
    flat = m["planar"] < 0.02
    if flat:
        if m["circ"] is not None and m["circ"] < 0.12 and n >= 6:
            return "DISC", "flat, constant radius -> reads as a Blender circle"
        if n <= 8 and t <= 6:
            return "QUAD", "flat, %d verts / %d tris -> reads as a plane" % (n, t)
        if m["fan"] >= 0.9 and n >= 6:
            return "DISC", "flat triangle fan around one hub vertex"
        return "PLANE", "flat sheet (%d verts) -- effect / shadow / decal?" % n
    if m["tube"] is not None and m["tube"] < 0.12 and t <= 64:
        return "TUBE", "constant radius about its long axis -> cylinder-like"
    if n <= 12 and t <= 16:
        ex = m["extent"]
        boxy = ex[2] > 0.25 * ex[0]
        return ("BOX" if boxy else "QUAD"), "only %d verts / %d tris" % (n, t)
    return "MESH", ""


# ---------------------------------------------------------------------- main


def shape_key(verts, tris):
    """Position-independent fingerprint, so the same part shared by two weapons
    is recognisable even when the two files place it differently."""
    if not verts:
        return None
    n = len(verts)
    c = [sum(v[i] for v in verts) / n for i in range(3)]
    d = sorted(round(math.sqrt(sum((v[i] - c[i]) ** 2 for i in range(3))), 2)
               for v in verts)
    return (n, len(tris), tuple(d))


def analyse(path):
    rows = []
    for name, verts, tris in read_obj(path):
        m = measure(verts, tris)
        m["key"] = shape_key(verts, tris)
        label, note = classify(m)
        rows.append((name, m, label, note))
    return rows


def main(argv):
    csv_path = None
    if argv[:1] == ["--csv"]:
        csv_path = argv[1]
        argv = argv[2:]
    here = os.path.dirname(os.path.abspath(__file__))
    dirs = argv or sorted(d for d in glob.glob(os.path.join(here, "out", "*"))
                          if os.path.isdir(d))
    if not dirs:
        print("No OBJ folders. Run dmcextract.py first, or pass a folder.")
        return 1

    csv_rows = [("folder", "file", "mesh", "label", "verts", "tris",
                 "len", "wid", "thk", "planar", "circ", "tube", "note")]
    shared = {}          # shape fingerprint -> ["file:mesh", ...]
    for d in dirs:
        objs = sorted(glob.glob(os.path.join(d, "*.obj")))
        print("")
        print("=== %s  (%d files)" % (os.path.basename(d), len(objs)))
        for f in objs:
            rows = analyse(f)
            prim = sum(1 for _, _, l, _ in rows if l in PRIMITIVE)
            tris = sum(m["tris"] for _, m, _, _ in rows)
            ptris = sum(m["tris"] for _, m, l, _ in rows if l in PRIMITIVE)
            verdict = ("ALL-PRIMITIVE" if rows and prim == len(rows) else
                       "clean" if prim == 0 else "mixed")
            print("%-44s %2d mesh %6d tris  %-13s  %d primitive, %d%% of tris"
                  % (os.path.basename(f), len(rows), tris, verdict, prim,
                     round(100.0 * ptris / tris) if tris else 0))
            for name, m, label, note in rows:
                ex = m["extent"]
                flag = "<<" if label in PRIMITIVE else "  "
                if m["key"]:
                    shared.setdefault(m["key"], []).append(
                        "%s:%s" % (os.path.splitext(os.path.basename(f))[0],
                                   name))
                print("   %s %-22s %-11s v%-5d t%-5d %7.1f x %6.1f x %6.1f  %s"
                      % (flag, name, label, m["verts"], m["tris"],
                         ex[0], ex[1], ex[2], note))
                csv_rows.append((
                    os.path.basename(d), os.path.basename(f), name, label,
                    m["verts"], m["tris"],
                    "%.2f" % ex[0], "%.2f" % ex[1], "%.2f" % ex[2],
                    "%.4f" % m["planar"],
                    "" if m["circ"] is None else "%.4f" % m["circ"],
                    "" if m["tube"] is None else "%.4f" % m["tube"],
                    note))

    dup = sorted(((k, v) for k, v in shared.items() if len(v) > 1),
                 key=lambda kv: -len(kv[1]))
    if dup:
        print("")
        print("=== parts shared between files (same welded shape) ===")
        for (nv, nt, _), where in dup:
            print("  v%-5d t%-5d  %s" % (nv, nt, ", ".join(where)))

    if csv_path:
        import csv as _csv
        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            _csv.writer(fh).writerows(csv_rows)
        print("")
        print("CSV: %s (%d mesh rows)" % (csv_path, len(csv_rows) - 1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
