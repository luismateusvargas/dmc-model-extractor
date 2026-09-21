"""Hair, coats and scarves: the physics parts the games keep as separate models.

A DMC character's hair or coat tails are not in its body mesh. They are models
of their own with their own small skeleton (a cloth or hair chain the game
simulates), stored in the part's local space and hung on a body bone at run
time. The body's motions never drive them, so pairing motions by bone count
leaves them out and the character comes out bald or coatless.

This merges each part into its body, rigidly on the body bone it hangs from:
    DMC3  a second .mod in the same PAC (12.mod beside 01.mod; its cloth
          settings are the .clt text, 13.bin). Dante's and Vergil's coats,
          Lady's hair.
    DMC2  a sub-model of the same .mdl (pl00_gm s01 hair + s04 coat tails,
          Lucia s04 hair + s01 scarf, Trish s01 hair; the costumes alike).
The file does not say which bone a part hangs from, so every body bone is
tried and the one that seats the part closest onto the body's surface wins;
parts already in model space (Lucia's scarf) are tried as they are too.
Each part vertex is then skinned to the body the way its nearest body
vertices are (weight transfer), so a coat swings with the legs and hair turns
with the head; the cloth simulation itself is not reproduced.
"""
import copy

import numpy as np

# DMC3: PAC -> body .mod -> [(part .mod, body bone, meshes to keep or None)].
# Small parts (hair) fit badly - a 25-unit cap sits near the body anywhere -
# so the known ones name their bone: 03 chest, 04 neck, 05 head.
# Dante's coat model holds two whole coats on the same texture area; the
# first has the flared Devil Trigger collar, so only the plain one (mesh 5)
# is kept, and the strap/buckle pieces (meshes 1-4) with it are left out.
# Vergil's two coat meshes are the blue shell and its lining: both stay.
DMC3 = {
    'PL000': {'01': [('12', 4, [5])]},                   # Dante: coat
    'PL001': {'01': [('12', 4, None)]},                  # Vergil: coat + lining
    'PL021': {'01': [('12', 4, None)]},                  # Vergil (playable): coat + lining
    'PL002': {'01': [('12', 5, None)]},                  # Lady: hair
    'EM034': {'01': [('17', 5, None)], '32': [('34', 5, None)]},   # Lady (boss): hair
    'EM035': {'01': [('02', 5, None), ('03', 4, None)], '51': [('52', 4, None)]},   # Vergil (boss)
}
# DMC2: .mdl stem -> body sub-model -> [(part sub-model, body bone or None
# to fit, bone it follows or None for the same)]. Hair is placed by fitting
# but follows the head (bone04), whichever bone the fit seated it on.
_DANTE2 = {0: [(1, 4, None), (4, None, None)]}      # hair (on the head), coat tails
_LUCIA = {0: [(1, None, None), (4, None, 4)]}       # scarf, hair
DMC2 = {
    'pl00_gm': _DANTE2, 'pl04_gm': _DANTE2, 'pl06_gm': _DANTE2,
    'pl01_gm': _LUCIA, 'pl03_gm': _LUCIA, 'pl05_gm': _LUCIA, 'pl07_gm': _LUCIA,
    'pl02_gm': {0: [(1, None, 4)]},                 # Trish: hair
}


def _sample(a, n, seed=0):
    if len(a) <= n:
        return a
    return a[np.random.default_rng(seed).choice(len(a), n, replace=False)]


def fit(body_skel, body_meshes, part_skel, part_meshes):
    """(bone, shift, score): the body bone the part hangs from and the shift
    that moves the part from its own space into the body's."""
    B = _sample(np.concatenate([np.asarray(m['pos'], float) for m in body_meshes]), 3000)
    P = _sample(np.concatenate([np.asarray(m['pos'], float) for m in part_meshes]), 400, 1)
    world = np.asarray(body_skel['world'], float)
    cands = [(i, world[i]) for i in range(len(world))]
    root = np.asarray(part_skel['world'][0], float)
    if np.linalg.norm(root) > 1e-3:           # already placed in model space
        near = int(np.argmin(np.linalg.norm(world - root, axis=1)))
        cands.append((near, np.zeros(3)))
    best = None
    for bone, shift in cands:
        Q = P + shift
        d = np.sqrt(((Q[:, None, :] - B[None, :, :]) ** 2).sum(-1)).min(1)
        score = float(np.median(d))
        if best is None or score < best[2]:
            best = (bone, shift, score)
    return best


def transfer(body_meshes, pos, k=6):
    """Skin weights for points `pos` copied from the nearest body vertices,
    blended by inverse distance, top four bones kept."""
    B = np.concatenate([np.asarray(m['pos'], float) for m in body_meshes])
    J = np.concatenate([np.asarray(m['joints'], int)[:, :4] for m in body_meshes])
    W = np.concatenate([np.asarray(m['weights'], float)[:, :4] for m in body_meshes])
    P = np.asarray(pos, float)
    joints, weights = [], []
    for i0 in range(0, len(P), 256):
        d = np.sqrt(((P[i0:i0 + 256, None, :] - B[None, :, :]) ** 2).sum(-1))
        near = np.argsort(d, axis=1)[:, :k]
        for r, idx in enumerate(near):
            acc = {}
            inv = 1. / (d[r, idx] + 1e-3)
            for v, f in zip(idx, inv / inv.sum()):
                for j, w in zip(J[v], W[v]):
                    if w > 0:
                        acc[int(j)] = acc.get(int(j), 0.) + f * w
            top = sorted(acc.items(), key=lambda x: -x[1])[:4]
            t = sum(w for _, w in top) or 1.
            js = [j for j, _ in top] + [0] * (4 - len(top))
            ws = [w / t for _, w in top] + [0.] * (4 - len(top))
            joints.append(js)
            weights.append(ws)
    return joints, weights


def push_out(body_meshes, pos, clearance, k=4):
    """Move points that sit inside the body (or closer to its surface than
    `clearance`) out along the surface normal. Hair and coats hang straight
    in the bind pose, so without this a ponytail runs through the back."""
    B = np.concatenate([np.asarray(m['pos'], float) for m in body_meshes])
    N = np.concatenate([np.asarray(m['nrm'], float) for m in body_meshes])
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)
    P = np.array(pos, float)
    for i0 in range(0, len(P), 256):
        Q = P[i0:i0 + 256]
        d = ((Q[:, None, :] - B[None, :, :]) ** 2).sum(-1)
        near = np.argsort(d, axis=1)[:, :k]
        for r, idx in enumerate(near):
            n = N[idx].mean(0)
            ln = np.linalg.norm(n)
            if ln < 1e-6:
                continue
            n /= ln
            depth = (Q[r] - B[idx].mean(0)) @ n
            if depth < clearance:
                Q[r] += n * (clearance - depth)
        P[i0:i0 + 256] = Q
    return [tuple(v) for v in P]


def merge(body_skel, body_meshes, parts, mode='transfer'):
    """parts: [(part_skel, part_meshes, key, bone[, follow[, keep]])] -> (skel, meshes, report).
    `keep`, when given, lists the part's mesh indices to use.
    mode 'transfer' (default) skins each part vertex to the body bones of the
    nearest body vertices, so coat tails follow the legs and hair the head and
    back; 'rigid' keeps the part's own bones, hung unanimated on one body bone.
    `bone` is the body bone that places the part (None: fit it), `follow` the
    bone it moves with (default: the same one); `key`, when
    not None, prefixes the part meshes' material keys so their textures stay
    apart from the body's."""
    skel = dict(parent=list(body_skel['parent']), offset=[tuple(o) for o in body_skel['offset']],
                world=[tuple(w) for w in body_skel['world']])
    meshes = list(body_meshes)
    report = []
    for part in parts:
        pskel, pmeshes, key, want = part[:4]
        follow = part[4] if len(part) > 4 else None
        keep = part[5] if len(part) > 5 else None
        if keep is not None:
            pmeshes = [m for i, m in enumerate(pmeshes) if i in keep]
        if not pmeshes:
            continue
        if want is None:
            bone, shift, score = fit(body_skel, body_meshes, pskel, pmeshes)
        else:
            bone, shift, score = want, np.asarray(body_skel['world'][want], float), 0.
        if follow is not None:
            bone = follow
        if mode == 'transfer':
            B = np.concatenate([np.asarray(m['pos'], float) for m in body_meshes])
            clearance = 0.004 * float(B[:, 1].max() - B[:, 1].min())   # ~0.7 units on a 180 body
            for m in pmeshes:
                m = copy.copy(m)
                m['pos'] = push_out(body_meshes, [np.asarray(v, float) + shift for v in m['pos']], clearance)
                m['joints'], m['weights'] = transfer(body_meshes, m['pos'])
                if key is not None:
                    m['mat'] = (key, m['tex'])
                meshes.append(m)
            report.append((key, bone, round(score, 1), len(pmeshes)))
            continue
        base = len(skel['parent'])
        pw = np.asarray(pskel['world'], float) + shift
        for k, p in enumerate(pskel['parent']):
            if p < 0:
                skel['parent'].append(bone)
                skel['offset'].append(tuple(pw[k] - np.asarray(skel['world'][bone], float)))
            else:
                skel['parent'].append(base + p)
                skel['offset'].append(tuple(pskel['offset'][k]))
            skel['world'].append(tuple(pw[k]))
        n = len(pskel['parent'])
        for m in pmeshes:
            m = copy.copy(m)
            m['pos'] = [tuple(np.asarray(v, float) + shift) for v in m['pos']]
            m['joints'] = [[base + min(j, n - 1) for j in js] for js in m['joints']]
            if key is not None:
                m['mat'] = (key, m['tex'])
            meshes.append(m)
        report.append((key, bone, round(score, 1), len(pmeshes)))
    return skel, meshes, report
