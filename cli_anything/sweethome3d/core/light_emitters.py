"""Per-light emitter tuning — point sources and glowing materials.

A SH3D light piece has two specialisations beyond the basic `power` knob:

- ``lightSources``: list of point emitters with their own position
  (0–1 fractions of the piece geometry), colour, and optional diameter
  (used by Java3D's photo renderer to approximate area lights).
- ``lightSourceMaterials``: list of material-group names within the
  light's 3D model that should glow when the light is on (typical for
  lamp-shade meshes).

Only `light` pieces accept these; validators below enforce the kind.
"""

from __future__ import annotations

from typing import Optional

from cli_anything.sweethome3d.core.model import (
    Home,
    LightSource,
    LightSourceMaterial,
    PieceOfFurniture,
)


def _resolve_light(home: Home, ident: str) -> PieceOfFurniture:
    piece = home.find_furniture(ident)
    if piece is None:
        raise KeyError(f"furniture not found: {ident}")
    if piece.kind != "light":
        raise ValueError(
            f"light sources apply to light pieces only; {piece.name!r} is "
            f"kind={piece.kind!r}"
        )
    return piece


def _validate_fraction(value: float, label: str) -> None:
    if not -1.0 <= value <= 1.0:
        raise ValueError(
            f"{label} must be a fraction in [-1, 1] (got {value})"
        )


def list_sources(home: Home, piece_ident: str) -> list[LightSource]:
    return list(_resolve_light(home, piece_ident).lightSources)


def add_source(home: Home, piece_ident: str, *,
                x: float, y: float, z: float,
                color: int,
                diameter: Optional[float] = None) -> LightSource:
    """Append a new point emitter to a light piece."""
    piece = _resolve_light(home, piece_ident)
    _validate_fraction(x, "x")
    _validate_fraction(y, "y")
    _validate_fraction(z, "z")
    if diameter is not None and diameter <= 0:
        raise ValueError("diameter must be positive when provided")
    src = LightSource(x=x, y=y, z=z, color=color, diameter=diameter)
    piece.lightSources.append(src)
    return src


def delete_source(home: Home, piece_ident: str, index: int) -> LightSource:
    piece = _resolve_light(home, piece_ident)
    if index < 0 or index >= len(piece.lightSources):
        raise IndexError(
            f"light source index {index} out of range "
            f"({piece.name!r} has {len(piece.lightSources)} sources)"
        )
    return piece.lightSources.pop(index)


def clear_sources(home: Home, piece_ident: str) -> int:
    piece = _resolve_light(home, piece_ident)
    n = len(piece.lightSources)
    piece.lightSources = []
    return n


def list_materials(home: Home, piece_ident: str) -> list[LightSourceMaterial]:
    return list(_resolve_light(home, piece_ident).lightSourceMaterials)


def add_material(home: Home, piece_ident: str,
                   name: str) -> LightSourceMaterial:
    """Mark a model material group as light-emitting."""
    piece = _resolve_light(home, piece_ident)
    if not name:
        raise ValueError("material name is required")
    if any(m.name == name for m in piece.lightSourceMaterials):
        raise ValueError(f"material already marked emissive: {name!r}")
    mat = LightSourceMaterial(name=name)
    piece.lightSourceMaterials.append(mat)
    return mat


def delete_material(home: Home, piece_ident: str, name: str) -> bool:
    piece = _resolve_light(home, piece_ident)
    for m in piece.lightSourceMaterials:
        if m.name == name:
            piece.lightSourceMaterials.remove(m)
            return True
    return False


def clear_materials(home: Home, piece_ident: str) -> int:
    piece = _resolve_light(home, piece_ident)
    n = len(piece.lightSourceMaterials)
    piece.lightSourceMaterials = []
    return n
