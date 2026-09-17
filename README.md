# DMC Model Extractor

Pulls the 3D models out of **Devil May Cry HD Collection (PS3)** and writes them
as textured `.obj` files you can open in Blender.

You drop your disc image into the `iso/` folder and run **one command**.

| Game | weapons | players | enemies | props |
|---|---|---|---|---|
| DMC1 | 10 | 5 | 58 | 99 |
| DMC2 | *(inside the players)* | 8 | 51 | 26 |
| DMC3 | 121 | 48 | 315 | *(format not read)* |

**741 OBJ files in all**, with **1,756 PNG textures** — 737 of the 741 open
already textured.

The file formats are undocumented — no public spec, and no Noesis or Blender
plugin exists for DMC1/DMC2. They were reverse-engineered for this repo. Format
notes are in the comments at the top of `bdp.py`, `dmcmesh.py`, `modbe2.py` and
`dmctex.py` — the last one covers all three games' texture containers.

---

## 1. What you need

### Python

**Python 3.6 or newer.** Developed and tested on **3.14.5**.

To check if you have it, open a terminal (on Windows: press `Win`, type
`powershell`, press Enter) and type:

```powershell
python --version
```

If you see something like `Python 3.14.5`, you're set. If you get an error,
install it from <https://www.python.org/downloads/> and **tick "Add Python to
PATH"** during setup.

### Dependencies

**None.** There is nothing to `pip install`. The scripts use only Python's
built-in standard library (`struct`, `os`, `sys`, `glob`, `math`, `shutil`,
`subprocess`, `re`, `collections`).

### 7-Zip

Used to read files out of the `.iso`. Install from <https://www.7-zip.org/>.

You do **not** need to configure anything — the extractor finds it on your PATH,
and also checks `C:\Program Files\7-Zip\7z.exe` automatically.

### The game

Your own **Devil May Cry HD Collection (PS3)** disc image — a single file of
about 10 GB ending in `.iso`. **This repo contains no game data** and will not
get you any.

### Disk space

About **6 GB** free, on top of the ISO itself.

### Optional

**Blender** (<https://www.blender.org/>) to view the results. Any program that
opens OBJ files works.

---

## 2. How to run it

### Step 1 — put your ISO in the `iso/` folder

There is an empty folder named `iso/` in this repo. Copy your `.iso` into it.

```
dmc-model-extractor/
├── iso/
│   └── Devil May Cry - HD Collection (USA) (En,Ja,Fr,De,Es,It).iso   <- your file
├── dmcextract.py
└── ...
```

The name does not matter. The extractor uses the first `.iso` it finds there.

### Step 2 — run one command

```powershell
python dmcextract.py
```

That's it. It does not matter which folder you run it from — everything is
resolved relative to the script.

### What you'll see

```
ISO:   ...\iso\Devil May Cry - HD Collection (USA) ....iso
7-Zip: C:\Program Files\7-Zip\7z.exe

[1/4] Reading the ISO (this takes a few minutes, ~4.6 GB)
[2/4] Unpacking the DMC1 and DMC2 bundles
[3/4] Converting DMC1 and DMC2 to OBJ
OK   pw08             meshes=  3 verts=   376 tris=   236 nrmlen=1.0000 tex=1
...
[4/4] Unpacking and converting DMC3

Done. OBJ files written to ...\out:
   DMC1_enemies       58 obj    269 png
   DMC1_players        5 obj     21 png
   DMC1_props         99 obj    292 png
   DMC1_weapons       10 obj     10 png
   DMC2_enemies       51 obj    282 png
   DMC2_players        8 obj    185 png
   DMC2_props         26 obj    181 png
   DMC3_enemies      315 obj    335 png
   DMC3_players       48 obj     60 png
   DMC3_weapons      121 obj    121 png
```

The first run takes around twenty minutes, most of it reading the ISO. **Running it again is safe** — it skips the
slow ISO step and reuses what it already extracted.

### Where your models are

```
out/
├── DMC1_weapons/     pw01.obj ... pw0a.obj          <- all 10 DMC1 weapons
├── DMC1_players/     pl00.obj ...                   <- Dante and the other players
├── DMC1_enemies/     em00.obj ...                   <- every enemy
├── DMC1_props/       r11b.obj ...                   <- one file per room (`.fsd`)
├── DMC2_players/     pl00_gm.obj ...                <- Dante, Lucia, their weapons
├── DMC2_enemies/     em00_gm.obj ...
├── DMC2_props/       sobj_10.obj ...                <- stage objects
├── DMC3_weapons/     PLWP_SHOTGUN_PAC_01.obj ...
├── DMC3_players/     PL000_PAC_01.obj ...           <- Dante, Vergil, Lady, NPCs
└── DMC3_enemies/     EM000_PAC_01.obj ...
```

Each folder also holds a `.mtl` per model and a `textures/` subfolder of PNGs:

```
out/DMC1_weapons/
├── pw02.obj
├── pw02.mtl
└── textures/
    └── pw02_tex0.png
```

**Just open the `.obj`** — Blender reads the `.mtl` and the PNGs beside it, and
the model comes in textured. Nothing to point at by hand. The textures keep
their alpha, which the games use for cut-outs (hair, coat trims, foliage), so
the material sets each one as both the colour and the opacity map.

Every mesh is one OBJ group named `obj<NN>_m<MM>_tex<T>`: `NN` is the model's
own object index — a body part, a held weapon, a damage state — `MM` the mesh
within it, and `T` the texture slot it asks for. Hide and show them in Blender's
outliner to pull a model apart.

A PNG is named after the slot that uses it (`pw02_tex0.png`). Where one file
carries several independent texture sets — a DMC2 character file is a dozen
submodels in a row, each numbering its slots from zero again — the set number
goes in too: `pl00_gm_s03_tex1.png`.

> ✅ **`nrmlen=1.0000` in the output is your proof it worked.** That's the
> average length of the surface normals. Geometry read correctly gives 1.0000;
> 716 of the 741 files are exact. A dozen land between 0.92 and 0.99 — PS2-era
> normals that were quantised slightly short, not a misread. Anything far off
> that would mean the file was read wrong.

### If the `iso/` folder is empty

The extractor prints where it looked and **does nothing at all** — no files
created, no changes:

```
No .iso found in:
    ...\dmc-model-extractor\iso

Put your Devil May Cry HD Collection (PS3) disc image in that
folder and run this again. Nothing was changed.
```

---

## 3. Folders it creates

| Folder | What it is | Safe to delete? |
|---|---|---|
| `iso/` | where **you** put your disc image | it's your file |
| `build/` | intermediate files pulled from the ISO (~5.3 GB) | yes — regenerated on the next run |
| `out/` | **your finished `.obj` models** | that's the product, keep it |

`build/` and `out/` are in `.gitignore`, so they are never committed. Delete
`build/` when you're done to reclaim the space.

---

## 4. Which model is which weapon

**[`WEAPON_LABELS.md`](WEAPON_LABELS.md) identifies the 233 files of the first
pass** (DMC1 weapons/players/enemies, DMC2 characters, DMC3 weapons) — every
DMC1 weapon by name, every DMC3 PAC checked against its geometry, and the DMC2
weapons located inside the player models. Two things worth knowing up front:

- **Only 35 of the 233 files are weapons.** The 96 long-named DMC3 files
  (`PLWP_*_PAC_0N_01_NNN.obj`) are a shared effects library — slash arcs,
  shockwave rings, billboard quads, glow spheres — which is why so many of them
  look like Blender primitives. They are meaningless without their textures.
- **Four DMC3 PACs ship duplicate mesh payloads.** That is in Capcom's data,
  not a bug here; `GRENADE_PAC` in particular holds Rebellion, not Kalina Ann.

### Checking it yourself

`classify.py` measures every mesh and prints the ones that are geometrically a
disc, quad, plane, box, tube or sphere, plus a report of shapes shared between
files (which is how Force Edge and Sparda were confirmed to use the same grip):

```powershell
python classify.py                       # all of out/
python classify.py --csv report.csv out/DMC1_weapons
```

`contactsheet.py` renders many models onto one labelled page, each normalised
to its most readable silhouette, so you can identify a folder at a glance. It
needs Blender:

```powershell
blender -b -P contactsheet.py -- sheet.png out/DMC1_weapons
blender -b -P contactsheet.py -- parts.png --submesh out/DMC2_players/pl00_gm.obj
```

The sheets behind `WEAPON_LABELS.md` are in `out/sheets/`.

---

## 5. Running the individual scripts

You do **not** need any of this if you just ran `dmcextract.py`. It is here for
picking apart single files or poking at the formats.

| Script | How you run it | What it does |
|---|---|---|
| `dmcextract.py` | `python dmcextract.py` | **the whole pipeline** — start here |
| `classify.py` | `python classify.py` | measures every OBJ and flags the ones that are primitives rather than art |
| `contactsheet.py` | `blender -b -P contactsheet.py -- sheet.png out/DMC1_weapons` | renders a labelled sheet of many models at once |
| `bdp.py` | `python bdp.py <file.BDP>` | prints what's inside a bundle; extracts nothing |
| `extract.py` | `python extract.py [<bundles dir>] [<out dir>]` | bundle → individual game files |
| `dmc2obj.py` | `python dmc2obj.py <game> <pattern>... <outdir>` | DMC1/DMC2 files → OBJ |
| `unpack_all.py` | `python unpack_all.py [<GDATA.AFS dir>] [<out dir>] [<pattern>]` | DMC3 `.PAC` → `.mod` (pattern defaults to `PLWP_*.PAC`; use `EM???.PAC` or `PL???.PAC` for the characters) |
| `modbe2.py` | `python modbe2.py [<unpacked dir>] [<out dir>]` | DMC3 `.mod` → OBJ |
| `dmcmesh.py` | not run directly | shared mesh reader used by `dmc2obj.py` |
| `dmctex.py` | not run directly | shared texture reader � all three games' formats, and the PNG writer |

### `dmc2obj.py` arguments

```
python dmc2obj.py <game> <pattern> [<pattern> ...] <outdir>
```

- `<game>` — `dmc1` or `dmc2`. **Not optional and not guessable**: DMC1 data is
  big-endian, DMC2 little-endian. The wrong one simply finds no meshes.
- `<pattern>` — which files to convert. Wildcards work. **Put quotes around any
  pattern containing `*`** so the shell passes it to Python untouched.
- `<outdir>` — the last argument is always the output folder. Created if missing.

Example — convert just the DMC1 weapons from an existing `build/`:

```powershell
python dmc2obj.py dmc1 "build/extract/DMC1/data/pld/*.pws" myweapons
```

### Keeping the files together

`dmc2obj.py` imports `dmcmesh.py` and `dmctex.py`, `modbe2.py` and
`unpack_all.py` import `dmctex.py`, and `extract.py` imports `bdp.py`. **Keep all
the `.py` files in one folder** or those imports fail.

---

## 6. When something goes wrong

**`python: command not found` / `'python' is not recognized`**
Python isn't installed, or wasn't added to PATH. Reinstall and tick "Add Python
to PATH". On some Linux/macOS systems the command is `python3`.

**`7-Zip was not found`**
Install it from <https://www.7-zip.org/>. On Windows the default install location
is detected automatically; otherwise make sure `7z` is on your PATH.

**It says "No .iso found" but my ISO is right there**
Check the file really ends in `.iso` — Windows hides extensions by default, so
`game.iso.txt` shows up as `game.iso`. Turn on **View → File name extensions**
in Explorer.

**`UnicodeEncodeError: 'charmap' codec can't encode character`**
The Windows console choking on a non-English filename. Run this once in the same
terminal, then try again:

```powershell
$env:PYTHONIOENCODING = "utf-8"
```

**An OBJ opens but looks like a scrambled pile of parts**
Expected for **character models** in all three games. Their meshes are stored in
bone-local space — each body part sits at its own origin, and the skeleton has
not been reverse-engineered, so they cannot be assembled automatically. Move the
parts by hand in Blender; the `obj<NN>` group names tell you what belongs
together. DMC1 weapons and props do not have this problem.

**`ModuleNotFoundError: No module named 'dmcmesh'`**
The `.py` files were separated. Keep them all in one folder.

---

## 7. Known limits

- **No textures.** The models have UV coordinates but no images. Texture decoding
  is not implemented for any of the three games. The raw texture files are pulled
  out into `build/extract/` (DMC1 `.t32`/`.tm2`, DMC2 `.tm2`) if you want to
  attack that.
- **No skeletons and no animation.** Geometry only.
- **DMC2 has no separate weapon files.** Dante's and Lucia's weapons are
  sub-meshes inside `pl*_gm.obj` — `pl00_gm` holds his coat and the Rebellion
  blade. Open it in Blender and pick the parts you want.
- **Mesh discovery is a validated brute-force scan.** It reads the real object
  tables rather than guessing, and every candidate has to survive the vertex
  total and the array packing, so what comes out is geometry the game ships —
  but a file may still yield a mesh or two more or less than it loads at once
  (LODs, damage states and unused objects all live in the same file).
- **Props are what the stage files hold, not a curated list.** DMC1 `.fsd` rooms
  and DMC2 `sobj_*.bin` carry gates, platforms, rings, panels and rigging along
  with flat effect quads. Run `classify.py` over `out/DMC1_props` to separate
  the shaped objects from the billboards.
- **DMC3 has no props here.** Its stage and item archives (`ST*.PAC`, `ID*.PAC`)
  hold `SCM ` scenes and `ipum` images, not the `MOD ` meshes the characters and
  weapons use, and neither format has been read yet.
- **DMC2 stage geometry is out too.** `st*_*.bin` is MOMO with the same object
  records but a 16-byte mesh descriptor whose arrays are implied rather than
  pointed at — a different variant, not yet reversed. Only `sobj_*` props parse.
- **DMC3 costume PACs are skipped.** `PL???_??_?.PAC` carry no geometry of their
  own, so the extractor leaves them on the disc.
- These are PS2-era models — 200–750 vertices for a weapon. They are reference
  geometry, not modern drop-in assets.

---

## 8. Legal

Tools only. No game data is included or distributed here. Use them on a copy of
the game you own. The extracted models remain Capcom's property — keep the
output to personal use.
