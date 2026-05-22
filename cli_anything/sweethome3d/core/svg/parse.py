"""SVG path parsing, fill classification, and 2D-affine transform helpers.

Path tokenizer + line walker handle the common SVG commands (M/m/L/l/H/h/V/v/Z/z
and Bezier/quadratic curves approximated by their endpoints — adequate for
floorplans where curves are minor authoring artefacts).

Transforms compose left-to-right: an element's effective matrix is the
product of its ancestors' transforms with its own. All other modules use
``apply()`` to resolve a local-coord point to absolute coords.
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from typing import Optional


# ──────────────────────────────────────────────────────── SVG path parsing

PATH_ARGS = {
    "M": 2, "m": 2, "L": 2, "l": 2,
    "H": 1, "h": 1, "V": 1, "v": 1,
    "Z": 0, "z": 0,
    "C": 6, "c": 6, "S": 4, "s": 4,
    "Q": 4, "q": 4, "T": 2, "t": 2,
    "A": 7, "a": 7,
}


def parse_path(d: str) -> list[tuple[str, list[float]]]:
    """Tokenize an SVG `d` attribute into (cmd, args) pairs."""
    # Numbers: integer with optional decimal (123, 123.45, 123.) OR
    # leading-dot decimal (.71). Both forms may be negative or have
    # an exponent. Inkscape's compressed export uses the leading-dot
    # form heavily to save bytes.
    tokens = re.findall(
        r"[A-Za-z]|-?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?",
        d,
    )
    out: list[tuple[str, list[float]]] = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t.isalpha():
            cmd = t
            i += 1
            n = PATH_ARGS.get(cmd, 0)
            if n == 0:
                out.append((cmd, []))
                continue
            first = True
            while i + n <= len(tokens) and not tokens[i].isalpha():
                out.append((cmd, [float(x) for x in tokens[i:i + n]]))
                # Repeated M/m flows into L/l for subsequent coordinate pairs.
                if first and cmd == "M":
                    cmd = "L"
                elif first and cmd == "m":
                    cmd = "l"
                first = False
                i += n
        else:
            i += 1
    return out


def walk_path(cmds: list[tuple[str, list[float]]]) -> list[tuple[float, float, float, float]]:
    """Return all line-equivalent segments of the path.

    Bezier/arc curves are approximated by a straight line between the
    current point and the segment's endpoint — adequate for floorplans
    where curves are minor Inkscape artefacts of nominally straight walls.
    """
    x = y = 0.0
    start_x = start_y = 0.0
    segs: list[tuple[float, float, float, float]] = []
    for cmd, args in cmds:
        if cmd == "M":
            x, y = args
            start_x, start_y = x, y
        elif cmd == "m":
            x += args[0]; y += args[1]
            start_x, start_y = x, y
        elif cmd == "L":
            segs.append((x, y, args[0], args[1]))
            x, y = args[0], args[1]
        elif cmd == "l":
            x2, y2 = x + args[0], y + args[1]
            segs.append((x, y, x2, y2))
            x, y = x2, y2
        elif cmd == "H":
            segs.append((x, y, args[0], y)); x = args[0]
        elif cmd == "h":
            x2 = x + args[0]; segs.append((x, y, x2, y)); x = x2
        elif cmd == "V":
            segs.append((x, y, x, args[0])); y = args[0]
        elif cmd == "v":
            y2 = y + args[0]; segs.append((x, y, x, y2)); y = y2
        elif cmd in ("Z", "z"):
            if (x, y) != (start_x, start_y):
                segs.append((x, y, start_x, start_y))
            x, y = start_x, start_y
        elif cmd in ("C", "S", "Q"):
            x2, y2 = args[-2], args[-1]
            segs.append((x, y, x2, y2)); x, y = x2, y2
        elif cmd in ("c", "s", "q"):
            x2, y2 = x + args[-2], y + args[-1]
            segs.append((x, y, x2, y2)); x, y = x2, y2
    return segs


# ──────────────────────────────────────────────────────── colour utilities

def style_value(style: str, key: str) -> Optional[str]:
    m = re.search(rf"{re.escape(key)}\s*:\s*([^;]+)", style)
    return m.group(1).strip().lower() if m else None


def classify_fill(el: ET.Element) -> Optional[str]:
    """Return the element's fill colour as a normalised lowercase #rrggbb.

    Expands short 3-digit hex (``#f0f`` → ``#ff00ff``) which Inkscape's
    compressed export emits to save bytes.
    """
    fill = el.get("fill") or style_value(el.get("style", ""), "fill")
    if fill is None or fill == "none":
        return None
    fill = fill.lower().strip()
    # Expand 3-digit hex (#rgb) to 6-digit hex (#rrggbb)
    if re.fullmatch(r"#[0-9a-f]{3}", fill):
        fill = "#" + "".join(c * 2 for c in fill[1:])
    return fill


def is_wall_fill(el: ET.Element) -> bool:
    """A path/rect counts as a wall if it's drawn in solid black.

    Includes the SVG default: when no ``fill`` attribute and no ``fill:``
    style is given, SVG renders black. Some authoring tools (Inkscape)
    omit ``fill`` for elements intended to render as default-black walls.
    """
    fill_attr = el.get("fill")
    style_fill = style_value(el.get("style", ""), "fill")
    if fill_attr is None and style_fill is None:
        return True
    fill = (fill_attr or style_fill or "").lower()
    return fill == "#000000"


def strip_ns(el: ET.Element) -> None:
    """Strip XML namespace prefixes from `el` and all its descendants.

    Lets us write ``el.tag == 'path'`` instead of
    ``el.tag.endswith('}path')`` after calling this once on the root.
    """
    if "}" in el.tag:
        el.tag = el.tag.split("}", 1)[1]
    for c in el:
        strip_ns(c)


# ──────────────────────────────────────────────────────── transform composition

# Affine 2x3 matrix represented as a 6-tuple (a, b, c, d, e, f) such that
#   [x'] = [a c e] [x]
#   [y']   [b d f] [y]
#   [1 ]   [0 0 1] [1]
IDENT = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def mul(m1, m2):
    a1, b1, c1, d1, e1, f1 = m1
    a2, b2, c2, d2, e2, f2 = m2
    return (
        a1 * a2 + c1 * b2,        b1 * a2 + d1 * b2,
        a1 * c2 + c1 * d2,        b1 * c2 + d1 * d2,
        a1 * e2 + c1 * f2 + e1,   b1 * e2 + d1 * f2 + f1,
    )


def parse_transform(spec: str):
    """Parse an SVG ``transform="..."`` attribute into a 2x3 matrix."""
    if not spec:
        return IDENT
    m = IDENT
    for fn, args in re.findall(r"(translate|matrix|scale|rotate)\(([^)]+)\)", spec):
        nums = [float(x) for x in re.findall(r"-?\d+\.?\d*(?:[eE][+-]?\d+)?", args)]
        if fn == "translate":
            tx, ty = nums[0], nums[1] if len(nums) > 1 else 0.0
            m = mul(m, (1, 0, 0, 1, tx, ty))
        elif fn == "scale":
            sx = nums[0]; sy = nums[1] if len(nums) > 1 else sx
            m = mul(m, (sx, 0, 0, sy, 0, 0))
        elif fn == "matrix":
            m = mul(m, tuple(nums[:6]))
        elif fn == "rotate":
            # rotate(angle [, cx, cy]) — angle in degrees
            ang = math.radians(nums[0])
            cos_a, sin_a = math.cos(ang), math.sin(ang)
            rot = (cos_a, sin_a, -sin_a, cos_a, 0.0, 0.0)
            if len(nums) >= 3:
                cx, cy = nums[1], nums[2]
                rot = mul(mul((1, 0, 0, 1, cx, cy), rot), (1, 0, 0, 1, -cx, -cy))
            m = mul(m, rot)
    return m


def apply(m, x: float, y: float) -> tuple[float, float]:
    a, b, c, d, e, f = m
    return (a * x + c * y + e, b * x + d * y + f)
