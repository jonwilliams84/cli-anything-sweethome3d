"""Furniture groups — bundle pieces so they move/rotate as a unit.

Mirrors the SH3D `FurnitureGroup` model (DTD: `<furnitureGroup>` containing
nested `<pieceOfFurniture>` / `<doorOrWindow>` / `<light>` / nested groups).
A group keeps its members in its own `furniture` list; top-level
`home.furniture` lists are unaffected except that members are *moved* (not
copied) into the group so they don't render twice.

Group bounding-box (`x`, `y`, `elevation`, `width`, `depth`, `height`) is
recomputed when members change so the group's plan-view footprint stays
honest.
"""

from __future__ import annotations

from typing import Iterable, Optional

from cli_anything.sweethome3d.core.model import (
    FurnitureGroup,
    Home,
    PieceOfFurniture,
)


def list_groups(home: Home, *,
                  level: Optional[str] = None) -> list[FurnitureGroup]:
    """Return all furniture groups, optionally filtered by level id/name."""
    groups = list(home.furnitureGroups)
    if level is not None:
        lvl_id = _resolve_level_id(home, level)
        groups = [g for g in groups if g.level == lvl_id]
    return groups


def find_group(home: Home, ident: str) -> Optional[FurnitureGroup]:
    """Return the group whose id or name matches `ident`."""
    for g in home.furnitureGroups:
        if g.id == ident or g.name == ident:
            return g
    return None


def _resolve_level_id(home: Home, level: Optional[str]) -> Optional[str]:
    if level is None:
        return None
    lvl = home.find_level(level)
    return lvl.id if lvl is not None else level


def _recompute_bounds(group: FurnitureGroup) -> None:
    """Refresh the group's plan footprint from its current members.

    Empty groups keep their previously-stored bounds (no None overwrite) so
    a deliberately positioned empty group can still be picked up later.
    """
    if not group.furniture:
        return
    xs_lo, ys_lo, zs_lo = [], [], []
    xs_hi, ys_hi, zs_hi = [], [], []
    for member in group.furniture:
        if isinstance(member, FurnitureGroup):
            if member.x is None or member.width is None:
                continue
            cx = member.x
            cy = member.y or 0
            w = member.width or 0
            d = member.depth or 0
            ce = member.elevation or 0
            ch = member.height or 0
        else:
            cx = member.x
            cy = member.y
            w = member.width
            d = member.depth
            ce = member.elevation
            ch = member.height
        xs_lo.append(cx - w / 2)
        xs_hi.append(cx + w / 2)
        ys_lo.append(cy - d / 2)
        ys_hi.append(cy + d / 2)
        zs_lo.append(ce)
        zs_hi.append(ce + ch)
    if not xs_lo:
        return
    group.x = (min(xs_lo) + max(xs_hi)) / 2
    group.y = (min(ys_lo) + max(ys_hi)) / 2
    group.width = max(xs_hi) - min(xs_lo)
    group.depth = max(ys_hi) - min(ys_lo)
    group.elevation = min(zs_lo)
    group.height = max(zs_hi) - min(zs_lo)


def create_group(home: Home, name: str, *,
                  piece_idents: Iterable[str],
                  level: Optional[str] = None) -> FurnitureGroup:
    """Build a new group from existing pieces and move them into it.

    `piece_idents` are resolved via `Home.find_furniture` (id or
    case-insensitive name). Pieces are removed from `home.furniture` and
    appended to the new group. Raises `KeyError` for any missing piece.
    Raises `ValueError` if `piece_idents` is empty.
    """
    members: list[PieceOfFurniture] = []
    seen = set()
    for ident in piece_idents:
        piece = home.find_furniture(ident)
        if piece is None:
            raise KeyError(f"furniture not found: {ident}")
        if id(piece) in seen:
            continue
        seen.add(id(piece))
        members.append(piece)
    if not members:
        raise ValueError("at least one piece is required to create a group")
    lvl_id = _resolve_level_id(home, level) or members[0].level
    for piece in members:
        home.furniture.remove(piece)
    group = FurnitureGroup(name=name, level=lvl_id, furniture=members)
    _recompute_bounds(group)
    home.furnitureGroups.append(group)
    return group


def ungroup(home: Home, ident: str) -> list[PieceOfFurniture]:
    """Dissolve a group, putting its members back into `home.furniture`.

    Nested sub-groups are preserved (flattened up one level: a nested group
    becomes a top-level group again). Returns the list of released pieces.
    """
    group = find_group(home, ident)
    if group is None:
        raise KeyError(f"group not found: {ident}")
    released: list[PieceOfFurniture] = []
    for member in group.furniture:
        if isinstance(member, FurnitureGroup):
            home.furnitureGroups.append(member)
        else:
            home.furniture.append(member)
            released.append(member)
    home.furnitureGroups.remove(group)
    return released


def add_to_group(home: Home, group_ident: str,
                   piece_idents: Iterable[str]) -> FurnitureGroup:
    """Move existing top-level pieces into an existing group."""
    group = find_group(home, group_ident)
    if group is None:
        raise KeyError(f"group not found: {group_ident}")
    for ident in piece_idents:
        piece = home.find_furniture(ident)
        if piece is None:
            raise KeyError(f"furniture not found: {ident}")
        home.furniture.remove(piece)
        group.furniture.append(piece)
    _recompute_bounds(group)
    return group


def remove_from_group(home: Home, group_ident: str,
                        piece_idents: Iterable[str]) -> FurnitureGroup:
    """Move pieces out of a group, back into `home.furniture`."""
    group = find_group(home, group_ident)
    if group is None:
        raise KeyError(f"group not found: {group_ident}")
    targets = set()
    for ident in piece_idents:
        for member in group.furniture:
            if isinstance(member, PieceOfFurniture) and (
                member.id == ident
                or (member.name and member.name.lower() == ident.lower())
            ):
                targets.add(id(member))
                break
        else:
            raise KeyError(f"piece not in group {group.name!r}: {ident}")
    kept = []
    for member in group.furniture:
        if id(member) in targets:
            home.furniture.append(member)
        else:
            kept.append(member)
    group.furniture = kept
    _recompute_bounds(group)
    return group


def delete_group(home: Home, ident: str) -> list[PieceOfFurniture]:
    """Delete a group AND its member pieces entirely.

    Distinct from `ungroup`: `delete_group` discards the members instead of
    releasing them. Returns the deleted pieces so callers can log/inspect.
    """
    group = find_group(home, ident)
    if group is None:
        raise KeyError(f"group not found: {ident}")
    home.furnitureGroups.remove(group)
    deleted: list[PieceOfFurniture] = []
    for member in group.furniture:
        if isinstance(member, PieceOfFurniture):
            deleted.append(member)
    return deleted


_SETTABLE_FIELDS = {
    "name", "x", "y", "elevation", "angle", "width", "depth", "height",
    "visible", "movable", "modelMirrored", "nameVisible", "nameAngle",
    "nameXOffset", "nameYOffset", "price", "description", "information",
    "license", "creator",
}


def set_group_properties(home: Home, ident: str, **fields) -> FurnitureGroup:
    """Update one or more attributes on an existing group."""
    group = find_group(home, ident)
    if group is None:
        raise KeyError(f"group not found: {ident}")
    for k, v in fields.items():
        if k not in _SETTABLE_FIELDS:
            raise AttributeError(f"unknown group field: {k!r}")
        setattr(group, k, v)
    return group
