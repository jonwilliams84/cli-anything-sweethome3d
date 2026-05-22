# Catalog Usage & Gap Analysis

Analysis of SH3D catalog entity references across the SVG → SH3D import pipeline. Reports what catalog entries are actively used in the codebase, what comes from the spec, and what high-value entries ship in SH3D but are not yet integrated.

**Analysis date:** 2026-05-15  
**Codebase:** `/home/jonwi/CLI-Anything/cli-anything-sweethome3d/`  
**Home spec:** `/mnt/c/Users/jonwi/Documents/Home-spec.yaml`

---

## 1. Catalog IDs Used in Code (By Usage Pattern)

### Actively Used in Core Openings Pipeline

These are the primary catalog IDs referenced in the spec or pipeline stages:

| catalogId | Used In | Context | Kind | Spec-Driven? |
|-----------|---------|---------|------|--------------|
| `eTeks#frontDoor` | `spec.py:100`, `catalog.py:41` | External door (default) | doorOrWindow | YES (spec) |
| `eTeks#garageDoor` | `spec.py:101`, `catalog.py:44` | External door (width >= 120cm) | doorOrWindow | YES (spec) |
| `eTeks#doorFrame` | `spec.py:103`, `catalog.py:38`, `furniture.py:21` | Internal door (default) | doorOrWindow | YES (spec) |
| `eTeks#slidingDoors` | `spec.py:104`, `catalog.py:45` | Patio door (default) | doorOrWindow | YES (spec) |
| `eTeks#fixedWindow85x123` | `spec.py:106`, `catalog.py:47`, `furniture.py:22` | Standard window (default) | doorOrWindow | YES (spec) |
| `eTeks#doubleWindow126x163` | `spec.py:107`, `catalog.py:51` | Large window (width >= 200cm) | doorOrWindow | YES (spec) |
| `eTeks#texturableBox` | `spec.py:110`, `pipeline.py:245`, `pipeline.py:652` | Skylight & fallback box | pieceOfFurniture | YES (spec) |
| `eTeks#pendantLamp` | `spec.py:131`, `catalog.py:57`, `furniture.py:23` | Light fixture (default) | light | YES (spec) |

### Hardcoded in Pipeline (Not in Spec)

| catalogId | Used In | Context | Kind | Spec-Driven? |
|-----------|---------|---------|------|--------------|
| `eTeks#doubleFrenchWindow126x200` | `pipeline.py:193` | Fallback for patio_door (internal override) | doorOrWindow | NO |
| `eTeks#brickWallTexture` | `spec.py:55` (comment example) | Wall texture (not actually used) | texture | NO (example only) |

---

## 2. Catalog IDs Referenced in Home-spec.yaml

Complete list from the spec file:

| catalogId | Spec Field | Value |
|-----------|-----------|-------|
| `eTeks#frontDoor` | `openings.catalogs.external_door.default` | Primary external door |
| `eTeks#garageDoor` | `openings.catalogs.external_door.variants[0].catalog` | Large external door (>= 120cm) |
| `eTeks#doorFrame` | `openings.catalogs.internal_door.default` | Internal door |
| `eTeks#slidingDoors` | `openings.catalogs.patio_door.default` | Sliding glass doors |
| `eTeks#fixedWindow85x123` | `openings.catalogs.window.default` | Standard window |
| `eTeks#doubleWindow126x163` | `openings.catalogs.window.variants[0].catalog` | Double window (>= 200cm) |
| `eTeks#texturableBox` | `openings.catalogs.skylight.default` | Skylight (texturable) |
| `eTeks#pendantLamp` | `lights.catalog` | Pendant ceiling lamp |
| `eTeks#brickWallTexture` | (comment example) | Wall texture reference (not used) |

**Total in spec:** 9 catalog IDs (1 example comment)

---

## 3. Hard-Coded vs Spec-Driven Analysis

### Hard-Coded Catalog IDs (Candidates for Externalization)

| catalogId | Location | Lines | Current Behavior | Recommendation |
|-----------|----------|-------|------------------|-----------------|
| `eTeks#doorFrame` | `furniture.py:21` | `DEFAULT_DOOR_CATALOG_ID` | Fallback when no spec provided | Move to spec `meta.defaults.door_catalog_id` |
| `eTeks#fixedWindow85x123` | `furniture.py:22` | `DEFAULT_WINDOW_CATALOG_ID` | Fallback when no spec provided | Move to spec `meta.defaults.window_catalog_id` |
| `eTeks#pendantLamp` | `furniture.py:23` | `DEFAULT_LIGHT_CATALOG_ID` | Fallback when no spec provided | Move to spec `meta.defaults.light_catalog_id` |
| `eTeks#doubleFrenchWindow126x200` | `pipeline.py:193` | Hard-coded patio door override | Overrides spec silently (not obvious from spec) | **Move to spec variant or add spec override mechanism** |

**Summary:** 3 of 4 hard-coded IDs are defensive fallbacks; 1 (`doubleFrenchWindow126x200`) silently overrides the spec and should be externalized or at least documented.

---

## 4. Catalog Metadata Availability

The codebase maintains a comprehensive metadata dictionary in `_sh3d_catalog_metadata.SH3D_CATALOG` with **100 distinct furniture catalog entries**, all with:
- JAR resource paths (3D model `.obj` file location)
- Icon paths (`.png` preview image)
- Model size in bytes
- Creator attribution
- Kind classification (`pieceOfFurniture`, `doorOrWindow`, `light`)

This full catalog is available for expansion. See `/home/jonwi/CLI-Anything/cli-anything-sweethome3d/cli_anything/sweethome3d/core/_sh3d_catalog_metadata.py` for the complete list.

---

## 5. Gap Analysis

### Status: Waiting for Reference Catalogs

The sibling reference files do not yet exist:
- `docs/sh3d-reference/01-furniture-catalog.md` — full furniture catalog (TBD)
- `docs/sh3d-reference/02-textures-catalog.md` — full textures catalog (TBD)

Once those land, this gap analysis should be re-run to generate recommendations for:
- Door styles available but unused (e.g., `roundedDoor`, `door`, `openDoor`, French windows)
- Window styles available but unused (e.g., `halfRoundWindow`, `roundWindow`, `doubleOutwardOpeningWindow`)
- Light fixtures available but unused (e.g., `spotlight`, `wallUplight`, `floorUplight`, `workLamp`)
- Furniture categories we don't populate at all:
  - **Bedroom:** `bed`, `bed90x190`, `bed140x190`, `bunkBed90x190`, `loftBed140x190`, `bedsideTable`, `wardrobe`, `chest`
  - **Lounge/Living:** `sofa`, `sofa2`, `armchair`, `armchair2`, `coffeeTable`, `tvUnit`, `flatTV`, `bookcase`, `filledBookcase`
  - **Kitchen:** `kitchenCabinet`, `kitchenUpperCabinet`, `sink`, `fridge`, `fridgeFreezer`, `oven`, `cooker`, `dishwasher`, `hood`, `table`, `chair`, `chair2`
  - **Bathroom:** `bath`, `fittedBath`, `shower`, `washbasin`, `washbasinWithCabinet`, `toiletUnit`, `clothesWasher`
  - **Other:** Stairs, radiators, decorative items, etc.
- Textures available but unused (unavailable until `02-textures-catalog.md` is ready)

---

## 6. Recommendations (High-Value Additions)

Based on current usage patterns and the spec structure, the following enhancements would provide immediate value:

### Immediate (No Spec Changes Required)

1. **Document the `eTeks#doubleFrenchWindow126x200` override** in `pipeline.py:193`
   - Currently silently overrides the patio_door spec entry
   - Add a comment explaining why this override exists

2. **Export hard-coded defaults to spec comments**
   - `DEFAULT_DOOR_CATALOG_ID`, `DEFAULT_WINDOW_CATALOG_ID`, `DEFAULT_LIGHT_CATALOG_ID` are fallbacks
   - Mention in spec that these come from `furniture.py` if not overridden

### Medium-Term (Spec Enhancement)

3. **Extend the spec to support room-type-driven furniture**
   - Add optional `rooms.furniture_rules` section:
     ```yaml
     rooms:
       furniture_rules:
         bedroom:
           - catalog: eTeks#bed90x190
             placement: center_of_room
             count: 1
         living_room:
           - catalog: eTeks#sofa
             placement: wall_facing
     ```
   - This would auto-populate rooms detected as "Bedroom", "Living Room", etc.

4. **Support per-opening catalog overrides**
   - Extend openings spec to allow instance-level catalog selection:
     ```yaml
     openings:
       overrides:
         - region: "garage"
           kind: external_door
           catalog: eTeks#garageDoor
     ```

5. **Add a textures section to the spec**
   - Parallel to current `lights` and `openings` sections:
     ```yaml
     textures:
       walls:
         external_outside: eTeks#brickWallTexture  # currently commented example
       environment:
         sky: eTeks#skyTexture
         ground: eTeks#grassTexture
     ```

### Long-Term (Feature Expansion)

6. **Auto-place furniture by room type**
   - When a bedroom is detected, place `bed90x190` (or variant based on room size)
   - When a living room is detected, place `sofa` + `coffeeTable` + `tvUnit`
   - When a kitchen is detected, place `kitchenCabinet`, `sink`, `cooker`, `fridge`
   - Requires room name classification or geometry-based heuristics

7. **Window style variants**
   - Extend `openings.catalogs.window.variants` to include frame style, pane count
   - E.g., `window.variants[1]: {if_width_cm_gte: 150, style: "french", catalog: "eTeks#frenchWindow85x200"}`

---

## Summary Statistics

| Metric | Value |
|--------|-------|
| Total catalog IDs in SH3D metadata | 100 |
| Actively used in spec | 8 |
| Actively used in pipeline (hardcoded overrides) | 1 |
| Hard-coded fallback defaults | 3 |
| Total distinct door/window styles referenced | 8 |
| Total light fixtures referenced | 1 |
| Furniture categories with at least one entry | 0 (gap) |
| Recommended gap-filling entries | 50+ |

---

## Files Modified by This Report

- Created: `/home/jonwi/CLI-Anything/cli-anything-sweethome3d/docs/sh3d-reference/04-usage-and-gaps.md`

## Next Steps

1. Once `01-furniture-catalog.md` and `02-textures-catalog.md` are available, re-run this analysis to identify specific unused entries in each category
2. Prioritize room-driven furniture placement as the highest-value quick win
3. Consider making `eTeks#doubleFrenchWindow126x200` configurable in the spec rather than hard-coded
