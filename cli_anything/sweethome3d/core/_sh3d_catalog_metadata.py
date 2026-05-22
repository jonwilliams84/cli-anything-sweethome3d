"""Auto-generated catalog metadata for SH3D 7.x default furniture.

Maps each catalogId to the XML attributes required for SH3D to find and
render the piece's 3D model. The values come from the SH3D bundled
`Furniture.jar/DefaultFurnitureCatalog.properties`.

`model` and `icon` are JAR-resource paths (without the leading slash). At
save time, `project.save_home` copies the matching .obj/.png bytes out of
the user's Furniture.jar and into the .sh3d zip under the same name —
SH3D's loader then resolves the reference via its content-context lookup.
"""

from __future__ import annotations

import os
import zipfile
from typing import Optional


def find_furniture_jar() -> Optional[str]:
    """Locate Furniture.jar from a SH3D install.

    Checks $SWEETHOME3D_FURNITURE_JAR, then common install locations.
    Returns None if not found; the writer falls back to omitting model
    content (file will load but pieces will be flagged as damaged).
    """
    env = os.environ.get("SWEETHOME3D_FURNITURE_JAR")
    if env and os.path.isfile(env):
        return env
    candidates = [
        # Linux unpacked install (matches sh3d.tgz layout)
        os.path.expanduser("~/sh3d/SweetHome3D-7.5/lib/Furniture.jar"),
        os.path.expanduser("~/sh3d/SweetHome3D-7.4/lib/Furniture.jar"),
        "/opt/sweethome3d/lib/Furniture.jar",
        "/usr/share/sweethome3d/lib/Furniture.jar",
        # macOS app bundle
        "/Applications/Sweet Home 3D.app/Contents/Java/Furniture.jar",
        # Windows install
        "C:/Program Files/Sweet Home 3D/lib/Furniture.jar",
        "C:/Program Files (x86)/Sweet Home 3D/lib/Furniture.jar",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


_jar_cache: Optional[zipfile.ZipFile] = None


def read_catalog_resource(resource_path: str) -> Optional[bytes]:
    """Read a model or icon resource from the installed Furniture.jar.

    `resource_path` is a JAR-internal path like
    `com/eteks/sweethome3d/io/resources/doorFrame.obj`. Returns None when
    Furniture.jar can't be located or the entry is missing.
    """
    global _jar_cache
    if _jar_cache is None:
        jar = find_furniture_jar()
        if jar is None:
            return None
        _jar_cache = zipfile.ZipFile(jar)
    try:
        return _jar_cache.read(resource_path)
    except KeyError:
        return None

# catalogId -> dict of {model, icon, modelSize, creator, doorOrWindow_flag, _kind}
SH3D_CATALOG: dict[str, dict] = {
    'eTeks#bed140x190': {'model': 'com/eteks/sweethome3d/io/resources/bed140x190.obj', 'icon': 'com/eteks/sweethome3d/io/resources/bed140x190.png', 'modelSize': 11797, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#chest': {'model': 'com/eteks/sweethome3d/io/resources/chest.obj', 'icon': 'com/eteks/sweethome3d/io/resources/chest.png', 'modelSize': 52875, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#bedsideTable': {'model': 'com/eteks/sweethome3d/io/resources/bedsideTable.obj', 'icon': 'com/eteks/sweethome3d/io/resources/bedsideTable.png', 'modelSize': 2243, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#bookcase': {'model': 'com/eteks/sweethome3d/io/resources/bookcase.obj', 'icon': 'com/eteks/sweethome3d/io/resources/bookcase.png', 'modelSize': 3516, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#chair': {'model': 'com/eteks/sweethome3d/io/resources/chair.obj', 'icon': 'com/eteks/sweethome3d/io/resources/chair.png', 'modelSize': 3025, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#roundTable': {'model': 'com/eteks/sweethome3d/io/resources/roundTable.obj', 'icon': 'com/eteks/sweethome3d/io/resources/roundTable.png', 'modelSize': 8110, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#toiletUnit': {'model': 'com/eteks/sweethome3d/io/resources/toiletUnit.obj', 'icon': 'com/eteks/sweethome3d/io/resources/toiletUnit.png', 'modelSize': 125874, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#washbasin': {'model': 'com/eteks/sweethome3d/io/resources/washbasin.obj', 'icon': 'com/eteks/sweethome3d/io/resources/washbasin.png', 'modelSize': 239991, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#bath': {'model': 'com/eteks/sweethome3d/io/resources/bath.obj', 'icon': 'com/eteks/sweethome3d/io/resources/bath.png', 'modelSize': 139580, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#bed90x190': {'model': 'com/eteks/sweethome3d/io/resources/bed90x190.obj', 'icon': 'com/eteks/sweethome3d/io/resources/bed90x190.png', 'modelSize': 11692, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#plant': {'model': 'com/eteks/sweethome3d/io/resources/plant.obj', 'icon': 'com/eteks/sweethome3d/io/resources/plant.png', 'modelSize': 113183, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#window85x123': {'model': 'com/eteks/sweethome3d/io/resources/window85x123.obj', 'icon': 'com/eteks/sweethome3d/io/resources/window85x123.png', 'modelSize': 9333, 'creator': 'eTeks', '_kind': 'doorOrWindow'},
    'eTeks#window85x163': {'model': 'com/eteks/sweethome3d/io/resources/window85x163.obj', 'icon': 'com/eteks/sweethome3d/io/resources/window85x163.png', 'modelSize': 8910, 'creator': 'eTeks', '_kind': 'doorOrWindow'},
    'eTeks#frenchWindow85x200': {'model': 'com/eteks/sweethome3d/io/resources/frenchWindow85x200.obj', 'icon': 'com/eteks/sweethome3d/io/resources/frenchWindow85x200.png', 'modelSize': 9824, 'creator': 'eTeks', '_kind': 'doorOrWindow'},
    'eTeks#doubleWindow126x123': {'model': 'com/eteks/sweethome3d/io/resources/doubleWindow126x123.obj', 'icon': 'com/eteks/sweethome3d/io/resources/doubleWindow126x123.png', 'modelSize': 13503, 'creator': 'eTeks', '_kind': 'doorOrWindow'},
    'eTeks#doubleWindow126x163': {'model': 'com/eteks/sweethome3d/io/resources/doubleWindow126x163.obj', 'icon': 'com/eteks/sweethome3d/io/resources/doubleWindow126x163.png', 'modelSize': 13650, 'creator': 'eTeks', '_kind': 'doorOrWindow'},
    'eTeks#doubleFrenchWindow126x200': {'model': 'com/eteks/sweethome3d/io/resources/doubleFrenchWindow126x200.obj', 'icon': 'com/eteks/sweethome3d/io/resources/doubleFrenchWindow126x200.png', 'modelSize': 13346, 'creator': 'eTeks', '_kind': 'doorOrWindow'},
    'eTeks#doubleHungWindow80x122': {'model': 'com/eteks/sweethome3d/io/resources/doubleHungWindow80x122.obj', 'icon': 'com/eteks/sweethome3d/io/resources/doubleHungWindow80x122.png', 'modelSize': 3457, 'creator': 'eTeks', '_kind': 'doorOrWindow'},
    'eTeks#door': {'model': 'com/eteks/sweethome3d/io/resources/door.obj', 'icon': 'com/eteks/sweethome3d/io/resources/door.png', 'modelSize': 14086, 'creator': 'eTeks', '_kind': 'doorOrWindow'},
    'eTeks#openDoor': {'model': 'com/eteks/sweethome3d/io/resources/openDoor.obj', 'icon': 'com/eteks/sweethome3d/io/resources/openDoor.png', 'modelSize': 14055, 'creator': 'eTeks', '_kind': 'doorOrWindow'},
    'eTeks#armchair': {'model': 'com/eteks/sweethome3d/io/resources/armchair.obj', 'icon': 'com/eteks/sweethome3d/io/resources/armchair.png', 'modelSize': 104093, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#bunkBed90x190': {'model': 'com/eteks/sweethome3d/io/resources/bunkBed90x190.obj', 'icon': 'com/eteks/sweethome3d/io/resources/bunkBed90x190.png', 'modelSize': 19590, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#clothesWasher': {'model': 'com/eteks/sweethome3d/io/resources/clothesWasher.obj', 'icon': 'com/eteks/sweethome3d/io/resources/clothesWasher.png', 'modelSize': 24815, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#cooker': {'model': 'com/eteks/sweethome3d/io/resources/cooker.obj', 'icon': 'com/eteks/sweethome3d/io/resources/cooker.png', 'modelSize': 42013, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#cornerBunkBed90x190': {'model': 'com/eteks/sweethome3d/io/resources/cornerBunkBed90x190.obj', 'icon': 'com/eteks/sweethome3d/io/resources/cornerBunkBed90x190.png', 'modelSize': 24469, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#cornerSofa': {'model': 'com/eteks/sweethome3d/io/resources/cornerSofa.obj', 'icon': 'com/eteks/sweethome3d/io/resources/cornerSofa.png', 'modelSize': 364199, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#curveStaircase': {'model': 'com/eteks/sweethome3d/io/resources/curveStaircase.obj', 'icon': 'com/eteks/sweethome3d/io/resources/curveStaircase.png', 'modelSize': 14116, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#dishwasher': {'model': 'com/eteks/sweethome3d/io/resources/dishwasher.obj', 'icon': 'com/eteks/sweethome3d/io/resources/dishwasher.png', 'modelSize': 7169, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#fridge': {'model': 'com/eteks/sweethome3d/io/resources/fridge.obj', 'icon': 'com/eteks/sweethome3d/io/resources/fridge.png', 'modelSize': 13397, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#fridgeFreezer': {'model': 'com/eteks/sweethome3d/io/resources/fridgeFreezer.obj', 'icon': 'com/eteks/sweethome3d/io/resources/fridgeFreezer.png', 'modelSize': 26363, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#kitchenCabinet': {'model': 'com/eteks/sweethome3d/io/resources/kitchenCabinet.obj', 'icon': 'com/eteks/sweethome3d/io/resources/kitchenCabinet.png', 'modelSize': 11366, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#loftBed140x190': {'model': 'com/eteks/sweethome3d/io/resources/loftBed140x190.obj', 'icon': 'com/eteks/sweethome3d/io/resources/loftBed140x190.png', 'modelSize': 14640, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#piano': {'model': 'com/eteks/sweethome3d/io/resources/piano.obj', 'icon': 'com/eteks/sweethome3d/io/resources/piano.png', 'modelSize': 29003, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#sink': {'model': 'com/eteks/sweethome3d/io/resources/sink.obj', 'icon': 'com/eteks/sweethome3d/io/resources/sink.png', 'modelSize': 41849, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#sofa': {'model': 'com/eteks/sweethome3d/io/resources/sofa.obj', 'icon': 'com/eteks/sweethome3d/io/resources/sofa.png', 'modelSize': 148511, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#squareTable': {'model': 'com/eteks/sweethome3d/io/resources/squareTable.obj', 'icon': 'com/eteks/sweethome3d/io/resources/squareTable.png', 'modelSize': 3045, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#staircase': {'model': 'com/eteks/sweethome3d/io/resources/staircase.obj', 'icon': 'com/eteks/sweethome3d/io/resources/staircase.png', 'modelSize': 13868, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#stool': {'model': 'com/eteks/sweethome3d/io/resources/stool.obj', 'icon': 'com/eteks/sweethome3d/io/resources/stool.png', 'modelSize': 19756, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#tvUnit': {'model': 'com/eteks/sweethome3d/io/resources/tvUnit.obj', 'icon': 'com/eteks/sweethome3d/io/resources/tvUnit.png', 'modelSize': 9569, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#wardrobe': {'model': 'com/eteks/sweethome3d/io/resources/wardrobe.obj', 'icon': 'com/eteks/sweethome3d/io/resources/wardrobe.png', 'modelSize': 23218, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#texturableBox': {'model': 'com/eteks/sweethome3d/io/resources/texturableBox/texturableBox.obj', 'icon': 'com/eteks/sweethome3d/io/resources/box.png', 'modelSize': 1661, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#doorFrame': {'model': 'com/eteks/sweethome3d/io/resources/doorFrame.obj', 'icon': 'com/eteks/sweethome3d/io/resources/doorFrame.png', 'modelSize': 1281, 'creator': 'eTeks', '_kind': 'doorOrWindow'},
    'eTeks#sliderWindow126x200': {'model': 'com/eteks/sweethome3d/io/resources/sliderWindow126x200.obj', 'icon': 'com/eteks/sweethome3d/io/resources/sliderWindow126x200.png', 'modelSize': 7950, 'creator': 'eTeks', '_kind': 'doorOrWindow'},
    'eTeks#texturableCylinder0': {'model': 'com/eteks/sweethome3d/io/resources/texturableCylinder0/texturableCylinder0.obj', 'icon': 'com/eteks/sweethome3d/io/resources/cylinder.png', 'modelSize': 6394, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#fittedBath': {'model': 'com/eteks/sweethome3d/io/resources/fittedBath.obj', 'icon': 'com/eteks/sweethome3d/io/resources/fittedBath.png', 'modelSize': 87663, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#washbasinWithCabinet': {'model': 'com/eteks/sweethome3d/io/resources/washbasinWithCabinet.obj', 'icon': 'com/eteks/sweethome3d/io/resources/washbasinWithCabinet.png', 'modelSize': 66142, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#slidingDoors': {'model': 'com/eteks/sweethome3d/io/resources/slidingDoors.obj', 'icon': 'com/eteks/sweethome3d/io/resources/slidingDoors.png', 'modelSize': 6835, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#shower': {'model': 'com/eteks/sweethome3d/io/resources/shower.obj', 'icon': 'com/eteks/sweethome3d/io/resources/shower.png', 'modelSize': 21504, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#electricRadiator': {'model': 'com/eteks/sweethome3d/io/resources/electricRadiator.obj', 'icon': 'com/eteks/sweethome3d/io/resources/electricRadiator.png', 'modelSize': 7415, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#hotWaterRadiator': {'model': 'com/eteks/sweethome3d/io/resources/hotWaterRadiator.obj', 'icon': 'com/eteks/sweethome3d/io/resources/hotWaterRadiator.png', 'modelSize': 336022, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#serviceHatch': {'model': 'com/eteks/sweethome3d/io/resources/serviceHatch.obj', 'icon': 'com/eteks/sweethome3d/io/resources/serviceHatch.png', 'modelSize': 2316, 'creator': 'eTeks', '_kind': 'doorOrWindow'},
    'eTeks#fixedWindow85x123': {'model': 'com/eteks/sweethome3d/io/resources/fixedWindow85x123.obj', 'icon': 'com/eteks/sweethome3d/io/resources/fixedWindow85x123.png', 'modelSize': 2198, 'creator': 'eTeks', '_kind': 'doorOrWindow'},
    'eTeks#lightSource': {'model': 'com/eteks/sweethome3d/io/resources/lightSource.obj', 'icon': 'com/eteks/sweethome3d/io/resources/lightSource.png', 'modelSize': 1286, 'creator': 'eTeks', '_kind': 'light'},
    'eTeks#halogenLightSource': {'model': 'com/eteks/sweethome3d/io/resources/lightSource.obj', 'icon': 'com/eteks/sweethome3d/io/resources/halogenLightSource.png', 'modelSize': 1286, 'creator': 'eTeks', '_kind': 'light'},
    'eTeks#incandescentLightSource': {'model': 'com/eteks/sweethome3d/io/resources/lightSource.obj', 'icon': 'com/eteks/sweethome3d/io/resources/incandescentLightSource.png', 'modelSize': 1286, 'creator': 'eTeks', '_kind': 'light'},
    'eTeks#fireglowLightSource': {'model': 'com/eteks/sweethome3d/io/resources/lightSource.obj', 'icon': 'com/eteks/sweethome3d/io/resources/fireglowLightSource.png', 'modelSize': 1286, 'creator': 'eTeks', '_kind': 'light'},
    'eTeks#redLightSource': {'model': 'com/eteks/sweethome3d/io/resources/lightSource.obj', 'icon': 'com/eteks/sweethome3d/io/resources/redLightSource.png', 'modelSize': 1286, 'creator': 'eTeks', '_kind': 'light'},
    'eTeks#greenLightSource': {'model': 'com/eteks/sweethome3d/io/resources/lightSource.obj', 'icon': 'com/eteks/sweethome3d/io/resources/greenLightSource.png', 'modelSize': 1286, 'creator': 'eTeks', '_kind': 'light'},
    'eTeks#blueLightSource': {'model': 'com/eteks/sweethome3d/io/resources/lightSource.obj', 'icon': 'com/eteks/sweethome3d/io/resources/blueLightSource.png', 'modelSize': 1286, 'creator': 'eTeks', '_kind': 'light'},
    'eTeks#magentaLightSource': {'model': 'com/eteks/sweethome3d/io/resources/lightSource.obj', 'icon': 'com/eteks/sweethome3d/io/resources/magentaLightSource.png', 'modelSize': 1286, 'creator': 'eTeks', '_kind': 'light'},
    'eTeks#floorUplight': {'model': 'com/eteks/sweethome3d/io/resources/floorUplight.obj', 'icon': 'com/eteks/sweethome3d/io/resources/floorUplight.png', 'modelSize': 19627, 'creator': 'eTeks', '_kind': 'light'},
    'eTeks#spotlight': {'model': 'com/eteks/sweethome3d/io/resources/spotlight.obj', 'icon': 'com/eteks/sweethome3d/io/resources/spotlight.png', 'modelSize': 9300, 'creator': 'eTeks', '_kind': 'light'},
    'eTeks#pendantLamp': {'model': 'com/eteks/sweethome3d/io/resources/pendantLamp.obj', 'icon': 'com/eteks/sweethome3d/io/resources/pendantLamp.png', 'modelSize': 15723, 'creator': 'eTeks', '_kind': 'light'},
    'eTeks#workLamp': {'model': 'com/eteks/sweethome3d/io/resources/workLamp.obj', 'icon': 'com/eteks/sweethome3d/io/resources/workLamp.png', 'modelSize': 26784, 'creator': 'eTeks', '_kind': 'light'},
    'eTeks#wallUplight': {'model': 'com/eteks/sweethome3d/io/resources/wallUplight.obj', 'icon': 'com/eteks/sweethome3d/io/resources/wallUplight.png', 'modelSize': 5211, 'creator': 'eTeks', '_kind': 'light'},
    'eTeks#roundDoorFrame': {'model': 'com/eteks/sweethome3d/io/resources/roundDoorFrame.obj', 'icon': 'com/eteks/sweethome3d/io/resources/roundDoorFrame.png', 'modelSize': 4396, 'creator': 'eTeks', '_kind': 'doorOrWindow'},
    'eTeks#fixedTriangleWindow85x85': {'model': 'com/eteks/sweethome3d/io/resources/fixedTriangleWindow85x85.obj', 'icon': 'com/eteks/sweethome3d/io/resources/fixedTriangleWindow85x85.png', 'modelSize': 2618, 'creator': 'eTeks', '_kind': 'doorOrWindow'},
    'eTeks#halfRoundWindow': {'model': 'com/eteks/sweethome3d/io/resources/halfRoundWindow.obj', 'icon': 'com/eteks/sweethome3d/io/resources/halfRoundWindow.png', 'modelSize': 8190, 'creator': 'eTeks', '_kind': 'doorOrWindow'},
    'eTeks#roundWindow': {'model': 'com/eteks/sweethome3d/io/resources/roundWindow.obj', 'icon': 'com/eteks/sweethome3d/io/resources/roundWindow.png', 'modelSize': 16819, 'creator': 'eTeks', '_kind': 'doorOrWindow'},
    'eTeks#roundedDoor': {'model': 'com/eteks/sweethome3d/io/resources/roundedDoor.obj', 'icon': 'com/eteks/sweethome3d/io/resources/roundedDoor.png', 'modelSize': 42916, 'creator': 'eTeks', '_kind': 'doorOrWindow'},
    'eTeks#bed': {'model': 'com/eteks/sweethome3d/io/resources/bed.obj', 'icon': 'com/eteks/sweethome3d/io/resources/bed.png', 'modelSize': 24868, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#flatTV': {'model': 'com/eteks/sweethome3d/io/resources/flatTV.obj', 'icon': 'com/eteks/sweethome3d/io/resources/flatTV.png', 'modelSize': 13041, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#flowers': {'model': 'com/eteks/sweethome3d/io/resources/flowers.obj', 'icon': 'com/eteks/sweethome3d/io/resources/flowers.png', 'modelSize': 185791, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#frontDoor': {'model': 'com/eteks/sweethome3d/io/resources/frontDoor.obj', 'icon': 'com/eteks/sweethome3d/io/resources/frontDoor.png', 'modelSize': 24179, 'creator': 'eTeks', '_kind': 'doorOrWindow'},
    'eTeks#kitchenUpperCabinet': {'model': 'com/eteks/sweethome3d/io/resources/kitchenUpperCabinet.obj', 'icon': 'com/eteks/sweethome3d/io/resources/kitchenUpperCabinet.png', 'modelSize': 11850, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#texturableTriangle': {'model': 'com/eteks/sweethome3d/io/resources/texturableTriangle/texturableTriangle.obj', 'icon': 'com/eteks/sweethome3d/io/resources/triangle.png', 'modelSize': 1544, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#spiralStaircase': {'model': 'com/eteks/sweethome3d/io/resources/spiralStaircase.obj', 'icon': 'com/eteks/sweethome3d/io/resources/spiralStaircase.png', 'modelSize': 36584, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#laptop': {'model': 'com/eteks/sweethome3d/io/resources/laptop.obj', 'icon': 'com/eteks/sweethome3d/io/resources/laptop.png', 'modelSize': 45826, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#crib': {'model': 'com/eteks/sweethome3d/io/resources/crib.obj', 'icon': 'com/eteks/sweethome3d/io/resources/crib.png', 'modelSize': 34501, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#fireplace': {'model': 'com/eteks/sweethome3d/io/resources/fireplace.obj', 'icon': 'com/eteks/sweethome3d/io/resources/fireplace.png', 'modelSize': 14508, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#glassDoorCabinet': {'model': 'com/eteks/sweethome3d/io/resources/glassDoorCabinet.obj', 'icon': 'com/eteks/sweethome3d/io/resources/glassDoorCabinet.png', 'modelSize': 44252, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#frame': {'model': 'com/eteks/sweethome3d/io/resources/frame/frame.obj', 'icon': 'com/eteks/sweethome3d/io/resources/frame.png', 'modelSize': 3155, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#garageDoor': {'model': 'com/eteks/sweethome3d/io/resources/garageDoor.obj', 'icon': 'com/eteks/sweethome3d/io/resources/garageDoor.png', 'modelSize': 10637, 'creator': 'eTeks', '_kind': 'doorOrWindow'},
    'eTeks#armchair2': {'model': 'com/eteks/sweethome3d/io/resources/armchair2.obj', 'icon': 'com/eteks/sweethome3d/io/resources/armchair2.png', 'modelSize': 33509, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#sofa2': {'model': 'com/eteks/sweethome3d/io/resources/sofa2.obj', 'icon': 'com/eteks/sweethome3d/io/resources/sofa2.png', 'modelSize': 55383, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#desk': {'model': 'com/eteks/sweethome3d/io/resources/desk.obj', 'icon': 'com/eteks/sweethome3d/io/resources/desk.png', 'modelSize': 16760, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#mannequin': {'model': 'com/eteks/sweethome3d/io/resources/mannequin/mannequin.obj', 'icon': 'com/eteks/sweethome3d/io/resources/mannequin.png', 'modelSize': 133023, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#lamp': {'model': 'com/eteks/sweethome3d/io/resources/lamp.obj', 'icon': 'com/eteks/sweethome3d/io/resources/lamp.png', 'modelSize': 21749, 'creator': 'eTeks', '_kind': 'light'},
    'eTeks#dresser': {'model': 'com/eteks/sweethome3d/io/resources/dresser.obj', 'icon': 'com/eteks/sweethome3d/io/resources/dresser.png', 'modelSize': 22106, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#filledBookcase': {'model': 'com/eteks/sweethome3d/io/resources/filledBookcase.obj', 'icon': 'com/eteks/sweethome3d/io/resources/filledBookcase.png', 'modelSize': 50961, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#aquarium': {'model': 'com/eteks/sweethome3d/io/resources/aquarium.obj', 'icon': 'com/eteks/sweethome3d/io/resources/aquarium.png', 'modelSize': 22044, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#doubleOutwardOpeningWindow': {'model': 'com/eteks/sweethome3d/io/resources/doubleOutwardOpeningWindow.obj', 'icon': 'com/eteks/sweethome3d/io/resources/doubleOutwardOpeningWindow.png', 'modelSize': 26300, 'creator': 'eTeks', '_kind': 'doorOrWindow'},
    'eTeks#railing': {'model': 'com/eteks/sweethome3d/io/resources/railing.obj', 'icon': 'com/eteks/sweethome3d/io/resources/railing.png', 'modelSize': 6781, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#hood': {'model': 'com/eteks/sweethome3d/io/resources/hood.obj', 'icon': 'com/eteks/sweethome3d/io/resources/hood.png', 'modelSize': 10536, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#coffeeTable': {'model': 'com/eteks/sweethome3d/io/resources/coffeeTable.obj', 'icon': 'com/eteks/sweethome3d/io/resources/coffeeTable.png', 'modelSize': 9814, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#table': {'model': 'com/eteks/sweethome3d/io/resources/table.obj', 'icon': 'com/eteks/sweethome3d/io/resources/table.png', 'modelSize': 5486, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#chair2': {'model': 'com/eteks/sweethome3d/io/resources/chair2.obj', 'icon': 'com/eteks/sweethome3d/io/resources/chair2.png', 'modelSize': 16429, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#blind': {'model': 'com/eteks/sweethome3d/io/resources/blind.obj', 'icon': 'com/eteks/sweethome3d/io/resources/blind.png', 'modelSize': 47958, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#curtains': {'model': 'com/eteks/sweethome3d/io/resources/curtains/curtains.obj', 'icon': 'com/eteks/sweethome3d/io/resources/curtains.png', 'modelSize': 38679, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
    'eTeks#oven': {'model': 'com/eteks/sweethome3d/io/resources/oven.obj', 'icon': 'com/eteks/sweethome3d/io/resources/oven.png', 'modelSize': 30619, 'creator': 'eTeks', '_kind': 'pieceOfFurniture'},
}
