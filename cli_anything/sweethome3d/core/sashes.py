"""Door / window sashes — swing geometry for openings.

A `Sash` is the pivoting leaf of a door or window. In SH3D the sash is
rendered as an arc in 2D and an animated opening in 3D. Coordinates are
fractions of the parent piece's dimensions (0–1 along the local axes), and
angles are in radians.

Only `doorOrWindow` pieces accept sashes; the validators below enforce
that so callers can't quietly attach a sash to a sofa.
"""

from __future__ import annotations

import math
from typing import Optional

from cli_anything.sweethome3d.core.model import Home, PieceOfFurniture, Sash


def _resolve_door(home: Home, ident: str) -> PieceOfFurniture:
    piece = home.find_furniture(ident)
    if piece is None:
        raise KeyError(f"furniture not found: {ident}")
    if piece.kind != "doorOrWindow":
        raise ValueError(
            f"sashes apply to doorOrWindow pieces only; {piece.name!r} is "
            f"kind={piece.kind!r}"
        )
    return piece


def _validate_fraction(value: float, label: str) -> None:
    if not -1.0 <= value <= 1.0:
        raise ValueError(
            f"{label} must be a fraction in [-1, 1] (got {value}); "
            "SH3D measures sash coordinates as fractions of the piece's size"
        )


def list_sashes(home: Home, piece_ident: str) -> list[Sash]:
    return list(_resolve_door(home, piece_ident).sashes)


def add_sash(home: Home, piece_ident: str, *,
              xAxis: float, yAxis: float,
              width: float,
              startAngle: float, endAngle: float) -> Sash:
    """Append a new sash to a door/window. Returns the created Sash."""
    piece = _resolve_door(home, piece_ident)
    _validate_fraction(xAxis, "xAxis")
    _validate_fraction(yAxis, "yAxis")
    if not 0 < width <= 1.0:
        raise ValueError("width must be a positive fraction in (0, 1]")
    if not -2 * math.pi <= startAngle <= 2 * math.pi:
        raise ValueError("startAngle must be in [-2π, 2π]")
    if not -2 * math.pi <= endAngle <= 2 * math.pi:
        raise ValueError("endAngle must be in [-2π, 2π]")
    sash = Sash(xAxis=xAxis, yAxis=yAxis, width=width,
                startAngle=startAngle, endAngle=endAngle)
    piece.sashes.append(sash)
    return sash


def delete_sash(home: Home, piece_ident: str, index: int) -> Sash:
    """Remove the sash at the given index (0-based). Returns the removed
    sash so callers can echo it."""
    piece = _resolve_door(home, piece_ident)
    if index < 0 or index >= len(piece.sashes):
        raise IndexError(
            f"sash index {index} out of range (piece has {len(piece.sashes)} sashes)"
        )
    return piece.sashes.pop(index)


def clear_sashes(home: Home, piece_ident: str) -> int:
    """Drop every sash on a door/window; returns the count removed."""
    piece = _resolve_door(home, piece_ident)
    n = len(piece.sashes)
    piece.sashes = []
    return n
