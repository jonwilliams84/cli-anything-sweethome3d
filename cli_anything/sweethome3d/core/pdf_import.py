"""pdf_import — turn a vector architect's floorplan PDF into a Sweet Home 3D Home.

The USP: feed an estate-agent / architect extension plan (a *vector* PDF) and get
a .sh3d with the walls in the right place. Architect plans draw walls as filled
"poché" polygons — existing walls black, proposed/new walls grey — with room
labels and dimensions as real positioned text. We read that geometry directly
(no VLM): classify fills by colour, merge the poché into axis-aligned wall
centrelines, calibrate scale (1:100 by default, or from a known dimension), and
build Wall objects.

v1 scope: WALLS (existing + new extension), single plan region, axis-aligned.
Doors/windows/rooms are follow-ups (see cli_anything/sweethome3d/core/floorplan_eval.py
for how accuracy is scored). Requires PyMuPDF (fitz).

Typical use:
    from cli_anything.sweethome3d.core.pdf_import import pdf_to_home
    home = pdf_to_home("plans.pdf", plan_title="Ground Floor - Proposed")
    save_home(home, "ground_floor.sh3d")
"""
from __future__ import annotations
import math

# 1:100 on a true-size sheet: 1 PDF point (1/72") = 0.352778 mm paper × 100 = 3.5278 cm real.
CM_PER_PT_1TO100 = 72 ** -1 * 25.4 * 100 / 10  # = 3.5278


def _require_fitz():
    try:
        import fitz  # PyMuPDF
        return fitz
    except ImportError as e:  # pragma: no cover - dependency guard
        raise ImportError("pdf_import needs PyMuPDF — `pip install PyMuPDF`") from e


def classify_fill(path):
    """Classify a filled vector path as an 'existing' (black poché) or 'new'
    (grey poché) wall, or None if it isn't wall fill."""
    f = path.get("fill")
    if f is None:
        return None
    r, g, b = f
    if r + g + b < 0.3:
        return "existing"
    if abs(r - g) < 0.08 and abs(g - b) < 0.08 and 0.35 < r < 0.65:
        return "new"
    return None


def _is_dimension_mark(path, area):
    """Dimension arrowheads: small, triangular (few points), and never a rect."""
    if area > 55 or any(it[0] == "re" for it in path["items"]):
        return False
    return sum(1 for it in path["items"] if it[0] in ("l", "c")) <= 3


def find_plan_region(page, plan_title, pad=45, gap=80):
    """Derive the bounding box of a named plan (e.g. 'Ground Floor - Proposed')
    on a multi-drawing sheet, using its title text + nearby wall fills. Returns a
    fitz.Rect, or None if the title isn't found."""
    fitz = _require_fitz()
    words = page.get_text("words")
    seq = plan_title.split()
    title = None
    for i in range(len(words) - len(seq) + 1):
        if [words[i + k][4] for k in range(len(seq))] == seq:
            xs = [words[i + k][0] for k in range(len(seq))] + [words[i + k][2] for k in range(len(seq))]
            ys = [words[i + k][1] for k in range(len(seq))] + [words[i + k][3] for k in range(len(seq))]
            title = fitz.Rect(min(xs), min(ys), max(xs), max(ys))
            break
    if title is None:
        return None
    # A busy A0 sheet holds many drawings (existing/proposed plans + elevations). Isolate
    # the target: cluster all wall fills into vertical bands separated by whitespace gaps
    # (each band = one drawing), then keep the band whose y-range contains the title — the
    # plan wraps its own title. Region = that band's fill bbox (dimension leaders aren't
    # fills, so they're naturally excluded). Robust to titles offset to the side.
    tx, ty = (title.x0 + title.x1) / 2, (title.y0 + title.y1) / 2
    fills = []
    for path in page.get_drawings():
        if not classify_fill(path):
            continue
        r = path.get("rect")
        if not r or r.width > 700 or r.height > 700:
            continue
        fills.append(r)
    if not fills:
        return None
    # Stage 1 — find the plan's y-band by clustering fills in the TITLE'S COLUMN (there the
    # inter-drawing whitespace is clean; across the full width, dimension leaders bridge it).
    col = sorted((r for r in fills if abs((r.x0 + r.x1) / 2 - tx) < 300),
                 key=lambda r: (r.y0 + r.y1) / 2)
    if not col:
        col = sorted(fills, key=lambda r: (r.y0 + r.y1) / 2)
    ylo = yhi = None; start = 0
    for i in range(1, len(col) + 1):
        prev_cy = (col[i - 1].y0 + col[i - 1].y1) / 2
        nxt_cy = (col[i].y0 + col[i].y1) / 2 if i < len(col) else 1e18
        if nxt_cy - prev_cy > gap or i == len(col):
            cl = col[start:i]
            lo, hi = min(r.y0 for r in cl), max(r.y1 for r in cl)
            if lo - gap <= ty <= hi + gap:
                ylo, yhi = lo, hi
            start = i
    if ylo is None:
        return None
    # Stage 2 — region = bbox of ALL fills within that y-band (captures the full width, e.g. an
    # extension wider than the original house; dimension leaders aren't fills, so excluded).
    band = [r for r in fills if ylo - 4 <= (r.y0 + r.y1) / 2 <= yhi + 4]
    xs = [c.x0 for c in band] + [c.x1 for c in band]
    yy = [c.y0 for c in band] + [c.y1 for c in band]
    return fitz.Rect(min(xs) - pad, min(yy) - pad, max(xs) + pad, max(yy) + pad)


def extract_wall_polygons(page, region):
    """Return each wall poché as a list of (x, y) vertex polygons (in PDF points),
    inside `region`, with dimension arrowheads removed. These outlines are the wall
    *faces* — feeding them to the SVG wall-pairing pipeline recovers centrelines."""
    polys = []
    for path in page.get_drawings():
        if not classify_fill(path):
            continue
        r = path.get("rect")
        if not r:
            continue
        cx, cy = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
        area = r.width * r.height
        if not (region.x0 < cx < region.x1 and region.y0 < cy < region.y1):
            continue
        if r.width > 700 or r.height > 700 or _is_dimension_mark(path, area):
            continue
        cur = []
        for it in path["items"]:
            if it[0] == "l":
                if not cur:
                    cur.append((it[1].x, it[1].y))
                cur.append((it[2].x, it[2].y))
            elif it[0] == "re":
                rr = it[1]
                if cur:
                    polys.append(cur); cur = []
                polys.append([(rr.x0, rr.y0), (rr.x1, rr.y0), (rr.x1, rr.y1), (rr.x0, rr.y1), (rr.x0, rr.y0)])
            elif it[0] == "qu":
                q = it[1]
                if cur:
                    polys.append(cur); cur = []
                polys.append([(q.ul.x, q.ul.y), (q.ur.x, q.ur.y), (q.lr.x, q.lr.y), (q.ll.x, q.ll.y), (q.ul.x, q.ul.y)])
            elif it[0] == "c":
                if not cur:
                    cur.append((it[1].x, it[1].y))
                cur.append((it[4].x, it[4].y))
        if cur:
            polys.append(cur)
    return polys


def skeleton_walls(polys, scale_cm_per_pt, *, min_wall_cm=25, weld_cm=20, ss=2):
    """Recover connected wall centrelines from messy architect poché via the
    medial axis: rasterise the filled poché -> morphological close (heal hatching)
    -> skeletonise -> Hough-vectorise -> snap to H/V + merge collinear (reusing
    walls.py) -> weld junctions. Thickness comes from the distance transform.

    Returns [(xStart, yStart, xEnd, yEnd, thickness)] in cm. Robust where naive
    bbox-merge (disconnected) and edge-pairing (under-reads real poché) fail.
    """
    import numpy as np
    from skimage.draw import polygon as draw_polygon
    from skimage.morphology import skeletonize, closing, footprint_rectangle
    from skimage.transform import probabilistic_hough_line
    from scipy.ndimage import distance_transform_edt
    from cli_anything.sweethome3d.core.svg.walls import axis_aligned, close_corners, join_walls, grid_snap

    ox = min(x for po in polys for x, _ in po)
    oy = min(y for po in polys for _, y in po)
    w = int((max(x for po in polys for x, _ in po) - ox) * ss) + 4
    h = int((max(y for po in polys for _, y in po) - oy) * ss) + 4
    mask = np.zeros((h, w), bool)
    for po in polys:
        xs = np.array([(x - ox) * ss for x, _ in po])
        ys = np.array([(y - oy) * ss for _, y in po])
        rr, cc = draw_polygon(ys, xs, shape=mask.shape)
        mask[rr, cc] = True
    mask = closing(mask, footprint_rectangle((3, 3)))         # heal hatching / hairline gaps
    dist = distance_transform_edt(mask)
    skel = skeletonize(mask)
    px_per_cm = ss / scale_cm_per_pt
    segs = probabilistic_hough_line(
        skel, threshold=8,
        line_length=max(6, int(min_wall_cm * 0.5 * px_per_cm)),
        line_gap=max(3, int(6 * px_per_cm)))
    if not segs:
        return []
    # px -> cm segments for the repo's axis snapper/merger
    cm = scale_cm_per_pt / ss
    xy = [(a[0] * cm, a[1] * cm, b[0] * cm, b[1] * cm) for a, b in segs]

    def thickness_cm(xcm, ycm):
        ix = min(w - 1, max(0, int(xcm / cm))); iy = min(h - 1, max(0, int(ycm / cm)))
        return max(5.0, round(dist[iy, ix] * 2 / ss * scale_cm_per_pt, 1))

    # merge collinear Hough fragments with a SMALL min length (keep short partitions),
    # then a gentle weld — the repo's grid_snap is too aggressive for skeleton output.
    walls = []
    for mid, lo, hi in axis_aligned(xy, "h", 6.0, 8.0):
        walls.append((lo, mid, hi, mid, thickness_cm((lo + hi) / 2, mid)))
    for mid, lo, hi in axis_aligned(xy, "v", 6.0, 8.0):
        walls.append((mid, lo, mid, hi, thickness_cm(mid, (lo + hi) / 2)))
    if walls:
        walls = close_corners(walls, snap_distance=max(weld_cm, 25.0))
        walls = join_walls(walls, join_tolerance=max(weld_cm, 25.0))
    # final: drop stubs shorter than min_wall_cm (spurs) but keep everything else
    return [w for w in walls if math.hypot(w[2] - w[0], w[3] - w[1]) >= min_wall_cm]


# ---- input preparation for the model backend -------------------------------------
def _grey_to_black(path):
    """Architect plans draw NEW/proposed walls grey; floorplan models are trained on
    BLACK walls. Recolour mid-grey poché to black so the model reads the extension."""
    try:
        import numpy as np
        from PIL import Image
    except ImportError:  # pragma: no cover
        return
    im = np.asarray(Image.open(path).convert("RGB")).astype(int)
    r, g, b = im[..., 0], im[..., 1], im[..., 2]
    grey = (np.abs(r - g) < 28) & (np.abs(g - b) < 28) & (r > 70) & (r < 175)
    im[grey] = [0, 0, 0]
    Image.fromarray(im.astype("uint8")).save(path)


def render_region_png(page, region, out_path, *, dpi=200, grey_to_black=True):
    """Render one plan region to a PNG suitable for a floorplan model."""
    page.get_pixmap(dpi=dpi, clip=region).save(out_path)
    if grey_to_black:
        _grey_to_black(out_path)
    return out_path


# ---- external model backend (e.g. CubiCasa5k, user-supplied — see cubicasa_runner) --
def run_model(png_path, out_json, *, model_cmd=None):
    """Invoke the configured model backend to produce a polygons JSON
    {w,h,walls:[{points,class}],openings:[{points,class}],rooms:[...]}. `model_cmd` is a
    command (list or string) with `{in}`/`{out}` placeholders; falls back to $SH3D_MODEL_CMD.
    The model itself is NOT shipped with this package (licence/size) — the user supplies it."""
    import os, json, shlex, subprocess
    cmd = model_cmd or os.environ.get("SH3D_MODEL_CMD")
    if not cmd:
        raise RuntimeError(
            "no model backend configured. Set --model-cmd or $SH3D_MODEL_CMD, e.g.\n"
            "  '/path/to/torch-venv/bin/python /path/to/cubicasa_runner.py {in} {out}'\n"
            "(see cli_anything/sweethome3d/tools/cubicasa_runner.py). Or use backend='geometry'.")
    if isinstance(cmd, str):
        cmd = shlex.split(cmd)
    cmd = [c.replace("{in}", png_path).replace("{out}", out_json) for c in cmd]
    subprocess.run(cmd, check=True)
    return json.load(open(out_json))


# ---- map model polygons -> Home ---------------------------------------------------
_OPENING_CAT = {1: ("eTeks#window", "Window"), 2: ("eTeks#doubleDoor", "Door")}


def _poly_bbox(pts):
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def _place_opening(walls, cx, cy, w_cm, name, cat, level):
    """Bind a door/window piece to the nearest wall (projected onto it)."""
    from cli_anything.sweethome3d.core.model import PieceOfFurniture
    best, bd = None, 1e18
    for w in walls:
        dx, dy = w.xEnd - w.xStart, w.yEnd - w.yStart
        L2 = dx * dx + dy * dy or 1
        t = max(0.0, min(1.0, ((cx - w.xStart) * dx + (cy - w.yStart) * dy) / L2))
        px, py = w.xStart + t * dx, w.yStart + t * dy
        d = math.hypot(cx - px, cy - py)
        if d < bd:
            bd, best = d, (w, px, py, dx, dy)
    if not best or bd > max(70.0, w_cm):
        return None
    w, px, py, dx, dy = best
    return PieceOfFurniture(name=name, x=round(px, 1), y=round(py, 1), width=round(max(20.0, w_cm), 1),
                            depth=round(w.thickness + 2, 1), height=200, kind="doorOrWindow",
                            angle=round(math.degrees(math.atan2(dy, dx)), 1),
                            catalogId=cat, level=level, boundToWall=True)


def polygons_to_home(pred, *, cm_per_px, level_name="Ground Floor", min_wall_cm=20, weld_cm=20,
                                 override_walls=None):
    """Convert a model prediction (pixel polygons) into a Home — walls (axis-aligned
    centrelines + thickness, welded) and doors/windows (bound to walls). Rooms if present.

    If ``override_walls`` is provided as a list of (x0,y0,x1,y1,thickness_cm) segments,
    those wall segments are used instead of deriving walls from ``pred['walls']``.
    Openings from ``pred['openings']`` are still bound onto the override walls via
    ``_place_opening``.  This makes the model backend testable and fusable with the
    room-contour wall network.
    """
    from cli_anything.sweethome3d.core.model import Home, Wall, Level, Room, Point
    from cli_anything.sweethome3d.core.svg.walls import close_corners, join_walls
    s = cm_per_px
    raw = []
    if override_walls is not None:
        raw = list(override_walls)
    else:
        for wp in pred.get("walls", []):
            pts = wp.get("points", [])
            if len(pts) < 2:
                continue
            x0, y0, x1, y1 = _poly_bbox(pts)
            ww, hh = x1 - x0, y1 - y0
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            if ww >= hh:
                raw.append((x0 * s, cy * s, x1 * s, cy * s, max(6.0, hh * s)))
            else:
                raw.append((cx * s, y0 * s, cx * s, y1 * s, max(6.0, ww * s)))
    if raw:
        raw = close_corners(raw, snap_distance=max(weld_cm, 25.0))
        raw = join_walls(raw, join_tolerance=max(weld_cm, 25.0))
    raw = [w for w in raw if math.hypot(w[2] - w[0], w[3] - w[1]) >= min_wall_cm]

    home = Home()
    lvl = Level(name=level_name, elevation=0)
    home.levels.append(lvl)
    home.selectedLevel = lvl.id
    for xs_, ys_, xe_, ye_, th in raw:
        home.walls.append(Wall(round(xs_, 1), round(ys_, 1), round(xe_, 1), round(ye_, 1),
                               thickness=max(5.0, round(th, 1)), level=lvl.id, height=250))
    for op in pred.get("openings", []):
        pts = op.get("points", [])
        if len(pts) < 2:
            continue
        x0, y0, x1, y1 = _poly_bbox(pts)
        cx, cy = (x0 + x1) / 2 * s, (y0 + y1) / 2 * s
        w_cm = max(x1 - x0, y1 - y0) * s
        cat, name = _OPENING_CAT.get(op.get("class", 2), _OPENING_CAT[2])
        piece = _place_opening(home.walls, cx, cy, w_cm, name, cat, lvl.id)
        if piece:
            home.furniture.append(piece)
    for rp in pred.get("rooms", []):
        pts = rp.get("points", []) if isinstance(rp, dict) else rp
        if len(pts) >= 3:
            home.rooms.append(Room(points=[Point(round(p[0] * s, 1), round(p[1] * s, 1)) for p in pts],
                                   level=lvl.id, name=(rp.get("name") if isinstance(rp, dict) else None)))
    return home


def pdf_to_home(pdf_path, *, page_index=0, plan_title=None, region=None,
                scale_cm_per_pt=CM_PER_PT_1TO100, backend="geometry", dpi=200,
                grey_to_black=True, model_cmd=None, min_wall_cm=25, weld_cm=20,
                level_name="Ground Floor", wall_source="model"):
    """Convert one plan on a vector floorplan PDF into a Home.

    `plan_title` (e.g. 'Ground Floor - Proposed') auto-locates the plan on a
    multi-drawing sheet (isolating it from other plans/elevations); or pass an
    explicit `region` (fitz.Rect). Two backends:
      * "model"    — render the region (grey→black) and run an external floorplan
                     model (see run_model / cubicasa_runner) for walls + doors +
                     windows + rooms. Highest accuracy; needs a configured model.
      * "geometry" — offline, dependency-light medial-axis extraction of the poché
                     (walls only). No model required.
    """
    from cli_anything.sweethome3d.core.model import Home, Wall, Level
    fitz = _require_fitz()
    doc = fitz.open(pdf_path)
    page = doc[page_index]
    if page.rotation:
        page.set_rotation(0)  # text + geometry share one coordinate space
    if region is None:
        if not plan_title:
            region = page.rect
        else:
            region = find_plan_region(page, plan_title)
            if region is None:
                raise ValueError(f"plan titled {plan_title!r} not found on page {page_index}")

    if backend == "model":
        import os, tempfile
        d = tempfile.mkdtemp(prefix="sh3d-pdf-")
        png, out = os.path.join(d, "plan.png"), os.path.join(d, "pred.json")
        render_region_png(page, region, png, dpi=dpi, grey_to_black=grey_to_black)
        pred = run_model(png, out, model_cmd=model_cmd)
        cm_per_px = (72.0 / dpi) * scale_cm_per_pt
        override_walls = None
        if wall_source in ("rooms", "fused"):
            rc = room_contours(png, cm_per_px=cm_per_px)
            room_walls = rc.get("walls", [])
            if wall_source == "rooms":
                override_walls = room_walls
            else:
                # fused: start with room walls, add model walls that have no nearby room wall
                model_walls = []
                for wp in pred.get("walls", []):
                    pts = wp.get("points", [])
                    if len(pts) < 2:
                        continue
                    x0, y0, x1, y1 = _poly_bbox(pts)
                    ww, hh = x1 - x0, y1 - y0
                    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                    if ww >= hh:
                        model_walls.append((x0 * cm_per_px, cy * cm_per_px,
                                            x1 * cm_per_px, cy * cm_per_px,
                                            max(6.0, hh * cm_per_px)))
                    else:
                        model_walls.append((cx * cm_per_px, y0 * cm_per_px,
                                            cx * cm_per_px, y1 * cm_per_px,
                                            max(6.0, ww * cm_per_px)))
                fused = list(room_walls)
                for mw in model_walls:
                    mx0, my0, mx1, my1, mt = mw
                    mmx, mmy = (mx0 + mx1) / 2.0, (my0 + my1) / 2.0
                    near = False
                    for rw in room_walls:
                        rx0, ry0, rx1, ry1, _rt = rw
                        rlen = math.hypot(rx1 - rx0, ry1 - ry0) or 1.0
                        t = max(0.0, min(1.0, ((mmx - rx0) * (rx1 - rx0) +
                                               (mmy - ry0) * (ry1 - ry0)) / (rlen * rlen)))
                        rpx, rpy = rx0 + t * (rx1 - rx0), ry0 + t * (ry1 - ry0)
                        if math.hypot(mmx - rpx, mmy - rpy) <= max(25.0, mt):
                            near = True
                            break
                    if not near:
                        fused.append(mw)
                override_walls = fused
        return polygons_to_home(pred, cm_per_px=cm_per_px,
                                level_name=level_name, min_wall_cm=min_wall_cm,
                                weld_cm=weld_cm, override_walls=override_walls)

    polys = extract_wall_polygons(page, region)
    if not polys:
        raise ValueError("no wall poché found in the region — is this a vector plan?")
    walls = skeleton_walls(polys, scale_cm_per_pt, min_wall_cm=min_wall_cm, weld_cm=weld_cm)
    home = Home()
    lvl = Level(name=level_name, elevation=0)
    home.levels.append(lvl)
    home.selectedLevel = lvl.id
    for xs_, ys_, xe_, ye_, thick in walls:
        home.walls.append(Wall(round(xs_, 1), round(ys_, 1), round(xe_, 1), round(ye_, 1),
                               thickness=max(5.0, round(thick, 1)), level=lvl.id, height=250))
    return home


if __name__ == "__main__":
    import argparse
    from cli_anything.sweethome3d.core.project import save_home
    ap = argparse.ArgumentParser(description="Convert a vector floorplan PDF to .sh3d")
    ap.add_argument("pdf")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--page", type=int, default=0)
    ap.add_argument("--plan", help="plan title to locate, e.g. 'Ground Floor - Proposed'")
    ap.add_argument("--backend", choices=["geometry", "model"], default="geometry")
    ap.add_argument("--model-cmd", help="model backend command with {in}/{out} (or $SH3D_MODEL_CMD)")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--scale", type=float, default=CM_PER_PT_1TO100, help="cm per PDF point")
    a = ap.parse_args()
    h = pdf_to_home(a.pdf, page_index=a.page, plan_title=a.plan, backend=a.backend,
                    model_cmd=a.model_cmd, dpi=a.dpi, scale_cm_per_pt=a.scale)
    save_home(h, a.output)
    print(f"{a.output}: {len(h.walls)} walls, {len(h.furniture)} openings, {len(h.rooms)} rooms")


# ─────────────────────────────────────────────────────────────────────────────
# OpenCV room-contour extraction — stub-free rectilinear wall network
# ─────────────────────────────────────────────────────────────────────────────
# This layer fills the gaps left by the CubiCasa backend (missing wall segments
# and short floating stubs) by re-detecting rooms from the raw raster image.
#
# Pipeline:
#   threshold (Otsu or fixed) → morphology close (bridge small gaps)
#   → connectedComponents on the background → per-room contour
#   → approxPolyDP (epsilon ~1% of perimeter) → rectilinear room polygons
#   → wall segments = the boundary edges shared between adjacent rooms
#     (de-duplicated so each physical wall appears once, not twice).
#
# Every wall endpoint meets another wall endpoint — no floating stubs.
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# OpenCV room-contour extraction — stub-free rectilinear wall network
# ─────────────────────────────────────────────────────────────────────────────
# This layer fills gaps left by the CubiCasa backend (missing wall segments
# and floating stubs) by re-detecting rooms from the raster image.
#
# Pipeline:
#   threshold → morphology close (bridge 1-2px gaps)
#   → connectedComponents on background → identify bg by border-touch
#   → per-component findContours(RETR_EXTERNAL) → room contour polygon
#   → approxPolyDP (epsilon=2% perimeter) → rectilinear room polys
#   → wall segments = deduplicated room-boundary edges (each shared edge
#     appears once, not twice — no stubs, all junctions connected).
#
# opencv-python-headless is an optional dependency; guarded import via
# _require_cv2().  Install with: pip install opencv-python-headless
# or use the [rooms] extra: pip install -e ".[rooms]"
# ─────────────────────────────────────────────────────────────────────────────

def _require_cv2():
    """Lazily import OpenCV; raises ImportError with a clear message if absent."""
    try:
        import cv2
        return cv2
    except ImportError as e:
        raise ImportError(
            "room_contours needs opencv-python-headless — install with:\n"
            "  pip install opencv-python-headless\n"
            "or use the [rooms] extra: pip install -e '.[rooms]'"
        ) from e


def walls_from_rooms(room_polys, tol: float = 0.5):
    """
    Convert a list of rectilinear room polygons into a de-duplicated wall network.

    Each room's edges are candidate wall segments.  Where two rooms share an edge
    (same geometric segment, ignoring direction) that edge is counted **once** —
    the physical wall between them.  All non-shared edges are outer walls.

    The result is a closed, stub-free rectilinear network: every wall endpoint
    meets at least one other wall endpoint (within ``tol`` cm).

    Args:
        room_polys: list of polygons, each a list of (x_cm, y_cm) tuples.
        tol:        coordinate equality tolerance in cm (default 0.5).
                    Two segment endpoints closer than this are considered identical.

    Returns:
        List of (x0, y0, x1, y1, thickness_cm) wall segments.
        ``thickness_cm`` is fixed at 15.0 (typical residential wall); call sites
        can scale/adjust as needed.
    """
    import math

    def _pt_key(a, b, tol=tol):
        """Canonical (unordered) key for a directed segment."""
        ax, ay = a; bx, by = b
        if (ax, ay) <= (bx, by):
            return (ax, ay, bx, by)
        return (bx, by, ax, ay)

    THICKNESS = 15.0
    seen = {}  # canonical key → (x0, y0, x1, y1)

    for poly in room_polys:
        if len(poly) < 3:
            continue
        for i in range(len(poly)):
            a = poly[i]
            b = poly[(i + 1) % len(poly)]
            # Skip zero-length edges
            if math.hypot(b[0] - a[0], b[1] - a[1]) < tol:
                continue
            key = _pt_key(a, b)
            if key not in seen:
                seen[key] = (a[0], a[1], b[0], b[1])

    return [(x0, y0, x1, y1, THICKNESS) for (x0, y0, x1, y1) in seen.values()]


def room_contours(image_path, *, cm_per_px, wall_thresh=200):
    """
    Extract rooms and a clean, stub-free wall network from a floorplan raster image.

    The image should be a top-down architectural floorplan (black/dark walls on
    white/light background).  Works on PNG, JPEG, TIFF, or any format OpenCV reads.

    Pipeline
    --------
    1. Read image, convert to grayscale.
    2. ``cv2.threshold`` at ``wall_thresh`` (0-255); pixels <= this are wall (dark).
    3. ``MORPH_CLOSE`` (5×5 kernel) to bridge 1-2 px gaps in the wall lines.
    4. ``connectedComponents`` on the inverted (interior) image → room components.
       The component that touches the image border is the exterior/background and
       is excluded, so only genuine interior rooms are kept.
    5. Per component: ``findContours(RETR_EXTERNAL)`` → room boundary polygon;
       ``approxPolyDP`` (epsilon=2% perimeter) → simplified rectilinear polygon.
    6. ``walls_from_rooms()`` → de-duplicated shared-edge wall segments.

    Args
    ----
    image_path : str | Path
        Path to the raster floorplan image.
    cm_per_px : float
        Pixel-to-centimetre scale factor (e.g. 0.5 → 1 px = 0.5 cm).
    wall_thresh : int, default 200
        Fixed threshold value (0-255).  Pixels <= this are treated as wall (dark).
        For very dark scanned plans try 150-200; for bright CAD renders try 200-240.

    Returns
    -------
    dict with keys:
        ``rooms``      : list of room polygons, each a list of (x_cm, y_cm) tuples.
        ``walls``      : list of (x0, y0, x1, y1, thickness_cm) wall segments
                         forming a closed rectilinear network (no floating stubs).
        ``image_size_px``: (width_px, height_px) of the input image.

    Raises
    ------
    ImportError   : if OpenCV is not installed.
    FileNotFoundError : if the image path does not exist.
    RuntimeError  : if no interior rooms are found (try lowering wall_thresh).

    Example
    -------
        result = room_contours("floorplan.png", cm_per_px=0.5)
        print(f"Found {len(result['rooms'])} rooms")
        for x0, y0, x1, y1, t in result["walls"]:
            print(f"  Wall: ({x0:.1f},{y0:.1f}) → ({x1:.1f},{y1:.1f}), {t}cm thick")
    """
    cv2 = _require_cv2()
    import numpy as np

    # ── Step 1: read and grayscale ───────────────────────────────────────────
    img = cv2.imread(str(image_path))
    if img is None:
        raise FileNotFoundError(f"Cannot read image: {image_path}")
    h, w = img.shape[:2]

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # ── Step 2: threshold (dark = wall) ───────────────────────────────────────
    _, binary = cv2.threshold(gray, wall_thresh, 255, cv2.THRESH_BINARY_INV)

    # ── Step 3: morphology close (bridge small gaps / broken lines) ───────────
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

    # ── Step 4: connectedComponents on interior pixels → room labels ──────────
    # Invert: 255 = interior (room pixel), 0 = wall pixel
    interior = cv2.bitwise_not(closed)

    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
        interior, connectivity=8
    )

    # Identify the background component: the non-zero label whose bounding box
    # touches the image border (or the largest non-zero label if none touches the
    # border — e.g. a fully-enclosed floor plan).
    # Guard: if num_labels == 1 there are no interior (non-wall) pixels at all.
    bg_label = None
    candidate_labels = list(range(1, num_labels))
    if not candidate_labels:
        raise RuntimeError(
            f"room_contours found no interior room pixels in '{image_path}'. "
            "Try a different wall_thresh (default 200; lower = more wall)."
        )
    for label in candidate_labels:
        x = stats[label, cv2.CC_STAT_LEFT]
        y = stats[label, cv2.CC_STAT_TOP]
        bw = stats[label, cv2.CC_STAT_WIDTH]
        bh = stats[label, cv2.CC_STAT_HEIGHT]
        if x == 0 or y == 0 or x + bw >= w or y + bh >= h:
            bg_label = label
            break
    # Fallback: largest non-zero label is background
    if bg_label is None:
        bg_label = max(candidate_labels,
                       key=lambda l: stats[l, cv2.CC_STAT_AREA])

    # ── Step 5: per-room contour extraction ───────────────────────────────────
    rooms = []
    for label in range(1, num_labels):
        if label == bg_label:
            continue
        area = stats[label, cv2.CC_STAT_AREA]
        if area < 50:  # skip tiny noise components
            continue

        mask = (labels == label).astype(np.uint8) * 255
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            peri = cv2.arcLength(cnt, True)
            if peri < 4:
                continue
            # epsilon=2% of perimeter — sufficient to straighten rectilinear rooms
            # without collapsing narrow corridors
            approx = cv2.approxPolyDP(cnt, epsilon=0.02 * peri, closed=True)
            pts = [(float(p[0][0]), float(p[0][1])) for p in approx]
            # Scale from pixels → centimetres
            pts_cm = [(x * cm_per_px, y * cm_per_px) for (x, y) in pts]
            rooms.append(pts_cm)

    if not rooms:
        raise RuntimeError(
            f"room_contours found no rooms in '{image_path}'. "
            "Try a different wall_thresh (default 200; lower = more wall)."
        )

    # ── Step 6: walls from room boundaries (de-duplicated shared edges) ──────
    walls = walls_from_rooms(rooms)

    return {
        "rooms": rooms,
        "walls": walls,
        "image_size_px": (int(w), int(h)),
    }
