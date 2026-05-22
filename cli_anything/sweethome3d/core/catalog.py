"""Curated index of stock SH3D 7.x catalog entries.

Sweet Home 3D ships a bundled FurnitureCatalog with hundreds of pieces under
catalog ids like `eTeks#door`, `eTeks#fixedWindow85x123`. The full catalog
lives inside SH3D's JAR; here we keep a curated subset of the most useful
ids so the CLI can suggest valid `--catalog-id` values for `furniture add`,
`add-door`, and `add-window` without parsing the SH3D installation.

Dimensions are in cm. Selecting an entry as the catalog id is enough for SH3D
to render the piece with its 3D model in the photo view.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class CatalogEntry:
    catalogId: str
    name: str
    kind: str           # pieceOfFurniture | doorOrWindow | light
    category: str       # Doors, Windows, Lights, Bedroom, Kitchen, Bathroom, ...
    width: float
    depth: float
    height: float


# Curated subset of SH3D 7.x "Default" catalog. Every catalogId here must
# exist in the real SH3D Furniture.jar catalog — see
# `_sh3d_catalog_metadata.SH3D_CATALOG` for the canonical list. If an id
# below is renamed or removed in SH3D, pieces using it lose their model
# reference and render as invisible in the 3D view.
_DEFAULT: list[CatalogEntry] = [
    # Doors
    CatalogEntry("eTeks#door",                "Door",                "doorOrWindow", "Doors",   80,  6, 200),
    CatalogEntry("eTeks#doorFrame",           "Door frame",          "doorOrWindow", "Doors",   80,  6, 200),
    CatalogEntry("eTeks#openDoor",            "Open door",           "doorOrWindow", "Doors",   80,  6, 200),
    CatalogEntry("eTeks#roundedDoor",         "Rounded door",        "doorOrWindow", "Doors",   80,  6, 200),
    CatalogEntry("eTeks#frontDoor",           "Front door",          "doorOrWindow", "Doors",   95,  6, 215),
    CatalogEntry("eTeks#frenchWindow85x200",  "French window",       "doorOrWindow", "Doors",   85,  6, 200),
    CatalogEntry("eTeks#doubleFrenchWindow126x200", "Double French window", "doorOrWindow", "Doors", 126, 6, 200),
    CatalogEntry("eTeks#garageDoor",          "Garage door",         "doorOrWindow", "Doors",  240,  6, 200),
    CatalogEntry("eTeks#slidingDoors",        "Sliding doors",       "doorOrWindow", "Doors",  120,  6, 200),
    # Windows
    CatalogEntry("eTeks#fixedWindow85x123",   "Fixed window",        "doorOrWindow", "Windows", 85,  6, 123),
    CatalogEntry("eTeks#window85x123",        "Small window",        "doorOrWindow", "Windows", 85,  6, 123),
    CatalogEntry("eTeks#window85x163",        "Window",              "doorOrWindow", "Windows", 85,  6, 163),
    CatalogEntry("eTeks#doubleWindow126x123", "Double small window", "doorOrWindow", "Windows",126,  6, 123),
    CatalogEntry("eTeks#doubleWindow126x163", "Double window",       "doorOrWindow", "Windows",126,  6, 163),
    CatalogEntry("eTeks#doubleHungWindow80x122", "Double-hung window", "doorOrWindow", "Windows", 80, 6, 122),
    CatalogEntry("eTeks#sliderWindow126x200", "Slider window",       "doorOrWindow", "Windows",126,  6, 200),
    CatalogEntry("eTeks#halfRoundWindow",     "Half-round window",   "doorOrWindow", "Windows", 80,  6,  40),
    CatalogEntry("eTeks#roundWindow",         "Round window",        "doorOrWindow", "Windows", 60,  6,  60),
    # Lights
    CatalogEntry("eTeks#pendantLamp",         "Pendant lamp",        "light",        "Lights",  40, 40,  35),
    CatalogEntry("eTeks#wallUplight",         "Wall uplight",        "light",        "Lights",  25, 15,  30),
    CatalogEntry("eTeks#floorUplight",        "Floor uplight",       "light",        "Lights",  30, 30, 180),
    CatalogEntry("eTeks#workLamp",            "Work lamp",           "light",        "Lights",  30, 30,  50),
    CatalogEntry("eTeks#spotlight",           "Spotlight",           "light",        "Lights",  15, 15,  20),
    CatalogEntry("eTeks#lamp",                "Lamp",                "light",        "Lights",  30, 30,  60),
    # Bedroom
    CatalogEntry("eTeks#bed140x190",          "Bed 140x190",         "pieceOfFurniture", "Bedroom", 158, 208, 70),
    CatalogEntry("eTeks#bed90x190",           "Bed 90x190",          "pieceOfFurniture", "Bedroom", 108, 208, 70),
    CatalogEntry("eTeks#bed",                 "Bed",                 "pieceOfFurniture", "Bedroom", 160, 215, 90),
    CatalogEntry("eTeks#bunkBed90x190",       "Bunk bed",            "pieceOfFurniture", "Bedroom",  98, 200, 160),
    CatalogEntry("eTeks#wardrobe",            "Wardrobe",            "pieceOfFurniture", "Bedroom", 150,  60, 200),
    CatalogEntry("eTeks#bedsideTable",        "Bedside table",       "pieceOfFurniture", "Bedroom",  38,  38, 50),
    CatalogEntry("eTeks#chest",               "Chest",               "pieceOfFurniture", "Bedroom", 100,  55, 80),
    # Lounge / Living
    CatalogEntry("eTeks#sofa",                "Sofa",                "pieceOfFurniture", "Lounge",  220,  90, 80),
    CatalogEntry("eTeks#armchair",            "Armchair",            "pieceOfFurniture", "Lounge",   90,  90, 90),
    CatalogEntry("eTeks#coffeeTable",         "Coffee table",        "pieceOfFurniture", "Lounge",  100,  60, 45),
    CatalogEntry("eTeks#tvUnit",              "TV unit",             "pieceOfFurniture", "Lounge",  160,  40, 50),
    CatalogEntry("eTeks#flatTV",              "Flat TV",             "pieceOfFurniture", "Lounge",  100,  10, 60),
    CatalogEntry("eTeks#bookcase",            "Bookcase",            "pieceOfFurniture", "Lounge",  100,  40, 211),
    # Kitchen
    CatalogEntry("eTeks#kitchenCabinet",      "Kitchen cabinet",     "pieceOfFurniture", "Kitchen",  60,  60, 90),
    CatalogEntry("eTeks#kitchenUpperCabinet", "Kitchen upper cabinet","pieceOfFurniture","Kitchen",  60,  35, 70),
    CatalogEntry("eTeks#sink",                "Sink",                "pieceOfFurniture", "Kitchen",  60,  60, 90),
    CatalogEntry("eTeks#fridge",              "Fridge",              "pieceOfFurniture", "Kitchen",  60,  60, 180),
    CatalogEntry("eTeks#fridgeFreezer",       "Fridge & Freezer",    "pieceOfFurniture", "Kitchen",  60,  60, 180),
    CatalogEntry("eTeks#oven",                "Oven",                "pieceOfFurniture", "Kitchen",  60,  60, 90),
    CatalogEntry("eTeks#cooker",              "Cooker",              "pieceOfFurniture", "Kitchen",  60,  60, 90),
    CatalogEntry("eTeks#dishwasher",          "Dishwasher",          "pieceOfFurniture", "Kitchen",  60,  60, 90),
    CatalogEntry("eTeks#hood",                "Hood",                "pieceOfFurniture", "Kitchen",  60,  50, 35),
    CatalogEntry("eTeks#table",               "Dining table",        "pieceOfFurniture", "Kitchen", 160,  90, 75),
    CatalogEntry("eTeks#chair",               "Chair",               "pieceOfFurniture", "Kitchen",  45,  50, 90),
    # Bathroom
    CatalogEntry("eTeks#bath",                "Bath",                "pieceOfFurniture", "Bathroom",170, 70, 60),
    CatalogEntry("eTeks#fittedBath",          "Fitted bath",         "pieceOfFurniture", "Bathroom",170, 70, 60),
    CatalogEntry("eTeks#shower",              "Shower",              "pieceOfFurniture", "Bathroom", 80, 80,200),
    CatalogEntry("eTeks#washbasin",           "Washbasin",           "pieceOfFurniture", "Bathroom", 60, 40, 85),
    CatalogEntry("eTeks#washbasinWithCabinet","Washbasin with cabinet","pieceOfFurniture","Bathroom",60, 50, 85),
    CatalogEntry("eTeks#toiletUnit",          "Toilet unit",         "pieceOfFurniture", "Bathroom", 40, 60, 80),
    CatalogEntry("eTeks#clothesWasher",       "Clothes washer",      "pieceOfFurniture", "Bathroom", 60, 60, 85),
    # Stairs / Misc / Office
    CatalogEntry("eTeks#staircase",           "Staircase",           "pieceOfFurniture", "Stairs",  100,300,250),
    CatalogEntry("eTeks#spiralStaircase",     "Spiral staircase",    "pieceOfFurniture", "Stairs",  120,120,250),
    CatalogEntry("eTeks#curveStaircase",      "Curve staircase",     "pieceOfFurniture", "Stairs",  170,200,250),
    CatalogEntry("eTeks#desk",                "Desk",                "pieceOfFurniture", "Office",  120, 60, 75),
    CatalogEntry("eTeks#laptop",              "Laptop",              "pieceOfFurniture", "Office",   33, 24,  2),
    CatalogEntry("eTeks#filledBookcase",      "Filled bookcase",     "pieceOfFurniture", "Office",  100, 40,211),
    CatalogEntry("eTeks#electricRadiator",    "Electric radiator",   "pieceOfFurniture", "Misc",     60, 10, 60),
    CatalogEntry("eTeks#fireplace",           "Fireplace",           "pieceOfFurniture", "Misc",    140, 40,120),
    CatalogEntry("eTeks#curtains",            "Curtains",            "pieceOfFurniture", "Misc",    200, 10,250),
]


def list_catalog(*, kind: Optional[str] = None,
                  category: Optional[str] = None,
                  query: Optional[str] = None,
                  ) -> list[CatalogEntry]:
    """Return curated catalog entries, optionally filtered.

    `kind` matches doorOrWindow / pieceOfFurniture / light exactly.
    `category` is case-insensitive (e.g. "Doors", "kitchen").
    `query` is a case-insensitive substring match on name and catalogId.
    """
    items = _DEFAULT
    if kind is not None:
        items = [e for e in items if e.kind == kind]
    if category is not None:
        cat = category.lower()
        items = [e for e in items if e.category.lower() == cat]
    if query is not None:
        q = query.lower()
        items = [e for e in items
                  if q in e.name.lower() or q in e.catalogId.lower()]
    return list(items)


def find_catalog(catalogId: str) -> Optional[CatalogEntry]:
    """Look up an entry by exact catalogId."""
    for e in _DEFAULT:
        if e.catalogId == catalogId:
            return e
    return None
