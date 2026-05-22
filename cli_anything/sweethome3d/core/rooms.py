"""Room operations — polygons with floor/ceiling."""

from __future__ import annotations

import math
from typing import Optional

from cli_anything.sweethome3d.core.model import Home, Point, Room, Texture


def list_rooms(home: Home, *, level: Optional[str] = None) -> list[Room]:
    rooms = home.rooms
    if level is not None:
        rooms = [r for r in rooms if r.level == level]
    return list(rooms)


def add_room(home: Home, points: list[tuple[float, float]],
              *, name: Optional[str] = None,
              level: Optional[str] = None,
              floorColor: Optional[int] = None,
              ceilingColor: Optional[int] = None,
              floorTexture: Optional[Texture] = None,
              ceilingTexture: Optional[Texture] = None,
              areaVisible: bool = False) -> Room:
    """Add a room defined by a polygon of (x, y) corners.

    At least 3 points are required.
    """
    if len(points) < 3:
        raise ValueError("a room requires at least 3 points")
    r = Room(
        points=[Point(x, y) for x, y in points],
        name=name,
        level=level,
        floorColor=floorColor,
        ceilingColor=ceilingColor,
        floorTexture=floorTexture,
        ceilingTexture=ceilingTexture,
        areaVisible=areaVisible,
    )
    home.rooms.append(r)
    return r


def add_rectangle_room(home: Home, x: float, y: float,
                        width: float, depth: float,
                        *, name: Optional[str] = None,
                        level: Optional[str] = None,
                        **kwargs) -> Room:
    """Convenience: add a rectangular room aligned to axes."""
    if width <= 0 or depth <= 0:
        raise ValueError("width and depth must be positive")
    pts = [(x, y), (x + width, y), (x + width, y + depth), (x, y + depth)]
    return add_room(home, pts, name=name, level=level, **kwargs)


def delete_room(home: Home, ident: str) -> bool:
    r = home.find_room(ident)
    if r is None:
        return False
    home.rooms.remove(r)
    return True


def set_room_properties(home: Home, ident: str, **fields) -> Room:
    r = home.find_room(ident)
    if r is None:
        raise KeyError(ident)
    for k, v in fields.items():
        if not hasattr(r, k):
            raise AttributeError(f"unknown room field: {k!r}")
        setattr(r, k, v)
    return r


def area(r: Room) -> float:
    """Shoelace polygon area. Returns positive square units (cm²)."""
    pts = r.points
    n = len(pts)
    if n < 3:
        return 0
    a = 0.0
    for i in range(n):
        j = (i + 1) % n
        a += pts[i].x * pts[j].y - pts[j].x * pts[i].y
    return abs(a) / 2


def recompute_room_points(home: Home, room_id: str, *, tol: float = 20.0) -> Room:
    """Snap a room's polygon vertices to nearby wall endpoints.

    Mimics SH3D's "Recompute room points" right-click action: for each vertex
    of the room's existing polygon, find the nearest wall endpoint on the same
    level within *tol* cm and snap to it.  This corrects small gaps that arise
    when rooms are drawn near (but not exactly on) wall junctions.

    Raises KeyError if *room_id* is not found.
    Raises ValueError if fewer than 3 distinct points remain after snapping
    and deduplication.

    Returns the modified Room (mutated in-place).
    """
    r = home.find_room(room_id)
    if r is None:
        raise KeyError(room_id)

    # Collect all wall endpoints on the same level as the room.
    endpoints: list[tuple[float, float]] = []
    for w in home.walls:
        if w.level != r.level:
            continue
        endpoints.append((w.xStart, w.yStart))
        endpoints.append((w.xEnd, w.yEnd))

    def snap(px: float, py: float) -> tuple[float, float]:
        best_dist = tol
        bx, by = px, py
        for ex, ey in endpoints:
            d = math.hypot(ex - px, ey - py)
            if d < best_dist:
                best_dist = d
                bx, by = ex, ey
        return bx, by

    new_points: list[Point] = []
    for p in r.points:
        sx, sy = snap(p.x, p.y)
        new_points.append(Point(sx, sy))

    # Deduplicate consecutive identical points.
    deduped: list[Point] = []
    for pt in new_points:
        if not deduped or (pt.x, pt.y) != (deduped[-1].x, deduped[-1].y):
            deduped.append(pt)
    # Also remove wrap-around duplicate (last == first).
    if len(deduped) > 1 and (deduped[-1].x, deduped[-1].y) == (deduped[0].x, deduped[0].y):
        deduped.pop()

    if len(deduped) < 3:
        raise ValueError(
            f"room {room_id!r} has fewer than 3 distinct points after snapping"
        )

    r.points = deduped
    return r
