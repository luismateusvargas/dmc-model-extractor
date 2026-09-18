"""DMC3: skinned models with their animations, as glTF binary (.glb).

A model PAC carries everything a character needs: the 'MOD ' meshes, the
skeleton inside each MOD, and its motions as 'MOT\\0' entries in the nested
sub-PACs that unpack_all writes out as NN.bin. Players keep most of their
motions outside, in PL???_??_?.PAC next to the model PAC in GDATA.AFS. A motion
belongs to a model when its bone count matches the model's skeleton.

MOD skeleton (big-endian), at the u32 in header 0x1c:
    +0x00 u32 hierarchy off | +0x04 u32 order off | +0x08 u32 ? off
    +0x0c u32 transforms off | +0x10 u32 boneCount     (offsets from skel start)
    hierarchy[i]  u8 parent of bone order[i], 0xff for the root
    order[i]      u8 bone number the i-th hierarchy entry describes
    transforms    boneCount x 32 B: f32 x, y, z (offset from parent), f32 length
The bind pose has no rotations: a bone sits at the sum of its offsets up the
chain, and the mesh is stored already posed there, in model space.

MOD vertex skinning:
    bone  4 x u8 per vertex, each a bone number times 4 (PS2 matrix address);
          bytes 1..3 are the influences, byte 0 is unused
    word  u16: bit 15 is the triangle-strip break, bits 0..14 are three 5-bit
          weights for bytes 1, 2, 3, which add up to 31

MOT (big-endian), preceded by a u32 giving the offset of its track data:
    0x00 'MOT\\0' | 0x08 f32 frames | 0x10 f32 frames | 0x14 u16 ?, u16 ?
    0x18 u16 boneCount | 0x1a boneCount x u16 channel mask
         mask bits 0-2 scale xyz, 3-5 rotation xyz (radians), 6-8 translation xyz
    track data: u32 trackCount, then one track per set bit, bones in order,
                and within a bone translation, rotation, scale (x, y, z each):
        u16 size | u16 keyCount | u16 type | u16 0
        type 1  keys: u16 frame | u16 0 | f32 value, inTangent, outTangent
        type 2  f32 min, range | keys: u16 frame | u16 value
        type 3  f32 min, range, inMin, inRange, outMin, outRange
                keys: u16 frame | u16 value, inTangent, outTangent
    Frames carry bit 15, which is masked off. Tangents are per frame and the
    curve between keys is cubic Hermite. The quantised u16 spans either
    0..65535 or 16383..49151 depending on the encoder, per channel; either way
    the span is [min, min + range].

    python dmc3anim.py [<unpacked dir>] [<GDATA.AFS dir>] [<output dir>] [<pattern>]
"""
import struct
import os
import sys
import glob
import math
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dmctex
import modbe2

FPS = 60.0
# a bone's tracks are stored translation first, then rotation, then scale -
# not in bit order, which only shows on bones that mix the groups
STREAM_ORDER = (6, 7, 8, 3, 4, 5, 0, 1, 2)


def be(fmt, b, o):
    return struct.unpack_from('>' + fmt, b, o)


# ------------------------------------------------------------------ model

def parse_skeleton(b):
    so = be('I', b, 0x1c)[0]
    nb = b[0x11]
    if not so or nb == 0 or so + 0x14 > len(b):
        return None
    ho, oo, _, to, cnt = be('5I', b, so)
    if cnt != nb:
        return None
    parent = [-1] * nb
    for i in range(nb):
        slot = b[so + oo + i]
        p = b[so + ho + i]
        parent[slot] = -1 if p == 0xff else p
    offs = [be('3f', b, so + to + 32 * i) for i in range(nb)]
    world = [None] * nb

    def w(i):
        if world[i] is None:
            p = parent[i]
            base = (0., 0., 0.) if p < 0 else w(p)
            world[i] = tuple(base[k] + offs[i][k] for k in range(3))
        return world[i]
    for i in range(nb):
        w(i)
    return dict(parent=parent, offset=offs, world=world)


def parse_meshes(b):
    """Every mesh with its skin, as triangle lists."""
    N = len(b)
    out = []
    for oi in range(b[0x10]):
        o = 0x30 + oi * 0x30
        mc = b[o]
        mo = be('i', b, o + 4)[0]
        if not 0 < mo < N:
            continue
        for mi in range(mc):
            m = mo + mi * 32
            if m + 32 > N:
                break
            nv, tex = be('hh', b, m)
            po, no, uo, bo, wo = be('5i', b, m + 12)
            if nv <= 0 or not all(0 < x < N for x in (po, no, uo, bo, wo)):
                continue
            if po + nv * 12 > N or no + nv * 12 > N or wo + nv * 2 > N or bo + nv * 4 > N:
                continue
            pos = [be('3f', b, po + 12 * i) for i in range(nv)]
            nrm = [be('3f', b, no + 12 * i) for i in range(nv)]
            uv = [(be('h', b, uo + 4 * i)[0] / 4096., be('h', b, uo + 4 * i + 2)[0] / 4096.)
                  for i in range(nv)]
            words = [be('H', b, wo + 2 * i)[0] for i in range(nv)]
            joints, weights = [], []
            for i in range(nv):
                bb = b[bo + 4 * i:bo + 4 * i + 4]
                wd = words[i] & 0x7fff
                ws = [wd & 31, (wd >> 5) & 31, (wd >> 10) & 31]
                js = [bb[1] >> 2, bb[2] >> 2, bb[3] >> 2]
                rest = 31 - sum(ws)
                js.append(bb[0] >> 2)
                ws.append(max(rest, 0))
                t = float(sum(ws)) or 1.
                joints.append(js)
                weights.append([x / t for x in ws])
            skip = [(x >> 15) & 1 for x in words]
            tris = modbe2.get_tris(pos, nrm, skip, nv)
            out.append(dict(obj=oi, mesh=mi, tex=tex, pos=pos, nrm=nrm, uv=uv,
                            joints=joints, weights=weights, tris=tris))
    return out


# ------------------------------------------------------------------ motion

def _span(qs):
    lo, hi = min(qs), max(qs)
    if lo >= 16382 and hi <= 49152:
        return 16383., 32768.
    return 0., 65535.


def parse_mot(b, o=0):
    """A MOT whose u32 prefix is at `o`. Returns dict or None."""
    if b[o + 4:o + 8] != b'MOT\0':
        return None
    hs = be('I', b, o)[0]
    m = o + 4
    frames = be('f', b, m + 8)[0]
    nb = be('H', b, m + 0x18)[0]
    masks = be('%dH' % nb, b, m + 0x1a)
    d = o + hs
    ntr = be('I', b, d)[0]
    d += 4
    tracks = []
    for bone, mask in enumerate(masks):
        for bit in STREAM_ORDER:
            if not mask >> bit & 1:
                continue
            size, nk, ty, _ = be('4H', b, d)
            keys = []   # (frame, value, inTangent, outTangent)
            if ty == 1:
                for k in range(nk):
                    f = be('H', b, d + 8 + 16 * k)[0] & 0x7fff
                    v, ti, to = be('3f', b, d + 12 + 16 * k)
                    keys.append((f, v, ti, to))
            elif ty == 2:
                mn, rg = be('2f', b, d + 8)
                raw = [be('2H', b, d + 16 + 4 * k) for k in range(nk)]
                lo, sp = _span([r[1] for r in raw])
                keys = [(r[0] & 0x7fff, mn + rg * (r[1] - lo) / sp, None, None) for r in raw]
            elif ty == 3:
                fl = be('6f', b, d + 8)
                raw = [be('4H', b, d + 32 + 8 * k) for k in range(nk)]
                ch = []
                for c in range(3):
                    lo, sp = _span([r[c + 1] for r in raw])
                    ch.append([fl[2 * c] + fl[2 * c + 1] * (r[c + 1] - lo) / sp for r in raw])
                keys = [(raw[k][0] & 0x7fff, ch[0][k], ch[1][k], ch[2][k]) for k in range(nk)]
            else:
                return None
            tracks.append((bone, bit, keys))
            d += size
    if len(tracks) != ntr:
        return None
    return dict(frames=frames, bones=nb, tracks=tracks)


def sample(keys, f):
    if not keys:
        return None
    if f <= keys[0][0] or len(keys) == 1:
        return keys[0][1]
    for a, c in zip(keys, keys[1:]):
        if f <= c[0]:
            span = c[0] - a[0]
            if span <= 0:
                return c[1]
            t = (f - a[0]) / span
            if a[3] is None or c[2] is None:
                return a[1] + (c[1] - a[1]) * t
            t2, t3 = t * t, t * t * t
            return ((2 * t3 - 3 * t2 + 1) * a[1] + (t3 - 2 * t2 + t) * span * a[3]
                    + (-2 * t3 + 3 * t2) * c[1] + (t3 - t2) * span * c[2])
    return keys[-1][1]


def euler_quat(x, y, z):
    """Rotation X, then Y, then Z (R = Rz Ry Rx), as glTF x, y, z, w."""
    cx, sx = math.cos(x / 2), math.sin(x / 2)
    cy, sy = math.cos(y / 2), math.sin(y / 2)
    cz, sz = math.cos(z / 2), math.sin(z / 2)
    return (sx * cy * cz - cx * sy * sz,
            cx * sy * cz + sx * cy * sz,
            cx * cy * sz - sx * sy * cz,
            cx * cy * cz + sx * sy * sz)


def bake(mot, skel):
    """Per-bone per-frame (translation, rotation, scale) lists."""
    nf = max(1, int(round(mot['frames'])))
    nb = len(skel['parent'])
    ch = {}
    for bone, bit, keys in mot['tracks']:
        ch[(bone, bit)] = keys
    out = []
    for bone in range(nb):
        T, R, S = [], [], []
        animated = any((bone, k) in ch for k in range(9))
        if not animated:
            out.append(None)
            continue
        prevq = None
        for f in range(nf + 1):
            v = [sample(ch.get((bone, k)), f) for k in range(9)]
            s = tuple(1. if v[k] is None else v[k] for k in range(3))
            r = tuple(0. if v[k] is None else v[k] for k in range(3, 6))
            t = tuple(skel['offset'][bone][k - 6] if v[k] is None else v[k] for k in range(6, 9))
            q = euler_quat(*r)
            if prevq and sum(a * c for a, c in zip(q, prevq)) < 0:
                q = tuple(-a for a in q)
            prevq = q
            T.append(t); R.append(q); S.append(s)
        out.append((T, R, S))
    return nf, out


def find_mots(paths):
    """(name, mot) for every MOT inside the given files (bare, or in a PAC)."""
    out = []
    for p in paths:
        with open(p, 'rb') as f:
            b = f.read()
        if b[4:8] == b'MOT\0':
            offs = [(0, None)]
        elif b[:4] == b'PAC\0':
            cnt = be('I', b, 4)[0]
            offs = [(be('I', b, 8 + 4 * i)[0], i) for i in range(cnt)]
        else:
            continue
        for o, i in offs:
            if o + 8 > len(b) or b[o + 4:o + 8] != b'MOT\0':
                continue
            m = parse_mot(b, o)
            if m:
                out.append((p, i, m))
    return out


# ------------------------------------------------------------------ glTF

class GLB:
    def __init__(self):
        self.bin = bytearray()
        self.g = dict(asset=dict(version="2.0", generator="dmc-model-extractor dmc3anim.py"),
                      scene=0, scenes=[dict(nodes=[])], nodes=[], meshes=[], skins=[],
                      accessors=[], bufferViews=[], buffers=[], animations=[],
                      materials=[], textures=[], images=[], samplers=[])

    def view(self, data, target=None):
        while len(self.bin) % 4:
            self.bin.append(0)
        v = dict(buffer=0, byteOffset=len(self.bin), byteLength=len(data))
        if target:
            v['target'] = target
        self.bin += data
        self.g['bufferViews'].append(v)
        return len(self.g['bufferViews']) - 1

    def acc(self, rows, ctype, typ, target=None, minmax=False):
        fmt = {5126: 'f', 5123: 'H', 5125: 'I', 5121: 'B'}[ctype]
        n = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}[typ]
        flat = []
        for r in rows:
            if n == 1:
                flat.append(r)
            else:
                flat.extend(r)
        data = struct.pack('<%d%s' % (len(flat), fmt), *flat)
        a = dict(bufferView=self.view(data, target), componentType=ctype,
                 count=len(rows), type=typ)
        if minmax:
            cols = [[r] if n == 1 else list(r) for r in rows]
            a['min'] = [min(c[k] for c in cols) for k in range(n)]
            a['max'] = [max(c[k] for c in cols) for k in range(n)]
        self.g['accessors'].append(a)
        return len(self.g['accessors']) - 1

    def save(self, path):
        g = {k: v for k, v in self.g.items() if v != []}
        g['buffers'] = [dict(byteLength=len(self.bin))]
        js = json.dumps(g, separators=(',', ':')).encode()
        js += b' ' * (-len(js) % 4)
        while len(self.bin) % 4:
            self.bin.append(0)
        total = 12 + 8 + len(js) + 8 + len(self.bin)
        with open(path, 'wb') as f:
            f.write(struct.pack('<III', 0x46546C67, 2, total))
            f.write(struct.pack('<II', len(js), 0x4E4F534A) + js)
            f.write(struct.pack('<II', len(self.bin), 0x004E4942) + bytes(self.bin))


def png_bytes(w, h, rgba):
    import zlib
    raw = b''.join(b'\x00' + bytes(rgba[y * w * 4:(y + 1) * w * 4]) for y in range(h))

    def chunk(tag, data):
        c = tag + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 6)) + chunk(b'IEND', b''))


def write_glb(path, name, skel, meshes, images, motions):
    G = GLB()
    g = G.g
    nb = len(skel['parent'])
    # bones
    for i in range(nb):
        g['nodes'].append(dict(name="bone%02d" % i, translation=list(skel['offset'][i])))
    for i in range(nb):
        kids = [c for c in range(nb) if skel['parent'][c] == i]
        if kids:
            g['nodes'][i]['children'] = kids
    roots = [i for i in range(nb) if skel['parent'][i] < 0]
    ibm = []
    for i in range(nb):
        x, y, z = skel['world'][i]
        ibm.append((1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, -x, -y, -z, 1))
    g['skins'].append(dict(joints=list(range(nb)), skeleton=roots[0],
                           inverseBindMatrices=G.acc(ibm, 5126, 'MAT4')))
    # materials, one per texture used. `images` maps a mesh's 'mat' key (its
    # texture slot, or (container, slot) where a file holds several sets) to
    # (w, h, rgba); meshes without a match get a plain material.
    mat = {}
    if images:
        g['samplers'].append(dict(wrapS=10497, wrapT=10497))
    for key in sorted({m.get('mat', m['tex']) for m in meshes}, key=str):
        label = "tex%d" % key if isinstance(key, int) else "s%02d_tex%d" % key
        md = dict(name=label, doubleSided=True,
                  pbrMetallicRoughness=dict(metallicFactor=0., roughnessFactor=1.))
        if key in images:
            w, h, px = images[key]
            bv = G.view(png_bytes(w, h, px))
            g['images'].append(dict(bufferView=bv, mimeType="image/png", name="%s_%s" % (name, label)))
            g['textures'].append(dict(source=len(g['images']) - 1, sampler=0))
            md['pbrMetallicRoughness']['baseColorTexture'] = dict(index=len(g['textures']) - 1)
            md['alphaMode'] = 'MASK'
            md['alphaCutoff'] = 0.5
        g['materials'].append(md)
        mat[key] = len(g['materials']) - 1
    # one mesh, one primitive per source mesh
    prims = []
    for m in meshes:
        used = sorted({i for t in m['tris'] for i in t})
        if not used:
            continue
        remap = {v: k for k, v in enumerate(used)}
        nrm = []
        for i in used:
            n = m['nrm'][i]
            l = math.sqrt(sum(c * c for c in n)) or 1.
            nrm.append(tuple(c / l for c in n))
        j = [tuple(min(x, nb - 1) for x in m['joints'][i]) for i in used]
        prims.append(dict(
            attributes=dict(
                POSITION=G.acc([m['pos'][i] for i in used], 5126, 'VEC3', 34962, True),
                NORMAL=G.acc(nrm, 5126, 'VEC3', 34962),
                TEXCOORD_0=G.acc([m['uv'][i] for i in used], 5126, 'VEC2', 34962),
                JOINTS_0=G.acc(j, 5121, 'VEC4', 34962),
                WEIGHTS_0=G.acc([m['weights'][i] for i in used], 5126, 'VEC4', 34962)),
            indices=G.acc([remap[i] for t in m['tris'] for i in t], 5125, 'SCALAR', 34963),
            material=mat[m.get('mat', m['tex'])]))
    g['meshes'].append(dict(name=name, primitives=prims))
    g['nodes'].append(dict(name=name, mesh=0, skin=0))
    mesh_node = len(g['nodes']) - 1
    arm = dict(name=name + "_skeleton", children=roots)
    g['nodes'].append(arm)
    g['scenes'][0]['nodes'] = [len(g['nodes']) - 1, mesh_node]
    # animations
    for aname, mot in motions:
        nf, baked = bake(mot, skel)
        times = G.acc([f / FPS for f in range(nf + 1)], 5126, 'SCALAR', None, True)
        samplers, channels = [], []
        for bone, data in enumerate(baked):
            if data is None:
                continue
            for prop, rows, typ in (('translation', data[0], 'VEC3'),
                                    ('rotation', data[1], 'VEC4'),
                                    ('scale', data[2], 'VEC3')):
                if prop == 'scale' and all(r == (1., 1., 1.) for r in rows):
                    continue
                samplers.append(dict(input=times, output=G.acc(rows, 5126, typ),
                                     interpolation='LINEAR'))
                channels.append(dict(sampler=len(samplers) - 1,
                                     target=dict(node=bone, path=prop)))
        if channels:
            g['animations'].append(dict(name=aname, samplers=samplers, channels=channels))
    G.save(path)
    return len(g['animations'])


# ------------------------------------------------------------------ driver

def model_dirs(unpacked):
    return sorted(d for d in glob.glob(os.path.join(unpacked, '*', '*_PAC')) if os.path.isdir(d))


def convert(unpacked, afs, outdir, pattern='*'):
    os.makedirs(outdir, exist_ok=True)
    total = 0
    for d in model_dirs(unpacked):
        pac = os.path.basename(d)[:-4]            # PL000
        if not glob.fnmatch.fnmatch(pac, pattern):
            continue
        cat = os.path.basename(os.path.dirname(d))
        mots = find_mots(sorted(glob.glob(os.path.join(d, '**', '*.bin'), recursive=True)))
        ext = sorted(glob.glob(os.path.join(afs, pac + '_??_*.PAC')),
                     key=lambda p: [int(x) if x.isdigit() else x
                                    for x in os.path.basename(p)[:-4].split('_')])
        mots += find_mots(ext)
        if not mots:
            continue
        cache = {}
        models = []
        for mp in sorted(glob.glob(os.path.join(d, '*.mod'))):
            with open(mp, 'rb') as f:
                b = f.read()
            skel = parse_skeleton(b)
            if skel and len(skel['parent']) >= 2:
                models.append((mp, b, skel))
        # Some bodies carry one bone more than their motions drive (an
        # attachment at the end of the list). So a model also takes the
        # motions one bone smaller when no model here has that size, or when
        # nothing matches it exactly.
        counts = {len(s['parent']) for _, _, s in models}
        for mp, b, skel in models:
            n = len(skel['parent'])
            mine = [(p, i, m) for p, i, m in mots if m['bones'] == n]
            if not mine or n - 1 not in counts:
                mine += [(p, i, m) for p, i, m in mots if m['bones'] == n - 1]
            if not mine:
                continue
            meshes = parse_meshes(b)
            if not meshes:
                continue
            name = "%s_%s" % (os.path.basename(d), os.path.splitext(os.path.basename(mp))[0])
            images = dict(enumerate(modbe2.textures_for(mp, unpacked, cache)))
            motions = []
            for p, i, m in mine:
                rel = os.path.relpath(p, d) if p.startswith(d) else os.path.basename(p)
                tag = os.path.splitext(rel)[0].replace(os.sep, '_').replace('.', '_')
                motions.append(("%s_%02d" % (tag, i) if i is not None else tag, m))
            os.makedirs(os.path.join(outdir, cat), exist_ok=True)
            n = write_glb(os.path.join(outdir, cat, name + '.glb'), name, skel, meshes, images, motions)
            total += 1
            print("OK   %-28s bones=%2d meshes=%3d anims=%4d" % (name, len(skel['parent']), len(meshes), n))
    return total


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join("build", "unpacked")
    afs = sys.argv[2] if len(sys.argv) > 2 else os.path.join("build", "isoextract", "PS3_GAME", "USRDIR", "GDATA.AFS")
    out = sys.argv[3] if len(sys.argv) > 3 else os.path.join("out", "DMC3_animated")
    pat = sys.argv[4] if len(sys.argv) > 4 else "*"
    print("\nGLB files written:", convert(src, afs, out, pat))
