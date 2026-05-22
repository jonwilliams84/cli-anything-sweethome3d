"""Door / window / skylight / light extraction from coloured SVG rects.

Each opening is a coloured rect on top of the wall path. The fill colour
maps to a ``kind`` (external_door, internal_door, patio_door, window,
skylight). Lights are yellow circles.

Plus two helpers that depend on opening geometry:

* ``drop_walls_inside_openings`` — removes phantom walls that
  ``pair_edges`` extracted from the rect's own outline.
* ``snap_opening_to_wall`` — projects an opening's centre onto the
  nearest aligned wall so SH3D's auto-bind treats it as embedded.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from typing import Optional

from cli_anything.sweethome3d.core.svg.parse import (
    IDENT,
    apply,
    classify_fill,
    mul,
    parse_transform,
)


DOOR_RED = "#ff0000"
DOOR_MAGENTA = "#ff00ff"
DOOR_GREEN = "#00ff00"
WINDOW_BLUE = "#0000ff"
SKYLIGHT_CYAN = "#00ffff"
LIGHT_YELLOW = "#ffff00"


def rect_center_local(r: ET.Element) -> tuple[float, float, float, float, float]:
    """Return ``(cx, cy, width, depth, angle)`` for an SVG rect in
    *local* coords. ``width`` is the rect's long dimension (along the
    wall), ``depth`` is the short dimension. ``angle`` is 0 for
    horizontal rects (long axis along X) or π/2 for vertical rects.
    """
    x = float(r.get("x", 0))
    y = float(r.get("y", 0))
    w = float(r.get("width", 0))
    h = float(r.get("height", 0))
    cx, cy = x + w / 2, y + h / 2
    if w >= h:
        return cx, cy, w, h, 0.0
    return cx, cy, h, w, math.pi / 2


def extract_openings(svg_root: ET.Element):
    """Return list of ``(kind, cx, cy, width, depth, angle, fill)``.

    Coordinates are in absolute SVG units after composing every
    ancestor transform. ``kind`` is one of: ``external_door``,
    ``internal_door``, ``patio_door``, ``window``, ``skylight``.
    """
    out = []
    kinds = {
        DOOR_RED: "external_door",
        DOOR_MAGENTA: "internal_door",
        DOOR_GREEN: "patio_door",
        WINDOW_BLUE: "window",
        SKYLIGHT_CYAN: "skylight",
    }

    def visit(el: ET.Element, parent_xform):
        my_xform = mul(parent_xform, parse_transform(el.get("transform", "")))
        if el.tag == "rect":
            fill = classify_fill(el)
            if fill in kinds:
                cx, cy, w, d, angle = rect_center_local(el)
                cx, cy = apply(my_xform, cx, cy)
                a, b, c, d_, _, _ = my_xform
                scale = math.hypot(a, b)
                out.append((kinds[fill], cx, cy,
                             w * scale, d * scale, angle, fill))
        elif el.tag == "path":
            # Inkscape's compressed export emits opening rects as paths.
            # A single coloured path can contain MULTIPLE openings as
            # subpaths (each starting with M/m).  Split per subpath and
            # emit one opening per shape; fitting one bbox to all of them
            # would capture the whole drawing as one giant "opening".
            fill = classify_fill(el)
            if fill in kinds:
                from cli_anything.sweethome3d.core.svg.parse import (
                    parse_path, walk_path,
                )
                cmds = parse_path(el.get("d", ""))
                # Split commands at each M/m into subpath chunks.
                subpaths: list[list] = []
                cur: list = []
                for cmd, args in cmds:
                    if cmd in ("M", "m") and cur:
                        subpaths.append(cur)
                        cur = []
                    cur.append((cmd, args))
                if cur:
                    subpaths.append(cur)
                a, b, c, d_, _, _ = my_xform
                scale = math.hypot(a, b)
                for sub in subpaths:
                    segs = walk_path(sub)
                    if not segs:
                        continue
                    xs = [v for s in segs for v in (s[0], s[2])]
                    ys = [v for s in segs for v in (s[1], s[3])]
                    minx, maxx = min(xs), max(xs)
                    miny, maxy = min(ys), max(ys)
                    w, h = maxx - minx, maxy - miny
                    if w <= 0 or h <= 0:
                        continue
                    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
                    cx, cy = apply(my_xform, cx, cy)
                    if w >= h:
                        out.append((kinds[fill], cx, cy,
                                     w * scale, h * scale, 0.0, fill))
                    else:
                        out.append((kinds[fill], cx, cy,
                                     h * scale, w * scale, math.pi / 2, fill))
        for child in el:
            visit(child, my_xform)

    visit(svg_root, IDENT)
    return out


def extract_lights(svg_root: ET.Element):
    """Return list of ``(cx, cy, radius)`` for yellow circles."""
    out = []

    def visit(el: ET.Element, parent_xform):
        my_xform = mul(parent_xform, parse_transform(el.get("transform", "")))
        if el.tag == "circle" and classify_fill(el) == LIGHT_YELLOW:
            cx = float(el.get("cx", 0))
            cy = float(el.get("cy", 0))
            r = float(el.get("r", 10))
            cx, cy = apply(my_xform, cx, cy)
            out.append((cx, cy, r))
        for child in el:
            visit(child, my_xform)

    visit(svg_root, IDENT)
    return out


def drop_walls_inside_openings(walls, openings, *, margin: float = 10.0):
    """Drop walls running PERPENDICULAR to an opening whose midpoint
    falls inside the opening's plan bbox.

    Edge-pair extraction sees the two short vertical edges at a small
    window's left/right sides as parallel "wall faces" and pairs them
    into a spurious wall whose thickness equals the window width.
    """
    bboxes: list[tuple[bool, float, float, float, float]] = []
    for kind, cx, cy, ow, od, ang, _fill in openings:
        if kind == "skylight":
            continue
        op_h = abs(ang) < 0.1 or abs(abs(ang) - math.pi) < 0.1
        if op_h:
            bbox = (cx - ow / 2 - margin, cy - od / 2 - margin,
                    cx + ow / 2 + margin, cy + od / 2 + margin)
        else:
            bbox = (cx - od / 2 - margin, cy - ow / 2 - margin,
                    cx + od / 2 + margin, cy + ow / 2 + margin)
        bboxes.append((op_h, *bbox))

    out = []
    for xs, ys, xe, ye, t in walls:
        mx, my = (xs + xe) / 2, (ys + ye) / 2
        wall_h = abs(ye - ys) < 1.0
        wall_v = abs(xe - xs) < 1.0
        keep = True
        for op_h, bx0, by0, bx1, by1 in bboxes:
            if op_h and not wall_v:
                continue
            if not op_h and not wall_h:
                continue
            if bx0 <= mx <= bx1 and by0 <= my <= by1:
                keep = False
                break
        if keep:
            out.append((xs, ys, xe, ye, t))
    return out


def snap_opening_to_wall(cx: float, cy: float, opening_angle: float,
                            opening_width: float,
                            walls, *, max_perp_distance: float = 80.0
                            ) -> Optional[tuple[float, float, float, float, float, float, float]]:
    """Project a door/window centre onto the nearest wall's centreline.

    Returns ``(snapped_cx, snapped_cy, wall_thickness, wall_angle,
               wall_length, left_offset, top_offset)`` if a suitably-aligned
    wall is found within ``max_perp_distance``.

    * ``wall_length``  — full length of the host wall (cm)
    * ``left_offset``  — distance along the wall from the wall's start to the
                         door's left edge (cm), clamped to [0, wall_length]
    * ``top_offset``   — always 0.0 for SVG import (doors hang from soffit)

    A horizontal-rect door (angle ≈ 0) snaps only to horizontal walls;
    vertical (angle ≈ π/2) only to vertical walls.

    Tie-breaking rules (most important first):
      1. Direction match (horiz/vert) — enforced as a hard filter.
      2. Wall must be long enough to host the opening (wall_length ≥
         opening_width − 5 cm); too-short walls are rejected.
      3. Smallest perpendicular distance wins.
      4. Among equal-perp candidates, largest wall_length wins (favours
         the main span at T-junctions over the short stub).
    """
    is_horiz = abs(opening_angle) < 0.1 or abs(abs(opening_angle) - math.pi) < 0.1
    is_vert = abs(abs(opening_angle) - math.pi / 2) < 0.1
    # best stores (perp, -wall_length, px, py, t, wall_angle, L, left_offset, top_offset)
    # sorting by (perp ASC, -L ASC) gives smallest-perp then largest-L
    best: Optional[tuple] = None
    for xs, ys, xe, ye, t in walls:
        dx, dy = xe - xs, ye - ys
        L = math.hypot(dx, dy)
        if L < 1.0:
            continue
        wall_h = abs(dy) < 1.0
        wall_v = abs(dx) < 1.0
        if is_horiz and not wall_h:
            continue
        if is_vert and not wall_v:
            continue
        # Reject walls that are too short to host this opening.
        if L < opening_width - 5.0:
            continue
        u = ((cx - xs) * dx + (cy - ys) * dy) / (L * L)
        if u < -0.1 or u > 1.1:
            continue
        u_clamped = max(0.0, min(1.0, u))
        px, py = xs + u_clamped * dx, ys + u_clamped * dy
        perp = math.hypot(cx - px, cy - py)
        if perp > max_perp_distance:
            continue
        wall_angle = 0.0 if wall_h else math.pi / 2
        half_w = opening_width / 2.0
        left_offset = max(0.0, min(L, u_clamped * L - half_w))
        # Tie-break: prefer smallest perp, then largest L (negate for min-heap logic)
        candidate = (perp, -L, px, py, t, wall_angle, L, left_offset, 0.0)
        if best is None or (perp, -L) < (best[0], best[1]):
            best = candidate
    if best is None:
        return None
    _, _neg_L, px, py, t, wall_angle, wall_length, left_offset, top_offset = best
    return px, py, t, wall_angle, wall_length, left_offset, top_offset
