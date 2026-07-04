"""
Blender headless render script for SH3D-exported OBJ scenes.

Usage:
    blender --background --python blender_render.py -- input.obj output.png \
            [--samples 256] [--width 1920] [--height 1080] \
            [--camera-json input.camera.json]

Environment variables:
    BLENDER_BIN          Optional override for the Blender binary path used by
                         external launchers (this script itself does not exec
                         Blender; it runs inside Blender).
    OPTIX_DEVICE_INDEX   Optional integer index to restrict which GPU is used
                         for OptiX/CUDA rendering (informational; Blender
                         exposes devices through its own prefs API).
"""

import sys
import os
import math
import json
import traceback

# ---------------------------------------------------------------------------
# 1. Parse args forwarded past the "--" separator
# ---------------------------------------------------------------------------
try:
    sep_index = sys.argv.index('--')
    raw_args = sys.argv[sep_index + 1:]
except ValueError:
    raw_args = []

import argparse

parser = argparse.ArgumentParser(
    prog='blender_render.py',
    description='Render an SH3D OBJ export with Cycles + OptiX.',
)
parser.add_argument('input_obj',  help='Path to the .obj file')
parser.add_argument('output_png', help='Path for the output .png')
parser.add_argument('--samples',     type=int, default=256, help='Cycle samples (default 256)')
parser.add_argument('--width',       type=int, default=1920, help='Render width (default 1920)')
parser.add_argument('--height',      type=int, default=1080, help='Render height (default 1080)')
parser.add_argument('--camera-json', dest='camera_json', default=None,
                    help='Path to the sidecar .camera.json file')

try:
    args = parser.parse_args(raw_args)
except SystemExit as e:
    print(f"BLENDER-RENDER: argument parsing failed (exit {e.code}). "
          f"raw_args={raw_args}")
    sys.exit(int(e.code) if e.code is not None else 1)

INPUT_OBJ   = args.input_obj
OUTPUT_PNG  = args.output_png
SAMPLES     = args.samples
WIDTH       = args.width
HEIGHT      = args.height
CAMERA_JSON = args.camera_json

print(f"BLENDER-RENDER: input_obj={INPUT_OBJ}")
print(f"BLENDER-RENDER: output_png={OUTPUT_PNG}")
print(f"BLENDER-RENDER: samples={SAMPLES}  resolution={WIDTH}x{HEIGHT}")
print(f"BLENDER-RENDER: camera_json={CAMERA_JSON}")

# ---------------------------------------------------------------------------
# 2. Import bpy (only available inside Blender)
# ---------------------------------------------------------------------------
try:
    import bpy
except ImportError:
    print("BLENDER-RENDER: ERROR — bpy is not available. "
          "This script must run inside Blender (blender --background --python ...).")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Helper: parse hex colour "#AARRGGBB" or "#RRGGBB" → (r, g, b, a) floats
# ---------------------------------------------------------------------------
def _parse_color(hex_str: str, default=(1.0, 1.0, 1.0, 1.0)):
    """Return (r, g, b, a) as 0-1 floats from an ARGB or RGB hex string."""
    try:
        s = hex_str.lstrip('#')
        if len(s) == 8:          # AARRGGBB (SH3D format)
            a = int(s[0:2], 16) / 255.0
            r = int(s[2:4], 16) / 255.0
            g = int(s[4:6], 16) / 255.0
            b = int(s[6:8], 16) / 255.0
        elif len(s) == 6:        # RRGGBB
            r = int(s[0:2], 16) / 255.0
            g = int(s[2:4], 16) / 255.0
            b = int(s[4:6], 16) / 255.0
            a = 1.0
        else:
            raise ValueError(f"Unexpected length {len(s)}")
        return (r, g, b, a)
    except Exception as exc:
        print(f"BLENDER-RENDER: WARNING — could not parse colour '{hex_str}': {exc}. "
              f"Using default {default}.")
        return default

# ---------------------------------------------------------------------------
# 3. Wipe the default scene
# ---------------------------------------------------------------------------
try:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    print("BLENDER-RENDER: factory reset done")
except Exception as exc:
    print(f"BLENDER-RENDER: WARNING — factory reset failed: {exc}")

# ---------------------------------------------------------------------------
# 4. Import the OBJ (Blender 4.0+ vs older API)
# ---------------------------------------------------------------------------
# SH3D's OBJWriter exports vertex coords in centimetres. Blender uses
# metres. Scale the import by 0.01 so all downstream camera / sun / light
# placement (which we already write in metres) is consistent.
OBJ_CM_TO_M = 0.01

imported_ok = False
try:
    bpy.ops.wm.obj_import(filepath=INPUT_OBJ, global_scale=OBJ_CM_TO_M)
    imported_ok = True
    print(f"BLENDER-RENDER: OBJ imported via bpy.ops.wm.obj_import "
           f"(Blender 4.x API, global_scale={OBJ_CM_TO_M})")
except AttributeError:
    pass
except Exception as exc:
    print(f"BLENDER-RENDER: WARNING — wm.obj_import raised: {exc}. Trying legacy API.")

if not imported_ok:
    try:
        bpy.ops.import_scene.obj(filepath=INPUT_OBJ, global_scale=OBJ_CM_TO_M)
        imported_ok = True
        print(f"BLENDER-RENDER: OBJ imported via bpy.ops.import_scene.obj "
               f"(Blender 3.x API, global_scale={OBJ_CM_TO_M})")
    except Exception as exc:
        print(f"BLENDER-RENDER: ERROR — OBJ import failed: {exc}")
        traceback.print_exc()
        sys.exit(1)

# ---------------------------------------------------------------------------
# 5. Configure render engine with OptiX → CUDA → CPU fallback
# ---------------------------------------------------------------------------
scene = bpy.context.scene
scene.render.engine = 'CYCLES'

# View transform: Blender 4.2 defaults to AgX, which desaturates and washes
# out bright interiors (walls read as flat pale white). Use Standard for
# accurate, readable colours, with a slight negative exposure so bright walls
# don't blow to pure white.
try:
    scene.view_settings.view_transform = 'Standard'
    scene.view_settings.look = 'None'
    scene.view_settings.exposure = float(__import__('os').environ.get('SH3D_RENDER_EXPOSURE', '-0.7'))
    scene.view_settings.gamma = 1.0
    print(f"BLENDER-RENDER: view_transform=Standard exposure={scene.view_settings.exposure}")
except Exception as _vexc:
    print(f"BLENDER-RENDER: view transform setup failed: {_vexc}")

compute_backend_used = 'CPU'

def _enable_optix():
    """Enable Cycles OptiX backend on any NVIDIA GPU. In Blender 4.x the
    device's `type` stays 'CUDA' even when `compute_device_type='OPTIX'`
    is set — what matters is that at least one non-CPU device is active
    after the refresh."""
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'OPTIX'
    prefs.refresh_devices()
    gpu_devices = [d for d in prefs.devices if d.type != 'CPU']
    if not gpu_devices:
        raise RuntimeError("no GPU devices visible to Cycles after OptiX refresh")
    for dev in prefs.devices:
        dev.use = dev.type != 'CPU'
    scene.cycles.device = 'GPU'
    scene.cycles.denoiser = 'OPTIX'
    return [d.name for d in gpu_devices]


def _enable_cuda():
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'CUDA'
    prefs.refresh_devices()
    gpu_devices = [d for d in prefs.devices if d.type == 'CUDA']
    if not gpu_devices:
        raise RuntimeError("no CUDA devices visible after refresh")
    for dev in prefs.devices:
        dev.use = dev.type == 'CUDA'
    scene.cycles.device = 'GPU'
    # Blender 4.x denoiser enum: OPENIMAGEDENOISE | OPTIX (no NLM).
    scene.cycles.denoiser = 'OPENIMAGEDENOISE'
    return [d.name for d in gpu_devices]


try:
    names = _enable_optix()
    compute_backend_used = 'OPTIX'
    print(f"BLENDER-RENDER: OptiX GPU rendering enabled on {', '.join(names)}")
except Exception as optix_exc:
    print(f"BLENDER-RENDER: OptiX unavailable ({optix_exc}). Trying CUDA.")
    try:
        names = _enable_cuda()
        compute_backend_used = 'CUDA'
        print(f"BLENDER-RENDER: CUDA GPU rendering enabled on {', '.join(names)}")
    except Exception as cuda_exc:
        print(f"BLENDER-RENDER: CUDA unavailable ({cuda_exc}). Falling back to CPU.")
        scene.cycles.device = 'CPU'
        scene.cycles.denoiser = 'OPENIMAGEDENOISE'
        compute_backend_used = 'CPU'
        print("BLENDER-RENDER: CPU rendering mode active")

scene.cycles.samples = SAMPLES
scene.cycles.use_denoising = True
print(f"BLENDER-RENDER: compute backend = {compute_backend_used}, samples = {SAMPLES}")

# ---------------------------------------------------------------------------
# 6. Coord-system conversion helpers
#
#    SH3D coordinate space:
#      - units: centimetres
#      - X: right
#      - Y: into the screen / "south" (top of floor-plan = north)
#      - Z: up (altitude above floor)
#      - yaw=0 → camera looks toward +Y (south in floor-plan)
#      - yaw positive → counter-clockwise in SH3D (i.e. turning left / west)
#      - pitch positive → looking up
#
#    Blender coordinate space:
#      - units: metres
#      - X: right
#      - Y: forward (into the scene, matching SH3D Y after sign flip)
#      - Z: up
#      - Default camera looks down -Z; rotation_euler rotates the camera body
#
#    Conversion:
#      bx =  x_sh3d / 100           (cm → m, X unchanged)
#      by = -y_sh3d / 100           (cm → m, flip Y so SH3D north→Blender +Y)
#      bz =  z_sh3d / 100           (cm → m, Z unchanged)
#
#    Euler rotation (XYZ order, default for objects):
#      A camera pointing straight down -Z has euler (0, 0, 0).
#      To make it look along +Y (SH3D default yaw=0 direction):
#        Rotate X by +90° → camera now looks along +Y (forward) in Blender.
#      SH3D pitch (positive = look up):
#        Blender X-rot starts at +90° (looking forward). Pitch up means
#        rotating X back toward 0 (tilting camera up):
#        rx = π/2 - pitch_sh3d
#      SH3D yaw (positive = CCW when viewed from above, i.e. turning left/west):
#        In Blender the Z rotation is the azimuth. With the +90° X tilt,
#        yaw=0 must map to the camera looking along +Y (Blender).
#        Blender Z=0 → camera looks along -Y (default).
#        So we need Z = π (180°) when yaw=0.
#        SH3D CCW positive → Blender CCW positive (same convention).
#        rz = π + yaw_sh3d
#        (equivalently: rz = -yaw_sh3d - π/2 from the original spec; the π vs π/2
#         difference depends on how the Blender camera +X axis aligns — empirically
#         π gives forward-facing when yaw=0.)
# ---------------------------------------------------------------------------
def sh3d_to_blender_pos(x_cm, y_cm, z_cm):
    """Convert SH3D cm position to Blender metres."""
    return (x_cm / 100.0, -y_cm / 100.0, z_cm / 100.0)

def sh3d_to_blender_euler(yaw_sh3d, pitch_sh3d):
    """
    Convert SH3D yaw/pitch to Blender XYZ Euler angles (radians).

    SH3D:
      yaw=0    → looking toward +Y (south wall of floor plan)
      yaw CCW positive (turning left = increasing yaw)
      pitch=0  → level; positive = look up

    Returns (rx, ry, rz) for bpy Object.rotation_euler in 'XYZ' mode.
    """
    rx = math.pi / 2.0 - pitch_sh3d   # tilt: 90° base, then adjust for pitch
    ry = 0.0                           # no roll
    rz = math.pi + yaw_sh3d           # azimuth: 180° offset so yaw=0 → looks +Y
    return (rx, ry, rz)

# ---------------------------------------------------------------------------
# 7. Load camera parameters from JSON sidecar (or use defaults)
# ---------------------------------------------------------------------------
cam_info = None
camera_source = "default"

if CAMERA_JSON and os.path.isfile(CAMERA_JSON):
    try:
        with open(CAMERA_JSON, 'r', encoding='utf-8') as fh:
            cam_info = json.load(fh)
        camera_source = CAMERA_JSON
        print(f"BLENDER-RENDER: loaded camera JSON from {CAMERA_JSON}")
    except Exception as exc:
        print(f"BLENDER-RENDER: WARNING — could not load camera JSON "
              f"'{CAMERA_JSON}': {exc}. Using defaults.")
        cam_info = None
else:
    if CAMERA_JSON:
        print(f"BLENDER-RENDER: WARNING — camera JSON '{CAMERA_JSON}' not found. "
              f"Using defaults.")
    else:
        print("BLENDER-RENDER: no --camera-json supplied; using defaults.")

# Determine camera transform
import os as _os2
_use_ortho = False
_ortho_scale = 0.0
_topdown = _os2.environ.get('SH3D_RENDER_TOPDOWN', '') not in ('', '0', 'false')
if _topdown:
    _xs = []; _ys = []; _zs = []
    for obj in bpy.context.scene.objects:
        if obj.type == 'MESH':
            for v in obj.data.vertices:
                wv = obj.matrix_world @ v.co
                _xs.append(wv.x); _ys.append(wv.y); _zs.append(wv.z)
    if _xs:
        # Imported SH3D geometry is Y-UP in Blender: Y is height, the floor
        # plane is X-Z. Look straight DOWN the -Y axis to get a true plan view.
        _cx = (min(_xs) + max(_xs)) / 2.0
        _cz = (min(_zs) + max(_zs)) / 2.0
        cam_loc = (_cx, max(_ys) + 10.0, _cz)   # above the roof, in +Y
        cam_rot = (-math.pi / 2.0, 0.0, 0.0)     # look straight down -Y
        fov = math.radians(60.0)
        _use_ortho = True
        _ortho_scale = max(max(_xs) - min(_xs), max(_zs) - min(_zs)) * 1.08
        print(f"BLENDER-RENDER: TOP-DOWN ortho cam centre=({_cx:.2f},{_cz:.2f}) "
              f"scale={_ortho_scale:.2f}")
    else:
        _topdown = False

if not _topdown and cam_info and 'camera' in cam_info:
    c = cam_info['camera']
    x_sh3d   = float(c.get('x',          0.0))
    y_sh3d   = float(c.get('y',          0.0))
    z_sh3d   = float(c.get('z',        500.0))
    yaw      = float(c.get('yaw',        0.0))
    pitch    = float(c.get('pitch',      0.0))
    fov      = float(c.get('fieldOfView', math.radians(60)))

    cam_loc  = sh3d_to_blender_pos(x_sh3d, y_sh3d, z_sh3d)
    cam_rot  = sh3d_to_blender_euler(yaw, pitch)
    print(f"BLENDER-RENDER: SH3D camera x={x_sh3d} y={y_sh3d} z={z_sh3d} "
          f"yaw={yaw:.4f} pitch={pitch:.4f} fov={fov:.4f}")
    print(f"BLENDER-RENDER: Blender camera loc={cam_loc} rot={cam_rot}")
else:
    # Default: look at centroid of imported geometry from 5m elevation, -15° pitch
    try:
        all_verts = []
        for obj in bpy.context.scene.objects:
            if obj.type == 'MESH':
                for v in obj.data.vertices:
                    wv = obj.matrix_world @ v.co
                    all_verts.append((wv.x, wv.y, wv.z))
        if all_verts:
            cx = sum(v[0] for v in all_verts) / len(all_verts)
            cy = sum(v[1] for v in all_verts) / len(all_verts)
        else:
            cx, cy = 0.0, 0.0
    except Exception as exc:
        print(f"BLENDER-RENDER: WARNING — centroid calculation failed: {exc}. "
              f"Defaulting to origin.")
        cx, cy = 0.0, 0.0

    cam_loc = (cx - 5.0, cy - 5.0, 5.0)   # 5m above, slightly offset
    pitch_default = math.radians(-15.0)      # -15° = look slightly down
    # For default camera: aim at centroid from the offset position
    # Use a fixed yaw that roughly faces the scene centre
    yaw_default = 0.0
    cam_rot = (
        math.pi / 2.0 - pitch_default,      # rx: looking slightly down
        0.0,
        math.pi + yaw_default,
    )
    fov = math.radians(60.0)
    camera_source = "default (centroid fallback)"
    print(f"BLENDER-RENDER: using default camera at {cam_loc}, rot={cam_rot}")

# Environment colours
sky_color    = (0.529, 0.808, 0.922, 1.0)   # light blue default
ground_color = (0.486, 0.702, 0.255, 1.0)   # grass green default

if cam_info and 'environment' in cam_info:
    env = cam_info['environment']
    if 'skyColor' in env:
        sky_color = _parse_color(env['skyColor'])
    if 'groundColor' in env:
        ground_color = _parse_color(env['groundColor'])

# ---------------------------------------------------------------------------
# 8. World / lighting setup
# ---------------------------------------------------------------------------
try:
    world = bpy.data.worlds.new('RenderWorld')
    scene.world = world
    world.use_nodes = True
    wnt = world.node_tree
    wnt.nodes.clear()

    bg_node  = wnt.nodes.new('ShaderNodeBackground')
    out_node = wnt.nodes.new('ShaderNodeOutputWorld')
    wnt.links.new(bg_node.outputs['Background'], out_node.inputs['Surface'])

    bg_node.inputs['Color'].default_value = sky_color
    # Stronger sky gives ambient fill on the shadow-side facades so they
    # don't read as solid black under a low directional sun.
    bg_node.inputs['Strength'].default_value = 4.0
    print(f"BLENDER-RENDER: sky colour set to {sky_color}")
except Exception as exc:
    print(f"BLENDER-RENDER: WARNING — world/sky setup failed: {exc}")
    traceback.print_exc()

# Sun light (warm morning sun, 7am: low in east, slightly south)
try:
    sun_data = bpy.data.lights.new(name='Sun', type='SUN')
    sun_data.energy   = 3.0
    sun_data.color    = (1.0, 0.87, 0.7)   # warm yellowish
    sun_data.angle    = math.radians(0.5)
    sun_obj = bpy.data.objects.new('Sun', sun_data)
    bpy.context.collection.objects.link(sun_obj)

    # Centroid of scene for placement
    try:
        all_verts_sun = []
        for obj in bpy.context.scene.objects:
            if obj.type == 'MESH':
                for v in obj.data.vertices:
                    wv = obj.matrix_world @ v.co
                    all_verts_sun.append((wv.x, wv.y, wv.z))
        if all_verts_sun:
            scx = sum(v[0] for v in all_verts_sun) / len(all_verts_sun)
            scy = sum(v[1] for v in all_verts_sun) / len(all_verts_sun)
        else:
            scx, scy = 0.0, 0.0
    except Exception:
        scx, scy = 0.0, 0.0

    sun_obj.location = (scx + 5.0, scy - 5.0, 20.0)
    # Point the sun downward and slightly south: tilt X ~-60°, rotate Z ~45°
    sun_obj.rotation_euler = (math.radians(-60.0), 0.0, math.radians(45.0))
    print(f"BLENDER-RENDER: sun light placed at {sun_obj.location}")
except Exception as exc:
    print(f"BLENDER-RENDER: WARNING — sun light setup failed: {exc}")
    traceback.print_exc()

# Ground plane (below z=0) with ground colour as diffuse
try:
    bpy.ops.mesh.primitive_plane_add(size=2000.0, location=(0.0, 0.0, -0.01))
    ground_obj = bpy.context.active_object
    ground_obj.name = 'GroundPlane'

    ground_mat = bpy.data.materials.new('GroundMaterial')
    ground_mat.use_nodes = True
    gnt = ground_mat.node_tree
    bsdf = gnt.nodes.get('Principled BSDF')
    if bsdf is None:
        bsdf = gnt.nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.inputs['Base Color'].default_value = ground_color
    bsdf.inputs['Roughness'].default_value  = 0.9

    ground_obj.data.materials.append(ground_mat)
    print(f"BLENDER-RENDER: ground plane added with colour {ground_color}")
except Exception as exc:
    print(f"BLENDER-RENDER: WARNING — ground plane setup failed: {exc}")
    traceback.print_exc()

# ---------------------------------------------------------------------------
# 9. Camera object setup
# ---------------------------------------------------------------------------
try:
    cam_data = bpy.data.cameras.new('RenderCamera')
    cam_data.lens_unit = 'FOV'
    cam_data.angle     = fov
    if _use_ortho:
        cam_data.type = 'ORTHO'
        cam_data.ortho_scale = _ortho_scale

    cam_obj = bpy.data.objects.new('RenderCamera', cam_data)
    bpy.context.collection.objects.link(cam_obj)

    cam_obj.location = cam_loc

    # Camera framing policy:
    #
    # - When --camera-json supplies an explicit camera with non-zero yaw or
    #   pitch (i.e. the user picked a viewpoint via `render --from-camera`
    #   or `camera set`), trust the SH3D angles. The Euler conversion in
    #   sh3d_to_blender_euler() is approximate but matches the convention
    #   the rest of the harness uses, so users who tune `camera set` get
    #   what they're tuning.
    #
    # - Otherwise (no camera JSON, or yaw/pitch both 0 = default), fall
    #   back to track_quat(centroid) so a no-config render still produces
    #   a usable "see the building" framing.
    import mathutils  # local import — bpy guarantees this is available
    explicit_angles = (
        cam_info is not None
        and 'camera' in cam_info
        and (float(cam_info['camera'].get('yaw', 0.0)) != 0.0
              or float(cam_info['camera'].get('pitch', 0.0)) != 0.0)
    )
    if explicit_angles:
        cam_obj.rotation_mode  = 'XYZ'
        cam_obj.rotation_euler = cam_rot
        print(f"BLENDER-RENDER: camera placed at {cam_loc} rot={cam_rot} "
               f"(honoring explicit SH3D yaw/pitch) fov={math.degrees(fov):.1f}°")
    else:
        centroid_verts = []
        for ob in bpy.context.scene.objects:
            if ob.type == 'MESH' and not ob.name.startswith(('Sun', 'Ground', 'RenderCamera')):
                for v in ob.data.vertices:
                    wv = ob.matrix_world @ v.co
                    centroid_verts.append(wv)
        if centroid_verts:
            scx = sum(v.x for v in centroid_verts) / len(centroid_verts)
            scy = sum(v.y for v in centroid_verts) / len(centroid_verts)
            scz = sum(v.z for v in centroid_verts) / len(centroid_verts)
            target = mathutils.Vector((scx, scy, scz))
            direction = target - mathutils.Vector(cam_loc)
            cam_obj.rotation_mode = 'QUATERNION'
            cam_obj.rotation_quaternion = direction.to_track_quat('-Z', 'Y')
            print(f"BLENDER-RENDER: camera placed at {cam_loc} aiming at centroid {tuple(target)} "
                   f"(no explicit angles in camera JSON) fov={math.degrees(fov):.1f}°")
        else:
            cam_obj.rotation_mode  = 'XYZ'
            cam_obj.rotation_euler = cam_rot
            print(f"BLENDER-RENDER: camera placed at {cam_loc} rot={cam_rot} "
                   f"(no geometry to track) fov={math.degrees(fov):.1f}°")

    scene.camera = cam_obj
except Exception as exc:
    print(f"BLENDER-RENDER: ERROR — camera setup failed: {exc}")
    traceback.print_exc()
    sys.exit(1)

# ---------------------------------------------------------------------------
# 10. Render settings
# ---------------------------------------------------------------------------
try:
    scene.render.resolution_x = WIDTH
    scene.render.resolution_y = HEIGHT
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = OUTPUT_PNG
    print(f"BLENDER-RENDER: render output → {OUTPUT_PNG}  ({WIDTH}x{HEIGHT})")
except Exception as exc:
    print(f"BLENDER-RENDER: ERROR — render settings failed: {exc}")
    traceback.print_exc()
    sys.exit(1)

# ---------------------------------------------------------------------------
# 11. Render
# ---------------------------------------------------------------------------
try:
    bpy.ops.render.render(write_still=True)
    print("BLENDER-RENDER: render complete")
except Exception as exc:
    print(f"BLENDER-RENDER: ERROR — render failed: {exc}")
    traceback.print_exc()
    sys.exit(1)

# ---------------------------------------------------------------------------
# 12. Summary
# ---------------------------------------------------------------------------
print("---")
print(f"engine: BlenderCycles-{compute_backend_used}")
print(f"samples: {SAMPLES}")
print(f"resolution: {WIDTH}x{HEIGHT}")
print(f"camera: loc={cam_loc} rot={tuple(round(r, 4) for r in cam_rot)} "
      f"fov={math.degrees(fov):.1f}° (source: {camera_source})")
print(f"wrote: {OUTPUT_PNG}")
