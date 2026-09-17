"""Render a labelled contact sheet of extracted OBJ models, for identifying
which weapon each file actually is.

Every model is normalised the same way -- longest axis across the page, thinnest
axis into the camera -- so each tile shows the most readable silhouette, and the
real dimensions are printed under it. Orthographic Workbench render, no
materials needed, so it works on the raw untextured OBJs.

Run it through Blender (it needs bpy):

    blender --background --python contactsheet.py -- <out.png> <obj or dir>...
    blender -b -P contactsheet.py -- sheet.png out/DMC1_weapons
    blender -b -P contactsheet.py -- sheet.png --cols 10 "out/DMC3_weapons/*.obj"

Options (before or after the paths):
    --cols N     tiles per row (default: about square)
    --ppu N      pixels per grid unit, i.e. resolution (default 210)
    --submesh    one tile per mesh inside each OBJ, not one per file --
                 use it on DMC1/DMC2 files, where each part is its own mesh
    --no-label   omit the captions
"""

import glob
import math
import os
import sys

import bpy
from mathutils import Vector

CELL = 1.0          # every model is scaled to this size
GAP_X = 1.25
GAP_Z = 1.45


def wipe():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for blk in (bpy.data.meshes, bpy.data.curves, bpy.data.cameras,
                bpy.data.materials, bpy.data.objects):
        for x in list(blk):
            if x.users == 0:
                blk.remove(x)


def import_parts(path):
    """-> the OBJ's objects, untouched. DMC1/DMC2 files hold one mesh per
    weapon part, which is what you want to see separately."""
    before = set(bpy.data.objects)
    bpy.ops.wm.obj_import(filepath=path, forward_axis="Y", up_axis="Z")
    return [o for o in bpy.data.objects
            if o not in before and o.type == "MESH"]


def import_obj(path):
    meshes = import_parts(path)
    if not meshes:
        return None
    for o in bpy.data.objects:
        o.select_set(False)
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    return bpy.context.view_layer.objects.active


def normalise(ob):
    """Longest axis -> X, shortest -> Y (into the camera), scaled to CELL.
    Returns the true dimensions, longest first."""
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    me = ob.data
    lo = Vector([min(v.co[i] for v in me.vertices) for i in range(3)])
    hi = Vector([max(v.co[i] for v in me.vertices) for i in range(3)])
    dim = hi - lo
    order = sorted(range(3), key=lambda i: -dim[i])     # long, mid, short
    mid = (hi + lo) * 0.5
    s = CELL / (max(dim) or 1.0)
    for v in me.vertices:
        c = v.co - mid
        v.co = Vector((c[order[0]] * s, c[order[2]] * s, c[order[1]] * s))
    me.update()
    return [dim[i] for i in order]


def caption(text, x, z, size=0.062):
    cu = bpy.data.curves.new(type="FONT", name="cap")
    cu.body = text
    cu.align_x = "CENTER"
    cu.size = size
    ob = bpy.data.objects.new("cap", cu)
    bpy.context.collection.objects.link(ob)
    ob.rotation_euler = (math.radians(90), 0, 0)
    ob.location = (x, 0, z)
    return ob


def shorten(name):
    return (name.replace("PLWP_", "").replace("_PAC", "")
                .replace("unpacked_", ""))


def sheet(files, out_png, cols=None, ppu=210, labels=True, submesh=False):
    wipe()
    if not files:
        raise SystemExit("no OBJ files given")

    # One tile per file, or -- with submesh -- one tile per mesh inside them.
    tiles = []
    for path in files:
        name = os.path.splitext(os.path.basename(path))[0]
        if submesh:
            parts = import_parts(path)
            if not parts:
                tiles.append((None, name))
            for p in parts:
                tiles.append((p, p.name))
        else:
            tiles.append((import_obj(path), name))

    if not cols:
        cols = max(1, int(round(math.sqrt(len(tiles)) * 1.1)))
    rows = (len(tiles) + cols - 1) // cols

    for n, (ob, name) in enumerate(tiles):
        x, z = (n % cols) * GAP_X, -(n // cols) * GAP_Z
        if ob is None or not ob.data.vertices:
            caption("(empty) " + shorten(name), x, z)
            continue
        for o in bpy.data.objects:
            o.select_set(False)
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        dim = normalise(ob)
        ob.location = (x, 0, z)
        if labels:
            caption("%s  %d x %d x %d" % (shorten(name), dim[0], dim[1],
                                          dim[2]), x, z - CELL * 0.62)

    print("contactsheet: %d tiles from %d file(s)" % (len(tiles), len(files)))
    w = (cols - 1) * GAP_X + CELL * 1.3
    h = (rows - 1) * GAP_Z + CELL * 1.5
    cam_data = bpy.data.cameras.new("cam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = max(w, h)
    cam = bpy.data.objects.new("cam", cam_data)
    bpy.context.collection.objects.link(cam)
    cam.location = ((cols - 1) * GAP_X / 2, -20,
                    -(rows - 1) * GAP_Z / 2 - 0.1)
    cam.rotation_euler = (math.radians(90), 0, 0)

    sc = bpy.context.scene
    sc.camera = cam
    try:
        sc.render.engine = "BLENDER_WORKBENCH"
    except TypeError as exc:                # engine not available in this build
        print("contactsheet: keeping", sc.render.engine, "--", exc)
    sh = sc.display.shading
    sh.light = "STUDIO"
    sh.color_type = "SINGLE"
    sh.single_color = (0.62, 0.64, 0.68)
    sh.show_cavity = True
    sh.show_object_outline = True
    sh.background_type = "VIEWPORT"
    sh.background_color = (1.0, 1.0, 1.0)

    sc.render.resolution_x = min(int(w * ppu), 2400)
    sc.render.resolution_y = min(int(h * ppu), 2400)
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = out_png
    bpy.ops.render.render(write_still=True)
    print("contactsheet: -> %s (%dx%d)"
          % (out_png, sc.render.resolution_x, sc.render.resolution_y))
    return out_png


def collect(args):
    out = []
    for a in args:
        if os.path.isdir(a):
            out += sorted(glob.glob(os.path.join(a, "*.obj")))
        else:
            hits = sorted(glob.glob(a))
            out += hits if hits else [a]
    return out


def main(argv):
    cols, ppu, labels, submesh, rest = None, 210, True, False, []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--cols":
            cols = int(argv[i + 1]); i += 2
        elif a == "--ppu":
            ppu = int(argv[i + 1]); i += 2
        elif a == "--no-label":
            labels = False; i += 1
        elif a == "--submesh":
            submesh = True; i += 1
        else:
            rest.append(a); i += 1
    if len(rest) < 2:
        print(__doc__)
        return 1
    sheet(collect(rest[1:]), rest[0], cols, ppu, labels, submesh)
    return 0


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    sys.exit(main(args))
