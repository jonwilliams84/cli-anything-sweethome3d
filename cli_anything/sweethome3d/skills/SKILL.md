---
name: "cli-anything-sweethome3d"
description: "CLI harness for Sweet Home 3D — create and modify .sh3d interior-design projects (walls, rooms, furniture, lights, cameras) from the command line. Works headlessly via the XML form of .sh3d files; calls the real Sweet Home 3D binary for photo render."
---

# cli-anything-sweethome3d

A command-line interface to **Sweet Home 3D 7.x**, the open-source Java interior
design application. Sweet Home 3D itself has no real CLI; this harness fills
the gap by manipulating `.sh3d` files directly (they're ZIP archives containing
a `Home.xml` schema since SH3D 7.0).

## When to use this skill

Use this CLI when an agent needs to:
- Create a `.sh3d` file from scratch (project, walls, rooms, furniture)
- Inspect or modify an existing `.sh3d` file (list walls, move furniture, etc.)
- Export a 2D plan view of a project to SVG
- Hand off the project to Sweet Home 3D for photo render

## Installation prerequisites

```bash
pip install cli-anything-sweethome3d   # or pip install -e . from source
```

**For `render` commands**, the user must additionally install Sweet Home 3D:
- Download from https://www.sweethome3d.com/download.jsp
- Or set `SWEETHOME3D_BIN` (path to binary) or `SWEETHOME3D_JAR`
- The data-layer commands (project, wall, room, furniture, export svg) all
  work **without** Sweet Home 3D installed.

## Schema

This harness writes the **SH3D 7.x XML schema** (`<home version="7400">`).
Files written by this CLI open in SH3D 7.0 and later. Legacy `.sh3d` files
containing only the binary `Home` entry must be re-saved in SH3D 7.x first.

## Coordinate system

- Units are **centimetres** (1 cm = 1 internal unit)
- Plan-view Y axis points **down** (screen convention)
- Angles in **radians**
- Colors as `#RRGGBB` hex or unprefixed `RRGGBB`

## Command groups

| Group | Subcommands |
|-------|-------------|
| `project` | `new`, `open`, `info`, `save` |
| `level` | `list`, `add`, `delete`, `set`, `select` |
| `wall` | `list`, `add`, `rectangle`, `move`, `set`, `baseboard`, `delete` |
| `room` | `list`, `rectangle`, `add`, `set`, `recompute-points`, `delete` |
| `furniture` | `list`, `add`, `add-door`, `add-window`, `add-light`, `move`, `set`, `delete` |
| `group` | `list`, `create`, `info`, `add`, `remove`, `ungroup`, `delete`, `set` — bundle pieces for batch move |
| `material` | `list`, `set`, `clear`, `clear-all` — per-piece colour / shininess / texture overrides |
| `sash` | `list`, `add`, `delete`, `clear` — door / window swing leaf geometry |
| `emitter` | `source list/add/delete/clear`, `material list/add/delete/clear` — per-light point sources + emissive material groups |
| `shelf` | `list`, `add` (flat `--elevation` or 3D `--bounds`), `delete`, `clear` — shelf compartments inside a shelfUnit |
| `catalog` | browse stock SH3D furniture entries |
| `textures` | `list`, `search`, `info` — 26 stock SH3D textures |
| `find` | `rooms`, `walls`, `pieces`, `doors`, `lights` — read-only spatial / semantic queries |
| `camera` | `get`, `set`, `activate`, `save`, `list`, `delete`, `go` — stored viewpoints |
| `dimension` | `list`, `add`, `set`, `delete` |
| `label` | `list`, `add`, `set`, `delete` |
| `polyline` | `list`, `add`, `set`, `delete` |
| `compass` | `get`, `set` |
| `environment` | `get`, `set`, `photo-size`, `video-size` |
| `background` | `set`, `clear`, `show`, `hide`, `info` — calibrated background plan image (home or per-level) |
| `print` | `get`, `set`, `clear`, `add-level`, `remove-level`, `set-levels` |
| `edit` | named shortcuts: `floor`, `wall`, `light`, `door` |
| `export` | `svg` |
| `import` | `svg` |
| `render` | `open`, `status`, `photo` |
| `watch` | re-render PNG on every .sh3d save |
| top-level | `undo`, `redo`, `status` |

## JSON output (agent mode)

Every command supports `--json` for machine-readable output:

```bash
cli-anything-sweethome3d --project house.sh3d --json wall list
# → [{"id": "...", "xStart": 0, "yStart": 0, "xEnd": 500, ...}, ...]

cli-anything-sweethome3d --project house.sh3d --json project info
# → {"name": "House", "version": 7400, "walls": 4, ...}
```

## Worked example — minimal one-room studio

```bash
# 1. Create the project
cli-anything-sweethome3d project new -n "Studio" -o /tmp/studio.sh3d

# 2. Add four connected walls (5m × 4m room, 7.5cm thickness, 250cm height)
cli-anything-sweethome3d --project /tmp/studio.sh3d \
    wall rectangle 0 0 500 400

# 3. Floor a single room
cli-anything-sweethome3d --project /tmp/studio.sh3d \
    room rectangle 0 0 500 400 -n "Studio" --area-visible

# 4. Door on south wall, window on north wall
cli-anything-sweethome3d --project /tmp/studio.sh3d \
    furniture add-door  Door1   250  0
cli-anything-sweethome3d --project /tmp/studio.sh3d \
    furniture add-window Win1   250  400

# 5. Ceiling light
cli-anything-sweethome3d --project /tmp/studio.sh3d \
    furniture add-light Ceiling 250  200 --power 0.8

# 6. Export the 2D plan to SVG for visual inspection
cli-anything-sweethome3d --project /tmp/studio.sh3d \
    export svg /tmp/studio.svg

# 7. (Optional) Open in Sweet Home 3D for a photo render
cli-anything-sweethome3d --project /tmp/studio.sh3d render open
```

## Worked example — grouped furniture with material overrides

```bash
cli-anything-sweethome3d --project studio.sh3d furniture add Sofa  100 200 \
    -w 200 -d 90 -h 80
cli-anything-sweethome3d --project studio.sh3d furniture add Chair 300 200 \
    -w 60  -d 60 -h 90

# Bundle them — they now move/rotate as a unit
cli-anything-sweethome3d --project studio.sh3d group create SeatingSet \
    --pieces Sofa,Chair

# Grouped pieces stay editable by name — recolour just the cushion
cli-anything-sweethome3d --project studio.sh3d material set Sofa Cushion \
    --color "#AABBCC" --shininess 0.4

# Add a door with an animated swing
cli-anything-sweethome3d --project studio.sh3d furniture add-door EntryDoor 250 0
cli-anything-sweethome3d --project studio.sh3d sash add EntryDoor \
    --x-axis 0 --y-axis 0 --width 0.95 --start-angle 0 --end-angle 1.5707
```

## Worked example — background image + print

```bash
# Trace your real plan: scaleDistance=cm represented by the (start,end) line
cli-anything-sweethome3d --project studio.sh3d background set scan.png \
    --scale-distance 500 --x-start 10 --y-start 10 --x-end 110 --y-end 10

# Configure A3 landscape, 1:100, both levels included
cli-anything-sweethome3d --project studio.sh3d print set \
    --paper-width 420 --paper-height 297 --orientation LANDSCAPE \
    --plan-scale 100
cli-anything-sweethome3d --project studio.sh3d print add-level Ground
cli-anything-sweethome3d --project studio.sh3d print add-level Upper
```

## Auto-save semantics

In one-shot mode (each command launches a fresh process), every mutation
auto-saves the project. Pass `--dry-run` to discard changes.

In REPL mode (no subcommand → interactive prompt), mutations stay in memory
until you run `save`. Use `undo` / `redo` to navigate the history (50 deep).

## Error handling for agents

- File not found / wrong format → `ClickException` with clear message
- Pre-7.0 `.sh3d` (binary `Home` only) → instructs user to re-save in SH3D 7.x
- Render commands when SH3D isn't installed → message with download URL and
  `SWEETHOME3D_BIN` / `SWEETHOME3D_JAR` instructions
- Validation: walls reject zero length, rooms need ≥ 3 points, furniture
  needs positive width/depth/height
