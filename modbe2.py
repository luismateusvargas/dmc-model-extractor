"""DMC3: convert big-endian 'MOD ' meshes to OBJ.

PS3 'MOD ' format (big-endian):
    0x00 magic 'MOD ' | 0x04 f32 version | 0x10 u8 objectCount, u8 boneCount, u8 numTex
    0x30 OBJECT records, stride 16:  u8 meshCount | u8 ? | i16 numVerts | i32 mshOffs
         MESH records at mshOffs, stride 32:
           i16 numVerts | i16 texInd | 8 skip |
           i32 pos | i32 nrm | i32 uv | i32 boneIdx | i32 weights
    positions/normals 3xf32, UVs 2xi16/4096 with V flipped, bone 4 B, weights u16.
    Geometry is triangle strips; bit 15 of the weight is the strip break.

Note the PC port puts objects at 0x40 with int64 offsets - that is why IgrBn's
addon silently imports zero objects from PS3 files.

    python modbe2.py [<unpacked dir>] [<output dir>]
"""
import struct
import os
import sys
import glob
import math


def be(fmt, b, o):
    return struct.unpack_from('>' + fmt, b, o)[0]


def get_tris(pos, nrm, skip, n):
    tris = []
    p1, p2 = 0, 1
    for i in range(2, n):
        p3 = i
        if not skip[i]:
            v1, v2, v3 = pos[p1], pos[p2], pos[p3]
            e1 = [v3[k] - v1[k] for k in range(3)]
            e2 = [v2[k] - v1[k] for k in range(3)]
            z = [e1[1]*e2[2] - e1[2]*e2[1],
                 e1[2]*e2[0] - e1[0]*e2[2],
                 e1[0]*e2[1] - e1[1]*e2[0]]
            nn = [nrm[p1][k] + nrm[p2][k] + nrm[p3][k] for k in range(3)]
            d = sum(nn[k] * z[k] for k in range(3))
            tris.append([p1, p3, p2] if d > 0 else [p1, p2, p3])
        p1, p2 = p2, p3
    return tris


def parse(path):
    with open(path, 'rb') as f:
        b = f.read()
    N = len(b)
    if b[:4] != b'MOD ':
        return None
    oc, bc = b[0x10], b[0x11]
    meshes = []
    for oi in range(oc):
        o = 0x30 + oi * 16
        if o + 8 > N:
            break
        meshCount = b[o]
        mshOffs = be('i', b, o + 4)
        if not (0 < mshOffs < N):
            continue
        for mi in range(meshCount):
            m = mshOffs + mi * 32
            if m + 32 > N:
                break
            nv = be('h', b, m)
            tex = be('h', b, m + 2)
            po, no, uo = be('i', b, m + 12), be('i', b, m + 16), be('i', b, m + 20)
            wo = be('i', b, m + 28)
            if nv <= 0:
                continue
            if not all(0 < x < N for x in (po, no, uo, wo)):
                continue
            if po + nv*12 > N or no + nv*12 > N or wo + nv*2 > N:
                continue
            pos = [struct.unpack_from('>3f', b, po + 12*i) for i in range(nv)]
            nrm = [struct.unpack_from('>3f', b, no + 12*i) for i in range(nv)]
            uv = [(be('h', b, uo + 4*i) / 4096., 1. - be('h', b, uo + 4*i + 2) / 4096.)
                  for i in range(nv)]
            skip = [(be('H', b, wo + 2*i) >> 15) & 1 for i in range(nv)]
            meshes.append((oi, mi, tex, pos, nrm, uv, get_tris(pos, nrm, skip, nv)))
    return oc, bc, meshes


def convert_dir(unpacked, outdir):
    """Convert every .mod under `unpacked`. Returns how many OBJ files were written."""
    os.makedirs(outdir, exist_ok=True)
    tot = 0
    for mp in sorted(glob.glob(os.path.join(unpacked, "**", "*.mod"), recursive=True)):
        r = parse(mp)
        if not r:
            continue
        oc, bc, meshes = r
        name = os.path.relpath(mp, unpacked).replace(os.sep, '_')[:-4]
        if not meshes:
            print("--   %-42s objs=%d no meshes" % (name, oc))
            continue
        tv = sum(len(m[3]) for m in meshes)
        tf = sum(len(m[6]) for m in meshes)
        nl = [math.sqrt(sum(c*c for c in n)) for m in meshes for n in m[4][:50]]
        with open(os.path.join(outdir, name + ".obj"), 'w') as f:
            base = 0
            for oi, mi, tex, pos, nrm, uv, tris in meshes:
                f.write("o o%d_m%d_tex%d\n" % (oi, mi, tex))
                for p in pos:
                    f.write("v %.6f %.6f %.6f\n" % p)
                for u in uv:
                    f.write("vt %.6f %.6f\n" % u)
                for n3 in nrm:
                    f.write("vn %.6f %.6f %.6f\n" % n3)
                for t in tris:
                    a, c, d = [x + 1 + base for x in t]
                    f.write("f %d/%d/%d %d/%d/%d %d/%d/%d\n" % (a, a, a, c, c, c, d, d, d))
                base += len(pos)
        tot += 1
        # unit-length normals are the signal the arrays were read correctly
        print("OK   %-42s meshes=%2d verts=%6d tris=%6d nrmlen=%.4f" %
              (name, len(meshes), tv, tf, sum(nl) / len(nl) if nl else 0))
    return tot


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "unpacked"
    out = sys.argv[2] if len(sys.argv) > 2 else "objout"
    print("\nOBJ files written:", convert_dir(src, out))
