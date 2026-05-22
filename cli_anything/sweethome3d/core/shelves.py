"""Shelf-unit shelves — flat planes or 3D bounding boxes inside a shelfUnit.

A SH3D `shelfUnit` piece carries a list of `Shelf` entries that describe
where shelves sit inside the cabinet. Two variants:

- **Flat shelf**: only `elevation` is set; the shelf spans the unit's full
  width and depth at the given Z.
- **Box shelf**: all six bounds (`xLower..zUpper`) are set; describes an
  arbitrary axis-aligned compartment.

The data layer round-trips both; we only expose simple add/delete here
since this is rarely a hot edit surface.
"""

from __future__ import annotations

from typing import Optional

from cli_anything.sweethome3d.core.model import Home, PieceOfFurniture, Shelf


def _resolve_shelf_unit(home: Home, ident: str) -> PieceOfFurniture:
    piece = home.find_furniture(ident)
    if piece is None:
        raise KeyError(f"furniture not found: {ident}")
    if piece.kind != "shelfUnit":
        raise ValueError(
            f"shelves apply to shelfUnit pieces only; {piece.name!r} is "
            f"kind={piece.kind!r}"
        )
    return piece


def list_shelves(home: Home, piece_ident: str) -> list[Shelf]:
    return list(_resolve_shelf_unit(home, piece_ident).shelves)


def add_flat_shelf(home: Home, piece_ident: str,
                     elevation: float) -> Shelf:
    """Append a flat shelf at the given Z (cm)."""
    piece = _resolve_shelf_unit(home, piece_ident)
    shelf = Shelf(elevation=elevation)
    piece.shelves.append(shelf)
    return shelf


def add_box_shelf(home: Home, piece_ident: str, *,
                    xLower: float, yLower: float, zLower: float,
                    xUpper: float, yUpper: float, zUpper: float) -> Shelf:
    """Append a 3D box-bound shelf compartment."""
    piece = _resolve_shelf_unit(home, piece_ident)
    if xUpper <= xLower or yUpper <= yLower or zUpper <= zLower:
        raise ValueError(
            "upper bounds must be strictly greater than lower bounds"
        )
    shelf = Shelf(xLower=xLower, yLower=yLower, zLower=zLower,
                   xUpper=xUpper, yUpper=yUpper, zUpper=zUpper)
    piece.shelves.append(shelf)
    return shelf


def delete_shelf(home: Home, piece_ident: str, index: int) -> Shelf:
    piece = _resolve_shelf_unit(home, piece_ident)
    if index < 0 or index >= len(piece.shelves):
        raise IndexError(
            f"shelf index {index} out of range "
            f"(piece has {len(piece.shelves)} shelves)"
        )
    return piece.shelves.pop(index)


def clear_shelves(home: Home, piece_ident: str) -> int:
    piece = _resolve_shelf_unit(home, piece_ident)
    n = len(piece.shelves)
    piece.shelves = []
    return n
