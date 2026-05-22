# SH3D Home.xml Schema Coverage Report

**Date**: 2026-05-22 (refine pass — last full schema audit 2026-05-15)
**Python model**: `cli_anything/sweethome3d/core/model.py`
**Schema version**: 7400 (SH3D 7.5)

---

## Refine pass — 2026-05-22

CLI coverage expansion (no new model fields, but lots of previously-internal
fields now reachable from the CLI):

- New `textures` command group + 26-entry stock catalog
- New `find` command group wrapping `core/find.py`
- New `polyline` command group
- New `level set/select`, `room set`, `room recompute-points`
- New `wall baseboard` and texture options on `wall add/set`
- New `camera save/list/delete/go` for stored viewpoints
- New `dimension set` / `label set`
- New `environment video-size`, sky/ground texture options + extras
- **Schema fix**: `<texture attribute="..."/>` flat form now emitted (was
  silently incompatible with SH3D's reader)

Tests: 282 → 329 (+47 in `test_refine.py`), 6 skipped SH3D-binary-only.

---

## Summary (schema field coverage — 2026-05-15)

| Metric | Before | After |
|--------|--------|-------|
| Total model fields | 197 | 329 |
| Coverage (of ~185 schema attributes) | ~39% (72) | ≥95% |
| Dataclasses | 13 | 24 |
| Test pass count | 97 | 123 |
| New tests added | 0 | 26 |

---

## Fields Added (Grouped by Element/Dataclass)

### New Dataclasses

| Dataclass | Fields | Description |
|-----------|--------|-------------|
| `Baseboard` | 4 | Skirting board on wall sides |
| `Sash` | 5 | Door/window opening leaf geometry |
| `LightSource` | 5 | Point light emitter within a light fixture |
| `LightSourceMaterial` | 1 | Named material group that glows |
| `Material` | 5 | Per-material colour/shininess/texture override |
| `Transformation` | 2 | Named 4×3 affine joint transformation |
| `TextStyle` | 5 | Font/size/alignment for text annotations |
| `FurnitureGroup` | 25 | Named group of furniture pieces |
| `Print` | 14 | Page layout and print options |
| `Shelf` | 7 | Shelf plane or bounding box in a shelf unit |

### Existing Dataclasses — New Fields

#### `Texture` (+1)
- `leftToRightOriented` — mirror texture on back face

#### `Wall` (+3)
- `leftSideBaseboard` — baseboard on left wall face
- `rightSideBaseboard` — baseboard on right wall face
- `properties` — key/value metadata dict

#### `Room` (+6)
- `nameStyle` — TextStyle for name label
- `areaStyle` — TextStyle for area label
- `areaAngle` — area label rotation
- `areaXOffset` — area label X offset
- `areaYOffset` — area label Y offset
- `properties` — key/value metadata dict

#### `PieceOfFurniture` (+36)
- `sashes` — list of Sash for doorOrWindow
- `lightSources` — list of LightSource for light
- `lightSourceMaterials` — list of LightSourceMaterial for light
- `materials` — list of Material overrides
- `modelTransformations` — list of Transformation
- `nameStyle` — TextStyle for name label
- `texture` — piece texture (no wrapper element)
- `properties` — key/value metadata dict
- `shelves` — list of Shelf for shelfUnit
- `planIcon` — plan-view icon (CONTENT path)
- `widthInPlan` — override width for plan display
- `depthInPlan` — override depth for plan display
- `heightInPlan` — override height for plan display
- `modelFlags` — bitfield (1=backFaceShown)
- `modelSize` — file size hint in bytes
- `modelMirrored` — mirror model along width axis
- `modelRotation` — 3×3 rotation matrix string
- `modelCenteredAtOrigin` — whether model origin is centred
- `staircaseCutOutShape` — SVG path for staircase cut-out
- `dropOnTopElevation` — relative elevation for drop-on-top
- `resizable` — dimensions can be changed
- `deformable` — W/D/H can be set independently
- `texturable` — texture can be applied
- `horizontallyRotatable` — pitch/roll can be set
- `doorOrWindowFlag` — behaves as door/window
- `nameAngle` — name label rotation
- `nameXOffset` — name label X offset
- `nameYOffset` — name label Y offset
- `information` — additional info (URL etc.)
- `license` — license text
- `price` — unit price (decimal string)
- `valueAddedTaxPercentage` — VAT %
- `currency` — ISO 4217 code
- `wallCutOutOnBothSides` — cut through both sides
- `widthDepthDeformable` — width/depth can be resized independently
- `lockedInBasePlan` — locked in base plan

#### `DimensionLine` (+1)
- `lengthStyle` — TextStyle for the length annotation

#### `Label` (+1)
- `style` — TextStyle for the label text

#### `Polyline` (+2)
- `dashPattern` — custom dash pattern (space-separated floats)
- `visibleIn3D` — rendered in 3D view

#### `Compass` (+1)
- `properties` — key/value metadata dict

#### `Level` (+1)
- `properties` — key/value metadata dict

#### `Environment` (+3)
- `backgroundImageVisibleOnGround3D` — project background image on 3D ground
- `videoCameraPath` — list of Camera waypoints for video fly-through
- `observerCameraElevationAdjusted` — already existed in field but wasn't read from XML

#### `Home` (+5)
- `furnitureGroups` — list of FurnitureGroup
- `furnitureVisibleProperties` — list of visible furniture column names
- `properties` — key/value metadata dict
- `storedCameras` — list of stored camera viewpoints
- `printSettings` — Print settings object

---

## Fields Deliberately Skipped

| Field | Element | Reason |
|-------|---------|--------|
| `backFaceShown` | `pieceOfFurniture` | Legacy alias for `modelFlags & 1`; the canonical `modelFlags` attribute covers this. Reading SH3D files writes `modelFlags`, not `backFaceShown`. |

---

## Chunks Completed

| Chunk | Description | Status |
|-------|-------------|--------|
| 1 | Baseboard dataclass, Wall fields, leftToRightOriented on Texture | Done |
| 2 | Sash dataclass, PieceOfFurniture.sashes | Done |
| 3 | LightSource + LightSourceMaterial dataclasses | Done |
| 4 | Material + Transformation dataclasses | Done |
| 5 | TextStyle dataclass; nameStyle/areaStyle/lengthStyle/style fields | Done |
| 6 | FurnitureGroup (recursive), Home.furnitureGroups | Done |
| 7 | Print dataclass, Home.printSettings | Done |
| 8 | PieceOfFurniture: 28 missing attributes from schema | Done |
| 9 | Wall missing fields | Skipped — already complete after Chunk 1 |
| 10 | Room missing fields | Covered in Chunks 5 and part of 8 |
| 11 | Camera missing fields | Already complete in original model |
| 12 | DimensionLine missing fields | Covered in Chunks 5 |
| 13 | Label missing fields | Covered in Chunk 5 |
| 14 | Polyline: dashPattern, visibleIn3D | Done |
| 15 | Compass missing fields | Already complete in original model |
| 16 | Environment: backgroundImageVisibleOnGround3D, videoCameraPath | Done |
| 17 | Properties on Home/Wall/Room/Furniture/Level/Compass; storedCameras; furnitureVisibleProperties | Done |
| 18 | Shelf + ShelfUnit (kind="shelfUnit") | Done |
| 19 | CameraPath | Covered in Chunk 16 as videoCameraPath |
| 20 | FurnitureVisibleProperties | Covered in Chunk 17 |

---

## Schema Attributes Found Not in Reference Doc

None discovered — the reference doc (`03-home-xml-schema.md`) appeared complete.

---

## Final Field Distribution

```
BackgroundImage:     9 fields
Baseboard:           4 fields
Camera:             13 fields
Compass:             9 fields
DimensionLine:      14 fields
Environment:        22 fields
FurnitureGroup:     25 fields
Home:               25 fields
Label:              11 fields
Level:              10 fields
LightSource:         5 fields
LightSourceMaterial: 1 fields
Material:            5 fields
PieceOfFurniture:   68 fields
Point:               2 fields
Polyline:           15 fields
Print:              14 fields
Room:               23 fields
Sash:                5 fields
Shelf:               7 fields
TextStyle:           5 fields
Texture:            12 fields
Transformation:      2 fields
Wall:               23 fields
─────────────────────────────
TOTAL:             329 fields
```
