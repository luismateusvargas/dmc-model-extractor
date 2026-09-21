"""DMC1: skinned models with their animations, as glTF binary (.glb).

A DMC1 model file is a big-endian list of sections, the same bare offset list
dmc12anim reads. Player bodies (pl00, pl05) start it at 0; the Devil Trigger
bodies (pl01, pl03, pl06) and every enemy (.emd) put a 0x800-byte texture
directory first and the section list at 0x800, with offsets from there and 0
for an empty section. Section 0 is the geometry, skeleton included (see
dmc12anim.py). The skeleton's second table, unnamed there, is one flag byte per
bone that marks the IK chains:

    root flag (3, 4, 5, 6, 0x11, 0x12, ...) then two bones flagged 1
        a two-segment chain: root -> middle -> end, legs mostly
    7 / 8 / 0x0f  other bones whose second channel is not a scale (see below)

Motion bank (players section 6 and 7, enemies section 3 and 5):
    u32 count | u32 0 | count x (u32 A, u32 B), offsets from the bank start;
    B is an event table this reader ignores.
    motion at A:
        u16 frames | u8 channelCount - 1 | u8 ?
        (channelCount - 2) channel ids, padded to 4
        channelCount x u32 channel offset from A; an offset >= B - A is empty
    The first two channels have no id: channel 0 is a rotation that is not
    applied to the body (it does not line up with the IK targets when used as
    one) and channel 1 is root motion, a translation added to bone 0. Every
    other id is bone | 0x80 * second, where the first channel of a bone is its
    Euler rotation (X, then Y, then Z, radians, as in DMC2/3) and the second is
        bone 0          translation
        IK root         knee hinge axis, in the root's parent space
        IK end          target position, in model space
        flag 8          translation
        any other bone  scale
    channel = x, y and z subtracks, each: u16 n | n x u16 frame | pad to 4 |
              n x f32 (value, inTangent, outTangent); Hermite as in DMC3.

IK: the end bone's rotation channel is its orientation in model space. The
target is where the end bone sits, except on chains whose end has a child
(Dante's ankle -> toe), where it is where that child sits; the reader tells
the two apart per chain by which one keeps the hinge axis perpendicular to
root -> end. The middle joint is placed by the law of cosines in the plane
normal to the hinge axis, on the side given by the root flag (odd and even
flags bend opposite ways, which is how left and right legs mirror), and
unreachable targets straighten the chain towards them.

Dante's DT bodies carry no motions of their own. They share his first 28
bones, so they are given pl00's bank; so are the enemy files built on his rig
(Trish em24, his doubles em20/21/28/29), on top of their own one or two. pl00 also holds a 13-bone coat skeleton
driven by the second bank.

    python dmc1anim.py <extract/DMC1/data dir> <output dir> [<pattern>]
"""
import struct
import os
import sys
import glob
import math

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dmc3anim
import dmc12anim
from dmc3anim import sample

E = '>'
SCALE_FLAGS = ()           # flags whose second channel is scale: everything else
MOVE_FLAGS = (8,)          # flags whose second channel is a translation


# ------------------------------------------------------------------ container

def sections(b):
    """[(start, end) or None] per section, in file order."""
    for base in (0, 0x800):
        if base + 8 > len(b):
            continue
        n = struct.unpack_from(E + 'I', b, base)[0]
        if not 0 < n < 64:
            continue
        offs = struct.unpack_from(E + '%dI' % n, b, base + 4)
        nz = sorted(o for o in offs if o)
        if not nz or nz[0] < 4 + 4 * n or base + nz[-1] > len(b):
            continue
        if any(x >= y for x, y in zip(nz, nz[1:])):
            continue
        out = []
        for o in offs:
            if not o:
                out.append(None)
                continue
            later = [x for x in nz if x > o]
            out.append((base + o, base + later[0] if later else len(b)))
        return out
    return []


def is_bank(b, s, e):
    if s + 16 > e:
        return 0
    n, z = struct.unpack_from(E + '2I', b, s)
    if not (0 < n < 2000 and z == 0) or s + 8 + 8 * n > e:
        return 0
    pairs = struct.unpack_from(E + '%dI' % (2 * n), b, s + 8)
    if not all(0 < a < e - s and 0 < c < e - s for a, c in zip(pairs[::2], pairs[1::2])):
        return 0
    return n


def flags_of(b, s):
    so = struct.unpack_from(E + 'I', b, s + 4)[0]
    sk = s + so
    _, fo, _, cnt = struct.unpack_from(E + '4I', b, sk)
    return list(b[sk + fo:sk + fo + cnt])


# ------------------------------------------------------------------ motions

def _channel(b, q):
    subs = []
    for _ in range(3):
        n = struct.unpack_from(E + 'H', b, q)[0]
        q += 2
        frames = struct.unpack_from(E + '%dH' % n, b, q)
        q = (q + 2 * n + 3) // 4 * 4
        keys = []
        for i, f in enumerate(frames):
            v, ti, to = struct.unpack_from(E + '3f', b, q + 12 * i)
            keys.append((f, v, ti, to))
        q += 12 * n
        subs.append(keys)
    return subs


def parse_motion(b, A, B):
    frames, last = struct.unpack_from(E + 'HB', b, A)
    count = last + 1
    ids = list(b[A + 4:A + 4 + count - 2])
    p = (A + 4 + count - 2 + 3) // 4 * 4
    offs = struct.unpack_from(E + '%dI' % count, b, p)
    ch = {}
    for i, o in enumerate(offs):
        if o >= B - A:
            continue
        key = 'E' if i == 0 else 'R' if i == 1 else ids[i - 2]
        if key != 0xff:              # a trailing id some motions carry; no bone
            ch[key] = _channel(b, A + o)
    return dict(frames=frames, ch=ch)


def banks(b, secs):
    """Every motion bank in the file, as lists of parsed motions."""
    out = []
    for si, se in enumerate(secs):
        if not se or si == 0:
            continue
        s, e = se
        n = is_bank(b, s, e)
        if not n:
            continue
        pairs = struct.unpack_from(E + '%dI' % (2 * n), b, s + 8)
        mots = []
        for k in range(n):
            try:
                mots.append(parse_motion(b, s + pairs[2 * k], s + pairs[2 * k + 1]))
            except struct.error:
                mots.append(None)
        out.append((si, mots))
    return out


def ev(ch, key, f, default):
    subs = ch.get(key)
    if subs is None:
        return None
    out = []
    for i, keys in enumerate(subs):
        v = sample(keys, f)
        out.append(default[i] if v is None else v)
    return np.array(out)


def rot(x, y, z):
    cx, sx, cy, sy, cz, sz = math.cos(x), math.sin(x), math.cos(y), math.sin(y), math.cos(z), math.sin(z)
    return (np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
            @ np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
            @ np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]]))


def mat_quat(m):
    """3x3 rotation matrix -> glTF (x, y, z, w)."""
    t = m[0, 0] + m[1, 1] + m[2, 2]
    if t > 0:
        s = math.sqrt(t + 1.) * 2
        return ((m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s, .25 * s)
    i = int(np.argmax([m[0, 0], m[1, 1], m[2, 2]]))
    j, k = (i + 1) % 3, (i + 2) % 3
    s = math.sqrt(1. + m[i, i] - m[j, j] - m[k, k]) * 2
    q = [0., 0., 0., 0.]
    q[i] = .25 * s
    q[j] = (m[j, i] + m[i, j]) / s
    q[k] = (m[k, i] + m[i, k]) / s
    q[3] = (m[k, j] - m[j, k]) / s
    return tuple(q)


def _basis(u, v):
    u = u / np.linalg.norm(u)
    v = v - u * (u @ v)
    nv = np.linalg.norm(v)
    if nv < 1e-9:
        v = np.array([1., 0, 0]) if abs(u[0]) < .9 else np.array([0, 1., 0])
        v = v - u * (u @ v)
        nv = np.linalg.norm(v)
    v = v / nv
    return np.column_stack([u, v, np.cross(u, v)])


# ------------------------------------------------------------------ IK

def chains(skel, flags):
    """[(root, mid, end, flag)] for every two-segment IK chain."""
    par = skel['parent']
    out = []
    for r, fl in enumerate(flags):
        if fl in (0, 1, 7, 8, 0x0f) or r + 2 >= len(flags):
            continue
        m, e = r + 1, r + 2
        if flags[m] == 1 and flags[e] == 1 and par[m] == r and par[e] == m:
            out.append((r, m, e, fl))
    return out


class Poser:
    def __init__(self, skel, flags):
        self.skel = skel
        self.flags = flags
        self.nb = len(skel['parent'])
        self.off = [np.array(o, dtype=float) for o in skel['offset']]
        self.chains = chains(skel, flags)
        self.ik_root = {c[0]: c for c in self.chains}
        self.ik_mid = {c[1] for c in self.chains}
        self.ik_end = {c[2]: c for c in self.chains}
        # the child whose position the target gives, where there is one
        self.tip = {}
        self.hinge_bind = {}
        for r, m, e, fl in self.chains:
            kids = [c for c in range(self.nb) if self.skel['parent'][c] == e]
            self.tip[e] = kids[0] if kids else None

    def calibrate(self, mots):
        """Per chain: does the target mean the end joint or its child? And the
        hinge axis in bind space, averaged over the bank."""
        for r, m, e, fl in self.chains:
            votes = {False: [], True: []}
            hsum = np.zeros(3)
            for mo in mots:
                if not mo or (0x80 | e) not in mo['ch'] or (0x80 | r) not in mo['ch']:
                    continue
                for f in range(0, mo['frames'] + 1, max(1, mo['frames'] // 6)):
                    P, W = self.pose(mo, f, solve=False)
                    t = ev(mo['ch'], 0x80 | e, f, (0, 0, 0))
                    h = W[self.skel['parent'][r]] @ ev(mo['ch'], 0x80 | r, f, (0, 0, 0))
                    hsum += h / (np.linalg.norm(h) or 1)
                    hn = h / (np.linalg.norm(h) or 1)
                    for use_tip in (False, True):
                        if use_tip and self.tip[e] is None:
                            continue
                        p = t
                        if use_tip:
                            re = ev(mo['ch'], e, f, (0, 0, 0))
                            p = t - (rot(*re) if re is not None else np.eye(3)) @ self.off[self.tip[e]]
                        a = p - P[r]
                        la = np.linalg.norm(a)
                        if la > 1e-6:
                            votes[use_tip].append(abs(a @ hn) / la)
            if not (votes[True] and np.median(votes[True]) < np.median(votes[False] or [1])):
                self.tip[e] = None
            # bind hinge: the averaged axis, made perpendicular to the bind chain
            u0 = self.off[m] / (np.linalg.norm(self.off[m]) or 1)
            h = hsum if np.linalg.norm(hsum) > 1e-6 else np.array([1., 0, 0])
            self.hinge_bind[r] = _basis(u0, h)

    def pose(self, mo, f, solve=True):
        """World positions and rotations of every bone at frame f."""
        ch = mo['ch']
        nb, par = self.nb, self.skel['parent']
        P, W, S = [None] * nb, [None] * nb, [np.ones(3)] * nb
        T = [self.off[i] for i in range(nb)]
        root = ev(ch, 'R', f, (0, 0, 0))
        solved = set()
        for i in range(nb):
            r = ev(ch, i, f, (0, 0, 0))
            R = rot(*r) if r is not None else np.eye(3)
            second = ev(ch, 0x80 | i, f, (0, 0, 0))
            if second is not None:
                if i == 0 or self.flags[i] in MOVE_FLAGS:
                    T[i] = second
                elif i not in self.ik_root and i not in self.ik_end:
                    S[i] = ev(ch, 0x80 | i, f, (1, 1, 1))
            p = par[i]
            if p < 0:
                P[i] = T[i] + (root if root is not None else 0)
                W[i] = R
            else:
                P[i] = P[p] + W[p] @ T[i]
                if i in solved:
                    pass
                elif solve and i in self.ik_end and (0x80 | i) in ch:
                    W[i] = R if r is not None else W[p]
                else:
                    W[i] = W[p] @ R
            if solve and i in self.ik_root and (0x80 | self.ik_root[i][2]) in ch:
                self._solve(mo, f, self.ik_root[i], P, W)
                solved.add(self.ik_root[i][1])
        return (P, W, S) if solve else (P, W)

    def _solve(self, mo, f, chain, P, W):
        r, m, e, fl = chain
        ch = mo['ch']
        par = self.skel['parent']
        t = ev(ch, 0x80 | e, f, (0, 0, 0))
        re = ev(ch, e, f, (0, 0, 0))
        We = rot(*re) if re is not None else None
        if self.tip.get(e) is not None and We is not None:
            t = t - We @ self.off[self.tip[e]]
        h = ev(ch, 0x80 | r, f, (0, 0, 0))
        n = W[par[r]] @ h if h is not None else W[par[r]] @ self.hinge_bind[r][:, 1]
        L1, L2 = np.linalg.norm(self.off[m]), np.linalg.norm(self.off[e])
        a = t - P[r]
        d = np.linalg.norm(a)
        if d < 1e-6:
            return
        ad = a / d
        d = min(max(d, abs(L1 - L2) + 1e-4), L1 + L2 - 1e-4)
        x = (L1 * L1 - L2 * L2 + d * d) / (2 * d)
        hgt = math.sqrt(max(L1 * L1 - x * x, 0.))
        side = np.cross(n, ad) if fl & 1 else np.cross(ad, n)
        ns = np.linalg.norm(side)
        side = side / ns if ns > 1e-9 else np.zeros(3)
        knee = P[r] + ad * x + side * hgt
        end = P[r] + ad * d
        B0 = self.hinge_bind[r]
        W[r] = _basis(knee - P[r], n) @ _basis(self.off[m], B0[:, 1]).T
        W[m] = _basis(end - knee, n) @ _basis(self.off[e], B0[:, 1]).T
        P[m] = knee
        # the end bone is placed by the caller from W[m]; its rotation is its own
        if We is not None:
            W[e] = We

    def bake(self, mo):
        """(nf, [(T, R, S) per bone]) in the layout dmc3anim.write_glb wants."""
        nf = max(1, int(mo['frames']))
        par = self.skel['parent']
        rows = [([], [], []) for _ in range(self.nb)]
        prev = [None] * self.nb
        for f in range(nf + 1):
            P, W, S = self.pose(mo, f)
            for i in range(self.nb):
                p = par[i]
                if p < 0:
                    t, R = P[i], W[i]
                else:
                    t = W[p].T @ (P[i] - P[p])
                    R = W[p].T @ W[i]
                q = mat_quat(R)
                if prev[i] and sum(x * y for x, y in zip(q, prev[i])) < 0:
                    q = tuple(-x for x in q)
                prev[i] = q
                rows[i][0].append(tuple(float(x) for x in t))
                rows[i][1].append(tuple(float(x) for x in q))
                rows[i][2].append(tuple(float(x) for x in S[i]))
        return nf, rows


# ------------------------------------------------------------------ driver

def load(path):
    with open(path, 'rb') as fh:
        b = fh.read()
    secs = sections(b)
    models = []
    for si, se in enumerate(secs):
        if not se:
            continue
        m = dmc12anim.parse_section(b, se[0], se[1] - se[0], E, 8)
        if m:
            m['flags'] = flags_of(b, se[0])
            m['section'] = si
            models.append(m)
    return b, models, banks(b, secs)


def convert(data_dir, outdir, pattern='*'):
    os.makedirs(outdir, exist_ok=True)
    files = sorted(glob.glob(os.path.join(data_dir, 'pld', 'pl*.pld'))) + \
        sorted(glob.glob(os.path.join(data_dir, 'emd', '*.emd')))
    shared, p0_skel = {}, None
    p0 = os.path.join(data_dir, 'pld', 'pl00.pld')
    if os.path.exists(p0):
        _, p0_models, shared_banks = load(p0)
        shared = dict(shared_banks)
        p0_skel = p0_models[0]
    total = 0
    for path in files:
        stem = os.path.splitext(os.path.basename(path))[0]
        if not glob.fnmatch.fnmatch(stem, pattern):
            continue
        b, models, bks = load(path)
        if not models:
            continue
        if stem.startswith('pl') and not bks and 6 in shared:
            bks = [(6, shared[6])]
        elif not stem.startswith('pl') and 6 in shared and models and _dante_like(models[0], p0_skel):
            # humans built on Dante's rig (Trish em24, his doubles em20/21/28/29)
            # carry only a pose or two; give them his moveset as well
            bks = bks + [('pl00_6', shared[6])]
        for mi, m in enumerate(models):
            n = len(m['skel']['parent'])
            if n < 2:
                continue
            mine = []
            for si, mots in bks:
                used = [(k, mo) for k, mo in enumerate(mots) if mo and _fits(mo, n)]
                # players: bank 6 is the body's, bank 7 the coat's; enemies
                # keep both of theirs (3 and 5) on the body
                body = si != 7
                if (mi == 0) == body:
                    tag = si if isinstance(si, str) else "bank%d" % si
                    mine += [("%s_%03d" % (tag, k), mo) for k, mo in used]
            if not mine:
                continue
            poser = Poser(m['skel'], m['flags'])
            poser.calibrate([mo for _, mo in mine])
            motions = [(name, dict(baked=poser.bake(mo))) for name, mo in mine]
            name = stem if len(models) == 1 else "%s_s%02d" % (stem, m['section'])
            images = dmc12anim.textures(b, E, m['meshes'])
            cnt = dmc3anim.write_glb(os.path.join(outdir, name + '.glb'), name, m['skel'],
                                     m['meshes'], images, motions)
            total += 1
            print("OK   %-14s bones=%2d meshes=%3d ik=%d anims=%4d" % (
                name, n, len(m['meshes']), len(poser.chains), cnt))
    return total


def _dante_like(m, dante):
    """Same first 28 bones and IK flags as Dante's body."""
    if dante is None:
        return False
    a, c = m['skel']['parent'], dante['skel']['parent']
    return len(a) >= 28 and a[:28] == c[:28] and m['flags'][:28] == dante['flags'][:28]


def _fits(mo, n):
    """A motion fits a skeleton when every bone it drives exists there."""
    ids = [k & 0x7f for k in mo['ch'] if isinstance(k, int) and k != 0xff]
    return not ids or max(ids) < n


if __name__ == "__main__":
    src, out = sys.argv[1], sys.argv[2]
    pat = sys.argv[3] if len(sys.argv) > 3 else '*'
    print("\nGLB files written:", convert(src, out, pat))
