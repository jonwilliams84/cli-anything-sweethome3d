"""First-pass furnish of Jon's big open-plan room (Living room, Level 0) from photos + Wren plan."""
import sys
sys.path.insert(0, "/home/jon/projects/recovered/cli-anything-sweethome3d")
from cli_anything.sweethome3d.core.project import open_home, save_home
from cli_anything.sweethome3d.core.furniture import add_piece

h = open_home("examples/Home-Clean-Base-RAL.sh3d")
g = next(l for l in h.levels if l.name == "Level 0")
L = g.id

def P(name, cat, x, y, w, d, ht, *, angle=0.0, elev=0.0, color=None):
    import math
    add_piece(h, name, x, y, width=w, depth=d, height=ht,
              catalogId=cat, level=L, angle=math.radians(angle), elevation=elev, color=color)

# Room "Living room": x[35,903] y[568,1351]; patio doors at south (y~1351).
# KITCHEN = north/east; ISLAND central; FAMILY (sofa/TV) = south near patio.

# --- Kitchen run along the EAST wall (x~850) ---
P("Fridge Freezer", "eTeks#fridgeFreezer", 845, 640, 65, 65, 180, angle=90)
P("Oven Tower",     "eTeks#oven",          848, 720, 60, 60, 60, angle=90, elev=80)
P("Oven Tower 2",   "eTeks#oven",          848, 720, 60, 60, 60, angle=90, elev=145)
P("Base Cabinet 1", "eTeks#kitchenCabinet", 850, 800, 60, 60, 85, angle=90)
P("Base Cabinet 2", "eTeks#kitchenCabinet", 850, 862, 60, 60, 85, angle=90)
P("Kitchen Sink",   "eTeks#sink",          850, 800, 55, 45, 20, angle=90, elev=85)
P("Dishwasher",     "eTeks#dishwasher",    850, 925, 60, 60, 85, angle=90)
P("Upper Cabinet 1","eTeks#kitchenUpperCabinet", 855, 800, 60, 35, 70, angle=90, elev=140)
P("Upper Cabinet 2","eTeks#kitchenUpperCabinet", 855, 865, 60, 35, 70, angle=90, elev=140)

# --- Kitchen run along the NORTH edge (y~620) ---
P("Base Cabinet 3", "eTeks#kitchenCabinet", 640, 615, 60, 60, 85)
P("Base Cabinet 4", "eTeks#kitchenCabinet", 705, 615, 60, 60, 85)
P("Hob Cabinet",    "eTeks#kitchenCabinet", 770, 615, 60, 60, 85)

# --- Island (central), white quartz top approximated by a stretched cabinet ---
P("Kitchen Island", "eTeks#kitchenCabinet", 500, 830, 110, 260, 92, angle=90, color=0xF2F2EC)
# stools (no stool in catalog -> small chairs approximated by cabinets)
for i, sy in enumerate((760, 830, 900)):
    P(f"Bar Stool {i+1}", "eTeks#kitchenCabinet", 400, sy, 40, 40, 75, color=0x9A9A9A)

# --- Family zone (south, near patio doors) ---
P("TV Unit",   "eTeks#tvUnit", 90, 1040, 160, 45, 50, angle=90)
P("Flat TV",   "eTeks#flatTV", 60, 1040, 130, 10, 75, angle=90, elev=55)
P("Sofa",      "eTeks#sofa",   360, 1060, 240, 95, 85, angle=90)
P("Sofa Chaise","eTeks#sofa",  480, 1175, 240, 95, 85, angle=0)
P("Coffee Table","eTeks#table", 300, 1160, 110, 60, 42)

# --- Dining table (near the middle, by the original-house opening) ---
P("Dining Table", "eTeks#table", 250, 780, 160, 90, 74)

save_home(h, "/tmp/furnished.sh3d", copy_content_from="examples/Home-Clean-Base-RAL.sh3d")
added = [f.name for f in h.furniture if getattr(f,'level',None)==L and f.catalogId and 'door' not in (f.name.lower()) and 'window' not in f.name.lower() and 'stair' not in f.name.lower()]
print("furnished saved. new pieces placed:", len([n for n in added if any(k in n for k in ('Cabinet','Oven','Fridge','Sink','Dishwasher','Island','Stool','TV','Sofa','Table','Hob'))]))
