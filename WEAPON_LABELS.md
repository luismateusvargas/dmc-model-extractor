# What each extracted model actually is

Identified from geometry, not from guesswork about filenames: every one of the
233 OBJs was measured with `classify.py` and rendered with `contactsheet.py`,
then read off the sheets in `out/sheets/`.

> **This covers the first extraction pass.** The extractor now reads the object
> tables properly and also pulls DMC2 and DMC3 players, enemies and props — 741
> OBJs in total (see the README). The identifications below still hold: the DMC1
> weapons, the DMC3 weapon PACs and the DMC2 characters are the same files, with
> `DMC2_models/` now split into `DMC2_players/` and `DMC2_enemies/`, and the
> character files carrying more meshes each than they did here. Everything added
> since — DMC1 `.fsd` props, DMC2 `sobj_*` props, DMC3 `PL*`/`EM*` — has not been
> named model by model.

Confidence is marked: **certain** (the silhouette is unmistakable),
*likely* (shape and slot both fit, no contradicting evidence), and
`unresolved` (needs someone who knows the game to look).

---

## 1. The headline result: only 35 of the 233 files are weapons

| Group | Files | What they are |
|---|---|---|
| `DMC1_weapons/pw01`-`pw0a` | 10 | **all ten DMC1 weapons**, one per file |
| `DMC3_weapons/PLWP_*_PAC_0N.obj` (short names) | 25 | **DMC3 weapon meshes**, split into parts |
| `DMC3_weapons/PLWP_*_PAC_0N_01_NNN.obj` (long names) | 96 | **not weapons** — a shared VFX library |
| `DMC2_players/pl*_gm` | 8 | weapons are **sub-meshes inside** the player models |
| `DMC1_players`, `DMC1_enemies`, `DMC2_enemies` | 94 | characters, not weapons |

---

## 2. DMC1 — `out/DMC1_weapons/` (sheet: `sheet_dmc1_weapons.png`)

A clean 5 guns + 5 melee split, in ID order.

| File | Size (L x W x T) | Identification | Confidence |
|---|---|---|---|
| `pw01` | 156 x 87 x 15 | **Ebony & Ivory** — an M1911 with the extended slide | certain |
| `pw02` | 325 x 74 x 43 | **Shotgun** — break-action, swept pistol grip, long barrel | certain |
| `pw03` | 488 x 170 x 123 | **Grenadegun** — stock, foregrip loop, box receiver | certain |
| `pw04` | 279 x 114 x 83 | **Nightmare-β** — the only organic, spiked, non-manufactured shape | certain |
| `pw05` | 497 x 269 x 147 | **Needlegun** — stubby body, projectile visible in a square muzzle frame | certain |
| `pw06` | 775 x 202 x 76 | **Force Edge** — straight blade, ornate winged guard | certain |
| `pw07` | 995 x 228 x 30 | **Alastor** — broad swept single-edged blade, bat-wing guard | certain |
| `pw08` | 954 x 561 x 50 | **Sparda** — the huge jagged bat-wing guard | certain |
| `pw09` | 1056 x 222 x 81 | A second large swept blade that **also contains all three of `pw0a`'s meshes** (hilt + blade + scabbard) — reads as Nelo Angelo's set: his broadsword plus Yamato at the hip | *likely* |
| `pw0a` | 604 x 63 x 58 | **Yamato** — plain katana, hilt + blade + scabbard | certain |

**Ifrit is not in `pw*`.** No gauntlet appears in any of the ten files. It is
worn rather than held, so it lives in the player model — `pl03` / `pl06`
(968 x 647 x 202) are a clawed arm/gauntlet set, the best candidate.

Corroborating evidence beyond silhouette, from `classify.py`'s shared-shape
report:

- `pw06` and `pw08` share an identical 17-vert grip mesh → Force Edge and
  Sparda are the same sword, which is exactly the lore relationship.
- `pw09` contains `pw0a` whole. Two files, one weapon inside the other.
- `pw06` and `pw09` share a 29-vert pommel.

`pw03` and `pw05` were the last pair left open — the silhouettes alone could
not say which was the Grenadegun. They are settled now: **`pw03` is the
Grenadegun and `pw05` is the Needlegun.**

## 3. DMC3 — `out/DMC3_weapons/`, short-named files (sheet: `sheet_dmc3_weapons.png`)

Capcom's own PAC names, checked against the geometry. Where a PAC has several
short-named files, they are parts of one weapon.

| File(s) | Identification | Confidence |
|---|---|---|
| `SWORD_PAC_01` | **Rebellion** — ornate crossguard, 164 long | certain |
| `SWORD2_PAC_01` | An ornate sword with a larger guard, 165 long — Sparda / awakened Rebellion | *likely* |
| `SWORD3_PAC_01` | **Force Edge** (byte-identical to `FORCEEDGE_PAC_01`) | certain |
| `FORCEEDGE_PAC_01` | **Force Edge** — straight double-edged blade | certain |
| `2SWORD_PAC_01` | **Agni & Rudra** — curved serrated blade, ornate pommel | certain |
| `NUNCHAKU_PAC_01` + `_02` | **Cerberus** — ring-topped rod, plus the twisted chain section | certain |
| `GUITAR_PAC_01` | **Nevan** — the scythe-guitar | certain |
| `FIGHT_PAC_01` | **Beowulf** — gauntlet and greave plates (4 detached pieces) | certain |
| `NEWVERGILFIGHT_PAC_01` | **Beowulf**, Vergil's (byte-identical to `FIGHT_PAC_01`) | certain |
| `VERGILSWORD_PAC_01` + `_04` | **Yamato** — tsuka (hilt) plus the 115-long blade | certain |
| `NEWVERGILSWORD_PAC_01` + `_04` | **Yamato** (byte-identical to `VERGILSWORD`) | certain |
| `GUN_PAC_01` + `GUN_PAC_02` | **Ebony & Ivory** — the two handguns, same dims, separate files | certain |
| `SHOTGUN_PAC_01` | **Shotgun** | certain |
| `RIFLE_PAC_01` | **Spiral** — 195-long rifle | certain |
| `LASER_PAC_01` | **Artemis** — the winged, splayed-leg launcher | certain |
| `LADYGUN_PAC_01` + `_04` | **Kalina Ann** — launcher with grip and hook, plus the 111-long bayonet | certain |
| `LADYGUN1_PAC_01` | Lady's handgun, 21 long | *likely* |
| `LADYGUN3_PAC_01` | Lady's second sidearm, break-action look, 30 long | *likely* |
| `GRENADE_PAC_01` | **Rebellion** (byte-identical to `SWORD_PAC_01`) — the PAC name does **not** match its contents | certain |
| `NEROSWORD_PAC_01` | A plain forked-tip blade, 155 long. Does not read as Red Queen | `unresolved` |

### Four PACs ship duplicate payloads — and it is not our tooling

Verified: `GDATA.AFS` is a real directory on the PS3 disc, so these are
Capcom's own filenames, and the duplication is in the shipped data.
`mod_files/*/01.mod` md5s:

| Same payload | Note |
|---|---|
| `SWORD_PAC` = `GRENADE_PAC` | Rebellion's mesh under Kalina Ann's name. Kalina Ann is really in `LADYGUN_PAC`, so `GRENADE_PAC` is a dead slot. |
| `SWORD3_PAC` = `FORCEEDGE_PAC` | Force Edge twice. |
| `FIGHT_PAC` = `NEWVERGILFIGHT_PAC` | Legitimate — Dante and Vergil both wield Beowulf. |
| `VERGILSWORD_PAC` = `NEWVERGILSWORD_PAC` | Legitimate — same Yamato in both Vergil PACs. |

The containers still differ (different entry counts and offset tables); only
the mesh payloads coincide.

## 4. The 96 long-named DMC3 files are a VFX library (sheet: `sheet_dmc3_vfx.png`)

**This is the answer to "why are so many of these circles and squares".**
They are not bugged, not attachment helpers, and not weapon parts. They are
the additive-blended effect geometry each PAC embeds a copy of:

| Shape on the sheet | What it is in game |
|---|---|
| Crescent "C" arcs | sword slash trails |
| Rings / tori | shockwaves, impact rings |
| Flat rectangles and squares | billboard sprites — muzzle flash, beams, glows |
| Cones and triangles | thrust / burst cones |
| Zigzag ribbons | lightning (Nevan, Cerberus) |
| Spheres and icospheres | glow orbs, charge balls |
| Spiky starbursts | hit sparks |

`classify.py`'s shared-shape report proves they are a *library*: the same
60-unit sphere (86 verts / 168 tris) appears in `FIGHT`, `GUITAR`, `GUN`,
`LADYGUN`, `LASER`, `RIFLE`, `SHOTGUN`, `VERGILSWORD` and
`NEWVERGILSWORD` — nine unrelated weapons. Likewise one 42-vert cone is in
eleven PACs. Weapon parts are never shared between unrelated weapons; effects
always are.

**These are exactly the case where a texture changes the meaning of a default
primitive.** A quad is a muzzle flash only once its additive alpha texture is
on it; the geometry carries none of the information. So texture decoding
matters for *these* files and is not needed to identify any of the 35 weapons.

## 5. DMC2 — weapons live inside the player models

Confirmed: there are no separate DMC2 weapon files. Sheets
`sheet_dmc2_dante_parts.png` and `sheet_dmc2_lucia_parts.png` explode the two
player models mesh by mesh.

**`pl00_gm` — Dante** (also `pl04_gm`, `pl06_gm`; all three share the same
part set):

| Mesh | What it is |
|---|---|
| `mesh00`-`mesh05` | coat tails and hems |
| `mesh06` | flat pierced plate (belt / decal) |
| `mesh07` | hair |
| `mesh08`, `mesh09` | bat-wing collar pieces, 256 long |
| `mesh12`, `mesh14` | **Ebony & Ivory** — the handgun pair |
| `mesh13`, `mesh15` | slide / barrel parts |
| `mesh16` | a second sidearm (revolver-like) |
| `mesh20` | **submachine gun** |
| `mesh22` | **Rebellion** — 204-long straight sword with crossguard |
| `mesh23`, `mesh24` | two further blades (134 and 174 long) |
| `mesh17`, `mesh18`, `mesh25` | barrel / rod / tube parts |
| `mesh21` | flat plane (effect or decal) |

**`pl01_gm` — Lucia** (also `pl03_gm`, `pl05_gm`, `pl07_gm`):

| Mesh | What it is |
|---|---|
| `mesh02`-`mesh04` | feathered Devil Trigger wings, 435-453 long |
| `mesh07` | curved 99-long blade — one of the **Cutlaseer** daggers |
| `mesh09` | **a bundle of seven throwing daggers** |
| `mesh13`-`mesh16` | single daggers and needles |
| `mesh20` | a fan of blades |
| `mesh01` | flat 135 x 63 x 0 sheet — effect plane, not a weapon |

`em39_gm_mesh10` is shared with `pl01_gm_mesh05`, so at least one prop is
reused between Lucia and an enemy.

## 6. Genuine junk and genuine gaps

Of 1384 meshes, 196 are primitives. Almost all are effect geometry on enemies
(67 flat planes in `DMC1_enemies` alone). The ones worth acting on:

**Four DMC2 enemy files yield nothing at all.** `em00_gm`, `em46_gm`,
`em52_gm` and `em53_gm` each contain one single 16 x 3 x 1 flat quad — the
*same* quad in all four. These should be real enemy models. This is a mesh-scan
miss in the DMC2 reader, not game data, and is the one open extractor bug the
labelling pass turned up. `build/` was deleted, so re-running
`dmcextract.py` is needed to dig into it.

**Two more DMC2 files are single primitives** and may be legitimate:
`em09_gm` is one flat pentagon plane, `em51_gm` is a 73-unit faceted sphere
(an effect ball).

**Engine volumes, not art.** A handful of meshes have exactly round
dimensions, which no artist produces: `NEWVERGILSWORD_07_01_207` and
`VERGILSWORD_07_01_207` are 200 x 100 x 50; `em00_mesh39/40` and
`em1b_mesh27/28` are 1000 x 1000 x 500. Treat these as collision or bounding
hulls and skip them.

**Clean bill of health for the weapons.** Across all 35 weapon files the only
primitive-flagged meshes are `pw04_mesh01` (an 8-vert box — a real barrel
band) and `pw09_mesh01` (an 8-sided 688-long tube — a real blade spine).
Nothing in any weapon file is a placeholder.

---

## Reproducing this

```powershell
python classify.py --csv mesh_report.csv          # measure all 233, list the primitives
blender -b -P contactsheet.py -- sheet.png out/DMC1_weapons
blender -b -P contactsheet.py -- parts.png --submesh out/DMC2_players/pl00_gm.obj
```
