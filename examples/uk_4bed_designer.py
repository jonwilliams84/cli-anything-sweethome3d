#!/usr/bin/env python3
"""UK 4-bedroom semi-detached house — Designer API demo.

Produces:
  Home.sh3d  — SweetHome3D project file
  Home.png   — 2-D floor-plan render

Run:
    python3 examples/uk_4bed_designer.py

This script also exports examples/uk_4bed_spec.json so you can verify
the CLI round-trip:

    python3 -m cli_anything.sweethome3d.core.designer \\
        --spec examples/uk_4bed_spec.json \\
        --out  Home_from_spec.sh3d \\
        --render Home_from_spec.png

Layout (all dimensions in cm, ground floor)
-------------------------------------------
Footprint: 850 × 900 cm (8.5 m × 9.0 m — typical UK semi)

Ground floor
  Hallway:        850 × 150  (0,0) – (850,150)
  Living room:    500 × 450  (0,150) – (500,600)
  Kitchen/Dining: 350 × 450  (500,150) – (850,600)
  Utility room:   200 × 300  (0,600) – (200,900)
  WC:             200 × 300  (200,600) – (400,900)
  Study:          450 × 300  (400,600) – (850,900)

First floor
  Landing:        850 × 180  (0,0) – (850,180)
  Master bedroom: 400 × 350  (0,180) – (400,530)
  Bedroom 2:      450 × 350  (400,180) – (850,530)
  Bedroom 3:      300 × 370  (0,530) – (300,900)
  Bedroom 4:      300 × 370  (300,530) – (600,900)
  Bathroom:       250 × 370  (600,530) – (850,900)
"""

import json
import os
import sys
from pathlib import Path

# Allow running from repo root without install
sys.path.insert(0, str(Path(__file__).parent.parent))

from cli_anything.sweethome3d.core.designer import Designer

OUTPUT_DIR = Path(__file__).parent

# ---------------------------------------------------------------------------
# Build the house
# ---------------------------------------------------------------------------

d = Designer(name="UK 4-Bed Semi")

# ── Ground Floor ─────────────────────────────────────────────────────────────
ground = d.add_level("Ground Floor", floor_height=0, ceiling_height=250)

# Exterior envelope
d.envelope(ground, width=850, depth=900, thickness=20)

# Interior partitions — order matters: lay horizontal dividers first so
# vertical partitions can snap to them.

# Horizontal divider: hallway / main rooms
d.partition(ground, (0, 150), (850, 150), thickness=10)
# Horizontal divider: main rooms / rear rooms
d.partition(ground, (0, 600), (850, 600), thickness=10)

# Vertical divider: living / kitchen (touches two horizontal partitions)
d.partition(ground, (500, 150), (500, 600), thickness=10)

# Vertical dividers in rear: utility | WC | study (touch south envelope + y=600 partition)
d.partition(ground, (200, 600), (200, 900), thickness=10)
d.partition(ground, (400, 600), (400, 900), thickness=10)

# Rooms (ground)
d.room(ground, polygon=[(0,0),(850,0),(850,150),(0,150)],
       label="Hallway", floor_color="#C8B99A")
d.room(ground, polygon=[(0,150),(500,150),(500,600),(0,600)],
       label="Living Room", floor_color="#D4C5A9")
d.room(ground, polygon=[(500,150),(850,150),(850,600),(500,600)],
       label="Kitchen/Dining", floor_color="#C8A880")
d.room(ground, polygon=[(0,600),(200,600),(200,900),(0,900)],
       label="Utility Room", floor_color="#B0C8C0")
d.room(ground, polygon=[(200,600),(400,600),(400,900),(200,900)],
       label="WC", floor_color="#C0C8D0")
d.room(ground, polygon=[(400,600),(850,600),(850,900),(400,900)],
       label="Study", floor_color="#C8C0B0")

# External doors
north_wall = d.wall_facing("north", level=ground)
d.add_external_door(ground, wall=north_wall, position_along=0.25,
                    width=90, label="Front Door")

# Side door (east wall to rear garden)
east_wall = d.wall_facing("east", level=ground)
d.add_external_door(ground, wall=east_wall, position_along=0.85,
                    width=80, label="Side Door")

# Internal doors (partition walls referenced by list_walls)
# The horizontal partition at y=150 spans the full width (x=0..850).
# We place two doors on it: one for the living side (position ~30%) and
# one for the kitchen side (position ~70%).
ground_walls = d.list_walls(ground)
h_partition = next(
    w for w in ground_walls
    if not w["is_envelope"]
    and abs(w["start"][1] - 150) < 5 and abs(w["end"][1] - 150) < 5
)
d.add_internal_door(ground, wall=h_partition["id"], position_along=0.3,
                    width=80, label="Hallway→Living")
d.add_internal_door(ground, wall=h_partition["id"], position_along=0.75,
                    width=80, label="Hallway→Kitchen")

# Windows — south (rear) wall
south_wall = d.wall_facing("south", level=ground)
d.add_window(ground, wall=south_wall, position_along=0.2, width=120, label="Living-S Window")
d.add_window(ground, wall=south_wall, position_along=0.65, width=120, label="Kitchen-S Window")

# North-facing windows (living and kitchen)
d.add_window(ground, wall=north_wall, position_along=0.6, width=90, label="Living-N Window")

# West wall windows
west_wall = d.wall_facing("west", level=ground)
d.add_window(ground, wall=west_wall, position_along=0.5, width=100, label="Living-W Window")

# Ground floor furniture
# Living room
d.place_furniture(ground, catalog_id="SOFA_3_SEATS", x=80, y=500, rotation_deg=0,
                  label="Main Sofa")
d.place_furniture(ground, catalog_id="COFFEE_TABLE", x=180, y=430, label="Coffee Table")
d.place_furniture(ground, catalog_id="ARMCHAIR", x=350, y=500, rotation_deg=90,
                  label="Armchair")
d.place_furniture(ground, catalog_id="TV_UNIT", x=80, y=200, rotation_deg=180,
                  label="TV Unit")

# Kitchen/Dining
d.place_furniture(ground, catalog_id="KITCHEN_UNIT_BASE", x=530, y=200, label="Kitchen Base")
d.place_furniture(ground, catalog_id="KITCHEN_SINK",      x=650, y=180, label="Sink")
d.place_furniture(ground, catalog_id="OVEN",              x=570, y=200, label="Oven")
d.place_furniture(ground, catalog_id="REFRIGERATOR",      x=810, y=210, label="Fridge")
d.place_furniture(ground, catalog_id="DINING_TABLE_4",    x=660, y=400, label="Dining Table")

# Utility room
d.place_furniture(ground, catalog_id="WASHING_MACHINE", x=50, y=650, label="Washing Machine")
d.place_furniture(ground, catalog_id="TUMBLE_DRYER",    x=100, y=650, label="Dryer")

# WC
d.place_furniture(ground, catalog_id="TOILET",  x=260, y=820, label="WC")
d.place_furniture(ground, catalog_id="BASIN",   x=260, y=650, label="Basin")

# Study
d.place_furniture(ground, catalog_id="DESK",        x=600, y=650, label="Desk")
d.place_furniture(ground, catalog_id="OFFICE_CHAIR", x=600, y=720, label="Office Chair")
d.place_furniture(ground, catalog_id="BOOKCASE",     x=780, y=650, label="Bookcase")

# ── First Floor ───────────────────────────────────────────────────────────────
first = d.add_level("First Floor", floor_height=250, ceiling_height=250)

# Envelope (same footprint)
d.envelope(first, width=850, depth=900, thickness=20)

# Partitions — horizontal dividers first so verticals can touch them
d.partition(first, (0, 180),   (850, 180),  thickness=10)  # landing divider
d.partition(first, (0, 530),   (850, 530),  thickness=10)  # upper / lower
# Now vertical dividers (each endpoint touches a horizontal or envelope wall)
d.partition(first, (400, 180), (400, 530),  thickness=10)  # master / bed2
d.partition(first, (300, 530), (300, 900),  thickness=10)  # bed3 / bed4
d.partition(first, (600, 530), (600, 900),  thickness=10)  # bed4 / bathroom

# Rooms (first)
d.room(first, polygon=[(0,0),(850,0),(850,180),(0,180)],
       label="Landing", floor_color="#C8B99A")
d.room(first, polygon=[(0,180),(400,180),(400,530),(0,530)],
       label="Master Bedroom", floor_color="#D4C5A9")
d.room(first, polygon=[(400,180),(850,180),(850,530),(400,530)],
       label="Bedroom 2", floor_color="#D0C8BE")
d.room(first, polygon=[(0,530),(300,530),(300,900),(0,900)],
       label="Bedroom 3", floor_color="#C8D0C0")
d.room(first, polygon=[(300,530),(600,530),(600,900),(300,900)],
       label="Bedroom 4", floor_color="#C8CCD4")
d.room(first, polygon=[(600,530),(850,530),(850,900),(600,900)],
       label="Bathroom", floor_color="#B8C8D8")

# Windows (first floor)
north1 = d.wall_facing("north", level=first)
south1 = d.wall_facing("south", level=first)
east1  = d.wall_facing("east",  level=first)
west1  = d.wall_facing("west",  level=first)

d.add_window(first, wall=north1, position_along=0.25, width=100, label="Master-N Window")
d.add_window(first, wall=north1, position_along=0.70, width=100, label="Bed2-N Window")
d.add_window(first, wall=south1, position_along=0.15, width=100, label="Bed3-S Window")
d.add_window(first, wall=south1, position_along=0.45, width=100, label="Bed4-S Window")
d.add_window(first, wall=south1, position_along=0.80, width=80,  label="Bath-S Window")
d.add_window(first, wall=west1,  position_along=0.50, width=90,  label="Master-W Window")
d.add_window(first, wall=east1,  position_along=0.50, width=90,  label="Bed2-E Window")

# First floor internal doors (landing → bedroom rooms)
# The landing partition at y=180 spans the full width (x=0..850).
# We add doors at positions matching master bedroom and bedroom 2.
first_walls = d.list_walls(first)
landing_partition = next(
    w for w in first_walls
    if not w["is_envelope"]
    and abs(w["start"][1] - 180) < 5 and abs(w["end"][1] - 180) < 5
)
d.add_internal_door(first, wall=landing_partition["id"], position_along=0.25,
                    width=80, label="Landing→Master")
d.add_internal_door(first, wall=landing_partition["id"], position_along=0.70,
                    width=80, label="Landing→Bed2")

# Bedroom furniture
# Master
d.place_furniture(first, catalog_id="KING_BED",       x=150, y=350, label="King Bed")
d.place_furniture(first, catalog_id="WARDROBE",        x=30,  y=200, label="Wardrobe")
d.place_furniture(first, catalog_id="CHEST_OF_DRAWERS",x=320, y=200, label="Drawers")

# Bedroom 2
d.place_furniture(first, catalog_id="DOUBLE_BED",  x=580, y=380, label="Double Bed")
d.place_furniture(first, catalog_id="WARDROBE",    x=430, y=200, label="Wardrobe 2")

# Bedroom 3
d.place_furniture(first, catalog_id="SINGLE_BED",  x=100, y=680, label="Single Bed 3")
d.place_furniture(first, catalog_id="BOOKCASE",    x=30,  y=560, label="Bookcase 3")

# Bedroom 4
d.place_furniture(first, catalog_id="SINGLE_BED",  x=430, y=680, label="Single Bed 4")
d.place_furniture(first, catalog_id="DESK",        x=530, y=560, label="Study Desk")

# Bathroom
d.place_furniture(first, catalog_id="BATH",              x=680, y=800, label="Bath")
d.place_furniture(first, catalog_id="SHOWER_ENCLOSURE",  x=760, y=600, label="Shower")
d.place_furniture(first, catalog_id="TOILET",            x=640, y=560, label="Toilet")
d.place_furniture(first, catalog_id="VANITY_UNIT",       x=700, y=560, label="Vanity")

# ---------------------------------------------------------------------------
# Validate
# ---------------------------------------------------------------------------
report = d.validate()
print("=== Validation report ===")
print(json.dumps(report, indent=2))
if report["warnings"]:
    print("\nWarnings:")
    for w in report["warnings"]:
        print(" •", w)

# ---------------------------------------------------------------------------
# Describe
# ---------------------------------------------------------------------------
state = d.describe()
print("\n=== State ===")
print(json.dumps(state, indent=2))

# ---------------------------------------------------------------------------
# Save spec JSON (for CLI round-trip demo)
# ---------------------------------------------------------------------------
spec = d.to_spec()
spec_path = OUTPUT_DIR / "uk_4bed_spec.json"
with spec_path.open("w", encoding="utf-8") as fh:
    json.dump(spec, fh, indent=2)
print(f"\nSpec saved: {spec_path}")

# ---------------------------------------------------------------------------
# Write SH3D + PNG
# ---------------------------------------------------------------------------
out_sh3d = OUTPUT_DIR / "Home.sh3d"
out_png  = OUTPUT_DIR / "Home.png"
d.save(out_sh3d, render_png=out_png)
print(f"SH3D:  {out_sh3d}")
print(f"PNG:   {out_png}")

print("\nCLI round-trip command:")
print(
    f"  python3 -m cli_anything.sweethome3d.core.designer "
    f"--spec {spec_path} "
    f"--out {OUTPUT_DIR / 'Home_from_spec.sh3d'} "
    f"--render {OUTPUT_DIR / 'Home_from_spec.png'}"
)
