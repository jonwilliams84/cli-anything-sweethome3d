# SweetHome3D Furniture Catalog

This document lists all valid `catalog_id` values for use with
`Designer.place_furniture()`. Use `d.list_catalog_furniture(category=...)` at
runtime to retrieve these programmatically.

---

## sofa
| catalog_id | Description |
|---|---|
| `SOFA_2_SEATS` | 2-seat sofa |
| `SOFA_3_SEATS` | 3-seat sofa (standard) |
| `CORNER_SOFA` | L-shaped corner sofa |
| `SOFA_BED` | Sofa bed (converts to single) |

## chair
| catalog_id | Description |
|---|---|
| `DINING_CHAIR` | Standard dining chair |
| `OFFICE_CHAIR` | Swivel office chair |
| `ARMCHAIR` | Upholstered armchair |
| `STOOL` | Bar/kitchen stool |

## table
| catalog_id | Description |
|---|---|
| `DINING_TABLE_4` | 4-person dining table |
| `DINING_TABLE_6` | 6-person dining table |
| `COFFEE_TABLE` | Low living-room table |
| `DESK` | Writing / computer desk |
| `SIDE_TABLE` | Bedside/side table |
| `KITCHEN_TABLE` | Informal kitchen table |

## bed
| catalog_id | Description |
|---|---|
| `SINGLE_BED` | Single / twin bed (90×190 cm) |
| `DOUBLE_BED` | Double bed (140×190 cm) |
| `KING_BED` | King-size bed (180×200 cm) |
| `BUNK_BED` | Children's bunk bed |

## storage
| catalog_id | Description |
|---|---|
| `WARDROBE` | Full-height wardrobe |
| `BOOKCASE` | Freestanding bookcase |
| `SIDEBOARD` | Low sideboard / buffet |
| `CHEST_OF_DRAWERS` | Chest of drawers |
| `TV_UNIT` | Low TV stand / media unit |
| `SHOE_RACK` | Shoe rack (hallway) |

## kitchen
| catalog_id | Description |
|---|---|
| `KITCHEN_UNIT_BASE` | Base kitchen unit (60 cm wide) |
| `KITCHEN_UNIT_WALL` | Wall-hung kitchen unit |
| `KITCHEN_ISLAND` | Kitchen island / breakfast bar |
| `OVEN` | Built-in or freestanding oven |
| `REFRIGERATOR` | Fridge-freezer |
| `DISHWASHER` | Undercounter dishwasher |
| `WASHING_MACHINE` | Washing machine |
| `TUMBLE_DRYER` | Tumble dryer |
| `KITCHEN_SINK` | Kitchen sink unit |

## bathroom
| catalog_id | Description |
|---|---|
| `BATH` | Standard bath (170×70 cm) |
| `SHOWER_ENCLOSURE` | Shower enclosure |
| `TOILET` | Close-coupled WC |
| `BASIN` | Pedestal or wall-hung basin |
| `VANITY_UNIT` | Basin with vanity unit |
| `TOWEL_RAIL` | Heated towel rail |

## door
| catalog_id | Description |
|---|---|
| `DOOR_STANDARD` | Standard single door |
| `DOOR_BIFOLD` | Bi-fold door |
| `DOOR_FRENCH` | French double door |
| `DOOR_SLIDING` | Sliding door |
| `DOOR_POCKET` | Pocket / cavity-sliding door |

## window
| catalog_id | Description |
|---|---|
| `WINDOW_CASEMENT` | Casement window (side-hung) |
| `WINDOW_SASH` | Sash window |
| `WINDOW_TILT_AND_TURN` | Tilt-and-turn window |
| `WINDOW_BAY` | Bay window |
| `SKYLIGHT` | Roof skylight / Velux |

## stair
| catalog_id | Description |
|---|---|
| `STAIRCASE_STRAIGHT` | Straight staircase |
| `STAIRCASE_L` | L-shaped staircase |
| `STAIRCASE_U` | U-shaped staircase |

## misc
| catalog_id | Description |
|---|---|
| `FIREPLACE` | Open fireplace / hearth |
| `RADIATOR` | Panel radiator |
| `BOILER` | Combi / system boiler |
| `CONSUMER_UNIT` | Fuse / consumer unit |
| `TV` | Flatscreen TV |
| `DESK_LAMP` | Desk lamp |
| `FLOOR_LAMP` | Floor-standing lamp |

---

## Usage

```python
# List all IDs
ids = d.list_catalog_furniture()

# Filter by category
kitchen_items = d.list_catalog_furniture(category="kitchen")

# Place an item
d.place_furniture(ground,
    catalog_id="SOFA_3_SEATS",
    x=150, y=300,
    rotation_deg=0,
    label="Main Sofa")
```

## Notes for LLM agents

- Always call `d.list_catalog_furniture(category=...)` before placing items to
  confirm the `catalog_id` is valid — do not guess.
- Coordinates are in **centimetres** from the top-left corner of the floor plan.
- `rotation_deg` is **clockwise** in degrees (0 = facing south/down on the plan).
- Use `d.validate()` after placing all furniture to check for warnings.
