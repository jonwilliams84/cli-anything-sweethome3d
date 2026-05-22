"""Cross-floor alignment helpers: green-marker extraction, Procrustes
fit, and SVG-unit auto-detection.

Markers are small ``#55d400`` rects the user places at known intersecting
X/Y reference points on each floor. With at least two pairs we can derive
a uniform scale + translation that aligns one floor's coords onto a
canonical floor's — independent of the SVG's stated units.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Optional

from cli_anything.sweethome3d.core.svg.parse import (
    IDENT,
    apply,
    classify_fill,
    mul,
    parse_transform,
)


CORNER_MARKER = "#55d400"  # bright green squares the user places at corner refs


def extract_corner_markers(svg_root: ET.Element) -> list[tuple[float, float, float, float]]:
    """Return list of (xMin, yMin, xMax, yMax) for ``#55d400`` rects.

    These are explicit user-placed reference points indicating known
    intersecting X/Y corners. We use their bounding box as the floor's
    anchor and (per-floor) scale source — much more reliable than
    inferring extents from the wall path.
    """
    out: list[tuple[float, float, float, float]] = []

    def visit(el: ET.Element, parent_xform):
        my_xform = mul(parent_xform, parse_transform(el.get("transform", "")))
        if classify_fill(el) == CORNER_MARKER:
            if el.tag == "rect":
                x = float(el.get("x", 0)); y = float(el.get("y", 0))
                w = float(el.get("width", 0)); h = float(el.get("height", 0))
                ax, ay = apply(my_xform, x, y)
                bx, by = apply(my_xform, x + w, y + h)
                xmin, xmax = min(ax, bx), max(ax, bx)
                ymin, ymax = min(ay, by), max(ay, by)
                out.append((xmin, ymin, xmax, ymax))
            elif el.tag == "path":
                # Inkscape's compressed export emits marker rects as paths;
                # walk the path's line segments and use the axis-aligned bbox.
                from cli_anything.sweethome3d.core.svg.parse import (
                    parse_path, walk_path,
                )
                # Split into subpaths at each M/m so each marker square is
                # its own bbox (one compound path may carry several).
                cmds = parse_path(el.get("d", ""))
                subs: list[list] = []
                cur: list = []
                for cmd, args in cmds:
                    if cmd in ("M", "m") and cur:
                        subs.append(cur); cur = []
                    cur.append((cmd, args))
                if cur:
                    subs.append(cur)
                for sub in subs:
                    segs = walk_path(sub)
                    if not segs:
                        continue
                    xs = [v for s in segs for v in (s[0], s[2])]
                    ys = [v for s in segs for v in (s[1], s[3])]
                    minx, maxx = min(xs), max(xs)
                    miny, maxy = min(ys), max(ys)
                    if maxx <= minx or maxy <= miny:
                        continue
                    ax, ay = apply(my_xform, minx, miny)
                    bx, by = apply(my_xform, maxx, maxy)
                    out.append((min(ax, bx), min(ay, by),
                                 max(ax, bx), max(ay, by)))
        for child in el:
            visit(child, my_xform)

    visit(svg_root, IDENT)
    return out


def fit_uniform_affine(src: list[tuple[float, float]],
                        dst: list[tuple[float, float]]
                        ) -> tuple[float, float, float]:
    """Closed-form least-squares fit of ``target = s * source + (tx, ty)``.

    Used to align one floor's green-marker centres onto the canonical
    floor's markers — uniform scale (no rotation, no shear) is enough
    because all floors share the same axes, only the SVG's unit/scale
    convention differs.

    With one pair we can only compute translation: scale defaults to 1.
    With two or more pairs the scale is the standard Procrustes ratio.
    """
    n = len(src)
    if n != len(dst) or n == 0:
        return 1.0, 0.0, 0.0
    sx = sum(p[0] for p in src) / n
    sy = sum(p[1] for p in src) / n
    dx = sum(p[0] for p in dst) / n
    dy = sum(p[1] for p in dst) / n
    if n == 1:
        return 1.0, dx - sx, dy - sy
    num = sum((src[i][0] - sx) * (dst[i][0] - dx)
               + (src[i][1] - sy) * (dst[i][1] - dy)
               for i in range(n))
    den = sum((src[i][0] - sx) ** 2 + (src[i][1] - sy) ** 2 for i in range(n))
    s = num / den if den > 1e-12 else 1.0
    tx = dx - s * sx
    ty = dy - s * sy
    return s, tx, ty


def detect_svg_unit_scale(root: ET.Element) -> float:
    """Pick a user-unit → centimetre scale based on the SVG declaration.

    Two common shapes appear in practice:
      * Width given as bare number (or ``"px"``). Inkscape
        "document-units: cm" files use this with the path data already
        in cm. Scale = 1.
      * Width given in ``mm`` with a matching viewBox, drawn at a
        standard 1:50 architectural scale (1 mm on paper = 5 cm in
        real life). Scale = 5.
    Anything ambiguous falls back to 1 — better to import small than
    silently rescale by the wrong amount.
    """
    width = (root.get("width") or "").strip()
    if re.match(r"^[\d.]+\s*mm$", width):
        return 5.0
    return 1.0


def apply_unit_scale(root: ET.Element, scale: float) -> None:
    """Prepend a uniform scale to the SVG root's transform so all
    downstream coordinate extractors see scaled values.

    Works because every extractor composes the parent transform onto
    each element's own transform; adding ``scale(s)`` on the root
    applies ``s`` as the last operation in the chain (i.e. multiplies
    every final coordinate by ``s``).
    """
    if scale == 1.0:
        return
    existing = root.get("transform", "")
    root.set("transform", (f"scale({scale}) {existing}").strip())
