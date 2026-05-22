"""Furniture operations — pieces, doors/windows, lights."""

from __future__ import annotations

from typing import Optional

from cli_anything.sweethome3d.core.model import Home, PieceOfFurniture


KINDS = ("pieceOfFurniture", "doorOrWindow", "light")

# SH3D opens a wall opening where a doorOrWindow's footprint overlaps the
# wall AND `cutOutShape` is set. The default unit-square path tells SH3D to
# cut a full-rectangle opening matching the piece footprint.
DEFAULT_CUT_OUT_SHAPE = "M0,0 v1 h1 v-1 z"

# Stock SH3D 7.x default-catalog ids. Used as fallbacks when the user does
# not specify --catalog-id so SH3D has a visible 3D model for the opening.
# All ids must exist in `_sh3d_catalog_metadata.SH3D_CATALOG`, otherwise the
# saved piece has no model reference and is invisible in SH3D's 3D view.
DEFAULT_DOOR_CATALOG_ID = "eTeks#doorFrame"
DEFAULT_WINDOW_CATALOG_ID = "eTeks#fixedWindow85x123"
DEFAULT_LIGHT_CATALOG_ID = "eTeks#pendantLamp"


def list_furniture(home: Home, *, kind: Optional[str] = None,
                    level: Optional[str] = None) -> list[PieceOfFurniture]:
    items = home.furniture
    if kind is not None:
        if kind not in KINDS:
            raise ValueError(f"kind must be one of {KINDS}")
        items = [f for f in items if f.kind == kind]
    if level is not None:
        items = [f for f in items if f.level == level]
    return list(items)


def add_piece(home: Home, name: str, x: float, y: float,
               *, width: float, depth: float, height: float,
               kind: str = "pieceOfFurniture",
               catalogId: Optional[str] = None,
               model: Optional[str] = None,
               level: Optional[str] = None,
               elevation: float = 0,
               angle: float = 0,
               color: Optional[int] = None,
               power: Optional[float] = None,
               wallThickness: Optional[float] = None,
               wallDistance: Optional[float] = None,
               wallWidth: Optional[float] = None,
               wallLeft: Optional[float] = None,
               wallTop: Optional[float] = None,
               wallHeight: Optional[float] = None,
               boundToWall: Optional[bool] = None,
               cutOutShape: Optional[str] = None) -> PieceOfFurniture:
    """Add a piece of furniture / door-or-window / light at (x, y).

    If `catalogId` does not exist in the SH3D catalog, a warning is issued
    and the piece may render as 'damaged' in SH3D 7.x.
    """
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    if width <= 0 or depth <= 0 or height <= 0:
        raise ValueError("width, depth, height must all be positive")
    if catalogId is not None:
        from cli_anything.sweethome3d.core import _sh3d_catalog_metadata as _md
        if catalogId not in _md.SH3D_CATALOG:
            import warnings
            warnings.warn(
                f"catalog id {catalogId!r} not found in SH3D catalog; "
                f"piece will render as 'damaged' in SH3D 7.x",
                stacklevel=2,
            )
    f = PieceOfFurniture(
        name=name, x=x, y=y,
        width=width, depth=depth, height=height,
        kind=kind, catalogId=catalogId, model=model,
        level=level, elevation=elevation, angle=angle,
        color=color,
        power=power if kind == "light" else None,
        wallThickness=wallThickness if kind == "doorOrWindow" else None,
        wallDistance=wallDistance if kind == "doorOrWindow" else None,
        wallWidth=wallWidth if kind == "doorOrWindow" else None,
        wallLeft=wallLeft if kind == "doorOrWindow" else None,
        wallTop=wallTop if kind == "doorOrWindow" else None,
        wallHeight=wallHeight if kind == "doorOrWindow" else None,
        boundToWall=boundToWall if kind == "doorOrWindow" else None,
        cutOutShape=cutOutShape if kind == "doorOrWindow" else None,
    )
    home.furniture.append(f)
    return f


def add_door(home: Home, name: str, x: float, y: float, *,
              width: float = 80, depth: float = 10, height: float = 200,
              catalogId: Optional[str] = None,
              cutOutShape: Optional[str] = None,
              **kwargs) -> PieceOfFurniture:
    # Note: do NOT set wallThickness — SH3D's default behaviour (omit
    # attribute) lets the engine compute the wall-cut from the piece's
    # own depth, which matches how the wall-binding detection runs.
    # Explicitly writing wallThickness=1.0 was suppressing the auto-bind
    # for some doors in the render.
    return add_piece(home, name, x, y, width=width, depth=depth, height=height,
                      kind="doorOrWindow",
                      catalogId=catalogId if catalogId is not None else DEFAULT_DOOR_CATALOG_ID,
                      cutOutShape=cutOutShape if cutOutShape is not None else DEFAULT_CUT_OUT_SHAPE,
                      **kwargs)


def add_window(home: Home, name: str, x: float, y: float, *,
                width: float = 100, depth: float = 10, height: float = 120,
                elevation: float = 100,
                catalogId: Optional[str] = None,
                cutOutShape: Optional[str] = None,
                **kwargs) -> PieceOfFurniture:
    return add_piece(home, name, x, y, width=width, depth=depth, height=height,
                      kind="doorOrWindow", elevation=elevation,
                      catalogId=catalogId if catalogId is not None else DEFAULT_WINDOW_CATALOG_ID,
                      cutOutShape=cutOutShape if cutOutShape is not None else DEFAULT_CUT_OUT_SHAPE,
                      **kwargs)


def add_light(home: Home, name: str, x: float, y: float, *,
               width: float = 20, depth: float = 20, height: float = 20,
               elevation: float = 220,
               power: float = 0.5,
               color: int = 0xFFFFE0,
               catalogId: Optional[str] = None,
               **kwargs) -> PieceOfFurniture:
    return add_piece(home, name, x, y, width=width, depth=depth, height=height,
                      kind="light", elevation=elevation,
                      power=power, color=color,
                      catalogId=catalogId if catalogId is not None else DEFAULT_LIGHT_CATALOG_ID,
                      **kwargs)


def delete_piece(home: Home, ident: str) -> bool:
    f = home.find_furniture(ident)
    if f is None:
        return False
    home.furniture.remove(f)
    return True


def move_piece(home: Home, ident: str, *,
                x: Optional[float] = None, y: Optional[float] = None,
                elevation: Optional[float] = None,
                angle: Optional[float] = None) -> PieceOfFurniture:
    f = home.find_furniture(ident)
    if f is None:
        raise KeyError(ident)
    if x is not None: f.x = x
    if y is not None: f.y = y
    if elevation is not None: f.elevation = elevation
    if angle is not None: f.angle = angle
    return f


def set_piece_properties(home: Home, ident: str, **fields) -> PieceOfFurniture:
    f = home.find_furniture(ident)
    if f is None:
        raise KeyError(ident)
    for k, v in fields.items():
        if not hasattr(f, k):
            raise AttributeError(f"unknown furniture field: {k!r}")
        setattr(f, k, v)
    return f
