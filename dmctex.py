"""Texture reader for the DMC HD Collection (PS3).

Three games, three containers, and none of them is documented. What they have
in common is that a model file carries its own textures, so a mesh's `texIndex`
is an index into a list that lives in the same file.

DMC1 - Pipeworks container, magic 'T32\\0' or 'TM2\\0' stored word-reversed, so
       the first four bytes on disc read `00 32 33 54`. Big-endian.

           file header   u32 magic | u32 imageCount | u32 headerSize | u32 dataSize
           image header  0xa0 B each, from +0x10; headerSize == 0x10 + 0xa0*count
                 +0x00 u32 index   +0x24 u32 dataSize   +0x38 u8 formatCode
                 +0x40 u16 width   +0x42 u16 height
           then every image's data back to back, in header order.

       Despite the 'T32' name the payload is almost always DXT: the HD port
       re-encoded the PS2 art at twice the original resolution (UVs are
       normalised, so that costs nothing here). The low nibble of the format
       code says which - 5 = uncompressed ARGB8888, 6 = DXT1, 8 = DXT5 - and
       bit 0x20 means the image carries no mipmaps. Only level 0 is read.

DMC2 - stock PS2 TIM2, little-endian, one picture per block, PSMT8 with a
       256-entry CSM1 palette in the overwhelming majority. Textures sit in
       their own MOMO section, the one right after the geometry they belong to.

DMC3 - entry 0 of every model .PAC. Big-endian:

           u32 imageCount | u32 size[count-1], in 2 KiB units
           image 0 at 0x800, the rest back to back; the last runs to the end
           image header 0x50 B, data right after it
                 +0x04 u8 formatCode (same nibbles as DMC1)
                 +0x0c u16 width  +0x0e u16 height   (the stored, 2x size)
                 +0x30 u16 width  +0x32 u16 height   (the PS2 size the UVs use)

       DXT again, but each block's 32-bit words are rotated: what a decoder
       wants as [w0 w1 ... wn] is stored as [wn w0 ... wn-1]. Read it straight
       and you get plausible-looking noise, which is what makes it worth saying
       out loud. (There are no textures in 'ipum' blocks - that magic only
       shows up in ID55??.PAC, which are PS2 IPU video streams.)

The alpha channel is real and used for cut-outs (hair, coat trims, foliage), so
it is kept; TIM2's 0..128 alpha is rescaled to 0..255 on the way out.
"""
import os
import struct
import zlib

# low nibble of the DMC1/DMC3 format code
ARGB, DXT1, DXT5 = 5, 6, 8


# ---------------------------------------------------------------- PNG output

def write_png(path, w, h, rgba):
    """Write RGBA8888 as a PNG. No dependencies, so no Pillow required."""
    raw = b''.join(b'\x00' + bytes(rgba[y * w * 4:(y + 1) * w * 4]) for y in range(h))

    def chunk(tag, data):
        c = tag + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)

    open(path, 'wb').write(
        b'\x89PNG\r\n\x1a\n'
        + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
        + chunk(b'IDAT', zlib.compress(raw, 6))
        + chunk(b'IEND', b''))


# ------------------------------------------------------------ pixel decoding

def _rgb565(c):
    return ((c >> 11 & 31) * 255 // 31, (c >> 5 & 63) * 255 // 63, (c & 31) * 255 // 31)


def _unrotate(data, size):
    """DMC3 only: move each block's last 32-bit word back to the front."""
    out = bytearray(len(data))
    for o in range(0, len(data) - size + 1, size):
        out[o:o + size - 4] = data[o + 4:o + size]
        out[o + size - 4:o + size] = data[o:o + 4]
    return bytes(out)


def decode_dxt(data, w, h, dxt5):
    """Level 0 of a DXT1/DXT5 surface as RGBA8888."""
    out = bytearray(w * h * 4)
    bw, bh = max(1, (w + 3) // 4), max(1, (h + 3) // 4)
    step = 16 if dxt5 else 8
    for by in range(bh):
        for bx in range(bw):
            o = (by * bw + bx) * step
            if o + step > len(data):
                return bytes(out)
            if dxt5:
                a0, a1 = data[o], data[o + 1]
                abits = int.from_bytes(data[o + 2:o + 8], 'little')
                alpha = [a0, a1]
                if a0 > a1:
                    alpha += [((7 - k) * a0 + k * a1) // 7 for k in range(1, 7)]
                else:
                    alpha += [((5 - k) * a0 + k * a1) // 5 for k in range(1, 5)] + [0, 255]
                o += 8
            c0, c1, bits = struct.unpack_from('<HHI', data, o)
            cols = [_rgb565(c0), _rgb565(c1)]
            # DXT5 always interpolates; in DXT1 c0 <= c1 selects the 1-bit
            # alpha mode, where index 3 is a hole rather than a colour
            if dxt5 or c0 > c1:
                cols.append(tuple((2 * cols[0][k] + cols[1][k]) // 3 for k in range(3)))
                cols.append(tuple((cols[0][k] + 2 * cols[1][k]) // 3 for k in range(3)))
                ca = (255, 255, 255, 255)
            else:
                cols.append(tuple((cols[0][k] + cols[1][k]) // 2 for k in range(3)))
                cols.append((0, 0, 0))
                ca = (255, 255, 255, 0)
            for py in range(4):
                y = by * 4 + py
                if y >= h:
                    break
                for px in range(4):
                    x = bx * 4 + px
                    if x >= w:
                        break
                    i = py * 4 + px
                    ci = (bits >> (2 * i)) & 3
                    p = (y * w + x) * 4
                    out[p:p + 3] = bytes(cols[ci])
                    out[p + 3] = alpha[(abits >> (3 * i)) & 7] if dxt5 else ca[ci]
    return bytes(out)


def decode_argb(data, w, h):
    """Uncompressed DMC1 images are ARGB8888, alpha first."""
    out = bytearray(w * h * 4)
    for k in range(min(w * h, len(data) // 4)):
        a, r, g, b = data[k * 4:k * 4 + 4]
        out[k * 4:k * 4 + 4] = bytes((r, g, b, a))
    return bytes(out)


def _decode(code, data, w, h, rotated):
    """Dispatch on a DMC1/DMC3 format code. Returns RGBA8888 or None."""
    kind = code & 0x0f
    if kind in (DXT1, DXT5):
        size = 16 if kind == DXT5 else 8
        return decode_dxt(_unrotate(data, size) if rotated else data, w, h, kind == DXT5)
    if kind == ARGB:
        return decode_argb(data, w, h)
    return None


# ------------------------------------------------- DMC1: Pipeworks container

_PIPEWORKS_MAGIC = (b'\x0023T', b'\x002MT')     # 'T32\0' and 'TM2\0', word-reversed


def pipeworks_sets(b):
    """Every T32/TM2 container in `b`, as (endOffset, [(w, h, rgba), ...]).

    Offsets are kept so a mesh can be matched to the container that follows it;
    see `pick`. The header-size check is what keeps a stray 'T32' in the middle
    of vertex data from being mistaken for a container.
    """
    starts = []
    for magic in _PIPEWORKS_MAGIC:
        i = b.find(magic)
        while i >= 0:
            count, hsize = struct.unpack_from('>2I', b, i + 4)
            if count and hsize == 0x10 + 0xa0 * count:
                starts.append((i, count))
            i = b.find(magic, i + 1)

    sets = []
    for i, count in sorted(starts):
        off = i + 0x10 + 0xa0 * count
        images = []
        for k in range(count):
            head = i + 0x10 + 0xa0 * k
            size = struct.unpack_from('>I', b, head + 0x24)[0]
            w, h = struct.unpack_from('>2H', b, head + 0x40)
            code = b[head + 0x38]
            if w and h and off + size <= len(b):
                px = _decode(code, b[off:off + size], w, h, rotated=False)
                if px is not None:
                    images.append((w, h, px))
            off += size
        if images:
            sets.append((off, images))
    return sets


# -------------------------------------------------------------- DMC2: TIM2

def _clut_order(n):
    """CSM1 stores a 256-entry palette with every other pair of 8 swapped."""
    if n != 256:
        return list(range(n))
    return [(i & 0xE7) | ((i & 0x08) << 1) | ((i & 0x10) >> 1) for i in range(n)]


def _tim2(b, i):
    """One TIM2 picture at `i`, or None. Returns (endOffset, w, h, rgba)."""
    if b[i + 4] != 4:                       # only version 4 is used here
        return None
    # format byte 5 selects the alignment: 0 puts the picture header at 0x10,
    # 1 pads it out to 0x80 so the pixels land on a 128-byte boundary
    ph = i + (0x10 if b[i + 5] == 0 else 0x80)
    if ph + 0x30 > len(b):
        return None
    total, clutsize, imgsize = struct.unpack_from('<3I', b, ph)
    hsize, ncol = struct.unpack_from('<2H', b, ph + 0x0c)
    itype = b[ph + 0x13]
    w, h = struct.unpack_from('<2H', b, ph + 0x14)
    if not (w and h) or hsize not in (0x30, 0x80) or ph + hsize + imgsize > len(b):
        return None
    img = b[ph + hsize:ph + hsize + imgsize]
    clut = b[ph + hsize + imgsize:ph + hsize + imgsize + clutsize]
    end = ph + hsize + total

    out = bytearray(w * h * 4)
    if itype in (4, 5) and ncol:
        if len(clut) < ncol * 4:            # truncated palette: not a picture
            return None
        order = _clut_order(ncol)
        # PS2 alpha runs 0..128, where 128 is opaque
        pal = [bytes((clut[order[k] * 4], clut[order[k] * 4 + 1], clut[order[k] * 4 + 2],
                      min(255, clut[order[k] * 4 + 3] * 2))) for k in range(ncol)]
        for k in range(min(w * h, imgsize * (2 if itype == 4 else 1))):
            idx = (img[k >> 1] >> (4 * (k & 1))) & 15 if itype == 4 else img[k]
            if idx < ncol:
                out[k * 4:k * 4 + 4] = pal[idx]
    elif itype == 3:                        # straight RGBA32
        for k in range(min(w * h, imgsize // 4)):
            r, g, bl, a = img[k * 4:k * 4 + 4]
            out[k * 4:k * 4 + 4] = bytes((r, g, bl, min(255, a * 2)))
    elif itype == 1:                        # RGBA5551
        for k in range(min(w * h, imgsize // 2)):
            c = struct.unpack_from('<H', img, k * 2)[0]
            out[k * 4:k * 4 + 4] = bytes(((c & 31) * 255 // 31, (c >> 5 & 31) * 255 // 31,
                                          (c >> 10 & 31) * 255 // 31, 255 if c >> 15 else 0))
    else:
        return None
    return end, w, h, bytes(out)


def tim2_sets(b):
    """TIM2 pictures grouped by MOMO section, as (endOffset, [(w, h, rgba), ...]).

    Grouping matters: a DMC2 model file holds a dozen submodels, and each one's
    texIndex counts from zero within its own section. Sections come in pairs -
    geometry, then the textures it uses - so a section's pictures are exactly
    the list the preceding geometry indexes into.
    """
    bounds = []
    if b[:4] == b'MOMO':
        n = struct.unpack_from('<I', b, 4)[0]
        if 0 < n < 4096 and 8 + 8 * n <= len(b):
            bounds = [struct.unpack_from('<2I', b, 8 + 8 * k) for k in range(n)]
    if not bounds:
        bounds = [(0, len(b))]

    sets = []
    for off, size in bounds:
        if not (0 <= off < len(b)):
            continue
        end = min(off + size, len(b))
        images, i = [], b.find(b'TIM2', off, end)
        while i >= 0:
            r = _tim2(b, i)
            if r is None:
                i = b.find(b'TIM2', i + 4, end)
                continue
            nxt, w, h, px = r
            images.append((w, h, px))
            i = b.find(b'TIM2', max(nxt, i + 4), end)
        if images:
            sets.append((end, images))
    return sets


# --------------------------------------------------------------- DMC3: PAC

def is_dmc3_textures(b):
    """True for the texture entry of a model PAC.

    The tell is the constant at +0x808 - the first image header always starts
    at 0x800 and always carries 0x0000aae4 in its second word.
    """
    return len(b) > 0x900 and struct.unpack_from('>I', b, 0x808)[0] == 0xaae4


def dmc3_textures(b):
    """Every image in a DMC3 texture block, in index order."""
    count = struct.unpack_from('>I', b, 0)[0]
    if not (0 < count < 256) or 4 + 4 * count > len(b):
        return []
    sizes = [struct.unpack_from('>I', b, 4 + 4 * k)[0] * 0x800 for k in range(count - 1)]
    if sum(sizes) + 0x800 > len(b):
        return []
    sizes.append(len(b) - 0x800 - sum(sizes))

    images, off = [], 0x800
    for size in sizes:
        code = b[off + 4]
        w, h = struct.unpack_from('>2H', b, off + 0x0c)
        if w and h:
            px = _decode(code, b[off + 0x50:off + size], w, h, rotated=True)
            if px is not None:
                images.append((w, h, px))
        off += size
    return images


# ------------------------------------------------------------- mesh pairing

def assign(sets, positions):
    """Match meshes to texture containers. `positions` is [(offset, slot), ...].

    Textures follow the geometry that uses them, so meshes are first split into
    groups by which container comes next - that grouping is the format talking,
    since a DMC2 file is a dozen geometry/texture section pairs in a row and
    each pair numbers its slots from zero again.

    The group, not the mesh, then picks the container: it has to be one that
    holds every slot the group asks for. DMC1 enemies are why - they drop one-
    and four-image containers (damage states) between a body and the nine-image
    container the body actually indexes into, so resolving a mesh on its own
    would hand slot 0 to the wrong container and split one model's skin across
    three of them.

    Returns [containerIndex or None] parallel to `positions`.
    """
    if not sets:
        return [None] * len(positions)

    def nxt(pos):
        for k, (end, _) in enumerate(sets):
            if end > pos:
                return k
        return len(sets)

    groups = {}
    for pos, slot in positions:
        k = nxt(pos)
        groups[k] = max(groups.get(k, 0), slot + 1)

    biggest = max(range(len(sets)), key=lambda k: len(sets[k][1]))
    for k, need in list(groups.items()):
        # the first container from here on that holds the whole group; a few
        # DMC1 props over-index every container, and then the largest is the
        # only sensible guess left
        groups[k] = next((j for j in range(k, len(sets)) if len(sets[j][1]) >= need),
                         biggest)

    out = []
    for pos, slot in positions:
        j = groups[nxt(pos)]
        out.append(j if slot < len(sets[j][1]) else None)
    return out


# ------------------------------------------------------------- OBJ material

def save(sets, outdir, stem, used):
    """Write the (container, slot) pairs in `used` as PNGs under `outdir/textures`.

    Returns {(container, slot): material name}. Material names stay plain
    `texN` for the common single-container model and only grow the container
    number when a file really does carry several texture sets.
    """
    if not used:
        return {}
    tdir = os.path.join(outdir, "textures")
    os.makedirs(tdir, exist_ok=True)
    many = len({k for k, _ in used}) > 1
    out = {}
    for k, slot in sorted(used):
        w, h, px = sets[k][1][slot]
        mtl = "s%02d_tex%d" % (k, slot) if many else "tex%d" % slot
        write_png(os.path.join(tdir, "%s_%s.png" % (stem, mtl)), w, h, px)
        out[(k, slot)] = mtl
    return out


def write_mtl(path, stem, mtls):
    """A material per texture, named to match the OBJ's `usemtl` lines."""
    with open(path, 'w') as f:
        f.write("# Devil May Cry HD Collection (PS3)\n")
        for mtl in sorted(set(mtls.values())):
            png = "textures/%s_%s.png" % (stem, mtl)
            f.write("\nnewmtl %s\n" % mtl)
            f.write("Kd 1 1 1\nd 1\nillum 1\n")
            f.write("map_Kd %s\n" % png)
            f.write("map_d %s\n" % png)             # the alpha is the cut-out mask
