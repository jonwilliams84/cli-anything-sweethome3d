# Sweet Home 3D — Harness SOP

## TL;DR

Sweet Home 3D 7.x is a Java GUI app for interior design. It has **no real
CLI** — its binary only accepts `-open <file>`. We work around this by
manipulating `.sh3d` files (ZIP archives) directly in Python via the
`Home.xml` schema that SH3D 7.0+ writes alongside the legacy binary
`Home` entry. The real binary is invoked only for photo render.

## Phase 1: Codebase Analysis (summary)

- **Source**: SH3D 7.5 from SourceForge (`SweetHome3D-7.5-src.zip`)
- **Main launcher**: `com.eteks.sweethome3d.SweetHome3D`
- **Persistence**: `com.eteks.sweethome3d.io.HomeFileRecorder`,
  `DefaultHomeOutputStream`, `DefaultHomeInputStream`
- **XML schema**: `com.eteks.sweethome3d.io.HomeXMLHandler` (read) and
  `HomeXMLExporter` (write); version field `7400`
- **Model classes**: `com.eteks.sweethome3d.model.{Home,Wall,Room,Level,
  HomePieceOfFurniture,Camera,DimensionLine,Label,Polyline,Compass,
  HomeEnvironment}`
- **Rendering**: GUI-coupled (`PhotoController` / Java3D photo renderer);
  not invokable headlessly without significant work

## Phase 2: CLI Architecture

### Interaction model

- **Subcommand CLI** with one-shot auto-save (`cli-anything-sweethome3d
  --project file.sh3d wall add 0 0 100 0` writes immediately)
- **REPL** for stateful sessions with undo/redo (default behavior when
  no subcommand is given)
- `--json` flag on every command for agent consumption

### Command groups

| Group | Concerns |
|-------|----------|
| `project` | new / open / info / save |
| `level` | multi-floor levels (+ set / select) |
| `wall` | walls (single + rectangle + set + baseboard) |
| `room` | floor polygons (+ set + recompute-points + textures) |
| `furniture` | pieces + doors/windows + lights |
| `catalog` | stock furniture catalog browser |
| `textures` | stock texture catalog (26 entries: floor/wall/sky) |
| `find` | read-only spatial queries (rooms/walls/pieces/doors/lights) |
| `camera` | top-down + observer cameras + stored viewpoints (save/list/delete/go) |
| `dimension` / `label` / `polyline` / `compass` | annotations (all support `set`) |
| `group` | furniture groups (`create / ungroup / add / remove / set / delete`) |
| `material` | per-piece material overrides (colour, shininess, texture) |
| `sash` | door/window sash geometry |
| `emitter` | per-light point sources + emissive material groups |
| `shelf` | shelfUnit shelf planes and box compartments |
| `background` | calibrated background plan image on home or per level |
| `print` | print settings (paper, margins, orientation, level filter) |
| `environment` | sky/ground/lighting/photo, sky/ground textures, video-size, extras |
| `edit` | named edit shortcuts (floor / wall / light / door) |
| `export` | SVG plan view (pure Python) |
| `import` | YAML+SVG → .sh3d (multi-level pipeline) |
| `render` | open in SH3D for photo render |
| `watch` | re-render PNG on every .sh3d save |
| top-level | `undo` / `redo` / `status` |

### Data layer

- `.sh3d` file = ZIP with `Home.xml` (and optionally `Home` binary +
  numbered content entries for textures/3D models)
- We read & write **only the XML form**, which SH3D 7.x readers prefer
  over the binary form
- Save preserves embedded content from the source file (`copy_content_from`)
  so textures/models survive a roundtrip
- Pre-7.0 binary-only files are rejected with a clear error message

### Backend integration

- `utils/sweethome3d_backend.py` locates the SH3D binary in this order:
  `SWEETHOME3D_BIN`, `which sweethome3d`, macOS app bundle, Linux
  `/opt/sweethome3d`, `SWEETHOME3D_JAR` + `java`
- `render open` launches the GUI with `-open <file>` (the only CLI flag
  SH3D supports); requires a display
- True headless photo render is **not** v1.0; it's deferred to v1.1 once
  a small Java helper JAR can be embedded

## Phase 3: Implementation Notes

### Schema fidelity

The XML writer mirrors `HomeXMLExporter.java` field by field:
- Float attributes are written without trailing zeros (`100` not `100.0`)
- Default values are **omitted** for attributes that match SH3D defaults
  (e.g., `nameYOffset` = -40 → not written; `areaVisible` = false → not
  written); SH3D's reader fills them in
- Colors are 8-char hex uppercase (`#80808080` → `"80808080"`)

### Auto-save vs --dry-run

One-shot commands auto-save after every mutation. The `--dry-run` flag
suppresses the save so commands can preview without persisting. In REPL
mode, mutations stay in memory until `save` is called.

### Undo/redo

Implemented via deepcopy snapshots on a stack capped at 50 entries. Each
mutating CLI command calls `session.checkpoint()` before applying its
change, and rolls back on validation failure.

### SVG plan export

Pure-Python top-down render:
- Rooms drawn as filled polygons (floorColor)
- Walls as filled rectangles using thickness perpendicular to the segment
- Furniture as rotated rectangles (or circles for lights)
- Dimension lines + labels + compass marker overlaid

This is the harness's introspection surface — agents can verify their
mutations by checking the SVG without ever launching SH3D.

## Phase 4-6: Tests

See `cli_anything/sweethome3d/tests/TEST.md`. **398 / 398 tests pass**
in ~34 seconds, covering every data-layer operation, the SVG export,
the session/undo stack, the backend lookup logic, the CLI subprocess
surface, a full end-to-end studio workflow that builds a `.sh3d`
file + exports SVG, the PNG/SVG import pipelines, the render runtime
shim, the v1-refine surface (textures, spatial `find`, polylines,
level/room/dimension/label `set`, baseboards, stored cameras), and the
v2-refine surface (furniture groups, per-piece materials, door/window
sashes, light emitters, shelf compartments, calibrated background plan
image with PNG embedded in the .sh3d ZIP, print settings with paper /
margin / level filter, and the stored-camera observer/top kind fix).

## Refine pass — 2026-05-22

A `/cli-anything:refine` run added the following coverage on top of the
v1.0 surface:

- **Textures** — new `textures` core module and command group exposes the
  26 stock SH3D textures (11 floor, 11 wall, 3 sky). Texture options
  (`--floor-texture`, `--ceiling-texture`, `--left-texture`,
  `--right-texture`, `--sky-texture`, `--ground-texture`) are threaded
  through `wall`, `room`, and `environment`.
- **Texture serialization fix** — the previous writer wrapped textures in a
  non-standard `<leftSideTexture><texture .../></leftSideTexture>` form
  that SH3D's `HomeXMLHandler` silently ignores. The writer now emits the
  canonical `<texture attribute="leftSideTexture" .../>` form, and the
  reader still accepts the legacy wrapper for backward compatibility.
- **Find** — `find rooms/walls/pieces/doors/lights` surfaces the rich query
  helpers in `core/find.py` to agents (no more JSON-dump-and-parse).
- **Polyline** — full CRUD CLI group around the existing `Polyline` data
  layer (`add` / `list` / `set` / `delete`).
- **Level set / select** — closes the level editing gap; ties into the
  pre-existing `Home.selectedLevel` field.
- **Room set / recompute-points** — closes the room editing gap.
- **Stored cameras** — `camera save/list/delete/go` make named viewpoints
  first-class so agents can recall them before `render photo`.
- **Baseboards** — `wall baseboard` with side/thickness/height/color/texture
  exposes the `Baseboard` dataclass that was already round-tripping but
  unreachable from the CLI.
- **Dimension / label set** — in-place editing of existing annotations
  (color, elevation, visibleIn3D, outline, text, position, …).
- **Environment extras** — sky/ground textures, `--background-on-ground`,
  `--all-levels-visible`, `--observer-elevation-adjusted`,
  `--subpart-size-under-light`, plus new `environment video-size`.

Tests live in `cli_anything/sweethome3d/tests/test_refine.py` (47 tests).

## Refine pass v2 — 2026-05-22

A second `/cli-anything:refine` run closed every remaining
"data-layer-round-trips-but-no-CLI" gap from v1:

- **Furniture groups** — new `group` command group + `core/furniture_groups.py`.
  Pieces are moved (not copied) into the group; `Home.find_furniture` now
  recurses into groups so `material set Sofa …` still works after the
  Sofa has been bundled into a SeatingSet. `ungroup` releases members,
  `delete` discards them.
- **Per-piece materials** — `material list/set/clear/clear-all` + new
  `core/materials.py`. Texture overrides accept catalog ids from
  `textures list`.
- **Door/window sashes** — `sash list/add/delete/clear` + new
  `core/sashes.py`. Rejects sashes on non-door pieces and validates
  fraction ranges.
- **Light emitter tuning** — new `emitter` group with `source` and
  `material` sub-groups + `core/light_emitters.py`.
- **Shelf units** — `shelf list/add/delete/clear` + new `core/shelves.py`,
  with separate `--elevation` (flat shelf) and `--bounds` (box compartment)
  add modes.
- **Background plan image** — new `background` group + `core/background_image.py`
  + `Session.add_content` for queuing the PNG bytes into the .sh3d ZIP on
  the next save. Supports per-level and home-root attachment with full
  calibration (scale line + origin).
- **Print settings** — new `print` group + `core/print_settings.py` with
  paper size, margins, orientation, header/footer, plan scale, and a
  printed-levels filter.
- **Stored camera kind bug fix** — writer now picks `<observerCamera>`
  vs `<camera>` based on `cam.kind`, and the reader derives `kind` from
  the element tag instead of setting the non-existent `"storedCamera"`
  kind. Pre-existing test that encoded the old bug behaviour was updated.
- **Group nested-piece serialization** — the writer's previously-minimal
  inline writer for pieces inside a `FurnitureGroup` is replaced with the
  shared `_write_piece` helper, so materials / sashes / sources /
  properties survive a roundtrip even on grouped pieces.

Tests live in `cli_anything/sweethome3d/tests/test_refine2.py` (69 tests).
Total suite: **398 / 398 pass** in ~34s, 6 skipped (render-runtime,
SH3D-binary-only).

## Known Gaps

- **Catalog browsing**: agents must supply `catalogId` / `model` strings
  directly; we don't enumerate `.sh3f` libraries
- **Photo render**: requires launching the GUI; no headless path yet
- **PDF export**: SH3D's built-in PDF export is GUI-only
- **Video render**: same constraint as photo
- **Model joint transformations** (`<transformation>`): data layer round-trips
  but no CLI command group yet — agents must construct `Transformation`
  objects in code if they need to rig a model.
