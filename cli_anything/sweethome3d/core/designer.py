"""SweetHome3D Designer API — pure-Python, no Java/SH3D runtime required.

This module provides the Designer class, a high-level API for building
2-D floor-plan models that can be serialised to SweetHome3D (.sh3d) files
and rendered as PNG images.

The API is intentionally LLM-ergonomic:
- Every public method has a docstring with at least one example invocation.
- Spatial selectors (wall_facing, room_at, room_named) let the LLM refer
  to elements symbolically without tracking internal ids.
- validate() returns a structured diagnostic dict that the LLM can inspect
  after each major construction step.
- describe() / list_walls() / list_rooms() / list_openings() / list_catalog_furniture()
  let the LLM verify state before continuing.
- to_spec() / from_spec() round-trip the full design as plain JSON so the
  LLM can save, reload, and hand off work.
- Error messages are actionable — they tell the LLM what to call next.

Coordinate system
-----------------
All coordinates are in **centimetres** (cm).
(0, 0) is the top-left corner of the home bounding box.
x increases rightward; y increases downward (screen convention).
Wall thickness default = 20 cm (exterior walls) or 10 cm (partitions).
Floor-ceiling height default = 250 cm.
"""

from __future__ import annotations

import copy
import json
import math
import uuid
import zipfile
import struct
import zlib
from pathlib import Path
from typing import Any, Optional, Union

# ---------------------------------------------------------------------------
# Catalogue (bundled furniture IDs, mirroring the SH3D default catalogue)
# ---------------------------------------------------------------------------

_CATALOG: dict[str, list[str]] = {
    "sofa": [
        "SOFA_2_SEATS", "SOFA_3_SEATS", "CORNER_SOFA", "SOFA_BED",
    ],
    "chair": [
        "DINING_CHAIR", "OFFICE_CHAIR", "ARMCHAIR", "STOOL",
    ],
    "table": [
        "DINING_TABLE_4", "DINING_TABLE_6", "COFFEE_TABLE", "DESK",
        "SIDE_TABLE", "KITCHEN_TABLE",
    ],
    "bed": [
        "SINGLE_BED", "DOUBLE_BED", "KING_BED", "BUNK_BED",
    ],
    "storage": [
        "WARDROBE", "BOOKCASE", "SIDEBOARD", "CHEST_OF_DRAWERS",
        "TV_UNIT", "SHOE_RACK",
    ],
    "kitchen": [
        "KITCHEN_UNIT_BASE", "KITCHEN_UNIT_WALL", "KITCHEN_ISLAND",
        "OVEN", "REFRIGERATOR", "DISHWASHER", "WASHING_MACHINE",
        "TUMBLE_DRYER", "KITCHEN_SINK",
    ],
    "bathroom": [
        "BATH", "SHOWER_ENCLOSURE", "TOILET", "BASIN", "VANITY_UNIT",
        "TOWEL_RAIL",
    ],
    "door": [
        "DOOR_STANDARD", "DOOR_BIFOLD", "DOOR_FRENCH", "DOOR_SLIDING",
        "DOOR_POCKET",
    ],
    "window": [
        "WINDOW_CASEMENT", "WINDOW_SASH", "WINDOW_TILT_AND_TURN",
        "WINDOW_BAY", "SKYLIGHT",
    ],
    "stair": [
        "STAIRCASE_STRAIGHT", "STAIRCASE_L", "STAIRCASE_U",
    ],
    "misc": [
        "FIREPLACE", "RADIATOR", "BOILER", "CONSUMER_UNIT",
        "TV", "DESK_LAMP", "FLOOR_LAMP",
    ],
}


def _all_catalog_ids() -> list[str]:
    result: list[str] = []
    for ids in _CATALOG.values():
        result.extend(ids)
    return result


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

Pt = tuple[float, float]  # (x, y) in cm


def _dist(a: Pt, b: Pt) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def _pt_to_seg_dist(p: Pt, a: Pt, b: Pt) -> tuple[float, Pt]:
    """Return (distance, closest_point) from point p to segment a-b."""
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    seg_len2 = dx * dx + dy * dy
    if seg_len2 < 1e-12:
        return _dist(p, a), a
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg_len2))
    cx = ax + t * dx
    cy = ay + t * dy
    return _dist(p, (cx, cy)), (cx, cy)


def _polygon_area(pts: list[Pt]) -> float:
    """Signed area via shoelace; positive = CCW."""
    n = len(pts)
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += pts[i][0] * pts[j][1]
        area -= pts[j][0] * pts[i][1]
    return area / 2.0


def _pt_in_polygon(pt: Pt, poly: list[Pt]) -> bool:
    """Ray-casting point-in-polygon test."""
    x, y = pt
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _polygon_centroid(pts: list[Pt]) -> Pt:
    n = len(pts)
    cx = sum(p[0] for p in pts) / n
    cy = sum(p[1] for p in pts) / n
    return (cx, cy)


# ---------------------------------------------------------------------------
# Unique ID helpers
# ---------------------------------------------------------------------------

def _uid(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# Handle objects (thin wrappers that hold an id so the LLM can pass them
# back into selectors without knowing internal structure)
# ---------------------------------------------------------------------------

class WallHandle:
    """Opaque reference to a wall returned by spatial selectors.

    Pass this directly into partition(), add_door(), add_window() etc.
    Do not try to read its internal fields — use list_walls() instead.
    """

    def __init__(self, wall_id: str, designer: "Designer"):
        self._id = wall_id
        self._d = designer

    def __repr__(self) -> str:
        return f"WallHandle(id={self._id!r})"


class RoomHandle:
    """Opaque reference to a room returned by spatial selectors."""

    def __init__(self, room_id: str, designer: "Designer"):
        self._id = room_id
        self._d = designer

    def __repr__(self) -> str:
        return f"RoomHandle(id={self._id!r})"


# ---------------------------------------------------------------------------
# Level model
# ---------------------------------------------------------------------------

class _Level:
    def __init__(self, *, name: str, floor_height: float, ceiling_height: float, idx: int):
        self.id = _uid("level-")
        self.name = name
        self.floor_height = floor_height   # cm above datum
        self.ceiling_height = ceiling_height  # cm (room height)
        self.idx = idx
        self.walls: list[dict] = []
        self.rooms: list[dict] = []
        self.openings: list[dict] = []   # doors + windows
        self.furniture: list[dict] = []

    # ---- wall helpers ----

    def _find_wall(self, wall_id: str) -> Optional[dict]:
        for w in self.walls:
            if w["id"] == wall_id:
                return w
        return None

    def _closest_wall_to_point(self, pt: Pt) -> tuple[Optional[dict], float, Pt]:
        best_wall = None
        best_dist = float("inf")
        best_close: Pt = (0.0, 0.0)
        for w in self.walls:
            d, cp = _pt_to_seg_dist(pt, tuple(w["start"]), tuple(w["end"]))
            if d < best_dist:
                best_dist = d
                best_wall = w
                best_close = cp
        return best_wall, best_dist, best_close

    def _envelope_walls(self) -> list[dict]:
        return [w for w in self.walls if w.get("is_envelope", False)]

    def _partition_walls(self) -> list[dict]:
        return [w for w in self.walls if not w.get("is_envelope", False)]

    def _wall_facing(self, direction: str) -> Optional[dict]:
        """Return the envelope wall facing a compass direction.

        Uses the wall's stored 'facing' label if present; otherwise falls back
        to positional heuristics (northernmost wall = 'north', etc.).
        """
        direction_lower = direction.lower()
        if direction_lower not in ("north", "south", "east", "west"):
            raise ValueError(
                f"Unknown direction {direction!r}. Valid values: 'north','south','east','west'."
            )

        # Fast path: use the stored facing label set by envelope()
        for w in self._envelope_walls():
            if w.get("facing") == direction_lower:
                return w

        # Fallback: positional heuristic for walls that have no facing label.
        # north = min y midpoint, south = max y midpoint,
        # west = min x midpoint,  east = max x midpoint.
        env_walls = self._envelope_walls()
        if not env_walls:
            return None

        def mid(w):
            sx, sy = w["start"]
            ex, ey = w["end"]
            return ((sx + ex) / 2.0, (sy + ey) / 2.0)

        if direction_lower == "north":
            return min(env_walls, key=lambda w: mid(w)[1])
        if direction_lower == "south":
            return max(env_walls, key=lambda w: mid(w)[1])
        if direction_lower == "west":
            return min(env_walls, key=lambda w: mid(w)[0])
        # east
        return max(env_walls, key=lambda w: mid(w)[0])

    # ---- room helpers ----

    def _room_at(self, x: float, y: float) -> Optional[dict]:
        for r in self.rooms:
            if _pt_in_polygon((x, y), [tuple(p) for p in r["polygon"]]):
                return r
        return None

    def _room_named(self, label: str) -> Optional[dict]:
        for r in self.rooms:
            if r.get("label", "").lower() == label.lower():
                return r
        return None

    # ---- serialization ----

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "floor_height": self.floor_height,
            "ceiling_height": self.ceiling_height,
            "idx": self.idx,
            "walls": copy.deepcopy(self.walls),
            "rooms": copy.deepcopy(self.rooms),
            "openings": copy.deepcopy(self.openings),
            "furniture": copy.deepcopy(self.furniture),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "_Level":
        lv = cls(
            name=d["name"],
            floor_height=d.get("floor_height", 0.0),
            ceiling_height=d.get("ceiling_height", 250.0),
            idx=d.get("idx", 0),
        )
        lv.id = d["id"]
        lv.walls = copy.deepcopy(d.get("walls", []))
        lv.rooms = copy.deepcopy(d.get("rooms", []))
        lv.openings = copy.deepcopy(d.get("openings", []))
        lv.furniture = copy.deepcopy(d.get("furniture", []))
        return lv


# ---------------------------------------------------------------------------
# Designer
# ---------------------------------------------------------------------------

class Designer:
    """High-level API for building SweetHome3D floor-plan models.

    Coordinates are in centimetres. (0,0) is top-left; x→right, y→down.

    Quick-start example
    -------------------
    >>> d = Designer(name="My House")
    >>> ground = d.add_level("Ground Floor")
    >>> d.envelope(ground, width=1000, depth=800)
    >>> living = d.room(ground, polygon=[(20,20),(480,20),(480,400),(20,400)], label="Living Room")
    >>> d.partition(ground, start=(480,20), end=(480,400))
    >>> h = d.wall_facing("north", level=ground)
    >>> d.add_external_door(ground, wall=h, position_along=0.5)
    >>> spec = d.to_spec()
    >>> d2 = Designer.from_spec(spec)
    """

    _SNAP_TOL = 8.0   # cm — points closer than this snap together
    _VALID_UNITS = {"CENTIMETER", "INCH", "MILLIMETER", "METER"}

    def __init__(self, *, name: str = "Home", unit: str = "CENTIMETER"):
        if unit not in self._VALID_UNITS:
            raise ValueError(
                f"Invalid unit {unit!r}. Valid units: "
                f"{sorted(self._VALID_UNITS)}."
            )
        self.name = name
        self.unit = unit
        self._levels: list[_Level] = []
        self._meta: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Level management
    # ------------------------------------------------------------------

    def add_level(
        self,
        name: str,
        *,
        floor_height: float = 0.0,
        ceiling_height: float = 250.0,
    ) -> _Level:
        """Add a storey and return its handle.

        Example
        -------
        >>> ground = d.add_level("Ground Floor", floor_height=0, ceiling_height=250)
        >>> first  = d.add_level("First Floor",  floor_height=250, ceiling_height=250)
        """
        lv = _Level(
            name=name,
            floor_height=floor_height,
            ceiling_height=ceiling_height,
            idx=len(self._levels),
        )
        self._levels.append(lv)
        return lv

    def _resolve_level(self, level: Union[_Level, int, None]) -> _Level:
        if level is None:
            if not self._levels:
                raise ValueError(
                    "No levels defined yet. Call d.add_level('Ground Floor') first."
                )
            return self._levels[0]
        if isinstance(level, int):
            if level < 0 or level >= len(self._levels):
                raise IndexError(
                    f"Level index {level} out of range (have {len(self._levels)} levels). "
                    f"Use d.add_level() to create levels first."
                )
            return self._levels[level]
        return level

    # ------------------------------------------------------------------
    # Envelope (exterior walls)
    # ------------------------------------------------------------------

    def envelope(
        self,
        level: Union[_Level, int, None] = None,
        *,
        width: float,
        depth: float,
        x_offset: float = 0.0,
        y_offset: float = 0.0,
        thickness: float = 20.0,
    ) -> list[str]:
        """Draw the four exterior walls of a rectangular footprint.

        Parameters
        ----------
        level       : level handle (or index) to draw on
        width       : exterior width in cm (x direction)
        depth       : exterior depth in cm (y direction)
        x_offset    : x origin of top-left corner (default 0)
        y_offset    : y origin of top-left corner (default 0)
        thickness   : wall thickness in cm (default 20)

        Returns
        -------
        List of wall ids [north, east, south, west]

        Example
        -------
        >>> ground = d.add_level("Ground Floor")
        >>> d.envelope(ground, width=1000, depth=800)
        """
        lv = self._resolve_level(level)
        x0, y0 = x_offset, y_offset
        x1, y1 = x_offset + width, y_offset + depth
        corners = [
            (x0, y0),  # NW
            (x1, y0),  # NE
            (x1, y1),  # SE
            (x0, y1),  # SW
        ]
        labels = ["north", "east", "south", "west"]
        starts = [corners[0], corners[1], corners[3], corners[0]]
        ends   = [corners[1], corners[2], corners[2], corners[3]]
        ids = []
        for label, s, e in zip(labels, starts, ends):
            wid = _uid("wall-")
            lv.walls.append({
                "id": wid,
                "start": list(s),
                "end": list(e),
                "thickness": thickness,
                "is_envelope": True,
                "facing": label,
                "level_id": lv.id,
            })
            ids.append(wid)
        return ids

    # ------------------------------------------------------------------
    # Internal partitions
    # ------------------------------------------------------------------

    def partition(
        self,
        level: Union[_Level, int, None] = None,
        start: Optional[Pt] = None,
        end: Optional[Pt] = None,
        *,
        thickness: float = 10.0,
        snap_to: Optional[WallHandle] = None,
    ) -> str:
        """Add an interior partition wall.

        Both endpoints should touch an existing wall (envelope or partition).
        If an endpoint is within snap_tolerance of an existing wall endpoint,
        it snaps automatically.

        Parameters
        ----------
        level     : level handle
        start     : (x, y) start point in cm
        end       : (x, y) end point in cm
        thickness : wall thickness in cm (default 10)
        snap_to   : if given, the start point is projected onto this wall

        Returns
        -------
        The new wall id.

        Example
        -------
        >>> d.partition(ground, start=(500, 0), end=(500, 800))
        >>> d.partition(ground, start=(500, 400), end=(1000, 400), thickness=10)
        """
        lv = self._resolve_level(level)
        if start is None or end is None:
            raise ValueError(
                "partition() requires both 'start' and 'end' as (x, y) tuples. "
                "Example: d.partition(ground, (500, 0), (500, 800))"
            )
        start = (float(start[0]), float(start[1]))
        end   = (float(end[0]),   float(end[1]))

        # Apply snap_to if given
        if snap_to is not None:
            w = lv._find_wall(snap_to._id)
            if w is not None:
                _, snap_pt = _pt_to_seg_dist(start, tuple(w["start"]), tuple(w["end"]))
                start = snap_pt

        # Validate endpoints touch existing wall
        for label, pt in [("start", start), ("end", end)]:
            closest_wall, cdist, cpt = lv._closest_wall_to_point(pt)
            if closest_wall is None:
                raise ValueError(
                    f"partition() called but no existing walls found. "
                    f"Call d.envelope() first to draw exterior walls."
                )
            if cdist > self._SNAP_TOL:
                # Give actionable guidance
                wid = closest_wall["id"]
                facing = closest_wall.get("facing", "")
                if label == "start":
                    # snap_to projects the start point onto a wall
                    snap_hint = (
                        f" Did you mean to snap to it? If so, call: "
                        f"d.partition(level, {pt}, {end}, "
                        f"snap_to=d.wall_facing({facing!r}, level))"
                        if facing else
                        f" Adjust the start coordinate to touch the wall, "
                        f"or pass snap_to=wall id={wid!r}."
                    )
                else:
                    # snap_to only snaps the start point; for the end point
                    # the user must adjust the coordinate directly.
                    snap_hint = (
                        f" Adjust the end coordinate {pt} so it touches the "
                        f"wall (snap_to only snaps the start point)."
                    )
                raise ValueError(
                    f"partition {label} endpoint {pt} doesn't touch any existing wall. "
                    f"Closest wall is {wid!r}{(' ('+facing+' envelope)') if facing else ''} "
                    f"at distance {cdist:.1f} cm.{snap_hint}"
                )

        wid = _uid("wall-")
        lv.walls.append({
            "id": wid,
            "start": list(start),
            "end": list(end),
            "thickness": thickness,
            "is_envelope": False,
            "facing": None,
            "level_id": lv.id,
        })
        return wid

    # ------------------------------------------------------------------
    # Rooms
    # ------------------------------------------------------------------

    def room(
        self,
        level: Union[_Level, int, None] = None,
        *,
        polygon: list[Pt],
        label: str = "",
        floor_color: Optional[str] = None,
        ceiling_color: Optional[str] = None,
    ) -> RoomHandle:
        """Define a named room from a polygon (list of corner (x,y) points).

        Parameters
        ----------
        level         : level handle
        polygon       : list of (x, y) corner coordinates in cm (≥3 points)
        label         : room name, e.g. "Kitchen"
        floor_color   : hex color string, e.g. "#C8A880"
        ceiling_color : hex color string

        Returns
        -------
        RoomHandle for use with spatial selectors.

        Example
        -------
        >>> kitchen = d.room(ground,
        ...     polygon=[(500,0),(1000,0),(1000,400),(500,400)],
        ...     label="Kitchen", floor_color="#C8A880")
        """
        lv = self._resolve_level(level)
        if len(polygon) < 3:
            raise ValueError(
                f"room() needs at least 3 polygon points, got {len(polygon)}. "
                "Example: polygon=[(0,0),(400,0),(400,300),(0,300)]"
            )
        pts = [list(p) for p in polygon]
        area = abs(_polygon_area([tuple(p) for p in pts]))
        rid = _uid("room-")
        r = {
            "id": rid,
            "polygon": pts,
            "label": label,
            "area_cm2": area,
            "area_m2": round(area / 10000.0, 2),
            "floor_color": floor_color,
            "ceiling_color": ceiling_color,
            "level_id": lv.id,
        }
        lv.rooms.append(r)
        return RoomHandle(rid, self)

    # ------------------------------------------------------------------
    # Openings (doors and windows)
    # ------------------------------------------------------------------

    def _place_opening(
        self,
        level: _Level,
        *,
        wall: Union[WallHandle, str, None],
        position_along: float,
        width: float,
        height: float,
        sill_height: float,
        kind: str,   # "door" or "window"
        catalog_id: str,
        label: str,
    ) -> str:
        """Internal: insert a door or window on a wall at fractional position."""
        # Resolve wall
        if wall is None:
            raise ValueError(
                f"add_external_{kind}() / add_internal_{kind}() requires a wall= argument. "
                f"Use d.wall_facing('north', level) or d.list_walls(level) to get one."
            )
        if isinstance(wall, WallHandle):
            wid = wall._id
        elif isinstance(wall, str):
            wid = wall
        else:
            raise TypeError(f"wall must be a WallHandle or wall id string, got {type(wall)}")

        wobj = level._find_wall(wid)
        if wobj is None:
            raise ValueError(
                f"Wall id {wid!r} not found on level {level.name!r}. "
                f"Available wall ids: {[w['id'] for w in level.walls]}"
            )

        if not (0.0 <= position_along <= 1.0):
            raise ValueError(
                f"position_along must be in [0.0, 1.0], got {position_along}. "
                f"0.0 = start endpoint, 1.0 = end endpoint, 0.5 = midpoint."
            )

        sx, sy = wobj["start"]
        ex, ey = wobj["end"]
        px = sx + position_along * (ex - sx)
        py = sy + position_along * (ey - sy)

        oid = _uid("opening-")
        level.openings.append({
            "id": oid,
            "kind": kind,
            "catalog_id": catalog_id,
            "wall_id": wid,
            "position_along": position_along,
            "x": px,
            "y": py,
            "width": width,
            "height": height,
            "sill_height": sill_height,
            "label": label,
            "level_id": level.id,
        })
        return oid

    def add_external_door(
        self,
        level: Union[_Level, int, None] = None,
        *,
        wall: Union[WallHandle, str, None] = None,
        position_along: float = 0.5,
        width: float = 90.0,
        height: float = 210.0,
        catalog_id: str = "DOOR_STANDARD",
        label: str = "Front Door",
    ) -> str:
        """Add an exterior door on an envelope wall.

        Parameters
        ----------
        level          : level handle
        wall           : WallHandle from d.wall_facing() or a wall id string
        position_along : fractional position along wall [0=start, 1=end] (default 0.5)
        width          : door width in cm (default 90)
        height         : door height in cm (default 210)
        catalog_id     : furniture catalog id (default 'DOOR_STANDARD')
        label          : display label

        Returns
        -------
        Opening id string.

        Example
        -------
        >>> north = d.wall_facing("north", level=ground)
        >>> d.add_external_door(ground, wall=north, position_along=0.35,
        ...                     width=90, label="Front Door")
        """
        lv = self._resolve_level(level)
        return self._place_opening(
            lv,
            wall=wall,
            position_along=position_along,
            width=width,
            height=height,
            sill_height=0.0,
            kind="door",
            catalog_id=catalog_id,
            label=label,
        )

    def add_internal_door(
        self,
        level: Union[_Level, int, None] = None,
        *,
        wall: Union[WallHandle, str, None] = None,
        position_along: float = 0.5,
        width: float = 80.0,
        height: float = 210.0,
        catalog_id: str = "DOOR_STANDARD",
        label: str = "Door",
    ) -> str:
        """Add an interior door on a partition wall.

        Example
        -------
        >>> hallway_wall = d.wall_facing("west", level=ground)
        >>> d.add_internal_door(ground, wall=hallway_wall, position_along=0.4)
        """
        lv = self._resolve_level(level)
        return self._place_opening(
            lv,
            wall=wall,
            position_along=position_along,
            width=width,
            height=height,
            sill_height=0.0,
            kind="door",
            catalog_id=catalog_id,
            label=label,
        )

    def add_window(
        self,
        level: Union[_Level, int, None] = None,
        *,
        wall: Union[WallHandle, str, None] = None,
        position_along: float = 0.5,
        width: float = 120.0,
        height: float = 120.0,
        sill_height: float = 90.0,
        catalog_id: str = "WINDOW_CASEMENT",
        label: str = "Window",
    ) -> str:
        """Add a window on a wall.

        Parameters
        ----------
        level          : level handle
        wall           : WallHandle from d.wall_facing() or wall id string
        position_along : fractional position [0.0-1.0]
        width          : window width in cm
        height         : window height in cm
        sill_height    : height of bottom of window above floor in cm
        catalog_id     : catalog id (e.g. 'WINDOW_CASEMENT', 'WINDOW_SASH')
        label          : display label

        Example
        -------
        >>> south = d.wall_facing("south", level=ground)
        >>> d.add_window(ground, wall=south, position_along=0.5,
        ...              width=120, height=120, sill_height=90)
        """
        lv = self._resolve_level(level)
        return self._place_opening(
            lv,
            wall=wall,
            position_along=position_along,
            width=width,
            height=height,
            sill_height=sill_height,
            kind="window",
            catalog_id=catalog_id,
            label=label,
        )

    # ------------------------------------------------------------------
    # Furniture placement
    # ------------------------------------------------------------------

    def place_furniture(
        self,
        level: Union[_Level, int, None] = None,
        *,
        catalog_id: str,
        x: float,
        y: float,
        rotation_deg: float = 0.0,
        width: Optional[float] = None,
        depth: Optional[float] = None,
        height: Optional[float] = None,
        label: str = "",
    ) -> str:
        """Place a furniture item from the catalog at (x, y).

        Parameters
        ----------
        level        : level handle
        catalog_id   : id from list_catalog_furniture() e.g. 'SOFA_3_SEATS'
        x, y         : position in cm
        rotation_deg : clockwise rotation in degrees
        width        : override default width in cm
        depth        : override default depth in cm
        height       : override default height in cm
        label        : display name

        Returns
        -------
        Furniture id string.

        Example
        -------
        >>> d.place_furniture(ground, catalog_id="SOFA_3_SEATS",
        ...                   x=100, y=200, rotation_deg=90, label="Main Sofa")
        >>> d.place_furniture(ground, catalog_id="DINING_TABLE_4",
        ...                   x=600, y=300)
        """
        lv = self._resolve_level(level)
        all_ids = _all_catalog_ids()
        if catalog_id not in all_ids:
            cats = ", ".join(_CATALOG.keys())
            raise ValueError(
                f"Unknown catalog_id {catalog_id!r}. "
                f"Call d.list_catalog_furniture() to see valid ids, or filter by "
                f"category: d.list_catalog_furniture(category='sofa'). "
                f"Available categories: {cats}."
            )
        fid = _uid("furn-")
        lv.furniture.append({
            "id": fid,
            "catalog_id": catalog_id,
            "x": float(x),
            "y": float(y),
            "rotation_deg": float(rotation_deg),
            "width": width,
            "depth": depth,
            "height": height,
            "label": label or catalog_id,
            "level_id": lv.id,
        })
        return fid

    # ------------------------------------------------------------------
    # Spatial selectors
    # ------------------------------------------------------------------

    def wall_facing(
        self,
        direction: str,
        level: Union[_Level, int, None] = None,
    ) -> WallHandle:
        """Return the envelope wall whose outward face is closest to a compass direction.

        Parameters
        ----------
        direction : 'north', 'south', 'east', or 'west'
        level     : level handle (default: first level)

        Returns
        -------
        WallHandle — pass this to add_external_door(), add_window(), etc.

        Example
        -------
        >>> north_wall = d.wall_facing("north", level=ground)
        >>> d.add_external_door(ground, wall=north_wall, position_along=0.4)
        >>> d.add_window(ground, wall=d.wall_facing("south", level=ground), position_along=0.5)
        """
        lv = self._resolve_level(level)
        w = lv._wall_facing(direction)
        if w is None:
            raise ValueError(
                f"No envelope wall found facing {direction!r} on level {lv.name!r}. "
                f"Have you called d.envelope() yet? "
                f"Available walls: {[x['id'] for x in lv._envelope_walls()]}"
            )
        return WallHandle(w["id"], self)

    def room_at(
        self,
        level: Union[_Level, int, None] = None,
        *,
        x: float,
        y: float,
    ) -> RoomHandle:
        """Return the room whose polygon contains point (x, y).

        Example
        -------
        >>> living = d.room_at(ground, x=200, y=150)
        >>> print(d.list_rooms(ground))
        """
        lv = self._resolve_level(level)
        r = lv._room_at(x, y)
        if r is None:
            rooms = [(rm["label"] or rm["id"], rm["polygon"]) for rm in lv.rooms]
            raise ValueError(
                f"No room found containing point ({x}, {y}) on level {lv.name!r}. "
                f"Defined rooms: {[rm[0] for rm in rooms]}. "
                f"Use d.list_rooms(level) to inspect their polygons."
            )
        return RoomHandle(r["id"], self)

    def room_named(
        self,
        name: str,
        level: Union[_Level, int, None] = None,
    ) -> RoomHandle:
        """Return the room with the given label (case-insensitive).

        Example
        -------
        >>> kitchen = d.room_named("Kitchen", level=ground)
        >>> bedroom = d.room_named("Master Bedroom", level=first)
        """
        lv = self._resolve_level(level)
        r = lv._room_named(name)
        if r is None:
            labels = [rm.get("label", "") for rm in lv.rooms]
            raise ValueError(
                f"No room named {name!r} on level {lv.name!r}. "
                f"Available room labels: {labels}. "
                f"Room labels are case-insensitive."
            )
        return RoomHandle(r["id"], self)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def describe(self) -> dict:
        """Return a full JSON-serialisable state snapshot.

        The LLM can call this after every major step to confirm the design
        matches its intent.

        Example
        -------
        >>> state = d.describe()
        >>> state["levels"][0]["wall_count"]
        4
        """
        levels_out = []
        for lv in self._levels:
            levels_out.append({
                "id": lv.id,
                "name": lv.name,
                "floor_height_cm": lv.floor_height,
                "ceiling_height_cm": lv.ceiling_height,
                "wall_count": len(lv.walls),
                "room_count": len(lv.rooms),
                "opening_count": len(lv.openings),
                "furniture_count": len(lv.furniture),
            })
        return {
            "name": self.name,
            "unit": self.unit,
            "level_count": len(self._levels),
            "levels": levels_out,
        }

    def list_walls(
        self,
        level: Union[_Level, int, None] = None,
    ) -> list[dict]:
        """Return all walls on a level as dicts with id, endpoints, thickness, facing.

        Example
        -------
        >>> walls = d.list_walls(ground)
        >>> for w in walls:
        ...     print(w["id"], w["start"], w["end"], w["facing"])
        """
        lv = self._resolve_level(level)
        return [
            {
                "id": w["id"],
                "start": w["start"],
                "end": w["end"],
                "thickness": w["thickness"],
                "is_envelope": w.get("is_envelope", False),
                "facing": w.get("facing"),
            }
            for w in lv.walls
        ]

    def list_rooms(
        self,
        level: Union[_Level, int, None] = None,
    ) -> list[dict]:
        """Return all rooms on a level with id, polygon, area, label.

        Example
        -------
        >>> rooms = d.list_rooms(ground)
        >>> for r in rooms:
        ...     print(r["label"], r["area_m2"], "m²")
        """
        lv = self._resolve_level(level)
        return [
            {
                "id": r["id"],
                "label": r.get("label", ""),
                "polygon": r["polygon"],
                "area_m2": r.get("area_m2", 0.0),
            }
            for r in lv.rooms
        ]

    def list_openings(
        self,
        level: Union[_Level, int, None] = None,
    ) -> list[dict]:
        """Return all doors and windows on a level.

        Example
        -------
        >>> openings = d.list_openings(ground)
        >>> doors = [o for o in openings if o["kind"] == "door"]
        """
        lv = self._resolve_level(level)
        return [
            {
                "id": o["id"],
                "kind": o["kind"],
                "catalog_id": o["catalog_id"],
                "wall_id": o["wall_id"],
                "position_along": o["position_along"],
                "x": o["x"],
                "y": o["y"],
                "width": o["width"],
                "height": o["height"],
                "sill_height": o.get("sill_height", 0.0),
                "label": o.get("label", ""),
            }
            for o in lv.openings
        ]

    def list_catalog_furniture(
        self,
        category: Optional[str] = None,
    ) -> list[str]:
        """Return valid catalog furniture ids.

        Parameters
        ----------
        category : optional filter — one of 'sofa','chair','table','bed',
                   'storage','kitchen','bathroom','door','window','stair','misc'

        Example
        -------
        >>> d.list_catalog_furniture()              # all ids
        >>> d.list_catalog_furniture("kitchen")     # kitchen appliances only
        >>> d.list_catalog_furniture("bathroom")
        """
        if category is not None:
            if category not in _CATALOG:
                cats = list(_CATALOG.keys())
                raise ValueError(
                    f"Unknown category {category!r}. Valid categories: {cats}"
                )
            return list(_CATALOG[category])
        return _all_catalog_ids()

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> dict:
        """Return a structured diagnostic report the LLM can inspect.

        The LLM should call this after each major build step (envelope,
        partitions, rooms) to verify correctness before continuing.

        Returns
        -------
        dict with keys:
          envelope_closed   : [bool, ...]  per level — True if the 4 envelope walls
                              are present and form a closed loop
          orphan_endpoints  : [{level, x, y}, ...]  partition endpoints that don't
                              touch another wall within snap_tolerance
          t_join_failures   : [{level, wall_id, x, y}, ...]  partition endpoints
                              near but not touching a wall (8–20 cm range)
          rooms_unnamed     : [{level, id}, ...]  rooms with empty label
          wall_count_per_level : {level_name: int, ...}
          warnings          : [str, ...]  human-readable advisory messages

        Example
        -------
        >>> report = d.validate()
        >>> if not all(report["envelope_closed"]):
        ...     print("Envelope not closed on some levels!")
        >>> if report["orphan_endpoints"]:
        ...     print("Partition endpoints disconnected:", report["orphan_endpoints"])
        """
        envelope_closed = []
        orphan_endpoints = []
        t_join_failures = []
        rooms_unnamed = []
        wall_count_per_level = {}
        warnings = []

        for lv in self._levels:
            # --- envelope closed? ---
            env_walls = lv._envelope_walls()
            if len(env_walls) >= 4:
                # Build adjacency: each wall endpoint should touch another's endpoint
                endpoints = []
                for w in env_walls:
                    endpoints.append(tuple(w["start"]))
                    endpoints.append(tuple(w["end"]))
                # Check closure: each endpoint should match one other
                unmatched = 0
                for i, pt in enumerate(endpoints):
                    matched = any(
                        j != i and _dist(pt, endpoints[j]) < self._SNAP_TOL
                        for j in range(len(endpoints))
                    )
                    if not matched:
                        unmatched += 1
                envelope_closed.append(unmatched == 0)
            else:
                envelope_closed.append(False)
                if len(env_walls) == 0:
                    warnings.append(
                        f"Level {lv.name!r}: no envelope walls. "
                        f"Call d.envelope(level, width=..., depth=...) to add them."
                    )
                else:
                    warnings.append(
                        f"Level {lv.name!r}: only {len(env_walls)} envelope walls "
                        f"(expected ≥4)."
                    )

            # --- orphan endpoints and T-join failures ---
            for w in lv._partition_walls():
                for label, pt in [("start", tuple(w["start"])), ("end", tuple(w["end"]))]:
                    min_dist = float("inf")
                    for other in lv.walls:
                        if other["id"] == w["id"]:
                            continue
                        d, _ = _pt_to_seg_dist(pt, tuple(other["start"]), tuple(other["end"]))
                        min_dist = min(min_dist, d)
                    if min_dist > self._SNAP_TOL * 2.5:  # >20 cm
                        orphan_endpoints.append({
                            "level": lv.name,
                            "wall_id": w["id"],
                            "endpoint": label,
                            "x": pt[0],
                            "y": pt[1],
                            "nearest_wall_dist_cm": round(min_dist, 1),
                        })
                    elif min_dist > self._SNAP_TOL:  # 8–20 cm: near-miss
                        t_join_failures.append({
                            "level": lv.name,
                            "wall_id": w["id"],
                            "endpoint": label,
                            "x": pt[0],
                            "y": pt[1],
                            "gap_cm": round(min_dist, 1),
                        })

            # --- unnamed rooms ---
            for r in lv.rooms:
                if not r.get("label"):
                    rooms_unnamed.append({"level": lv.name, "id": r["id"]})

            wall_count_per_level[lv.name] = len(lv.walls)

        # Advisory warnings
        for lv in self._levels:
            if len(lv.rooms) == 0 and len(lv.walls) > 0:
                warnings.append(
                    f"Level {lv.name!r} has walls but no rooms defined. "
                    f"Call d.room(level, polygon=..., label=...) to define rooms."
                )
            if len(lv.furniture) == 0 and len(lv.rooms) > 0:
                warnings.append(
                    f"Level {lv.name!r} has no furniture. "
                    f"Call d.place_furniture(level, catalog_id=..., x=..., y=...) to add some."
                )

        return {
            "envelope_closed": envelope_closed,
            "orphan_endpoints": orphan_endpoints,
            "t_join_failures": t_join_failures,
            "rooms_unnamed": rooms_unnamed,
            "wall_count_per_level": wall_count_per_level,
            "warnings": warnings,
        }

    # ------------------------------------------------------------------
    # Spec round-trip
    # ------------------------------------------------------------------

    def to_spec(self) -> dict:
        """Serialise the entire design to a plain JSON-serialisable dict.

        The LLM can save this dict (as JSON) then pass it to Designer.from_spec()
        to reconstruct an equivalent Designer, or hand off to the CLI:

            python3 -m cli_anything.sweethome3d.core.designer \\
                --spec design.json --out Home.sh3d --render Home.png

        Example
        -------
        >>> spec = d.to_spec()
        >>> import json
        >>> json.dump(spec, open("design.json", "w"), indent=2)
        >>> d2 = Designer.from_spec(spec)
        """
        return {
            "spec_version": "1.0",
            "meta": {
                "name": self.name,
                "unit": self.unit,
                **self._meta,
            },
            "levels": [lv.to_dict() for lv in self._levels],
        }

    @classmethod
    def from_spec(cls, spec: dict) -> "Designer":
        """Reconstruct a Designer from a spec dict (produced by to_spec()).

        Parameters
        ----------
        spec : dict produced by d.to_spec() or loaded from a JSON file

        Returns
        -------
        A new Designer instance equivalent to the original.

        Example
        -------
        >>> import json
        >>> spec = json.load(open("design.json"))
        >>> d = Designer.from_spec(spec)
        >>> report = d.validate()
        """
        if not isinstance(spec, dict):
            raise TypeError(
                f"from_spec() expects a dict, got {type(spec).__name__}. "
                "Load your JSON file with json.load() first."
            )
        meta = spec.get("meta", {})
        d = cls(name=meta.get("name", "Home"), unit=meta.get("unit", "CENTIMETER"))
        d._meta = {k: v for k, v in meta.items() if k not in ("name", "unit")}
        for lv_dict in spec.get("levels", []):
            lv = _Level.from_dict(lv_dict)
            d._levels.append(lv)
        return d

    # ------------------------------------------------------------------
    # Export to SH3D
    # ------------------------------------------------------------------

    def save(self, path: Union[str, Path], *, render_png: Optional[Union[str, Path]] = None) -> Path:
        """Write a .sh3d file (ZIP format) and optionally a PNG floor-plan render.

        Parameters
        ----------
        path       : destination .sh3d file path
        render_png : if given, also write a PNG floor-plan image here

        Returns
        -------
        Path to the written .sh3d file.

        Example
        -------
        >>> d.save("Home.sh3d", render_png="Home.png")
        """
        path = Path(path)
        xml = self._to_sh3d_xml()
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("Home.xml", xml.encode("utf-8"))
            # Add a minimal thumbnail placeholder
            zf.writestr("thumbnail.png", self._make_thumbnail_png())
        if render_png is not None:
            self._render_png(Path(render_png))
        return path

    def _to_sh3d_xml(self) -> str:
        """Generate SweetHome3D XML representation."""
        lines = ['<?xml version="1.0" encoding="UTF-8"?>']
        lines.append(f'<home version="7.2" name="{_xml_escape(self.name)}" '
                     f'wallHeight="250" unit="{self.unit}">')

        # Levels
        for lv in self._levels:
            lines.append(
                f'  <level id="{lv.id}" name="{_xml_escape(lv.name)}" '
                f'elevation="{lv.floor_height}" height="{lv.ceiling_height}" '
                f'floorThickness="20" visible="true" />'
            )

        # Walls
        for lv in self._levels:
            for w in lv.walls:
                sx, sy = w["start"]
                ex, ey = w["end"]
                lid = f' level="{lv.id}"' if len(self._levels) > 1 else ""
                lines.append(
                    f'  <wall id="{w["id"]}" '
                    f'xStart="{sx:.2f}" yStart="{sy:.2f}" '
                    f'xEnd="{ex:.2f}" yEnd="{ey:.2f}" '
                    f'thickness="{w["thickness"]:.1f}"{lid} />'
                )

        # Rooms
        for lv in self._levels:
            for r in lv.rooms:
                lid = f' level="{lv.id}"' if len(self._levels) > 1 else ""
                pts_str = " ".join(
                    f'<point x="{p[0]:.2f}" y="{p[1]:.2f}" />' for p in r["polygon"]
                )
                fc = f' floorColor="{_color_int(r["floor_color"])}"' if r.get("floor_color") else ""
                cc = f' ceilingColor="{_color_int(r["ceiling_color"])}"' if r.get("ceiling_color") else ""
                lines.append(
                    f'  <room id="{r["id"]}" name="{_xml_escape(r.get("label",""))}"'
                    f'{fc}{cc}{lid}>{pts_str}</room>'
                )

        # Openings (doors + windows)
        # Both doors and windows are <doorOrWindow> elements in SH3D XML.
        # isDoor="true" for doors, isDoor="false" for windows.
        # depth (wall penetration) is the thickness of the wall the opening sits on.
        for lv in self._levels:
            for o in lv.openings:
                lid = f' level="{lv.id}"' if len(self._levels) > 1 else ""
                is_door = "true" if o["kind"] == "door" else "false"
                wobj = lv._find_wall(o.get("wall_id", ""))
                wall_thickness = wobj["thickness"] if wobj else 20.0
                lines.append(
                    f'  <doorOrWindow id="{o["id"]}" catalogId="{o["catalog_id"]}" '
                    f'name="{_xml_escape(o.get("label",""))}" '
                    f'isDoor="{is_door}" '
                    f'x="{o["x"]:.2f}" y="{o["y"]:.2f}" '
                    f'elevation="{o.get("sill_height",0):.1f}" '
                    f'width="{o["width"]:.1f}" depth="{wall_thickness:.1f}" '
                    f'height="{o["height"]:.1f}" wallSide="BOTH"{lid} />'
                )

        # Furniture
        for lv in self._levels:
            for f in lv.furniture:
                lid = f' level="{lv.id}"' if len(self._levels) > 1 else ""
                w_attr = f' width="{f["width"]}"' if f.get("width") else ""
                d_attr = f' depth="{f["depth"]}"' if f.get("depth") else ""
                h_attr = f' height="{f["height"]}"' if f.get("height") else ""
                lines.append(
                    f'  <pieceOfFurniture id="{f["id"]}" catalogId="{f["catalog_id"]}" '
                    f'name="{_xml_escape(f.get("label",""))}" '
                    f'x="{f["x"]:.2f}" y="{f["y"]:.2f}" '
                    f'elevation="0" angle="{math.radians(f["rotation_deg"]):.4f}" '
                    f'{w_attr}{d_attr}{h_attr}{lid} />'
                )

        lines.append("</home>")
        return "\n".join(lines)

    def _make_thumbnail_png(self) -> bytes:
        """Create a minimal 1×1 white PNG as placeholder thumbnail."""
        # PNG signature + IHDR + IDAT + IEND
        def chunk(name: bytes, data: bytes) -> bytes:
            crc = zlib.crc32(name + data) & 0xFFFFFFFF
            return struct.pack(">I", len(data)) + name + data + struct.pack(">I", crc)

        sig = b"\x89PNG\r\n\x1a\n"
        ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        raw = b"\x00\xff\xff\xff"
        idat = chunk(b"IDAT", zlib.compress(raw))
        iend = chunk(b"IEND", b"")
        return sig + ihdr + idat + iend

    def _render_png(self, path: Path) -> None:
        """Write a simple 2-D floor-plan PNG using only stdlib (no Pillow required)."""
        try:
            from cli_anything.sweethome3d.core.renderer import render_floorplan
            render_floorplan(self, path)
        except ImportError:
            # Fall back to minimal SVG→PNG via cairosvg if available
            try:
                import cairosvg  # type: ignore
                svg = self._to_svg()
                cairosvg.svg2png(bytestring=svg.encode(), write_to=str(path))
            except ImportError:
                # Last resort: just write a placeholder PNG
                path.write_bytes(self._make_placeholder_png(800, 600))

    def _make_placeholder_png(self, w: int, h: int) -> bytes:
        """Create a minimal valid PNG (grey rectangle) without Pillow."""

        def make_chunk(ctype: bytes, data: bytes) -> bytes:
            crc = zlib.crc32(ctype + data) & 0xFFFFFFFF
            return struct.pack(">I", len(data)) + ctype + data + struct.pack(">I", crc)

        sig = b"\x89PNG\r\n\x1a\n"
        ihdr_data = struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0)  # greyscale
        ihdr = make_chunk(b"IHDR", ihdr_data)
        # Build image rows: one filter byte per row + grey pixels
        raw_rows = b""
        for _ in range(h):
            raw_rows += b"\x00" + bytes([200]) * w  # filter=None + light grey
        idat = make_chunk(b"IDAT", zlib.compress(raw_rows))
        iend = make_chunk(b"IEND", b"")
        return sig + ihdr + idat + iend

    def to_svg(self) -> str:
        """Return an SVG floor-plan string for the design (public API).

        Delegates to the internal SVG generator. Renderers and external
        callers should use this method rather than the private ``_to_svg``.
        """
        return self._to_svg()

    def _to_svg(self) -> str:
        """Minimal SVG floor-plan for quick rendering."""
        # Compute bounding box — include walls, rooms, and furniture so that
        # furniture placed outside the wall/room extents is not clipped.
        all_pts: list[Pt] = []
        for lv in self._levels:
            for w in lv.walls:
                all_pts.append(tuple(w["start"]))
                all_pts.append(tuple(w["end"]))
            for r in lv.rooms:
                all_pts.extend(tuple(p) for p in r["polygon"])
            for f in lv.furniture:
                all_pts.append((float(f["x"]), float(f["y"])))
        if not all_pts:
            return '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600"/>'
        min_x = min(p[0] for p in all_pts)
        min_y = min(p[1] for p in all_pts)
        max_x = max(p[0] for p in all_pts)
        max_y = max(p[1] for p in all_pts)
        scale = min(800.0 / max(max_x - min_x, 1), 600.0 / max(max_y - min_y, 1))
        margin = 20

        def tx(x: float) -> float:
            return margin + (x - min_x) * scale

        def ty(y: float) -> float:
            return margin + (y - min_y) * scale

        lines = [
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{int(max_x - min_x) * scale + 2 * margin:.0f}" '
            f'height="{int(max_y - min_y) * scale + 2 * margin:.0f}" '
            f'style="background:#f8f8f0">'
        ]
        # Draw rooms first (filled polygons)
        for lv in self._levels:
            for r in lv.rooms:
                pts_str = " ".join(f"{tx(p[0]):.1f},{ty(p[1]):.1f}" for p in r["polygon"])
                color = r.get("floor_color") or "#ddd8c4"
                lines.append(
                    f'<polygon points="{pts_str}" '
                    f'fill="{color}" stroke="#888" stroke-width="0.5" opacity="0.7"/>'
                )
                cx, cy = _polygon_centroid([tuple(p) for p in r["polygon"]])
                label = r.get("label", "")
                if label:
                    lines.append(
                        f'<text x="{tx(cx):.1f}" y="{ty(cy):.1f}" '
                        f'font-size="10" text-anchor="middle" fill="#333">{_xml_escape(label)}</text>'
                    )
        # Draw walls
        for lv in self._levels:
            for w in lv.walls:
                sx, sy = w["start"]
                ex, ey = w["end"]
                stroke_w = 3.0 if w.get("is_envelope") else 1.5
                color = "#222" if w.get("is_envelope") else "#555"
                lines.append(
                    f'<line x1="{tx(sx):.1f}" y1="{ty(sy):.1f}" '
                    f'x2="{tx(ex):.1f}" y2="{ty(ey):.1f}" '
                    f'stroke="{color}" stroke-width="{stroke_w:.1f}"/>'
                )
        # Draw openings
        for lv in self._levels:
            for o in lv.openings:
                color = "#e07b2a" if o["kind"] == "door" else "#4a90d9"
                r_px = max(3.0, o["width"] * scale / 4.0)
                lines.append(
                    f'<circle cx="{tx(o["x"]):.1f}" cy="{ty(o["y"]):.1f}" '
                    f'r="{r_px:.1f}" fill="{color}" opacity="0.8"/>'
                )
        # Draw furniture — simple filled rectangles at (x, y).
        for lv in self._levels:
            for f in lv.furniture:
                fw = float(f.get("width") or 60)
                fd = float(f.get("depth") or 60)
                # Centre the rectangle on the furniture's (x, y)
                rx = tx(f["x"]) - fw * scale / 2.0
                ry = ty(f["y"]) - fd * scale / 2.0
                lines.append(
                    f'<rect x="{rx:.1f}" y="{ry:.1f}" '
                    f'width="{fw * scale:.1f}" height="{fd * scale:.1f}" '
                    f'fill="#8a8a8a" stroke="#444" stroke-width="0.5" opacity="0.6"/>'
                )
                label = f.get("label", "")
                if label:
                    lines.append(
                        f'<text x="{tx(f["x"]):.1f}" y="{ty(f["y"]):.1f}" '
                        f'font-size="7" text-anchor="middle" fill="#222">'
                        f'{_xml_escape(label)}</text>'
                    )
        lines.append("</svg>")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _xml_escape(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _color_int(hex_color: str) -> int:
    """Convert '#RRGGBB' to SH3D integer ARGB.

    Returns a default grey (0xFF888888) for malformed input instead of
    raising, so the renderer and XML export stay robust.
    """
    try:
        h = str(hex_color).lstrip("#")
        if len(h) != 6:
            return 0xFF888888
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return (0xFF << 24) | (r << 16) | (g << 8) | b
    except (ValueError, TypeError):
        return 0xFF888888


# ---------------------------------------------------------------------------
# Allow `python3 -m cli_anything.sweethome3d.core.designer ...` invocation
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from cli_anything.sweethome3d.core.__main__ import main  # type: ignore
    main()
