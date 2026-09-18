"""DMC Model Extractor - one-command pipeline.

Put your Devil May Cry HD Collection (PS3) .iso into the `iso/` folder next to
this script, then run:

    python dmcextract.py

If no .iso is there, this does nothing and says so. Nothing else is required.

Everything is resolved relative to this file, so it does not matter which folder
you run it from. Intermediate files land in `build/`, finished models in `out/`,
one folder per game and category (players, enemies, weapons, props). Each OBJ
comes with its .mtl and a `textures/` folder of PNGs, so it opens textured.
DMC2's and DMC3's characters also come out rigged and animated, as .glb files
in DMC2_animated and DMC3_animated.
"""
import os
import sys
import glob
import shutil
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import extract as bdp_extract
import unpack_all
import modbe2
import dmc3anim
import dmc12anim
from dmc2obj import convert as obj_convert

REPO = os.path.dirname(os.path.abspath(__file__))
ISO_DIR = os.path.join(REPO, "iso")
BUILD = os.path.join(REPO, "build")
OUT = os.path.join(REPO, "out")

# Members pulled from the ISO. DMC1/DMC2 live in bundles; DMC3 in GDATA.AFS,
# which 7-Zip descends into on its own. PL???_??_?.PAC carry no geometry: they
# are the players' motion packs, which dmc3anim pairs with PL???.PAC.
BUNDLES = ["PS3_GAME/USRDIR/BUNDLES/DMC1.BDP", "PS3_GAME/USRDIR/BUNDLES/DMC2.BDP"]
DMC3_MEMBERS = ["PS3_GAME/USRDIR/GDATA.AFS/PLWP_*.PAC",
                "PS3_GAME/USRDIR/GDATA.AFS/PL???.PAC",
                "PS3_GAME/USRDIR/GDATA.AFS/PL???_*.PAC",
                "PS3_GAME/USRDIR/GDATA.AFS/EM???.PAC"]

SEVENZIP_GUESSES = [
    r"C:\Program Files\7-Zip\7z.exe",
    r"C:\Program Files (x86)\7-Zip\7z.exe",
    "/usr/bin/7z",
    "/usr/local/bin/7z",
]


def find_iso():
    """The first .iso in iso/, or None. Case-insensitive, so .ISO works too."""
    if not os.path.isdir(ISO_DIR):
        return None
    found = [f for f in sorted(glob.glob(os.path.join(ISO_DIR, "*")))
             if os.path.isfile(f) and os.path.splitext(f)[1].lower() == ".iso"]
    return found[0] if found else None


def find_7zip():
    for name in ("7z", "7za", "7zz"):
        p = shutil.which(name)
        if p:
            return p
    for p in SEVENZIP_GUESSES:
        if os.path.isfile(p):
            return p
    return None


def sevenzip(exe, iso, outdir, members):
    """Extract members from the ISO.

    7-Zip exits 2 with 'Open Errors: 1' on this image but extracts correctly,
    so the return code is reported and not treated as fatal.
    """
    cmd = [exe, "x", iso, "-o" + outdir] + list(members) + ["-y"]
    print("   7z ->", outdir)
    r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    if r.returncode not in (0, 1, 2):
        print("   !! 7-Zip failed with exit code %d" % r.returncode)
        return False
    return True


def convert_all(pattern, game, outdir):
    n = 0
    for p in sorted(glob.glob(pattern)):
        n += obj_convert(p, outdir, {"dmc1": ">", "dmc2": "<"}[game])
    return n


def dmc3(afs, name, pattern, outdir):
    """Unpack one family of DMC3 archives and convert every MOD inside."""
    unpacked = os.path.join(BUILD, "unpacked", name)
    # a re-run over a stale directory would leave the previous unpack's files
    # behind, and a texture block saved as .bin by an older version with it
    shutil.rmtree(unpacked, ignore_errors=True)
    mods = unpack_all.unpack_dir(afs, unpacked, pattern=pattern)
    print("   %s: %d MOD meshes found" % (name, len(mods)))
    return modbe2.convert_dir(unpacked, outdir)


def main():
    iso = find_iso()
    if iso is None:
        os.makedirs(ISO_DIR, exist_ok=True)
        print("No .iso found in:\n    %s\n" % ISO_DIR)
        print("Put your Devil May Cry HD Collection (PS3) disc image in that")
        print("folder and run this again. Nothing was changed.")
        return 0

    exe = find_7zip()
    if exe is None:
        print("7-Zip was not found. Install it from https://www.7-zip.org/")
        print("(looked on PATH and in %s)" % SEVENZIP_GUESSES[0])
        return 1

    print("ISO:   %s" % iso)
    print("7-Zip: %s" % exe)
    print("Build: %s" % BUILD)
    print("Out:   %s\n" % OUT)

    # ---- 1. unpack the ISO -------------------------------------------------
    print("[1/5] Reading the ISO (this takes a few minutes, ~4.6 GB)")
    bundle_dir = os.path.join(BUILD, "bundles")
    iso_pac_dir = os.path.join(BUILD, "isoextract")
    if not glob.glob(os.path.join(bundle_dir, "PS3_GAME", "USRDIR", "BUNDLES", "*.BDP")):
        if not sevenzip(exe, iso, bundle_dir, BUNDLES):
            return 1
    else:
        print("   bundles already extracted, skipping")
    afs = os.path.join(iso_pac_dir, "PS3_GAME", "USRDIR", "GDATA.AFS")
    if not (glob.glob(os.path.join(afs, "EM???.PAC"))
            and glob.glob(os.path.join(afs, "PL???_*.PAC"))):
        if not sevenzip(exe, iso, iso_pac_dir, DMC3_MEMBERS):
            return 1
    else:
        print("   DMC3 archives already extracted, skipping")

    # ---- 2. DMC1 / DMC2 ----------------------------------------------------
    print("\n[2/5] Unpacking the DMC1 and DMC2 bundles")
    bdir = os.path.join(bundle_dir, "PS3_GAME", "USRDIR", "BUNDLES")
    ex = os.path.join(BUILD, "extract")
    # dump() renames rather than overwrites when a name repeats, so a stale
    # directory would accumulate duplicates on every re-run. Start clean.
    shutil.rmtree(ex, ignore_errors=True)
    bdp_extract.dump(os.path.join(bdir, "DMC1.BDP"), os.path.join(ex, "DMC1"),
                     bdp_extract.DMC1_PATTERNS)
    bdp_extract.dump(os.path.join(bdir, "DMC2.BDP"), os.path.join(ex, "DMC2"),
                     bdp_extract.DMC2_PATTERNS)

    print("\n[3/5] Converting DMC1 and DMC2 to OBJ")
    d1 = os.path.join(ex, "DMC1", "data")
    d2 = os.path.join(ex, "DMC2", "data")
    jobs = [
        (os.path.join(d1, "pld", "*.pws"), "dmc1", "DMC1_weapons"),
        (os.path.join(d1, "pld", "*.pwd"), "dmc1", "DMC1_weapons"),
        (os.path.join(d1, "pld", "*.pld"), "dmc1", "DMC1_players"),
        (os.path.join(d1, "emd", "*.emd"), "dmc1", "DMC1_enemies"),
        (os.path.join(d1, "fsd", "*.fsd"), "dmc1", "DMC1_props"),
        (os.path.join(d2, "pl*.md*"), "dmc2", "DMC2_players"),
        (os.path.join(d2, "em*.md*"), "dmc2", "DMC2_enemies"),
        (os.path.join(d2, "sobj_*.bin"), "dmc2", "DMC2_props"),
        (os.path.join(d2, "mclear.mdz"), "dmc2", "DMC2_props"),
    ]
    totals = {}
    for pattern, game, name in jobs:
        n = convert_all(pattern, game, os.path.join(OUT, name))
        totals[name] = totals.get(name, 0) + n

    # ---- 3. DMC3 -----------------------------------------------------------
    print("\n[4/5] Unpacking and converting DMC3")
    for name, pattern in (("DMC3_weapons", "PLWP_*.PAC"),
                          ("DMC3_players", "PL???.PAC"),
                          ("DMC3_enemies", "EM???.PAC")):
        totals[name] = dmc3(afs, name, pattern, os.path.join(OUT, name))

    # ---- 4. skeletons and motions -----------------------------------------
    print("\n[5/5] Rigging and animating the characters")
    glbs = {}
    for name, run in (("DMC2_animated", lambda o: dmc12anim.convert_dmc2(d2, o)),
                      ("DMC3_animated", lambda o: dmc3anim.convert(
                          os.path.join(BUILD, "unpacked"), afs, o))):
        anim = os.path.join(OUT, name)
        shutil.rmtree(anim, ignore_errors=True)
        glbs[name] = run(anim)

    print("\nDone. OBJ files written to %s:" % OUT)
    for name in sorted(totals):
        png = len(glob.glob(os.path.join(OUT, name, "textures", "*.png")))
        print("   %-16s %4d obj  %5d png" % (name, totals[name], png))
    for name in sorted(glbs):
        print("   %-16s %4d glb  (rigged, with their animations)" % (name, glbs[name]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
