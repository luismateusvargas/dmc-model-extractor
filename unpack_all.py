"""DMC3: recursively unpack the PAC / PNST containers from GDATA.AFS.

Both magics are the same big-endian structure:
    magic 'PAC\\0' or 'PNST' | u32 count @4 | u32 offset table @8
An entry ends where the next begins. Containers nest, so this recurses.
The model archives are really PNST containers holding 'MOD ' meshes:
PLWP_*.PAC (weapons), PL???.PAC (players) and EM???.PAC (enemies).

    python unpack_all.py [<GDATA.AFS dir>] [<output dir>] [<pattern>]

Defaults match the layout dmcextract.py builds.
"""
import struct
import os
import sys
import glob

CONTAINERS = (b'PAC\x00', b'PNST')


def is_container(b):
    if len(b) < 12 or b[:4] not in CONTAINERS:
        return False
    cnt = struct.unpack_from(">I", b, 4)[0]
    if not (0 < cnt < 4096) or 8 + 4 * cnt > len(b):
        return False
    return True


def entries(b):
    cnt = struct.unpack_from(">I", b, 4)[0]
    offs = [struct.unpack_from(">I", b, 8 + 4 * i)[0] for i in range(cnt)]
    offs = [o for o in offs if 0 < o <= len(b)]
    ends = offs[1:] + [len(b)]
    return list(zip(offs, ends))


def walk(b, outdir, found, depth=0, tag="root", quiet=False):
    pad = "  " * depth
    os.makedirs(outdir, exist_ok=True)
    if not quiet:
        print(f"{pad}{tag}: {b[:4]!r} {len(b)} bytes, {len(entries(b))} entries")
    for i, (o, e) in enumerate(entries(b)):
        sub = b[o:e]
        if len(sub) < 4:
            continue
        m = sub[:4]
        am = ''.join(chr(c) if 32 <= c < 127 else '.' for c in m)
        if is_container(sub):
            walk(sub, os.path.join(outdir, f"{i:02d}"), found, depth + 1,
                 f"[{i:02d}] {am}", quiet)
        else:
            ext = 'mod' if m == b'MOD ' else ('shw' if m == b'SHW ' else 'bin')
            fn = os.path.join(outdir, f"{i:02d}.{ext}")
            with open(fn, 'wb') as f:
                f.write(sub)
            if m == b'MOD ':
                found.append(fn)
            if not quiet:
                note = (" ver(BE)=%.3f" % struct.unpack_from('>f', sub, 4)[0]
                        if m == b'MOD ' else "")
                print(f"{pad}  [{i:02d}] size={len(sub):>8} '{am}' -> {fn}{note}")


def unpack_dir(afs_dir, outdir, quiet=True, pattern="PLWP_*.PAC"):
    """Unpack every archive matching `pattern`. Returns the list of .mod files."""
    found = []
    for path in sorted(glob.glob(os.path.join(afs_dir, pattern))):
        name = os.path.basename(path)
        with open(path, 'rb') as f:
            b = f.read()
        walk(b, os.path.join(outdir, name.replace('.', '_')), found, 0, name, quiet)
    return found


if __name__ == "__main__":
    afs = sys.argv[1] if len(sys.argv) > 1 else r"isoextract\PS3_GAME\USRDIR\GDATA.AFS"
    out = sys.argv[2] if len(sys.argv) > 2 else "unpacked"
    pat = sys.argv[3] if len(sys.argv) > 3 else "PLWP_*.PAC"
    mods = unpack_dir(afs, out, quiet=False, pattern=pat)
    print("MOD files found:", len(mods))
    for f in mods:
        print("  ", f, os.path.getsize(f))
