"""Convert DMC1 / DMC2 models from the PS3 HD Collection to Wavefront OBJ.

    python dmc2obj.py dmc1 "extract/DMC1/data/pld/*.pws" out/DMC1
    python dmc2obj.py dmc2 "extract/DMC2/data/*.mdl"     out/DMC2

Endianness follows the game: DMC1 is big-endian, DMC2 little-endian.
See dmcmesh.py for the format itself.

Each mesh becomes one OBJ group named `obj<NN>_m<MM>_tex<T>`: NN is the model's
own object index (a body part, a weapon, a damage state), MM the mesh within it
and T the texture slot it asks for.
"""
import sys, os, glob, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dmcmesh import Reader

ENDIAN = {"dmc1": ">", "dmc2": "<"}


def convert(path, outdir, endian):
    name = os.path.splitext(os.path.basename(path))[0]
    meshes = Reader(open(path, "rb").read(), endian).find_all()
    meshes = [m for m in meshes if m["tris"]]
    if not meshes:
        print("--   %-16s no meshes" % name)
        return 0
    os.makedirs(outdir, exist_ok=True)
    tv = tf = 0
    nl = []
    seq = {}
    with open(os.path.join(outdir, name + ".obj"), "w") as f:
        f.write("# %s - Devil May Cry HD Collection (PS3)\n" % name)
        base = 0
        for m in meshes:
            oi = m.get("obj", 0)
            mi = seq[oi] = seq.get(oi, -1) + 1
            f.write("o %s_obj%02d_m%02d_tex%d\n" % (name, oi, mi, m.get("tex", 0)))
            for p in m["pos"]:
                f.write("v %.6f %.6f %.6f\n" % p)
            for u in m["uv"]:
                f.write("vt %.6f %.6f\n" % u)
            for n in m["nrm"]:
                f.write("vn %.6f %.6f %.6f\n" % n)
            for t in m["tris"]:
                a, c, d = [x + 1 + base for x in t]
                f.write("f %d/%d/%d %d/%d/%d %d/%d/%d\n" % (a, a, a, c, c, c, d, d, d))
            base += m["nv"]
            tv += m["nv"]
            tf += len(m["tris"])
            nl += [math.sqrt(sum(c*c for c in n)) for n in m["nrm"][:50]]
    # unit-length normals are the signal that the arrays were read correctly
    print("OK   %-16s meshes=%3d verts=%6d tris=%6d nrmlen=%.4f" %
          (name, len(meshes), tv, tf, sum(nl) / len(nl)))
    return 1


if __name__ == "__main__":
    game, outdir = sys.argv[1], sys.argv[-1]
    n = 0
    for pat in sys.argv[2:-1]:
        for p in sorted(glob.glob(pat)):
            n += convert(p, outdir, ENDIAN[game])
    print("\nOBJ written:", n)
