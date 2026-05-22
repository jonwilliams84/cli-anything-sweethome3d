"""Level operations — multi-floor support."""

from __future__ import annotations

from typing import Optional

from cli_anything.sweethome3d.core.model import Home, Level


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


def select_level(home: Home, ident: Optional[str]) -> Optional[Level]:
    if ident is None:
        home.selectedLevel = None
        return None
    lvl = home.find_level(ident)
    if lvl is None:
        raise KeyError(ident)
    home.selectedLevel = lvl.id
    return lvl
