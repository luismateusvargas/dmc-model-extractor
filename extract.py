import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bdp import BDP

def dump(bundle, outdir, exts):
    b = BDP(bundle)
    n = 0
    for e in b.entries:
        p = b.path_of(e)
        if not p.lower().endswith(exts):
            continue
        # several entries can share one logical name (header + payload chunks)
        fn = os.path.join(outdir, p.replace("\\", os.sep))
        if os.path.exists(fn):
            fn = "%s.%d%s" % (os.path.splitext(fn)[0], e["i"], os.path.splitext(fn)[1])
        os.makedirs(os.path.dirname(fn), exist_ok=True)
        open(fn, "wb").write(b.read(e))
        n += 1
    print("%s -> %d files in %s" % (os.path.basename(bundle), n, outdir))

DMC1_EXTS = (".pws", ".pwd", ".pld", ".emd", ".tm2", ".t32")
DMC2_EXTS = (".mdl", ".mdz", ".tm2")

if __name__ == "__main__":
    # python extract.py [<bundles dir>] [<output dir>]
    bdir = sys.argv[1] if len(sys.argv) > 1 else "PS3_GAME/USRDIR/BUNDLES"
    out = sys.argv[2] if len(sys.argv) > 2 else "extract"
    dump(os.path.join(bdir, "DMC1.BDP"), os.path.join(out, "DMC1"), DMC1_EXTS)
    dump(os.path.join(bdir, "DMC2.BDP"), os.path.join(out, "DMC2"), DMC2_EXTS)
