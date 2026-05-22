"""PNG floor-plan → synthetic SVG converter.

Converts a colour-coded PNG floor plan into a synthetic SVG that the
existing ``svg_to_home_multi`` pipeline can consume.  The colour
conventions mirror those used in the user's SVGs:

  black (#000000)       → walls (fill-rule evenodd path)
  red (#FF0000)         → external doors
  magenta (#FF00FF)     → internal doors
  blue (#0000FF)        → windows
  green (#00FF00-ish)   → patio doors (large, wall-adjacent) OR
                          corner-alignment markers (small, isolated)
  cyan (#00FFFF)        → skylights
  yellow (#FFFF00)      → pendant light circles
  marker green (#55d400)→ corner-marker squares (explicit distinct hue)

Scale convention
----------------
The user's SVGs have ``width="NNNN"`` (bare number, no units) and the
pipeline treats 1 SVG unit = 1 cm.  The PNGs are exported at the same
pixel-per-cm ratio — the PNG width in pixels equals the SVG width in cm.
So the default ``cm_per_pixel = 1.0`` is correct (1 pixel → 1 cm output).

If ``cm_per_pixel`` is supplied explicitly, that value overrides the default.

Usage::

    from cli_anything.sweethome3d.core.png_import import png_to_svg
    meta = png_to_svg('Ground Floor.png', '/tmp/Ground-Floor-synth.svg')
    # meta: {width_px, height_px, walls_extracted, openings, lights, markers}
"""

from __future__ import annotations

import math
import sys
from collections import deque
from typing import Optional

# ── third-party (PIL + numpy only; no OpenCV, no scikit-image) ─────────────
try:
    from PIL import Image
    import numpy as np
except ImportError as exc:
    raise ImportError("PIL and numpy are required for png_import") from exc


# ══════════════════════════════════════════════════════════════════════════════
# Colour classification helpers
# ══════════════════════════════════════════════════════════════════════════════

def _to_rgb(img: Image.Image) -> np.ndarray:
    """Return an H×W×3 uint8 array in RGB order."""
    if img.mode == "RGBA":
        # Composite over white background so transparent areas don't
        # confuse the colour classifiers.
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        return np.array(bg)
    return np.array(img.convert("RGB"))


def _black_mask(arr: np.ndarray) -> np.ndarray:
    """True where pixel is a wall (very dark)."""
    return (arr[:, :, 0] < 60) & (arr[:, :, 1] < 60) & (arr[:, :, 2] < 60)


def _red_mask(arr: np.ndarray) -> np.ndarray:
    """True where pixel is red (external door)."""
    return (arr[:, :, 0] > 180) & (arr[:, :, 1] < 80) & (arr[:, :, 2] < 80)


def _magenta_mask(arr: np.ndarray) -> np.ndarray:
    """True where pixel is magenta (internal door)."""
    return (arr[:, :, 0] > 180) & (arr[:, :, 1] < 80) & (arr[:, :, 2] > 180)


def _blue_mask(arr: np.ndarray) -> np.ndarray:
    """True where pixel is blue (window)."""
    return (arr[:, :, 0] < 80) & (arr[:, :, 1] < 80) & (arr[:, :, 2] > 180)


def _cyan_mask(arr: np.ndarray) -> np.ndarray:
    """True where pixel is cyan (skylight)."""
    return (arr[:, :, 0] < 80) & (arr[:, :, 1] > 180) & (arr[:, :, 2] > 180)


def _yellow_mask(arr: np.ndarray) -> np.ndarray:
    """True where pixel is yellow (light circle)."""
    return (arr[:, :, 0] > 180) & (arr[:, :, 1] > 180) & (arr[:, :, 2] < 80)


def _pure_green_mask(arr: np.ndarray) -> np.ndarray:
    """True where pixel is pure/bright green (patio door or corner marker)."""
    return (arr[:, :, 0] < 100) & (arr[:, :, 1] > 150) & (arr[:, :, 2] < 100)


def _marker_green_mask(arr: np.ndarray) -> np.ndarray:
    """True where pixel is the specific #55d400 corner-marker hue."""
    # #55d400 = (85, 212, 0) — distinct from pure green (0,255,0)
    return (
        (arr[:, :, 0] > 55) & (arr[:, :, 0] < 120) &
        (arr[:, :, 1] > 170) & (arr[:, :, 1] < 240) &
        (arr[:, :, 2] < 30)
    )


# ══════════════════════════════════════════════════════════════════════════════
# Connected-component labelling (pure numpy / BFS — no scipy)
# ══════════════════════════════════════════════════════════════════════════════

def _label_components(mask: np.ndarray) -> tuple[np.ndarray, int]:
    """4-connected BFS labelling.

    Returns (label_array, num_labels) where label_array has dtype int32
    and values 1..num_labels.  Pixels with mask==False get label 0.
    """
    h, w = mask.shape
    labels = np.zeros((h, w), dtype=np.int32)
    current_label = 0
    for r in range(h):
        for c in range(w):
            if mask[r, c] and labels[r, c] == 0:
                current_label += 1
                q: deque = deque()
                q.append((r, c))
                labels[r, c] = current_label
                while q:
                    y, x = q.popleft()
                    for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                        ny, nx = y + dy, x + dx
                        if 0 <= ny < h and 0 <= nx < w:
                            if mask[ny, nx] and labels[ny, nx] == 0:
                                labels[ny, nx] = current_label
                                q.append((ny, nx))
    return labels, current_label


def _component_bboxes(mask: np.ndarray,
                      min_area: int = 10) -> list[dict]:
    """Return a list of {label, ymin, ymax, xmin, xmax, area} dicts.

    Components smaller than ``min_area`` pixels are dropped (noise).
    """
    labels, n = _label_components(mask)
    if n == 0:
        return []
    bboxes = []
    for lbl in range(1, n + 1):
        lys, lxs = np.where(labels == lbl)
        if len(lys) < min_area:
            continue
        bboxes.append({
            "label": lbl,
            "ymin": int(lys.min()), "ymax": int(lys.max()),
            "xmin": int(lxs.min()), "xmax": int(lxs.max()),
            "area": int(len(lys)),
        })
    return bboxes


# ══════════════════════════════════════════════════════════════════════════════
# Douglas-Peucker polyline simplification
# ══════════════════════════════════════════════════════════════════════════════

def _dp_simplify(pts: list[tuple[int, int]], epsilon: float) -> list[tuple[int, int]]:
    """Iterative Douglas-Peucker simplification (avoids recursion depth issues)."""
    if len(pts) <= 2:
        return list(pts)
    # Use a stack-based iterative approach
    stack = [(0, len(pts) - 1)]
    keep = [False] * len(pts)
    keep[0] = True
    keep[-1] = True
    while stack:
        lo, hi = stack.pop()
        if hi - lo <= 1:
            continue
        x1, y1 = pts[lo]
        x2, y2 = pts[hi]
        dx, dy = x2 - x1, y2 - y1
        denom = math.hypot(dx, dy)
        max_d = 0.0
        max_i = lo
        if denom < 1e-9:
            for i in range(lo + 1, hi):
                d = math.hypot(pts[i][0] - x1, pts[i][1] - y1)
                if d > max_d:
                    max_d = d
                    max_i = i
        else:
            for i in range(lo + 1, hi):
                xi, yi = pts[i]
                d = abs(dy * xi - dx * yi + x2 * y1 - y2 * x1) / denom
                if d > max_d:
                    max_d = d
                    max_i = i
        if max_d > epsilon:
            keep[max_i] = True
            stack.append((lo, max_i))
            stack.append((max_i, hi))
    return [pts[i] for i in range(len(pts)) if keep[i]]


# ══════════════════════════════════════════════════════════════════════════════
# Wall contour tracing (per-component boundary walking)
# ══════════════════════════════════════════════════════════════════════════════

# 8-neighbourhood directions (clockwise from right)
_DIRS8 = [(0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1)]


def _trace_boundary(mask: np.ndarray, start_r: int, start_c: int,
                    dir_start: int = 4) -> list[tuple[int, int]]:
    """Moore-neighbourhood contour tracing from a known boundary pixel.

    ``dir_start`` is the index into _DIRS8 for the direction from which
    we "entered" the start pixel (default 4 = came from the left).

    Returns the ordered list of boundary pixels as (row, col) tuples.
    """
    h, w = mask.shape
    boundary = [(start_r, start_c)]
    prev_dir = dir_start
    pr, pc = start_r, start_c

    for _ in range(4 * (h + w) + 8):  # safety limit
        found = False
        for i in range(1, 9):
            idx = (prev_dir + i) % 8
            dr, dc = _DIRS8[idx]
            nr, nc = pr + dr, pc + dc
            if 0 <= nr < h and 0 <= nc < w and mask[nr, nc]:
                prev_dir = (idx + 4) % 8  # backtrack direction
                pr, pc = nr, nc
                if pr == start_r and pc == start_c:
                    return boundary
                boundary.append((pr, pc))
                found = True
                break
        if not found:
            break  # isolated pixel
    return boundary


def _polygon_area_rc(poly: list[tuple[int, int]]) -> float:
    """Shoelace formula for a polygon in (row, col) order."""
    n = len(poly)
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        r1, c1 = poly[i]
        r2, c2 = poly[(i + 1) % n]
        s += c1 * r2 - c2 * r1
    return abs(s) / 2.0


def _flood_fill_nonblack(wall_mask: np.ndarray,
                          start_r: int, start_c: int,
                          visited: np.ndarray) -> tuple[np.ndarray | None, bool]:
    """BFS flood-fill from (start_r, start_c) in the non-black (white) region.

    Returns (region_mask, touches_border).
    region_mask is a boolean mask of the filled pixels.
    touches_border indicates the fill reached the image edge (exterior region).
    Marks visited pixels in the passed-in array so each white region is processed
    only once.
    """
    h, w = wall_mask.shape
    region = np.zeros((h, w), dtype=bool)
    q: deque = deque()
    q.append((start_r, start_c))
    visited[start_r, start_c] = True
    touched_border = False
    while q:
        r, c = q.popleft()
        region[r, c] = True
        if r == 0 or r == h - 1 or c == 0 or c == w - 1:
            touched_border = True
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < h and 0 <= nc < w:
                if not wall_mask[nr, nc] and not visited[nr, nc]:
                    visited[nr, nc] = True
                    q.append((nr, nc))
    return region, touched_border


def _extract_wall_subpaths(wall_mask: np.ndarray,
                            dp_epsilon: float = 2.5,
                            min_area_px: float = 400.0,
                            ) -> list[list[tuple[int, int]]]:
    """Extract wall-region boundaries as simplified polygons for evenodd fill.

    The goal is to replicate what collect_wall_subpaths reads from the SVG:
    - FIRST subpath (largest area): the outer building envelope polygon,
      traced around the OUTSIDE of the combined (walls + rooms) footprint.
    - SUBSEQUENT subpaths: individual room polygons that punch holes in the
      solid black fill (rooms appear white via evenodd rule).

    Strategy:
    1. Build a "building footprint" mask = union of black walls and all
       enclosed (non-exterior) white regions. This fills in all rooms.
    2. Trace the outer boundary of the footprint → outer envelope subpath.
    3. For each enclosed white region (room), trace its boundary → hole subpath.
    4. Each large black wall component NOT part of the main footprint gets
       its own subpath (detached wall structures).
    5. Sort: outer envelope first (largest area), then holes/others descending.

    Returns a list of polygon vertex lists in (row, col) pixel order.
    The pipeline picks the largest-area subpath as the building envelope via
    ``max(subpaths, key=polygon_area)``.
    """
    h, w = wall_mask.shape

    # ── Step 1: Identify enclosed white regions (rooms) ─────────────────
    visited = np.zeros((h, w), dtype=bool)
    visited[wall_mask] = True  # skip all black pixels

    interior_regions: list[np.ndarray] = []
    exterior_regions: list[np.ndarray] = []

    for r in range(h):
        for c in range(w):
            if visited[r, c]:
                continue
            region, touched_border = _flood_fill_nonblack(wall_mask, r, c, visited)
            region_area = int(region.sum())
            if touched_border:
                exterior_regions.append(region)
            elif region_area >= min_area_px:
                interior_regions.append(region)

    # ── Step 2: Building footprint = walls ∪ all interior (room) regions ─
    footprint_mask = wall_mask.copy()
    for region in interior_regions:
        footprint_mask |= region

    # ── Step 3: Outer envelope — trace boundary of the largest footprint
    #            connected component ─────────────────────────────────────
    fp_labels, fp_n = _label_components(footprint_mask)

    outer_subpaths: list[list[tuple[int, int]]] = []

    # Process each footprint component (usually just 1 large one)
    for lbl in range(1, fp_n + 1):
        comp_mask = (fp_labels == lbl)
        comp_area = int(comp_mask.sum())
        if comp_area < min_area_px:
            continue

        comp_ys, comp_xs = np.where(comp_mask)
        # Topmost-leftmost pixel = guaranteed outer boundary pixel
        top_idx = int(np.argmin(comp_ys * w + comp_xs))
        sr, sc = int(comp_ys[top_idx]), int(comp_xs[top_idx])

        # Trace outer boundary; entry direction = came from left (dir_start=4)
        contour = _trace_boundary(comp_mask, sr, sc, dir_start=4)
        if len(contour) < 4:
            continue

        simplified = _dp_simplify(contour, dp_epsilon)
        if len(simplified) < 3:
            continue

        poly_area = _polygon_area_rc(simplified)
        if poly_area < min_area_px:
            continue

        outer_subpaths.append(simplified)

    # Sort outer subpaths largest first
    outer_subpaths.sort(key=_polygon_area_rc, reverse=True)

    # ── Step 4: Interior room subpaths ───────────────────────────────────
    interior_subpaths: list[list[tuple[int, int]]] = []

    for region in interior_regions:
        rys, rxs = np.where(region)
        top_idx = int(np.argmin(rys * w + rxs))
        ir, ic = int(rys[top_idx]), int(rxs[top_idx])

        # Trace boundary of the room (treating room pixels as foreground).
        # Topmost-leftmost pixel: the pixel above is NOT in the region, so
        # we "entered" by moving down from above.  Backtrack direction =
        # pointing back up = index 6 in _DIRS8 ((-1, 0) = up).
        room_boundary = _trace_boundary(region, ir, ic, dir_start=6)
        if len(room_boundary) < 4:
            continue

        room_simplified = _dp_simplify(room_boundary, dp_epsilon)
        if len(room_simplified) < 3:
            continue

        room_poly_area = _polygon_area_rc(room_simplified)
        if room_poly_area < min_area_px:
            continue

        interior_subpaths.append(room_simplified)

    # Sort interiors descending by area
    interior_subpaths.sort(key=_polygon_area_rc, reverse=True)

    return outer_subpaths + interior_subpaths


# ══════════════════════════════════════════════════════════════════════════════
# Opening (rect) and light extraction
# ══════════════════════════════════════════════════════════════════════════════

_MARKER_MAX_SIZE_PX = 40  # px; green squares larger than this are patio doors


def _classify_green_component(bbox: dict, wall_mask: np.ndarray) -> str:
    """Decide if a green component is a corner marker or patio door.

    A component is a corner *marker* if:
      • Its bounding box is ≤ ``_MARKER_MAX_SIZE_PX`` px in BOTH axes, AND
      • No black wall pixel exists within a 5-pixel neighbourhood.
    Otherwise it is a patio door (large, or adjacent to a wall).
    """
    h = bbox["ymax"] - bbox["ymin"] + 1
    w = bbox["xmax"] - bbox["xmin"] + 1
    if h > _MARKER_MAX_SIZE_PX or w > _MARKER_MAX_SIZE_PX:
        return "patio_door"
    # Check neighbourhood for wall pixels
    ymin = max(0, bbox["ymin"] - 5)
    ymax = min(wall_mask.shape[0] - 1, bbox["ymax"] + 5)
    xmin = max(0, bbox["xmin"] - 5)
    xmax = min(wall_mask.shape[1] - 1, bbox["xmax"] + 5)
    region = wall_mask[ymin:ymax + 1, xmin:xmax + 1]
    if region.any():
        return "patio_door"
    return "marker"


def _components_to_rects(bboxes: list[dict], scale: float
                         ) -> list[tuple[float, float, float, float]]:
    """Convert component bboxes to (cx, cy, width, height) in scaled units."""
    out = []
    for b in bboxes:
        cx = (b["xmin"] + b["xmax"]) / 2.0 * scale
        cy = (b["ymin"] + b["ymax"]) / 2.0 * scale
        w  = (b["xmax"] - b["xmin"] + 1) * scale
        h  = (b["ymax"] - b["ymin"] + 1) * scale
        out.append((cx, cy, w, h))
    return out


def _components_to_circles(bboxes: list[dict], scale: float
                            ) -> list[tuple[float, float, float]]:
    """Convert component bboxes to (cx, cy, r) in scaled units."""
    out = []
    for b in bboxes:
        cx = (b["xmin"] + b["xmax"]) / 2.0 * scale
        cy = (b["ymin"] + b["ymax"]) / 2.0 * scale
        # Radius estimated from the bounding box diagonal / 2
        r_from_bbox = math.hypot(
            b["xmax"] - b["xmin"] + 1,
            b["ymax"] - b["ymin"] + 1
        ) / 4.0 * scale
        out.append((cx, cy, r_from_bbox))
    return out


# ══════════════════════════════════════════════════════════════════════════════
# SVG generation helpers
# ══════════════════════════════════════════════════════════════════════════════

def _path_d_from_subpaths(subpaths: list[list[tuple[int, int]]],
                           scale: float) -> str:
    """Build the SVG ``d`` attribute from a list of pixel polygons.

    Each subpath is a closed polygon in (row, col) pixel order.
    We scale to SVG units (col → x, row → y) and emit M + L + Z sequences.
    """
    parts = []
    for poly in subpaths:
        if not poly:
            continue
        # (row, col) → (x=col*scale, y=row*scale)
        r0, c0 = poly[0]
        pts_str = (
            f"M {c0 * scale:.2f} {r0 * scale:.2f} " +
            " ".join(
                f"L {c * scale:.2f} {r * scale:.2f}"
                for r, c in poly[1:]
            ) +
            " Z"
        )
        parts.append(pts_str)
    return " ".join(parts)


def _svg_rect(cx: float, cy: float, w: float, h: float, fill: str) -> str:
    x = cx - w / 2.0
    y = cy - h / 2.0
    return (
        f'<rect x="{x:.2f}" y="{y:.2f}" '
        f'width="{w:.2f}" height="{h:.2f}" '
        f'fill="{fill}"/>'
    )


def _svg_circle(cx: float, cy: float, r: float, fill: str) -> str:
    return (
        f'<circle cx="{cx:.2f}" cy="{cy:.2f}" '
        f'r="{r:.2f}" fill="{fill}"/>'
    )


# ══════════════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════════════

def png_to_svg(png_path: str, out_svg_path: str, *,
               cm_per_pixel: float | None = None) -> dict:
    """Convert a coloured floor-plan PNG into a synthetic SVG that the
    existing svg_to_home pipeline can consume.

    Parameters
    ----------
    png_path:
        Path to the source colour-coded PNG floor plan.
    out_svg_path:
        Destination path for the generated synthetic SVG.
    cm_per_pixel:
        Physical scale.  If ``None``, defaults to ``1.0`` (1 pixel = 1 cm),
        which matches the user's SVG export convention where the SVG width
        in user units equals the PNG width in pixels.

    Returns
    -------
    dict with keys:
        width_px, height_px, cm_per_pixel,
        walls_extracted, openings, lights, markers,
        red_doors, magenta_doors, windows, patio_doors, skylights
    """
    # ── Load image ─────────────────────────────────────────────────────────
    img = Image.open(png_path)
    arr = _to_rgb(img)
    H, W = arr.shape[:2]

    # ── Default scale: 1 px → 1 cm ─────────────────────────────────────────
    # The user's PNGs are exported at 1:1 pixel-to-SVG-unit ratio and the
    # SVG coordinate system uses cm as its native unit.
    scale = float(cm_per_pixel) if cm_per_pixel is not None else 1.0

    # ── Colour masks ───────────────────────────────────────────────────────
    black    = _black_mask(arr)
    red      = _red_mask(arr)
    magenta  = _magenta_mask(arr)
    blue     = _blue_mask(arr)
    cyan     = _cyan_mask(arr)
    yellow   = _yellow_mask(arr)
    pg       = _pure_green_mask(arr)
    mk_green = _marker_green_mask(arr)

    # ── Wall mask for contour tracing: add opening pixels to close gaps ─
    # Openings (doors/windows) replace wall pixels with their own color,
    # creating gaps in the black wall region.  For contour tracing we want
    # to "close" these gaps so rooms appear as fully enclosed white regions.
    # We treat all opening pixels (except lights, markers) as wall-equivalent.
    wall_closed = (
        black | red | magenta | blue | cyan |
        (_pure_green_mask(arr) & ~_marker_green_mask(arr))
    )
    # Note: we still use `black` for the actual wall rect/path output,
    # but use `wall_closed` for the contour-tracing step.

    # ── Connected components ───────────────────────────────────────────────
    # Minimum areas chosen to suppress anti-aliasing specks while keeping
    # the smallest real openings (narrow magenta door ≈ 5×60 px = 300 px²)
    red_bboxes     = _component_bboxes(red,     min_area=50)
    magenta_bboxes = _component_bboxes(magenta, min_area=50)
    blue_bboxes    = _component_bboxes(blue,    min_area=50)
    cyan_bboxes    = _component_bboxes(cyan,    min_area=50)
    yellow_bboxes  = _component_bboxes(yellow,  min_area=50)

    # Pure green: split into corner markers vs patio doors
    pg_bboxes = _component_bboxes(pg, min_area=20)
    patio_bboxes: list[dict] = []
    pg_marker_bboxes: list[dict] = []
    for b in pg_bboxes:
        kind = _classify_green_component(b, black)
        if kind == "marker":
            pg_marker_bboxes.append(b)
        else:
            patio_bboxes.append(b)

    # Explicit #55d400 corner-marker-green components — always markers
    explicit_marker_bboxes = _component_bboxes(mk_green, min_area=20)

    all_marker_bboxes = pg_marker_bboxes + explicit_marker_bboxes

    # ── Wall contour tracing ───────────────────────────────────────────────
    # Use wall_closed (black + colored openings) for room detection so
    # doors/windows don't create gaps that break the enclosed-room logic.
    # Drop noise/text components: minimum 400 px² (≈ 20×20 px blob).
    wall_subpaths_px = _extract_wall_subpaths(
        wall_closed,
        dp_epsilon=2.5,
        min_area_px=400.0,
    )

    # ── Build SVG ──────────────────────────────────────────────────────────
    # The SVG uses bare numbers (no unit suffix) so 1 SVG unit = 1 cm.
    # The pipeline's detect_svg_unit_scale() returns 1.0 for bare-number widths.
    svg_w = W * scale
    svg_h = H * scale

    lines: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg"',
        f'     width="{svg_w:.4f}" height="{svg_h:.4f}"',
        f'     viewBox="0 0 {svg_w:.4f} {svg_h:.4f}">',
    ]

    # Wall path — fill-rule evenodd so interior holes (rooms) render white.
    # Largest subpath first = outer building envelope (as collect_wall_subpaths expects).
    if wall_subpaths_px:
        d = _path_d_from_subpaths(wall_subpaths_px, scale)
        lines.append(f'  <path fill-rule="evenodd" fill="#000000" d="{d}"/>')

    # Opening rects
    for cx, cy, w, h in _components_to_rects(red_bboxes, scale):
        lines.append(f'  {_svg_rect(cx, cy, w, h, "#ff0000")}')

    for cx, cy, w, h in _components_to_rects(magenta_bboxes, scale):
        lines.append(f'  {_svg_rect(cx, cy, w, h, "#ff00ff")}')

    for cx, cy, w, h in _components_to_rects(blue_bboxes, scale):
        lines.append(f'  {_svg_rect(cx, cy, w, h, "#0000ff")}')

    for cx, cy, w, h in _components_to_rects(patio_bboxes, scale):
        lines.append(f'  {_svg_rect(cx, cy, w, h, "#00ff00")}')

    for cx, cy, w, h in _components_to_rects(cyan_bboxes, scale):
        lines.append(f'  {_svg_rect(cx, cy, w, h, "#00ffff")}')

    # Light circles
    for cx, cy, r in _components_to_circles(yellow_bboxes, scale):
        lines.append(f'  {_svg_circle(cx, cy, r, "#ffff00")}')

    # Corner markers — emit as #55d400 rects so the pipeline's align.py
    # can pick them up via extract_corner_markers().
    for cx, cy, w, h in _components_to_rects(all_marker_bboxes, scale):
        lines.append(f'  {_svg_rect(cx, cy, w, h, "#55d400")}')

    lines.append("</svg>")

    # ── Write file ─────────────────────────────────────────────────────────
    svg_content = "\n".join(lines)
    with open(out_svg_path, "w", encoding="utf-8") as fh:
        fh.write(svg_content)

    # ── Metadata ───────────────────────────────────────────────────────────
    n_openings = (
        len(red_bboxes) + len(magenta_bboxes) + len(blue_bboxes) +
        len(patio_bboxes) + len(cyan_bboxes)
    )
    meta = {
        "width_px":        W,
        "height_px":       H,
        "cm_per_pixel":    scale,
        "walls_extracted": len(wall_subpaths_px),
        "openings":        n_openings,
        "lights":          len(yellow_bboxes),
        "markers":         len(all_marker_bboxes),
        "red_doors":       len(red_bboxes),
        "magenta_doors":   len(magenta_bboxes),
        "windows":         len(blue_bboxes),
        "patio_doors":     len(patio_bboxes),
        "skylights":       len(cyan_bboxes),
    }

    print(
        f"[png_import] {png_path}: {W}x{H}px  scale={scale:.3f}cm/px  "
        f"wall_subpaths={len(wall_subpaths_px)}  openings={n_openings}  "
        f"lights={len(yellow_bboxes)}  markers={len(all_marker_bboxes)}",
        file=sys.stderr,
    )
    return meta
