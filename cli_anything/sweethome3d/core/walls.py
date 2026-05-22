"""Wall operations — add, find, move, set properties, connect."""

from __future__ import annotations

import math
from typing import Optional

from cli_anything.sweethome3d.core.model import Home, Wall, Texture


def list_walls(home: Home, *, level: Optional[str] = None) -> list[Wall]:
    walls = home.walls
    if level is not None:
        walls = [w for w in walls if w.level == level]
    return list(walls)


def add_wall(home: Home, xStart: float, yStart: float, xEnd: float, yEnd: float,
              *, thickness: float = 7.5, height: Optional[float] = None,
              level: Optional[str] = None,
              leftSideColor: Optional[int] = None,
              rightSideColor: Optional[int] = None,
              pattern: Optional[str] = None,
              leftSideTexture: Optional[Texture] = None,
              rightSideTexture: Optional[Texture] = None) -> Wall:
    """Add a wall and return it. Length 0 is rejected."""
    if xStart == xEnd and yStart == yEnd:
        raise ValueError("wall start and end coincide — zero-length wall")
    w = Wall(
        xStart=xStart, yStart=yStart, xEnd=xEnd, yEnd=yEnd,
        thickness=thickness,
        height=home.wallHeight if height is None else height,
        level=level,
        leftSideColor=leftSideColor,
        rightSideColor=rightSideColor,
        pattern=pattern if pattern is not None else "hatchUp",
        leftSideTexture=leftSideTexture,
        rightSideTexture=rightSideTexture,
    )
    home.walls.append(w)
    return w


def delete_wall(home: Home, ident: str) -> bool:
    w = home.find_wall(ident)
    if w is None:
        return False
    # detach any incoming references
    for other in home.walls:
        if other.wallAtStart == w.id:
            other.wallAtStart = None
        if other.wallAtEnd == w.id:
            other.wallAtEnd = None
    home.walls.remove(w)
    return True


def move_wall(home: Home, ident: str, *,
               xStart: Optional[float] = None, yStart: Optional[float] = None,
               xEnd: Optional[float] = None, yEnd: Optional[float] = None) -> Wall:
    w = home.find_wall(ident)
    if w is None:
        raise KeyError(ident)
    if xStart is not None: w.xStart = xStart
    if yStart is not None: w.yStart = yStart
    if xEnd   is not None: w.xEnd = xEnd
    if yEnd   is not None: w.yEnd = yEnd
    return w


def set_wall_properties(home: Home, ident: str, **fields) -> Wall:
    """Set arbitrary scalar properties on a wall."""
    w = home.find_wall(ident)
    if w is None:
        raise KeyError(ident)
    for k, v in fields.items():
        if not hasattr(w, k):
            raise AttributeError(f"unknown wall field: {k!r}")
        setattr(w, k, v)
    return w


def length(w: Wall) -> float:
    return math.hypot(w.xEnd - w.xStart, w.yEnd - w.yStart)


def project_onto_wall(w: Wall, x: float, y: float) -> tuple[float, float, float, float]:
    """Project (x, y) onto the wall's centerline.

    Returns (snapped_x, snapped_y, wall_angle, perpendicular_distance). The
    angle is the wall's direction in radians; doors/windows aligned to this
    sit flush along the wall.
    """
    dx = w.xEnd - w.xStart
    dy = w.yEnd - w.yStart
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return w.xStart, w.yStart, 0.0, math.hypot(x - w.xStart, y - w.yStart)
    t = ((x - w.xStart) * dx + (y - w.yStart) * dy) / L2
    t = max(0.0, min(1.0, t))   # clamp to segment
    sx = w.xStart + t * dx
    sy = w.yStart + t * dy
    return sx, sy, math.atan2(dy, dx), math.hypot(x - sx, y - sy)


def nearest_wall(home: Home, x: float, y: float, *,
                  level: Optional[str] = None,
                  max_distance: Optional[float] = None
                  ) -> Optional[tuple[Wall, float, float, float, float]]:
    """Find the wall closest to (x, y) and return placement data.

    Returns (wall, snapped_x, snapped_y, angle, distance), or None if no
    walls match (e.g. no walls on the given level, or all are beyond
    `max_distance` cm).
    """
    best: Optional[tuple[Wall, float, float, float, float]] = None
    for w in home.walls:
        if level is not None and w.level != level:
            continue
        sx, sy, ang, dist = project_onto_wall(w, x, y)
        if max_distance is not None and dist > max_distance:
            continue
        if best is None or dist < best[4]:
            best = (w, sx, sy, ang, dist)
    return best


def split_wall(home: Home, ident: str, *,
                 at_x: float, at_y: float,
                 endpoint_tol_cm: float = 1.0,
                 perp_tol_cm: float = 50.0) -> tuple[Wall, Wall]:
    """Split a wall at the point (at_x, at_y) projected onto its centerline.

    The original wall is replaced by two new walls (first half + second
    half). Properties are copied verbatim — thickness, height, textures,
    colours, baseboards, level, arc extent, shininess, all preserved.

    Neighbour links rewire as follows:
      - half1.wallAtStart = original.wallAtStart  (untouched outer corner)
      - half1.wallAtEnd   = half2.id              (new interior join)
      - half2.wallAtStart = half1.id              (new interior join)
      - half2.wallAtEnd   = original.wallAtEnd    (untouched outer corner)
    Walls that previously referenced the original via wallAtStart /
    wallAtEnd are rewired to whichever half they actually meet at.

    Raises:
      KeyError  — wall not found
      ValueError — split point is too close to an endpoint (≤ endpoint_tol_cm)
                   or too far from the centerline (> perp_tol_cm)
    """
    w = home.find_wall(ident)
    if w is None:
        raise KeyError(f"wall not found: {ident}")
    sx, sy, _, dist = project_onto_wall(w, at_x, at_y)
    if dist > perp_tol_cm:
        raise ValueError(
            f"split point ({at_x},{at_y}) is {dist:.1f} cm from the wall "
            f"centerline (> perp_tol_cm={perp_tol_cm}); refusing to split"
        )
    start_gap = math.hypot(sx - w.xStart, sy - w.yStart)
    end_gap   = math.hypot(sx - w.xEnd,   sy - w.yEnd)
    if start_gap < endpoint_tol_cm or end_gap < endpoint_tol_cm:
        raise ValueError(
            f"split point is within {endpoint_tol_cm} cm of an endpoint "
            f"(start={start_gap:.2f}, end={end_gap:.2f}); refusing to split"
        )

    # Build the two halves by deepcopying the original (preserves
    # textures, baseboards, colours, height, arcExtent, pattern, …).
    from copy import deepcopy
    from cli_anything.sweethome3d.core.model import _gen_id
    half1 = deepcopy(w)
    half2 = deepcopy(w)
    half1.id = _gen_id()
    half2.id = _gen_id()
    half1.xEnd, half1.yEnd     = sx, sy
    half2.xStart, half2.yStart = sx, sy
    # The original's outer neighbours stay attached to the matching half.
    half1.wallAtStart = w.wallAtStart
    half1.wallAtEnd   = half2.id
    half2.wallAtStart = half1.id
    half2.wallAtEnd   = w.wallAtEnd

    # Rewire any *other* wall that referenced the original's id.
    # Determine which endpoint of the other wall sits closer to which half
    # so the link points at the right new id.
    for other in home.walls:
        if other.id == w.id:
            continue
        for slot in ("wallAtStart", "wallAtEnd"):
            ref = getattr(other, slot)
            if ref != w.id:
                continue
            # Which end of `other` was joined to the original?
            ox, oy = (other.xStart, other.yStart) if slot == "wallAtStart" \
                       else (other.xEnd, other.yEnd)
            d_to_h1_start = math.hypot(ox - half1.xStart, oy - half1.yStart)
            d_to_h2_end   = math.hypot(ox - half2.xEnd,   oy - half2.yEnd)
            setattr(other, slot,
                    half1.id if d_to_h1_start <= d_to_h2_end else half2.id)

    # Swap the original out for the two halves at the same list position
    idx = home.walls.index(w)
    home.walls[idx:idx+1] = [half1, half2]
    return half1, half2


def join_walls(home: Home, first: str, second: str, *,
                 endpoint_tol_cm: float = 1.0,
                 angle_tol_deg: float = 2.0) -> Wall:
    """Fuse two walls that share an endpoint and lie on the same line.

    Result: a single wall spanning the outer endpoints of `first` and
    `second`. Properties are taken from `first` (thickness, height,
    textures, baseboards, …). Both walls must:
      - belong to the same level
      - share an endpoint within `endpoint_tol_cm`
      - have matching thickness and height (within 0.1 cm)
      - be collinear within `angle_tol_deg`

    Neighbour links: the surviving wall inherits the OUTER neighbours
    (the wall-link slots that *don't* point at the partner being merged).
    Walls that previously referenced either input by id are remapped to
    the survivor.

    Raises:
      KeyError   — either wall not found
      ValueError — preconditions fail (mismatched levels / properties /
                   non-collinear / no shared endpoint)
    """
    a = home.find_wall(first)
    b = home.find_wall(second)
    if a is None: raise KeyError(f"wall not found: {first}")
    if b is None: raise KeyError(f"wall not found: {second}")
    if a is b:
        raise ValueError("cannot join a wall to itself")
    if a.level != b.level:
        raise ValueError(
            f"walls are on different levels ({a.level!r} vs {b.level!r})"
        )
    if abs(a.thickness - b.thickness) > 0.1:
        raise ValueError(
            f"walls have different thickness ({a.thickness} vs {b.thickness})"
        )
    if abs(a.height - b.height) > 0.1:
        raise ValueError(
            f"walls have different height ({a.height} vs {b.height})"
        )

    # Find the shared endpoint pair
    def _close(p1, p2):
        return math.hypot(p1[0] - p2[0], p1[1] - p2[1]) <= endpoint_tol_cm

    a_s, a_e = (a.xStart, a.yStart), (a.xEnd, a.yEnd)
    b_s, b_e = (b.xStart, b.yStart), (b.xEnd, b.yEnd)
    if _close(a_e, b_s):
        a_outer, b_outer = a_s, b_e
        a_outer_link, b_outer_link = a.wallAtStart, b.wallAtEnd
    elif _close(a_s, b_e):
        a_outer, b_outer = a_e, b_s
        a_outer_link, b_outer_link = a.wallAtEnd, b.wallAtStart
    elif _close(a_s, b_s):
        a_outer, b_outer = a_e, b_e
        a_outer_link, b_outer_link = a.wallAtEnd, b.wallAtEnd
    elif _close(a_e, b_e):
        a_outer, b_outer = a_s, b_s
        a_outer_link, b_outer_link = a.wallAtStart, b.wallAtStart
    else:
        raise ValueError(
            f"walls don't share an endpoint within {endpoint_tol_cm} cm"
        )

    # Collinearity check: the angle of the would-be merged segment must
    # match each input's angle within angle_tol_deg.
    def _ang(p, q):
        return math.atan2(q[1] - p[1], q[0] - p[0])
    merged_ang = _ang(a_outer, b_outer)
    a_ang = _ang(a_s, a_e)
    b_ang = _ang(b_s, b_e)
    tol = math.radians(angle_tol_deg)
    def _close_ang(a1, a2):
        d = abs((a1 - a2 + math.pi) % (2 * math.pi) - math.pi)
        # Treat opposite-direction walls (180° apart) as collinear too
        return d <= tol or abs(d - math.pi) <= tol
    if not (_close_ang(merged_ang, a_ang) and _close_ang(merged_ang, b_ang)):
        raise ValueError(
            "walls are not collinear within "
            f"{angle_tol_deg}° (a={math.degrees(a_ang):.1f}°, "
            f"b={math.degrees(b_ang):.1f}°, merged={math.degrees(merged_ang):.1f}°)"
        )

    # Build the survivor in-place on `a`
    a.xStart, a.yStart = a_outer
    a.xEnd,   a.yEnd   = b_outer
    a.wallAtStart = a_outer_link
    a.wallAtEnd   = b_outer_link
    # Remove `b` and remap any neighbour references on other walls
    home.walls.remove(b)
    for other in home.walls:
        if other.wallAtStart == b.id:
            other.wallAtStart = a.id
        if other.wallAtEnd == b.id:
            other.wallAtEnd = a.id
    return a


def connect_walls(home: Home, first: str, second: str,
                    *, at: str = "end-start") -> tuple[Wall, Wall]:
    """Connect two walls so SH3D treats them as a continuous segment.

    `at` is one of: "end-start" (default — first wall's end joins second's
    start), "start-end", "start-start", "end-end".
    """
    a = home.find_wall(first)
    b = home.find_wall(second)
    if a is None: raise KeyError(first)
    if b is None: raise KeyError(second)
    if at == "end-start":
        a.wallAtEnd = b.id; b.wallAtStart = a.id
    elif at == "start-end":
        a.wallAtStart = b.id; b.wallAtEnd = a.id
    elif at == "start-start":
        a.wallAtStart = b.id; b.wallAtStart = a.id
    elif at == "end-end":
        a.wallAtEnd = b.id; b.wallAtEnd = a.id
    else:
        raise ValueError(f"invalid `at` value: {at!r}")
    return a, b


def rectangle(home: Home, x: float, y: float, width: float, depth: float,
                *, thickness: float = 7.5, height: Optional[float] = None,
                level: Optional[str] = None,
                pattern: Optional[str] = None,
                leftSideTexture: Optional[Texture] = None,
                rightSideTexture: Optional[Texture] = None) -> list[Wall]:
    """Add four connected walls forming a closed rectangle.

    Returns the walls in order: north, east, south, west.
    """
    if width <= 0 or depth <= 0:
        raise ValueError("width and depth must be positive")
    h = home.wallHeight if height is None else height
    n = add_wall(home, x, y,             x + width, y,             thickness=thickness, height=h, level=level, pattern=pattern, leftSideTexture=leftSideTexture, rightSideTexture=rightSideTexture)
    e = add_wall(home, x + width, y,     x + width, y + depth,     thickness=thickness, height=h, level=level, pattern=pattern, leftSideTexture=leftSideTexture, rightSideTexture=rightSideTexture)
    s = add_wall(home, x + width, y+depth, x, y + depth,            thickness=thickness, height=h, level=level, pattern=pattern, leftSideTexture=leftSideTexture, rightSideTexture=rightSideTexture)
    w = add_wall(home, x, y + depth,     x, y,                     thickness=thickness, height=h, level=level, pattern=pattern, leftSideTexture=leftSideTexture, rightSideTexture=rightSideTexture)
    connect_walls(home, n.id, e.id, at="end-start")
    connect_walls(home, e.id, s.id, at="end-start")
    connect_walls(home, s.id, w.id, at="end-start")
    connect_walls(home, w.id, n.id, at="end-start")
    return [n, e, s, w]
