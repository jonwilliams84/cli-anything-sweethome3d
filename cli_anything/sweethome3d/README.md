# cli-anything-sweethome3d

CLI harness for **Sweet Home 3D 7.x** — interior design from the command line.

Sweet Home 3D is a Java desktop app for drawing house plans and arranging
furniture. It has no real CLI: its binary only accepts `-open <file>`.
This harness solves that by manipulating `.sh3d` files (ZIP + XML) directly
in Python, then handing the project to the real Sweet Home 3D binary for
photo-realistic render when needed.

## Installation

```bash
# Install the CLI harness
pip install -e .

# Sweet Home 3D is a separate hard dependency for rendering:
# Download from https://www.sweethome3d.com/download.jsp
# Or set SWEETHOME3D_BIN / SWEETHOME3D_JAR
```

## Quick start

```bash
# Create a new project
cli-anything-sweethome3d project new -n "My House" -o /tmp/house.sh3d

# Add a 4-wall room
cli-anything-sweethome3d --project /tmp/house.sh3d wall rectangle 0 0 500 400

# Add a labelled room (floor)
cli-anything-sweethome3d --project /tmp/house.sh3d room rectangle 0 0 500 400 \
    -n "Living Room" --area-visible

# Drop a sofa
cli-anything-sweethome3d --project /tmp/house.sh3d furniture add Sofa 100 100 \
    -w 200 -d 80 -h 80

# Add a door, window, light
cli-anything-sweethome3d --project /tmp/house.sh3d furniture add-door  Door1 250 0
cli-anything-sweethome3d --project /tmp/house.sh3d furniture add-window Win1 0 200
cli-anything-sweethome3d --project /tmp/house.sh3d furniture add-light  Ceiling 250 200

# Export the plan to SVG (pure Python, no SH3D needed)
cli-anything-sweethome3d --project /tmp/house.sh3d export svg /tmp/house.svg

# Open in the GUI for photo render
cli-anything-sweethome3d --project /tmp/house.sh3d render open
```

## SVG-import workflow (the high-throughput path)

For real homes you don't want to add walls one at a time — you want to
**trace a scanned floor plan**. The harness ships an SVG importer that
turns colour-coded SVGs into a multi-level `.sh3d` in one pass.

Draw your plan in Inkscape (or any SVG editor) using these conventions:

| SVG element | Meaning |
|-------------|---------|
| Wall rectangles | Black/grey filled rects = walls (thickness inferred) |
| `#ff0000` (red) rect | External door |
| `#ff00ff` (magenta) rect | Internal door |
| `#00ff00` (bright green) rect | Patio door |
| `#0000ff` (blue) rect | Window |
| `#00ffff` (cyan) rect | Skylight (ceiling-mounted) |
| `#ffff00` (yellow) circle | Pendant light |
| `#55d400` (anchor green) square | Cross-floor alignment marker |
| `<text>` inside a polygon | Room name (drives floor/ceiling colour overrides) |

Drop the SVGs next to a YAML spec describing wall thickness, door
catalog choices, per-room floor colours, and environment settings, then
run a one-liner:

```python
from cli_anything.sweethome3d.core.svg_import import svg_to_home_multi
svg_to_home_multi(spec="bungalow-spec.yaml")
```

A complete worked spec ships in the package:
**[`cli_anything/sweethome3d/examples/bungalow-spec.yaml`](examples/bungalow-spec.yaml)**.
It covers every section: marker-based Procrustes alignment across floors,
width-driven catalog variants (e.g. `if_width_cm_gte: 200 →
doubleWindow126x163`), per-level / per-room floor-colour overrides, and
environment tuning.

Once the project is built you can refine it interactively (recolour a
material, drop in a stored camera, attach a calibrated background
image) via the rest of the CLI.

## REPL mode

Run with no subcommand to enter an interactive session:

```bash
cli-anything-sweethome3d --project /tmp/house.sh3d
sweethome3d (My House)> wall list
sweethome3d (My House)> furniture add Sofa 100 100 -w 200 -d 80 -h 80
sweethome3d (My House)> undo
sweethome3d (My House)> export svg /tmp/preview.svg
sweethome3d (My House)> save
```

Mutations stack as undo points (depth 50). `save` writes to disk; one-shot
commands auto-save unless `--dry-run` is passed.

## Command groups

| Group | What it does |
|-------|--------------|
| `project` | new / open / info / save |
| `level` | list / add / delete / **set** / **select** (multi-floor support) |
| `wall` | list / add / rectangle / move / delete / set / **baseboard** |
| `room` | list / rectangle / add / delete / **set** / **recompute-points** |
| `furniture` | list / add / add-door / add-window / add-light / move / delete / set |
| `catalog` | browse the stock catalog + **`scan`** installed `.sh3f` libraries + **`from-project`** for ids already in the loaded `.sh3d` |
| `textures` | **list / search / info** of the 26 stock SH3D textures |
| `find` | **rooms / walls / pieces / doors / lights** — read-only spatial queries |
| `camera` | top / observer view positioning, **save / list / delete / go** stored viewpoints |
| `dimension` | dimension lines (add / list / delete / **set**) |
| `label` | text annotations (add / list / delete / **set**) |
| `polyline` | **add / list / set / delete** open/closed paths |
| `compass` | north orientation + geolocation |
| `group` | **furniture groups** — `create / list / info / add / remove / ungroup / delete / set` |
| `material` | **per-piece material overrides** — `list / set / clear / clear-all` |
| `sash` | **door/window sashes** — `list / add / delete / clear` |
| `emitter` | **light emitters** — `source list/add/delete/clear` + `material list/add/delete/clear` |
| `shelf` | **shelf-unit shelves** — `list / add / delete / clear` (flat or 3D box) |
| `background` | **background plan image** — `set / clear / show / hide / info` with PNG embedding |
| `print` | **print settings** — `get / set / clear / add-level / remove-level / set-levels` |
| `environment` | sky, ground, lighting, **textures**, photo size, **video-size** |
| `edit` | named edit shortcuts (floor / wall / light / door) |
| `export` | SVG plan view |
| `import` | YAML/SVG floorplan → .sh3d |
| `render` | open in Sweet Home 3D for photo render |
| `watch` | re-render PNG on every .sh3d save |
| `undo` / `redo` / `status` | session state |

Every command supports `--json` for machine-readable output.

### Texture browsing & application

The 26 stock SH3D textures (11 floor, 11 wall, 3 sky — `eTeks#woodenFloor`,
`eTeks#smallBricks`, `eTeks#blueSky`, …) can be browsed with `textures list
--category Floor` and applied to walls, rooms, and the environment:

```bash
# Browse
cli-anything-sweethome3d textures list --category Wall
cli-anything-sweethome3d textures search brick
cli-anything-sweethome3d textures info eTeks#smallBricks

# Apply on creation
cli-anything-sweethome3d --project house.sh3d wall add 0 0 500 0 \
    --left-texture eTeks#smallBricks --right-texture eTeks#roughcast
cli-anything-sweethome3d --project house.sh3d room rectangle 0 0 400 300 \
    --floor-texture eTeks#woodenFloor

# Apply to an existing room/wall/environment
cli-anything-sweethome3d --project house.sh3d room set room-id \
    --floor-texture eTeks#stoneTiles
cli-anything-sweethome3d --project house.sh3d environment set \
    --sky-texture eTeks#blueSky --ground-texture eTeks#grass

# Clear an applied texture
cli-anything-sweethome3d --project house.sh3d wall set wall-id \
    --clear-left-texture
```

Textures emit `<texture attribute="leftSideTexture" .../>` (the canonical SH3D
HomeXMLExporter format), so they render in SH3D 7.x. Older project files
written with a nested `<leftSideTexture>` wrapper still parse correctly via
a backward-compatibility path in the reader.

### Discovering catalog ids

The curated `catalog list` view covers ~60 stock eTeks pieces. Real
homes drawn in SH3D lean on community libraries (`.sh3f` plugins).
Two commands reach the real universe:

```bash
# Read every installed .sh3f + bundled Furniture.jar, show counts by source
cli-anything-sweethome3d --json catalog scan --summary

# All windows in any installed catalog
cli-anything-sweethome3d --json catalog scan --kind doorOrWindow --query window

# Every catalogId already used in this project (community ids too)
cli-anything-sweethome3d --project house.sh3d --json catalog from-project
```

`catalog scan` reads `~/.eteks/sweethome3d/furniture/*.sh3f` on Linux,
`~/Library/Application Support/eTeks/Sweet Home 3D/furniture/*.sh3f`
on macOS, plus the bundled `Furniture.jar` (locatable via
`SWEETHOME3D_FURNITURE_JAR` or auto-detected next to the SH3D binary).

### Spatial / semantic find queries

`find` is the agent's primary introspection surface — pure read-only queries
that return JSON arrays of matched objects:

```bash
# Which room contains a point?
cli-anything-sweethome3d --project house.sh3d --json find rooms --contains 200,150

# Walls near a coordinate (single nearest match within --max-distance cm)
cli-anything-sweethome3d --project house.sh3d --json find walls --near 100,0

# Lights inside a named room
cli-anything-sweethome3d --project house.sh3d --json find lights --in-room Kitchen

# Doors near the front of the house
cli-anything-sweethome3d --project house.sh3d --json find doors --near 250,0

# Walls the importer failed to fuse (no wallAtStart / wallAtEnd)
cli-anything-sweethome3d --project house.sh3d --json find walls --unlinked
```

### Furniture groups, materials & sashes

Bundle related pieces so they move/rotate together. Pieces inside a group
stay reachable via `find_furniture` (and the `material` / `sash` /
`emitter` commands) by name or id, so editing a grouped piece is no
different from editing a top-level piece.

```bash
# Build a sofa-and-chair set
cli-anything-sweethome3d --project house.sh3d group create SeatingSet \
    --pieces Sofa,Chair,Coffee_Table

# Recolour just the cushion material on the grouped Sofa
cli-anything-sweethome3d --project house.sh3d material set Sofa Cushion \
    --color "#AABBCC" --shininess 0.4

# Animate a swing-out door
cli-anything-sweethome3d --project house.sh3d sash add EntryDoor \
    --x-axis 0 --y-axis 0 --width 0.95 \
    --start-angle 0 --end-angle 1.5707

# Add a point emitter inside a light fixture
cli-anything-sweethome3d --project house.sh3d emitter source add CeilingLamp \
    --x 0 --y 0 --z 0.5 --color "#FFFFCC" --diameter 3.0

# Ungroup later (members rejoin home.furniture) or delete the group + members
cli-anything-sweethome3d --project house.sh3d group ungroup SeatingSet
cli-anything-sweethome3d --project house.sh3d group delete SeatingSet
```

### Background plan image

Trace your real-world floorplan over a scanned drawing. The PNG is
embedded inside the .sh3d ZIP so the project is self-contained.

```bash
# Calibrate via two image-pixel endpoints + the real-world distance (cm)
cli-anything-sweethome3d --project house.sh3d background set plan.png \
    --scale-distance 500 \
    --x-start 10 --y-start 10 \
    --x-end 110 --y-end 10

# Per-level background (attach to "Ground")
cli-anything-sweethome3d --project house.sh3d background set plan.png \
    --scale-distance 500 --x-start 0 --y-start 0 --x-end 100 --y-end 0 \
    --level Ground

# Show / hide / drop the overlay
cli-anything-sweethome3d --project house.sh3d background hide
cli-anything-sweethome3d --project house.sh3d background show
cli-anything-sweethome3d --project house.sh3d background clear
```

### Print settings

```bash
cli-anything-sweethome3d --project house.sh3d print set \
    --paper-width 297 --paper-height 420 \
    --orientation LANDSCAPE \
    --plan-scale 100 \
    --header-format "Plan rev \$page"

cli-anything-sweethome3d --project house.sh3d print add-level Ground
cli-anything-sweethome3d --project house.sh3d print add-level Upper
cli-anything-sweethome3d --project house.sh3d --json print get
```

### Stored cameras

Capture the current observer pose as a named viewpoint, then recall it
before a photo render:

```bash
# Frame the camera, save it
cli-anything-sweethome3d --project house.sh3d camera set --kind observerCamera \
    --x 200 --y 150 --z 170 --yaw 0.5
cli-anything-sweethome3d --project house.sh3d camera save kitchen-view

# Later: list, recall, render
cli-anything-sweethome3d --project house.sh3d camera list
cli-anything-sweethome3d --project house.sh3d camera go kitchen-view
cli-anything-sweethome3d --project house.sh3d render photo /tmp/kitchen.png
```

## Schema compatibility

This harness writes `.sh3d` files containing a **`Home.xml`** entry
(schema version `7400`, used by Sweet Home 3D 7.x). Sweet Home 3D readers
prioritise `Home.xml` over the legacy binary `Home` entry, so files written
by this CLI open cleanly in SH3D 7.0+.

Files saved by older SH3D versions (pre-7.0) that contain only the binary
`Home` entry cannot be opened directly — open them in SH3D 7.x once and
re-save to add the XML form.

## Coordinate system

- Units are **centimetres**.
- The plan view's Y axis points **down** (matches SH3D's screen convention).
- Angles are in **radians**.
- Colors are `#RRGGBB` hex (alpha optional).

## Tests

```bash
pip install pytest
pytest cli_anything/sweethome3d/tests -v
```

Run end-to-end tests against the installed CLI:

```bash
CLI_ANYTHING_FORCE_INSTALLED=1 pytest cli_anything/sweethome3d/tests -v -s
```

## License

This harness is independently published under the MIT license.
Sweet Home 3D itself is GPL — see https://www.sweethome3d.com/ for terms.
