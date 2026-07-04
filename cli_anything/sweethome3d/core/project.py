"""Project I/O — read & write `.sh3d` files.

A `.sh3d` file is a ZIP archive that holds either a `Home` entry (Java
serialized binary) or a `Home.xml` entry (the SH3D 7.x schema), plus any
embedded content (textures, 3D models) in numbered entries.

This module reads/writes the **XML form** only. SH3D 7.x readers prioritize
`Home.xml` over `Home`, so a file containing just `Home.xml` is valid and
opens cleanly in SH3D. Older binary-only files (pre-7.0) can be read if the
user re-saves them in SH3D 7.x first.

Format reference: `com.eteks.sweethome3d.io.DefaultHomeOutputStream` and
`com.eteks.sweethome3d.io.HomeXMLExporter`.
"""

from __future__ import annotations

import io
import os
import zipfile
from typing import Optional
from xml.etree import ElementTree as ET

from cli_anything.sweethome3d.core.model import (
    CURRENT_VERSION,
    BackgroundImage,
    Baseboard,
    Camera,
    Compass,
    DimensionLine,
    Environment,
    FurnitureGroup,
    Home,
    Label,
    Level,
    LightSource,
    LightSourceMaterial,
    Material,
    PieceOfFurniture,
    Point,
    Polyline,
    Print,
    Room,
    Sash,
    Shelf,
    TextStyle,
    Texture,
    Transformation,
    Wall,
)
from cli_anything.sweethome3d.core._sh3d_catalog_metadata import (
    SH3D_CATALOG,
    read_catalog_resource,
)

HOME_XML_ENTRY = "Home.xml"
HOME_BINARY_ENTRY = "Home"


# ─────────────────────────────────────────────────────────── XML serialization

def _fmt_float(v: float) -> str:
    """Match SH3D's XMLWriter.floatToString — trim trailing zeros."""
    if v == int(v):
        return str(int(v))
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return s or "0"


def _set_attr(el: ET.Element, key: str, value):
    """Set attribute if value is not None/empty."""
    if value is None:
        return
    if isinstance(value, bool):
        el.set(key, "true" if value else "false")
    elif isinstance(value, float):
        el.set(key, _fmt_float(value))
    elif isinstance(value, int):
        el.set(key, str(value))
    else:
        s = str(value)
        if s:
            el.set(key, s)


def _color_to_str(v: Optional[int]) -> Optional[str]:
    if v is None:
        return None
    # ARGB hex
    return f"{v & 0xFFFFFFFF:08X}"


def _piece_color_to_str(v: Optional[int]) -> Optional[str]:
    """Like `_color_to_str` but forces alpha=FF for furniture color overrides.

    A bare 24-bit RGB value (no alpha bits set) would serialize with
    alpha=00 (fully transparent) and SH3D would render the piece as
    invisible. Environment colors keep their original alpha behaviour
    because alpha=00 there acts as a "use defaults" sentinel.
    """
    if v is None:
        return None
    if v <= 0xFFFFFF:
        v |= 0xFF000000
    return f"{v & 0xFFFFFFFF:08X}"


def _background_to_xml(parent: ET.Element, bg: Optional[BackgroundImage]) -> None:
    if bg is None:
        return
    el = ET.SubElement(parent, "backgroundImage")
    _set_attr(el, "image", bg.image)
    _set_attr(el, "scaleDistance", bg.scaleDistance)
    _set_attr(el, "scaleDistanceXStart", bg.scaleDistanceXStart)
    _set_attr(el, "scaleDistanceYStart", bg.scaleDistanceYStart)
    _set_attr(el, "scaleDistanceXEnd", bg.scaleDistanceXEnd)
    _set_attr(el, "scaleDistanceYEnd", bg.scaleDistanceYEnd)
    if bg.xOrigin:
        _set_attr(el, "xOrigin", bg.xOrigin)
    if bg.yOrigin:
        _set_attr(el, "yOrigin", bg.yOrigin)
    if not bg.visible:
        _set_attr(el, "visible", False)


def _texture_el_to_xml(parent: ET.Element, tx: "Texture",
                       attribute: Optional[str] = None) -> ET.Element:
    """Write a <texture> element directly into parent; return the element.

    When ``attribute`` is provided, writes ``attribute="<name>"`` so SH3D's
    HomeXMLHandler can route the texture to wall/room/environment slots.
    Per-piece and per-material textures pass ``attribute=None``.
    """
    inner = ET.SubElement(parent, "texture")
    if attribute is not None:
        _set_attr(inner, "attribute", attribute)
    _set_attr(inner, "catalogId", tx.catalogId)
    _set_attr(inner, "name", tx.name)
    _set_attr(inner, "image", tx.image)
    if tx.width is not None:
        _set_attr(inner, "width", tx.width)
    if tx.height is not None:
        _set_attr(inner, "height", tx.height)
    _set_attr(inner, "xOffset", tx.xOffset)
    _set_attr(inner, "yOffset", tx.yOffset)
    _set_attr(inner, "angle", tx.angle)
    _set_attr(inner, "scale", tx.scale)
    _set_attr(inner, "creator", tx.creator)
    if tx.fittingArea:
        _set_attr(inner, "fittingArea", True)
    if not tx.leftToRightOriented:
        _set_attr(inner, "leftToRightOriented", False)
    return inner


def _texture_to_xml(parent: ET.Element, tag: str, tx: Optional[Texture]) -> None:
    """Write an attribute-discriminated <texture attribute="..."/> child.

    Matches the format SH3D's HomeXMLExporter emits (see
    HomeXMLExporter#writeTexture). The previous implementation wrote a
    nested ``<leftSideTexture><texture .../></leftSideTexture>`` wrapper,
    which SH3D silently ignores — see HomeXMLHandler line ~721 where the
    reader keys textures by the ``attribute`` field on the ``<texture>``
    element itself.
    """
    if tx is None:
        return
    _texture_el_to_xml(parent, tx, attribute=tag)


def _properties_to_xml(parent: ET.Element, props: dict) -> None:
    """Write <property name="..." value="..."/> children."""
    for key, val in props.items():
        p_el = ET.SubElement(parent, "property")
        _set_attr(p_el, "name", key)
        _set_attr(p_el, "value", val)


def _parse_properties(parent: ET.Element) -> dict:
    """Read <property> children into a dict."""
    return {
        el.get("name", ""): el.get("value", "")
        for el in parent.findall("property")
        if el.get("name")
    }


def _textstyle_to_xml(parent: ET.Element, ts: Optional["TextStyle"],
                      attribute: Optional[str] = None) -> None:
    """Write a <textStyle> element into parent."""
    if ts is None:
        return
    el = ET.SubElement(parent, "textStyle")
    if attribute:
        _set_attr(el, "attribute", attribute)
    _set_attr(el, "fontName", ts.fontName)
    _set_attr(el, "fontSize", ts.fontSize)
    if ts.bold:
        _set_attr(el, "bold", True)
    if ts.italic:
        _set_attr(el, "italic", True)
    if ts.alignment != "CENTER":
        _set_attr(el, "alignment", ts.alignment)


def _parse_textstyle(parent: ET.Element, attribute: Optional[str] = None
                     ) -> Optional["TextStyle"]:
    """Parse a <textStyle> child element with matching attribute (or no attribute)."""
    for ts_el in parent.findall("textStyle"):
        attr = ts_el.get("attribute")
        if attribute is None and attr is None:
            pass  # direct match
        elif attr != attribute:
            continue
        return TextStyle(
            fontSize=_float_attr(ts_el, "fontSize", 18) or 18,
            fontName=ts_el.get("fontName"),
            bold=_bool_attr(ts_el, "bold"),
            italic=_bool_attr(ts_el, "italic"),
            alignment=ts_el.get("alignment", "CENTER"),
        )
    return None


def _baseboard_to_xml(parent: ET.Element, attribute: str,
                      bb: Optional["Baseboard"]) -> None:
    """Write a <baseboard attribute="..."> element."""
    if bb is None:
        return
    el = ET.SubElement(parent, "baseboard")
    _set_attr(el, "attribute", attribute)
    _set_attr(el, "thickness", bb.thickness)
    _set_attr(el, "height", bb.height)
    if bb.color is not None:
        _set_attr(el, "color", _color_to_str(bb.color))
    if bb.texture is not None:
        _texture_el_to_xml(el, bb.texture)


def _catalog_resource_entries(home: Home) -> dict[str, str]:
    """Assign a numeric zip-entry name to each catalog model/icon used.

    Matches SH3D's own `DefaultHomeOutputStream` convention: each unique
    Content object becomes "0", "1", "2"... in the zip, and the XML
    `model=`/`icon=` attributes reference those names. Deduplicates so two
    pieces that share the same model only embed it once.

    Returns: {jar-resource-path -> "N"}  e.g.
        {"com/eteks/sweethome3d/io/resources/doorFrame.obj": "0", ...}
    """
    # Newly-embedded catalog content must NOT reuse zip-entry names already
    # occupied by pieces loaded from an existing .sh3d (their models/icons take
    # "0","1",..., possibly "5/window/..."). Start numbering after the highest
    # existing content id, else the new bytes collide with — and drop — the
    # original models on save (SH3D then reports the file "damaged").
    used_ints: set[int] = set()

    def _note(v):
        if v is None:
            return
        seg = str(v).split("/", 1)[0]
        if seg.isdigit():
            used_ints.add(int(seg))

    def _note_tex(t):
        if t is not None:
            _note(getattr(t, "image", None))

    # Content ids are used by MODELS/ICONS *and* TEXTURES (room floor/ceiling,
    # wall sides, piece + material textures, sky/ground, background images).
    # Miss any of these and new furniture will clobber e.g. the oak floor
    # texture. Scan them all.
    if home.backgroundImage:
        _note(home.backgroundImage.image)
    env = getattr(home, "environment", None)
    if env is not None:
        _note_tex(getattr(env, "skyTexture", None))
        _note_tex(getattr(env, "groundTexture", None))
    for lvl in home.levels:
        if getattr(lvl, "backgroundImage", None):
            _note(lvl.backgroundImage.image)
    for w in home.walls:
        _note_tex(getattr(w, "leftSideTexture", None))
        _note_tex(getattr(w, "rightSideTexture", None))
    for r in home.rooms:
        _note_tex(getattr(r, "floorTexture", None))
        _note_tex(getattr(r, "ceilingTexture", None))
    for f in home.furniture:
        _note(f.model)
        _note(f.icon)
        _note(getattr(f, "planIcon", None))
        _note_tex(getattr(f, "texture", None))
        for m in (getattr(f, "materials", None) or []):
            _note_tex(getattr(m, "texture", None))

    mapping: dict[str, str] = {}
    idx = (max(used_ints) + 1) if used_ints else 0
    for f in home.furniture:
        meta = SH3D_CATALOG.get(f.catalogId) if f.catalogId else None
        if not meta:
            continue
        for key in ("model", "icon"):
            res = meta.get(key)
            if res and res not in mapping:
                mapping[res] = str(idx)
                idx += 1
    return mapping


def home_to_xml(home: Home) -> ET.ElementTree:
    """Serialize a Home to an ElementTree matching the SH3D 7.x schema."""
    root = ET.Element("home")
    _set_attr(root, "version", home.version)
    _set_attr(root, "name", home.name)
    _set_attr(root, "camera",
              "observerCamera" if home.camera == "observerCamera" else "topCamera")
    _set_attr(root, "selectedLevel", home.selectedLevel)
    _set_attr(root, "wallHeight", home.wallHeight)
    if home.basePlanLocked:
        _set_attr(root, "basePlanLocked", True)
    _set_attr(root, "furnitureSortedProperty", home.furnitureSortedProperty)
    if home.furnitureDescendingSorted:
        _set_attr(root, "furnitureDescendingSorted", True)

    # home-level properties
    _properties_to_xml(root, home.properties)
    # furniture visible properties
    for prop_name in home.furnitureVisibleProperties:
        fvp = ET.SubElement(root, "furnitureVisibleProperty")
        _set_attr(fvp, "name", prop_name)

    # environment
    env = ET.SubElement(root, "environment")
    _set_attr(env, "groundColor", _color_to_str(home.environment.groundColor))
    if home.environment.backgroundImageVisibleOnGround3D:
        _set_attr(env, "backgroundImageVisibleOnGround3D", True)
    _set_attr(env, "skyColor", _color_to_str(home.environment.skyColor))
    _set_attr(env, "lightColor", _color_to_str(home.environment.lightColor))
    _set_attr(env, "ceilingLightColor",
              _color_to_str(home.environment.ceilingLightColor))
    _set_attr(env, "wallsAlpha", home.environment.wallsAlpha)
    if home.environment.drawingMode != "FILL":
        _set_attr(env, "drawingMode", home.environment.drawingMode)
    _set_attr(env, "subpartSizeUnderLight",
              home.environment.subpartSizeUnderLight)
    if home.environment.allLevelsVisible:
        _set_attr(env, "allLevelsVisible", True)
    if not home.environment.observerCameraElevationAdjusted:
        _set_attr(env, "observerCameraElevationAdjusted", False)
    _set_attr(env, "photoWidth", home.environment.photoWidth)
    _set_attr(env, "photoHeight", home.environment.photoHeight)
    _set_attr(env, "photoAspectRatio", home.environment.photoAspectRatio)
    _set_attr(env, "photoQuality", home.environment.photoQuality)
    _set_attr(env, "videoWidth", home.environment.videoWidth)
    _set_attr(env, "videoAspectRatio", home.environment.videoAspectRatio)
    _set_attr(env, "videoQuality", home.environment.videoQuality)
    _set_attr(env, "videoSpeed", home.environment.videoSpeed)
    _set_attr(env, "videoFrameRate", home.environment.videoFrameRate)
    _texture_to_xml(env, "skyTexture", home.environment.skyTexture)
    _texture_to_xml(env, "groundTexture", home.environment.groundTexture)
    for cp_cam in home.environment.videoCameraPath:
        cp_tag = "observerCamera" if cp_cam.kind == "observerCamera" else "camera"
        cp_el = ET.SubElement(env, cp_tag)
        _set_attr(cp_el, "attribute", "cameraPath")
        _set_attr(cp_el, "lens", cp_cam.lens)
        _set_attr(cp_el, "x", cp_cam.x)
        _set_attr(cp_el, "y", cp_cam.y)
        _set_attr(cp_el, "z", cp_cam.z)
        _set_attr(cp_el, "yaw", cp_cam.yaw)
        _set_attr(cp_el, "pitch", cp_cam.pitch)
        _set_attr(cp_el, "fieldOfView", cp_cam.fieldOfView)
        _set_attr(cp_el, "time", cp_cam.time)

    # home-level background image (overlay shown on the plan)
    _background_to_xml(root, home.backgroundImage)

    # print settings
    if home.printSettings is not None:
        pr = home.printSettings
        pr_el = ET.SubElement(root, "print")
        _set_attr(pr_el, "headerFormat", pr.headerFormat)
        _set_attr(pr_el, "footerFormat", pr.footerFormat)
        if pr.planScale is not None:
            _set_attr(pr_el, "planScale", pr.planScale)
        if not pr.furniturePrinted:
            _set_attr(pr_el, "furniturePrinted", False)
        if not pr.planPrinted:
            _set_attr(pr_el, "planPrinted", False)
        if not pr.view3DPrinted:
            _set_attr(pr_el, "view3DPrinted", False)
        _set_attr(pr_el, "paperWidth", pr.paperWidth)
        _set_attr(pr_el, "paperHeight", pr.paperHeight)
        _set_attr(pr_el, "paperTopMargin", pr.paperTopMargin)
        _set_attr(pr_el, "paperLeftMargin", pr.paperLeftMargin)
        _set_attr(pr_el, "paperBottomMargin", pr.paperBottomMargin)
        _set_attr(pr_el, "paperRightMargin", pr.paperRightMargin)
        _set_attr(pr_el, "paperOrientation", pr.paperOrientation)
        for level_id in pr.printedLevels:
            pl_el = ET.SubElement(pr_el, "printedLevel")
            _set_attr(pl_el, "level", level_id)

    # compass
    c = ET.SubElement(root, "compass")
    _set_attr(c, "x", home.compass.x)
    _set_attr(c, "y", home.compass.y)
    _set_attr(c, "diameter", home.compass.diameter)
    _set_attr(c, "northDirection", home.compass.northDirection)
    _set_attr(c, "longitude", home.compass.longitude)
    _set_attr(c, "latitude", home.compass.latitude)
    _set_attr(c, "timeZone", home.compass.timeZone)
    if not home.compass.visible:
        _set_attr(c, "visible", False)
    _properties_to_xml(c, home.compass.properties)

    # cameras
    for cam, attribute in [(home.topCamera, "topCamera"),
                            (home.observerCamera, "observerCamera")] + [
                           (sc, "storedCamera") for sc in home.storedCameras]:
        if attribute == "observerCamera":
            tag = "observerCamera"
        elif attribute == "storedCamera":
            # SH3D writes stored observer-cameras as <observerCamera> and stored
            # top-cameras as <camera>; preserving cam.kind keeps that distinction
            # alive across roundtrips.
            tag = "observerCamera" if cam.kind == "observerCamera" else "camera"
        else:
            tag = "camera"
        cam_el = ET.SubElement(root, tag)
        _set_attr(cam_el, "attribute", attribute)
        _set_attr(cam_el, "id", cam.id)
        _set_attr(cam_el, "name", cam.name)
        _set_attr(cam_el, "lens", cam.lens)
        _set_attr(cam_el, "x", cam.x)
        _set_attr(cam_el, "y", cam.y)
        _set_attr(cam_el, "z", cam.z)
        _set_attr(cam_el, "yaw", cam.yaw)
        _set_attr(cam_el, "pitch", cam.pitch)
        _set_attr(cam_el, "fieldOfView", cam.fieldOfView)
        _set_attr(cam_el, "time", cam.time)
        if cam.fixedSize:
            _set_attr(cam_el, "fixedSize", True)
        _set_attr(cam_el, "renderer", cam.renderer)

    # levels
    for lvl in home.levels:
        lvl_el = ET.SubElement(root, "level")
        _set_attr(lvl_el, "id", lvl.id)
        _set_attr(lvl_el, "name", lvl.name)
        _set_attr(lvl_el, "elevation", lvl.elevation)
        _set_attr(lvl_el, "floorThickness", lvl.floorThickness)
        _set_attr(lvl_el, "height", lvl.height)
        _set_attr(lvl_el, "elevationIndex", lvl.elevationIndex)
        _set_attr(lvl_el, "visible", lvl.visible)
        _set_attr(lvl_el, "viewable", lvl.viewable)
        _properties_to_xml(lvl_el, lvl.properties)
        _background_to_xml(lvl_el, lvl.backgroundImage)

    # furniture (pieceOfFurniture, doorOrWindow, light, shelfUnit)
    resource_entries = _catalog_resource_entries(home)

    def _write_piece(parent_el: ET.Element, f: PieceOfFurniture) -> None:
        """Write a piece element into parent_el with full schema fidelity.

        Shared between top-level home pieces and pieces nested inside
        furniture groups so grouped pieces don't silently drop their
        materials / sashes / sources / properties on roundtrip.
        """
        tag = f.kind if f.kind in (
            "pieceOfFurniture", "doorOrWindow", "light", "shelfUnit"
        ) else "pieceOfFurniture"
        cat_meta = SH3D_CATALOG.get(f.catalogId) if f.catalogId else None
        model_path = cat_meta.get("model") if cat_meta else None
        icon_path = cat_meta.get("icon") if cat_meta else None
        model = f.model or resource_entries.get(model_path) if model_path else f.model
        icon = f.icon or resource_entries.get(icon_path) if icon_path else f.icon
        creator = f.creator or (cat_meta and cat_meta.get("creator"))
        model_size = cat_meta.get("modelSize") if (cat_meta and f.model is None) else None

        el = ET.SubElement(parent_el, tag)
        _set_attr(el, "id", f.id)
        _set_attr(el, "level", f.level)
        _set_attr(el, "catalogId", f.catalogId)
        _set_attr(el, "name", f.name)
        _set_attr(el, "creator", creator)
        _set_attr(el, "model", model)
        _set_attr(el, "icon", icon)
        if model_size is not None:
            _set_attr(el, "modelSize", model_size)
        _set_attr(el, "x", f.x)
        _set_attr(el, "y", f.y)
        _set_attr(el, "elevation", f.elevation)
        _set_attr(el, "angle", f.angle)
        _set_attr(el, "pitch", f.pitch)
        _set_attr(el, "roll", f.roll)
        _set_attr(el, "width", f.width)
        _set_attr(el, "depth", f.depth)
        _set_attr(el, "height", f.height)
        _set_attr(el, "planIcon", f.planIcon)
        _set_attr(el, "color", _piece_color_to_str(f.color))
        _set_attr(el, "shininess", f.shininess)
        if f.widthInPlan is not None:
            _set_attr(el, "widthInPlan", f.widthInPlan)
        if f.depthInPlan is not None:
            _set_attr(el, "depthInPlan", f.depthInPlan)
        if f.heightInPlan is not None:
            _set_attr(el, "heightInPlan", f.heightInPlan)
        if f.modelFlags is not None:
            _set_attr(el, "modelFlags", f.modelFlags)
        if f.modelMirrored:
            _set_attr(el, "modelMirrored", True)
        if f.modelRotation is not None:
            _set_attr(el, "modelRotation", f.modelRotation)
        if f.modelCenteredAtOrigin is not None:
            _set_attr(el, "modelCenteredAtOrigin", f.modelCenteredAtOrigin)
        if f.staircaseCutOutShape is not None:
            _set_attr(el, "staircaseCutOutShape", f.staircaseCutOutShape)
        if f.dropOnTopElevation != 1.0:
            _set_attr(el, "dropOnTopElevation", f.dropOnTopElevation)
        if not f.resizable:
            _set_attr(el, "resizable", False)
        if not f.deformable:
            _set_attr(el, "deformable", False)
        if not f.texturable:
            _set_attr(el, "texturable", False)
        if not f.horizontallyRotatable:
            _set_attr(el, "horizontallyRotatable", False)
        if f.doorOrWindowFlag:
            _set_attr(el, "doorOrWindow", True)
        if f.nameAngle:
            _set_attr(el, "nameAngle", f.nameAngle)
        if f.nameXOffset:
            _set_attr(el, "nameXOffset", f.nameXOffset)
        if f.nameYOffset:
            _set_attr(el, "nameYOffset", f.nameYOffset)
        _set_attr(el, "information", f.information)
        _set_attr(el, "license", f.license)
        _set_attr(el, "price", f.price)
        _set_attr(el, "valueAddedTaxPercentage", f.valueAddedTaxPercentage)
        _set_attr(el, "currency", f.currency)
        if not f.visible:
            _set_attr(el, "visible", False)
        if not f.movable:
            _set_attr(el, "movable", False)
        if f.nameVisible:
            _set_attr(el, "nameVisible", True)
        _set_attr(el, "description", f.description)
        if tag == "doorOrWindow":
            _set_attr(el, "wallThickness", f.wallThickness)
            _set_attr(el, "wallDistance",  f.wallDistance)
            _set_attr(el, "wallWidth",     f.wallWidth)
            _set_attr(el, "wallLeft",      f.wallLeft)
            _set_attr(el, "wallTop",       f.wallTop)
            _set_attr(el, "wallHeight",    f.wallHeight)
            _set_attr(el, "cutOutShape", f.cutOutShape)
            if f.boundToWall is not None:
                _set_attr(el, "boundToWall", f.boundToWall)
            if f.wallCutOutOnBothSides:
                _set_attr(el, "wallCutOutOnBothSides", True)
            if not f.widthDepthDeformable:
                _set_attr(el, "widthDepthDeformable", False)
            for sash in f.sashes:
                s_el = ET.SubElement(el, "sash")
                _set_attr(s_el, "xAxis", sash.xAxis)
                _set_attr(s_el, "yAxis", sash.yAxis)
                _set_attr(s_el, "width", sash.width)
                _set_attr(s_el, "startAngle", sash.startAngle)
                _set_attr(s_el, "endAngle", sash.endAngle)
        if tag == "light":
            _set_attr(el, "power", f.power)
            for ls in f.lightSources:
                ls_el = ET.SubElement(el, "lightSource")
                _set_attr(ls_el, "x", ls.x)
                _set_attr(ls_el, "y", ls.y)
                _set_attr(ls_el, "z", ls.z)
                _set_attr(ls_el, "color", _color_to_str(ls.color))
                if ls.diameter is not None:
                    _set_attr(ls_el, "diameter", ls.diameter)
            for lsm in f.lightSourceMaterials:
                lsm_el = ET.SubElement(el, "lightSourceMaterial")
                _set_attr(lsm_el, "name", lsm.name)
        # shelf unit shelves
        if tag == "shelfUnit":
            for sh in f.shelves:
                sh_el = ET.SubElement(el, "shelf")
                if sh.elevation is not None:
                    _set_attr(sh_el, "elevation", sh.elevation)
                if sh.xLower is not None:
                    _set_attr(sh_el, "xLower", sh.xLower)
                if sh.yLower is not None:
                    _set_attr(sh_el, "yLower", sh.yLower)
                if sh.zLower is not None:
                    _set_attr(sh_el, "zLower", sh.zLower)
                if sh.xUpper is not None:
                    _set_attr(sh_el, "xUpper", sh.xUpper)
                if sh.yUpper is not None:
                    _set_attr(sh_el, "yUpper", sh.yUpper)
                if sh.zUpper is not None:
                    _set_attr(sh_el, "zUpper", sh.zUpper)
        # properties (all furniture kinds)
        _properties_to_xml(el, f.properties)
        # nameStyle textStyle (all furniture kinds)
        _textstyle_to_xml(el, f.nameStyle, attribute="nameStyle")
        # furniture texture (if any, written without a wrapper tag directly)
        if f.texture is not None:
            _texture_el_to_xml(el, f.texture)
        # per-material overrides (all furniture kinds)
        for mat in f.materials:
            m_el = ET.SubElement(el, "material")
            _set_attr(m_el, "name", mat.name)
            _set_attr(m_el, "key", mat.key)
            if mat.color is not None:
                _set_attr(m_el, "color", _color_to_str(mat.color))
            if mat.shininess is not None:
                _set_attr(m_el, "shininess", mat.shininess)
            if mat.texture is not None:
                _texture_el_to_xml(m_el, mat.texture)
        # model joint transformations (all furniture kinds)
        for tr in f.modelTransformations:
            t_el = ET.SubElement(el, "transformation")
            _set_attr(t_el, "name", tr.name)
            _set_attr(t_el, "matrix", tr.matrix)

    for f in home.furniture:
        _write_piece(root, f)

    # furniture groups
    def _write_furnituregroup(parent_el: ET.Element, grp: FurnitureGroup) -> None:
        g_el = ET.SubElement(parent_el, "furnitureGroup")
        _set_attr(g_el, "id", grp.id)
        _set_attr(g_el, "level", grp.level)
        _set_attr(g_el, "name", grp.name)
        _set_attr(g_el, "x", grp.x)
        _set_attr(g_el, "y", grp.y)
        _set_attr(g_el, "elevation", grp.elevation)
        if grp.angle:
            _set_attr(g_el, "angle", grp.angle)
        _set_attr(g_el, "width", grp.width)
        _set_attr(g_el, "depth", grp.depth)
        _set_attr(g_el, "height", grp.height)
        _set_attr(g_el, "dropOnTopElevation", grp.dropOnTopElevation)
        if not grp.visible:
            _set_attr(g_el, "visible", False)
        if not grp.movable:
            _set_attr(g_el, "movable", False)
        if grp.modelMirrored:
            _set_attr(g_el, "modelMirrored", True)
        if grp.nameVisible:
            _set_attr(g_el, "nameVisible", True)
        if grp.nameAngle:
            _set_attr(g_el, "nameAngle", grp.nameAngle)
        if grp.nameXOffset:
            _set_attr(g_el, "nameXOffset", grp.nameXOffset)
        if grp.nameYOffset:
            _set_attr(g_el, "nameYOffset", grp.nameYOffset)
        _set_attr(g_el, "price", grp.price)
        _set_attr(g_el, "description", grp.description)
        _set_attr(g_el, "information", grp.information)
        _set_attr(g_el, "license", grp.license)
        _set_attr(g_el, "creator", grp.creator)
        # write child furniture with full schema fidelity (group children
        # come first per DTD). Use the shared piece writer so materials,
        # sashes, light sources, properties, etc. survive a roundtrip.
        for child in grp.furniture:
            if isinstance(child, FurnitureGroup):
                _write_furnituregroup(g_el, child)
            elif isinstance(child, PieceOfFurniture):
                _write_piece(g_el, child)
        _textstyle_to_xml(g_el, grp.nameStyle, attribute="nameStyle")

    for grp in home.furnitureGroups:
        _write_furnituregroup(root, grp)

    # walls
    for w in home.walls:
        el = ET.SubElement(root, "wall")
        _set_attr(el, "id", w.id)
        _set_attr(el, "level", w.level)
        _set_attr(el, "wallAtStart", w.wallAtStart)
        _set_attr(el, "wallAtEnd", w.wallAtEnd)
        _set_attr(el, "xStart", w.xStart)
        _set_attr(el, "yStart", w.yStart)
        _set_attr(el, "xEnd", w.xEnd)
        _set_attr(el, "yEnd", w.yEnd)
        _set_attr(el, "height", w.height)
        if w.heightAtEnd:
            _set_attr(el, "heightAtEnd", w.heightAtEnd)
        _set_attr(el, "thickness", w.thickness)
        if w.arcExtent:
            _set_attr(el, "arcExtent", w.arcExtent)
        _set_attr(el, "pattern", w.pattern)
        _set_attr(el, "topColor", _color_to_str(w.topColor))
        _set_attr(el, "leftSideColor", _color_to_str(w.leftSideColor))
        if w.leftSideShininess:
            _set_attr(el, "leftSideShininess", w.leftSideShininess)
        _set_attr(el, "rightSideColor", _color_to_str(w.rightSideColor))
        if w.rightSideShininess:
            _set_attr(el, "rightSideShininess", w.rightSideShininess)
        _properties_to_xml(el, w.properties)
        _texture_to_xml(el, "leftSideTexture", w.leftSideTexture)
        _texture_to_xml(el, "rightSideTexture", w.rightSideTexture)
        _baseboard_to_xml(el, "leftSideBaseboard", w.leftSideBaseboard)
        _baseboard_to_xml(el, "rightSideBaseboard", w.rightSideBaseboard)

    # rooms
    for r in home.rooms:
        el = ET.SubElement(root, "room")
        _set_attr(el, "id", r.id)
        _set_attr(el, "level", r.level)
        _set_attr(el, "name", r.name)
        if r.nameAngle:
            _set_attr(el, "nameAngle", r.nameAngle)
        if r.nameXOffset:
            _set_attr(el, "nameXOffset", r.nameXOffset)
        if r.nameYOffset != -40:
            _set_attr(el, "nameYOffset", r.nameYOffset)
        if r.areaVisible:
            _set_attr(el, "areaVisible", True)
        if r.areaAngle:
            _set_attr(el, "areaAngle", r.areaAngle)
        if r.areaXOffset:
            _set_attr(el, "areaXOffset", r.areaXOffset)
        if r.areaYOffset:
            _set_attr(el, "areaYOffset", r.areaYOffset)
        if not r.floorVisible:
            _set_attr(el, "floorVisible", False)
        _set_attr(el, "floorColor", _color_to_str(r.floorColor))
        if r.floorShininess:
            _set_attr(el, "floorShininess", r.floorShininess)
        if not r.ceilingVisible:
            _set_attr(el, "ceilingVisible", False)
        _set_attr(el, "ceilingColor", _color_to_str(r.ceilingColor))
        if r.ceilingShininess:
            _set_attr(el, "ceilingShininess", r.ceilingShininess)
        if r.ceilingFlat:
            _set_attr(el, "ceilingFlat", True)
        _properties_to_xml(el, r.properties)
        _textstyle_to_xml(el, r.nameStyle, attribute="nameStyle")
        _textstyle_to_xml(el, r.areaStyle, attribute="areaStyle")
        _texture_to_xml(el, "floorTexture", r.floorTexture)
        _texture_to_xml(el, "ceilingTexture", r.ceilingTexture)
        for p in r.points:
            pt = ET.SubElement(el, "point")
            _set_attr(pt, "x", p.x)
            _set_attr(pt, "y", p.y)

    # polylines
    for p in home.polylines:
        el = ET.SubElement(root, "polyline")
        _set_attr(el, "id", p.id)
        _set_attr(el, "level", p.level)
        _set_attr(el, "thickness", p.thickness)
        if p.capStyle != "BUTT":
            _set_attr(el, "capStyle", p.capStyle)
        if p.joinStyle != "MITER":
            _set_attr(el, "joinStyle", p.joinStyle)
        if p.dashStyle != "SOLID":
            _set_attr(el, "dashStyle", p.dashStyle)
        if p.dashPattern is not None:
            _set_attr(el, "dashPattern", p.dashPattern)
        if p.dashOffset:
            _set_attr(el, "dashOffset", p.dashOffset)
        if p.startArrowStyle != "NONE":
            _set_attr(el, "startArrowStyle", p.startArrowStyle)
        if p.endArrowStyle != "NONE":
            _set_attr(el, "endArrowStyle", p.endArrowStyle)
        if p.elevation is not None:
            _set_attr(el, "elevation", p.elevation)
        _set_attr(el, "color", _color_to_str(p.color))
        if p.closedPath:
            _set_attr(el, "closedPath", True)
        if p.visibleIn3D:
            _set_attr(el, "visibleIn3D", True)
        for pt_data in p.points:
            pt = ET.SubElement(el, "point")
            _set_attr(pt, "x", pt_data.x)
            _set_attr(pt, "y", pt_data.y)

    # dimensionLines
    for d in home.dimensionLines:
        el = ET.SubElement(root, "dimensionLine")
        _set_attr(el, "id", d.id)
        _set_attr(el, "level", d.level)
        _set_attr(el, "xStart", d.xStart)
        _set_attr(el, "yStart", d.yStart)
        if d.elevationStart:
            _set_attr(el, "elevationStart", d.elevationStart)
        _set_attr(el, "xEnd", d.xEnd)
        _set_attr(el, "yEnd", d.yEnd)
        if d.elevationEnd:
            _set_attr(el, "elevationEnd", d.elevationEnd)
        _set_attr(el, "offset", d.offset)
        if d.endMarkSize != 10:
            _set_attr(el, "endMarkSize", d.endMarkSize)
        if d.pitch:
            _set_attr(el, "pitch", d.pitch)
        _set_attr(el, "color", _color_to_str(d.color))
        if d.visibleIn3D:
            _set_attr(el, "visibleIn3D", True)
        _textstyle_to_xml(el, d.lengthStyle, attribute="lengthStyle")

    # labels
    for lb in home.labels:
        el = ET.SubElement(root, "label")
        _set_attr(el, "id", lb.id)
        _set_attr(el, "level", lb.level)
        _set_attr(el, "x", lb.x)
        _set_attr(el, "y", lb.y)
        if lb.angle:
            _set_attr(el, "angle", lb.angle)
        if lb.elevation:
            _set_attr(el, "elevation", lb.elevation)
        if lb.pitch is not None:
            _set_attr(el, "pitch", lb.pitch)
        _set_attr(el, "color", _color_to_str(lb.color))
        _set_attr(el, "outlineColor", _color_to_str(lb.outlineColor))
        # label textStyle (no attribute discriminator per DTD)
        _textstyle_to_xml(el, lb.style)
        # text is element body
        text_el = ET.SubElement(el, "text")
        text_el.text = lb.text

    return ET.ElementTree(root)


# ─────────────────────────────────────────────────────────── XML deserialization

def _color_from_str(s: Optional[str]) -> Optional[int]:
    if s is None:
        return None
    try:
        return int(s, 16)
    except ValueError:
        return None


def _float_attr(el: ET.Element, name: str, default: Optional[float] = None) -> Optional[float]:
    v = el.get(name)
    if v is None:
        return default
    try:
        return float(v)
    except ValueError:
        return default


def _int_attr(el: ET.Element, name: str, default: Optional[int] = None) -> Optional[int]:
    v = el.get(name)
    if v is None:
        return default
    try:
        return int(float(v))
    except ValueError:
        return default


def _bool_attr(el: ET.Element, name: str, default: bool = False) -> bool:
    v = el.get(name)
    if v is None:
        return default
    return v.lower() == "true"


def _parse_furniture_el(el: ET.Element, kind: str) -> PieceOfFurniture:
    """Parse a single pieceOfFurniture/doorOrWindow/light element into a PieceOfFurniture."""
    return PieceOfFurniture(
        kind=kind,
        id=el.get("id") or "",
        level=el.get("level"),
        catalogId=el.get("catalogId"),
        name=el.get("name") or "",
        creator=el.get("creator"),
        model=el.get("model"),
        icon=el.get("icon"),
        planIcon=el.get("planIcon"),
        x=_float_attr(el, "x", 0) or 0,
        y=_float_attr(el, "y", 0) or 0,
        elevation=_float_attr(el, "elevation", 0) or 0,
        angle=_float_attr(el, "angle", 0) or 0,
        pitch=_float_attr(el, "pitch", 0) or 0,
        roll=_float_attr(el, "roll", 0) or 0,
        width=_float_attr(el, "width", 0) or 0,
        depth=_float_attr(el, "depth", 0) or 0,
        height=_float_attr(el, "height", 0) or 0,
        widthInPlan=_float_attr(el, "widthInPlan"),
        depthInPlan=_float_attr(el, "depthInPlan"),
        heightInPlan=_float_attr(el, "heightInPlan"),
        modelFlags=_int_attr(el, "modelFlags"),
        modelMirrored=_bool_attr(el, "modelMirrored"),
        modelRotation=el.get("modelRotation"),
        modelCenteredAtOrigin=(
            _bool_attr(el, "modelCenteredAtOrigin")
            if el.get("modelCenteredAtOrigin") is not None else None
        ),
        staircaseCutOutShape=el.get("staircaseCutOutShape"),
        dropOnTopElevation=_float_attr(el, "dropOnTopElevation", 1.0) or 1.0,
        resizable=_bool_attr(el, "resizable", True),
        deformable=_bool_attr(el, "deformable", True),
        texturable=_bool_attr(el, "texturable", True),
        horizontallyRotatable=_bool_attr(el, "horizontallyRotatable", True),
        doorOrWindowFlag=_bool_attr(el, "doorOrWindow"),
        nameAngle=_float_attr(el, "nameAngle", 0) or 0,
        nameXOffset=_float_attr(el, "nameXOffset", 0) or 0,
        nameYOffset=_float_attr(el, "nameYOffset", 0) or 0,
        information=el.get("information"),
        license=el.get("license"),
        price=el.get("price"),
        valueAddedTaxPercentage=el.get("valueAddedTaxPercentage"),
        currency=el.get("currency"),
        color=_color_from_str(el.get("color")),
        shininess=_float_attr(el, "shininess", 0) or 0,
        visible=_bool_attr(el, "visible", True),
        movable=_bool_attr(el, "movable", True),
        nameVisible=_bool_attr(el, "nameVisible"),
        description=el.get("description"),
        wallThickness=_float_attr(el, "wallThickness") if kind == "doorOrWindow" else None,
        wallDistance=_float_attr(el, "wallDistance") if kind == "doorOrWindow" else None,
        wallWidth=_float_attr(el, "wallWidth") if kind == "doorOrWindow" else None,
        wallLeft=_float_attr(el, "wallLeft") if kind == "doorOrWindow" else None,
        wallTop=_float_attr(el, "wallTop") if kind == "doorOrWindow" else None,
        wallHeight=_float_attr(el, "wallHeight") if kind == "doorOrWindow" else None,
        cutOutShape=el.get("cutOutShape") if kind == "doorOrWindow" else None,
        boundToWall=(_bool_attr(el, "boundToWall", True)
                     if kind == "doorOrWindow" and el.get("boundToWall") is not None
                     else None),
        wallCutOutOnBothSides=(
            _bool_attr(el, "wallCutOutOnBothSides")
            if kind == "doorOrWindow" else False
        ),
        widthDepthDeformable=(
            _bool_attr(el, "widthDepthDeformable", True)
            if kind == "doorOrWindow" else True
        ),
        power=_float_attr(el, "power") if kind == "light" else None,
        sashes=[
            Sash(
                xAxis=_float_attr(s, "xAxis", 0) or 0,
                yAxis=_float_attr(s, "yAxis", 0) or 0,
                width=_float_attr(s, "width", 1) or 1,
                startAngle=_float_attr(s, "startAngle", 0) or 0,
                endAngle=_float_attr(s, "endAngle", 0) or 0,
            )
            for s in el.findall("sash")
        ] if kind == "doorOrWindow" else [],
        lightSources=[
            LightSource(
                x=_float_attr(ls, "x", 0) or 0,
                y=_float_attr(ls, "y", 0) or 0,
                z=_float_attr(ls, "z", 0) or 0,
                color=_color_from_str(ls.get("color")) or 0xFFFFFFFF,
                diameter=_float_attr(ls, "diameter"),
            )
            for ls in el.findall("lightSource")
        ] if kind == "light" else [],
        lightSourceMaterials=[
            LightSourceMaterial(name=lsm.get("name") or "")
            for lsm in el.findall("lightSourceMaterial")
        ] if kind == "light" else [],
        materials=[
            Material(
                name=m.get("name") or "",
                key=m.get("key"),
                color=_color_from_str(m.get("color")),
                shininess=_float_attr(m, "shininess"),
                texture=(
                    _parse_texture_el(m.find("texture"))
                    if m.find("texture") is not None else None
                ),
            )
            for m in el.findall("material")
        ],
        modelTransformations=[
            Transformation(
                name=t.get("name") or "",
                matrix=t.get("matrix") or "",
            )
            for t in el.findall("transformation")
        ],
        nameStyle=_parse_textstyle(el, "nameStyle"),
        texture=(
            _parse_texture_el(el.find("texture"))
            if el.find("texture") is not None else None
        ),
        properties=_parse_properties(el),
        shelves=[
            Shelf(
                elevation=_float_attr(sh, "elevation"),
                xLower=_float_attr(sh, "xLower"),
                yLower=_float_attr(sh, "yLower"),
                zLower=_float_attr(sh, "zLower"),
                xUpper=_float_attr(sh, "xUpper"),
                yUpper=_float_attr(sh, "yUpper"),
                zUpper=_float_attr(sh, "zUpper"),
            )
            for sh in el.findall("shelf")
        ] if kind == "shelfUnit" else [],
    )


def _parse_furnituregroup_el(el: ET.Element) -> FurnitureGroup:
    """Recursively parse a <furnitureGroup> element."""
    children = []
    for child in el:
        if child.tag == "furnitureGroup":
            children.append(_parse_furnituregroup_el(child))
        elif child.tag in ("pieceOfFurniture", "doorOrWindow", "light"):
            children.append(_parse_furniture_el(child, child.tag))
    return FurnitureGroup(
        id=el.get("id") or "",
        name=el.get("name") or "",
        level=el.get("level"),
        x=_float_attr(el, "x"),
        y=_float_attr(el, "y"),
        elevation=_float_attr(el, "elevation"),
        angle=_float_attr(el, "angle", 0) or 0,
        width=_float_attr(el, "width"),
        depth=_float_attr(el, "depth"),
        height=_float_attr(el, "height"),
        dropOnTopElevation=_float_attr(el, "dropOnTopElevation"),
        visible=_bool_attr(el, "visible", True),
        movable=_bool_attr(el, "movable", True),
        modelMirrored=_bool_attr(el, "modelMirrored"),
        nameVisible=_bool_attr(el, "nameVisible"),
        nameAngle=_float_attr(el, "nameAngle", 0) or 0,
        nameXOffset=_float_attr(el, "nameXOffset", 0) or 0,
        nameYOffset=_float_attr(el, "nameYOffset", 0) or 0,
        price=el.get("price"),
        description=el.get("description"),
        information=el.get("information"),
        license=el.get("license"),
        creator=el.get("creator"),
        nameStyle=_parse_textstyle(el, "nameStyle"),
        furniture=children,
    )


def _parse_background(parent: ET.Element) -> Optional[BackgroundImage]:
    el = parent.find("backgroundImage")
    if el is None:
        return None
    img = el.get("image")
    if not img:
        return None
    return BackgroundImage(
        image=img,
        scaleDistance=_float_attr(el, "scaleDistance", 100) or 100,
        scaleDistanceXStart=_float_attr(el, "scaleDistanceXStart", 0) or 0,
        scaleDistanceYStart=_float_attr(el, "scaleDistanceYStart", 0) or 0,
        scaleDistanceXEnd=_float_attr(el, "scaleDistanceXEnd", 0) or 0,
        scaleDistanceYEnd=_float_attr(el, "scaleDistanceYEnd", 0) or 0,
        xOrigin=_float_attr(el, "xOrigin", 0) or 0,
        yOrigin=_float_attr(el, "yOrigin", 0) or 0,
        visible=_bool_attr(el, "visible", True),
    )


def _parse_texture_el(tex: ET.Element) -> Texture:
    """Parse a <texture> element directly."""
    return Texture(
        catalogId=tex.get("catalogId"),
        name=tex.get("name"),
        image=tex.get("image"),
        width=_float_attr(tex, "width"),
        height=_float_attr(tex, "height"),
        xOffset=_float_attr(tex, "xOffset", 0) or 0,
        yOffset=_float_attr(tex, "yOffset", 0) or 0,
        angle=_float_attr(tex, "angle", 0) or 0,
        scale=_float_attr(tex, "scale", 1) or 1,
        creator=tex.get("creator"),
        fittingArea=_bool_attr(tex, "fittingArea"),
        leftToRightOriented=_bool_attr(tex, "leftToRightOriented", True),
    )


def _parse_texture(parent: ET.Element, tag: str) -> Optional[Texture]:
    """Find a texture by attribute discriminator (canonical SH3D format).

    Reads ``<texture attribute="<tag>" ... />`` children of *parent*. Falls
    back to the legacy nested ``<<tag>><texture .../></<tag>>`` wrapper so
    files written by older versions of this harness still load.
    """
    for tex in parent.findall("texture"):
        if tex.get("attribute") == tag:
            return _parse_texture_el(tex)
    wrapper = parent.find(tag)
    if wrapper is not None:
        tex = wrapper.find("texture")
        if tex is not None:
            return _parse_texture_el(tex)
    return None


def _parse_baseboard(parent: ET.Element, attribute: str) -> Optional["Baseboard"]:
    """Parse a <baseboard attribute="..."> child element."""
    from cli_anything.sweethome3d.core.model import Baseboard
    for bb in parent.findall("baseboard"):
        if bb.get("attribute") == attribute:
            thickness = _float_attr(bb, "thickness", 1.0) or 1.0
            height = _float_attr(bb, "height", 10.0) or 10.0
            color = _color_from_str(bb.get("color"))
            tex_el = bb.find("texture")
            texture = _parse_texture_el(tex_el) if tex_el is not None else None
            return Baseboard(thickness=thickness, height=height,
                             color=color, texture=texture)
    return None


def xml_to_home(tree: ET.ElementTree) -> Home:
    """Parse a `Home.xml` ElementTree into a Home model."""
    root = tree.getroot()
    if root.tag != "home":
        raise ValueError(f"expected <home> root, got <{root.tag}>")
    home = Home(
        name=root.get("name"),
        version=_int_attr(root, "version", CURRENT_VERSION) or CURRENT_VERSION,
        camera=root.get("camera") or "topCamera",
        wallHeight=_float_attr(root, "wallHeight", 250) or 250,
        basePlanLocked=_bool_attr(root, "basePlanLocked"),
        furnitureSortedProperty=root.get("furnitureSortedProperty"),
        furnitureDescendingSorted=_bool_attr(root, "furnitureDescendingSorted"),
        selectedLevel=root.get("selectedLevel"),
    )

    # home-level properties
    home.properties = _parse_properties(root)
    # furniture visible properties
    home.furnitureVisibleProperties = [
        el.get("name", "")
        for el in root.findall("furnitureVisibleProperty")
        if el.get("name")
    ]

    # home-level background image (sits between environment and compass)
    home.backgroundImage = _parse_background(root)

    # print settings
    pr_el = root.find("print")
    if pr_el is not None:
        home.printSettings = Print(
            headerFormat=pr_el.get("headerFormat"),
            footerFormat=pr_el.get("footerFormat"),
            planScale=_float_attr(pr_el, "planScale"),
            furniturePrinted=_bool_attr(pr_el, "furniturePrinted", True),
            planPrinted=_bool_attr(pr_el, "planPrinted", True),
            view3DPrinted=_bool_attr(pr_el, "view3DPrinted", True),
            paperWidth=_float_attr(pr_el, "paperWidth", 210) or 210,
            paperHeight=_float_attr(pr_el, "paperHeight", 297) or 297,
            paperTopMargin=_float_attr(pr_el, "paperTopMargin", 10) or 10,
            paperLeftMargin=_float_attr(pr_el, "paperLeftMargin", 10) or 10,
            paperBottomMargin=_float_attr(pr_el, "paperBottomMargin", 10) or 10,
            paperRightMargin=_float_attr(pr_el, "paperRightMargin", 10) or 10,
            paperOrientation=pr_el.get("paperOrientation", "PORTRAIT"),
            printedLevels=[pl.get("level") or ""
                           for pl in pr_el.findall("printedLevel")],
        )

    # environment
    env_el = root.find("environment")
    if env_el is not None:
        # parse video camera path keyframes
        env_cam_path = []
        for cp_el in list(env_el.findall("camera")) + list(env_el.findall("observerCamera")):
            if cp_el.get("attribute") == "cameraPath":
                env_cam_path.append(Camera(
                    kind="observerCamera" if cp_el.tag == "observerCamera" else "topCamera",
                    lens=cp_el.get("lens", "PINHOLE"),
                    x=_float_attr(cp_el, "x", 0) or 0,
                    y=_float_attr(cp_el, "y", 0) or 0,
                    z=_float_attr(cp_el, "z", 170) or 170,
                    yaw=_float_attr(cp_el, "yaw", 0) or 0,
                    pitch=_float_attr(cp_el, "pitch", 0) or 0,
                    fieldOfView=_float_attr(cp_el, "fieldOfView", 1.0) or 1.0,
                    time=_int_attr(cp_el, "time"),
                ))
        home.environment = Environment(
            skyColor=_color_from_str(env_el.get("skyColor")),
            groundColor=_color_from_str(env_el.get("groundColor")),
            lightColor=_color_from_str(env_el.get("lightColor")),
            ceilingLightColor=_color_from_str(env_el.get("ceilingLightColor")),
            wallsAlpha=_float_attr(env_el, "wallsAlpha", 0) or 0,
            drawingMode=env_el.get("drawingMode", "FILL"),
            subpartSizeUnderLight=_float_attr(env_el, "subpartSizeUnderLight", 0) or 0,
            allLevelsVisible=_bool_attr(env_el, "allLevelsVisible"),
            observerCameraElevationAdjusted=_bool_attr(
                env_el, "observerCameraElevationAdjusted", True),
            backgroundImageVisibleOnGround3D=_bool_attr(
                env_el, "backgroundImageVisibleOnGround3D"),
            photoWidth=_int_attr(env_el, "photoWidth", 400) or 400,
            photoHeight=_int_attr(env_el, "photoHeight", 300) or 300,
            photoAspectRatio=env_el.get("photoAspectRatio", "VIEW_3D_RATIO"),
            photoQuality=_int_attr(env_el, "photoQuality", 0) or 0,
            videoWidth=_int_attr(env_el, "videoWidth", 320) or 320,
            videoAspectRatio=env_el.get("videoAspectRatio", "RATIO_4_3"),
            videoQuality=_int_attr(env_el, "videoQuality", 0) or 0,
            videoSpeed=_float_attr(env_el, "videoSpeed", 240) or 240,
            videoFrameRate=_int_attr(env_el, "videoFrameRate", 25) or 25,
            skyTexture=_parse_texture(env_el, "skyTexture"),
            groundTexture=_parse_texture(env_el, "groundTexture"),
            videoCameraPath=env_cam_path,
        )

    # compass
    comp_el = root.find("compass")
    if comp_el is not None:
        home.compass = Compass(
            x=_float_attr(comp_el, "x", 50) or 50,
            y=_float_attr(comp_el, "y", 50) or 50,
            diameter=_float_attr(comp_el, "diameter", 100) or 100,
            northDirection=_float_attr(comp_el, "northDirection", 0) or 0,
            longitude=_float_attr(comp_el, "longitude"),
            latitude=_float_attr(comp_el, "latitude"),
            timeZone=comp_el.get("timeZone"),
            visible=_bool_attr(comp_el, "visible", True),
            properties=_parse_properties(comp_el),
        )

    # cameras
    for cam_el in root.findall("camera") + root.findall("observerCamera"):
        attribute = cam_el.get("attribute") or cam_el.tag
        if attribute == "observerCamera":
            kind = "observerCamera"
        elif attribute == "storedCamera":
            # The XML tag of a stored camera reveals whether it was an
            # observer or top camera at the moment it was snapshotted.
            kind = "observerCamera" if cam_el.tag == "observerCamera" else "topCamera"
        else:
            kind = "topCamera"
        cam = Camera(
            kind=kind,
            id=cam_el.get("id"),
            name=cam_el.get("name"),
            lens=cam_el.get("lens", "PINHOLE"),
            x=_float_attr(cam_el, "x", 0) or 0,
            y=_float_attr(cam_el, "y", 0) or 0,
            z=_float_attr(cam_el, "z", 1000) or 1000,
            yaw=_float_attr(cam_el, "yaw", 0) or 0,
            pitch=_float_attr(cam_el, "pitch", 0) or 0,
            fieldOfView=_float_attr(cam_el, "fieldOfView", 1.0) or 1.0,
            time=_int_attr(cam_el, "time"),
            fixedSize=_bool_attr(cam_el, "fixedSize"),
            renderer=cam_el.get("renderer"),
        )
        if attribute == "observerCamera":
            home.observerCamera = cam
        elif attribute == "storedCamera":
            home.storedCameras.append(cam)
        else:
            home.topCamera = cam

    # levels
    for el in root.findall("level"):
        home.levels.append(Level(
            id=el.get("id") or "",
            name=el.get("name") or "Level",
            elevation=_float_attr(el, "elevation", 0) or 0,
            floorThickness=_float_attr(el, "floorThickness", 12) or 12,
            height=_float_attr(el, "height", 250) or 250,
            elevationIndex=_int_attr(el, "elevationIndex", 0) or 0,
            visible=_bool_attr(el, "visible", True),
            viewable=_bool_attr(el, "viewable", True),
            backgroundImage=_parse_background(el),
            properties=_parse_properties(el),
        ))

    # furniture
    for kind in ("pieceOfFurniture", "doorOrWindow", "light", "shelfUnit"):
        for el in root.findall(kind):
            home.furniture.append(_parse_furniture_el(el, kind))

    # furniture groups
    for el in root.findall("furnitureGroup"):
        home.furnitureGroups.append(_parse_furnituregroup_el(el))

    # walls
    for el in root.findall("wall"):
        home.walls.append(Wall(
            id=el.get("id") or "",
            level=el.get("level"),
            wallAtStart=el.get("wallAtStart"),
            wallAtEnd=el.get("wallAtEnd"),
            xStart=_float_attr(el, "xStart", 0) or 0,
            yStart=_float_attr(el, "yStart", 0) or 0,
            xEnd=_float_attr(el, "xEnd", 0) or 0,
            yEnd=_float_attr(el, "yEnd", 0) or 0,
            height=_float_attr(el, "height", 250) or 250,
            heightAtEnd=_float_attr(el, "heightAtEnd", 0) or 0,
            thickness=_float_attr(el, "thickness", 7.5) or 7.5,
            arcExtent=_float_attr(el, "arcExtent", 0) or 0,
            pattern=el.get("pattern"),
            topColor=_color_from_str(el.get("topColor")),
            leftSideColor=_color_from_str(el.get("leftSideColor")),
            rightSideColor=_color_from_str(el.get("rightSideColor")),
            leftSideShininess=_float_attr(el, "leftSideShininess", 0) or 0,
            rightSideShininess=_float_attr(el, "rightSideShininess", 0) or 0,
            leftSideTexture=_parse_texture(el, "leftSideTexture"),
            rightSideTexture=_parse_texture(el, "rightSideTexture"),
            leftSideBaseboard=_parse_baseboard(el, "leftSideBaseboard"),
            rightSideBaseboard=_parse_baseboard(el, "rightSideBaseboard"),
            properties=_parse_properties(el),
        ))

    # rooms
    for el in root.findall("room"):
        points = [Point(_float_attr(p, "x", 0) or 0,
                         _float_attr(p, "y", 0) or 0)
                   for p in el.findall("point")]
        home.rooms.append(Room(
            points=points,
            id=el.get("id") or "",
            level=el.get("level"),
            name=el.get("name"),
            nameAngle=_float_attr(el, "nameAngle", 0) or 0,
            nameXOffset=_float_attr(el, "nameXOffset", 0) or 0,
            nameYOffset=_float_attr(el, "nameYOffset", -40) or -40,
            areaVisible=_bool_attr(el, "areaVisible"),
            areaAngle=_float_attr(el, "areaAngle", 0) or 0,
            areaXOffset=_float_attr(el, "areaXOffset", 0) or 0,
            areaYOffset=_float_attr(el, "areaYOffset", 0) or 0,
            floorVisible=_bool_attr(el, "floorVisible", True),
            floorColor=_color_from_str(el.get("floorColor")),
            floorShininess=_float_attr(el, "floorShininess", 0) or 0,
            ceilingVisible=_bool_attr(el, "ceilingVisible", True),
            ceilingColor=_color_from_str(el.get("ceilingColor")),
            ceilingShininess=_float_attr(el, "ceilingShininess", 0) or 0,
            ceilingFlat=_bool_attr(el, "ceilingFlat"),
            floorTexture=_parse_texture(el, "floorTexture"),
            ceilingTexture=_parse_texture(el, "ceilingTexture"),
            nameStyle=_parse_textstyle(el, "nameStyle"),
            areaStyle=_parse_textstyle(el, "areaStyle"),
            properties=_parse_properties(el),
        ))

    # polylines
    for el in root.findall("polyline"):
        points = [Point(_float_attr(p, "x", 0) or 0,
                         _float_attr(p, "y", 0) or 0)
                   for p in el.findall("point")]
        home.polylines.append(Polyline(
            points=points,
            id=el.get("id") or "",
            level=el.get("level"),
            thickness=_float_attr(el, "thickness", 1) or 1,
            capStyle=el.get("capStyle", "BUTT"),
            joinStyle=el.get("joinStyle", "MITER"),
            dashStyle=el.get("dashStyle", "SOLID"),
            dashPattern=el.get("dashPattern"),
            dashOffset=_float_attr(el, "dashOffset", 0) or 0,
            startArrowStyle=el.get("startArrowStyle", "NONE"),
            endArrowStyle=el.get("endArrowStyle", "NONE"),
            color=_color_from_str(el.get("color")),
            closedPath=_bool_attr(el, "closedPath"),
            elevation=_float_attr(el, "elevation"),
            visibleIn3D=_bool_attr(el, "visibleIn3D"),
        ))

    # dimensionLines
    for el in root.findall("dimensionLine"):
        home.dimensionLines.append(DimensionLine(
            id=el.get("id") or "",
            level=el.get("level"),
            xStart=_float_attr(el, "xStart", 0) or 0,
            yStart=_float_attr(el, "yStart", 0) or 0,
            xEnd=_float_attr(el, "xEnd", 0) or 0,
            yEnd=_float_attr(el, "yEnd", 0) or 0,
            offset=_float_attr(el, "offset", 0) or 0,
            elevationStart=_float_attr(el, "elevationStart", 0) or 0,
            elevationEnd=_float_attr(el, "elevationEnd", 0) or 0,
            endMarkSize=_float_attr(el, "endMarkSize", 10) or 10,
            pitch=_float_attr(el, "pitch", 0) or 0,
            color=_color_from_str(el.get("color")),
            visibleIn3D=_bool_attr(el, "visibleIn3D"),
            lengthStyle=_parse_textstyle(el, "lengthStyle"),
        ))

    # labels
    for el in root.findall("label"):
        text_el = el.find("text")
        home.labels.append(Label(
            text=(text_el.text or "") if text_el is not None else "",
            x=_float_attr(el, "x", 0) or 0,
            y=_float_attr(el, "y", 0) or 0,
            id=el.get("id") or "",
            level=el.get("level"),
            angle=_float_attr(el, "angle", 0) or 0,
            elevation=_float_attr(el, "elevation", 0) or 0,
            pitch=_float_attr(el, "pitch"),
            color=_color_from_str(el.get("color")),
            outlineColor=_color_from_str(el.get("outlineColor")),
            style=_parse_textstyle(el, None),
        ))

    return home


# ─────────────────────────────────────────────────────────── .sh3d ZIP I/O

def new_home(name: Optional[str] = None) -> Home:
    """Create a fresh empty Home with sensible defaults."""
    h = Home(name=name)
    # SH3D always has at least one implicit level (level 0) — leave levels empty;
    # objects on home without level= attribute belong to the ground floor.
    return h


def open_home(path: str) -> Home:
    """Read a `.sh3d` file and return its Home model.

    Raises ValueError if the file contains only a binary `Home` entry (no XML).
    Suggest the user re-saves the file in SH3D 7.x to add the XML form.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if HOME_XML_ENTRY in names:
            with z.open(HOME_XML_ENTRY) as f:
                tree = ET.parse(f)
            return xml_to_home(tree)
        if HOME_BINARY_ENTRY in names:
            raise ValueError(
                f"{path} only contains a binary `Home` entry (no `Home.xml`). "
                "Open it in Sweet Home 3D 7.x and re-save to add the XML form, "
                "then re-run this command."
            )
        raise ValueError(f"{path} is not a Sweet Home 3D file "
                          "(missing `Home` and `Home.xml` entries)")


def save_home(home: Home, path: str, *,
              copy_content_from: Optional[str] = None,
              extra_content: Optional[dict[str, bytes]] = None) -> None:
    """Write a Home to a `.sh3d` file (ZIP containing `Home.xml`).

    `copy_content_from` — copy non-Home entries (textures, models, background
                          images) from an existing .sh3d to preserve content.
    `extra_content`     — map of {ZIP entry name → bytes} written verbatim.
                          Used to embed background image PNGs etc.
    """
    home.version = CURRENT_VERSION
    tree = home_to_xml(home)
    xml_buf = io.BytesIO()
    tree.write(xml_buf, encoding="UTF-8", xml_declaration=True)
    xml_bytes = xml_buf.getvalue()

    # Map each catalog jar-resource to the numbered zip-entry name the XML
    # references. Match this exact mapping when writing the bytes so SH3D's
    # content-context lookup finds the model at the same name. The bytes
    # come from the installed Furniture.jar.
    resource_entries = _catalog_resource_entries(home)

    tmp = path + ".tmp"
    written_names: set[str] = set()
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(HOME_XML_ENTRY, xml_bytes)
        written_names.add(HOME_XML_ENTRY)
        # 1. extra_content first (caller's explicit additions take precedence)
        for name, data in (extra_content or {}).items():
            if name in (HOME_XML_ENTRY, HOME_BINARY_ENTRY):
                continue
            z.writestr(name, data)
            written_names.add(name)
        # 2. catalog resources extracted from the installed Furniture.jar
        for resource_path, entry_name in resource_entries.items():
            if entry_name in written_names:
                continue
            data = read_catalog_resource(resource_path)
            if data is not None:
                z.writestr(entry_name, data)
                written_names.add(entry_name)
        # 3. then copy_content_from for anything not already written.
        #    Skip "ContentDigests": it only covers the source file's original
        #    content, so once we add new catalog models the stale digest set
        #    no longer matches and SH3D rejects the file as "damaged". The
        #    digest manifest is optional, so dropping it is safe.
        if copy_content_from and os.path.isfile(copy_content_from):
            with zipfile.ZipFile(copy_content_from) as src:
                for name in src.namelist():
                    if (name in written_names or name == HOME_BINARY_ENTRY
                            or name == "ContentDigests"):
                        continue
                    z.writestr(name, src.read(name))
    os.replace(tmp, path)


def next_content_id(home: Home) -> str:
    """Pick the next free numeric content-entry name (matches SH3D convention)."""
    used: set[str] = set()
    if home.backgroundImage:
        used.add(home.backgroundImage.image)
    for lvl in home.levels:
        if lvl.backgroundImage:
            used.add(lvl.backgroundImage.image)
    for f in home.furniture:
        if f.model: used.add(f.model)
        if f.icon:  used.add(f.icon)
    i = 0
    while str(i) in used:
        i += 1
    return str(i)


def info(home: Home) -> dict:
    """Return a summary dict for the home — counts of every entity type."""
    # rooms_named: list of (level_name, room_name) tuples for non-empty room names
    rooms_named = []
    for room in home.rooms:
        if room.name:  # skip unnamed rooms
            level_name = None
            if room.level:
                # find level with matching id
                for lvl in home.levels:
                    if lvl.id == room.level:
                        level_name = lvl.name
                        break
            rooms_named.append((level_name, room.name))

    # wall_link_rate: fraction of walls with wallAtStart OR wallAtEnd set
    walls_with_links = sum(1 for w in home.walls if w.wallAtStart or w.wallAtEnd)
    wall_link_rate = 1.0 if len(home.walls) == 0 else walls_with_links / len(home.walls)

    return {
        "name": home.name,
        "version": home.version,
        "wallHeight": home.wallHeight,
        "camera": home.camera,
        "levels": len(home.levels),
        "walls": len(home.walls),
        "rooms": len(home.rooms),
        "furniture": len(home.furniture),
        "doors_and_windows": sum(1 for f in home.furniture
                                   if f.kind == "doorOrWindow"),
        "lights": sum(1 for f in home.furniture if f.kind == "light"),
        "dimensionLines": len(home.dimensionLines),
        "labels": len(home.labels),
        "polylines": len(home.polylines),
        "rooms_named": rooms_named,
        "wall_link_rate": wall_link_rate,
    }
