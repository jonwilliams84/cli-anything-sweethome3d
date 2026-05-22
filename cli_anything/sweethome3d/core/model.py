"""Sweet Home 3D data model — Python dataclasses mirroring the SH3D XML schema.

Each class corresponds to an element in the `<home>` XML tree. Field names and
default values match `com.eteks.sweethome3d.io.HomeXMLExporter` (SH3D 7.5).

Schema version: 7400 (SH3D 7.x).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional

# Schema version SH3D writes into <home version="..."/>. SH3D 7.5 uses 7400.
CURRENT_VERSION = 7400


def _gen_id() -> str:
    """Generate a SH3D-style id."""
    # SH3D uses short uuids; ours is 8-char hex prefixed with a discriminator
    # so id collisions are impossible between sessions.
    return uuid.uuid4().hex[:12]


# ─────────────────────────────────────────────────────────────────── primitives


@dataclass
class TextStyle:
    """Text formatting for room names/areas, dimension labels, and furniture names.

    `attribute` is one of: 'nameStyle' | 'areaStyle' | 'lengthStyle' | None
    (None means the style applies directly to the label or furniture name).
    """
    fontSize: float
    fontName: Optional[str] = None
    bold: bool = False
    italic: bool = False
    alignment: str = "CENTER"   # LEFT | CENTER | RIGHT


@dataclass
class Material:
    """Per-material colour/shininess/texture override within a 3D model."""
    name: str
    key: Optional[str] = None
    color: Optional[int] = None        # AARRGGBB
    shininess: Optional[float] = None
    texture: Optional["Texture"] = None


@dataclass
class Transformation:
    """A named 4×3 affine transformation matrix applied to a model joint/bone.

    `matrix` is a space-separated string of 12 floats: m00 m01 m02 m03 ...
    """
    name: str
    matrix: str  # "m00 m01 m02 m03 m10 m11 m12 m13 m20 m21 m22 m23"


@dataclass
class LightSource:
    """A point light emitter within a light furniture piece.

    Positions are in the model's local coordinate space (0–1 normalised).
    """
    x: float
    y: float
    z: float
    color: int           # AARRGGBB
    diameter: Optional[float] = None


@dataclass
class LightSourceMaterial:
    """Names a material group in the light's 3D model that glows."""
    name: str


@dataclass
class Sash:
    """A door/window sash (opening leaf) pivot geometry.

    Coordinates are fractions of the door/window dimensions (0–1).
    """
    xAxis: float
    yAxis: float
    width: float
    startAngle: float
    endAngle: float


@dataclass
class Baseboard:
    """A baseboard (skirting board) on one side of a wall.

    `attribute` is either 'leftSideBaseboard' or 'rightSideBaseboard'.
    """
    thickness: float
    height: float
    color: Optional[int] = None
    texture: Optional["Texture"] = None


@dataclass
class Point:
    """A 2D point used inside room/polyline `<point>` children."""
    x: float
    y: float


@dataclass
class Texture:
    """An external texture reference (file path or catalog id)."""
    catalogId: Optional[str] = None
    name: Optional[str] = None
    image: Optional[str] = None  # CONTENT path (zip entry name)
    width: Optional[float] = None
    height: Optional[float] = None
    xOffset: float = 0
    yOffset: float = 0
    angle: float = 0
    scale: float = 1.0
    creator: Optional[str] = None
    fittingArea: bool = False
    leftToRightOriented: bool = True  # mirror texture on back face


# ─────────────────────────────────────────────────────────────────── elements


@dataclass
class BackgroundImage:
    """A reference floorplan image overlaid on the plan view.

    `image` is the in-ZIP content entry name (e.g. "0"). Scale calibration
    is the two clicked points (XStart, YStart, XEnd, YEnd) in image pixel
    coordinates, plus the real distance (cm) the line represents.
    """
    image: str                                  # ZIP entry name
    scaleDistance: float                        # cm
    scaleDistanceXStart: float                  # px
    scaleDistanceYStart: float                  # px
    scaleDistanceXEnd: float                    # px
    scaleDistanceYEnd: float                    # px
    xOrigin: float = 0
    yOrigin: float = 0
    visible: bool = True


@dataclass
class Level:
    id: str = field(default_factory=_gen_id)
    name: str = "Level"
    elevation: float = 0
    floorThickness: float = 12
    height: float = 250
    elevationIndex: int = 0
    visible: bool = True
    viewable: bool = True
    backgroundImage: Optional["BackgroundImage"] = None
    properties: dict[str, str] = field(default_factory=dict)


@dataclass
class Wall:
    xStart: float
    yStart: float
    xEnd: float
    yEnd: float
    id: str = field(default_factory=_gen_id)
    level: Optional[str] = None        # level id
    height: float = 250
    heightAtEnd: float = 0             # 0 = same as height
    thickness: float = 7.5
    arcExtent: float = 0
    pattern: Optional[str] = "hatchUp"
    topColor: Optional[int] = None
    leftSideColor: Optional[int] = None
    rightSideColor: Optional[int] = None
    leftSideShininess: float = 0
    rightSideShininess: float = 0
    leftSideTexture: Optional[Texture] = None
    rightSideTexture: Optional[Texture] = None
    wallAtStart: Optional[str] = None
    wallAtEnd: Optional[str] = None
    leftSideBaseboard: Optional[Baseboard] = None
    rightSideBaseboard: Optional[Baseboard] = None
    properties: dict[str, str] = field(default_factory=dict)


@dataclass
class Room:
    points: list[Point]
    id: str = field(default_factory=_gen_id)
    level: Optional[str] = None
    name: Optional[str] = None
    nameAngle: float = 0
    nameXOffset: float = 0
    nameYOffset: float = -40
    areaVisible: bool = False
    floorVisible: bool = True
    floorColor: Optional[int] = None
    floorShininess: float = 0
    ceilingVisible: bool = True
    ceilingColor: Optional[int] = None
    ceilingShininess: float = 0
    ceilingFlat: bool = False
    floorTexture: Optional[Texture] = None
    ceilingTexture: Optional[Texture] = None
    nameStyle: Optional["TextStyle"] = None
    areaStyle: Optional["TextStyle"] = None
    areaAngle: float = 0
    areaXOffset: float = 0
    areaYOffset: float = 0
    properties: dict[str, str] = field(default_factory=dict)


@dataclass
class PieceOfFurniture:
    """A piece of furniture instance placed in the home.

    `kind` is one of: pieceOfFurniture | doorOrWindow | light. The XML tag
    differs accordingly; specialized fields (e.g. wallThickness for doors,
    power for lights) live on the same class for simplicity.
    """
    name: str
    x: float
    y: float
    width: float
    depth: float
    height: float
    kind: str = "pieceOfFurniture"
    id: str = field(default_factory=_gen_id)
    catalogId: Optional[str] = None
    level: Optional[str] = None
    elevation: float = 0
    angle: float = 0
    pitch: float = 0
    roll: float = 0
    model: Optional[str] = None        # CONTENT path
    icon: Optional[str] = None
    color: Optional[int] = None
    shininess: float = 0
    visible: bool = True
    movable: bool = True
    nameVisible: bool = False
    creator: Optional[str] = None
    description: Optional[str] = None
    # door/window only
    wallThickness: Optional[float] = None  # fraction of opening width
    wallDistance: Optional[float] = None
    wallWidth: Optional[float] = None      # length of the host wall (cm)
    wallLeft: Optional[float] = None       # offset from wall start to door's left edge (cm)
    wallTop: Optional[float] = None        # offset from top of wall to top of cut (cm)
    wallHeight: Optional[float] = None     # height of the wall cut (cm)
    cutOutShape: Optional[str] = None
    boundToWall: Optional[bool] = None     # None = default (true); false = unbind explicitly
    # light only
    power: Optional[float] = None
    # additional piece attributes (schema completeness)
    planIcon: Optional[str] = None           # CONTENT path for plan-view icon
    widthInPlan: Optional[float] = None      # override width in 2D plan view
    depthInPlan: Optional[float] = None      # override depth in 2D plan view
    heightInPlan: Optional[float] = None     # override height in 2D plan view
    modelFlags: Optional[int] = None         # bitfield: 1=backFaceShown
    modelSize: Optional[int] = None          # hint: original file size in bytes
    modelMirrored: bool = False              # mirror model along width axis
    modelRotation: Optional[str] = None      # 3×3 matrix, 9 space-separated floats
    modelCenteredAtOrigin: Optional[bool] = None  # whether model origin is centred
    staircaseCutOutShape: Optional[str] = None   # SVG path for staircase cut-out
    dropOnTopElevation: float = 1.0          # relative elevation for drop-on-top
    resizable: bool = True                   # whether dimensions can be changed
    deformable: bool = True                  # whether W/D/H can be set independently
    texturable: bool = True                  # whether texture can be applied
    horizontallyRotatable: bool = True       # whether pitch/roll can be set
    doorOrWindowFlag: bool = False           # behaves as door/window (cuts walls)
    nameAngle: float = 0                     # name label rotation (rad)
    nameXOffset: float = 0                   # name label X offset from centre (cm)
    nameYOffset: float = 0                   # name label Y offset from centre (cm)
    information: Optional[str] = None        # additional info (URL etc.)
    license: Optional[str] = None            # license text
    price: Optional[str] = None             # unit price (decimal string)
    valueAddedTaxPercentage: Optional[str] = None  # VAT percentage (decimal string)
    currency: Optional[str] = None          # ISO 4217 currency code
    wallCutOutOnBothSides: bool = False      # cut through both sides of wall
    widthDepthDeformable: bool = True        # width/depth can be resized independently
    lockedInBasePlan: bool = False           # locked in base plan
    # door/window sashes
    sashes: list[Sash] = field(default_factory=list)
    # light sources and light-emitting materials
    lightSources: list[LightSource] = field(default_factory=list)
    lightSourceMaterials: list[LightSourceMaterial] = field(default_factory=list)
    # per-material colour/texture overrides and model joint transformations
    materials: list[Material] = field(default_factory=list)
    modelTransformations: list[Transformation] = field(default_factory=list)
    # text style for name label
    nameStyle: Optional[TextStyle] = None
    # piece texture (one per piece, no attribute discriminator)
    texture: Optional["Texture"] = None
    properties: dict[str, str] = field(default_factory=dict)
    # shelf unit shelves (only meaningful when kind="shelfUnit")
    shelves: list[Shelf] = field(default_factory=list)


@dataclass
class Camera:
    """Top-down (plan) or observer (first-person) camera."""
    kind: str = "topCamera"            # topCamera | observerCamera
    id: Optional[str] = None
    x: float = 0
    y: float = 0
    z: float = 1000
    yaw: float = 0                     # radians
    pitch: float = 0                   # radians (downward positive for topCamera)
    fieldOfView: float = 1.0           # radians
    time: Optional[int] = None         # millis-since-epoch (sun position)
    lens: str = "PINHOLE"              # PINHOLE | NORMAL | FISHEYE | SPHERICAL
    name: Optional[str] = None
    fixedSize: bool = False
    renderer: Optional[str] = None


@dataclass
class DimensionLine:
    xStart: float
    yStart: float
    xEnd: float
    yEnd: float
    offset: float = 0
    id: str = field(default_factory=_gen_id)
    level: Optional[str] = None
    elevationStart: float = 0
    elevationEnd: float = 0
    endMarkSize: float = 10
    pitch: float = 0
    color: Optional[int] = None
    visibleIn3D: bool = False
    lengthStyle: Optional["TextStyle"] = None


@dataclass
class Label:
    text: str
    x: float
    y: float
    id: str = field(default_factory=_gen_id)
    level: Optional[str] = None
    angle: float = 0
    elevation: float = 0
    pitch: Optional[float] = None
    color: Optional[int] = None
    outlineColor: Optional[int] = None
    style: Optional["TextStyle"] = None   # the label's own textStyle (no attribute)


@dataclass
class Polyline:
    points: list[Point]
    id: str = field(default_factory=_gen_id)
    level: Optional[str] = None
    thickness: float = 1
    capStyle: str = "BUTT"
    joinStyle: str = "MITER"
    dashStyle: str = "SOLID"
    dashPattern: Optional[str] = None   # space-separated floats for CUSTOMIZED dash
    dashOffset: float = 0
    startArrowStyle: str = "NONE"
    endArrowStyle: str = "NONE"
    color: Optional[int] = None
    closedPath: bool = False
    elevation: Optional[float] = None
    visibleIn3D: bool = False


@dataclass
class Compass:
    x: float = 50
    y: float = 50
    diameter: float = 100
    northDirection: float = 0          # radians
    longitude: Optional[float] = None
    latitude: Optional[float] = None
    timeZone: Optional[str] = None
    visible: bool = True
    properties: dict[str, str] = field(default_factory=dict)


@dataclass
class Environment:
    """Home-level environment: sky, ground, lighting, photo settings."""
    skyColor: Optional[int] = None         # ARGB int
    groundColor: Optional[int] = None
    lightColor: Optional[int] = None
    ceilingLightColor: Optional[int] = None
    wallsAlpha: float = 0
    drawingMode: str = "FILL"              # FILL | OUTLINE | FILL_AND_OUTLINE
    subpartSizeUnderLight: float = 0
    allLevelsVisible: bool = False
    observerCameraElevationAdjusted: bool = True
    backgroundImageVisibleOnGround3D: bool = False  # project background img on 3D ground
    photoWidth: int = 400
    photoHeight: int = 300
    photoAspectRatio: str = "VIEW_3D_RATIO"
    photoQuality: int = 0
    videoWidth: int = 320
    videoAspectRatio: str = "RATIO_4_3"
    videoQuality: int = 0
    videoSpeed: float = 240
    videoFrameRate: int = 25
    skyTexture: Optional[Texture] = None
    groundTexture: Optional[Texture] = None
    videoCameraPath: list["Camera"] = field(default_factory=list)


@dataclass
class Print:
    """Page layout and print options for SH3D print output.

    `printedLevels` is a list of level IDs to include in the printout.
    """
    paperWidth: float
    paperHeight: float
    paperTopMargin: float
    paperLeftMargin: float
    paperBottomMargin: float
    paperRightMargin: float
    paperOrientation: str  # PORTRAIT | LANDSCAPE | REVERSE_LANDSCAPE
    headerFormat: Optional[str] = None
    footerFormat: Optional[str] = None
    planScale: Optional[float] = None
    furniturePrinted: bool = True
    planPrinted: bool = True
    view3DPrinted: bool = True
    printedLevels: list[str] = field(default_factory=list)  # list of level IDs


@dataclass
class Shelf:
    """A shelf plane or bounding box within a shelf unit.

    Either `elevation` (flat shelf) or the 6 box-bound attributes are set.
    """
    elevation: Optional[float] = None
    xLower: Optional[float] = None
    yLower: Optional[float] = None
    zLower: Optional[float] = None
    xUpper: Optional[float] = None
    yUpper: Optional[float] = None
    zUpper: Optional[float] = None


@dataclass
class FurnitureGroup:
    """A named group of furniture pieces moved/rotated as a unit.

    The `furniture` list may contain `PieceOfFurniture` or nested `FurnitureGroup`
    instances (heterogeneous via Union — both are valid).
    """
    name: str
    furniture: list = field(default_factory=list)  # list[PieceOfFurniture | FurnitureGroup]
    id: str = field(default_factory=_gen_id)
    level: Optional[str] = None
    x: Optional[float] = None
    y: Optional[float] = None
    elevation: Optional[float] = None
    angle: float = 0
    width: Optional[float] = None
    depth: Optional[float] = None
    height: Optional[float] = None
    dropOnTopElevation: Optional[float] = None
    visible: bool = True
    movable: bool = True
    modelMirrored: bool = False
    nameVisible: bool = False
    nameAngle: float = 0
    nameXOffset: float = 0
    nameYOffset: float = 0
    price: Optional[str] = None
    description: Optional[str] = None
    information: Optional[str] = None
    license: Optional[str] = None
    creator: Optional[str] = None
    nameStyle: Optional[TextStyle] = None


# ─────────────────────────────────────────────────────────────────── root


@dataclass
class Home:
    """Root container — corresponds to <home> XML element."""
    name: Optional[str] = None
    version: int = CURRENT_VERSION
    camera: str = "topCamera"              # which camera is active
    wallHeight: float = 250
    basePlanLocked: bool = False
    furnitureSortedProperty: Optional[str] = None
    furnitureDescendingSorted: bool = False
    selectedLevel: Optional[str] = None    # level id

    levels: list[Level] = field(default_factory=list)
    walls: list[Wall] = field(default_factory=list)
    rooms: list[Room] = field(default_factory=list)
    furniture: list[PieceOfFurniture] = field(default_factory=list)
    furnitureGroups: list[FurnitureGroup] = field(default_factory=list)
    furnitureVisibleProperties: list[str] = field(default_factory=list)
    properties: dict[str, str] = field(default_factory=dict)  # key/value metadata
    storedCameras: list[Camera] = field(default_factory=list)
    dimensionLines: list[DimensionLine] = field(default_factory=list)
    labels: list[Label] = field(default_factory=list)
    polylines: list[Polyline] = field(default_factory=list)
    compass: Compass = field(default_factory=Compass)
    environment: Environment = field(default_factory=Environment)
    printSettings: Optional[Print] = None
    observerCamera: Camera = field(default_factory=lambda: Camera(kind="observerCamera", z=170))
    topCamera: Camera = field(default_factory=lambda: Camera(kind="topCamera"))
    backgroundImage: Optional["BackgroundImage"] = None

    def find_level(self, ident: str) -> Optional[Level]:
        for lvl in self.levels:
            if lvl.id == ident or lvl.name == ident:
                return lvl
        return None

    def find_wall(self, ident: str) -> Optional[Wall]:
        for w in self.walls:
            if w.id == ident:
                return w
        return None

    def find_room(self, ident: str) -> Optional[Room]:
        for r in self.rooms:
            if r.id == ident or r.name == ident:
                return r
        return None

    def find_furniture(self, ident: str) -> Optional[PieceOfFurniture]:
        # by id first (exact), then by name (case-insensitive). Also searches
        # recursively inside furniture groups so a piece keeps its edit
        # surface (material, sash, sources, …) after being grouped.
        def _scan(items, want_id: bool):
            for f in items:
                if isinstance(f, FurnitureGroup):
                    hit = _scan(f.furniture, want_id)
                    if hit is not None:
                        return hit
                    continue
                if want_id and f.id == ident:
                    return f
                if (not want_id) and f.name and f.name.lower() == ident.lower():
                    return f
            return None
        # Search top-level + groups by id first; then by name.
        for source in (self.furniture, self.furnitureGroups):
            hit = _scan(source, want_id=True)
            if hit is not None:
                return hit
        for source in (self.furniture, self.furnitureGroups):
            hit = _scan(source, want_id=False)
            if hit is not None:
                return hit
        return None
