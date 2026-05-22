"""Curated index of stock SH3D 7.x texture catalog entries.

Mirrors `docs/sh3d-reference/02-textures-catalog.md`. The full catalog lives
inside SH3D's `lib/Textures.jar`; here we keep an in-process copy so the CLI
can suggest valid texture ids for wall sides, room floors/ceilings, and the
environment sky/ground without parsing the SH3D installation.

Dimensions are the catalog's real-world tile size in cm; SH3D uses these to
tile the texture across the target surface. Categories are Floor / Wall /
Sky, matching SH3D's grouping. Reference doc: schema row §02-textures-catalog.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from cli_anything.sweethome3d.core.model import Texture


@dataclass
class TextureCatalogEntry:
    catalogId: str
    name: str
    category: str    # Floor | Wall | Sky
    width: float     # cm — tile width
    height: float    # cm — tile height
    creator: str = "eTeks"


_DEFAULT: list[TextureCatalogEntry] = [
    # Floor (11)
    TextureCatalogEntry("eTeks#beigeTile",          "Beige tiles",          "Floor", 20.0,   20.0),
    TextureCatalogEntry("eTeks#blackAndWhiteTiles", "Black and white tiles","Floor", 70.0,   70.0),
    TextureCatalogEntry("eTeks#darkBlueTile",       "Dark blue tiles",      "Floor", 33.5,   33.5),
    TextureCatalogEntry("eTeks#grass",              "Grass",                "Floor", 30.0,   30.0),
    TextureCatalogEntry("eTeks#greyTile",           "Grey tiles",           "Floor", 31.5,   31.5),
    TextureCatalogEntry("eTeks#lightBlueTile",      "Light blue tiles",     "Floor", 33.5,   33.5),
    TextureCatalogEntry("eTeks#oldWoodenFloor",     "Old wooden floor",     "Floor", 26.9,   26.9),
    TextureCatalogEntry("eTeks#pavingStone",        "Paving stone",         "Floor", 42.3,   30.0),
    TextureCatalogEntry("eTeks#pebbles",            "Pebbles",              "Floor", 20.0,   20.0),
    TextureCatalogEntry("eTeks#redTiles",           "Red tiles",            "Floor", 40.0,   40.0),
    TextureCatalogEntry("eTeks#stoneTiles",         "Stone tiles",          "Floor", 60.0,   40.0),
    TextureCatalogEntry("eTeks#woodenFloor",        "Wooden floor",         "Floor", 42.5,   42.5),
    # Wall (12)
    TextureCatalogEntry("eTeks#blueTiles",          "Blue tiles",           "Wall",  20.0,   20.0),
    TextureCatalogEntry("eTeks#boxTree",            "Box tree",             "Wall",  20.0,   20.0),
    TextureCatalogEntry("eTeks#marbleWall",         "Marble",               "Wall",  50.0,   50.0),
    TextureCatalogEntry("eTeks#roughcast",          "Roughcast",            "Wall",  20.0,   20.0),
    TextureCatalogEntry("eTeks#smallBricks",        "Small bricks",         "Wall",  23.0,   14.9),
    TextureCatalogEntry("eTeks#smallRedBricks",     "Small red bricks",     "Wall",  36.2,   14.9),
    TextureCatalogEntry("eTeks#smallWhiteBricks",   "Small white bricks",   "Wall",  35.3,   14.9),
    TextureCatalogEntry("eTeks#stone2Wall",         "Stone",                "Wall",  64.8,   40.0),
    TextureCatalogEntry("eTeks#stone3Wall",         "Stone",                "Wall",  55.3,   35.0),
    TextureCatalogEntry("eTeks#stoneWall",          "Stone",                "Wall",  76.0,   35.0),
    TextureCatalogEntry("eTeks#wallBeigeTile",      "Beige tiles",          "Wall",  20.0,   31.5),
    # Sky (3)
    TextureCatalogEntry("eTeks#blueSky",            "Blue sky",             "Sky",  100.0,   41.3),
    TextureCatalogEntry("eTeks#cloudy",             "Cloudy",               "Sky",  100.0,   27.6),
    TextureCatalogEntry("eTeks#veryCloudy",         "Very cloudy",          "Sky",  100.0,   44.8),
]


_CATEGORIES = ("Floor", "Wall", "Sky")


def list_textures(*, category: Optional[str] = None,
                  query: Optional[str] = None) -> list[TextureCatalogEntry]:
    """Return curated texture entries, optionally filtered.

    `category` is case-insensitive — Floor / Wall / Sky.
    `query` is a case-insensitive substring match on name and catalogId.
    """
    items = _DEFAULT
    if category is not None:
        cat = category.lower()
        items = [t for t in items if t.category.lower() == cat]
    if query is not None:
        q = query.lower()
        items = [t for t in items
                 if q in t.name.lower() or q in t.catalogId.lower()]
    return list(items)


def find_texture(catalogId: str) -> Optional[TextureCatalogEntry]:
    """Look up an entry by exact catalogId."""
    for t in _DEFAULT:
        if t.catalogId == catalogId:
            return t
    return None


def make_texture(catalogId: str, *, width: Optional[float] = None,
                  height: Optional[float] = None,
                  xOffset: float = 0, yOffset: float = 0,
                  angle: float = 0, scale: float = 1.0) -> Texture:
    """Build a `Texture` for the given catalogId, filling name/size from
    the stock catalog when not overridden.

    Raises KeyError when `catalogId` is unknown so callers fail loudly
    rather than emitting an invisible texture.
    """
    entry = find_texture(catalogId)
    if entry is None:
        raise KeyError(
            f"texture catalogId {catalogId!r} not found; "
            "browse with `textures list` to see valid ids"
        )
    return Texture(
        catalogId=entry.catalogId,
        name=entry.name,
        width=width if width is not None else entry.width,
        height=height if height is not None else entry.height,
        xOffset=xOffset, yOffset=yOffset,
        angle=angle, scale=scale,
        creator=entry.creator,
    )
