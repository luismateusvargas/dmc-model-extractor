"""DMC1 / DMC2: skinned models with their animations, as glTF binary (.glb).

Both games keep the skeleton inside the model's geometry section, in the same
layout DMC3 later inherited. DMC2 is little-endian, DMC1 big-endian.

Geometry section (offsets relative to its start):
    u8 objectCount | u8 boneCount | u8 texCount | u8 ? | (u32 ? - DMC2 only)
    u32 skeleton offset | object records, stride 16 (see dmcmesh.py)
Skeleton:
    u32 hierarchy off | u32 ? off | u32 transforms off | u32 boneCount
    hierarchy[i]  u8 parent of bone i, 0xff for the root
    transforms    boneCount x 16 B: f32 x, y, z (offset from parent), f32 length
Meshes are in model space, already in the bind pose, and skinned exactly like
DMC3's: bone bytes 1..3 of each vertex are bone numbers times 4 and the u16
beside the strip flag holds three 5-bit weights (see dmc3anim.py).

DMC2 motions live in the model's companion `.dat` (em00_gm.mdl -> em00_gm.dat),
a MOMO file whose first section is the motion bank:
    u32 offset table, as many entries as fit before the first motion; a 0 or
        an offset past the section ends it
    motion      u32 offset per bone (the first one also gives the bone count)
    bone block  u16 channel mask (bits 0-2 scale, 3-5 rotation, 6-8 translation)
                u16 offset per set bit, from the block start
                (a bone with no channels is a bare 0)
    channel     keys of s16 frame, value, inTangent, outTangent, ended by any
                frame with the top bit set
    Rotations are 1/4096 radian, translations 1/16 unit, scale 1/4096.
    Tangents are per frame, and the curve is cubic Hermite as in DMC3.

Cutscene motions (edm_NNN_4.bin) use the same bone blocks, except that a
bone whose mask has bit 15 set stores float keys: f32 frame, value, inTangent,
outTangent, unscaled, ended by 0xffffffff. See convert_dmc2_events.

    python dmc12anim.py dmc2 <extract/DMC2/data dir> <output dir> [<pattern>]
    python dmc12anim.py dmc2events <dir with edm_*_3/4.bin> <output dir> [<event>]
"""
import struct
import os
import sys
import glob
import math

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dmctex
import dmc3anim
import dmcattach
from dmcmesh import get_tris

ROT = 1 / 4096.
MOVE = 1 / 16.
SCALE = 1 / 4096.


# ------------------------------------------------------------------ model

def sections(b, e):
    """(offset, size) of every section. DMC2 is MOMO; DMC1 a bare offset list."""
    if b[:4] == b'MOMO':
        n = struct.unpack_from('<I', b, 4)[0]
        return [struct.unpack_from('<2I', b, 8 + 8 * k) for k in range(n)]
    n = struct.unpack_from(e + 'I', b, 0)[0]
    if not 0 < n < 256:
        return []
    offs = list(struct.unpack_from(e + '%dI' % n, b, 4))
    ends = offs[1:] + [len(b)]
    return [(o, c - o) for o, c in zip(offs, ends)]


def parse_section(b, base, size, e, hsize):
    """The skeleton and skinned meshes of one geometry section, or None."""
    N = len(b)
    if base + hsize + 16 > N:
        return None
    oc, nb = b[base], b[base + 1]
    if not (0 < oc <= 64 and 0 < nb <= 128):
        return None
    so = struct.unpack_from(e + 'I', b, base + hsize - 4)[0]
    sk = base + so
    if not (0 < so < size) or sk + 16 > N:
        return None
    ho, _, to, cnt = struct.unpack_from(e + '4I', b, sk)
    if cnt != nb or b[sk + ho] != 0xff or sk + to + 16 * nb > N:
        return None
    parent = [-1 if b[sk + ho + i] == 0xff else b[sk + ho + i] for i in range(nb)]
    if any(p >= nb for p in parent):
        return None
    offs = [struct.unpack_from(e + '3f', b, sk + to + 16 * i) for i in range(nb)]
    world = [None] * nb
    for i in range(nb):
        chain, j = [], i
        while j >= 0 and len(chain) <= nb:
            chain.append(j)
            j = parent[j]
        world[i] = tuple(sum(offs[k][c] for k in chain) for c in range(3))
    skel = dict(parent=parent, offset=offs, world=world)

    meshes = []
    for oi in range(oc):
        r = base + hsize + 16 * oi
        mc = b[r]
        doff = struct.unpack_from(e + 'I', b, r + 4)[0]
        for mi in range(mc):
            d = base + doff + 32 * mi
            if d + 32 > N:
                break
            nv, tex = struct.unpack_from(e + 'HH', b, d)
            po, no, uo, bo, wo = (base + x for x in struct.unpack_from(e + '5I', b, d + 4))
            if not (2 < nv < 65535) or max(po, no) + 12 * nv > N or bo + 4 * nv > N \
                    or wo + 2 * nv > N or uo + 4 * nv > N:
                continue
            pos = [struct.unpack_from(e + '3f', b, po + 12 * k) for k in range(nv)]
            nrm = [struct.unpack_from(e + '3f', b, no + 12 * k) for k in range(nv)]
            uv = [(struct.unpack_from(e + 'h', b, uo + 4 * k)[0] / 4096.,
                   struct.unpack_from(e + 'h', b, uo + 4 * k + 2)[0] / 4096.) for k in range(nv)]
            words = [struct.unpack_from(e + 'H', b, wo + 2 * k)[0] for k in range(nv)]
            joints, weights = [], []
            for k in range(nv):
                bb = b[bo + 4 * k:bo + 4 * k + 4]
                wd = words[k] & 0x7fff
                ws = [wd & 31, (wd >> 5) & 31, (wd >> 10) & 31]
                js = [min(bb[1] >> 2, nb - 1), min(bb[2] >> 2, nb - 1), min(bb[3] >> 2, nb - 1), 0]
                if not sum(ws):
                    ws[0] = 31
                ws.append(0)
                t = float(sum(ws))
                joints.append(js)
                weights.append([x / t for x in ws])
            tris = get_tris(pos, nrm, [(x >> 15) & 1 for x in words], nv)
            if tris:
                meshes.append(dict(obj=oi, mesh=mi, tex=tex, po=po, pos=pos, nrm=nrm,
                                   uv=uv, joints=joints, weights=weights, tris=tris))
    if not meshes:
        return None
    return dict(skel=skel, meshes=meshes, base=base)


def parse_models(b, e):
    hsize = 12 if e == '<' else 8
    out = []
    for off, size in sections(b, e):
        m = parse_section(b, off, size, e, hsize)
        if m:
            out.append(m)
    return out


# ------------------------------------------------------------------ DMC2 motion

def dmc2_motions(b):
    """Every motion in a DMC2 .dat, as dmc3anim-style dicts."""
    if b[:4] != b'MOMO':
        return []
    sec, size = struct.unpack_from('<2I', b, 8)
    first = struct.unpack_from('<I', b, sec)[0]
    out = []
    for k in range(first // 4):
        mo = struct.unpack_from('<I', b, sec + 4 * k)[0]
        if not mo or mo >= size:
            break
        m = _dmc2_motion(b, sec + mo, sec + size)
        if m:
            out.append((k, m))
    return out


def _dmc2_motion(b, M, end):
    nb = struct.unpack_from('<I', b, M)[0] // 4
    if not 0 < nb <= 128:
        return None
    blocks = struct.unpack_from('<%dI' % nb, b, M)
    tracks, last = [], 0
    for bone, bo in enumerate(blocks):
        o = M + bo
        if o + 2 > end:
            return None
        mask = struct.unpack_from('<H', b, o)[0]
        # bit 15: float keys (cutscene motions), otherwise fixed point
        floats = mask & 0x8000
        mask &= 0x7fff
        bits = [k for k in range(9) if mask >> k & 1]
        if mask >> 9:
            return None
        co = struct.unpack_from('<%dH' % len(bits), b, o + 2)
        for bit, c in zip(bits, co):
            p, keys = o + c, []
            if floats:
                while p + 16 <= end:
                    f, v, ti, to = struct.unpack_from('<4f', b, p)
                    if struct.unpack_from('<I', b, p)[0] == 0xffffffff or not 0 <= f < 65536:
                        break
                    keys.append((int(round(f)), v, ti, to))
                    p += 16
            else:
                k = MOVE if bit >= 6 else ROT if bit >= 3 else SCALE
                while p + 8 <= end:
                    f, v, ti, to = struct.unpack_from('<Hhhh', b, p)
                    if f & 0x8000:
                        break
                    keys.append((f, v * k, ti * k, to * k))
                    p += 8
            if not keys:
                continue
            last = max(last, keys[-1][0])
            tracks.append((bone, bit, keys))
    return dict(frames=float(last), bones=nb, tracks=tracks)


def event_motions(b):
    """Cutscene motion file (edm_NNN_4.bin): every MOMO section is a bank of
    its own, usually holding one motion, some with an 8-byte header (u16 ?,
    u16 boneCount, u16 frames, u16 0xffff) between the table and the motion."""
    if b[:4] != b'MOMO':
        return []
    out = []
    for si, (sec, size) in enumerate(sections(b, '<')):
        if size < 8 or sec + size > len(b):
            continue
        first = struct.unpack_from('<I', b, sec)[0]
        if not 4 <= first < size or first % 4:
            continue
        for k in range(first // 4):
            mo = struct.unpack_from('<I', b, sec + 4 * k)[0]
            if not mo or mo >= size:
                break
            try:
                m = _dmc2_motion(b, sec + mo, sec + size)
            except struct.error:
                m = None
            if m and m['tracks']:
                out.append((si, k, m))
    return out


# ------------------------------------------------------------------ driver

def textures(b, e, meshes):
    """{(container, slot): (w, h, rgba)} for the meshes, setting each mesh's 'mat'."""
    sets = dmctex.pipeworks_sets(b) if e == '>' else dmctex.tim2_sets(b)
    got = {}
    for m, k in zip(meshes, dmctex.assign(sets, [(m['po'], m['tex']) for m in meshes])):
        if k is None:
            m['mat'] = m['tex']
            continue
        m['mat'] = (k, m['tex'])
        got[m['mat']] = sets[k][1][m['tex']]
    # a file with a single texture set keeps plain slot names
    if len({k for k, _ in got}) == 1:
        for m in meshes:
            if isinstance(m['mat'], tuple):
                m['mat'] = m['mat'][1]
        got = {s: v for (_, s), v in got.items()}
    return got


def _read_mdl(path):
    with open(path, 'rb') as f:
        b = f.read()
    if b[:4] != b'MOMO' and b'MOMO' in b[:16]:
        b = b[b.index(b'MOMO'):]
    return b


def _borrowed_dat(data_dir, mdl, models):
    """The motion bank of the model this one is a costume of: costumes
    (pl03..pl07) ship without a .dat and share the base character's skeleton,
    so pick the .dat whose model's main skeleton matches most closely."""
    if not models:
        return None
    mine = models[0]['skel']
    best = None
    family = os.path.basename(mdl)[:2]          # a player borrows from players
    for dat in sorted(glob.glob(os.path.join(data_dir, family + '*_gm.dat'))):
        other = dat[:-4] + '.mdl'
        if not os.path.exists(other) or os.path.samefile(other, mdl):
            continue
        om = parse_models(_read_mdl(other), '<')
        if not om or om[0]['skel']['parent'] != mine['parent']:
            continue
        diff = max(abs(a - c) for p, q in zip(mine['offset'], om[0]['skel']['offset'])
                   for a, c in zip(p, q))
        if best is None or diff < best[0]:
            best = (diff, dat)
    return best and best[1]


def convert_dmc2(data_dir, outdir, pattern='*'):
    os.makedirs(outdir, exist_ok=True)
    total = 0
    for mdl in sorted(glob.glob(os.path.join(data_dir, '*_gm.mdl'))):
        stem = os.path.basename(mdl)[:-4]
        if not glob.fnmatch.fnmatch(stem, pattern):
            continue
        b = _read_mdl(mdl)
        models = parse_models(b, '<')
        dat = mdl[:-4] + '.dat'
        if not os.path.exists(dat):
            dat = _borrowed_dat(data_dir, mdl, models)
            if not dat:
                continue
            print("     %s has no motions of its own; using %s" % (stem, os.path.basename(dat)))
        with open(dat, 'rb') as f:
            mots = dmc2_motions(f.read())
        for si, m in enumerate(models):
            n = len(m['skel']['parent'])
            mine = [("motion_%03d" % k, mo) for k, mo in mots if mo['bones'] == n]
            if not mine or n < 2:
                continue
            name = stem if len(models) == 1 else "%s_s%02d" % (stem, si)
            skel, meshes = m['skel'], m['meshes']
            # hair / coat sub-models that hang on this body (see dmcattach.py)
            spec = [x for x in dmcattach.DMC2.get(stem, {}).get(si, []) if x[0] < len(models)]
            parts = [(models[x[0]]['skel'], models[x[0]]['meshes'], None) + tuple(x[1:]) for x in spec]
            if parts:
                skel, meshes, rep = dmcattach.merge(skel, meshes, parts)
                print("     %s: attached %s" % (name, ', '.join(
                    's%02d on bone%02d' % (k[0], r[1]) for k, r in zip(spec, rep))))
            images = textures(b, '<', meshes)
            cnt = dmc3anim.write_glb(os.path.join(outdir, name + '.glb'), name, skel,
                                     meshes, images, mine)
            total += 1
            print("OK   %-20s bones=%2d meshes=%3d anims=%4d" % (name, n, len(meshes), cnt))
    return total


def _runs(items, key):
    """[(key, [items])] for each run of consecutive items sharing a key."""
    out = []
    for it in items:
        k = key(it)
        if out and out[-1][0] == k:
            out[-1][1].append(it)
        else:
            out.append((k, [it]))
    return out


def _model_key(m):
    s = m['skel']
    return (tuple(s['parent']), tuple(tuple(round(c, 1) for c in o) for o in s['offset']),
            sum(len(x['pos']) for x in m['meshes']))


def convert_dmc2_events(data_dir, outdir, pattern='*'):
    """Cutscene actors. An event NNN keeps its models in edm_NNN_3.bin and their
    motions in edm_NNN_4.bin, and lists the motions actor by actor in the order
    the models come: each run of same-sized motions belongs to the next run of
    same-sized models (two hands of one actor share theirs). The same actor
    appears in many events, so identical models are merged and carry every
    event's motions, named eNNN_SS (event, motion section)."""
    os.makedirs(outdir, exist_ok=True)
    actors = {}                       # model key -> [name, file bytes, model, motions]
    for p3 in sorted(glob.glob(os.path.join(data_dir, 'edm_*_3.bin'))):
        ev = os.path.basename(p3).split('_')[1]
        p4 = p3[:-6] + '_4.bin'
        if not glob.fnmatch.fnmatch(ev, pattern) or not os.path.exists(p4):
            continue
        b = _read_mdl(p3)
        with open(p4, 'rb') as f:
            mots = event_motions(f.read())
        models = parse_models(b, '<')
        mruns = _runs(mots, lambda x: x[2]['bones'])
        pos = 0
        for n, group in _runs(list(enumerate(models)), lambda x: len(x[1]['skel']['parent'])):
            while pos < len(mruns) and mruns[pos][0] != n:
                pos += 1
            if pos == len(mruns):
                break
            run = mruns[pos][1]
            pos += 1
            if n < 2:
                continue
            for mi, m in group:
                k = _model_key(m)
                if k not in actors:
                    actors[k] = ["edm_%s_s%02d" % (ev, mi), b, m, []]
                actors[k][3] += [("e%s_%03d" % (ev, si), mo) for si, _, mo in run]
    total = 0
    for name, b, m, motions in actors.values():
        images = textures(b, '<', m['meshes'])
        cnt = dmc3anim.write_glb(os.path.join(outdir, name + '.glb'), name, m['skel'],
                                 m['meshes'], images, motions)
        total += 1
        print("OK   %-20s bones=%2d meshes=%3d anims=%4d" % (
            name, len(m['skel']['parent']), len(m['meshes']), cnt))
    return total


if __name__ == "__main__":
    game, src, out = sys.argv[1], sys.argv[2], sys.argv[3]
    pat = sys.argv[4] if len(sys.argv) > 4 else '*'
    if game == 'dmc2':
        print("\nGLB files written:", convert_dmc2(src, out, pat))
    elif game == 'dmc2events':
        print("\nGLB files written:", convert_dmc2_events(src, out, pat))
