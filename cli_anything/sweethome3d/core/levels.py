"""Level operations — multi-floor support."""

from __future__ import annotations

from copy import deepcopy
from typing import Optional

from cli_anything.sweethome3d.core.model import (
    DimensionLine,
    Home,
    Label,
    Level,
    PieceOfFurniture,
    Polyline,
    Room,
    Wall,
    _gen_id,
)


def list_levels(home: Home) -> list[Level]:
    return list(home.levels)


def add_level(home: Home, name: str, *, elevation: float = 0,
               height: float = 250, floorThickness: float = 12) -> Level:
    if any(l.name == name for l in home.levels):
        raise ValueError(f"level named {name!r} already exists")
    idx = max((l.elevationIndex for l in home.levels), default=-1) + 1
    lvl = Level(name=name, elevation=elevation, height=height,
                  floorThickness=floorThickness, elevationIndex=idx)
    home.levels.append(lvl)
    return lvl


def delete_level(home: Home, ident: str, *,
                   detach: bool = True) -> bool:
    """Delete a level. If `detach` is True (default), any objects on that
    level are detached (level=None); otherwise the call fails when objects
    are still attached.
    """
    lvl = home.find_level(ident)
    if lvl is None:
        return False
    attached = [
        *(o for o in home.walls if o.level == lvl.id),
        *(o for o in home.rooms if o.level == lvl.id),
        *(o for o in home.furniture if o.level == lvl.id),
        *(o for o in home.dimensionLines if o.level == lvl.id),
        *(o for o in home.labels if o.level == lvl.id),
        *(o for o in home.polylines if o.level == lvl.id),
    ]
    if attached and not detach:
        raise ValueError(
            f"level {lvl.name!r} has {len(attached)} attached objects; "
            "pass detach=True to clear them")
    for obj in attached:
        obj.level = None
    home.levels.remove(lvl)
    if home.selectedLevel == lvl.id:
        home.selectedLevel = None
    return True


def set_level_properties(home: Home, ident: str, **fields) -> Level:
    lvl = home.find_level(ident)
    if lvl is None:
        raise KeyError(ident)
    for k, v in fields.items():
        if not hasattr(lvl, k):
            raise AttributeError(f"unknown level field: {k!r}")
        setattr(lvl, k, v)
    return lvl


def duplicate_level(home: Home, src_ident: str, *,
                      new_name: str,
                      elevation: Optional[float] = None,
                      offset_x: float = 0,
                      offset_y: float = 0,
                      include_walls: bool = True,
                      include_rooms: bool = True,
                      include_furniture: bool = True,
                      include_annotations: bool = True) -> Level:
    """Deep-copy a level's geometry to a new level at a different elevation.

    Walls, rooms, dimension lines, labels, polylines, and furniture on
    the source level are duplicated with fresh ids and re-attached to
    the new level. Wall-to-wall ``wallAtStart`` / ``wallAtEnd`` links
    are remapped to the duplicated walls so the new floor's geometry
    is internally consistent.

    ``elevation`` defaults to ``src.elevation + src.height + src.floorThickness``
    — the natural "stack on top" position. Override to place the duplicate
    anywhere on the Z axis (e.g. -250 for a basement copy of the ground
    floor).

    Furniture inside :class:`FurnitureGroup` containers is not duplicated
    (groups stay on their original level). Pass each piece individually
    after duplication if you need cross-level grouping.
    """
    src = home.find_level(src_ident)
    if src is None:
        raise KeyError(f"level not found: {src_ident}")
    if any(L.name == new_name for L in home.levels):
        raise ValueError(f"level named {new_name!r} already exists")

    if elevation is None:
        elevation = src.elevation + src.height + src.floorThickness
    idx = max((L.elevationIndex for L in home.levels), default=-1) + 1
    new_lvl = Level(name=new_name,
                     elevation=elevation,
                     height=src.height,
                     floorThickness=src.floorThickness,
                     elevationIndex=idx,
                     visible=src.visible,
                     viewable=src.viewable)
    home.levels.append(new_lvl)

    # `level` attributes on existing objects may store the level *id*
    # (canonical, what SH3D writes) or its *name* (what the CLI's --level
    # flag passes through). Accept both as referring to the source level.
    def _belongs(level_ref: Optional[str]) -> bool:
        return level_ref == src.id or level_ref == src.name

    # Walls: deep-copy + remap wallAtStart / wallAtEnd
    wall_id_map: dict[str, str] = {}
    if include_walls:
        # First pass: clone walls with new ids, parked unlinked
        new_walls: list[Wall] = []
        for w in home.walls:
            if not _belongs(w.level):
                continue
            nw = deepcopy(w)
            nw.id = _gen_id()
            nw.level = new_lvl.id
            nw.xStart += offset_x; nw.xEnd += offset_x
            nw.yStart += offset_y; nw.yEnd += offset_y
            wall_id_map[w.id] = nw.id
            new_walls.append(nw)
        # Second pass: rewire wallAtStart / wallAtEnd to the cloned ids
        for nw in new_walls:
            if nw.wallAtStart in wall_id_map:
                nw.wallAtStart = wall_id_map[nw.wallAtStart]
            else:
                nw.wallAtStart = None
            if nw.wallAtEnd in wall_id_map:
                nw.wallAtEnd = wall_id_map[nw.wallAtEnd]
            else:
                nw.wallAtEnd = None
        home.walls.extend(new_walls)

    # Rooms (polygon coordinates also get offset)
    if include_rooms:
        for r in list(home.rooms):
            if not _belongs(r.level):
                continue
            nr = deepcopy(r)
            nr.id = _gen_id()
            nr.level = new_lvl.id
            for p in nr.points:
                p.x += offset_x
                p.y += offset_y
            home.rooms.append(nr)

    # Furniture (only top-level pieces; groups stay on the source level)
    if include_furniture:
        for f in list(home.furniture):
            if not _belongs(f.level):
                continue
            nf = deepcopy(f)
            nf.id = _gen_id()
            nf.level = new_lvl.id
            nf.x += offset_x
            nf.y += offset_y
            home.furniture.append(nf)

    # Annotations
    if include_annotations:
        for d in list(home.dimensionLines):
            if not _belongs(d.level):
                continue
            nd = deepcopy(d)
            nd.id = _gen_id()
            nd.level = new_lvl.id
            nd.xStart += offset_x; nd.xEnd += offset_x
            nd.yStart += offset_y; nd.yEnd += offset_y
            home.dimensionLines.append(nd)
        for lb in list(home.labels):
            if not _belongs(lb.level):
                continue
            nlb = deepcopy(lb)
            nlb.id = _gen_id()
            nlb.level = new_lvl.id
            nlb.x += offset_x
            nlb.y += offset_y
            home.labels.append(nlb)
        for p in list(home.polylines):
            if not _belongs(p.level):
                continue
            np = deepcopy(p)
            np.id = _gen_id()
            np.level = new_lvl.id
            for pt in np.points:
                pt.x += offset_x
                pt.y += offset_y
            home.polylines.append(np)

    return new_lvl


def select_level(home: Home, ident: Optional[str]) -> Optional[Level]:
    if ident is None:
        home.selectedLevel = None
        return None
    lvl = home.find_level(ident)
    if lvl is None:
        raise KeyError(ident)
    home.selectedLevel = lvl.id
    return lvl
