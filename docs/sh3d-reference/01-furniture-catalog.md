# Sweet Home 3D 7.5 — Default Furniture Catalog Reference

Complete reference for all entities in the default SH3D 7.5 furniture catalog. Extracted from
`SweetHome3D-7.5/lib/Furniture.jar` →
`com/eteks/sweethome3d/io/DefaultFurnitureCatalog.properties`.

---

## How to use this reference

Entities in the catalog are referenced by their `catalogId` (e.g. `eTeks#frontDoor`) when placing
furniture programmatically in the SVG → SH3D pipeline:

- **`cli_anything/sweethome3d/core/svg/openings.py`** — maps SVG opening shapes to door/window
  `catalogId` values; uses `doorOrWindowCutOutShape`, sash geometry, and wall-thickness parameters
  documented in the [Doors and Windows special section](#special-section-doors-and-windows).
- **`cli_anything/sweethome3d/core/svg/pipeline.py`** — orchestrates the full import pipeline;
  resolves furniture by `catalogId` to look up dimensions and placement rules.
- **`cli_anything/sweethome3d/core/catalog.py`** — loads and queries the catalog; the primary
  interface for resolving a `catalogId` to its property set.
- **`cli_anything/sweethome3d/core/_sh3d_catalog_metadata.py`** — pre-parsed catalog metadata
  cache used by the pipeline.

To place a catalog item in a `.sh3d` file, use the `catalogId` in the furniture XML element and
set `width`, `depth`, `height` to override the defaults shown here.

---

## Catalog Metadata

| Property    | Value                                          |
|-------------|------------------------------------------------|
| id          | `SweetHome3D#DefaultModels`                    |
| name        | Default Models catalog                         |
| description | Models created by Emmanuel Puybaret / eTeks    |
| version     | 7.5                                            |
| license     | GNU GPL / CC-BY © Space Mushrooms              |
| provider    | www.sweethome3d.com                            |

**Total entities: 100**

### Entity counts by category

| Category          | Count |
|-------------------|-------|
| Bathroom          | 6     |
| Bedroom           | 11    |
| Doors and windows | 21    |
| Kitchen           | 10    |
| Lights            | 14    |
| Living room       | 25    |
| Miscellaneous     | 10    |
| Staircases        | 3     |
| **Total**         | **100** |

---

## Entities by Category

All dimensions are in **centimetres**. The `W×D×H` column shows default dimensions; the pipeline
may override them from the SVG geometry. `elevation` is the height above floor level at which the
bottom of the model sits by default.

Columns:
- **catalogId** — the string used in `catalogId="..."` in SH3D XML
- **name** — English display name
- **W×D×H cm** — default width × depth × height
- **elev cm** — default elevation above floor
- **movable** — whether the user can freely move it in the plan
- **doorOrWindow** — creates a wall opening when placed against a wall
- **staircase** — has a `staircaseCutOutShape` (cuts hole in floor above)
- **creator** — original model author

---

### Bathroom (6 entities)

| catalogId | name | W×D×H cm | elev cm | movable | doorOrWindow | staircase | creator |
|-----------|------|-----------|---------|---------|--------------|-----------|---------|
| `eTeks#bath` | Bath | 163×73×57 | 0 | false | false | — | eTeks |
| `eTeks#fittedBath` | Fitted bath | 178×77×72 | 0 | false | false | — | eTeks |
| `eTeks#shower` | Shower | 79×79×211 | 0 | false | false | — | eTeks |
| `eTeks#toiletUnit` | Toilet unit | 40×80×62 | 0 | false | false | — | eTeks |
| `eTeks#washbasin` | Washbasin | 56×47×97 | 0 | false | false | — | eTeks |
| `eTeks#washbasinWithCabinet` | Washbasin with cabinet | 62×57×97 | 0 | false | false | — | eTeks |

Notable properties:
- `eTeks#fittedBath`: `dropOnTopElevation=62.5`
- `eTeks#shower`: `dropOnTopElevation=25`
- `eTeks#toiletUnit`: `dropOnTopElevation=61`
- `eTeks#washbasin`: `dropOnTopElevation=77.6`
- `eTeks#washbasinWithCabinet`: `dropOnTopElevation=75.3`

---

### Bedroom (11 entities)

| catalogId | name | W×D×H cm | elev cm | movable | doorOrWindow | staircase | creator |
|-----------|------|-----------|---------|---------|--------------|-----------|---------|
| `eTeks#bed` | Bed | 144.6×193.1×52.8 | 0 | true | false | — | eTeks |
| `eTeks#bed140x190` | Bed 140x190 | 158×208×70 | 0 | true | false | — | eTeks |
| `eTeks#bed90x190` | Bed 90x190 | 108×208×70 | 0 | true | false | — | eTeks |
| `eTeks#bedsideTable` | Bedside table | 38×38×50 | 0 | true | false | — | eTeks |
| `eTeks#bunkBed90x190` | Bunk bed | 115×208×180 | 0 | true | false | — | eTeks |
| `eTeks#chest` | Chest | 100×55×80 | 0 | true | false | — | eTeks |
| `eTeks#cornerBunkBed90x190` | Corner bunk bed | 208×208×155 | 0 | true | false | — | eTeks |
| `eTeks#crib` | Crib | 67×125×85 | 0 | true | false | — | eTeks |
| `eTeks#loftBed140x190` | Loft bed 140x190 | 165×208×180 | 0 | true | false | — | eTeks |
| `eTeks#slidingDoors` | Sliding doors | 154×8×250 | 0 | false | false | — | eTeks |
| `eTeks#wardrobe` | Wardrobe | 100×54×165 | 0 | true | false | — | eTeks |

Notable properties:
- `eTeks#bed`: `dropOnTopElevation=44.3`
- `eTeks#bed140x190`: `dropOnTopElevation=48`
- `eTeks#bed90x190`: `dropOnTopElevation=48`
- `eTeks#bedsideTable`: `shelfElevations=11.2 38 50`
- `eTeks#bunkBed90x190`: `dropOnTopElevation=154`, `shelfElevations=50.1 154`
- `eTeks#cornerBunkBed90x190`: `dropOnTopElevation=128.1`, `shelfElevations=50.1 128.1`
- `eTeks#crib`: `dropOnTopElevation=27.2`
- `eTeks#loftBed140x190`: `dropOnTopElevation=161`
- `eTeks#slidingDoors`: tags include `Adjustable` (width-resizable wardrobe doors)

---

### Doors and Windows (21 entities)

| catalogId | name | W×D×H cm | elev cm | movable | doorOrWindow | staircase | creator |
|-----------|------|-----------|---------|---------|--------------|-----------|---------|
| `eTeks#door` | Door | 91.5×14.5×208.5 | 0 | false | true | — | eTeks |
| `eTeks#doorFrame` | Door frame | 91.5×9.5×208.5 | 0 | false | true | — | eTeks |
| `eTeks#doubleFrenchWindow126x200` | Double French window | 132×34×210 | 11 | false | true | — | eTeks |
| `eTeks#doubleHungWindow80x122` | Double-hung window | 81×27×128 | 93 | false | true | — | eTeks |
| `eTeks#doubleOutwardOpeningWindow` | Outward opening window | 115.2×26×134 | 87 | false | true | — | eTeks |
| `eTeks#doubleWindow126x123` | Double small window | 132×34×134 | 87 | false | true | — | eTeks |
| `eTeks#doubleWindow126x163` | Double window | 132×34×174 | 47 | false | true | — | eTeks |
| `eTeks#fixedTriangleWindow85x85` | Fixed triangle window | 91×27×91 | 130 | false | true | — | eTeks |
| `eTeks#fixedWindow85x123` | Fixed window | 91×27×134 | 87 | false | true | — | eTeks |
| `eTeks#frenchWindow85x200` | French window | 91×34×210 | 11 | false | true | — | eTeks |
| `eTeks#frontDoor` | Front door | 101.5×23×208.5 | 0 | false | true | — | eTeks |
| `eTeks#garageDoor` | Garage door | 250×25×205 | 0 | false | true | — | eTeks |
| `eTeks#halfRoundWindow` | Half round window | 91×25×46 | 210 | false | true | — | eTeks |
| `eTeks#openDoor` | Open door | 91.5×68×208.5 | 0 | false | true | — | eTeks |
| `eTeks#roundDoorFrame` | Round door frame | 80×15×200 | 0 | false | true | — | eTeks |
| `eTeks#roundWindow` | Round window | 91×25×91 | 130 | false | true | — | eTeks |
| `eTeks#roundedDoor` | Rounded door | 91.5×14.5×208.5 | 0 | false | true | — | eTeks |
| `eTeks#serviceHatch` | Service hatch | 50×8.3×50 | 120 | false | true | — | eTeks |
| `eTeks#sliderWindow126x200` | Slider window | 132×31.5×210 | 11 | false | true | — | eTeks |
| `eTeks#window85x123` | Small window | 91×34×134 | 87 | false | true | — | eTeks |
| `eTeks#window85x163` | Window | 91×34×174 | 47 | false | true | — | eTeks |

Full door/window parameters are documented in the [special section below](#special-section-doors-and-windows).

---

### Kitchen (10 entities)

| catalogId | name | W×D×H cm | elev cm | movable | doorOrWindow | staircase | creator |
|-----------|------|-----------|---------|---------|--------------|-----------|---------|
| `eTeks#clothesWasher` | Clothes washer | 60×63×85 | 0 | true | false | — | eTeks |
| `eTeks#cooker` | Cooker | 60×62×85 | 0 | true | false | — | eTeks |
| `eTeks#dishwasher` | Dishwasher | 60×65×85 | 0 | true | false | — | eTeks |
| `eTeks#fridge` | Fridge | 60×66×85 | 0 | true | false | — | eTeks |
| `eTeks#fridgeFreezer` | Fridge & Freezer | 60×66×185 | 0 | true | false | — | eTeks |
| `eTeks#hood` | Hood | 60×52.6×94 | 156 | true | false | — | eTeks |
| `eTeks#kitchenCabinet` | Kitchen cabinet | 60×64×85 | 0 | false | false | — | eTeks |
| `eTeks#kitchenUpperCabinet` | Kitchen upper cabinet | 60×40.1×86.2 | 145 | true | false | — | eTeks |
| `eTeks#oven` | Oven | 51.5×47.75×29.5 | 0 | true | false | — | eTeks |
| `eTeks#sink` | Sink | 120×64×105.72 | 0 | false | false | — | eTeks |

Notable properties:
- `eTeks#hood`: `dropOnTopElevation=-1` (mounts below ceiling)
- `eTeks#sink`: `dropOnTopElevation=87.8`

---

### Lights (14 entities)

| catalogId | name | W×D×H cm | elev cm | movable | doorOrWindow | staircase | creator |
|-----------|------|-----------|---------|---------|--------------|-----------|---------|
| `eTeks#blueLightSource` | Blue light source | 10×10×10 | 220 | true | false | — | eTeks |
| `eTeks#fireglowLightSource` | Fireglow light source | 10×10×10 | 220 | true | false | — | eTeks |
| `eTeks#floorUplight` | Floor uplight | 33×33×181 | 0 | true | false | — | eTeks |
| `eTeks#greenLightSource` | Green light source | 10×10×10 | 220 | true | false | — | eTeks |
| `eTeks#halogenLightSource` | Halogen light source | 10×10×10 | 220 | true | false | — | eTeks |
| `eTeks#incandescentLightSource` | Incandescent light source | 10×10×10 | 220 | true | false | — | eTeks |
| `eTeks#lamp` | Lamp | 44×44×49.9 | 0 | true | false | — | eTeks |
| `eTeks#lightSource` | White light source | 10×10×10 | 220 | true | false | — | eTeks |
| `eTeks#magentaLightSource` | Magenta light source | 10×10×10 | 220 | true | false | — | eTeks |
| `eTeks#pendantLamp` | Pendant lamp | 60×60×80 | 170 | true | false | — | eTeks |
| `eTeks#redLightSource` | Red light source | 10×10×10 | 220 | true | false | — | eTeks |
| `eTeks#spotlight` | Spotlight | 6.84×9.87×13.1 | 150 | true | false | — | eTeks |
| `eTeks#wallUplight` | Wall uplight | 24×12×26 | 165 | true | false | — | eTeks |
| `eTeks#workLamp` | Work lamp | 12×29.5×49.3 | 0 | true | false | — | eTeks |

Full light-source parameters are documented in the [special section below](#special-section-lights).

---

### Living Room (25 entities)

| catalogId | name | W×D×H cm | elev cm | movable | doorOrWindow | staircase | creator |
|-----------|------|-----------|---------|---------|--------------|-----------|---------|
| `eTeks#aquarium` | Aquarium | 60×30×35 | 0 | true | false | — | eTeks |
| `eTeks#armchair` | Armchair | 87×92×87 | 0 | true | false | — | eTeks |
| `eTeks#armchair2` | Armchair | 80×78.1×77.2 | 0 | true | false | — | eTeks |
| `eTeks#bookcase` | Bookcase | 100×40×211 | 0 | true | false | — | eTeks |
| `eTeks#chair` | Chair | 40×42×90 | 0 | true | false | — | eTeks |
| `eTeks#chair2` | Chair | 48.6×49.9×80 | 0 | true | false | — | eTeks |
| `eTeks#coffeeTable` | Coffee table | 125×46×40 | 0 | true | false | — | eTeks |
| `eTeks#cornerSofa` | Corner sofa | 233×168×87 | 0 | true | false | — | eTeks |
| `eTeks#desk` | Desk | 140×67.8×77 | 0 | true | false | — | eTeks |
| `eTeks#dresser` | Dresser | 170×50×64.7 | 0 | true | false | — | eTeks |
| `eTeks#filledBookcase` | Filled bookcase | 85×35×180 | 0 | true | false | — | eTeks |
| `eTeks#fireplace` | Fireplace | 145×85×250 | 0 | false | false | — | eTeks |
| `eTeks#flatTV` | Flat TV | 121×30×79.3 | 0 | true | false | — | eTeks |
| `eTeks#flowers` | Flowers | 24.2×22.1×49.3 | 0 | true | false | — | eTeks |
| `eTeks#glassDoorCabinet` | Glass door cabinet | 70×38.7×198.2 | 0 | true | false | — | eTeks |
| `eTeks#laptop` | Laptop | 32.5×35.5×19.2 | 0 | true | false | — | eTeks |
| `eTeks#piano` | Piano | 140×43×82 | 0 | true | false | — | eTeks |
| `eTeks#plant` | Plant | 58×50×82 | 0 | true | false | — | eTeks |
| `eTeks#roundTable` | Round table | 126×126×74 | 0 | true | false | — | eTeks |
| `eTeks#sofa` | Sofa | 147×87×87 | 0 | true | false | — | eTeks |
| `eTeks#sofa2` | Sofa | 200×86.5×88 | 0 | true | false | — | eTeks |
| `eTeks#squareTable` | Square table | 115×115×74 | 0 | true | false | — | eTeks |
| `eTeks#stool` | Stool | 40×40×46 | 0 | true | false | — | eTeks |
| `eTeks#table` | Table | 150×75×74 | 0 | true | false | — | eTeks |
| `eTeks#tvUnit` | TV unit | 100×52×93 | 0 | true | false | — | eTeks |

Notable properties:
- `eTeks#armchair`: `dropOnTopElevation=32.5`
- `eTeks#armchair2`: `dropOnTopElevation=42.5`
- `eTeks#bookcase`: `dropOnTopElevation=97.2`, `shelfElevations=12.8 41 69 97.2 125.4 153.6 181.7 210`
- `eTeks#chair`: `dropOnTopElevation=46.2`
- `eTeks#chair2`: `dropOnTopElevation=44.5`
- `eTeks#cornerSofa`: `dropOnTopElevation=32.6`
- `eTeks#dresser`: `shelfElevations=8.2 36.1 64.7`
- `eTeks#filledBookcase`: `dropOnTopElevation=34.8`; `shelfBoxes` defines 9 shelf collision volumes
- `eTeks#fireplace`: `dropOnTopElevation=35.2`
- `eTeks#glassDoorCabinet`: `dropOnTopElevation=124.2`, `shelfElevations=15.8 36.3 58.8 80.8 95.6 124.3 146.8 169.3 197.5`
- `eTeks#laptop`: `dropOnTopElevation=0.7`
- `eTeks#sofa`: `dropOnTopElevation=32.4`
- `eTeks#sofa2`: `dropOnTopElevation=45`
- `eTeks#tvUnit`: `dropOnTopElevation=41.6`

---

### Miscellaneous (10 entities)

| catalogId | name | W×D×H cm | elev cm | movable | doorOrWindow | staircase | creator |
|-----------|------|-----------|---------|---------|--------------|-----------|---------|
| `eTeks#blind` | Venetian blind | 80×3.9×168.3 | 58.7 | true | false | — | eTeks |
| `eTeks#curtains` | Curtains | 150×22.9×225 | 8.5 | true | false | — | eTeks |
| `eTeks#electricRadiator` | Electric radiator | 37×10×45 | 20 | false | false | — | eTeks |
| `eTeks#frame` | Frame | 50×2.2×35 | 150 | true | false | — | eTeks |
| `eTeks#hotWaterRadiator` | Hot water radiator | 65×25×61 | 20 | false | false | — | eTeks |
| `eTeks#mannequin` | Mannequin | 44×52.7×175 | 0 | true | false | — | eTeks |
| `eTeks#railing` | Railing | 94.4×5×90 | 10 | false | false | — | eTeks |
| `eTeks#texturableBox` | Box | 100×100×100 | 0 | true | false | — | eTeks |
| `eTeks#texturableCylinder0` | Cylinder | 100×100×100 | 0 | true | false | — | eTeks |
| `eTeks#texturableTriangle` | Triangle | 100×100×100 | 0 | true | false | — | eTeks |

Notable properties:
- `eTeks#blind`: `dropOnTopElevation=-1` (ceiling-mounted)
- `eTeks#curtains`: `multiPartModel=true`, `dropOnTopElevation=-1`
- `eTeks#frame`: `multiPartModel=true`, `dropOnTopElevation=-1`
- `eTeks#mannequin`: `multiPartModel=true`; 13 poseable presets (see [Modelable Materials section](#special-section-modelable-materials))
- `eTeks#texturableBox`: `multiPartModel=true` — 6 individually texturable faces
- `eTeks#texturableCylinder0`: `multiPartModel=true` — texturable top, bottom, side
- `eTeks#texturableTriangle`: `multiPartModel=true` — texturable faces

---

### Staircases (3 entities)

| catalogId | name | W×D×H cm | elev cm | movable | doorOrWindow | staircase | creator |
|-----------|------|-----------|---------|---------|--------------|-----------|---------|
| `eTeks#curveStaircase` | Curve staircase | 72×238×362.4 | 0 | false | false | yes | eTeks |
| `eTeks#spiralStaircase` | Spiral staircase | 140×140×362 | 0 | false | false | yes | eTeks |
| `eTeks#staircase` | Staircase | 72×222×362.4 | 0 | false | false | yes | eTeks |

All staircase entities have `dropOnTopElevation=-1`.

Staircase cut-out shapes (SVG paths in normalized [0,1] coordinates):

**`eTeks#curveStaircase`** and **`eTeks#staircase`** — rectangular cut:
```
M0,0 v1 h1 v-1 z
```

**`eTeks#spiralStaircase`** — circular wedge cut:
```
M0.71077,0.94769 L0.5,0.5 h0.5 A0.5,0.5 0 1,0 0.71077,0.9476
```

---

## Special Section: Doors and Windows

Every entity with `doorOrWindow=true` creates a wall opening. The parameters below control exactly
how the opening is cut and how the sash(es) animate.

### Parameter glossary

| Parameter | Meaning |
|-----------|---------|
| `doorOrWindowWallThickness` | Fraction (%) of the opening depth that represents wall thickness — i.e. how deep the hole cut goes into the wall. Default: 100% (full depth). |
| `doorOrWindowWallDistance` | Gap (cm) between the exterior wall face and the front of the door/window frame. Default: 0. |
| `doorOrWindowWallCutOutOnBothSides` | If `false`, the wall cut-out is only on the side where the opening faces. If `true` (default), it is visible from both sides. |
| `doorOrWindowCutOutShape` | SVG path in normalized [0,1]×[0,1] space describing the shape of the hole cut in the wall. (0,0) = bottom-left, (1,1) = top-right of the opening bounding box. |
| `doorOrWindowWidthDepthDeformable` | If `false`, the depth cannot be resized independently of width. Default: `true`. |
| `doorOrWindowSashXAxis` | X pivot point of each sash (space-separated if multiple sashes), in cm from the left edge of the opening. |
| `doorOrWindowSashYAxis` | Y pivot point of each sash (depth direction, cm from the front of the opening). |
| `doorOrWindowSashWidth` | Arc radius of the sash swing (cm) — effectively the sash panel width. |
| `doorOrWindowSashStartAngle` | Open start angle of the sash arc (degrees, 0=toward interior). |
| `doorOrWindowSashEndAngle` | Open end angle of the sash arc (degrees, negative=counter-clockwise). |

### Full door/window property table

| catalogId | name | wallThickness | wallDistance | cutOnBothSides | widthDepthDeformable | sash count |
|-----------|------|---------------|--------------|----------------|----------------------|------------|
| `eTeks#door` | Door | 7.5% | 1 cm | true (default) | true (default) | 1 |
| `eTeks#doorFrame` | Door frame | 7.5% | 1 cm | true (default) | true (default) | 0 |
| `eTeks#doubleFrenchWindow126x200` | Double French window | 25% | 0 (default) | true (default) | true (default) | 2 |
| `eTeks#doubleHungWindow80x122` | Double-hung window | 25% | 0 (default) | true (default) | true (default) | 0 |
| `eTeks#doubleOutwardOpeningWindow` | Outward opening window | 25% | 0 (default) | true (default) | true (default) | 2 |
| `eTeks#doubleWindow126x123` | Double small window | 25% | 0 (default) | true (default) | true (default) | 2 |
| `eTeks#doubleWindow126x163` | Double window | 25% | 0 (default) | true (default) | true (default) | 2 |
| `eTeks#fixedTriangleWindow85x85` | Fixed triangle window | 100% (default) | 0 (default) | true (default) | true (default) | 0 |
| `eTeks#fixedWindow85x123` | Fixed window | 100% (default) | 0 cm | true (default) | true (default) | 0 |
| `eTeks#frenchWindow85x200` | French window | 25% | 0 (default) | true (default) | true (default) | 1 |
| `eTeks#frontDoor` | Front door | 18% | 0 (default) | true (default) | true (default) | 1 |
| `eTeks#garageDoor` | Garage door | 100% (default) | 0 (default) | true (default) | true (default) | 0 |
| `eTeks#halfRoundWindow` | Half round window | 100% (default) | 0 (default) | true (default) | true (default) | 0 |
| `eTeks#openDoor` | Open door | 7.5% | 1 cm | true (default) | **false** | 1 |
| `eTeks#roundDoorFrame` | Round door frame | 100% (default) | 0 (default) | true (default) | true (default) | 0 |
| `eTeks#roundWindow` | Round window | 100% (default) | 0 (default) | true (default) | true (default) | 0 |
| `eTeks#roundedDoor` | Rounded door | 7.5% | 1 cm | true (default) | true (default) | 1 |
| `eTeks#serviceHatch` | Service hatch | 100% (default) | 0 cm | **false** | true (default) | 0 |
| `eTeks#sliderWindow126x200` | Slider window | 25% | 0 (default) | true (default) | true (default) | 0 |
| `eTeks#window85x123` | Small window | 25% | 0 (default) | true (default) | true (default) | 1 |
| `eTeks#window85x163` | Window | 25% | 0 (default) | true (default) | true (default) | 1 |

### Cut-out shapes (SVG paths)

All paths use normalized [0,1]×[0,1] coordinates. `(0,0)` = bottom-left of opening, `(1,1)` = top-right.

**Standard rectangle** (used by all doors, most windows, garage door):
```svg
M0,0 v1 h1 v-1 z
```
Entities: `eTeks#door`, `eTeks#doorFrame`, `eTeks#doubleFrenchWindow126x200`,
`eTeks#doubleHungWindow80x122`, `eTeks#doubleOutwardOpeningWindow`, `eTeks#doubleWindow126x123`,
`eTeks#doubleWindow126x163`, `eTeks#fixedWindow85x123`, `eTeks#frenchWindow85x200`,
`eTeks#frontDoor`, `eTeks#garageDoor`, `eTeks#openDoor`, `eTeks#serviceHatch`,
`eTeks#sliderWindow126x200`, `eTeks#window85x123`, `eTeks#window85x163`

**Fixed triangle window** — right-triangle cut:
```svg
M0,0 v1 h1 z
```
Entity: `eTeks#fixedTriangleWindow85x85`

**Round door frame** — rectangular lower section + elliptical arch top:
```svg
M0,1 v-0.8 a0.5,0.2 0 1,1 1,0 v0.8 z
```
Entity: `eTeks#roundDoorFrame`

**Rounded door** — slightly shorter rectangular lower section + shallow elliptical arch:
```svg
M0,1 v-0.788 a0.5,0.2 0 1,1 1,0 v0.788 z
```
Entity: `eTeks#roundedDoor`

**Half-round window** — semicircular arch to base:
```svg
M0,1 a0.5,0.997 0 1,1 1,0 z
```
Entity: `eTeks#halfRoundWindow`

**Round window** — full circle:
```svg
M0,0.5 a0.5,0.5 0 1,0 1,0 a0.5,0.5 0 1,0 -1,0 z
```
Entity: `eTeks#roundWindow`

### Sash geometry

For entities with sashes, the values define how the door/window panel swings open in plan view.
Multiple sashes are space-separated within each property. All distances are in **cm**.

**`eTeks#door`** — 1 sash, opens inward (CCW):
- xAxis=5, yAxis=8.5, width=81.5, startAngle=0°, endAngle=-90°

**`eTeks#openDoor`** — 1 sash, opens inward (CCW), fixed at 90° open:
- xAxis=5, yAxis=8.5, width=81.5, startAngle=0°, endAngle=-90°

**`eTeks#doorFrame`** — 0 sashes (frame only, no swing shown)

**`eTeks#roundedDoor`** — 1 sash, opens inward (CCW):
- xAxis=5, yAxis=8.5, width=81.5, startAngle=0°, endAngle=-90°

**`eTeks#frontDoor`** — 1 sash, opens inward (CCW):
- xAxis=5, yAxis=18, width=91.5, startAngle=0°, endAngle=-90°

**`eTeks#window85x123`** — 1 sash, opens CCW (casement style):
- xAxis=2, yAxis=25, width=86, startAngle=0°, endAngle=-90°

**`eTeks#window85x163`** — 1 sash, opens CCW:
- xAxis=2, yAxis=25, width=86, startAngle=0°, endAngle=-90°

**`eTeks#frenchWindow85x200`** — 1 sash, opens CCW:
- xAxis=2, yAxis=25, width=86, startAngle=0°, endAngle=-90°

**`eTeks#doubleWindow126x123`** — 2 sashes (left CCW, right CW):
- Sash 1: xAxis=2, yAxis=25, width=63.5, startAngle=0°, endAngle=-90°
- Sash 2: xAxis=130, yAxis=25, width=63.5, startAngle=180°, endAngle=270°

**`eTeks#doubleWindow126x163`** — 2 sashes (left CCW, right CW):
- Sash 1: xAxis=2, yAxis=25, width=63.5, startAngle=0°, endAngle=-90°
- Sash 2: xAxis=130, yAxis=25, width=63.5, startAngle=180°, endAngle=270°

**`eTeks#doubleFrenchWindow126x200`** — 2 sashes (left CCW, right CW):
- Sash 1: xAxis=2, yAxis=25, width=63.5, startAngle=0°, endAngle=-90°
- Sash 2: xAxis=130, yAxis=25, width=63.5, startAngle=180°, endAngle=270°

**`eTeks#doubleOutwardOpeningWindow`** — 2 sashes opening outward:
- Sash 1: xAxis=5.9, yAxis=0.6, width=50.7, startAngle=90°, endAngle=0°
- Sash 2: xAxis=109.3, yAxis=0.6, width=50.7, startAngle=180°, endAngle=90°

**`eTeks#doubleHungWindow80x122`** — 0 sashes (sliding panels, no swing arc)

**`eTeks#sliderWindow126x200`** — 0 sashes (sliding panels, no swing arc)

**`eTeks#fixedWindow85x123`** — 0 sashes (fixed, no opening)

**`eTeks#fixedTriangleWindow85x85`** — 0 sashes (fixed)

**`eTeks#halfRoundWindow`** — 0 sashes (fixed)

**`eTeks#roundWindow`** — 0 sashes (fixed)

**`eTeks#roundDoorFrame`** — 0 sashes (frame only)

**`eTeks#garageDoor`** — 0 sashes (no plan-view arc; opens vertically)

**`eTeks#serviceHatch`** — 0 sashes

---

## Special Section: Lights

Every entity in the Lights category contains a light-source definition that SH3D uses to render
emissive illumination in the 3D view.

### Parameter glossary

| Parameter | Meaning |
|-----------|---------|
| `lightSourceX` | X position of the light emitter within the model bounding box (cm from left) |
| `lightSourceY` | Y position of the light emitter (cm from front) |
| `lightSourceZ` | Z height of the light emitter above the model's elevation origin (cm) |
| `lightSourceColor` | RGB hex color of the emitted light (e.g. `#BBBBBB`) |
| `lightSourceDiameter` | Sphere diameter of the point-light representation (cm) |

All 14 light entities have exactly **one light source** each (no multi-source entities in the default catalog).

### Light source details

| catalogId | name | X cm | Y cm | Z cm | color | diameter cm |
|-----------|------|------|------|------|-------|-------------|
| `eTeks#blueLightSource` | Blue light source | 5 | 5 | 5 | `#1010FF` | 10 |
| `eTeks#fireglowLightSource` | Fireglow light source | 5 | 5 | 5 | `#661C00` | 10 |
| `eTeks#floorUplight` | Floor uplight | 16.5 | 16.5 | 186.6 | `#BBAF96` | 15 |
| `eTeks#greenLightSource` | Green light source | 5 | 5 | 5 | `#10FF10` | 10 |
| `eTeks#halogenLightSource` | Halogen light source | 5 | 5 | 5 | `#BBAF96` | 10 |
| `eTeks#incandescentLightSource` | Incandescent light source | 5 | 5 | 5 | `#BB9854` | 10 |
| `eTeks#lamp` | Lamp | 22 | 22 | 34 | `#777777` | 6.0 |
| `eTeks#lightSource` | White light source | 5 | 5 | 5 | `#BBBBBB` | 10 |
| `eTeks#magentaLightSource` | Magenta light source | 5 | 5 | 5 | `#BB00BB` | 10 |
| `eTeks#pendantLamp` | Pendant lamp | 30 | 30 | 10 | `#AA9770` | 20 |
| `eTeks#redLightSource` | Red light source | 5 | 5 | 5 | `#FF1010` | 10 |
| `eTeks#spotlight` | Spotlight | 3.42 | 2.8 | 2.95 | `#44371B` | 4.5 |
| `eTeks#wallUplight` | Wall uplight | 12 | 8 | 19 | `#998764` | 7 |
| `eTeks#workLamp` | Work lamp | 6 | 2.9 | 29.5 | `#463E2E` | 5 |

### Additional light-source entity flags

The eight "raw light source" entities (`eTeks#lightSource`, `eTeks#halogenLightSource`,
`eTeks#incandescentLightSource`, `eTeks#fireglowLightSource`, `eTeks#redLightSource`,
`eTeks#greenLightSource`, `eTeks#blueLightSource`, `eTeks#magentaLightSource`) share these flags:

- `deformable=false` — cannot be resized in any axis
- `horizontallyRotatable=false` — cannot be rotated in the plan view
- `texturable=false` — material cannot be replaced
- `planIcon=/com/eteks/sweethome3d/io/resources/lightSourcePlanIcon.png` — custom top-down icon

The fixture lights (`eTeks#floorUplight`, `eTeks#spotlight`, `eTeks#pendantLamp`,
`eTeks#workLamp`, `eTeks#wallUplight`, `eTeks#lamp`) do not carry these restrictions and can be
freely moved, rotated, and re-textured.

---

## Special Section: Modelable Materials

Entities whose 3D models support per-part material overrides are marked `multiPartModel=true`.
In the SH3D XML, these accept `<material>` child elements that re-skin individual named mesh
parts.

### Multi-part model entities

| catalogId | name | category | notes |
|-----------|------|----------|-------|
| `eTeks#curtains` | Curtains | Miscellaneous | Fabric + rod materials |
| `eTeks#frame` | Frame | Miscellaneous | Frame body + mat + glass materials |
| `eTeks#mannequin` | Mannequin | Miscellaneous | Full articulated body; 13 poseable presets |
| `eTeks#texturableBox` | Box | Miscellaneous | 6 face-materials (top, bottom, front, back, left, right) |
| `eTeks#texturableCylinder0` | Cylinder | Miscellaneous | 3 materials (top cap, bottom cap, side) |
| `eTeks#texturableTriangle` | Triangle | Miscellaneous | Multiple face materials |

### Mannequin pose presets

`eTeks#mannequin` additionally carries 13 named `modelPresetTransformations` (bone-pose keyframes).
Preset names (1-indexed):

| # | Preset name |
|---|-------------|
| 1 | Standing |
| 2 | Standing with arms folded |
| 3 | Standing cross-legged |
| 4 | Walking |
| 5 | Running |
| 6 | Jumping |
| 7 | Dancing |
| 8 | Sitting |
| 9 | Sitting cross-legged |
| 10 | Cross-legged |
| 11 | Lying down |
| 12 | Lying on the back |
| 13 | Lying on the stomach |

To apply a preset in the SH3D XML, set the `modelTransformations` attribute on the furniture
element to the encoded transformation string stored in `modelPresetTransformations_<N>#87` in the
properties file.

### Additional entities with notable material structure

Entities below do not set `multiPartModel=true` but have texturable materials at the renderer level:

- `eTeks#filledBookcase` — `shelfBoxes` property defines 9 volumetric shelf collision boxes
  (each as `x y z w d h` in cm), allowing items to be placed on individual shelves.
- All light source "fixture" models (floorUplight, spotlight, pendantLamp, etc.) expose
  their lamp-shade/bulb mesh parts for re-texturing in the 3D view.

---

## Property Quick Reference

The following property names appear in the catalog. Use these as keys when parsing or generating
SH3D furniture XML:

| Property key (no index suffix) | Type | Description |
|---------------------------------|------|-------------|
| `id` | string | Catalog entity identifier, e.g. `eTeks#door` |
| `name` | string | Display name (English) |
| `category` | string | Category group name |
| `tags` | string | Space/comma separated tags |
| `icon` | path | JAR-relative path to PNG icon |
| `planIcon` | path | JAR-relative path to plan-view icon override |
| `model` | path | JAR-relative path to OBJ/DAE/3DS model file |
| `modelSize` | integer | Model file size in bytes |
| `modelRotation` | floats | 3×3 rotation matrix (row-major, space-separated) |
| `width` | float | Default width (cm) |
| `depth` | float | Default depth (cm) |
| `height` | float | Default height (cm) |
| `elevation` | float | Default elevation above floor (cm) |
| `dropOnTopElevation` | float | Top surface Z for placing items on top; -1 = ceiling/wall mount |
| `movable` | bool | Whether item is freely movable in plan |
| `doorOrWindow` | bool | Whether item cuts a wall opening |
| `doorOrWindowWallThickness` | float | % of opening depth representing wall thickness |
| `doorOrWindowWallDistance` | float | Gap from wall face to frame front (cm) |
| `doorOrWindowWallCutOutOnBothSides` | bool | Cut visible from both wall faces |
| `doorOrWindowCutOutShape` | SVG path | Normalized SVG path for wall hole shape |
| `doorOrWindowWidthDepthDeformable` | bool | Whether depth can be resized independently |
| `doorOrWindowSashXAxis` | float(s) | Sash pivot X position(s) (cm) |
| `doorOrWindowSashYAxis` | float(s) | Sash pivot Y position(s) (cm) |
| `doorOrWindowSashWidth` | float(s) | Sash arc radius/width(s) (cm) |
| `doorOrWindowSashStartAngle` | float(s) | Sash open start angle(s) (degrees) |
| `doorOrWindowSashEndAngle` | float(s) | Sash open end angle(s) (degrees) |
| `staircaseCutOutShape` | SVG path | Normalized SVG path for floor hole above staircase |
| `lightSourceX` | float | Light emitter X position within model (cm) |
| `lightSourceY` | float | Light emitter Y position within model (cm) |
| `lightSourceZ` | float | Light emitter Z height within model (cm) |
| `lightSourceColor` | hex string | Emitted light color (`#RRGGBB`) |
| `lightSourceDiameter` | float | Point-light sphere diameter (cm) |
| `multiPartModel` | bool | Whether model parts can be individually re-skinned |
| `deformable` | bool | Whether model can be non-uniformly scaled |
| `horizontallyRotatable` | bool | Whether model can be rotated in plan view |
| `texturable` | bool | Whether material can be replaced |
| `shelfElevations` | float(s) | Z heights of shelf surfaces for object placement (cm) |
| `shelfBoxes` | floats | Shelf collision volumes: `x y z w d h` sextuplets (cm) |
| `creator` | string | Model author |
| `license` | string | License identifier |
| `modelPresetTransformationsName_N` | string | Display name for pose preset N |
| `modelPresetTransformations_N` | encoded | Encoded bone transformation matrix for pose preset N |

---

*Generated from `DefaultFurnitureCatalog.properties` v7.5 — 100 entities across 8 categories.*
