"""Pipeworks bundle (.BDP) reader - DMC HD Collection (PS3, big-endian).

Header (all BE):
  0x00 char[36] "Pipeworks bundle v1.xx (big endian)   " + 0x1a 0x00
  0x26 char[]   bundle name, 0xeb padded
  0x4c u32 fileSize      0x50 u32 typeCount     0x54 u32 typeTblOff   0x58 u32 typeTblSize
  0x5c u32 entryCount    0x60 u32 entryTblOff   0x64 u32 count2       0x68 u32 tbl2Off
  0x6c u32 ?             0x70 u32 dataOff       0x74 u32 nameTblOff   0x78 u32 nameTblSize
Type record: u8 flags, u8 ?, cstring name, optional 0xff pad
Entry record (16 B): u32 offset, u8 f1/u24 size, u8 f2/u24 rawSize, u32 hash
Name table: char[32] tag, u32 recCount, u32 strCount,
            recCount x (u32 hash, u16 dir, u16 name, u16 ext, u16 x),
            recCount x u32 hash, strCount x u32 strOffset, string blob
"""
import struct, sys, os, re

U = lambda b, o: struct.unpack_from(">I", b, o)[0]

class BDP:
    def __init__(self, path):
        self.path = path
        self.f = open(path, "rb")
        h = self.f.read(0x200)
        if h[:16] != b"Pipeworks bundle":
            raise ValueError("not a Pipeworks bundle: %r" % h[:16])
        self.sig = h[:0x24].decode("ascii", "replace").strip()
        self.version = re.search(r"v(\d+\.\d+)", self.sig).group(1)
        self.name = h[0x26:].split(b"\xeb")[0].split(b"\0")[0].decode("ascii", "replace")
        (self.size, self.ntypes, self.type_off, self.type_size,
         self.nentries, self.entry_off) = struct.unpack_from(">6I", h, 0x4c)
        # The header ends where the type table begins; its last two words are
        # always the name-table pointer/size (v1.20 puts them at 0x74, v1.30 at 0x7c).
        self.name_off, self.name_size = struct.unpack_from(">2I", h, self.type_off - 8)
        self.data_off = None
        self.types = self._read_types()
        self.entries = self._read_entries()
        self.names = self._read_names()

    def _at(self, off, n):
        self.f.seek(off); return self.f.read(n)

    def _read_types(self):
        b = self._at(self.type_off, self.type_size)
        out, o = [], 0
        while o + 2 < len(b) and len(out) < self.ntypes:
            f1, f2 = b[o], b[o + 1]
            e = b.index(b"\0", o + 2)
            out.append((f1, f2, b[o + 2:e].decode("ascii", "replace")))
            o = e + 1
            while o < len(b) and b[o] == 0xff:
                o += 1
        return out

    def _read_entries(self):
        b = self._at(self.entry_off, self.nentries * 16)
        out = []
        for i in range(self.nentries):
            off, a, c, h = struct.unpack_from(">4I", b, i * 16)
            out.append(dict(i=i, off=off, size=a & 0xffffff, f1=a >> 24,
                            raw=c & 0xffffff, f2=c >> 24, hash=h))
        return out

    def _read_names(self):
        if not self.name_size:
            return {}
        b = self._at(self.name_off, self.name_size)
        nrec, nstr = U(b, 0x20), U(b, 0x24)
        rec_o = 0x28
        str_o = rec_o + nrec * 12 + nrec * 4
        blob = str_o + nstr * 4
        strs = []
        for i in range(nstr):
            s = blob + U(b, str_o + i * 4)
            strs.append(b[s:b.index(b"\0", s)].decode("ascii", "replace"))
        out = {}
        for i in range(nrec):
            h, d, n, x, _z = struct.unpack_from(">I4H", b, rec_o + i * 12)
            g = lambda k: strs[k] if k < len(strs) else "?%d" % k
            p = g(d)
            p = (p + "\\" if p else "") + g(n)
            if x:
                p += "." + g(x)
            out[h] = p
        return out

    def path_of(self, e):
        return self.names.get(e["hash"], "%08x" % e["hash"])

    def read(self, e):
        return self._at(e["off"], e["size"])

if __name__ == "__main__":
    b = BDP(sys.argv[1])
    print("%s  '%s'  v%s" % (os.path.basename(b.path), b.name, b.version))
    print("  size=%d entries=%d types=%d names=%d" %
          (b.size, b.nentries, b.ntypes, len(b.names)))
    print("  types:", ", ".join("%s(%02x,%02x)" % (t[2], t[0], t[1]) for t in b.types))
    from collections import Counter
    c = Counter(os.path.splitext(b.path_of(e))[1].lower() for e in b.entries)
    print("  extensions:", dict(c.most_common(30)))
    for e in b.entries[:12]:
        d = b.read(e)[:4]
        print("   [%4d] %-52s off=%9d size=%8d raw=%8d f=%02x/%02x magic=%r" %
              (e["i"], b.path_of(e), e["off"], e["size"], e["raw"], e["f1"], e["f2"], d))
