# Home.xml Schema Reference — Sweet Home 3D 7.5

**Schema version**: 7400 (written by SH3D 7.x into `<home version="7400"/>`).  
**Source authority**: `com/eteks/sweethome3d/io/HomeXMLHandler.java` (DTD embedded in Javadoc) and `HomeXMLExporter.java` from the SH3D 7.5 source tree.  
**Python model**: `cli_anything/sweethome3d/core/model.py`

---

## 1. Overview

### File format

A `.sh3d` file is a ZIP archive. The primary entry is `Home.xml` (and optionally a legacy `Home` binary entry). All textures, models, icons, and background images are stored as additional ZIP entries referenced by integer names (e.g. `"0"`, `"1"`, …).

### Coordinate system

| Axis | Direction | Unit |
|------|-----------|------|
| X    | Right (east) | centimetres (cm) |
| Y    | Down (south) | centimetres (cm) |
| Z    | Up          | centimetres (cm) |

Origin is the top-left corner of the plan view. Angles are in **radians** unless noted.

### Root structure (abbreviated)

```xml
<?xml version='1.0'?>
<home version="7400" name="..." camera="observerCamera" wallHeight="250.0">
  <property …/>*
  <furnitureVisibleProperty …/>*
  <environment …/>?
  <backgroundImage …/>?
  <print …/>?
  <compass …/>
  <observerCamera …/>
  <camera attribute="topCamera" …/>
  <camera attribute="storedCamera" …/>*
  <level …/>*
  <!-- furniture: pieceOfFurniture | doorOrWindow | furnitureGroup | light -->
  <wall …/>*
  <room …/>*
  <polyline …/>*
  <dimensionLine …/>*
  <label …/>*
</home>
```

---

## 2. Elements

### 2.1 `<home>` — Root element

**Description**: Root container. Every Home.xml document has exactly one `<home>` element. Stores global settings (active camera, wall height, sort state) and contains all home objects as direct children.

**Python model**: `Home`

**Children**:

| Child | Cardinality |
|-------|-------------|
| `property` | 0..n |
| `furnitureVisibleProperty` | 0..n |
| `environment` | 0..1 |
| `backgroundImage` | 0..1 |
| `print` | 0..1 |
| `compass` | 0..1 |
| `camera` (topCamera/storedCamera) | 0..n |
| `observerCamera` | 0..1 |
| `level` | 0..n |
| `pieceOfFurniture` | 0..n |
| `doorOrWindow` | 0..n |
| `furnitureGroup` | 0..n |
| `light` | 0..n |
| `wall` | 0..n |
| `room` | 0..n |
| `polyline` | 0..n |
| `dimensionLine` | 0..n |
| `label` | 0..n |

**Attributes**:

| Name | Type | Default | Required | Description | Units | model.py field |
|------|------|---------|----------|-------------|-------|----------------|
| `version` | CDATA (int) | — | no | Schema version; SH3D 7.5 writes `7400` | — | `Home.version` |
| `name` | CDATA | — | no | File name / project name shown in title bar | — | `Home.name` |
| `camera` | `observerCamera\|topCamera` | `topCamera` | no | Which camera is currently active | — | `Home.camera` |
| `selectedLevel` | IDREF | — | no | ID of the currently selected level | — | `Home.selectedLevel` |
| `wallHeight` | CDATA (float) | — | no | Default wall height for new walls | cm | `Home.wallHeight` |
| `basePlanLocked` | `false\|true` | `false` | no | Whether the base plan is locked (furniture-only editing) | — | `Home.basePlanLocked` |
| `furnitureSortedProperty` | CDATA | — | no | Name of the furniture column currently sorted | — | `Home.furnitureSortedProperty` |
| `furnitureDescendingSorted` | `false\|true` | `false` | no | Sort order of the furniture list | — | `Home.furnitureDescendingSorted` |

**Example**:

```xml
<home version="7400" name="bungalow.sh3d" camera="observerCamera"
      selectedLevel="b833f5de77d1" wallHeight="250.0"
      basePlanLocked="false">
```

---

### 2.2 `<property>` — Key/value metadata

**Description**: Arbitrary string or content property attached to a `<home>` or any other HomeObject-derived element. SH3D uses this to persist UI state (panel sizes, viewport positions) and plugin data.

**Python model**: stored in `Home` as opaque dict; not a dedicated dataclass

**Children**: none (EMPTY)

**Attributes**:

| Name | Type | Default | Required | Description | Units | model.py field |
|------|------|---------|----------|-------------|-------|----------------|
| `name` | CDATA | — | **yes** | Property key (often a fully qualified class name) | — | MISSING — no structured storage |
| `value` | CDATA | — | **yes** | Property value string, or ZIP-entry name if `type=CONTENT` | — | MISSING |
| `type` | `STRING\|CONTENT` | `STRING` | no | Discriminates string vs binary-content values | — | MISSING |

**Example**:

```xml
<property name="com.eteks.sweethome3d.SweetHome3D.FrameWidth" value="1329"/>
<property name="myPlugin.logo" value="42" type="CONTENT"/>
```

---

### 2.3 `<furnitureVisibleProperty>` — Furniture column visibility

**Description**: One element per visible column in the furniture list panel. Order defines column order.

**Python model**: `Home.furnitureSortedProperty` stores the sorted column; visible columns list is **MISSING**

**Children**: none (EMPTY)

**Attributes**:

| Name | Type | Default | Required | Description | Units | model.py field |
|------|------|---------|----------|-------------|-------|----------------|
| `name` | CDATA | — | **yes** | Column identifier: `NAME`, `WIDTH`, `DEPTH`, `HEIGHT`, `VISIBLE`, `MOVABLE`, `ANGLE`, `COLOR`, `TEXTURE`, `ELEVATION`, `LEVEL` | — | **MISSING** |

**Example**:

```xml
<furnitureVisibleProperty name="NAME"/>
<furnitureVisibleProperty name="WIDTH"/>
<furnitureVisibleProperty name="HEIGHT"/>
<furnitureVisibleProperty name="VISIBLE"/>
```

---

### 2.4 `<environment>` — Rendering environment

**Description**: Stores sky/ground colours, ambient light, transparency of walls in plan view, and photo/video rendering settings.

**Python model**: `Environment`

**Children**:

| Child | Cardinality | Description |
|-------|-------------|-------------|
| `property` | 0..n | Extended properties |
| `camera` / `observerCamera` | 0..n | `attribute="cameraPath"` cameras for video fly-through |
| `texture` (groundTexture) | 0..1 | Ground texture (`attribute="groundTexture"`) |
| `texture` (skyTexture) | 0..1 | Sky texture (`attribute="skyTexture"`) |

**Attributes**:

| Name | Type | Default | Required | Description | Units | model.py field |
|------|------|---------|----------|-------------|-------|----------------|
| `groundColor` | CDATA (RRGGBB hex) | — | no | Ground plane colour | — | `Environment.groundColor` |
| `backgroundImageVisibleOnGround3D` | `false\|true` | `false` | no | Show background image projected on the 3D ground | — | **MISSING** |
| `skyColor` | CDATA (RRGGBB hex) | — | no | Sky colour | — | `Environment.skyColor` |
| `lightColor` | CDATA (RRGGBB hex) | — | no | Ambient sunlight colour | — | `Environment.lightColor` |
| `wallsAlpha` | CDATA (float 0–1) | `0` | no | Transparency of walls in 3D view | — | `Environment.wallsAlpha` |
| `allLevelsVisible` | `false\|true` | `false` | no | Show all levels simultaneously in 3D | — | `Environment.allLevelsVisible` |
| `observerCameraElevationAdjusted` | `false\|true` | `true` | no | Auto-adjust observer camera elevation when moving between levels | — | `Environment.observerCameraElevationAdjusted` |
| `ceillingLightColor` | CDATA (RRGGBB hex) | — | no | Ceiling light colour (note: SH3D typo — double-l) | — | `Environment.ceilingLightColor` |
| `drawingMode` | `FILL\|OUTLINE\|FILL_AND_OUTLINE` | `FILL` | no | How surfaces are drawn in 3D | — | `Environment.drawingMode` |
| `subpartSizeUnderLight` | CDATA (float) | `0` | no | Max subpart size for accurate lighting; 0 = disabled | cm | `Environment.subpartSizeUnderLight` |
| `photoWidth` | CDATA (int) | `400` | no | Rendered photo width | px | `Environment.photoWidth` |
| `photoHeight` | CDATA (int) | `300` | no | Rendered photo height | px | `Environment.photoHeight` |
| `photoAspectRatio` | enum (see below) | `VIEW_3D_RATIO` | no | Photo aspect ratio mode | — | `Environment.photoAspectRatio` |
| `photoQuality` | CDATA (int 0–3) | `0` | no | Rendering quality level (0=fast … 3=best) | — | `Environment.photoQuality` |
| `videoWidth` | CDATA (int) | `320` | no | Video frame width | px | `Environment.videoWidth` |
| `videoAspectRatio` | `RATIO_4_3\|RATIO_16_9\|RATIO_24_10` | `RATIO_4_3` | no | Video aspect ratio | — | `Environment.videoAspectRatio` |
| `videoQuality` | CDATA (int 0–3) | `0` | no | Video rendering quality | — | `Environment.videoQuality` |
| `videoSpeed` | CDATA (float) | `240.0/3600` | no | Camera travel speed | cm/s | `Environment.videoSpeed` |
| `videoFrameRate` | CDATA (int) | `25` | no | Video frames per second | fps | `Environment.videoFrameRate` |

`photoAspectRatio` values: `FREE_RATIO | VIEW_3D_RATIO | RATIO_4_3 | RATIO_3_2 | RATIO_16_9 | RATIO_2_1 | RATIO_24_10 | SQUARE_RATIO`

**Example**:

```xml
<environment groundColor="FF7CFC00" skyColor="FF87CEEB" lightColor="FFFFE0B0"
             ceillingLightColor="00D0D0D0" wallsAlpha="0"
             drawingMode="FILL" allLevelsVisible="false"
             photoWidth="1920" photoHeight="1075"
             photoAspectRatio="VIEW_3D_RATIO" photoQuality="2"
             videoWidth="320" videoAspectRatio="RATIO_4_3"
             videoQuality="0" videoSpeed="240.0" videoFrameRate="25">
  <texture attribute="groundTexture" name="Grass" width="200" height="200" image="3"/>
</environment>
```

---

### 2.5 `<backgroundImage>` — Floor-plan overlay image

**Description**: A raster image overlaid on the plan view as a reference floor plan. Can appear as a direct child of `<home>` (home-level) or as a child of `<level>` (per-level). Scale is calibrated by two points in image-pixel coordinates that correspond to a known real distance.

**Python model**: `BackgroundImage`

**Children**: none (EMPTY)

**Attributes**:

| Name | Type | Default | Required | Description | Units | model.py field |
|------|------|---------|----------|-------------|-------|----------------|
| `image` | CDATA | — | **yes** | ZIP entry name of the image file | — | `BackgroundImage.image` |
| `scaleDistance` | CDATA (float) | — | **yes** | Real-world distance the calibration line represents | cm | `BackgroundImage.scaleDistance` |
| `scaleDistanceXStart` | CDATA (float) | — | **yes** | X of calibration line start in image pixels | px | `BackgroundImage.scaleDistanceXStart` |
| `scaleDistanceYStart` | CDATA (float) | — | **yes** | Y of calibration line start in image pixels | px | `BackgroundImage.scaleDistanceYStart` |
| `scaleDistanceXEnd` | CDATA (float) | — | **yes** | X of calibration line end in image pixels | px | `BackgroundImage.scaleDistanceXEnd` |
| `scaleDistanceYEnd` | CDATA (float) | — | **yes** | Y of calibration line end in image pixels | px | `BackgroundImage.scaleDistanceYEnd` |
| `xOrigin` | CDATA (float) | `0` | no | Image origin offset X | px | `BackgroundImage.xOrigin` |
| `yOrigin` | CDATA (float) | `0` | no | Image origin offset Y | px | `BackgroundImage.yOrigin` |
| `visible` | `false\|true` | `true` | no | Whether the background image is visible | — | `BackgroundImage.visible` |

**Example**:

```xml
<backgroundImage image="0"
                 scaleDistance="1000.0"
                 scaleDistanceXStart="10.5" scaleDistanceYStart="10.5"
                 scaleDistanceXEnd="210.5" scaleDistanceYEnd="10.5"
                 xOrigin="0" yOrigin="0" visible="true"/>
```

---

### 2.6 `<print>` — Print settings

**Description**: Page layout and print options. Child `<printedLevel>` elements list which levels are included in the printout.

**Python model**: **MISSING** — no `Print` dataclass

**Children**:

| Child | Cardinality |
|-------|-------------|
| `printedLevel` | 0..n |

**Attributes**:

| Name | Type | Default | Required | Description | Units | model.py field |
|------|------|---------|----------|-------------|-------|----------------|
| `headerFormat` | CDATA | — | no | Header text format string | — | **MISSING** |
| `footerFormat` | CDATA | — | no | Footer text format string | — | **MISSING** |
| `planScale` | CDATA (float) | — | no | Scale used to print the plan (e.g. `0.01` = 1:100) | — | **MISSING** |
| `furniturePrinted` | `false\|true` | `true` | no | Include furniture list in print | — | **MISSING** |
| `planPrinted` | `false\|true` | `true` | no | Include plan view in print | — | **MISSING** |
| `view3DPrinted` | `false\|true` | `true` | no | Include 3D view in print | — | **MISSING** |
| `paperWidth` | CDATA (float) | — | **yes** | Paper width | mm | **MISSING** |
| `paperHeight` | CDATA (float) | — | **yes** | Paper height | mm | **MISSING** |
| `paperTopMargin` | CDATA (float) | — | **yes** | Top margin | mm | **MISSING** |
| `paperLeftMargin` | CDATA (float) | — | **yes** | Left margin | mm | **MISSING** |
| `paperBottomMargin` | CDATA (float) | — | **yes** | Bottom margin | mm | **MISSING** |
| `paperRightMargin` | CDATA (float) | — | **yes** | Right margin | mm | **MISSING** |
| `paperOrientation` | `PORTRAIT\|LANDSCAPE\|REVERSE_LANDSCAPE` | — | **yes** | Paper orientation | — | **MISSING** |

#### 2.6.1 `<printedLevel>`

**Attributes**:

| Name | Type | Default | Required | Description | Units | model.py field |
|------|------|---------|----------|-------------|-------|----------------|
| `level` | ID | — | **yes** | ID of the level to include in the printout | — | **MISSING** |

**Example**:

```xml
<print headerFormat="{name}" footerFormat="Page {page}"
      furniturePrinted="true" planPrinted="true" view3DPrinted="false"
      planScale="0.01"
      paperWidth="210" paperHeight="297"
      paperTopMargin="10" paperLeftMargin="10"
      paperBottomMargin="10" paperRightMargin="10"
      paperOrientation="PORTRAIT">
  <printedLevel level="460c9bfcf066"/>
</print>
```

---

### 2.7 `<compass>` — Compass rose

**Description**: The compass overlay shown in the plan view. Also stores geographic location (latitude/longitude/timezone) used for sun-position calculations.

**Python model**: `Compass`

**Children**:

| Child | Cardinality |
|-------|-------------|
| `property` | 0..n |

**Attributes**:

| Name | Type | Default | Required | Description | Units | model.py field |
|------|------|---------|----------|-------------|-------|----------------|
| `x` | CDATA (float) | — | **yes** | Centre X position in the plan | cm | `Compass.x` |
| `y` | CDATA (float) | — | **yes** | Centre Y position in the plan | cm | `Compass.y` |
| `diameter` | CDATA (float) | — | **yes** | Compass rose diameter | cm | `Compass.diameter` |
| `northDirection` | CDATA (float) | `0` | no | Clockwise angle from plan-up to geographic north | rad | `Compass.northDirection` |
| `longitude` | CDATA (float) | — | no | Geographic longitude | rad | `Compass.longitude` |
| `latitude` | CDATA (float) | — | no | Geographic latitude | rad | `Compass.latitude` |
| `timeZone` | CDATA | — | no | Java timezone ID (e.g. `Europe/London`) | — | `Compass.timeZone` |
| `visible` | `false\|true` | `true` | no | Whether compass is visible in plan | — | `Compass.visible` |

**Example**:

```xml
<compass x="50.0" y="50.0" diameter="100.0"
         northDirection="0.0"
         longitude="-0.0020362234" latitude="0.89884454"
         timeZone="Europe/London"/>
```

---

### 2.8 `<observerCamera>` — First-person (observer) camera

**Description**: The observer (first-person, eye-level) camera. There is exactly one per file. The XML element name is always `observerCamera` and the `attribute` attribute is also `"observerCamera"` (or `"storedCamera"` for saved viewpoints, or `"cameraPath"` for video path keyframes).

**Python model**: `Camera` (with `kind="observerCamera"`)

**Children**:

| Child | Cardinality |
|-------|-------------|
| `property` | 0..n |

**Attributes**:

| Name | Type | Default | Required | Description | Units | model.py field |
|------|------|---------|----------|-------------|-------|----------------|
| `attribute` | `observerCamera\|storedCamera\|cameraPath` | — | **yes** | Role of this camera instance | — | `Camera.kind` |
| `id` | ID | — | no | Unique ID (only for storedCamera/cameraPath instances) | — | `Camera.id` |
| `name` | CDATA | — | no | Human-readable name (for stored cameras) | — | `Camera.name` |
| `lens` | `PINHOLE\|NORMAL\|FISHEYE\|SPHERICAL` | `PINHOLE` | no | Lens type | — | `Camera.lens` |
| `x` | CDATA (float) | — | **yes** | Camera X position | cm | `Camera.x` |
| `y` | CDATA (float) | — | **yes** | Camera Y position | cm | `Camera.y` |
| `z` | CDATA (float) | — | **yes** | Camera Z elevation | cm | `Camera.z` |
| `yaw` | CDATA (float) | — | **yes** | Horizontal rotation (0 = north, clockwise) | rad | `Camera.yaw` |
| `pitch` | CDATA (float) | — | **yes** | Vertical tilt (negative = look up, positive = look down) | rad | `Camera.pitch` |
| `fieldOfView` | CDATA (float) | — | **yes** | Horizontal field of view | rad | `Camera.fieldOfView` |
| `time` | CDATA (long) | — | no | Sun-position timestamp (ms since Unix epoch) | ms | `Camera.time` |
| `fixedSize` | `false\|true` | `false` | no | Whether camera avatar stays fixed size in plan view | — | `Camera.fixedSize` |
| `renderer` | CDATA | — | no | Renderer class name (e.g. `com.eteks.sweethome3d.j3d.YafarayRenderer`) | — | `Camera.renderer` |

**Example**:

```xml
<observerCamera attribute="observerCamera" lens="PINHOLE"
                x="532.0" y="994.0" z="170.0"
                yaw="3.5770922" pitch="0.0" fieldOfView="1.0472"
                time="1778760000000"
                renderer="com.eteks.sweethome3d.j3d.YafarayRenderer"/>
```

---

### 2.9 `<camera>` — Top-down or stored camera

**Description**: Used for both the top-down (plan) camera (`attribute="topCamera"`) and any number of user-saved viewpoints (`attribute="storedCamera"`) or video path keyframes (`attribute="cameraPath"`). Shares the same attribute set as `<observerCamera>` except there is no `fixedSize`.

**Python model**: `Camera` (with `kind="topCamera"` or `kind="storedCamera"`)

**Children**: same as `<observerCamera>` (property*)

**Attributes**: Same as `<observerCamera>` except:
- `attribute` values: `topCamera | storedCamera | cameraPath`
- No `fixedSize` attribute

| Name | Type | Default | Required | Description | Units | model.py field |
|------|------|---------|----------|-------------|-------|----------------|
| `attribute` | `topCamera\|storedCamera\|cameraPath` | — | **yes** | Camera role | — | `Camera.kind` |
| `id` | ID | — | no | Unique ID for storedCamera | — | `Camera.id` |
| `name` | CDATA | — | no | Human-readable name | — | `Camera.name` |
| `lens` | `PINHOLE\|NORMAL\|FISHEYE\|SPHERICAL` | `PINHOLE` | no | Lens type | — | `Camera.lens` |
| `x` | CDATA (float) | — | **yes** | Camera X | cm | `Camera.x` |
| `y` | CDATA (float) | — | **yes** | Camera Y | cm | `Camera.y` |
| `z` | CDATA (float) | — | **yes** | Camera Z elevation | cm | `Camera.z` |
| `yaw` | CDATA (float) | — | **yes** | Horizontal rotation | rad | `Camera.yaw` |
| `pitch` | CDATA (float) | — | **yes** | Vertical tilt | rad | `Camera.pitch` |
| `fieldOfView` | CDATA (float) | — | **yes** | Horizontal FOV | rad | `Camera.fieldOfView` |
| `time` | CDATA (long) | — | no | Sun-position timestamp | ms | `Camera.time` |
| `renderer` | CDATA | — | no | Renderer class | — | `Camera.renderer` |

**Example**:

```xml
<!-- Top-down camera -->
<camera attribute="topCamera" lens="PINHOLE"
        x="750.0" y="500.0" z="1500.0"
        yaw="0.0" pitch="1.5708" fieldOfView="0.78"
        time="1778760000000"/>

<!-- Stored viewpoint -->
<camera attribute="storedCamera" id="abc123"
        name="Kitchen view" lens="PINHOLE"
        x="400.0" y="600.0" z="160.0"
        yaw="2.1" pitch="-0.1" fieldOfView="1.0472"/>
```

---

### 2.10 `<cameraPath>` — Video camera path keyframe

**Description**: Not a separate element — video path keyframes are `<camera>` or `<observerCamera>` elements with `attribute="cameraPath"` inside `<environment>`. They form an ordered list of waypoints for the video fly-through animation.

**Python model**: `Camera` instances in `Environment` — **MISSING** (Environment has no `videoCameraPath` list)

See `<camera>` for attributes. No additional attributes.

**Example**:

```xml
<environment …>
  <camera attribute="cameraPath" lens="PINHOLE"
          x="100" y="100" z="170" yaw="0" pitch="0" fieldOfView="1.0472"
          time="1700000000000"/>
  <camera attribute="cameraPath" lens="PINHOLE"
          x="500" y="100" z="170" yaw="1.57" pitch="0" fieldOfView="1.0472"
          time="1700000000000"/>
</environment>
```

---

### 2.11 `<level>` — Building level (storey)

**Description**: Represents one storey of a multi-level building. All placeable elements (walls, rooms, furniture, etc.) reference a level by ID via their `level` attribute. A home may have zero levels (single-level mode) or many.

**Python model**: `Level`

**Children**:

| Child | Cardinality |
|-------|-------------|
| `property` | 0..n |
| `backgroundImage` | 0..1 |

**Attributes**:

| Name | Type | Default | Required | Description | Units | model.py field |
|------|------|---------|----------|-------------|-------|----------------|
| `id` | ID | — | **yes** | Unique identifier referenced by other elements | — | `Level.id` |
| `name` | CDATA | — | **yes** | Display name (e.g. `"Ground Floor"`) | — | `Level.name` |
| `elevation` | CDATA (float) | — | **yes** | Bottom of this level relative to building base | cm | `Level.elevation` |
| `floorThickness` | CDATA (float) | — | **yes** | Floor slab thickness | cm | `Level.floorThickness` |
| `height` | CDATA (float) | — | **yes** | Floor-to-floor height (ceiling height) | cm | `Level.height` |
| `elevationIndex` | CDATA (int) | `-1` | no | Order index used for display stacking | — | `Level.elevationIndex` |
| `visible` | `false\|true` | `true` | no | Whether level is visible in plan and 3D | — | `Level.visible` |
| `viewable` | `false\|true` | `true` | no | Whether level can be individually selected/viewed | — | `Level.viewable` |

**Example**:

```xml
<level id="460c9bfcf066" name="Ground Floor"
       elevation="0" floorThickness="12" height="240"
       elevationIndex="0" visible="true" viewable="true"/>

<level id="31489ff4a8ed" name="First Floor"
       elevation="252" floorThickness="12" height="240"
       elevationIndex="1" visible="true" viewable="true"/>
```

---

### 2.12 `<pieceOfFurniture>` — Generic furniture

**Description**: A placed furniture instance (not a door/window or light). References a catalog item via `catalogId` or provides embedded geometry via `model`/`icon`.

**Python model**: `PieceOfFurniture` (with `kind="pieceOfFurniture"`)

**Children**:

| Child | Cardinality |
|-------|-------------|
| `property` | 0..n |
| `textStyle` (nameStyle) | 0..1 |
| `texture` | 0..1 |
| `material` | 0..n |
| `transformation` | 0..n |

**Attributes** (furniture common + piece common + horizontal rotation attributes):

| Name | Type | Default | Required | Description | Units | model.py field |
|------|------|---------|----------|-------------|-------|----------------|
| `id` | ID | — | no | Unique identifier | — | `PieceOfFurniture.id` |
| `level` | IDREF | — | no | Level ID this piece belongs to | — | `PieceOfFurniture.level` |
| `catalogId` | CDATA | — | no | Catalog item identifier (e.g. `eTeks#stairs`) | — | `PieceOfFurniture.catalogId` |
| `name` | CDATA | — | **yes** | Display name | — | `PieceOfFurniture.name` |
| `creator` | CDATA | — | no | Author of the furniture model | — | `PieceOfFurniture.creator` |
| `model` | CDATA | — | no | ZIP entry name of the 3D model file | — | `PieceOfFurniture.model` |
| `icon` | CDATA | — | no | ZIP entry name of the catalog icon | — | `PieceOfFurniture.icon` |
| `planIcon` | CDATA | — | no | ZIP entry name of the plan-view icon | — | **MISSING** |
| `x` | CDATA (float) | — | **yes** | Centre X | cm | `PieceOfFurniture.x` |
| `y` | CDATA (float) | — | **yes** | Centre Y | cm | `PieceOfFurniture.y` |
| `elevation` | CDATA (float) | `0` | no | Bottom elevation above level floor | cm | `PieceOfFurniture.elevation` |
| `angle` | CDATA (float) | `0` | no | Rotation around vertical Z axis | rad | `PieceOfFurniture.angle` |
| `pitch` | CDATA (float) | `0` | no | Rotation around horizontal X axis | rad | `PieceOfFurniture.pitch` |
| `roll` | CDATA (float) | `0` | no | Rotation around horizontal Y axis | rad | `PieceOfFurniture.roll` |
| `width` | CDATA (float) | — | **yes** | Model bounding-box width (X extent) | cm | `PieceOfFurniture.width` |
| `depth` | CDATA (float) | — | **yes** | Model bounding-box depth (Y extent) | cm | `PieceOfFurniture.depth` |
| `height` | CDATA (float) | — | **yes** | Model bounding-box height (Z extent) | cm | `PieceOfFurniture.height` |
| `widthInPlan` | CDATA (float) | `=width` | no | Override width for plan-view display | cm | **MISSING** |
| `depthInPlan` | CDATA (float) | `=depth` | no | Override depth for plan-view display | cm | **MISSING** |
| `heightInPlan` | CDATA (float) | `=height` | no | Override height for plan-view display | cm | **MISSING** |
| `modelFlags` | CDATA (int) | `0` | no | Bitfield: 1=backFaceShown | — | **MISSING** |
| `modelMirrored` | `false\|true` | `false` | no | Mirror the model along its width axis | — | **MISSING** |
| `modelRotation` | CDATA (9 floats) | `1 0 0 0 1 0 0 0 1` | no | 3×3 rotation matrix (row-major) applied before placing | — | **MISSING** |
| `modelCenteredAtOrigin` | `false\|true` | implicit true | no | Whether model origin is centred | — | **MISSING** |
| `modelSize` | CDATA (long) | — | no | Original file size hint (bytes); `-1` = unknown | bytes | **MISSING** |
| `visible` | `false\|true` | `true` | no | Visibility | — | `PieceOfFurniture.visible` |
| `movable` | `false\|true` | `true` | no | Whether user can move this piece | — | `PieceOfFurniture.movable` |
| `color` | CDATA (AARRGGBB hex) | — | no | Tint colour applied to model | — | `PieceOfFurniture.color` |
| `shininess` | CDATA (float 0–1) | — | no | Specular shininess | — | `PieceOfFurniture.shininess` |
| `description` | CDATA | — | no | Free-text description | — | `PieceOfFurniture.description` |
| `information` | CDATA | — | no | Additional info (URL etc.) | — | **MISSING** |
| `license` | CDATA | — | no | License text | — | **MISSING** |
| `nameVisible` | `false\|true` | `false` | no | Show name label in plan | — | `PieceOfFurniture.nameVisible` |
| `nameAngle` | CDATA (float) | `0` | no | Name label rotation | rad | **MISSING** |
| `nameXOffset` | CDATA (float) | `0` | no | Name label X offset from centre | cm | **MISSING** |
| `nameYOffset` | CDATA (float) | `0` | no | Name label Y offset from centre | cm | **MISSING** |
| `doorOrWindow` | `false\|true` | `false` | no | Whether this piece behaves as a door/window (cuts walls) | — | **MISSING** |
| `horizontallyRotatable` | `false\|true` | `true` | no | Whether pitch/roll can be set | — | **MISSING** |
| `resizable` | `false\|true` | `true` | no | Whether dimensions can be changed | — | **MISSING** |
| `deformable` | `false\|true` | `true` | no | Whether width/depth/height can be set independently | — | **MISSING** |
| `texturable` | `false\|true` | `true` | no | Whether texture can be applied | — | **MISSING** |
| `staircaseCutOutShape` | CDATA | — | no | SVG path string defining the staircase cut-out | — | **MISSING** |
| `dropOnTopElevation` | CDATA (float 0–1) | `1` | no | Relative elevation for dropping objects on top | — | **MISSING** |
| `price` | CDATA (decimal) | — | no | Unit price | currency | **MISSING** |
| `valueAddedTaxPercentage` | CDATA (decimal) | — | no | VAT percentage | % | **MISSING** |
| `currency` | CDATA | — | no | ISO 4217 currency code | — | **MISSING** |

**Example**:

```xml
<pieceOfFurniture id="9587229af95c" level="460c9bfcf066"
    catalogId="eTeks#stairs" name="Stairs"
    x="100" y="245" elevation="0" angle="0" pitch="0" roll="0"
    width="90" depth="300" height="250" shininess="0"/>
```

---

### 2.13 `<doorOrWindow>` — Door or window

**Description**: A furniture piece that cuts an opening in the host wall. Inherits all furniture common attributes and piece-of-furniture attributes (but not the horizontal-rotation group — doors/windows are always upright). Adds door/window specific wall-cut geometry.

**Python model**: `PieceOfFurniture` (with `kind="doorOrWindow"`)

**Children**:

| Child | Cardinality |
|-------|-------------|
| `sash` | 0..n |
| `property` | 0..n |
| `textStyle` (nameStyle) | 0..1 |
| `texture` | 0..1 |
| `material` | 0..n |
| `transformation` | 0..n |

**Attributes**: All furniture-common + piece-common attributes (see `<pieceOfFurniture>`) **plus**:

| Name | Type | Default | Required | Description | Units | model.py field |
|------|------|---------|----------|-------------|-------|----------------|
| `wallThickness` | CDATA (float) | `1` | no | Fraction of `depth` that the wall cut spans (1 = full depth) | fraction | `PieceOfFurniture.wallThickness` |
| `wallDistance` | CDATA (float) | `0` | no | Offset from the front face of the wall to the opening | fraction | `PieceOfFurniture.wallDistance` |
| `wallWidth` | CDATA (float) | `1` | no | Fraction of `width` that the wall opening spans | fraction | `PieceOfFurniture.wallWidth` |
| `wallLeft` | CDATA (float) | `0` | no | Fraction of `width` offset from the left edge to the opening | fraction | `PieceOfFurniture.wallLeft` |
| `wallHeight` | CDATA (float) | `1` | no | Fraction of `height` that the wall cut spans | fraction | `PieceOfFurniture.wallHeight` |
| `wallTop` | CDATA (float) | `0` | no | Fraction of `height` offset from the top of the wall | fraction | `PieceOfFurniture.wallTop` |
| `wallCutOutOnBothSides` | `false\|true` | `false` | no | Cut through both sides of the wall (double-sided opening) | — | **MISSING** |
| `widthDepthDeformable` | `false\|true` | `true` | no | Whether width/depth can be resized independently | — | **MISSING** |
| `cutOutShape` | CDATA | — | no | SVG path defining the wall cut shape (unit coords 0–1) | — | `PieceOfFurniture.cutOutShape` |
| `boundToWall` | `false\|true` | `true` | no | Whether the door/window snaps to and follows the host wall | — | `PieceOfFurniture.boundToWall` |

**Example**:

```xml
<doorOrWindow id="5ad163895cd4" level="460c9bfcf066"
    catalogId="eTeks#doorFrame" name="Front Door"
    x="100" y="0" elevation="0" angle="0" pitch="0" roll="0"
    width="90" depth="10" height="200" shininess="0"
    wallThickness="1" cutOutShape="M0,0 v1 h1 v-1 z"/>
```

---

### 2.14 `<light>` — Light source furniture

**Description**: A furniture piece that emits light. Inherits all furniture common + piece + horizontal-rotation attributes. Adds `power` and child `<lightSource>` / `<lightSourceMaterial>` elements.

**Python model**: `PieceOfFurniture` (with `kind="light"`)

**Children**:

| Child | Cardinality |
|-------|-------------|
| `lightSource` | 0..n |
| `lightSourceMaterial` | 0..n |
| `property` | 0..n |
| `textStyle` (nameStyle) | 0..1 |
| `texture` | 0..1 |
| `material` | 0..n |
| `transformation` | 0..n |

**Additional attribute** (all furniture-common + piece-common + horizontal-rotation apply too):

| Name | Type | Default | Required | Description | Units | model.py field |
|------|------|---------|----------|-------------|-------|----------------|
| `power` | CDATA (float 0–1) | `0.5` | no | Light intensity (0 = off, 1 = full) | — | `PieceOfFurniture.power` |

**Example**:

```xml
<light id="ce7d4058e972" level="b833f5de77d1"
    catalogId="eTeks#ceilingLight" name="Lounge Light"
    x="250.0" y="150.0" elevation="220.0"
    width="20.0" depth="20.0" height="20.0"
    color="FFFFFFE0" shininess="0.0" power="0.7"/>
```

---

### 2.15 `<furnitureGroup>` — Furniture group

**Description**: A named group of furniture pieces that can be moved, rotated, and resized as a unit. Children are other furniture elements. Position/size may be derived from children if not set explicitly.

**Python model**: **MISSING** — no `FurnitureGroup` dataclass

**Children**:

| Child | Cardinality |
|-------|-------------|
| `pieceOfFurniture` | 0..n |
| `doorOrWindow` | 0..n |
| `furnitureGroup` | 0..n (nested) |
| `light` | 0..n |
| `property` | 0..n |
| `textStyle` | 0..1 |

**Attributes** (furniture-common applies; **no** piece-common or horizontal-rotation):

| Name | Type | Default | Required | Description | Units | model.py field |
|------|------|---------|----------|-------------|-------|----------------|
| `id` | ID | — | no | Unique identifier | — | **MISSING** |
| `level` | IDREF | — | no | Level this group belongs to | — | **MISSING** |
| `name` | CDATA | — | **yes** | Group display name | — | **MISSING** |
| `x` | CDATA (float) | — | no | Centre X (computed from children if omitted) | cm | **MISSING** |
| `y` | CDATA (float) | — | no | Centre Y | cm | **MISSING** |
| `elevation` | CDATA (float) | — | no | Bottom elevation | cm | **MISSING** |
| `angle` | CDATA (float) | `0` | no | Rotation | rad | **MISSING** |
| `width` | CDATA (float) | — | no | Override width | cm | **MISSING** |
| `depth` | CDATA (float) | — | no | Override depth | cm | **MISSING** |
| `height` | CDATA (float) | — | no | Override height | cm | **MISSING** |
| `dropOnTopElevation` | CDATA (float) | — | no | Relative drop elevation | — | **MISSING** |
| `visible` | `false\|true` | `true` | no | Visibility | — | **MISSING** |
| `movable` | `false\|true` | `true` | no | Movable | — | **MISSING** |
| `modelMirrored` | `false\|true` | `false` | no | Mirror group | — | **MISSING** |
| `nameVisible` | `false\|true` | `false` | no | Show name label | — | **MISSING** |
| `nameAngle` | CDATA (float) | `0` | no | Name label angle | rad | **MISSING** |
| `nameXOffset` | CDATA (float) | `0` | no | Name label X offset | cm | **MISSING** |
| `nameYOffset` | CDATA (float) | `0` | no | Name label Y offset | cm | **MISSING** |
| `price` | CDATA (decimal) | — | no | Group price (ignored if any child has a price) | — | **MISSING** |
| `description` | CDATA | — | no | Description | — | **MISSING** |
| `information` | CDATA | — | no | Additional info | — | **MISSING** |
| `license` | CDATA | — | no | License | — | **MISSING** |
| `creator` | CDATA | — | no | Creator | — | **MISSING** |

**Example**:

```xml
<furnitureGroup id="grp001" level="460c9bfcf066" name="Kitchen Set"
               x="300" y="600" angle="0">
  <pieceOfFurniture name="Worktop" x="300" y="600" width="200" depth="60" height="90"/>
  <pieceOfFurniture name="Hob" x="350" y="600" width="60" depth="60" height="91"/>
</furnitureGroup>
```

---

### 2.16 `<shelfUnit>` — Shelf unit furniture

**Description**: A furniture piece with one or more shelves. Inherits furniture-common + piece-common + horizontal-rotation attributes. Adds `<shelf>` children defining shelf planes or box bounds within the unit.

**Python model**: **MISSING** — no `ShelfUnit` dataclass

**Children**:

| Child | Cardinality |
|-------|-------------|
| `shelf` | 0..n |
| `property` | 0..n |
| `textStyle` | 0..1 |
| `texture` | 0..1 |
| `material` | 0..n |
| `transformation` | 0..n |

Attributes: same as `<pieceOfFurniture>` (furniture-common + piece-common + horizontal-rotation).

#### 2.16.1 `<shelf>` — Shelf plane or bounding box

| Name | Type | Default | Required | Description | Units | model.py field |
|------|------|---------|----------|-------------|-------|----------------|
| `elevation` | CDATA (float) | — | no | Shelf height (flat shelf mode; set this OR the box bounds) | cm | **MISSING** |
| `xLower` | CDATA (float) | — | no | Box lower X | cm | **MISSING** |
| `yLower` | CDATA (float) | — | no | Box lower Y | cm | **MISSING** |
| `zLower` | CDATA (float) | — | no | Box lower Z | cm | **MISSING** |
| `xUpper` | CDATA (float) | — | no | Box upper X | cm | **MISSING** |
| `yUpper` | CDATA (float) | — | no | Box upper Y | cm | **MISSING** |
| `zUpper` | CDATA (float) | — | no | Box upper Z | cm | **MISSING** |

---

### 2.17 `<wall>` — Wall segment

**Description**: A straight or arc wall segment between two endpoints. Walls can be joined at their endpoints (via `wallAtStart`/`wallAtEnd` IDs). Textures and baseboards appear as child elements.

**Python model**: `Wall`

**Children**:

| Child | Cardinality |
|-------|-------------|
| `property` | 0..n |
| `texture` (leftSideTexture) | 0..1 |
| `texture` (rightSideTexture) | 0..1 |
| `baseboard` (leftSideBaseboard) | 0..1 |
| `baseboard` (rightSideBaseboard) | 0..1 |

**Attributes**:

| Name | Type | Default | Required | Description | Units | model.py field |
|------|------|---------|----------|-------------|-------|----------------|
| `id` | ID | — | **yes** | Unique wall ID referenced by furniture | — | `Wall.id` |
| `level` | IDREF | — | no | Level ID | — | `Wall.level` |
| `wallAtStart` | IDREF | — | no | ID of the wall joined at the start point | — | `Wall.wallAtStart` |
| `wallAtEnd` | IDREF | — | no | ID of the wall joined at the end point | — | `Wall.wallAtEnd` |
| `xStart` | CDATA (float) | — | **yes** | Start point X | cm | `Wall.xStart` |
| `yStart` | CDATA (float) | — | **yes** | Start point Y | cm | `Wall.yStart` |
| `xEnd` | CDATA (float) | — | **yes** | End point X | cm | `Wall.xEnd` |
| `yEnd` | CDATA (float) | — | **yes** | End point Y | cm | `Wall.yEnd` |
| `height` | CDATA (float) | — | no | Wall height at start (or uniform height) | cm | `Wall.height` |
| `heightAtEnd` | CDATA (float) | — | no | Wall height at end (for sloped walls); omit = same as `height` | cm | `Wall.heightAtEnd` |
| `thickness` | CDATA (float) | — | **yes** | Wall thickness | cm | `Wall.thickness` |
| `arcExtent` | CDATA (float) | — | no | Arc angle for curved walls (0 = straight) | rad | `Wall.arcExtent` |
| `pattern` | CDATA | — | no | Fill pattern name (e.g. `hatchUp`, `hatchDown`, `hatchHorizontal`) | — | `Wall.pattern` |
| `topColor` | CDATA (AARRGGBB hex) | — | no | Colour of the wall top surface | — | `Wall.topColor` |
| `leftSideColor` | CDATA (AARRGGBB hex) | — | no | Colour of the left face | — | `Wall.leftSideColor` |
| `leftSideShininess` | CDATA (float 0–1) | `0` | no | Left-face shininess | — | `Wall.leftSideShininess` |
| `rightSideColor` | CDATA (AARRGGBB hex) | — | no | Colour of the right face | — | `Wall.rightSideColor` |
| `rightSideShininess` | CDATA (float 0–1) | `0` | no | Right-face shininess | — | `Wall.rightSideShininess` |

> **Left vs right**: standing at `xStart,yStart` looking toward `xEnd,yEnd` — left side is to your left, right side to your right.

**Example**:

```xml
<wall id="c02751646128" level="b833f5de77d1"
      wallAtStart="f687f0f2603d" wallAtEnd="8dce84202437"
      xStart="0.0" yStart="0.0" xEnd="1500.0" yEnd="0.0"
      height="260.0" thickness="7.5" pattern="hatchUp"/>
```

---

### 2.18 `<baseboard>` — Wall baseboard (skirting board)

**Description**: A baseboard (skirting board) applied to one side of a wall. The `attribute` discriminates left vs. right. Appears as a child of `<wall>`.

**Python model**: **MISSING** — no `Baseboard` dataclass

**Children**:

| Child | Cardinality |
|-------|-------------|
| `texture` | 0..1 |

**Attributes**:

| Name | Type | Default | Required | Description | Units | model.py field |
|------|------|---------|----------|-------------|-------|----------------|
| `attribute` | `leftSideBaseboard\|rightSideBaseboard` | — | **yes** | Which side this baseboard is on | — | **MISSING** |
| `thickness` | CDATA (float) | — | **yes** | Baseboard thickness (protrusion from wall face) | cm | **MISSING** |
| `height` | CDATA (float) | — | **yes** | Baseboard height | cm | **MISSING** |
| `color` | CDATA (AARRGGBB hex) | — | no | Baseboard colour | — | **MISSING** |

**Example**:

```xml
<wall id="abc123" xStart="0" yStart="0" xEnd="500" yEnd="0"
      height="250" thickness="7.5">
  <baseboard attribute="leftSideBaseboard"
             thickness="2.5" height="10" color="FFFFFFFF"/>
</wall>
```

---

### 2.19 `<room>` — Floor area polygon

**Description**: A filled polygon defining a room (floor + ceiling surfaces). Points are listed in order and the polygon is closed automatically. At least 3 points required.

**Python model**: `Room`

**Children**:

| Child | Cardinality |
|-------|-------------|
| `property` | 0..n |
| `textStyle` (nameStyle) | 0..1 |
| `textStyle` (areaStyle) | 0..1 |
| `texture` (floorTexture) | 0..1 |
| `texture` (ceilingTexture) | 0..1 |
| `point` | 1..n |

**Attributes**:

| Name | Type | Default | Required | Description | Units | model.py field |
|------|------|---------|----------|-------------|-------|----------------|
| `id` | ID | — | no | Unique identifier | — | `Room.id` |
| `level` | IDREF | — | no | Level ID | — | `Room.level` |
| `name` | CDATA | — | no | Room name label | — | `Room.name` |
| `nameAngle` | CDATA (float) | `0` | no | Name label rotation | rad | `Room.nameAngle` |
| `nameXOffset` | CDATA (float) | `0` | no | Name label X offset from centroid | cm | `Room.nameXOffset` |
| `nameYOffset` | CDATA (float) | `-40` | no | Name label Y offset from centroid | cm | `Room.nameYOffset` |
| `areaVisible` | `false\|true` | `false` | no | Show computed area label | — | `Room.areaVisible` |
| `areaAngle` | CDATA (float) | `0` | no | Area label rotation | rad | **MISSING** |
| `areaXOffset` | CDATA (float) | `0` | no | Area label X offset | cm | **MISSING** |
| `areaYOffset` | CDATA (float) | `0` | no | Area label Y offset | cm | **MISSING** |
| `floorVisible` | `false\|true` | `true` | no | Render the floor surface | — | `Room.floorVisible` |
| `floorColor` | CDATA (AARRGGBB hex) | — | no | Floor colour | — | `Room.floorColor` |
| `floorShininess` | CDATA (float 0–1) | `0` | no | Floor shininess | — | `Room.floorShininess` |
| `ceilingVisible` | `false\|true` | `true` | no | Render the ceiling surface | — | `Room.ceilingVisible` |
| `ceilingColor` | CDATA (AARRGGBB hex) | — | no | Ceiling colour | — | `Room.ceilingColor` |
| `ceilingShininess` | CDATA (float 0–1) | `0` | no | Ceiling shininess | — | `Room.ceilingShininess` |
| `ceilingFlat` | `false\|true` | `false` | no | Flat ceiling (no slope following roof geometry) | — | `Room.ceilingFlat` |

**Example**:

```xml
<room id="5fa09b2544ad" level="460c9bfcf066" name="Lounge" areaVisible="true">
  <point x="200" y="0"/>
  <point x="562" y="0"/>
  <point x="562" y="550"/>
  <point x="200" y="550"/>
</room>
```

---

### 2.20 `<polyline>` — 2D/3D polyline

**Description**: An open or closed polyline used for annotations, arrows, or in-plan drawings. When `visibleIn3D` / `elevation` is set, also rendered in the 3D view.

**Python model**: `Polyline`

**Children**:

| Child | Cardinality |
|-------|-------------|
| `property` | 0..n |
| `point` | 1..n |

**Attributes**:

| Name | Type | Default | Required | Description | Units | model.py field |
|------|------|---------|----------|-------------|-------|----------------|
| `id` | ID | — | no | Unique identifier | — | `Polyline.id` |
| `level` | IDREF | — | no | Level ID | — | `Polyline.level` |
| `thickness` | CDATA (float) | `1` | no | Line width | cm | `Polyline.thickness` |
| `capStyle` | `BUTT\|SQUARE\|ROUND` | `BUTT` | no | Line end cap style | — | `Polyline.capStyle` |
| `joinStyle` | `BEVEL\|MITER\|ROUND\|CURVED` | `MITER` | no | Line join style | — | `Polyline.joinStyle` |
| `dashStyle` | `SOLID\|DOT\|DASH\|DASH_DOT\|DASH_DOT_DOT\|CUSTOMIZED` | `SOLID` | no | Dash pattern | — | `Polyline.dashStyle` |
| `dashPattern` | CDATA (space-separated floats) | — | no | Custom dash pattern (only when `dashStyle=CUSTOMIZED`) | cm | **MISSING** |
| `dashOffset` | CDATA (float) | `0` | no | Dash pattern phase offset | cm | `Polyline.dashOffset` |
| `startArrowStyle` | `NONE\|DELTA\|OPEN\|DISC` | `NONE` | no | Start-end arrow style | — | `Polyline.startArrowStyle` |
| `endArrowStyle` | `NONE\|DELTA\|OPEN\|DISC` | `NONE` | no | End-end arrow style | — | `Polyline.endArrowStyle` |
| `elevation` | CDATA (float) | — | no | Z elevation (written only when `visibleIn3D=true`) | cm | `Polyline.elevation` |
| `color` | CDATA (AARRGGBB hex) | — | no | Line colour | — | `Polyline.color` |
| `closedPath` | `false\|true` | `false` | no | Close the polyline to form a polygon | — | `Polyline.closedPath` |

**Example**:

```xml
<polyline id="pol001" level="460c9bfcf066"
          thickness="2" capStyle="ROUND" joinStyle="ROUND"
          dashStyle="DASH" color="FF0000FF" closedPath="false">
  <point x="100" y="100"/>
  <point x="300" y="100"/>
  <point x="300" y="300"/>
</polyline>
```

---

### 2.21 `<dimensionLine>` — Dimension annotation

**Description**: A dimension annotation showing the distance between two points, with an offset line perpendicular to the measurement axis.

**Python model**: `DimensionLine`

**Children**:

| Child | Cardinality |
|-------|-------------|
| `property` | 0..n |
| `textStyle` (lengthStyle) | 0..1 |

**Attributes**:

| Name | Type | Default | Required | Description | Units | model.py field |
|------|------|---------|----------|-------------|-------|----------------|
| `id` | ID | — | no | Unique identifier | — | `DimensionLine.id` |
| `level` | IDREF | — | no | Level ID | — | `DimensionLine.level` |
| `xStart` | CDATA (float) | — | **yes** | Start point X | cm | `DimensionLine.xStart` |
| `yStart` | CDATA (float) | — | **yes** | Start point Y | cm | `DimensionLine.yStart` |
| `elevationStart` | CDATA (float) | `0` | no | Start elevation (for 3D dimensions) | cm | `DimensionLine.elevationStart` |
| `xEnd` | CDATA (float) | — | **yes** | End point X | cm | `DimensionLine.xEnd` |
| `yEnd` | CDATA (float) | — | **yes** | End point Y | cm | `DimensionLine.yEnd` |
| `elevationEnd` | CDATA (float) | `0` | no | End elevation | cm | `DimensionLine.elevationEnd` |
| `offset` | CDATA (float) | — | **yes** | Perpendicular offset of the dimension line from the measured segment | cm | `DimensionLine.offset` |
| `endMarkSize` | CDATA (float) | `10` | no | Size of the end tick marks | cm | `DimensionLine.endMarkSize` |
| `pitch` | CDATA (float) | `0` | no | Tilt angle for 3D dimension lines | rad | `DimensionLine.pitch` |
| `color` | CDATA (AARRGGBB hex) | — | no | Colour | — | `DimensionLine.color` |
| `visibleIn3D` | `false\|true` | `false` | no | Whether rendered in 3D view | — | `DimensionLine.visibleIn3D` |

> Note: the DTD also lists `angle CDATA "0"` but this is not written by the exporter and is not used in the handler — it appears to be vestigial.

**Example**:

```xml
<dimensionLine id="aa456f1db4ae" level="b833f5de77d1"
               xStart="0.0" yStart="0.0" xEnd="1500.0" yEnd="0.0"
               offset="-40.0"/>
```

---

### 2.22 `<label>` — Text annotation

**Description**: A free-standing text annotation placed in the plan. Can optionally be displayed in 3D when `pitch` is set.

**Python model**: `Label`

**Children**:

| Child | Cardinality |
|-------|-------------|
| `property` | 0..n |
| `textStyle` | 0..1 |
| `text` | 1..1 |

**Attributes**:

| Name | Type | Default | Required | Description | Units | model.py field |
|------|------|---------|----------|-------------|-------|----------------|
| `id` | ID | — | no | Unique identifier | — | `Label.id` |
| `level` | IDREF | — | no | Level ID | — | `Label.level` |
| `x` | CDATA (float) | — | **yes** | Anchor X | cm | `Label.x` |
| `y` | CDATA (float) | — | **yes** | Anchor Y | cm | `Label.y` |
| `angle` | CDATA (float) | `0` | no | Rotation | rad | `Label.angle` |
| `elevation` | CDATA (float) | `0` | no | Z elevation (for 3D labels) | cm | `Label.elevation` |
| `pitch` | CDATA (float) | — | no | Vertical tilt for 3D (absent = plan only) | rad | `Label.pitch` |
| `color` | CDATA (AARRGGBB hex) | — | no | Text colour | — | `Label.color` |
| `outlineColor` | CDATA (AARRGGBB hex) | — | no | Text outline/shadow colour | — | `Label.outlineColor` |

**Example**:

```xml
<label id="lbl001" level="460c9bfcf066" x="300" y="50" angle="0">
  <textStyle fontSize="20" bold="true" alignment="CENTER"/>
  <text>Kitchen</text>
</label>
```

---

### 2.23 `<text>` — Label text content

**Description**: Wraps the PCDATA text content of a `<label>`. Always a direct child of `<label>`.

**Python model**: `Label.text` (string field)

**Children**: #PCDATA (raw text)

**Attributes**: none

**Example**:

```xml
<text>Kitchen / Dining Room</text>
```

---

### 2.24 `<texture>` — Surface texture

**Description**: References a texture image applied to a surface. Used as a child of: `<environment>` (ground/sky), `<wall>`, `<room>`, `<pieceOfFurniture>`, `<material>`, `<baseboard>`. The `attribute` discriminates the target surface.

**Python model**: `Texture`

**Children**: none (EMPTY)

**Attributes**:

| Name | Type | Default | Required | Description | Units | model.py field |
|------|------|---------|----------|-------------|-------|----------------|
| `attribute` | enum (see below) | — | no | Which surface slot this texture fills | — | implicit by parent |
| `catalogId` | CDATA | — | no | Catalog texture identifier | — | `Texture.catalogId` |
| `name` | CDATA | — | **yes** | Texture display name | — | `Texture.name` |
| `creator` | CDATA | — | no | Texture author | — | `Texture.creator` |
| `width` | CDATA (float) | — | **yes** | Real-world width of one tile | cm | `Texture.width` |
| `height` | CDATA (float) | — | **yes** | Real-world height of one tile | cm | `Texture.height` |
| `xOffset` | CDATA (float) | `0` | no | Horizontal tile offset | cm | `Texture.xOffset` |
| `yOffset` | CDATA (float) | `0` | no | Vertical tile offset | cm | `Texture.yOffset` |
| `angle` | CDATA (float) | `0` | no | Texture rotation | rad | `Texture.angle` |
| `scale` | CDATA (float) | `1` | no | Uniform scale factor | — | `Texture.scale` |
| `fittingArea` | `false\|true` | `false` | no | Stretch texture to fit the entire surface | — | `Texture.fittingArea` |
| `leftToRightOriented` | `true\|false` | `true` | no | Mirror on back face | — | **MISSING** |
| `image` | CDATA | — | **yes** | ZIP entry name of the texture image | — | `Texture.image` |

`attribute` values: `groundTexture | skyTexture | leftSideTexture | rightSideTexture | floorTexture | ceilingTexture`
(For furniture/material textures, `attribute` is omitted.)

**Example**:

```xml
<texture attribute="floorTexture"
         catalogId="eTeks#woodParquet"
         name="Light wood parquet"
         width="120" height="120"
         xOffset="0" yOffset="0" angle="0" scale="1"
         image="5"/>
```

---

### 2.25 `<material>` — Per-material override

**Description**: Overrides the colour, shininess, or texture of a named material group within a 3D model. Multiple `<material>` elements may appear inside a furniture piece.

**Python model**: **MISSING** — no `Material` dataclass

**Children**:

| Child | Cardinality |
|-------|-------------|
| `texture` | 0..1 |

**Attributes**:

| Name | Type | Default | Required | Description | Units | model.py field |
|------|------|---------|----------|-------------|-------|----------------|
| `name` | CDATA | — | **yes** | Material group name in the 3D model | — | **MISSING** |
| `key` | CDATA | — | no | Alternative key (used when materials share names) | — | **MISSING** |
| `color` | CDATA (AARRGGBB hex) | — | no | Override colour | — | **MISSING** |
| `shininess` | CDATA (float 0–1) | — | no | Override shininess | — | **MISSING** |

**Example**:

```xml
<material name="body" color="FF2244AA" shininess="0.5"/>
<material name="glass">
  <texture name="Window Glass" width="50" height="50" image="7"/>
</material>
```

---

### 2.26 `<sash>` — Door/window sash (opening leaf)

**Description**: Defines the pivot geometry for a moving door or window leaf. One `<sash>` per leaf. Parent is `<doorOrWindow>`.

**Python model**: **MISSING** — no `Sash` dataclass

**Children**: none (EMPTY)

**Attributes**:

| Name | Type | Default | Required | Description | Units | model.py field |
|------|------|---------|----------|-------------|-------|----------------|
| `xAxis` | CDATA (float) | — | **yes** | X of pivot axis (in unit coords 0–1 relative to door width) | fraction | **MISSING** |
| `yAxis` | CDATA (float) | — | **yes** | Y of pivot axis | fraction | **MISSING** |
| `width` | CDATA (float) | — | **yes** | Sash width as fraction of door width | fraction | **MISSING** |
| `startAngle` | CDATA (float) | — | **yes** | Closed position angle | rad | **MISSING** |
| `endAngle` | CDATA (float) | — | **yes** | Open position angle | rad | **MISSING** |

**Example**:

```xml
<doorOrWindow name="Door" width="80" depth="10" height="200" …>
  <sash xAxis="0" yAxis="0.5" width="1" startAngle="0" endAngle="1.5708"/>
</doorOrWindow>
```

---

### 2.27 `<lightSource>` — Point light emitter

**Description**: Defines a point light source within a `<light>` furniture piece. Position is in the model's local coordinate space (normalised 0–1 range).

**Python model**: **MISSING** — no `LightSource` dataclass

**Children**: none (EMPTY)

**Attributes**:

| Name | Type | Default | Required | Description | Units | model.py field |
|------|------|---------|----------|-------------|-------|----------------|
| `x` | CDATA (float) | — | **yes** | X in model local coords (0=left, 1=right) | fraction | **MISSING** |
| `y` | CDATA (float) | — | **yes** | Y in model local coords (0=front, 1=back) | fraction | **MISSING** |
| `z` | CDATA (float) | — | **yes** | Z in model local coords (0=bottom, 1=top) | fraction | **MISSING** |
| `color` | CDATA (AARRGGBB hex) | — | **yes** | Light colour | — | **MISSING** |
| `diameter` | CDATA (float) | — | no | Sphere diameter of the source gizmo | fraction | **MISSING** |

**Example**:

```xml
<light name="Ceiling Light" power="0.8" …>
  <lightSource x="0.5" y="0.5" z="0.1" color="FFFFFFFF" diameter="0.05"/>
</light>
```

---

### 2.28 `<lightSourceMaterial>` — Named light-emitting material

**Description**: Marks a named material group within the light's 3D model as a light-emitting surface. Appearance-only — does not add a physics light.

**Python model**: **MISSING**

**Children**: none (EMPTY)

**Attributes**:

| Name | Type | Default | Required | Description | Units | model.py field |
|------|------|---------|----------|-------------|-------|----------------|
| `name` | CDATA | — | **yes** | Material group name in the model that glows | — | **MISSING** |

---

### 2.29 `<textStyle>` — Text formatting

**Description**: Defines font, size, weight, and alignment for a text element. Used by `<room>` (name/area labels), `<dimensionLine>` (length text), `<label>`, and furniture (name labels). The `attribute` discriminates the target slot.

**Python model**: **MISSING** — no `TextStyle` dataclass

**Children**: none (EMPTY)

**Attributes**:

| Name | Type | Default | Required | Description | Units | model.py field |
|------|------|---------|----------|-------------|-------|----------------|
| `attribute` | `nameStyle\|areaStyle\|lengthStyle` | — | no | Target slot (omitted for label/furniture) | — | **MISSING** |
| `fontName` | CDATA | — | no | Font family name; `null` = system default | — | **MISSING** |
| `fontSize` | CDATA (float) | — | **yes** | Font size | pt | **MISSING** |
| `bold` | `false\|true` | `false` | no | Bold | — | **MISSING** |
| `italic` | `false\|true` | `false` | no | Italic | — | **MISSING** |
| `alignment` | `LEFT\|CENTER\|RIGHT` | `CENTER` | no | Text alignment | — | **MISSING** |

**Example**:

```xml
<textStyle attribute="nameStyle" fontSize="18" bold="true" alignment="CENTER"/>
```

---

### 2.30 `<transformation>` — Bone/joint transformation

**Description**: A named 4×3 matrix transformation applied to a named joint/bone within the furniture's 3D model (for articulated models). Multiple transformations can be present.

**Python model**: **MISSING** — no `Transformation` dataclass

**Children**: none (EMPTY)

**Attributes**:

| Name | Type | Default | Required | Description | Units | model.py field |
|------|------|---------|----------|-------------|-------|----------------|
| `name` | CDATA | — | no | Joint/bone name in the model | — | **MISSING** |
| `matrix` | CDATA (12 floats) | — | **yes** | Row-major 3×4 affine transformation matrix: `m00 m01 m02 m03 m10 m11 m12 m13 m20 m21 m22 m23` | — | **MISSING** |

**Example**:

```xml
<transformation name="door_hinge"
    matrix="1 0 0 45 0 1 0 0 0 0 1 0"/>
```

---

### 2.31 `<point>` — 2D vertex

**Description**: A single 2D vertex used in `<room>` and `<polyline>` point lists.

**Python model**: `Point`

**Children**: none (EMPTY)

**Attributes**:

| Name | Type | Default | Required | Description | Units | model.py field |
|------|------|---------|----------|-------------|-------|----------------|
| `x` | CDATA (float) | — | **yes** | X coordinate | cm | `Point.x` |
| `y` | CDATA (float) | — | **yes** | Y coordinate | cm | `Point.y` |

**Example**:

```xml
<point x="200.0" y="0.0"/>
```

---

## 3. Coverage Summary

| Metric | Count |
|--------|-------|
| **Total XML elements** | 28 |
| **Total attributes across all elements** | ~185 |
| **Attributes modelled in Python** | ~72 |
| **Coverage** | ~39% |

### Missing fields by priority

| Priority | Element | Missing attributes | Impact on SVG→SH3D pipeline |
|----------|---------|-------------------|------------------------------|
| HIGH | `<pieceOfFurniture>` / `<doorOrWindow>` / `<light>` | `planIcon`, `widthInPlan`, `depthInPlan`, `heightInPlan`, `modelFlags`, `modelMirrored`, `modelRotation`, `modelCenteredAtOrigin`, `modelSize`, `information`, `license`, `nameAngle`, `nameXOffset`, `nameYOffset`, `doorOrWindow` flag, `horizontallyRotatable`, `resizable`, `deformable`, `texturable`, `staircaseCutOutShape`, `dropOnTopElevation`, `price`, `valueAddedTaxPercentage`, `currency` | Writing catalog furniture without these produces SH3D warnings and incorrect plan display |
| HIGH | `<doorOrWindow>` | `wallCutOutOnBothSides`, `widthDepthDeformable` | Double-sided window openings silently broken |
| HIGH | `<furnitureGroup>` | entire element missing | Cannot export grouped furniture |
| HIGH | `<textStyle>` | entire element missing | Room names, dimension labels use SH3D defaults |
| HIGH | `<baseboard>` | entire element missing | Cannot add skirting boards |
| HIGH | `<sash>` | entire element missing | Door swing not preserved |
| HIGH | `<print>` | entire element missing | Print settings lost on re-open |
| MEDIUM | `<room>` | `areaAngle`, `areaXOffset`, `areaYOffset` | Area label placement incorrect |
| MEDIUM | `<environment>` | `backgroundImageVisibleOnGround3D` | Minor rendering difference |
| MEDIUM | `<texture>` | `leftToRightOriented` | Texture mirroring on back face lost |
| MEDIUM | `<lightSource>` | entire element missing | Light source positions not written |
| MEDIUM | `<lightSourceMaterial>` | entire element missing | Emissive materials not tagged |
| MEDIUM | `<material>` | entire element missing | Per-material colour overrides lost |
| MEDIUM | `<transformation>` | entire element missing | Articulated model poses lost |
| LOW | `<shelfUnit>` / `<shelf>` | entire elements missing | Shelf furniture reads as basic piece |
| LOW | `<property>` | no structured Python storage | Custom/plugin properties lost |
| LOW | `<furnitureVisibleProperty>` | not stored | Column visibility resets to SH3D default |

---

## Appendix A — Full DTD (embedded in HomeXMLHandler.java)

The following is the authoritative DTD as documented in the `HomeXMLHandler` Javadoc. This is the schema SH3D 7.5 reads and writes.

```dtd
<!ELEMENT home (property*, furnitureVisibleProperty*, environment?, backgroundImage?, print?, compass?,
      (camera | observerCamera)*, level*,
      (pieceOfFurniture | doorOrWindow | furnitureGroup | light)*, wall*, room*, polyline*, dimensionLine*, label*)>
<!ATTLIST home
      version CDATA #IMPLIED
      name CDATA #IMPLIED
      camera (observerCamera | topCamera) "topCamera"
      selectedLevel CDATA #IMPLIED
      wallHeight CDATA #IMPLIED
      basePlanLocked (false | true) "false"
      furnitureSortedProperty CDATA #IMPLIED
      furnitureDescendingSorted (false | true) "false">

<!ELEMENT property EMPTY>
<!ATTLIST property
      name CDATA #REQUIRED
      value CDATA #REQUIRED
      type (STRING|CONTENT) "STRING">

<!ELEMENT furnitureVisibleProperty EMPTY>
<!ATTLIST furnitureVisibleProperty name CDATA #REQUIRED>

<!ELEMENT environment (property*, (camera | observerCamera)*, texture?, texture?) >
<!ATTLIST environment
      groundColor CDATA #IMPLIED
      backgroundImageVisibleOnGround3D (false | true) "false"
      skyColor CDATA #IMPLIED
      lightColor CDATA #IMPLIED
      wallsAlpha CDATA "0"
      allLevelsVisible (false | true) "false"
      observerCameraElevationAdjusted (false | true) "true"
      ceillingLightColor CDATA #IMPLIED
      drawingMode (FILL | OUTLINE | FILL_AND_OUTLINE) "FILL"
      subpartSizeUnderLight CDATA "0"
      photoWidth CDATA "400"
      photoHeight CDATA "300"
      photoAspectRatio (FREE_RATIO | VIEW_3D_RATIO | RATIO_4_3 | RATIO_3_2 | RATIO_16_9 | RATIO_2_1 | RATIO_24_10 | SQUARE_RATIO) "VIEW_3D_RATIO"
      photoQuality CDATA "0"
      videoWidth CDATA "320"
      videoAspectRatio (RATIO_4_3 | RATIO_16_9 | RATIO_24_10) "RATIO_4_3"
      videoQuality CDATA "0"
      videoSpeed CDATA #IMPLIED
      videoFrameRate CDATA "25">

<!ELEMENT backgroundImage EMPTY>
<!ATTLIST backgroundImage
      image CDATA #REQUIRED
      scaleDistance CDATA #REQUIRED
      scaleDistanceXStart CDATA #REQUIRED
      scaleDistanceYStart CDATA #REQUIRED
      scaleDistanceXEnd CDATA #REQUIRED
      scaleDistanceYEnd CDATA #REQUIRED
      xOrigin CDATA "0"
      yOrigin CDATA "0"
      visible (false | true) "true">

<!ELEMENT print (printedLevel*)>
<!ATTLIST print
      headerFormat CDATA #IMPLIED
      footerFormat CDATA #IMPLIED
      planScale CDATA #IMPLIED
      furniturePrinted (false | true) "true"
      planPrinted (false | true) "true"
      view3DPrinted (false | true) "true"
      paperWidth CDATA #REQUIRED
      paperHeight CDATA #REQUIRED
      paperTopMargin CDATA #REQUIRED
      paperLeftMargin CDATA #REQUIRED
      paperBottomMargin CDATA #REQUIRED
      paperRightMargin CDATA #REQUIRED
      paperOrientation (PORTRAIT | LANDSCAPE | REVERSE_LANDSCAPE) #REQUIRED>

<!ELEMENT printedLevel EMPTY>
<!ATTLIST printedLevel level ID #REQUIRED>

<!ELEMENT compass (property*)>
<!ATTLIST compass
      x CDATA #REQUIRED
      y CDATA #REQUIRED
      diameter CDATA #REQUIRED
      northDirection CDATA "0"
      longitude CDATA #IMPLIED
      latitude CDATA #IMPLIED
      timeZone CDATA #IMPLIED
      visible (false | true) "true">

<!ENTITY % cameraCommonAttributes
     'id ID #IMPLIED
      name CDATA #IMPLIED
      lens (PINHOLE | NORMAL | FISHEYE | SPHERICAL) "PINHOLE"
      x CDATA #REQUIRED
      y CDATA #REQUIRED
      z CDATA #REQUIRED
      yaw CDATA #REQUIRED
      pitch CDATA #REQUIRED
      time CDATA #IMPLIED
      fieldOfView CDATA #REQUIRED
      renderer CDATA #IMPLIED'>

<!ELEMENT camera (property*)>
<!ATTLIST camera
      %cameraCommonAttributes;
      attribute (topCamera | storedCamera | cameraPath) #REQUIRED>

<!ELEMENT observerCamera (property*)>
<!ATTLIST observerCamera
      %cameraCommonAttributes;
      attribute (observerCamera | storedCamera | cameraPath) #REQUIRED
      fixedSize (false | true) "false">

<!ELEMENT level (property*, backgroundImage?)>
<!ATTLIST level
      id ID #REQUIRED
      name CDATA #REQUIRED
      elevation CDATA #REQUIRED
      floorThickness CDATA #REQUIRED
      height CDATA #REQUIRED
      elevationIndex CDATA "-1"
      visible (false | true) "true"
      viewable (false | true) "true">

<!ENTITY % furnitureCommonAttributes
     'id ID #IMPLIED
      name CDATA #REQUIRED
      angle CDATA "0"
      visible (false | true) "true"
      movable (false | true) "true"
      description CDATA #IMPLIED
      information CDATA #IMPLIED
      license CDATA #IMPLIED
      creator CDATA #IMPLIED
      modelMirrored (false | true) "false"
      nameVisible (false | true) "false"
      nameAngle CDATA "0"
      nameXOffset CDATA "0"
      nameYOffset CDATA "0"
      price CDATA #IMPLIED'>

<!ELEMENT furnitureGroup ((pieceOfFurniture | doorOrWindow | furnitureGroup | light)*, property*, textStyle?)>
<!ATTLIST furnitureGroup
      %furnitureCommonAttributes;
      level IDREF #IMPLIED
      x CDATA #IMPLIED
      y CDATA #IMPLIED
      elevation CDATA #IMPLIED
      width CDATA #IMPLIED
      depth CDATA #IMPLIED
      height CDATA #IMPLIED
      dropOnTopElevation CDATA #IMPLIED>

<!ENTITY % pieceOfFurnitureCommonAttributes
     'level IDREF #IMPLIED
      catalogId CDATA #IMPLIED
      x CDATA #REQUIRED
      y CDATA #REQUIRED
      elevation CDATA "0"
      width CDATA #REQUIRED
      depth CDATA #REQUIRED
      height CDATA #REQUIRED
      dropOnTopElevation CDATA "1"
      model CDATA #IMPLIED
      icon CDATA #IMPLIED
      planIcon CDATA #IMPLIED
      modelRotation CDATA "1 0 0 0 1 0 0 0 1"
      modelCenteredAtOrigin CDATA #IMPLIED
      backFaceShown (false | true) "false"
      modelFlags CDATA #IMPLIED
      modelSize CDATA #IMPLIED
      doorOrWindow (false | true) "false"
      resizable (false | true) "true"
      deformable (false | true) "true"
      texturable (false | true) "true"
      staircaseCutOutShape CDATA #IMPLIED
      color CDATA #IMPLIED
      shininess CDATA #IMPLIED
      valueAddedTaxPercentage CDATA #IMPLIED
      currency CDATA #IMPLIED'>

<!ENTITY % pieceOfFurnitureHorizontalRotationAttributes
     'horizontallyRotatable (false | true) "true"
      pitch CDATA "0"
      roll CDATA "0"
      widthInPlan CDATA #IMPLIED
      depthInPlan CDATA #IMPLIED
      heightInPlan CDATA #IMPLIED'>

<!ELEMENT pieceOfFurniture (property*, textStyle?, texture?, material*, transformation*)>
<!ATTLIST pieceOfFurniture
      %furnitureCommonAttributes;
      %pieceOfFurnitureCommonAttributes;
      %pieceOfFurnitureHorizontalRotationAttributes;>

<!ELEMENT doorOrWindow (sash*, property*, textStyle?, texture?, material*, transformation*)>
<!ATTLIST doorOrWindow
      %furnitureCommonAttributes;
      %pieceOfFurnitureCommonAttributes;
      wallThickness CDATA "1"
      wallDistance CDATA "0"
      wallWidth CDATA "1"
      wallLeft CDATA "0"
      wallHeight CDATA "1"
      wallTop CDATA "0"
      wallCutOutOnBothSides (false | true) "false"
      widthDepthDeformable (false | true) "true"
      cutOutShape CDATA #IMPLIED
      boundToWall (false | true) "true">

<!ELEMENT sash EMPTY>
<!ATTLIST sash
      xAxis CDATA #REQUIRED
      yAxis CDATA #REQUIRED
      width CDATA #REQUIRED
      startAngle CDATA #REQUIRED
      endAngle CDATA #REQUIRED>

<!ELEMENT light (lightSource*, lightSourceMaterial*, property*, textStyle?, texture?, material*, transformation*)>
<!ATTLIST light
      %furnitureCommonAttributes;
      %pieceOfFurnitureCommonAttributes;
      %pieceOfFurnitureHorizontalRotationAttributes;
      power CDATA "0.5">

<!ELEMENT lightSource EMPTY>
<!ATTLIST lightSource
      x CDATA #REQUIRED
      y CDATA #REQUIRED
      z CDATA #REQUIRED
      color CDATA #REQUIRED
      diameter CDATA #IMPLIED>

<!ELEMENT lightSourceMaterial EMPTY>
<!ATTLIST lightSourceMaterial
      name CDATA #REQUIRED>

<!ELEMENT shelfUnit (shelf*, property*, textStyle?, texture?, material*, transformation*)>
<!ATTLIST shelfUnit
      %furnitureCommonAttributes;
      %pieceOfFurnitureCommonAttributes;
      %pieceOfFurnitureHorizontalRotationAttributes;>

<!ELEMENT shelf EMPTY>
<!ATTLIST shelf
      elevation CDATA #IMPLIED
      xLower CDATA #IMPLIED
      yLower CDATA #IMPLIED
      zLower CDATA #IMPLIED
      xUpper CDATA #IMPLIED
      yUpper CDATA #IMPLIED
      zUpper CDATA #IMPLIED>

<!ELEMENT textStyle EMPTY>
<!ATTLIST textStyle
      attribute (nameStyle | areaStyle | lengthStyle) #IMPLIED
      fontName CDATA #IMPLIED
      fontSize CDATA #REQUIRED
      bold (false | true) "false"
      italic (false | true) "false"
      alignment (LEFT | CENTER | RIGHT) "CENTER">

<!ELEMENT texture EMPTY>
<!ATTLIST texture
      attribute (groundTexture | skyTexture | leftSideTexture | rightSideTexture | floorTexture | ceilingTexture) #IMPLIED
      catalogId CDATA #IMPLIED
      name CDATA #REQUIRED
      width CDATA #REQUIRED
      height CDATA #REQUIRED
      xOffset CDATA "0"
      yOffset CDATA "0"
      angle CDATA "0"
      scale CDATA "1"
      creator CDATA #IMPLIED
      fittingArea (false | true) "false"
      leftToRightOriented (true | false) "true"
      image CDATA #REQUIRED>

<!ELEMENT material (texture?)>
<!ATTLIST material
      name CDATA #REQUIRED
      key CDATA #IMPLIED
      color CDATA #IMPLIED
      shininess CDATA #IMPLIED>

<!ELEMENT transformation EMPTY>
<!ATTLIST transformation
      name CDATA #REQUIRED
      matrix CDATA #REQUIRED>

<!ELEMENT wall (property*, texture?, texture?, baseboard?, baseboard?)>
<!ATTLIST wall
      id ID #REQUIRED
      level IDREF #IMPLIED
      wallAtStart IDREF #IMPLIED
      wallAtEnd IDREF #IMPLIED
      xStart CDATA #REQUIRED
      yStart CDATA #REQUIRED
      xEnd CDATA #REQUIRED
      yEnd CDATA #REQUIRED
      height CDATA #IMPLIED
      heightAtEnd CDATA #IMPLIED
      thickness CDATA #REQUIRED
      arcExtent CDATA #IMPLIED
      pattern CDATA #IMPLIED
      topColor CDATA #IMPLIED
      leftSideColor CDATA #IMPLIED
      leftSideShininess CDATA "0"
      rightSideColor CDATA #IMPLIED
      rightSideShininess CDATA "0">

<!ELEMENT baseboard (texture?)>
<!ATTLIST baseboard
      attribute (leftSideBaseboard | rightSideBaseboard) #REQUIRED
      thickness CDATA #REQUIRED
      height CDATA #REQUIRED
      color CDATA #IMPLIED>

<!ELEMENT room (property*, textStyle?, textStyle?, texture?, texture?, point+)>
<!ATTLIST room
      id ID #IMPLIED
      level IDREF #IMPLIED
      name CDATA #IMPLIED
      nameAngle CDATA "0"
      nameXOffset CDATA "0"
      nameYOffset CDATA "-40"
      areaVisible (false | true) "false"
      areaAngle CDATA "0"
      areaXOffset CDATA "0"
      areaYOffset CDATA "0"
      floorVisible (false | true) "true"
      floorColor CDATA #IMPLIED
      floorShininess CDATA "0"
      ceilingVisible (false | true) "true"
      ceilingColor CDATA #IMPLIED
      ceilingShininess CDATA "0"
      ceilingFlat (false | true) "false">

<!ELEMENT point EMPTY>
<!ATTLIST point
      x CDATA #REQUIRED
      y CDATA #REQUIRED>

<!ELEMENT polyline (property*, point+)>
<!ATTLIST polyline
      id ID #IMPLIED
      level IDREF #IMPLIED
      thickness CDATA "1"
      capStyle (BUTT | SQUARE | ROUND) "BUTT"
      joinStyle (BEVEL | MITER | ROUND | CURVED) "MITER"
      dashStyle (SOLID | DOT | DASH | DASH_DOT | DASH_DOT_DOT | CUSTOMIZED) "SOLID"
      dashPattern CDATA #IMPLIED
      dashOffset CDATA "0"
      startArrowStyle (NONE | DELTA | OPEN | DISC) "NONE"
      endArrowStyle (NONE | DELTA | OPEN | DISC) "NONE"
      elevation CDATA #IMPLIED
      color CDATA #IMPLIED
      closedPath (false | true) "false">

<!ELEMENT dimensionLine (property*, textStyle?)>
<!ATTLIST dimensionLine
      id ID #IMPLIED
      level IDREF #IMPLIED
      xStart CDATA #REQUIRED
      yStart CDATA #REQUIRED
      elevationStart CDATA "0"
      xEnd CDATA #REQUIRED
      yEnd CDATA #REQUIRED
      elevationEnd CDATA "0"
      offset CDATA #REQUIRED
      endMarkSize CDATA "10"
      pitch CDATA "0"
      color CDATA #IMPLIED
      visibleIn3D (false | true) "false">

<!ELEMENT label (property*, textStyle?, text)>
<!ATTLIST label
      id ID #IMPLIED
      level IDREF #IMPLIED
      x CDATA #REQUIRED
      y CDATA #REQUIRED
      angle CDATA "0"
      elevation CDATA "0"
      pitch CDATA #IMPLIED
      color CDATA #IMPLIED
      outlineColor CDATA #IMPLIED>

<!ELEMENT text (#PCDATA)>
```

---

## Appendix B — Colour encoding

SH3D encodes colours as 8-character hexadecimal strings in AARRGGBB order (alpha-red-green-blue). The alpha channel is significant: `FF` = fully opaque, `00` = fully transparent.

Examples:
- `FFFFFFFF` — white, fully opaque
- `FF000000` — black, fully opaque
- `FFFFE0B0` — warm ambient light
- `00D0D0D0` — grey ceiling light at zero intensity (transparent = disabled)

When writing colours from Python, use `format(color_int & 0xFFFFFFFF, '08X')`.

---

## Appendix C — Content reference encoding

Binary content (textures, models, icons, background images) is stored as additional entries in the `.sh3d` ZIP. The `image`, `model`, `icon`, and `planIcon` attributes hold one of:

1. **Integer string** — `"0"`, `"1"`, `"2"`, … — refers to a ZIP entry by that integer name. The exporter assigns these sequentially.
2. **`jar:file:…!…` URL** — refers to content inside another JAR (catalog model).
3. **`http://…` or `https://…` URL** — remote content (rarely used).

When building an SH3D file programmatically:
- Add the binary file as a ZIP entry with an integer name.
- Set the XML attribute to the matching integer string.
