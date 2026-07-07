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


def find_plan_region(page, plan_title, pad=45, window=300):
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
    # Stacked plans on one sheet each sit in a tight y-window just above their title.
    # Take wall fills in that window (dimension leaders can bridge the inter-plan gap,
    # so a fixed window is more robust than gap-detection). `window` is tuned so the
    # plan clears its neighbour above; pass an explicit `region` for awkward sheets.
    top, bot = title.y0 - window, title.y0 + 12
    cands = []
    for path in page.get_drawings():
        if not classify_fill(path):
            continue
        r = path.get("rect")
        if not r or r.width > 700 or r.height > 700:
            continue
        cy = (r.y0 + r.y1) / 2
        if top < cy < bot:
            cands.append(r)
    if not cands:
        return None
    xs = [c.x0 for c in cands] + [c.x1 for c in cands]
    yy = [c.y0 for c in cands] + [c.y1 for c in cands]
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


def pdf_to_home(pdf_path, *, page_index=0, plan_title=None, region=None,
                scale_cm_per_pt=CM_PER_PT_1TO100, min_wall_cm=25, weld_cm=20,
                level_name="Ground Floor"):
    """Convert one plan on a vector floorplan PDF into a Home (walls only, v1).

    Provide `plan_title` (e.g. 'Ground Floor - Proposed') to auto-locate the plan
    on a multi-drawing sheet, or an explicit `region` (fitz.Rect). Scale defaults
    to 1:100 on a true-size sheet; override for other scales/calibration.
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
    ap = argparse.ArgumentParser(description="Convert a vector floorplan PDF to .sh3d (walls, v1)")
    ap.add_argument("pdf")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--page", type=int, default=0)
    ap.add_argument("--plan", help="plan title to locate, e.g. 'Ground Floor - Proposed'")
    ap.add_argument("--scale", type=float, default=CM_PER_PT_1TO100, help="cm per PDF point")
    a = ap.parse_args()
    h = pdf_to_home(a.pdf, page_index=a.page, plan_title=a.plan, scale_cm_per_pt=a.scale)
    save_home(h, a.output)
    print(f"{a.output}: {len(h.walls)} walls")
