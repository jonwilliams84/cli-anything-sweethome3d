# Sweet Home 3D 7.5 — Default Textures Catalog Reference

> **Source**: `lib/Textures.jar` → `com/eteks/sweethome3d/io/DefaultTexturesCatalog.properties`
> **Catalog ID**: `SweetHome3D#DefaultTextures`
> **Version**: 7.5
> **License**: GNU GPL / CC-BY 3.0 — Space Mushrooms
> **Provider**: www.sweethome3d.com

---

## Catalog Summary

| Metric | Value |
|---|---|
| Total textures | 26 |
| Categories | Floor, Wall, Sky |
| Floor textures | 11 |
| Wall textures | 12 |
| Sky textures | 3 |

### All Categories

- **Floor** (11 textures): Flooring materials — tile, wood, stone, grass, paving
- **Wall** (12 textures): Wall cladding — brick, stone, marble, roughcast, tiles, vegetation
- **Sky** (3 textures): Panoramic sky images for the 3D environment background

---

## How to Use This Reference

### Referencing a texture in SH3D XML

Textures are embedded as child elements within walls, rooms, and the environment element.
The `catalogId` attribute links to a catalog entry so SH3D can resolve the image from
its built-in library.

```xml
<!-- Wall: left-side texture (interior face) -->
<wall ...>
  <leftSideTexture catalogId="eTeks#smallBricks" name="Small bricks"
    width="23.0" height="14.9" creator="eTeks"/>
</wall>

<!-- Wall: right-side texture (exterior face) -->
<wall ...>
  <rightSideTexture catalogId="eTeks#roughcast" name="Roughcast"
    width="20.0" height="20.0" creator="eTeks"/>
</wall>

<!-- Room: floor texture -->
<room ...>
  <floorTexture catalogId="eTeks#woodenFloor" name="Wooden floor"
    width="42.5" height="42.5" creator="eTeks"/>
</room>

<!-- Room: ceiling texture -->
<room ...>
  <ceilingTexture catalogId="eTeks#woodenFloor" name="Wooden floor"
    width="42.5" height="42.5" creator="eTeks"/>
</room>

<!-- Environment: sky and ground -->
<environment ...>
  <skyTexture catalogId="eTeks#blueSky" name="Blue sky"
    width="100.0" height="41.3" creator="eTeks"/>
  <groundTexture catalogId="eTeks#grass" name="Grass"
    width="30.0" height="30.0" creator="eTeks"/>
</environment>
```

### Python `Texture` dataclass (model.py)

```python
@dataclass
class Texture:
    catalogId: Optional[str] = None   # e.g. "eTeks#smallBricks"
    name: Optional[str] = None        # display name from catalog
    image: Optional[str] = None       # CONTENT path (embedded file)
    width: Optional[float] = None     # real-world tile width in cm
    height: Optional[float] = None    # real-world tile height in cm
    xOffset: float = 0
    yOffset: float = 0
    angle: float = 0
    scale: float = 1.0
    creator: Optional[str] = None     # e.g. "eTeks"
    fittingArea: bool = False         # True = stretch-to-fit, False = tile/repeat
```

When `catalogId` is set, SH3D resolves `name`, `image`, `width`, `height`, and
`creator` from the catalog automatically. You only need to supply the `catalogId`
and the redundant display fields (`name`, `width`, `height`, `creator`) that SH3D
writes into the XML for offline portability.

### Tile width/height units

`width` and `height` are in **centimetres** and represent the real-world size of
one texture tile. A `30 × 30 cm` tile on a `300 cm` wall will repeat 10 times
horizontally. When `fittingArea` is `true` (rare in this catalog) the texture
is stretched to cover the target surface exactly once.

---

## Floor Textures

Suitable for: `<room floorTexture .../>`, `<room ceilingTexture .../>`,
`<environment groundTexture .../>` (outdoor ground surfaces).

| catalogId | Name | W×H (cm) | fittingArea | Image path | Creator |
|---|---|---|---|---|---|
| `eTeks#beigeTile` | Beige tiles | 20 × 20 | false | `/com/eteks/sweethome3d/io/resources/textures/beigeTile.jpg` | eTeks |
| `eTeks#blackAndWhiteTiles` | Black and white tiles | 70 × 70 | false | `/com/eteks/sweethome3d/io/resources/textures/blackAndWhiteTiles.jpg` | eTeks |
| `eTeks#darkBlueTile` | Dark blue tiles | 33.5 × 33.5 | false | `/com/eteks/sweethome3d/io/resources/textures/darkBlueTile.jpg` | eTeks |
| `eTeks#grass` | Grass | 30 × 30 | false | `/com/eteks/sweethome3d/io/resources/textures/grass.jpg` | eTeks |
| `eTeks#greyTile` | Grey tiles | 31.5 × 31.5 | false | `/com/eteks/sweethome3d/io/resources/textures/greyTile.jpg` | eTeks |
| `eTeks#lightBlueTile` | Light blue tiles | 33.5 × 33.5 | false | `/com/eteks/sweethome3d/io/resources/textures/lightBlueTile.jpg` | eTeks |
| `eTeks#oldWoodenFloor` | Old wooden floor | 26.9 × 26.9 | false | `/com/eteks/sweethome3d/io/resources/textures/oldWoodenFloor.jpg` | eTeks |
| `eTeks#pavingStone` | Paving stone | 42.3 × 30 | false | `/com/eteks/sweethome3d/io/resources/textures/pavingStone.jpg` | eTeks |
| `eTeks#pebbles` | Pebbles | 20 × 20 | false | `/com/eteks/sweethome3d/io/resources/textures/pebbles.jpg` | eTeks |
| `eTeks#redTiles` | Red tiles | 40 × 40 | false | `/com/eteks/sweethome3d/io/resources/textures/redTiles.jpg` | eTeks |
| `eTeks#stoneTiles` | Stone tiles | 60 × 40 | false | `/com/eteks/sweethome3d/io/resources/textures/stoneTiles.jpg` | eTeks |
| `eTeks#woodenFloor` | Wooden floor | 42.5 × 42.5 | false | `/com/eteks/sweethome3d/io/resources/textures/woodenFloor.jpg` | eTeks |

> **Notes:**
> - `eTeks#grass` and `eTeks#pebbles` are the most natural choices for outdoor ground (`<environment groundTexture/>`).
> - All floor tiles have `fittingArea=false` (they tile/repeat), which is the correct behaviour for floor surfaces.
> - `eTeks#pavingStone` (42.3 × 30 cm) tiles are non-square; verify your UV mapping handles non-square aspect ratios.

---

## Wall Textures

Suitable for: `<wall leftSideTexture .../>`, `<wall rightSideTexture .../>`.
Also usable for `<room ceilingTexture .../>` (marble, roughcast).

| catalogId | Name | W×H (cm) | fittingArea | Image path | Creator |
|---|---|---|---|---|---|
| `eTeks#blueTiles` | Blue tiles | 20 × 20 | false | `/com/eteks/sweethome3d/io/resources/textures/blueTiles.jpg` | eTeks |
| `eTeks#boxTree` | Box tree | 20 × 20 | false | `/com/eteks/sweethome3d/io/resources/textures/boxTree.jpg` | eTeks |
| `eTeks#marbleWall` | Marble | 50 × 50 | false | `/com/eteks/sweethome3d/io/resources/textures/marbleWall.jpg` | eTeks |
| `eTeks#roughcast` | Roughcast | 20 × 20 | false | `/com/eteks/sweethome3d/io/resources/textures/roughcast.jpg` | eTeks |
| `eTeks#smallBricks` | Small bricks | 23 × 14.9 | false | `/com/eteks/sweethome3d/io/resources/textures/smallBricks.jpg` | eTeks |
| `eTeks#smallRedBricks` | Small red bricks | 36.2 × 14.9 | false | `/com/eteks/sweethome3d/io/resources/textures/smallRedBricks.jpg` | eTeks |
| `eTeks#smallWhiteBricks` | Small white bricks | 35.3 × 14.9 | false | `/com/eteks/sweethome3d/io/resources/textures/smallWhiteBricks.jpg` | eTeks |
| `eTeks#stone2Wall` | Stone | 64.8 × 40 | false | `/com/eteks/sweethome3d/io/resources/textures/stone2Wall.jpg` | eTeks |
| `eTeks#stone3Wall` | Stone | 55.3 × 35 | false | `/com/eteks/sweethome3d/io/resources/textures/stone3Wall.jpg` | eTeks |
| `eTeks#stoneWall` | Stone | 76 × 35 | false | `/com/eteks/sweethome3d/io/resources/textures/stoneWall.jpg` | eTeks |
| `eTeks#wallBeigeTile` | Beige tiles | 20 × 31.5 | false | `/com/eteks/sweethome3d/io/resources/textures/wallBeigeTile.jpg` | eTeks |

> **Notes:**
> - `eTeks#stoneWall`, `eTeks#stone2Wall`, `eTeks#stone3Wall` are three distinct stone
>   variations at different tile scales (76×35, 64.8×40, 55.3×35 cm). The catalog
>   assigns all three the display name "Stone" — use the `catalogId` to distinguish them.
> - The three brick variants (`eTeks#smallBricks`, `eTeks#smallRedBricks`,
>   `eTeks#smallWhiteBricks`) all have a height of 14.9 cm (standard brick course + mortar).
> - `eTeks#boxTree` is an ornamental hedge texture, useful on exterior garden walls.
> - `eTeks#marbleWall` and `eTeks#roughcast` can also function as ceiling textures.

---

## Sky Textures

Suitable for: `<environment skyTexture .../>` only.
These are panoramic images wrapped around the 3D scene horizon; they should not
be applied to walls or floors.

| catalogId | Name | W×H (cm) | fittingArea | Image path | Creator |
|---|---|---|---|---|---|
| `eTeks#blueSky` | Blue sky | 100 × 41.3 | false | `/com/eteks/sweethome3d/io/resources/textures/blueSky.jpg` | eTeks |
| `eTeks#cloudy` | Cloudy | 100 × 27.6 | false | `/com/eteks/sweethome3d/io/resources/textures/cloudy.jpg` | eTeks |
| `eTeks#veryCloudy` | Very cloudy | 100 × 44.8 | false | `/com/eteks/sweethome3d/io/resources/textures/veryCloudy.jpg` | eTeks |

> **Notes:**
> - Sky textures have very different aspect ratios; the `height` value controls how
>   much vertical sky is visible above the horizon in the 3D view.
> - `eTeks#blueSky` (100 × 41.3 cm) is the most neutral sky for rendering.
> - The `width=100` convention is a normalisation token — SH3D uses it to detect
>   panoramic sky images; do not change it.

---

## Notes for the SVG Import Pipeline

### Recommended texture choices by surface type

| Surface type | XML element | Recommended default catalogId | Notes |
|---|---|---|---|
| Interior wall face | `leftSideTexture` | `eTeks#roughcast` or `eTeks#smallBricks` | 20 cm tile works well at typical room scale |
| Exterior wall face | `rightSideTexture` | `eTeks#smallRedBricks` or `eTeks#roughcast` | Exterior-facing |
| Timber-frame interior | `leftSideTexture` | `eTeks#woodenFloor` | Can be applied vertically as wall panelling |
| Floor (interior) | `floorTexture` | `eTeks#woodenFloor` or `eTeks#greyTile` | — |
| Floor (wet room) | `floorTexture` | `eTeks#beigeTile` or `eTeks#stoneTiles` | — |
| Ceiling | `ceilingTexture` | `eTeks#roughcast` or `eTeks#marbleWall` | Sky textures are NOT valid here |
| Outdoor ground | `groundTexture` | `eTeks#grass` or `eTeks#pebbles` | Used in `<environment>` |
| Sky background | `skyTexture` | `eTeks#blueSky` | Used in `<environment>` |

### Which textures go where — quick rule

- **Floor category** textures → floors, ceilings, outdoor ground
- **Wall category** textures → wall faces (left/right side), sometimes ceilings
- **Sky category** textures → `<environment skyTexture/>` only; never walls or floors

---

## Cross-References: spec/code IDs vs. actual catalog

The pipeline spec (`bungalow-spec.yaml`) and codebase reference several texture IDs.
Here is the verification status against the actual catalog:

| Referenced ID | Exists in catalog? | Correct ID | Notes |
|---|---|---|---|
| `eTeks#brickWallTexture` | **No** | `eTeks#smallBricks` or `eTeks#smallRedBricks` | The catalog has no `brickWallTexture` entry. Use `eTeks#smallBricks` (grey/beige, 23×14.9 cm) or `eTeks#smallRedBricks` (36.2×14.9 cm). |
| `eTeks#brick` | **No** | `eTeks#smallBricks` | No bare `brick` entry exists. |
| `eTeks#wood` | **No** | `eTeks#woodenFloor` or `eTeks#oldWoodenFloor` | No bare `wood` entry. Use `eTeks#woodenFloor` (42.5×42.5) or `eTeks#oldWoodenFloor` (26.9×26.9). |
| `eTeks#tiles` | **No** | Depends on colour: `eTeks#greyTile`, `eTeks#beigeTile`, `eTeks#blueTiles`, etc. | No bare `tiles` entry. Pick by colour/surface context. |
| `eTeks#woodenFloor` | **Yes** | `eTeks#woodenFloor` | Confirmed — 42.5×42.5 cm, Floor category. |
| `eTeks#smallBricks` | **Yes** | `eTeks#smallBricks` | Confirmed — 23×14.9 cm, Wall category. |
| `eTeks#roughcast` | **Yes** | `eTeks#roughcast` | Confirmed — 20×20 cm, Wall category. |
| `eTeks#grass` | **Yes** | `eTeks#grass` | Confirmed — 30×30 cm, Floor/Ground category. |
| `eTeks#blueSky` | **Yes** | `eTeks#blueSky` | Confirmed — 100×41.3 cm, Sky category. |
| `eTeks#marbleWall` | **Yes** | `eTeks#marbleWall` | Confirmed — 50×50 cm, Wall category. |

### Key finding for the pipeline

The ID `eTeks#brickWallTexture` (used as an example in `bungalow-spec.yaml`) does **not**
exist in the default catalog. The spec comment was illustrative. The correct IDs for
brick textures are:

```
eTeks#smallBricks       — grey/mortar bricks, 23 × 14.9 cm
eTeks#smallRedBricks    — red bricks, 36.2 × 14.9 cm
eTeks#smallWhiteBricks  — white bricks, 35.3 × 14.9 cm
```

---

## Complete Catalog (All 26 Textures, by catalogId)

| # | catalogId | Name | Category | W×H (cm) | Image path |
|---|---|---|---|---|---|
| 16 | `eTeks#beigeTile` | Beige tiles | Floor | 20 × 20 | `…/beigeTile.jpg` |
| 6 | `eTeks#blackAndWhiteTiles` | Black and white tiles | Floor | 70 × 70 | `…/blackAndWhiteTiles.jpg` |
| 26 | `eTeks#blueSky` | Blue sky | Sky | 100 × 41.3 | `…/blueSky.jpg` |
| 3 | `eTeks#blueTiles` | Blue tiles | Wall | 20 × 20 | `…/blueTiles.jpg` |
| 13 | `eTeks#boxTree` | Box tree | Wall | 20 × 20 | `…/boxTree.jpg` |
| 25 | `eTeks#cloudy` | Cloudy | Sky | 100 × 27.6 | `…/cloudy.jpg` |
| 18 | `eTeks#darkBlueTile` | Dark blue tiles | Floor | 33.5 × 33.5 | `…/darkBlueTile.jpg` |
| 11 | `eTeks#grass` | Grass | Floor | 30 × 30 | `…/grass.jpg` |
| 2 | `eTeks#greyTile` | Grey tiles | Floor | 31.5 × 31.5 | `…/greyTile.jpg` |
| 17 | `eTeks#lightBlueTile` | Light blue tiles | Floor | 33.5 × 33.5 | `…/lightBlueTile.jpg` |
| 21 | `eTeks#marbleWall` | Marble | Wall | 50 × 50 | `…/marbleWall.jpg` |
| 10 | `eTeks#oldWoodenFloor` | Old wooden floor | Floor | 26.9 × 26.9 | `…/oldWoodenFloor.jpg` |
| 14 | `eTeks#pavingStone` | Paving stone | Floor | 42.3 × 30 | `…/pavingStone.jpg` |
| 7 | `eTeks#pebbles` | Pebbles | Floor | 20 × 20 | `…/pebbles.jpg` |
| 4 | `eTeks#redTiles` | Red tiles | Floor | 40 × 40 | `…/redTiles.jpg` |
| 12 | `eTeks#roughcast` | Roughcast | Wall | 20 × 20 | `…/roughcast.jpg` |
| 15 | `eTeks#smallBricks` | Small bricks | Wall | 23 × 14.9 | `…/smallBricks.jpg` |
| 22 | `eTeks#smallRedBricks` | Small red bricks | Wall | 36.2 × 14.9 | `…/smallRedBricks.jpg` |
| 23 | `eTeks#smallWhiteBricks` | Small white bricks | Wall | 35.3 × 14.9 | `…/smallWhiteBricks.jpg` |
| 9 | `eTeks#stone2Wall` | Stone (variant 2) | Wall | 64.8 × 40 | `…/stone2Wall.jpg` |
| 20 | `eTeks#stone3Wall` | Stone (variant 3) | Wall | 55.3 × 35 | `…/stone3Wall.jpg` |
| 8 | `eTeks#stoneWall` | Stone (variant 1) | Wall | 76 × 35 | `…/stoneWall.jpg` |
| 5 | `eTeks#stoneTiles` | Stone tiles | Floor | 60 × 40 | `…/stoneTiles.jpg` |
| 24 | `eTeks#veryCloudy` | Very cloudy | Sky | 100 × 44.8 | `…/veryCloudy.jpg` |
| 19 | `eTeks#wallBeigeTile` | Beige tiles | Wall | 20 × 31.5 | `…/wallBeigeTile.jpg` |
| 1 | `eTeks#woodenFloor` | Wooden floor | Floor | 42.5 × 42.5 | `…/woodenFloor.jpg` |

All image paths are prefixed with `/com/eteks/sweethome3d/io/resources/textures/` — the
`…` in the table above abbreviates that prefix. All textures are created by `eTeks`
and have `fittingArea=false` (tiling/repeating mode).

---

## Sanity Check Results

- **Total textures found**: 26 (below the 50+ typical for plugin catalogs, but this is
  the minimal *default* catalog bundled with the application; third-party plugin catalogs
  add hundreds more)
- `eTeks#brick` — NOT present (closest: `eTeks#smallBricks`, `eTeks#smallRedBricks`)
- `eTeks#wood` — NOT present (closest: `eTeks#woodenFloor`, `eTeks#oldWoodenFloor`)
- `eTeks#tiles` — NOT present (multiple specific tile IDs available)
- `eTeks#brickWallTexture` — NOT present (this is a fictional example ID)
- All 26 entries have valid image paths pointing to `.jpg` files inside the JAR
- No `fittingArea=true` entries exist in this catalog (all tile/repeat)
- No `multiPartTexturesUUID` or `version` per-texture fields in this catalog
