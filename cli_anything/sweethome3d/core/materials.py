"""Per-piece material overrides — fabric, paint, surface colours.

SH3D's "Modify furniture > Materials" tab lets users override individual
material groups embedded in a 3D model (e.g. swap the cushion fabric on a
sofa without changing its frame). The `<material>` child of a furniture
element captures one such override: a material `name` plus optional
`color`, `shininess`, and `texture`.

This module exposes that surface as a small CRUD API operating on
``piece.materials`` lists. The XML reader/writer already round-trips the
data layer; we just expose it through the CLI.
"""

from __future__ import annotations

from typing import Optional

from cli_anything.sweethome3d.core.model import (
    Home,
    Material,
    PieceOfFurniture,
    Texture,
)
from cli_anything.sweethome3d.core.textures import make_texture


def _resolve_piece(home: Home, ident: str) -> PieceOfFurniture:
    piece = home.find_furniture(ident)
    if piece is None:
        raise KeyError(f"furniture not found: {ident}")
    return piece


def list_materials(home: Home, piece_ident: str) -> list[Material]:
    """List material overrides on a piece (empty list when none)."""
    return list(_resolve_piece(home, piece_ident).materials)


def find_material(piece: PieceOfFurniture, name: str) -> Optional[Material]:
    for m in piece.materials:
        if m.name == name:
            return m
    return None


def set_material(home: Home, piece_ident: str, name: str, *,
                   color: Optional[int] = None,
                   shininess: Optional[float] = None,
                   texture_id: Optional[str] = None,
                   texture: Optional[Texture] = None,
                   key: Optional[str] = None,
                   clear_color: bool = False,
                   clear_shininess: bool = False,
                   clear_texture: bool = False) -> Material:
    """Set or replace a material override by name.

    Creates the entry if it doesn't exist. ``clear_*`` flags wipe an
    existing value (so callers can revert a single attribute back to the
    model default without dropping the whole override).
    """
    piece = _resolve_piece(home, piece_ident)
    mat = find_material(piece, name)
    if mat is None:
        mat = Material(name=name)
        piece.materials.append(mat)
    if key is not None:
        mat.key = key
    if color is not None:
        mat.color = color
    elif clear_color:
        mat.color = None
    if shininess is not None:
        mat.shininess = shininess
    elif clear_shininess:
        mat.shininess = None
    if texture is not None:
        mat.texture = texture
    elif texture_id is not None:
        mat.texture = make_texture(texture_id)
    elif clear_texture:
        mat.texture = None
    return mat


def clear_material(home: Home, piece_ident: str, name: str) -> bool:
    """Remove a single material override by name. Returns True if removed."""
    piece = _resolve_piece(home, piece_ident)
    mat = find_material(piece, name)
    if mat is None:
        return False
    piece.materials.remove(mat)
    return True


def clear_all_materials(home: Home, piece_ident: str) -> int:
    """Drop every material override on a piece; returns the count removed."""
    piece = _resolve_piece(home, piece_ident)
    n = len(piece.materials)
    piece.materials = []
    return n
