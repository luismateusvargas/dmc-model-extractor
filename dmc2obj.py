"""Convert DMC1 / DMC2 models from the PS3 HD Collection to Wavefront OBJ.

    python dmc2obj.py dmc1 "extract/DMC1/data/pld/*.pws" out/DMC1
    python dmc2obj.py dmc2 "extract/DMC2/data/*.mdl"     out/DMC2

Endianness follows the game: DMC1 is big-endian, DMC2 little-endian.
See dmcmesh.py for the format itself.

Each mesh becomes one OBJ group named `obj<NN>_m<MM>_tex<T>`: NN is the model's
own object index (a body part, a weapon, a damage state), MM the mesh within it
and T the texture slot it asks for. Slot T is resolved against the textures in
the same file and written out beside the OBJ, so the .mtl loads with it.
"""
import sys, os, glob, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dmctex
from dmcmesh import Reader

ENDIAN = {"dmc1": ">", "dmc2": "<"}


def convert(path, outdir, endian):
    name = os.path.splitext(os.path.basename(path))[0]
    data = open(path, "rb").read()
    # the reader skips the junk bytes a couple of files carry in front of the
    # MOMO magic; do the same here so texture and mesh offsets agree
    if data[:4] != b"MOMO" and b"MOMO" in data[:16]:
        data = data[data.index(b"MOMO"):]
    meshes = Reader(data, endian).find_all()
    meshes = [m for m in meshes if m["tris"]]
    if not meshes:
        print("--   %-16s no meshes" % name)
        return 0
    os.makedirs(outdir, exist_ok=True)

    # DMC1 keeps its images in Pipeworks containers, DMC2 in TIM2 blocks
    # grouped by MOMO section; either way they follow the geometry using them
    sets = dmctex.pipeworks_sets(data) if endian == ">" else dmctex.tim2_sets(data)
    for m, k in zip(meshes, dmctex.assign(sets, [(m["po"], m.get("tex", 0))
                                                 for m in meshes])):
        m["mtl"] = None if k is None else (k, m.get("tex", 0))
    mtls = dmctex.save(sets, outdir, name, {m["mtl"] for m in meshes if m["mtl"]})
    if mtls:
        dmctex.write_mtl(os.path.join(outdir, name + ".mtl"), name, mtls)

    tv = tf = 0
    nl = []
    seq = {}
    with open(os.path.join(outdir, name + ".obj"), "w") as f:
        f.write("# %s - Devil May Cry HD Collection (PS3)\n" % name)
        if mtls:
            f.write("mtllib %s.mtl\n" % name)
        base = 0
        for m in meshes:
            oi = m.get("obj", 0)
            mi = seq[oi] = seq.get(oi, -1) + 1
            tex = m.get("tex", 0)
            f.write("o %s_obj%02d_m%02d_tex%d\n" % (name, oi, mi, tex))
            if m["mtl"]:
                f.write("usemtl %s\n" % mtls[m["mtl"]])
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
    print("OK   %-16s meshes=%3d verts=%6d tris=%6d nrmlen=%.4f tex=%d" %
          (name, len(meshes), tv, tf, sum(nl) / len(nl), len(mtls)))
    return 1


if __name__ == "__main__":
    game, outdir = sys.argv[1], sys.argv[-1]
    n = 0
    for pat in sys.argv[2:-1]:
        for p in sorted(glob.glob(pat)):
            n += convert(p, outdir, ENDIAN[game])
    print("\nOBJ written:", n)
