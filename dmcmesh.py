"""Shared Pipeworks mesh reader for the DMC HD Collection (PS3).

DMC1 (.pws / .pwd / .pld) is big-endian, DMC2 (MOMO .mdl) little-endian, but the
geometry structures are identical:

  mesh record (stride 16)  u16 flags | u16 numVerts | u32 descOff | u32 | u32
  descriptor               u16 numVerts | u16 ? | u32 pos | u32 nrm
                           u32 uv | u32 bone | u32 weight

Every offset is relative to `base`, the start of the header that owns the record
table; the table itself begins 8 or 12 bytes into that header.

  arrays  pos/nrm 3xf32 | uv 2xi16/4096 with V flipped | bone 4 B | weight u16,
          bit 15 = triangle-strip break (the same convention as DMC3's MOD)
  0xcdcdcdcd is inter-block filler.

Meshes are keyed by their position-array offset, so the header walk and the
brute-force scan can be unioned without producing duplicates.
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
        self.b = data
        self.e = endian                 # ">" for DMC1, "<" for DMC2
        self.N = len(data)

    def u(self, f, o):
        return struct.unpack_from(self.e + f, self.b, o)[0]

    def mesh(self, base, r):
        """Parse the mesh record at `r` with offsets relative to `base`."""
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
        # The descriptor's leading u16 echoes numVerts in most files but not all,
        # so validate on array spacing instead. Arrays are padded up to 16, and
        # an already-aligned array still gets a full 16 bytes of 0xcd filler.
        def spaced(lo, hi, w):
            return nv * w <= hi - lo <= (nv * w + 15) // 16 * 16 + 16
        if not (spaced(po, no, 12) and spaced(no, uo, 12)
                and spaced(uo, bo, 4) and spaced(bo, wo, 4)):
            return None
        if max(po, no) + nv*12 > N or uo + nv*4 > N or wo + nv*2 > N:
            return None
        pos = [struct.unpack_from(e + "3f", b, po + 12*k) for k in range(nv)]
        if not all(-1e5 < c < 1e5 for p in pos for c in p):
            return None
        nrm = [struct.unpack_from(e + "3f", b, no + 12*k) for k in range(nv)]
        if not all(-2.0 < c < 2.0 for n in nrm for c in n):
            return None
        uv = [(self.u("h", uo + 4*k) / 4096., 1. - self.u("h", uo + 4*k + 2) / 4096.)
              for k in range(nv)]
        skip = [(self.u("H", wo + 2*k) >> 15) & 1 for k in range(nv)]
        return dict(po=po, nv=nv, pos=pos, nrm=nrm, uv=uv,
                    tris=get_tris(pos, nrm, skip, nv))

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
        """Union of both passes, keyed by position offset.

        Neither pass subsumes the other: they skip forward differently after a
        run, so a table one lands on mid-way the other can land on squarely.
        """
        found = self.scan(strict=False)
        found.update(self.scan(strict=True))
        return [found[k] for k in sorted(found)]
