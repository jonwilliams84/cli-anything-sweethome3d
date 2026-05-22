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
