# SH3D 7.5 User-Preferences Reference

**Authority**: `UserPreferences.java`, `FileUserPreferences.java`, `DefaultUserPreferences.java`,
`UserPreferencesPanel.java`, `UserPreferencesController.java` — SH3D 7.5 source tree and extracted
class files from `SweetHome3D.jar`.

**Scope**: Every persisted user-preference accessible via *File → Preferences* or programmatically
via `UserPreferences.setXxx()`. These live **outside** `Home.xml` — in the platform's Java
`Preferences` node (a portable XML file under the SH3D application folder) — so they survive across
home files. Where a preference seeds a new-Home default, that is called out explicitly.

---

## 1. How Preferences Relate to Home.xml

User preferences serve two distinct roles:

| Role | How it works |
|------|-------------|
| **Application behaviour** | Controls the SH3D UI for all homes (rulers, grid, magnetism, language, currency). Not written to `Home.xml`. |
| **New-home seed values** | When SH3D creates a new home element (wall, room, level), several preferences supply the initial values. These values then become part of `Home.xml` and travel with the file. |

### Preferences that seed Home.xml defaults

| Preference (Java field) | Home.xml attribute / element seeded |
|-------------------------|--------------------------------------|
| `newWallThickness` | `<wall thickness="…"/>` on each newly drawn wall |
| `newWallHeight` | `<home wallHeight="…"/>` root attribute |
| `newWallPattern` | `<wall pattern="…"/>` |
| `newWallBaseboardThickness` | `<baseboard thickness="…"/>` |
| `newWallBaseboardHeight` | `<baseboard height="…"/>` |
| `newRoomFloorColor` | `<room floorColor="…"/>` |
| `newFloorThickness` | `<level floorThickness="…"/>` |
| `wallPattern` | Default pattern shown for existing walls in plan view (display-only, not stored per-wall in XML unless overridden) |

**Compass / environment / photo / video** settings are stored **inside** `Home.xml` (in `<environment>`,
`<compass>`, and camera elements) — they are per-home, not per-user. The preferences dialogue for
photo/video size and quality writes back to the open home's `HomeEnvironment` object.

---

## 2. Preferences Dialogue — Tab-by-Tab Reference

SH3D 7.5 presents a **single flat dialogue** (not a tabbed panel) with all settings grouped
vertically in this order:

1. Language / Unit / Currency
2. Furniture catalog view
3. 3D navigation
4. Plan-view display (magnetism, rulers, grid, font)
5. Furniture plan icons
6. Room rendering in plan
7. Wall patterns
8. New-wall / new-level defaults
9. Updates and auto-save

The sections below mirror this grouping. Each section header matches the in-application label.

---

### 2.1 Language, Unit and Currency

GUI location: top of the Preferences dialogue.

| Preference | Java field / Property enum | Type | Default | Range / Values | Persisted key | Description |
|---|---|---|---|---|---|---|
| **Language** | `language` / `LANGUAGE` | String (ISO 639 + optional ISO 3166) | System locale's closest match from supported list; falls back to `en` | `bg cs de el en es fr it ja hu nl pl pt pt_BR ru sv vi zh_CN zh_TW` (SH3D built-in); extensible via language-library plugins | `language` | UI display language. Changing restarts resource-bundle resolution. |
| **Unit** | `unit` / `UNIT` | `LengthUnit` enum | `centimeter` (most locales); `inch` for `en_US` locale | `CENTIMETER`, `MILLIMETER`, `METER`, `INCH` (foot/inch/fraction), `INCH_FRACTION`, `INCH_DECIMALS`, `FOOT_DECIMALS` | `unit` / `extensibleUnit` | Measurement unit used throughout the application. The persistence key `extensibleUnit` stores the full enum name to tolerate future additions; `unit` is the legacy fallback. |
| **Currency** | `currency` / `CURRENCY` | String (ISO 4217) or `null` | `null` (prices not used); commented-out `EUR` example in defaults | Any ISO 4217 currency code (e.g. `EUR`, `USD`, `GBP`), or `null` / empty to disable pricing | `currency` | ISO 4217 code shown in furniture price fields. Null means prices are hidden entirely. |
| **Use VAT** | `valueAddedTaxEnabled` / `VALUE_ADDED_TAX_ENABLED` | boolean | `false` | `true` / `false` | `valueAddedTaxEnabled` | Whether Value-Added Tax is applied to furniture prices. |
| **Default VAT %** | `defaultValueAddedTaxPercentage` / `DEFAULT_VALUE_ADDED_TAX_PERCENTAGE` | `BigDecimal` | `0.20` (20%) | Any positive decimal; `null` if VAT disabled | `defaultValueAddedTaxPercentage` | Default VAT percentage applied to prices when VAT is enabled. Not exposed in the standard Preferences GUI — set programmatically or via the `defaultValueAddedTaxPercentage` key in the preferences file. |

---

### 2.2 Furniture Catalog View

GUI label: *Furniture catalog view:*

| Preference | Java field / Property enum | Type | Default | Range / Values | Persisted key | Description |
|---|---|---|---|---|---|---|
| **Catalog in tree (categories)** | `furnitureCatalogViewedInTree` / `FURNITURE_CATALOG_VIEWED_IN_TREE` | boolean | `true` (most platforms); `false` on Linux | `true` = tree of categories; `false` = searchable flat list | `furnitureCatalogViewedInTree` | Controls whether the left-hand furniture panel shows a folder-tree grouped by category or a searchable flat list. |

---

### 2.3 3D Navigation

GUI labels: *3D navigation arrows*, *Selection and editing in 3D view*, *Aerial view centered on selection*, *Select visitor in plan at 3D move*.

| Preference | Java field / Property enum | Type | Default | Range / Values | Persisted key | Description |
|---|---|---|---|---|---|---|
| **Navigation panel visible** | `navigationPanelVisible` / `NAVIGATION_PANEL_VISIBLE` | boolean | `true` | `true` / `false` | `navigationPanelVisible` | Shows or hides the 3D navigation arrow overlay in the 3D view. Hidden automatically on Mac OS X Tiger (unstable). |
| **Editing in 3D view enabled** | `editingIn3DViewEnabled` / `EDITING_IN_3D_VIEW_ENABLED` | boolean | `false` | `true` / `false` | `editingIn3DViewEnabled` | When true, objects can be selected and moved directly inside the 3D view (added in SH3D 7.2). |
| **Aerial view centered on selection** | `aerialViewCenteredOnSelectionEnabled` / `AERIAL_VIEW_CENTERED_ON_SELECTION_ENABLED` | boolean | `false` | `true` / `false` | `aerialViewCenteredOnSelectionEnabled` | When true, the top-down 3D aerial camera automatically re-centers on the currently selected object. |
| **Select visitor in plan at 3D move** | `observerCameraSelectedAtChange` / `OBSERVER_CAMERA_SELECTED_AT_CHANGE` | boolean | `true` | `true` / `false` | `observerCameraSelectedAtChange` | When true, moving the observer (visitor/first-person) camera in 3D also selects it in the plan view, making its position visible. |

---

### 2.4 Plan-View Display

GUI labels: *Magnetism*, *Rulers*, *Grid*, *Default font*.

| Preference | Java field / Property enum | Type | Default | Range / Values | Persisted key | Description |
|---|---|---|---|---|---|---|
| **Magnetism enabled** | `magnetismEnabled` / `MAGNETISM_ENABLED` | boolean | `true` | `true` / `false` | `magnetismEnabled` | Global snap-to-object (magnetism) toggle. When enabled, the cursor snaps to wall endpoints, furniture edges, grid lines, and dimension-line handles. |
| **Rulers visible** | `rulersVisible` / `RULERS_VISIBLE` | boolean | `true` | `true` / `false` | `rulersVisible` | Shows or hides the ruler bars along the top and left edges of the plan view. |
| **Grid visible** | `gridVisible` / `GRID_VISIBLE` | boolean | `true` | `true` / `false` | `gridVisible` | Shows or hides the background grid in the plan view. Grid spacing adapts to the current zoom level. |
| **Default font** | `defaultFontName` / `DEFAULT_FONT_NAME` | String or `null` | `null` (system default) | Any font family name installed on the host OS, or `null` | `defaultFontName` | Font applied to new dimension-line labels and room-name labels. Null means use the JVM's default font. |

---

### 2.5 Furniture Icons in Plan

GUI labels: *Furniture icons in plan:*, *Catalog icons / Top view*, *Icon size*.

| Preference | Java field / Property enum | Type | Default | Range / Values | Persisted key | Description |
|---|---|---|---|---|---|---|
| **Furniture viewed from top** | `furnitureViewedFromTop` / `FURNITURE_VIEWED_FROM_TOP` | boolean | `true` (most platforms); `false` on Linux | `true` = rendered top-view; `false` = catalog icon | `furnitureViewedFromTop` | When true, SH3D renders a real-time top-view projection of the 3D furniture model as its plan icon. When false, the static catalog icon PNG is used. |
| **Furniture model icon size** | `furnitureModelIconSize` / `FURNITURE_MODEL_ICON_SIZE` | int (pixels) | `128` | `128`, `256`, `512`, `1024` (custom values accepted) | `furnitureModelIconSize` | Resolution of the off-screen rendered top-view icon. Only relevant when `furnitureViewedFromTop` is true. Higher values are sharper on HiDPI displays but use more VRAM. |

---

### 2.6 Room Rendering in Plan

GUI labels: *Room rendering in plan:*, *Monochrome / Floor color or texture*.

| Preference | Java field / Property enum | Type | Default | Range / Values | Persisted key | Description |
|---|---|---|---|---|---|---|
| **Room floor colored or textured** | `roomFloorColoredOrTextured` / `ROOM_FLOOR_COLORED_OR_TEXTURED` | boolean | `true` (most platforms); `false` on Linux | `true` = colour/texture fill; `false` = monochrome | `roomFloorColoredOrTextured` | Controls whether room polygons in the plan view are filled with their assigned floor colour or texture, or rendered in a neutral grey (monochrome). |

---

### 2.7 Wall Patterns in Plan

GUI labels: *Wall pattern in plan:*, *New walls pattern in plan:*.

The pattern is identified by its **name string** (the `getName()` of the `TextureImage`). The built-in
pattern names (PNG resources in `com/eteks/sweethome3d/io/resources/patterns/`) are:

| Pattern name | Visual description |
|---|---|
| `hatchUp` | Diagonal hatching — lines going up-right (default) |
| `hatchDown` | Diagonal hatching — lines going down-right |
| `crossHatch` | Cross-hatch (both diagonals) |
| `reversedHatchUp` | Negative of hatchUp |
| `reversedHatchDown` | Negative of hatchDown |
| `reversedCrossHatch` | Negative of crossHatch |
| `foreground` | Solid foreground (opaque fill) |
| `background` | Transparent / no fill |

| Preference | Java field / Property enum | Type | Default | Persisted key | Description |
|---|---|---|---|---|---|
| **Wall pattern (existing walls)** | `wallPattern` / `WALL_PATTERN` | `TextureImage` (name) | `hatchUp` | `wallPattern` | The pattern used to fill the cross-section of *all* existing walls in the plan view. Acts as an application-level default; individual walls may override this in their own `<wall pattern="…"/>` attribute. |
| **New wall pattern** | `newWallPattern` / `NEW_WALL_PATTERN` | `TextureImage` (name) or `null` | `null` (inherits `wallPattern`) | `newWallPattern` | Pattern assigned to *newly drawn* walls. When null, new walls inherit `wallPattern`. Stored in `Home.xml` as `<wall pattern="…"/>` on each newly created wall element. |

---

### 2.8 New-Wall and New-Level Defaults

GUI labels: *New walls thickness*, *New walls height*, *New levels floor thickness*.
These are the most important preferences for automation — they seed the geometry of every new Home element.

All length values are stored and retrieved in **centimetres** regardless of the active unit setting.

| Preference | Java field / Property enum | Type | Default (cm) | en_US default | Min | Persisted key | What it seeds in Home.xml |
|---|---|---|---|---|---|---|---|
| **New wall thickness** | `newWallThickness` / `NEW_WALL_THICKNESS` | float (cm) | `7.5` | `7.62` (3 in) | > 0 | `newWallThickness` | `<wall thickness="…"/>` on newly drawn walls |
| **New wall height** | `newWallHeight` / `NEW_WALL_HEIGHT` | float (cm) | `250.0` | `243.84` (8 ft) | > 0 | `newHomeWallHeight` | `<home wallHeight="…"/>` root attribute |
| **New wall baseboard thickness** | `newWallBaseboardThickness` / `NEW_WALL_SIDEBOARD_THICKNESS` | float (cm) | `1.0` | `0.9525` (⅜ in) | ≥ 0 | `newWallBaseboardThickness` | `<baseboard thickness="…"/>` on new walls |
| **New wall baseboard height** | `newWallBaseboardHeight` / `NEW_WALL_SIDEBOARD_HEIGHT` | float (cm) | `7.0` | `6.35` (2½ in) | ≥ 0 | `newWallBaseboardHeight` | `<baseboard height="…"/>` on new walls |
| **New room floor color** | `newRoomFloorColor` / `NEW_ROOM_FLOOR_COLOR` | Integer (ARGB) or `null` | `null` | — | — | `newRoomFloorColor` | `<room floorColor="…"/>` on newly created rooms. Null means the room uses SH3D's default grey. |
| **New level floor thickness** | `newFloorThickness` / `NEW_FLOOR_THICKNESS` | float (cm) | `12.0` | `12.0` | > 0 | `newFloorThickness` | `<level floorThickness="…"/>` on newly added levels |

> **Note on `NEW_WALL_SIDEBOARD_*` naming**: In the Java Property enum and source, the baseboard
> properties are named `NEW_WALL_SIDEBOARD_THICKNESS` and `NEW_WALL_SIDEBOARD_HEIGHT` for historical
> reasons, but the public API methods are `getNewWallBaseboardThickness()` / `setNewWallBaseboardThickness()`.

---

### 2.9 Updates and Auto-Save

GUI labels: *Check updates at program launch*, *Save home data for recovery every: N minutes*.

| Preference | Java field / Property enum | Type | Default | Range / Values | Persisted key | Description |
|---|---|---|---|---|---|---|
| **Check updates enabled** | `checkUpdatesEnabled` / `CHECK_UPDATES_ENABLED` | boolean | `true` | `true` / `false` | `checkUpdatesEnabled` | Whether SH3D contacts the Sweet Home 3D server at startup to check for a newer version. |
| **Updates minimum date** | `updatesMinimumDate` / `UPDATES_MINIMUM_DATE` | Long (ms since epoch) or `null` | `null` | — | `updatesMinimumDate` | Timestamp of the last update the user dismissed. Update notifications older than this date are suppressed. Managed internally; not surfaced in the Preferences GUI. |
| **Auto-save delay for recovery** | `autoSaveDelayForRecovery` / `AUTO_SAVE_DELAY_FOR_RECOVERY` | int (milliseconds) | `600000` (10 min) | `0` = disabled; any positive int | `autoSaveDelayForRecovery` | Interval between automatic saves of the open home to a recovery file. The GUI presents this in minutes (divide by 60000). Setting to 0 disables auto-save. The controller exposes this as a separate `AUTO_SAVE_FOR_RECOVERY_ENABLED` boolean plus an integer delay. |

---

### 2.10 Photo Renderer Preference

This preference is stored in the user-preferences node (not Home.xml) but affects the *Create Photo*
and *Create Video* dialogs.

| Preference | Java field / Property enum | Type | Default | Values | Persisted key | Description |
|---|---|---|---|---|---|---|
| **Photo renderer** | `photoRenderer` / `PHOTO_RENDERER` | String or `null` | `null` (uses built-in SunFlow renderer) | `null` / `""` = SunFlow (default); `"YafarayRenderer"` = YafaRay | `photoRenderer` | Name of the rendering engine class used for photo/video creation. SH3D 7.5 ships SunFlow (built-in, quality levels 0–3) and optionally YafaRay. |

---

## 3. Non-Preference Settings Surfaced in the Same Dialogue

The following are per-**home** settings (stored in `Home.xml`) that SH3D presents in its
Photo/Video creation panels. They are **not** user preferences — they travel with the `.sh3d` file.
They are listed here for completeness so you know where NOT to look for them in UserPreferences.

### 3.1 Photo Settings (HomeEnvironment — per home)

| Property | Java field | Type | Default | Description |
|---|---|---|---|---|
| `PHOTO_WIDTH` | `photoWidth` | int (pixels) | `400` | Width of the rendered photo |
| `PHOTO_HEIGHT` | `photoHeight` | int (pixels) | `300` | Height of the rendered photo |
| `PHOTO_ASPECT_RATIO` | `photoAspectRatio` | `AspectRatio` enum | `VIEW_3D_RATIO` | Aspect ratio constraint |
| `PHOTO_QUALITY` | `photoQuality` | int | `0` | Quality level 0 (fast/3D-view) – 3 (full global illumination) |
| `CEILING_LIGHT_COLOR` | `ceilingLightColor` | int (RGB) | `0xD0D0D0` | Color of ceiling light sources for rendering |

### 3.2 Video Settings (HomeEnvironment — per home)

| Property | Java field | Type | Default | Description |
|---|---|---|---|---|
| `VIDEO_WIDTH` | `videoWidth` | int (pixels) | `320` | Width of rendered video |
| `VIDEO_ASPECT_RATIO` | `videoAspectRatio` | `AspectRatio` enum | `RATIO_4_3` | Aspect ratio constraint |
| `VIDEO_QUALITY` | `videoQuality` | int | `0` | Quality level 0–3 |
| `VIDEO_SPEED` | `videoSpeed` | float (cm/s) | `0.667` (≈ 2.4 km/h) | Camera path traversal speed |
| `VIDEO_FRAME_RATE` | `videoFrameRate` | int (fps) | `25` | Output frame rate |
| `VIDEO_CAMERA_PATH` | `cameraPath` | `List<Camera>` | `[]` | Recorded camera waypoints |

### 3.3 Photo Time, Lens, Renderer (stored per-camera in Home.xml)

| Property | Camera field | Type | Values | Description |
|---|---|---|---|---|
| `TIME` | `Camera.time` | long (ms since epoch midnight) | — | Time-of-day for sun position calculation |
| `LENS` | `Camera.lens` | `Camera.Lens` enum | `PINHOLE`, `NORMAL`, `FISHEYE`, `SPHERICAL` | Camera lens type for photo rendering |
| `RENDERER` | `Camera.renderer` | String | `null` (SunFlow), `"YafarayRenderer"` | Per-camera renderer override |

### 3.4 AspectRatio Enum Values

| Enum constant | Ratio | GUI label |
|---|---|---|
| `VIEW_3D_RATIO` | Matches the 3D panel | "3D view" |
| `FREE_RATIO` | Unconstrained | (free) |
| `SQUARE_RATIO` | 1:1 | "Square" |
| `RATIO_4_3` | 4:3 | "4:3" |
| `RATIO_3_2` | 3:2 | "3:2" |
| `RATIO_16_9` | 16:9 | "16:9" |
| `RATIO_2_1` | 2:1 | "2:1" |
| `RATIO_24_10` | 2.40:1 | "2.40:1" |

---

## 4. Runtime-Only / Session State (Not Persisted)

These are tracked by `UserPreferences` at runtime but not written to the preferences store.

| Field | Type | Description |
|---|---|---|
| `recentHomes` | `List<String>` | File paths of recently opened homes (max 10). Written per-index to `recentHomes0`, `recentHomes1`, etc. |
| `recentColors` | `List<Integer>` (ARGB) | Colour picker history, written as a comma-separated hex string to `recentColors`. |
| `recentTextures` | `List<TextureImage>` | Recently used textures, written per-index with keys `recentTextureName0`, etc. |
| `ignoredActionTips` | `Map<String, Boolean>` | Tracks which one-time action tips have been dismissed. Written per-index to `ignoredActionTip0`, etc. |
| `autoCompletionStrings` | `Map<String, List<String>>` | Text auto-complete suggestions for named fields (room names, level names). Seeded by `autoCompletionStrings#RoomName` and `autoCompletionStrings#LevelName` in `DefaultUserPreferences.properties`. |
| `homeExamples` | `List<HomeDescriptor>` | Built-in example homes shown in the "New home" dialogue. Not user-editable. |

---

## 5. Modifiable Furniture and Texture Catalogs (User-Added Items)

`FileUserPreferences` also stores user-added catalog entries in the same preferences node. These are
not exposed in the standard Preferences dialogue but are written automatically when the user installs
a library.

| Category | Stored under keys | Description |
|---|---|---|
| User furniture | `furniture0`, `furnitureName0`, `furnitureWidth0`, … | Modifiable pieces added to the user's personal furniture catalog |
| User textures | `texture0`, `textureName0`, `textureWidth0`, … | User-added texture catalog entries |
| Library paths | Written to disk by `copyToLibraryFolder()` | `.sh3f` (furniture), `.sh3t` (textures), `.sh3l` (language) library files copied into the application's plugin sub-folders |

---

## 6. Complete Persistence-Key Index

All keys written to the Java `Preferences` node by `FileUserPreferences.write()`:

| Preferences key | Java field | Type | Default value |
|---|---|---|---|
| `language` | `language` | String | System locale |
| `unit` | `unit` (legacy) | String enum name | `centimeter` |
| `extensibleUnit` | `unit` (future-safe) | String enum name | `centimeter` |
| `currency` | `currency` | String / null | `null` |
| `valueAddedTaxEnabled` | `valueAddedTaxEnabled` | boolean | `false` |
| `defaultValueAddedTaxPercentage` | `defaultValueAddedTaxPercentage` | BigDecimal string | `0.2` |
| `furnitureCatalogViewedInTree` | `furnitureCatalogViewedInTree` | boolean | `true` |
| `navigationPanelVisible` | `navigationPanelVisible` | boolean | `true` |
| `editingIn3DViewEnabled` | `editingIn3DViewEnabled` | boolean | `false` |
| `aerialViewCenteredOnSelectionEnabled` | `aerialViewCenteredOnSelectionEnabled` | boolean | `false` |
| `observerCameraSelectedAtChange` | `observerCameraSelectedAtChange` | boolean | `true` |
| `magnetismEnabled` | `magnetismEnabled` | boolean | `true` |
| `rulersVisible` | `rulersVisible` | boolean | `true` |
| `gridVisible` | `gridVisible` | boolean | `true` |
| `defaultFontName` | `defaultFontName` | String / null | `null` |
| `furnitureViewedFromTop` | `furnitureViewedFromTop` | boolean | `true` |
| `furnitureModelIconSize` | `furnitureModelIconSize` | int | `128` |
| `roomFloorColoredOrTextured` | `roomFloorColoredOrTextured` | boolean | `true` |
| `wallPattern` | `wallPattern` | String (pattern name) | `hatchUp` |
| `newWallPattern` | `newWallPattern` | String / null | `null` |
| `newWallThickness` | `newWallThickness` | float (cm) | `7.5` |
| `newHomeWallHeight` | `newWallHeight` | float (cm) | `250.0` |
| `newWallBaseboardThickness` | `newWallBaseboardThickness` | float (cm) | `1.0` |
| `newWallBaseboardHeight` | `newWallBaseboardHeight` | float (cm) | `7.0` |
| `newRoomFloorColor` | `newRoomFloorColor` | hex string / null | `null` |
| `newFloorThickness` | `newFloorThickness` | float (cm) | `12.0` |
| `checkUpdatesEnabled` | `checkUpdatesEnabled` | boolean | `true` |
| `updatesMinimumDate` | `updatesMinimumDate` | long (ms) | — |
| `autoSaveDelayForRecovery` | `autoSaveDelayForRecovery` | int (ms) | `600000` |
| `photoRenderer` | `photoRenderer` | String / null | `null` |
| `recentColors` | `recentColors` | comma-sep hex string | `""` |
| `recentHomes0`…`recentHomesN` | `recentHomes` | String (file path) | — |
| `ignoredActionTip0`…N | action tip keys | String | — |
| `autoCompletionProperty0`…N | property names | String | `RoomName`, `LevelName` |
| `autoCompletionStrings0`…N | suggestion lists | comma-sep string | see defaults |
| `recentTextureName0`…N | texture entries | String | — |

---

## 7. Cross-Reference with Home-spec.yaml

### 7.1 Preferences Already Exposed in the Spec

The current `Home-spec.yaml` / `bungalow-spec.yaml` format directly controls or implies these preferences:

| spec.yaml key | Equivalent UserPreferences field | How mapped |
|---|---|---|
| `walls.height_cm` | `newWallHeight` | Importer sets `<home wallHeight="…"/>` — effectively overrides the preference for the generated home |
| `walls.pattern` | `newWallPattern` / `wallPattern` | Importer sets `<wall pattern="…"/>` on every generated wall |
| `walls.external.thickness_cm` | `newWallThickness` | Applied per-wall (external override) |
| `walls.internal.thickness_cm` | `newWallThickness` | Applied per-wall (internal override) |
| `levels.thickness_cm` | `newFloorThickness` | Importer sets `<level floorThickness="…"/>` |
| `levels.height_cm` | `newWallHeight` (per-level) | Sets level height attribute |
| `rooms.by_level.<name>.default_floor` | (partial) `newRoomFloorColor` | Sets room floor colour — but only as ARGB hex in `<room floorColor="…"/>` |
| `environment.sky_color` | `HomeEnvironment.skyColor` | Written to `<environment skyColor="…"/>` |
| `environment.ground_color` | `HomeEnvironment.groundColor` | Written to `<environment groundColor="…"/>` |
| `environment.walls_alpha` | `HomeEnvironment.wallsAlpha` | Written to `<environment wallsAlpha="…"/>` |

**Total spec fields mapped to preferences or Home-level settings: 9**

### 7.2 Preferences NOT Exposed in the Spec (Recommended Additions)

The following preferences are not declarable in `Home-spec.yaml` today. Each represents a gap where
a user wanting to produce a reproducible, preference-consistent output file cannot currently express
the setting.

| # | Preference | Java field | Type | Recommended spec key | Notes |
|---|---|---|---|---|---|
| 1 | Measurement unit | `unit` | `LengthUnit` enum | `meta.unit` or `preferences.unit` | The importer hard-codes cm internally. Making the unit preference declarable would let the spec signal which unit system the design was authored in, and let any post-processing tool configure preferences correctly. |
| 2 | Wall baseboard thickness | `newWallBaseboardThickness` | float (cm) | `walls.baseboard.thickness_cm` | Baseboards are generated on new walls automatically. Spec currently can't set the default baseboard dimensions. |
| 3 | Wall baseboard height | `newWallBaseboardHeight` | float (cm) | `walls.baseboard.height_cm` | As above. |
| 4 | New wall plan pattern (new vs existing) | `newWallPattern` | String | `walls.new_wall_pattern` | Currently `walls.pattern` maps to both. Splitting lets you say "show existing walls with hatchUp but new walls with crossHatch". |
| 5 | Existing-wall display pattern | `wallPattern` | String | `preferences.wall_pattern` | The global background pattern for all plan walls (not just newly drawn ones). |
| 6 | Room floor colour (new rooms) | `newRoomFloorColor` | ARGB int | `rooms.default_floor_color` (global) | The spec currently expresses floor colour per-level with `by_level`, but there is no global new-room default. |
| 7 | Furniture icon mode | `furnitureViewedFromTop` | boolean | `preferences.furniture_viewed_from_top` | Whether plan icons are rendered top-views or catalog PNGs. Important for visual consistency. |
| 8 | Furniture icon size | `furnitureModelIconSize` | int (px) | `preferences.furniture_icon_size_px` | Icon resolution — 128, 256, 512, 1024. Affects how sharp furniture looks in exported plan images. |
| 9 | Room floor coloured/textured | `roomFloorColoredOrTextured` | boolean | `preferences.room_floor_colored` | Whether rooms show their assigned floor colour in plan view or monochrome grey. |
| 10 | Magnetism enabled | `magnetismEnabled` | boolean | `preferences.magnetism_enabled` | Snap behaviour during interactive editing — less relevant for batch generation but useful for a "run SH3D in kiosk mode" use-case. |
| 11 | Grid visible | `gridVisible` | boolean | `preferences.grid_visible` | Plan-view grid. Affects screenshots/exports. |
| 12 | Rulers visible | `rulersVisible` | boolean | `preferences.rulers_visible` | Ruler bars in plan view. Affects screenshots/exports. |
| 13 | Default font name | `defaultFontName` | String | `preferences.default_font` | Font for dimension labels and room-name text. |
| 14 | Navigation panel visible | `navigationPanelVisible` | boolean | `preferences.navigation_panel_visible` | 3D arrow overlay. Affects screenshots. |
| 15 | Aerial view centred on selection | `aerialViewCenteredOnSelectionEnabled` | boolean | `preferences.aerial_view_centered` | Affects how the 3D top-view camera moves. |
| 16 | Observer camera selected at change | `observerCameraSelectedAtChange` | boolean | `preferences.observer_selected_at_change` | Observer-camera selection behaviour. |
| 17 | Editing in 3D view | `editingIn3DViewEnabled` | boolean | `preferences.editing_in_3d_view` | Whether 3D view supports interactive editing. |
| 18 | Auto-save delay | `autoSaveDelayForRecovery` | int (ms) | `preferences.auto_save_delay_minutes` | Recovery save interval. Useful for "generate and leave open for 30 minutes" automation scenarios. |
| 19 | Check updates | `checkUpdatesEnabled` | boolean | `preferences.check_updates` | Suppress update prompts in non-interactive / CI runs. |
| 20 | Photo renderer | `photoRenderer` | String | `photo.renderer` | Choose between SunFlow and YafaRay for generated photos. |
| 21 | Currency | `currency` | String | `preferences.currency` | ISO 4217 code if cost estimation is needed. |
| 22 | VAT enabled | `valueAddedTaxEnabled` | boolean | `preferences.vat_enabled` | Enable price+VAT display. |
| 23 | Default VAT % | `defaultValueAddedTaxPercentage` | BigDecimal | `preferences.vat_percentage` | VAT rate for price calculations. |
| 24 | Language | `language` | String | `preferences.language` | Output language for labels and the UI when SH3D is run in batch/headless mode. |
| 25 | Furniture catalog view mode | `furnitureCatalogViewedInTree` | boolean | `preferences.furniture_catalog_tree` | Tree vs list layout of the left panel. Useful for automated "open and screenshot" workflows. |

**Recommended additions: 25 spec fields** across two new top-level sections:

```yaml
# Recommended new spec sections

preferences:
  unit: centimeter            # CENTIMETER | MILLIMETER | METER | INCH | INCH_FRACTION | INCH_DECIMALS | FOOT_DECIMALS
  language: en                # ISO 639 code; see SupportedLanguages.properties for list
  currency: null              # ISO 4217 code or null to disable pricing
  vat_enabled: false
  vat_percentage: 0.20
  furniture_viewed_from_top: true
  furniture_icon_size_px: 128 # 128 | 256 | 512 | 1024
  room_floor_colored: true
  wall_pattern: hatchUp       # hatchUp | hatchDown | crossHatch | reversedHatchUp | reversedHatchDown | reversedCrossHatch | foreground | background
  magnetism_enabled: true
  grid_visible: true
  rulers_visible: true
  navigation_panel_visible: true
  aerial_view_centered: false
  observer_selected_at_change: true
  editing_in_3d_view: false
  default_font: null          # null = system default
  auto_save_delay_minutes: 10 # 0 = disabled
  check_updates: false        # recommended false for CI/batch use
  furniture_catalog_tree: true

photo:
  renderer: null              # null = SunFlow | "YafarayRenderer"
  # photo width/height/quality/lens are per-Home in Home.xml, not preferences

walls:
  baseboard:
    thickness_cm: 1.0
    height_cm: 7.0
  new_wall_pattern: null      # null = inherits walls.pattern; override with pattern name to differ
```

---

## 8. Summary Statistics

| Category | Count |
|---|---|
| Total `UserPreferences` persisted fields documented | 36 |
| Preferences exposed in current `Home-spec.yaml` | 9 |
| Preferences recommended for addition to spec | 25 |
| Per-home settings (HomeEnvironment / Camera) documented for context | 13 |
| Built-in wall pattern names | 8 |
| `LengthUnit` enum values | 7 |
| `AspectRatio` enum values | 8 |
| `Camera.Lens` enum values | 4 |
| Supported built-in languages (SH3D 7.5) | 20 |
