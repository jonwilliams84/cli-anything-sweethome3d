"""Friendly lookup helpers for surgical edits.

The model accessors (``home.rooms``, ``home.walls``, ``home.furniture``)
return everything; these helpers let the caller say "the landing on the
first floor" or "the wall just east of Master" without juggling random
ID hashes. They are the foundation for the interactive editing loop —
``open_home → find_X(…) → mutate → save_home`` — that lets you swap a
light, paint a wall, or change a carpet without re-running the SVG
importer.

All ``find_one`` functions return ``None`` when nothing matches; the
plural variants always return a list.
"""

from __future__ import annotations

import math
from typing import Optional

from cli_anything.sweethome3d.core.model import (
    Home,
    Level,
    PieceOfFurniture,
    Room,
    Wall,
)
from cli_anything.sweethome3d.core.svg.geometry import (
    point_in_polygon,
    point_to_segment_dist,
)


# ───────────────────────────────────────────────────────── levels

def find_level(home: Home, *, name: Optional[str] = None) -> Optional[Level]:
    """Return the level whose name matches ``name`` (case-insensitive,
    substring match). When ``name`` is None and there's a single level,
    return that one."""
    if name is None:
        return home.levels[0] if len(home.levels) == 1 else None
    needle = name.lower().strip()
    matches = [L for L in home.levels if needle in L.name.lower()]
    if len(matches) == 1:
        return matches[0]
    exact = [L for L in matches if L.name.lower() == needle]
    return exact[0] if exact else None


def _level_id_filter(home, level):
    """Normalise a level selector (name | id | Level object | None)."""
    if level is None:
        return None
    if isinstance(level, Level):
        return level.id
    if isinstance(level, str):
        L = find_level(home, name=level)
        if L is not None:
            return L.id
        return level   # assume it's already an id
    raise TypeError(f"level must be None | str | Level, got {type(level).__name__}")


# ───────────────────────────────────────────────────────── rooms

def _room_centroid(r: Room) -> tuple[float, float]:
    pts = r.points
    cx = sum(p.x for p in pts) / len(pts)
    cy = sum(p.y for p in pts) / len(pts)
    return cx, cy


def find_rooms(home: Home, *,
                name: Optional[str] = None,
                level=None) -> list[Room]:
    """List rooms matching the (case-insensitive) name substring and/or
    level filter. Both filters are AND'd."""
    lvl_id = _level_id_filter(home, level)
    rooms = list(home.rooms)
    if lvl_id is not None:
        rooms = [r for r in rooms if r.level == lvl_id]
    if name is not None:
        needle = name.lower().strip()
        rooms = [r for r in rooms if r.name and needle in r.name.lower()]
    return rooms


def find_room(home: Home, *,
               name: Optional[str] = None,
               level=None,
               contains_point: Optional[tuple[float, float]] = None
               ) -> Optional[Room]:
    """Return the single room matching the filters, else ``None``.

    Prefers an exact case-insensitive name match when ``name`` is given;
    falls back to a substring match. If ``contains_point`` is set, only
    returns rooms whose polygon contains the point.
    """
    candidates = find_rooms(home, name=name, level=level)
    if contains_point is not None:
        px, py = contains_point
        candidates = [
            r for r in candidates
            if point_in_polygon(px, py, [(p.x, p.y) for p in r.points])
        ]
    if not candidates:
        return None
    if name is not None:
        needle = name.lower().strip()
        exact = [r for r in candidates if r.name and r.name.lower() == needle]
        if exact:
            return exact[0]
    return candidates[0] if len(candidates) == 1 else candidates[0]


# ───────────────────────────────────────────────────────── walls

def find_walls(home: Home, *,
                level=None,
                thickness: Optional[float] = None,
                horizontal: Optional[bool] = None,
                vertical: Optional[bool] = None,
                unlinked: Optional[bool] = None) -> list[Wall]:
    """List walls passing all supplied filters. ``horizontal=True``
    keeps walls whose endpoints share the same y (within 1 cm); same
    for ``vertical=True`` with x. ``unlinked=True`` keeps only walls
    whose endpoints are NOT joined to another wall (no ``wallAtStart``
    and no ``wallAtEnd``) — surfaces import-corner-fuse failures."""
    lvl_id = _level_id_filter(home, level)
    out = []
    for w in home.walls:
        if lvl_id is not None and w.level != lvl_id:
            continue
        if thickness is not None and abs(w.thickness - thickness) > 0.5:
            continue
        if horizontal is True and abs(w.yStart - w.yEnd) >= 1.0:
            continue
        if horizontal is False and abs(w.yStart - w.yEnd) < 1.0:
            continue
        if vertical is True and abs(w.xStart - w.xEnd) >= 1.0:
            continue
        if vertical is False and abs(w.xStart - w.xEnd) < 1.0:
            continue
        if unlinked is True and (w.wallAtStart or w.wallAtEnd):
            continue
        if unlinked is False and not (w.wallAtStart or w.wallAtEnd):
            continue
        out.append(w)
    return out


def find_wall(home: Home, *,
               near_point: Optional[tuple[float, float]] = None,
               level=None,
               horizontal: Optional[bool] = None,
               vertical: Optional[bool] = None,
               thickness: Optional[float] = None,
               max_distance_cm: float = 25.0) -> Optional[Wall]:
    """Return the single closest wall to ``near_point`` matching the
    other filters, or ``None`` if nothing is within
    ``max_distance_cm`` of the point."""
    candidates = find_walls(home, level=level, thickness=thickness,
                              horizontal=horizontal, vertical=vertical)
    if near_point is None:
        return candidates[0] if len(candidates) == 1 else None
    px, py = near_point
    best = None
    for w in candidates:
        d = point_to_segment_dist(px, py, w.xStart, w.yStart, w.xEnd, w.yEnd)
        if d <= max_distance_cm and (best is None or d < best[0]):
            best = (d, w)
    return best[1] if best else None


def find_room_walls(home: Home, room: Room, *,
                     side: Optional[str] = None,
                     tol: float = 25.0) -> list[Wall]:
    """Walls bounding ``room``. Optional ``side`` filter is one of
    ``"north"``, ``"south"``, ``"east"``, ``"west"`` and returns only
    walls along the room's bounding-box edge for that side.

    SH3D Y-down convention: smaller y = north, larger y = south.
    """
    poly = [(p.x, p.y) for p in room.points]
    if not poly:
        return []
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
    out = []
    for w in home.walls:
        if w.level != room.level:
            continue
        mx, my = (w.xStart + w.xEnd) / 2, (w.yStart + w.yEnd) / 2
        # Is wall midpoint near the room polygon's perimeter?
        on_perim = False
        n = len(poly)
        for i in range(n):
            x1, y1 = poly[i]; x2, y2 = poly[(i + 1) % n]
            if point_to_segment_dist(mx, my, x1, y1, x2, y2) <= tol:
                on_perim = True; break
        if not on_perim:
            continue
        if side is None:
            out.append(w); continue
        s = side.lower()
        if s == "north" and abs(my - ymin) <= tol:
            out.append(w)
        elif s == "south" and abs(my - ymax) <= tol:
            out.append(w)
        elif s == "west" and abs(mx - xmin) <= tol:
            out.append(w)
        elif s == "east" and abs(mx - xmax) <= tol:
            out.append(w)
    return out


# ───────────────────────────────────────────────────────── furniture / doors / windows / lights

def find_pieces(home: Home, *,
                  kind: Optional[str] = None,
                  name: Optional[str] = None,
                  catalog: Optional[str] = None,
                  level=None,
                  in_room: Optional[Room] = None,
                  near_point: Optional[tuple[float, float]] = None,
                  max_distance_cm: float = 200.0) -> list[PieceOfFurniture]:
    """List furniture matching all supplied filters.

    ``kind`` is ``"pieceOfFurniture"`` | ``"doorOrWindow"`` | ``"light"``.
    ``catalog`` matches as a case-insensitive substring against
    ``catalogId``. ``in_room`` keeps only pieces whose centre falls
    inside the room polygon.
    """
    lvl_id = _level_id_filter(home, level)
    items = list(home.furniture)
    if kind is not None:
        items = [f for f in items if f.kind == kind]
    if lvl_id is not None:
        items = [f for f in items if f.level == lvl_id]
    if name is not None:
        needle = name.lower().strip()
        items = [f for f in items if f.name and needle in f.name.lower()]
    if catalog is not None:
        needle = catalog.lower().strip()
        items = [f for f in items if f.catalogId and needle in f.catalogId.lower()]
    if in_room is not None:
        poly = [(p.x, p.y) for p in in_room.points]
        items = [f for f in items if point_in_polygon(f.x, f.y, poly)]
    if near_point is not None:
        px, py = near_point
        items = [f for f in items
                  if math.hypot(f.x - px, f.y - py) <= max_distance_cm]
        items.sort(key=lambda f: math.hypot(f.x - px, f.y - py))
    return items


def find_doors(home: Home, **kwargs) -> list[PieceOfFurniture]:
    """Shortcut: pieces with ``kind='doorOrWindow'``."""
    kwargs["kind"] = "doorOrWindow"
    return find_pieces(home, **kwargs)


def find_door(home: Home, **kwargs) -> Optional[PieceOfFurniture]:
    """Single-piece variant of :func:`find_doors`."""
    items = find_doors(home, **kwargs)
    return items[0] if items else None


def find_lights(home: Home, **kwargs) -> list[PieceOfFurniture]:
    """Shortcut: pieces with ``kind='light'``."""
    kwargs["kind"] = "light"
    return find_pieces(home, **kwargs)


def find_light(home: Home, **kwargs) -> Optional[PieceOfFurniture]:
    """Single-piece variant of :func:`find_lights`."""
    items = find_lights(home, **kwargs)
    return items[0] if items else None
