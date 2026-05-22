# Spec Expansion — Reference

**Date**: 2026-05-15  
**Files modified**: `spec.py`, `pipeline.py`, `Home-spec.yaml`  
**Tests**: 145 passed (22 new), 5 skipped  
**Regenerated baseline**: walls=51, rooms=18, furniture=70 (unchanged)

---

## 1. Sections Added to DEFAULT_SPEC

The following new top-level and nested sections were added.  Existing keys were not modified.

| Section | Key count | Description |
|---------|-----------|-------------|
| `preferences` | 21 | Mirror of SH3D File → Preferences dialogue (application-level settings stored as `<property>` elements on `<home>`) |
| `compass` | 8 | Maps to `<compass>` element: position, diameter, geographic location, north direction |
| `print` | 14 | Maps to `<print>` element: paper size, margins, orientation, scale, header/footer |
| `environment.photo` | 4 | Photo render settings: width, height, aspect ratio, quality |
| `environment.video` | 5 | Video render settings: width, aspect ratio, quality, frame rate, speed |
| `environment.*` (extended) | 7 | light_color, ceiling_light_color, drawing_mode, all_levels_visible, observer_camera_elevation_adjusted, background_image_visible_on_ground, subpart_size_under_light |
| `walls.baseboard` | 5 | Default skirting board: enabled, thickness_cm, height_cm, color, texture |
| `walls.new_wall_pattern` | 1 | Separate pattern for newly drawn walls (distinct from `walls.pattern`) |
| `rooms.text_style.name` | 5 | TextStyle for room name labels: font_size, font_name, bold, italic, alignment |
| `rooms.text_style.area` | 5 | TextStyle for room area labels (same shape) |
| `dimensions.text_style` | 5 | TextStyle for dimension line length annotations |
| `labels.text_style` | 5 | TextStyle for standalone label text |
| `labels.outline_color` | 1 | Outline/shadow colour for label text |
| `furniture.defaults` | 4 | Per-piece defaults: visible, movable, name_visible, drop_on_top_elevation |
| `openings.sash_defaults` | 1 (list) | Default sash list for doors/windows with no catalog sash data |
| `lights.source_defaults` | 1 (list) | Default light source list for fixtures with no catalog source data |

**Total new sections**: 11 top-level or sub-sections  
**Total new keys**: ~92

---

## 2. Mapping Table: spec key → model field

| spec key path | model class | field | XML attribute |
|---------------|-------------|-------|---------------|
| `preferences.unit` | `Home.properties["extensibleUnit"]` | — | `<property name="extensibleUnit" value="…"/>` |
| `preferences.language` | `Home.properties["language"]` | — | `<property name="language" value="…"/>` |
| `preferences.currency` | `Home.properties["currency"]` | — | `<property name="currency" value="…"/>` |
| `preferences.vat_enabled` | `Home.properties["valueAddedTaxEnabled"]` | — | `<property …/>` |
| `preferences.vat_percentage` | `Home.properties["defaultValueAddedTaxPercentage"]` | — | `<property …/>` |
| `preferences.furniture_catalog_tree` | `Home.properties["furnitureCatalogViewedInTree"]` | — | `<property …/>` |
| `preferences.furniture_viewed_from_top` | `Home.properties["furnitureViewedFromTop"]` | — | `<property …/>` |
| `preferences.furniture_icon_size_px` | `Home.properties["furnitureModelIconSize"]` | — | `<property …/>` |
| `preferences.room_floor_colored` | `Home.properties["roomFloorColoredOrTextured"]` | — | `<property …/>` |
| `preferences.wall_pattern` | `Home.properties["wallPattern"]` | — | `<property …/>` |
| `preferences.magnetism_enabled` | `Home.properties["magnetismEnabled"]` | — | `<property …/>` |
| `preferences.grid_visible` | `Home.properties["gridVisible"]` | — | `<property …/>` |
| `preferences.rulers_visible` | `Home.properties["rulersVisible"]` | — | `<property …/>` |
| `preferences.default_font` | `Home.properties["defaultFontName"]` | — | `<property …/>` |
| `preferences.navigation_panel_visible` | `Home.properties["navigationPanelVisible"]` | — | `<property …/>` |
| `preferences.aerial_view_centered` | `Home.properties["aerialViewCenteredOnSelectionEnabled"]` | — | `<property …/>` |
| `preferences.observer_selected_at_change` | `Home.properties["observerCameraSelectedAtChange"]` | — | `<property …/>` |
| `preferences.editing_in_3d_view` | `Home.properties["editingIn3DViewEnabled"]` | — | `<property …/>` |
| `preferences.auto_save_delay_minutes` | `Home.properties["autoSaveDelayForRecovery"]` (×60000 → ms) | — | `<property …/>` |
| `preferences.check_updates` | `Home.properties["checkUpdatesEnabled"]` | — | `<property …/>` |
| `preferences.photo_renderer` | `Home.properties["photoRenderer"]` | — | `<property …/>` |
| `compass.x` | `Compass.x` | `x` | `<compass x="…"/>` |
| `compass.y` | `Compass.y` | `y` | `<compass y="…"/>` |
| `compass.diameter` | `Compass.diameter` | `diameter` | `<compass diameter="…"/>` |
| `compass.north_direction` | `Compass.northDirection` | `northDirection` | `<compass northDirection="…"/>` |
| `compass.latitude` | `Compass.latitude` | `latitude` | `<compass latitude="…"/>` |
| `compass.longitude` | `Compass.longitude` | `longitude` | `<compass longitude="…"/>` |
| `compass.time_zone` | `Compass.timeZone` | `timeZone` | `<compass timeZone="…"/>` |
| `compass.visible` | `Compass.visible` | `visible` | `<compass visible="…"/>` |
| `print.enabled` | — | guard: creates `Print` object only when True | — |
| `print.paper_width_mm` | `Print.paperWidth` | `paperWidth` | `<print paperWidth="…"/>` |
| `print.paper_height_mm` | `Print.paperHeight` | `paperHeight` | `<print paperHeight="…"/>` |
| `print.paper_top_margin_mm` | `Print.paperTopMargin` | `paperTopMargin` | `<print paperTopMargin="…"/>` |
| `print.paper_left_margin_mm` | `Print.paperLeftMargin` | `paperLeftMargin` | `<print paperLeftMargin="…"/>` |
| `print.paper_bottom_margin_mm` | `Print.paperBottomMargin` | `paperBottomMargin` | `<print …/>` |
| `print.paper_right_margin_mm` | `Print.paperRightMargin` | `paperRightMargin` | `<print …/>` |
| `print.paper_orientation` | `Print.paperOrientation` | `paperOrientation` | `<print paperOrientation="…"/>` |
| `print.header_format` | `Print.headerFormat` | `headerFormat` | `<print headerFormat="…"/>` |
| `print.footer_format` | `Print.footerFormat` | `footerFormat` | `<print footerFormat="…"/>` |
| `print.plan_scale` | `Print.planScale` | `planScale` | `<print planScale="…"/>` |
| `print.furniture_printed` | `Print.furniturePrinted` | `furniturePrinted` | `<print …/>` |
| `print.plan_printed` | `Print.planPrinted` | `planPrinted` | `<print …/>` |
| `print.view_3d_printed` | `Print.view3DPrinted` | `view3DPrinted` | `<print …/>` |
| `environment.light_color` | `Environment.lightColor` | `lightColor` | `<environment lightColor="…"/>` |
| `environment.ceiling_light_color` | `Environment.ceilingLightColor` | `ceillingLightColor` | `<environment ceillingLightColor="…"/>` |
| `environment.drawing_mode` | `Environment.drawingMode` | `drawingMode` | `<environment drawingMode="…"/>` |
| `environment.all_levels_visible` | `Environment.allLevelsVisible` | `allLevelsVisible` | `<environment allLevelsVisible="…"/>` |
| `environment.observer_camera_elevation_adjusted` | `Environment.observerCameraElevationAdjusted` | `observerCameraElevationAdjusted` | `<environment …/>` |
| `environment.background_image_visible_on_ground` | `Environment.backgroundImageVisibleOnGround3D` | `backgroundImageVisibleOnGround3D` | `<environment …/>` |
| `environment.subpart_size_under_light` | `Environment.subpartSizeUnderLight` | `subpartSizeUnderLight` | `<environment …/>` |
| `environment.photo.width` | `Environment.photoWidth` | `photoWidth` | `<environment photoWidth="…"/>` |
| `environment.photo.height` | `Environment.photoHeight` | `photoHeight` | `<environment photoHeight="…"/>` |
| `environment.photo.aspect_ratio` | `Environment.photoAspectRatio` | `photoAspectRatio` | `<environment photoAspectRatio="…"/>` |
| `environment.photo.quality` | `Environment.photoQuality` | `photoQuality` | `<environment photoQuality="…"/>` |
| `environment.video.width` | `Environment.videoWidth` | `videoWidth` | `<environment videoWidth="…"/>` |
| `environment.video.aspect_ratio` | `Environment.videoAspectRatio` | `videoAspectRatio` | `<environment videoAspectRatio="…"/>` |
| `environment.video.quality` | `Environment.videoQuality` | `videoQuality` | `<environment videoQuality="…"/>` |
| `environment.video.frame_rate` | `Environment.videoFrameRate` | `videoFrameRate` | `<environment videoFrameRate="…"/>` |
| `environment.video.speed` | `Environment.videoSpeed` | `videoSpeed` | `<environment videoSpeed="…"/>` |
| `walls.baseboard.enabled` | guard: attaches `Baseboard` to each `Wall` only when True | — | — |
| `walls.baseboard.thickness_cm` | `Baseboard.thickness` | `thickness` | `<baseboard thickness="…"/>` |
| `walls.baseboard.height_cm` | `Baseboard.height` | `height` | `<baseboard height="…"/>` |
| `walls.baseboard.color` | `Baseboard.color` | `color` | `<baseboard color="…"/>` |
| `walls.new_wall_pattern` | `Wall.pattern` (all generated walls) | `pattern` | `<wall pattern="…"/>` |
| `rooms.text_style.name.*` | `Room.nameStyle` (TextStyle) | — | `<textStyle attribute="nameStyle" …/>` |
| `rooms.text_style.area.*` | `Room.areaStyle` (TextStyle) | — | `<textStyle attribute="areaStyle" …/>` |
| `dimensions.text_style.*` | `DimensionLine.lengthStyle` (TextStyle) | — | `<textStyle attribute="lengthStyle" …/>` |
| `labels.text_style.*` | `Label.style` (TextStyle) | — | `<textStyle …/>` |
| `labels.outline_color` | `Label.outlineColor` | `outlineColor` | `<label outlineColor="…"/>` |
| `furniture.defaults.visible` | `PieceOfFurniture.visible` | `visible` | `<pieceOfFurniture visible="…"/>` |
| `furniture.defaults.movable` | `PieceOfFurniture.movable` | `movable` | `<pieceOfFurniture movable="…"/>` |
| `furniture.defaults.name_visible` | `PieceOfFurniture.nameVisible` | `nameVisible` | `<pieceOfFurniture nameVisible="…"/>` |
| `furniture.defaults.drop_on_top_elevation` | `PieceOfFurniture.dropOnTopElevation` | `dropOnTopElevation` | `<pieceOfFurniture dropOnTopElevation="…"/>` |
| `openings.sash_defaults[].x_axis` | `Sash.xAxis` | `xAxis` | `<sash xAxis="…"/>` |
| `openings.sash_defaults[].y_axis` | `Sash.yAxis` | `yAxis` | `<sash yAxis="…"/>` |
| `openings.sash_defaults[].width` | `Sash.width` | `width` | `<sash width="…"/>` |
| `openings.sash_defaults[].start_angle_deg` | `Sash.startAngle` (×π/180) | `startAngle` | `<sash startAngle="…"/>` |
| `openings.sash_defaults[].end_angle_deg` | `Sash.endAngle` (×π/180) | `endAngle` | `<sash endAngle="…"/>` |
| `lights.source_defaults[].x` | `LightSource.x` | `x` | `<lightSource x="…"/>` |
| `lights.source_defaults[].y` | `LightSource.y` | `y` | `<lightSource y="…"/>` |
| `lights.source_defaults[].z` | `LightSource.z` | `z` | `<lightSource z="…"/>` |
| `lights.source_defaults[].color` | `LightSource.color` | `color` | `<lightSource color="…"/>` |
| `lights.source_defaults[].diameter` | `LightSource.diameter` | `diameter` | `<lightSource diameter="…"/>` |

---

## 3. Enum Validation

`load_spec()` now calls `_validate_enums()` after merging, which raises `ValueError` for invalid enum values at these paths:

| Path | Valid values |
|------|-------------|
| `preferences.unit` | centimeter, millimeter, meter, inch, inch_fraction, inch_decimals, foot_decimals |
| `preferences.wall_pattern` | hatchUp, hatchDown, crossHatch, reversedHatchUp, reversedHatchDown, reversedCrossHatch, foreground, background |
| `walls.pattern` | same set as wall_pattern above |
| `walls.new_wall_pattern` | same set + null |
| `environment.drawing_mode` | FILL, OUTLINE, FILL_AND_OUTLINE |
| `environment.photo.aspect_ratio` | FREE_RATIO, VIEW_3D_RATIO, RATIO_4_3, RATIO_3_2, RATIO_16_9, RATIO_2_1, RATIO_24_10, SQUARE_RATIO |
| `environment.video.aspect_ratio` | RATIO_4_3, RATIO_16_9, RATIO_24_10 |
| `print.paper_orientation` | PORTRAIT, LANDSCAPE, REVERSE_LANDSCAPE |
| `rooms.text_style.name.alignment` | LEFT, CENTER, RIGHT |
| `rooms.text_style.area.alignment` | LEFT, CENTER, RIGHT |
| `dimensions.text_style.alignment` | LEFT, CENTER, RIGHT |
| `labels.text_style.alignment` | LEFT, CENTER, RIGHT |

---

## 4. Common User Invocations

### Set wall plan pattern
```yaml
walls:
  pattern: crossHatch           # all walls — hatchUp|hatchDown|crossHatch|…
  new_wall_pattern: foreground  # newly drawn walls only; null = inherit pattern
```

### Enable skirting boards on all walls
```yaml
walls:
  baseboard:
    enabled: true
    thickness_cm: 1.0
    height_cm: 7.0
    color: "#D2B48C"   # tan wood colour
```

### Set photo render to 1080p at maximum quality
```yaml
environment:
  photo:
    width: 1920
    height: 1080
    aspect_ratio: RATIO_16_9
    quality: 3        # 3 = best (global illumination via SunFlow)
```

### Use YafaRay renderer instead of SunFlow
```yaml
preferences:
  photo_renderer: "YafarayRenderer"
```

### Set geographic location for accurate sun-position rendering
```yaml
compass:
  latitude: 0.8988      # London ~51.5° → 0.8988 rad
  longitude: -0.0020    # ~0.12° W
  time_zone: "Europe/London"
  north_direction: 0.0  # plan-up is north
  visible: true
```

### Embed A3 landscape print layout
```yaml
print:
  enabled: true
  paper_width_mm: 420.0
  paper_height_mm: 297.0
  paper_orientation: LANDSCAPE
  plan_scale: 0.005    # 1:200
  header_format: "{name}"
  footer_format: "Page {page}"
  view_3d_printed: false
```

### Room name labels in a specific font
```yaml
rooms:
  text_style:
    name:
      font_size: 20.0
      font_name: "Arial"
      bold: true
      alignment: CENTER
    area:
      font_size: 13.0
      italic: true
```

### Use metric units
```yaml
preferences:
  unit: centimeter     # centimeter | millimeter | meter | inch | …
  currency: "GBP"      # ISO 4217 currency code
```

### Disable grid and rulers (for cleaner screenshots)
```yaml
preferences:
  grid_visible: false
  rulers_visible: false
  magnetism_enabled: true  # keep snap behaviour
```

### Add a default sash to all doors
```yaml
openings:
  sash_defaults:
    - x_axis: 0.0
      y_axis: 0.5
      width: 1.0
      start_angle_deg: 0
      end_angle_deg: 90
```

### Add a default point light source to all ceiling fixtures
```yaml
lights:
  source_defaults:
    - x: 0
      y: 0
      z: 0.5
      color: "#FFFFE0"   # warm white
      diameter: 5
```

---

## 5. What Was Deliberately Omitted

| Category | Reason omitted |
|----------|---------------|
| Per-piece XYZ positions | Come from SVG geometry; declaring them in the spec would conflict with the Procrustes fitting and wall-snap pipeline |
| Auto-generated IDs (`id` attributes on all elements) | Meaningless to declare; always regenerated |
| `modelSize` on furniture | Read-back field computed from the 3D model file; not user-controlled |
| `planIcon` (CONTENT ZIP entry) | Binary content path; not meaningful in a text spec |
| `modelRotation` (3×3 matrix) | Complex matrix; users wanting custom rotation would need a separate tool. Could be added as a per-catalog-id override in a future expansion |
| `storedCameras` | Named camera viewpoints are interactive artefacts — declaring them in a build-from-SVG spec has no use case |
| `furnitureVisibleProperties` (column order) | UI-only list; irrelevant for programmatic builds |
| `recentHomes`, `recentColors`, `recentTextures` | Runtime-only session state (see 05-user-preferences §4) |
| `videoCameraPath` (camera waypoints) | Video path keyframes must be recorded interactively; cannot be expressed in a static spec |
| `backgroundImage` calibration points | Requires image pixel coordinates; out of scope for SVG-from-spec builds |
| `level.backgroundImage` | Per-level reference background; not needed for SVG-import use-cases |
| VAT updates minimum date (`updatesMinimumDate`) | Internal SH3D session tracking; not user-meaningful |
| Per-room texture overrides | Current spec exposes per-room floor *colour* overrides. Texture would require catalog-id lookup and is deferred |
| Furniture `materials` slot overrides | Per-material name/colour overrides require knowing the exact material name exported from the 3D model; not feasible in a generic build spec |
| `FurnitureGroup` spec declaration | Groups are assembled interactively in SH3D; building them from SVG has no established use-case |
| Observer/top camera spec declaration | Camera positions are set by SH3D on first open; declaring them in a build spec would conflict with the interactive editing workflow |
