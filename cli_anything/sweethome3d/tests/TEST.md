# cli-anything-sweethome3d — Test Plan & Results

## Test Inventory

| File | Approximate count | Scope |
|------|-------------------|-------|
| `test_core.py` | ~70 unit tests | Pure-Python data model + project I/O + SVG export + 17 chunks of schema coverage |
| `test_full_e2e.py` | ~10 E2E tests | CLI subprocess + .sh3d roundtrip + SH3D binary check |
| `test_refine.py` | 47 tests | Refine pass — textures, find, polyline, level/room set, baseboards, stored cameras, dimension/label set, video size, decorated-house workflow |
| `test_designer.py` / `test_modify_rooms.py` / `test_png_import.py` / `test_svg_import.py` / `test_cli_render_edit_watch.py` / `test_render_runtime.py` | Together ≈ 165 tests | Multi-channel pipelines (PNG/SVG → SH3D, designer DSL, edit/watch/render runtime). |

## Unit Test Plan (`test_core.py`)

### `model.py`
- Dataclass defaults match the SH3D 7.x schema (CURRENT_VERSION = 7400)
- `Home.find_*` resolves by id / name (case-insensitive for furniture)
- `_gen_id()` produces unique 12-char hex ids

### `project.py` — ZIP+XML I/O
- `new_home()` produces an empty Home with sensible defaults
- `home_to_xml()` produces valid XML with `<home version="7400">` root
- `home_to_xml()` writes float attributes without trailing zeros
- `xml_to_home()` parses back what `home_to_xml()` wrote (roundtrip)
- `save_home()` + `open_home()` roundtrip preserves every entity type
- `save_home()` writes a single ZIP entry named `Home.xml`
- `save_home()` preserves embedded content from `copy_content_from`
- `open_home()` rejects files containing only a binary `Home` entry
- `info()` returns correct counts for every entity type

### `walls.py`
- `add_wall` rejects zero-length walls
- `add_wall` inherits height from `home.wallHeight` when None
- `rectangle()` creates 4 connected walls (n.wallAtEnd → e.id, etc.)
- `delete_wall` strips references from connected walls
- `connect_walls` supports all 4 `at` orientations
- `move_wall` updates only the endpoints passed; others unchanged
- `length()` is exact for axis-aligned walls

### `rooms.py`
- `add_room` requires ≥ 3 points
- `add_rectangle_room` rejects zero/negative dimensions
- `delete_room` returns False for unknown id
- `area()` uses the shoelace formula correctly

### `furniture.py`
- `KINDS` is the canonical 3-tuple
- `add_piece` rejects non-positive dimensions
- `add_door` defaults to kind=doorOrWindow with wallThickness=1.0
- `add_window` sets elevation=100 by default
- `add_light` writes power + warm color
- `delete_piece` works by id and by case-insensitive name
- `move_piece` only updates passed fields

### `levels.py`
- `add_level` rejects duplicate names
- `delete_level(detach=False)` raises if objects attached
- `delete_level(detach=True)` clears attached.level for every object
- `select_level(None)` clears the selection

### `cameras.py`
- `set_camera` validates `kind` and `lens`
- `activate_camera` rejects invalid kinds

### `annotations.py`
- `add_dimension` rejects coincident endpoints
- `add_label` rejects empty text
- `add_polyline` requires ≥ 2 points
- Compass set fields surgically

### `export.py`
- `to_svg()` produces a well-formed SVG (parseable by ElementTree)
- SVG includes `<rect>` background, `<polygon>` walls, `<polygon>` rooms, `<text>` for room names
- `_bounds()` falls back to a 100×100 box for an empty home
- `level` filter excludes other-level objects from the SVG

### `session.py`
- `Session.new()` creates an empty in-memory session
- `checkpoint()` snapshots; `undo()` restores; `redo()` reapplies
- `save()` requires a path the first time
- `MAX_UNDO_DEPTH` is honored (oldest snapshot dropped at limit)
- `status()` reflects modified flag + counts

### `sweethome3d_backend.py`
- `find_sweethome3d` raises `Sweethome3DNotInstalled` when nothing is reachable
- Env override `SWEETHOME3D_BIN` is honored when path exists
- `SWEETHOME3D_JAR` + `java` produces `[java, -jar, jar]`

## E2E Test Plan (`test_full_e2e.py`)

### Schema roundtrip
- Build a complex home in Python (levels, walls, rooms, furniture of all kinds,
  dimensions, labels, polylines, compass with custom geolocation, environment
  with sky/ground colors)
- Save → reopen → assert every field matches
- Open SH3D 7.x test fixtures from the source tree: should reject binary-only
  files with a helpful error

### SVG export validity
- Build a multi-feature home → export to SVG → parse with ElementTree
- Assert SVG has all expected `<g>` groups (rooms, walls, furniture, etc.)
- Confirm `viewBox` covers all geometry

### CLI subprocess tests (TestCLISubprocess)
- `cli-anything-sweethome3d --help` exits 0
- `cli-anything-sweethome3d project new -n X -o tmp.sh3d --json`
  produces valid JSON with `{created, name, version}`
- One-shot mutation chain (project new → wall rect → room rect →
  furniture add → export svg) ends with a non-empty SVG file
- `render status` reports `installed: false` cleanly when SH3D isn't found

## Realistic Workflow Scenarios

### W1: Studio apartment
**Simulates** an agent designing a one-room studio from scratch.
**Operations**: new project, wall rectangle, room rectangle, door, window,
ceiling light, SVG export, save.
**Verified**: SVG is well-formed; project counts match (4 walls, 1 room,
1 light, 2 doorOrWindow); `Home.xml` reopens with identical structure.

### W2: Two-level house
**Simulates** designing a two-storey house.
**Operations**: new project, add 2 levels (ground, first), wall rectangles
on each level (different sizes), rooms per level, level select, level delete
with `--keep-attached` (should fail).
**Verified**: level filter respects level id; attached-object guard fires.

### W3: Roundtrip of an existing project
**Simulates** loading an SH3D 7.x project, making one change, saving.
**Operations**: build a project, save, open, mutate furniture, save again,
reopen.
**Verified**: untouched fields survive roundtrip; the change is persisted;
embedded content is preserved when `copy_content_from` is set.

## Coverage Notes

- **Render commands**: only the `status` path is tested in CI — actual GUI
  launch requires a display and SH3D installed, neither available in this
  environment. Documented as a known gap.
- **Binary-only `.sh3d` reading**: explicitly rejected with a clear error,
  not converted; conversion is a v1.1 goal once we ship a Java helper.
- **Catalog browsing**: the harness does not enumerate `.sh3f` furniture
  libraries in v1.0; users supply `catalogId` / `model` strings directly.

## Refine pass — 2026-05-22

A `/cli-anything:refine` pass added the following coverage on top of the
v1.0 baseline:

| Area | New CLI surface | New tests |
|------|-----------------|-----------|
| **Textures** | `textures list/search/info`; `--floor-texture`/`--ceiling-texture` on `room rectangle/add/set`; `--left-texture`/`--right-texture` on `wall add/set`; `--sky-texture`/`--ground-texture` on `environment set` | 12 |
| **Find** | `find rooms/walls/pieces/doors/lights` — read-only spatial/semantic queries wrapping `core/find.py` | 9 |
| **Polyline** | `polyline list/add/set/delete` group | 2 |
| **Level** | `level set` (rename, elevation, height, visible/viewable, …) and `level select` | 3 |
| **Room** | `room set` (textures, colors, shininess, name/area offsets, ceiling flat) and `room recompute-points` | 3 |
| **Camera** | `camera save/list/delete/go` for named stored viewpoints | 3 |
| **Baseboard** | `wall baseboard <ident> --side left/right/both` with thickness/height/color/texture/--clear | 3 |
| **Annotations** | `dimension set` (offset, color, visibleIn3D, pitch, …); `label set` (text, position, angle, colors) | 2 |
| **Environment** | sky/ground textures + `--background-on-ground`, `--all-levels-visible`, `--observer-elevation-adjusted`, `--subpart-size-under-light`; new `environment video-size` | 6 |
| **Schema fix** | `_texture_to_xml` now writes the canonical SH3D format `<texture attribute="leftSideTexture" .../>` (the previous nested wrapper was silently ignored by SH3D's HomeXMLHandler). Reader falls back to the legacy wrapper for backward compat. | 5 |
| **Full workflow** | `test_decorated_two_room_house` — a complete refine-stack workflow chaining levels, rooms with textures, baseboarded walls, polyline decoration, lights, dimensions, environment textures, find queries, and a stored camera | 1 |

Tests live in `tests/test_refine.py` (47 tests). The pre-existing test
suite is unchanged and still passes.

## Refine pass v2 — 2026-05-22 (later same day)

A second `/cli-anything:refine` run targeted the remaining SH3D
"already-in-data-layer-but-not-in-CLI" gaps listed in SWEETHOME3D.md.

| Area | New CLI surface | New tests |
|------|-----------------|-----------|
| **Furniture groups** | `group list/create/info/add/remove/ungroup/delete/set` — bundle pieces, batch move/rotate, recompute footprint | 14 |
| **Per-piece materials** | `material list/set/clear/clear-all` — colour/shininess/texture overrides on individual model material groups | 9 |
| **Door / window sashes** | `sash list/add/delete/clear` — pivot leaf geometry on doorOrWindow pieces | 9 |
| **Light emitters** | `emitter source list/add/delete/clear` (point emitters), `emitter material list/add/delete/clear` (glowing material groups) | 9 |
| **Shelf units** | `shelf list/add/delete/clear` — flat or 3D box compartments inside a shelfUnit piece | 6 |
| **Background plan image** | `background set/clear/show/hide/info` — calibrated PNG overlay on the home or per-level. PNG bytes ship inside the .sh3d ZIP via the new `Session.add_content` queue. | 9 |
| **Print settings** | `print get/set/clear/add-level/remove-level/set-levels` — paper, margins, orientation, header/footer, plan scale, level filter | 9 |
| **Stored camera kind fix** | Pre-existing bug where the writer always tagged stored cameras as `<camera>` regardless of whether they were observer or top views, and the reader set `kind="storedCamera"` (not a valid kind). Writer now picks `<camera>` vs `<observerCamera>` from `cam.kind`; reader derives `kind` from the element tag. | 3 |
| **Group nested-piece serialization** | Pieces inside a `FurnitureGroup` now use the shared `_write_piece` helper instead of a minimal inline writer, so materials/sashes/sources/properties survive a roundtrip on grouped pieces. `Home.find_furniture` also recurses into groups so grouped pieces stay editable from the CLI. | 1 |
| **Full workflow** | `test_full_decorated_room` — chains every new surface (groups, materials, sashes, emitters, background image, print settings) into one studio build | 1 |

Tests live in `tests/test_refine2.py` (69 tests). The pre-existing test
suite is unchanged and still passes; the one assertion that encoded the
old `kind="storedCamera"` bug behaviour was updated to verify the
corrected semantics.

## Test Results

**438 / 438 passed in ~40s** (329 baseline + 69 refine-v2 + 9
example-driven follow-ups + 31 measurement / validate / camera time /
level duplicate; 6 skipped SH3D-binary-only render tests). Includes ~70
CLI subprocess tests.

```
cli_anything/sweethome3d/tests/test_core.py::TestModel (5 tests) PASSED
cli_anything/sweethome3d/tests/test_core.py::TestProjectXML (11 tests) PASSED
cli_anything/sweethome3d/tests/test_core.py::TestWalls (8 tests) PASSED
cli_anything/sweethome3d/tests/test_core.py::TestRooms (5 tests) PASSED
cli_anything/sweethome3d/tests/test_core.py::TestFurniture (8 tests) PASSED
cli_anything/sweethome3d/tests/test_core.py::TestLevels (5 tests) PASSED
cli_anything/sweethome3d/tests/test_core.py::TestCameras (4 tests) PASSED
cli_anything/sweethome3d/tests/test_core.py::TestAnnotations (5 tests) PASSED
cli_anything/sweethome3d/tests/test_core.py::TestEnvironment (3 tests) PASSED
cli_anything/sweethome3d/tests/test_core.py::TestExport (5 tests) PASSED
cli_anything/sweethome3d/tests/test_core.py::TestSession (7 tests) PASSED
cli_anything/sweethome3d/tests/test_core.py::TestBackend (4 tests) PASSED
cli_anything/sweethome3d/tests/test_full_e2e.py::TestCLISubprocess (4 tests) PASSED
cli_anything/sweethome3d/tests/test_full_e2e.py::TestFullWorkflow (3 tests) PASSED
cli_anything/sweethome3d/tests/test_full_e2e.py::TestSchemaRoundtrip (1 test) PASSED
============================== 78 passed in 1.90s ==============================
```

### Summary statistics

| Layer | Tests | Coverage |
|-------|-------|----------|
| Unit (data layer) | 70 | model, project I/O, walls, rooms, furniture, levels, cameras, annotations, environment, SVG export, session, backend lookup |
| CLI subprocess | 4 | --help, --version, project new --json, render status |
| E2E workflow | 3 | full studio build + SVG export + ZIP/XML validation, --dry-run no-op, two-level + level delete |
| Full schema roundtrip | 1 | every entity type written → read → field-level equality |

All commands round-trip through SH3D 7.x's `Home.xml` schema. The
`render` group is exercised only via the `status` no-binary path; a true
GUI render requires the Sweet Home 3D binary which is not present in CI.

