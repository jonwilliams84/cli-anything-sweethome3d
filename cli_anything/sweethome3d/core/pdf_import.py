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


def extract_wall_rects(page, region):
    """Return [(cls, rect)] wall poché rectangles inside `region`, arrowheads removed."""
    fitz = _require_fitz()
    out = []
    for path in page.get_drawings():
        cls = classify_fill(path)
        r = path.get("rect")
        if not cls or not r:
            continue
        cx, cy = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
        area = r.width * r.height
        if not (region.x0 < cx < region.x1 and region.y0 < cy < region.y1):
            continue
        if r.width > 700 or r.height > 700 or _is_dimension_mark(path, area):
            continue
        out.append((cls, r))
    return out


def _merge_runs(rects, axis, cross_tol_frac=0.8, gap=10):
    """Merge poché rectangles into wall centreline runs.

    axis 0 = horizontal walls (constant y); axis 1 = vertical (constant x).
    Returns [(cross, a0, a1, thickness, cls)] in PDF points."""
    segs = []
    for cls, r in rects:
        if axis == 0:
            segs.append([(r.y0 + r.y1) / 2, r.x0, r.x1, r.height, cls])
        else:
            segs.append([(r.x0 + r.x1) / 2, r.y0, r.y1, r.width, cls])
    segs.sort()
    merged = []
    for cross, a0, a1, th, cls in segs:
        for m in merged:
            if abs(m[0] - cross) <= max(m[3], th) * cross_tol_frac and a0 <= m[2] + gap and a1 >= m[1] - gap:
                m[1], m[2] = min(m[1], a0), max(m[2], a1)
                m[3] = max(m[3], th)
                m[0] = (m[0] + cross) / 2
                if cls == "existing":
                    m[4] = "existing"
                break
        else:
            merged.append([cross, a0, a1, th, cls])
    return merged


def _weld(walls, tol):
    """Snap wall endpoints that are within `tol` (cm) to a shared point, so
    junctions actually meet (Sweet Home 3D needs connected walls for rooms)."""
    pts = []
    for w in walls:
        pts += [(w.xStart, w.yStart), (w.xEnd, w.yEnd)]
    clusters = []
    for x, y in pts:
        for c in clusters:
            if abs(c[0] - x) <= tol and abs(c[1] - y) <= tol:
                c[2].append((x, y))
                c[0] = sum(p[0] for p in c[2]) / len(c[2])
                c[1] = sum(p[1] for p in c[2]) / len(c[2])
                break
        else:
            clusters.append([x, y, [(x, y)]])

    def snap(x, y):
        for c in clusters:
            if abs(c[0] - x) <= tol and abs(c[1] - y) <= tol:
                return round(c[0], 1), round(c[1], 1)
        return x, y
    for w in walls:
        w.xStart, w.yStart = snap(w.xStart, w.yStart)
        w.xEnd, w.yEnd = snap(w.xEnd, w.yEnd)
    return walls


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

    rects = extract_wall_rects(page, region)
    if not rects:
        raise ValueError("no wall poché found in the region — is this a vector plan?")
    hor = [(c, r) for c, r in rects if r.width >= r.height]
    ver = [(c, r) for c, r in rects if r.height > r.width]
    runs = [("h", m) for m in _merge_runs(hor, 0)] + [("v", m) for m in _merge_runs(ver, 1)]

    # origin = min x and min y, taking coords per run TYPE (h-run m[1:3] are x, v-run m[1:3] are y)
    xs, ys = [], []
    for kind, m in runs:
        if kind == "h":
            ys.append(m[0]); xs += [m[1], m[2]]
        else:
            xs.append(m[0]); ys += [m[1], m[2]]
    ox, oy = min(xs), min(ys)
    s = scale_cm_per_pt

    home = Home()
    lvl = Level(name=level_name, elevation=0)
    home.levels.append(lvl)
    home.selectedLevel = lvl.id
    for kind, (cross, a0, a1, th, cls) in runs:
        if (a1 - a0) * s < min_wall_cm:      # drop stray poché fragments / corner blocks
            continue
        thickness = max(5.0, round(th * s, 1))
        if kind == "h":
            w = Wall(round((a0 - ox) * s, 1), round((cross - oy) * s, 1),
                     round((a1 - ox) * s, 1), round((cross - oy) * s, 1),
                     thickness=thickness, level=lvl.id, height=250)
        else:
            w = Wall(round((cross - ox) * s, 1), round((a0 - oy) * s, 1),
                     round((cross - ox) * s, 1), round((a1 - oy) * s, 1),
                     thickness=thickness, level=lvl.id, height=250)
        home.walls.append(w)
    _weld(home.walls, weld_cm)
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
