# DMC Model Extractor

Pulls the 3D models out of **Devil May Cry HD Collection (PS3)** and writes them
as textured `.obj` files you can open in Blender. DMC2's and DMC3's characters
also come out **rigged and animated**, as `.glb` files with every motion the game
ships for them.

You drop your disc image into the `iso/` folder and run **one command**.

| Game | weapons | players | enemies | props |
|---|---|---|---|---|
| DMC1 | 10 | 5 | 58 | 99 |
| DMC2 | *(inside the players)* | 8 | 51 | 26 |
| DMC3 | 143 | 49 | 367 | *(format not read)* |

**816 OBJ files in all**, with **1,893 PNG textures** — 813 of the 816 open
already textured.

**313 rigged, animated models** on top of that — 46 from DMC1 (leg IK solved),
102 from DMC2, 59 DMC2 cutscene actors and 106 from DMC3 — carrying **21,144
animations** between them (see [section 5](#5-animations)).

The file formats are undocumented — no public spec, and no Noesis or Blender
plugin exists for DMC1/DMC2. They were reverse-engineered for this repo. Format
notes are in the comments at the top of `bdp.py`, `dmcmesh.py`, `modbe2.py` and
`dmctex.py` — the last one covers all three games' texture containers — and, for
skeletons and motions, `dmc3anim.py` and `dmc12anim.py`.

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

[1/5] Reading the ISO (this takes a few minutes, ~4.6 GB)
[2/5] Unpacking the DMC1 and DMC2 bundles
[3/5] Converting DMC1 and DMC2 to OBJ
OK   pw08             meshes=  3 verts=   376 tris=   236 nrmlen=1.0000 tex=1
...
[4/5] Unpacking and converting DMC3
...
[5/5] Rigging and animating the characters
OK   em00_gm              bones=26 meshes=  7 anims=  89
OK   PL000_PAC_01                 bones=24 meshes= 17 anims= 477

Done. OBJ files written to ...\out:
   DMC1_enemies       58 obj    269 png
   DMC1_players        5 obj     21 png
   DMC1_props         99 obj    292 png
   DMC1_weapons       10 obj     10 png
   DMC2_enemies       51 obj    282 png
   DMC2_players        8 obj    185 png
   DMC2_props         26 obj    181 png
   DMC3_enemies      367 obj    435 png
   DMC3_players       49 obj     74 png
   DMC3_weapons      143 obj    144 png
   DMC1_animated      46 glb  (rigged, with their animations)
   DMC2_animated     102 glb  (rigged, with their animations)
   DMC2_cutscenes     59 glb  (rigged, with their animations)
   DMC3_animated     106 glb  (rigged, with their animations)
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
├── DMC3_enemies/     EM000_PAC_01.obj ...
├── DMC2_animated/    em00_gm.glb, pl00_gm_s00.glb ...   <- rigged + animated
└── DMC3_animated/    DMC3_players/PL000_PAC_01.glb ...  <- rigged + animated
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
> almost every file is exact. A dozen land between 0.92 and 0.99 — PS2-era
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
  look like Blender primitives. Their textures are extracted too, which is what
  makes them readable: the geometry is just the quad the effect is painted on.
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

### How the textures were read

Each game keeps its images in the model file itself, in its own container, and
none of the three is documented. Full notes are at the top of `dmctex.py`; the
short version:

| Game | Where | Container | Pixels |
|---|---|---|---|
| DMC1 | inside `.pld` / `.pws` / `.pwd` / `.emd` / `.fsd` | Pipeworks `T32`/`TM2`, big-endian, magic stored word-reversed | DXT1, DXT5 or ARGB8888 |
| DMC2 | inside `.mdl` / `.mdz` | stock PS2 TIM2, one picture per block, grouped by MOMO section | PSMT8 with a 256-entry CSM1 palette, mostly |
| DMC3 | entry 0 of each model `.PAC` | big-endian size table in 2 KiB units | DXT1 or DXT5, **every block's 32-bit words rotated by one** |

Three things worth knowing, because each one costs an afternoon if you meet it
cold:

- **The HD port re-encoded DMC1 and DMC3 to DXT at twice the PS2 resolution.**
  The DMC3 header carries the original size alongside the stored one; the UVs
  are normalised, so the extra resolution is free.
- **DMC3's DXT blocks are word-rotated.** Read straight, they decode to
  plausible-looking noise rather than to nothing, which is the trap.
- **There are no textures in `ipum` blocks.** That magic turns up only in
  `ID55??.PAC` — those are PS2 IPU video streams, not art.

Pairing a mesh to its image is its own problem, since a `texIndex` counts from
zero inside whichever container the mesh belongs to. Textures follow the
geometry that uses them, so meshes are grouped by which container comes next
and the **group** picks a container big enough to hold every slot it asks for.
That last part matters: a DMC1 enemy drops one- and four-image containers
(damage states) between a body and the nine-image container the body actually
indexes into. 737 of the 741 models pair cleanly.

---

## 5. Animations

All three games' characters come out a second time as **glTF binary (`.glb`)**:
the textured mesh, bound to its skeleton with the game's own skin weights, plus
every motion that belongs to it as a named animation.

```
out/DMC1_animated/            pl00_s00.glb (Dante, 215), em00.glb ...
out/DMC2_animated/            em00_gm.glb, pl00_gm_s00.glb ...
out/DMC2_cutscenes/           edm_000_s00.glb ... (cutscene actors, see below)
out/DMC3_animated/
├── DMC3_players/             PL000_PAC_01.glb  (Dante, 477 animations) ...
├── DMC3_enemies/             EM000_PAC_01.glb ...
└── DMC3_weapons/             PLWP_NUNCHAKU_PAC_01.glb ...
```

### Opening one in Blender

1. **Set the frame rate first:** *Output Properties → Format → Frame Rate → 60*.
   The motions are keyed at 60 fps, the games' frame rate. Blender converts glTF
   seconds into frames at the scene's rate, so at the default 24 they still play
   at the right speed, but the keys land between frames.
2. *File → Import → glTF 2.0* and pick the `.glb`.
3. Every motion arrives as an Action. Pick one in the *Action Editor* (Dope Sheet
   → Action Editor, armature selected) or the *NLA Editor*, and press play.

Any engine or tool that reads glTF works the same way.

### Where the motions came from, and how they were paired

- **DMC3** keeps a character's motions *inside its own model PAC*, as `MOT`
  entries in the nested sub-PACs (they unpack as `NN.bin`). Players carry most
  of theirs in the `PL???_??_?.PAC` files next to the model — which the
  extractor used to skip as "costumes". A motion belongs to a model when its
  bone count matches the model's skeleton. A few bodies have one extra bone the
  motions don't drive (EM000, EM006, EM010), so a model also takes the motions
  one bone smaller when no other model in the PAC has that size, or when nothing
  matches it exactly.
- **DMC2** keeps them in a companion file: `em00_gm.mdl` → `em00_gm.dat`. A
  DMC2 model file holds several sub-models (`_s00`, `_s03`...), and each gets
  the motions whose bone count matches it.
  The costumes (`pl03`..`pl07`) ship without a `.dat`; each borrows the bank
  of the player whose skeleton it matches (`pl04`/`pl06` Dante's,
  `pl03`/`pl05`/`pl07` Lucia's).
- **DMC2 cutscenes** are in `edm_NNN_3.bin` (actors) and `edm_NNN_4.bin` (their
  motions, float-keyed). The motions are listed actor by actor in model order,
  and the same actor appears in many cutscenes, so identical actors are merged
  into one `.glb` carrying every cutscene's motions, named `e000_017`
  (cutscene 000, motion section 17). Positions are in scene space.
- **DMC1** keeps them in the model file itself: section 6 (body) and 7 (coat)
  of `pl00.pld`, sections 3 and 5 of an enemy's `.emd`. Dante's Devil Trigger
  bodies (`pl01`, `pl03`, `pl06`) and `pl05` have none of their own and get
  `pl00`'s 215. DMC1 animates legs by **IK**: a motion stores a target position
  and a knee hinge axis, not hip/knee rotations. `dmc1anim.py` solves them back
  into rotations (two-segment chains, law of cosines in the hinge plane), so
  the `.glb` is plain forward kinematics that any tool plays. Its docstring
  has the format.

Animation names say where each motion lives: `02_05` is entry 5 of sub-PAC 02
inside the model's own PAC, `PL000_00_3_07` is entry 7 of `PL000_00_3.PAC`, and
DMC2's `motion_012` is entry 12 of the `.dat`, and DMC1's `bank6_012` is
motion 12 of section 6. The games give them no names.

**Hair and coats are merged in.** The games keep a character's hair, coat tails
and scarf as separate little models with their own physics skeleton, hung on a
body bone at run time; no body motion drives them, so they used to be left out
(bald heads, no coats). `dmcattach.py` now merges them into the body `.glb`:
DMC3 Dante's and Vergil's coats and Lady's hair (the second `.mod` in the PAC),
DMC2 Dante's hair and coat tails, Lucia's hair and scarf, Trish's hair (and the
costumes). Each part vertex is skinned like its nearest body vertices, so coats
swing with the legs and hair turns with the head; the cloth simulation itself
isn't reproduced.

Root motion is kept: a walk or dash really travels. Bones a motion does not
touch stay in their bind pose.

### What pairing by bone count can't know

Where several models in one PAC share a skeleton size — enemy variants, a
character's alternate forms — each gets the whole set. That is right for
variants (they are built to share motions) but it means a model can carry a few
motions meant for its sibling. DMC3's weapon GLBs animate only the weapon's own
bones (the nunchaku has 11, Nevan 6); how a weapon moves in Dante's hand is his
motion, not the weapon's.

---

## 6. Running the individual scripts

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
| `dmc3anim.py` | `python dmc3anim.py [<unpacked dir>] [<GDATA.AFS dir>] [<out dir>] [<pattern>]` | DMC3 models + skeletons + `MOT` motions → animated `.glb` (pattern like `PL000` or `EM0*`) |
| `dmc12anim.py` | `python dmc12anim.py dmc2 <extract/DMC2/data dir> <out dir> [<pattern>]` | DMC2 `.mdl` + `.dat` → animated `.glb` (pattern like `em00_gm`) |
| `dmc12anim.py` | `python dmc12anim.py dmc2events <extract/DMC2/data dir> <out dir> [<event>]` | DMC2 cutscene actors + motions → animated `.glb` |
| `dmc1anim.py` | `python dmc1anim.py <extract/DMC1/data dir> <out dir> [<pattern>]` | DMC1 `.pld`/`.emd` + IK solve → animated `.glb` (pattern like `pl00` or `em0*`) |
| `dmcmesh.py` | not run directly | shared mesh reader used by `dmc2obj.py` |
| `dmctex.py` | not run directly | shared texture reader — all three games' formats, and the PNG writer |

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
`unpack_all.py` import `dmctex.py`, `dmc3anim.py` imports `modbe2.py`,
`dmc12anim.py` imports `dmc3anim.py` and `dmcmesh.py`, and `extract.py` imports
`bdp.py`. **Keep all the `.py` files in one folder** or those imports fail.

---

## 7. When something goes wrong

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

**An OBJ opens with extra parts piled at the origin**
The body itself is assembled — every game stores it in its bind pose — but a
character file also carries other sub-models: held weapons, effect meshes,
alternate heads and damage states. Many of those sit at the origin. Hide them
with the `obj<NN>` groups in the outliner, or open the `.glb` in
`DMC2_animated`/`DMC3_animated` instead, where each skeleton gets its own file.

**An animated `.glb`'s keys fall between frames**
The scene was at 24 fps when it was imported. Timing is still right, but set
the scene to 60 fps *before* importing to get one key per frame (see
[section 5](#5-animations)).

**`ModuleNotFoundError: No module named 'dmcmesh'`**
The `.py` files were separated. Keep them all in one folder.

---

## 8. Known limits

- **DMC1 Trish (`em24`) has no hair.** Her hair is in none of the DMC1 files
  the extractor reads. (DMC2 Trish, `pl02_gm`, is complete.)
- **DMC1 Dante (`pl00`) carries the Ifrit gauntlets** as body parts 21 and 22;
  hide them in the catalog, which does so by default.
- **DMC1's IK is solved offline.** Unreachable targets straighten the leg
  towards them (jumps and falls), and one extra rotation channel per motion,
  which does not fit the body as a root rotation, is left out.
- **The skeleton comes without bone names.** The games don't store any; bones
  are `bone00`, `bone01`... in hierarchy order.
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
- These are PS2-era models — 200–750 vertices for a weapon. They are reference
  geometry, not modern drop-in assets.

---

## 9. Legal

Tools only. No game data is included or distributed here. Use them on a copy of
the game you own. The extracted models remain Capcom's property — keep the
output to personal use.
