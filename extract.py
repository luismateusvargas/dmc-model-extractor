"""Pull the model-bearing files out of a .BDP bundle.

    python extract.py [<bundles dir>] [<output dir>]

Selection is by filename pattern, not just extension, because DMC2 keeps its
stage props in `sobj_*.bin` next to three thousand other `.bin` files.
"""
import sys, os, fnmatch
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bdp import BDP

def dump(bundle, outdir, patterns):
    """Write every entry whose filename matches one of `patterns`."""
    b = BDP(bundle)
    n = 0
    for e in b.entries:
        p = b.path_of(e)
        base = os.path.basename(p).lower()
        if not any(fnmatch.fnmatch(base, pat) for pat in patterns):
            continue
        # several entries can share one logical name (header + payload chunks)
        fn = os.path.join(outdir, p.replace("\\", os.sep))
        if os.path.exists(fn):
            fn = "%s.%d%s" % (os.path.splitext(fn)[0], e["i"], os.path.splitext(fn)[1])
        os.makedirs(os.path.dirname(fn), exist_ok=True)
        open(fn, "wb").write(b.read(e))
        n += 1
    print("%s -> %d files in %s" % (os.path.basename(bundle), n, outdir))

# players and weapons (.pld/.pws/.pwd), enemies (.emd), stages and their props
# (.fsd), plus the textures nobody has decoded yet
DMC1_PATTERNS = ("*.pws", "*.pwd", "*.pld", "*.emd", "*.fsd", "*.tm2", "*.t32")
# players and enemies (.mdl/.mdz), stage props (sobj_*.bin), textures
DMC2_PATTERNS = ("*.mdl", "*.mdz", "sobj_*.bin", "*.tm2")

if __name__ == "__main__":
    # python extract.py [<bundles dir>] [<output dir>]
    bdir = sys.argv[1] if len(sys.argv) > 1 else "PS3_GAME/USRDIR/BUNDLES"
    out = sys.argv[2] if len(sys.argv) > 2 else "extract"
    dump(os.path.join(bdir, "DMC1.BDP"), os.path.join(out, "DMC1"), DMC1_PATTERNS)
    dump(os.path.join(bdir, "DMC2.BDP"), os.path.join(out, "DMC2"), DMC2_PATTERNS)
