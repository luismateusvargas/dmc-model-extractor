"""Shared Pipeworks mesh reader for the DMC HD Collection (PS3).

DMC1 (.pws / .pwd / .pld) is big-endian, DMC2 (MOMO .mdl / .mdz) little-endian,
but the geometry structures are identical. A model file is a handful of
sections; a geometry section owns a table of OBJECT records, and every object
points at a run of MESH descriptors:

  section header    u8 objectCount | 3 B | u32 | (u32)  -- 8 B in DMC1, 12 in DMC2
  object record     u8 meshCount | u8 0 | u16 numVerts | u32 descOff  (stride 16)
  mesh descriptor   u16 numVerts | u16 texIndex |
                    u32 pos | u32 nrm | u32 uv | u32 bone | u32 weight (stride 32)

Every offset is relative to `base`, the start of the section that owns the
record table; the table itself begins 8 or 12 bytes into that section.

  arrays  pos/nrm 3xf32 | uv 2xi16/4096 with V flipped | bone 4 B | weight u16,
          bit 15 = triangle-strip break (the same convention as DMC3's MOD)
  0xcdcdcdcd is inter-block filler.

An object's meshes share one array per attribute: all the positions sit back to
back, then all the normals, and so on. That packing is what validates a
candidate table - together with the object record's vertex total, which must
equal the sum of its descriptors. Both are sharp enough that the section table
never has to be located: every 4-aligned offset is tried as a record table and
only real ones survive. `numVerts` in the object record is the object's total,
not a mesh's, which is why reading it as a mesh vertex count (as this file used
to) found only the objects that happen to hold a single mesh.

Meshes are keyed by their position-array offset, so passes can be unioned
without producing duplicates.
"""
import struct


def get_tris(pos, nrm, skip, n):
    """Walk a triangle strip, orienting each face against its summed vertex normals."""
    tris = []
    p1, p2 = 0, 1
    for i in range(2, n):
        p3 = i
        if not skip[i] and len({p1, p2, p3}) == 3:
            v1, v2, v3 = pos[p1], pos[p2], pos[p3]
            e1 = [v3[k] - v1[k] for k in range(3)]
            e2 = [v2[k] - v1[k] for k in range(3)]
            z = [e1[1]*e2[2] - e1[2]*e2[1],
                 e1[2]*e2[0] - e1[0]*e2[2],
                 e1[0]*e2[1] - e1[1]*e2[0]]
            nn = [nrm[p1][k] + nrm[p2][k] + nrm[p3][k] for k in range(3)]
            tris.append([p1, p3, p2] if sum(nn[k]*z[k] for k in range(3)) > 0
                        else [p1, p2, p3])
        p1, p2 = p2, p3
    return tris


class Reader:
    def __init__(self, data, endian):
        # a couple of files (DMC2 mclear.mdz) carry two junk bytes in front of
        # the magic, which would throw every offset in the file out by two
        if data[:4] != b"MOMO" and b"MOMO" in data[:16]:
            data = data[data.index(b"MOMO"):]
        self.b = data
        self.e = endian                 # ">" for DMC1, "<" for DMC2
        self.N = len(data)

    def u(self, f, o):
        return struct.unpack_from(self.e + f, self.b, o)[0]

    # ---- object-aware pass -------------------------------------------------

    def _desc(self, base, d):
        """Header half of a mesh descriptor: (numVerts, texIndex, arrays) or None."""
        if d + 32 > self.N:
            return None
        nv, tex = struct.unpack_from(self.e + "HH", self.b, d)
        if not (2 < nv < 65535):
            return None
        arr = [base + x for x in struct.unpack_from(self.e + "5I", self.b, d + 4)]
        if not all(0 < x < self.N for x in arr):
            return None
        po, no, uo, bo, wo = arr
        if (max(po, no) + nv*12 > self.N or uo + nv*4 > self.N
                or bo + nv*4 > self.N or wo + nv*2 > self.N):
            return None
        return nv, tex, arr

    def _read(self, nv, tex, arr):
        """Read one descriptor's vertex data, or None if it isn't vertex data."""
        b, e = self.b, self.e
        po, no, uo, bo, wo = arr
        pos = [struct.unpack_from(e + "3f", b, po + 12*k) for k in range(nv)]
        if not all(-1e5 < c < 1e5 for p in pos for c in p):
            return None
        nrm = [struct.unpack_from(e + "3f", b, no + 12*k) for k in range(nv)]
        if not all(-2.0 < c < 2.0 for n in nrm for c in n):
            return None
        uv = [(self.u("h", uo + 4*k) / 4096., 1. - self.u("h", uo + 4*k + 2) / 4096.)
              for k in range(nv)]
        skip = [(self.u("H", wo + 2*k) >> 15) & 1 for k in range(nv)]
        return dict(po=po, nv=nv, tex=tex, pos=pos, nrm=nrm, uv=uv,
                    tris=get_tris(pos, nrm, skip, nv))

    def obj(self, base, r):
        """Parse the object record at `r`, offsets relative to `base`.

        Returns its list of meshes, or None if `r` is not an object record.
        """
        if r + 16 > self.N or base < 0:
            return None
        mc, pad = self.b[r], self.b[r + 1]
        tv, doff = struct.unpack_from(self.e + "HI", self.b, r + 2)
        if pad or not (0 < mc <= 64) or not (2 < tv < 200000):
            return None
        if not (0 < base + doff < self.N):
            return None
        heads = []
        for i in range(mc):
            h = self._desc(base, base + doff + 32*i)
            if h is None:
                return None
            heads.append(h)
        # the record's total is the sum of its meshes - the cheapest and
        # sharpest test that this really is an object record
        if sum(h[0] for h in heads) != tv:
            return None
        # and one attribute's arrays are packed back to back across the object's
        # meshes, padded up to 16 (an already aligned array still gets 16 B)
        for k, w in ((0, 12), (1, 12), (2, 4), (3, 4), (4, 2)):
            for i in range(mc - 1):
                gap = heads[i+1][2][k] - heads[i][2][k]
                if not (heads[i][0]*w <= gap <= (heads[i][0]*w + 15)//16*16 + 16):
                    return None
        meshes = []
        for nv, tex, arr in heads:
            m = self._read(nv, tex, arr)
            if m is None:
                return None
            meshes.append(m)
        return meshes

    def scan_objects(self):
        """Try every 4-aligned offset as the start of an object-record table."""
        b, found, r = self.b, {}, 0
        while r < self.N - 16:
            # cheap reject first: the file is mostly not object records, and
            # every one of them starts with a small mesh count and a zero byte
            if not (0 < b[r] <= 64) or b[r + 1]:
                r += 4
                continue
            hit = 0
            for back in (8, 12):            # DMC1 and DMC2 section headers
                base, rr, objs = r - back, r, []
                while len(objs) < 256:
                    o = self.obj(base, rr)
                    if o is None:
                        break
                    objs.append(o)
                    rr += 16
                if objs:
                    for oi, o in enumerate(objs):
                        for m in o:
                            m["obj"] = oi
                            found.setdefault(m["po"], m)
                    hit = len(objs)
                    break
            r += hit * 16 if hit else 4
        return found

    # ---- legacy single-record pass -----------------------------------------

    def mesh(self, base, r):
        """Parse a lone mesh record at `r` - the pre-object-table reading.

        Kept as a fallback for files the object pass finds nothing in: it asks
        much less of the data, at the price of accepting some noise.
        """
        b, N, e = self.b, self.N, self.e
        if r + 16 > N or base < 0:
            return None
        flags, nv, doff = struct.unpack_from(e + "HHI", b, r)
        if not (0 < flags <= 0x0200) or not (2 < nv < 65535):
            return None
        d = base + doff
        if d + 24 > N:
            return None
        po, no, uo, bo, wo = (base + x for x in struct.unpack_from(e + "5I", b, d + 4))
        if not all(0 < x < N for x in (po, no, uo, wo)):
            return None
        # here a mesh stands alone, so its own arrays must be adjacent
        def spaced(lo, hi, w):
            return nv * w <= hi - lo <= (nv * w + 15) // 16 * 16 + 16
        if not (spaced(po, no, 12) and spaced(no, uo, 12)
                and spaced(uo, bo, 4) and spaced(bo, wo, 4)):
            return None
        if max(po, no) + nv*12 > N or uo + nv*4 > N or wo + nv*2 > N:
            return None
        m = self._read(nv, 0, (po, no, uo, bo, wo))
        if m is not None:
            m["obj"] = 0
        return m

    def _run(self, base, r, into):
        """Read consecutive records from `r` until one fails. Returns how many."""
        k = 0
        while k < 512:
            m = self.mesh(base, r + k*16)
            if m is None:
                break
            into.setdefault(m["po"], m)
            k += 1
        return k

    def scan(self, strict=True):
        """Walk every 4-aligned offset as a possible record table start.

        `strict` demands the record's trailing 8 bytes be zero, which is true of
        most tables and makes the pass cheap; dropping it catches the rest.
        """
        found, r = {}, 0
        Z = bytes(8)
        while r < self.N - 16:
            if strict and self.b[r + 8:r + 16] != Z:
                r += 4
                continue
            for back in (8, 12):
                k = self._run(r - back, r, found)
                if k:
                    r += k * 16 - 4
                    break
            r += 4
        return found

    def find_all(self):
        """Every mesh in the file, ordered by position offset.

        The object pass is the one that reads the format; the loose pass only
        runs when it comes up empty, so its noise never dilutes a good read.
        """
        found = self.scan_objects()
        if not found:
            found = self.scan(strict=False)
            found.update(self.scan(strict=True))
        return [found[k] for k in sorted(found)]
