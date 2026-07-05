"""Unit tests for cli-anything-sweethome3d core modules."""

from __future__ import annotations

import io
import os
import tempfile
import zipfile
from xml.etree import ElementTree as ET

import pytest

from cli_anything.sweethome3d.core import (
    annotations as ann_core,
    cameras as cam_core,
    environment as env_core,
    export as export_core,
    furniture as furn_core,
    levels as lvl_core,
    project as proj_core,
    rooms as rooms_core,
    walls as walls_core,
)
from cli_anything.sweethome3d.core import model as model_mod
from cli_anything.sweethome3d.core.model import (
    CURRENT_VERSION,
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
    Transformation,
    Wall,
)
from cli_anything.sweethome3d.core.session import Session
from cli_anything.sweethome3d.utils import sweethome3d_backend as backend


# ─── model ──────────────────────────────────────────────────────────────────

class TestModel:
    def test_current_version(self):
        assert CURRENT_VERSION == 7400

    def test_home_defaults(self):
        h = Home()
        assert h.version == 7400
        assert h.wallHeight == 250
        assert h.camera == "topCamera"
        assert h.walls == [] and h.rooms == [] and h.furniture == []

    def test_gen_id_unique(self):
        ids = {model_mod._gen_id() for _ in range(100)}
        assert len(ids) == 100
        for i in ids:
            assert len(i) == 12

    def test_find_furniture_by_name(self):
        h = Home()
        h.furniture.append(PieceOfFurniture(
            name="Sofa", x=0, y=0, width=200, depth=80, height=80))
        # case-insensitive
        assert h.find_furniture("SOFA") is not None
        assert h.find_furniture("sofa").name == "Sofa"

    def test_find_room_by_name_or_id(self):
        h = Home()
        r = Room(points=[Point(0,0), Point(10,0), Point(10,10)], name="Lounge")
        h.rooms.append(r)
        assert h.find_room("Lounge") is r
        assert h.find_room(r.id) is r
        assert h.find_room("ghost") is None


# ─── project (XML) ──────────────────────────────────────────────────────────

class TestProjectXML:
    def test_new_home_empty(self):
        h = proj_core.new_home("X")
        assert h.name == "X"
        assert proj_core.info(h)["walls"] == 0

    def test_home_to_xml_root(self):
        h = proj_core.new_home("MyHouse")
        tree = proj_core.home_to_xml(h)
        root = tree.getroot()
        assert root.tag == "home"
        assert root.get("version") == "7400"
        assert root.get("name") == "MyHouse"
        assert root.get("camera") == "topCamera"

    def test_float_attrs_no_trailing_zeros(self):
        h = proj_core.new_home("F")
        walls_core.add_wall(h, 0, 0, 100, 0)
        tree = proj_core.home_to_xml(h)
        xs = tree.find("wall").get("xStart")
        assert xs == "0"  # not "0.0"
        ys = tree.find("wall").get("xEnd")
        assert ys == "100"

    def test_explicit_zero_float_attr_is_not_coerced_to_default(self):
        """Regression: _float_attr result must not be post-processed with `or default`."""
        xml = b'''<home version="6005"><room nameYOffset="0"><point x="0" y="0"/><point x="100" y="0"/><point x="100" y="100"/></room></home>'''
        tree = ET.parse(io.BytesIO(xml))
        home = proj_core.xml_to_home(tree)
        assert len(home.rooms) == 1
        assert home.rooms[0].nameYOffset == 0

    def test_roundtrip_preserves_walls(self):
        h = proj_core.new_home("RT")
        walls_core.add_wall(h, 0, 0, 500, 0, thickness=10, height=275)
        walls_core.add_wall(h, 500, 0, 500, 400)
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "test.sh3d")
            proj_core.save_home(h, p)
            h2 = proj_core.open_home(p)
        assert len(h2.walls) == 2
        assert h2.walls[0].thickness == 10
        assert h2.walls[0].height == 275

    def test_roundtrip_rooms(self):
        h = proj_core.new_home("R")
        rooms_core.add_rectangle_room(h, 0, 0, 500, 400,
                                        name="Living", areaVisible=True)
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "r.sh3d")
            proj_core.save_home(h, p)
            h2 = proj_core.open_home(p)
        assert h2.rooms[0].name == "Living"
        assert h2.rooms[0].areaVisible is True
        assert len(h2.rooms[0].points) == 4

    def test_roundtrip_furniture(self):
        h = proj_core.new_home("F")
        furn_core.add_piece(h, "Sofa", 100, 100,
                              width=200, depth=80, height=80,
                              color=0xC0C0C0)
        furn_core.add_door(h, "Door1", 250, 0)
        furn_core.add_window(h, "Win1", 250, 400)
        furn_core.add_light(h, "Lamp", 250, 200)
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "f.sh3d")
            proj_core.save_home(h, p)
            h2 = proj_core.open_home(p)
        kinds = sorted(f.kind for f in h2.furniture)
        assert kinds == ["doorOrWindow", "doorOrWindow", "light",
                          "pieceOfFurniture"]
        light = next(f for f in h2.furniture if f.kind == "light")
        assert light.power == 0.5

    def test_roundtrip_dimensions_labels_polylines(self):
        h = proj_core.new_home("ANN")
        ann_core.add_dimension(h, 0, 0, 100, 0)
        ann_core.add_label(h, "North", 50, 50)
        ann_core.add_polyline(h, [(0,0), (50,50), (100, 0)])
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "a.sh3d")
            proj_core.save_home(h, p)
            h2 = proj_core.open_home(p)
        assert len(h2.dimensionLines) == 1
        assert h2.labels[0].text == "North"
        assert len(h2.polylines[0].points) == 3

    def test_save_home_zip_has_only_xml_entry(self):
        h = proj_core.new_home("Z")
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "z.sh3d")
            proj_core.save_home(h, p)
            with zipfile.ZipFile(p) as z:
                assert z.namelist() == ["Home.xml"]

    def test_open_rejects_binary_only_sh3d(self):
        """A .sh3d with only the binary `Home` entry should error helpfully."""
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "binary.sh3d")
            with zipfile.ZipFile(p, "w") as z:
                z.writestr("Home", b"\xac\xed\x00\x05fake")
            with pytest.raises(ValueError, match="binary `Home` entry"):
                proj_core.open_home(p)

    def test_open_rejects_non_sh3d_zip(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "x.sh3d")
            with zipfile.ZipFile(p, "w") as z:
                z.writestr("other", b"x")
            with pytest.raises(ValueError, match="not a Sweet Home 3D file"):
                proj_core.open_home(p)

    def test_info_counts(self):
        h = proj_core.new_home("I")
        walls_core.add_wall(h, 0, 0, 100, 0)
        rooms_core.add_rectangle_room(h, 0, 0, 100, 100)
        furn_core.add_door(h, "D", 50, 0)
        furn_core.add_light(h, "L", 50, 50)
        info = proj_core.info(h)
        assert info["walls"] == 1
        assert info["rooms"] == 1
        assert info["furniture"] == 2
        assert info["doors_and_windows"] == 1
        assert info["lights"] == 1

    def test_lightsource_black_color_is_preserved(self):
        """HIGH-1: explicit black (#000000) light source color must not be
        coerced to the default white because 0x000000 is falsy."""
        xml = b'''<home version="6005">
  <light name="lamp" x="100" y="200" angle="0"
         width="10" depth="10" height="10"
         visible="true" movable="true"
         modelCenteredAtOrigin="true" doorOrWindow="false"
         resizable="true" deformable="true" texturable="true"
         horizontallyRotatable="true">
    <lightSource x="0" y="0" z="10" color="#000000"/>
  </light>
</home>'''
        tree = ET.parse(io.BytesIO(xml))
        home = proj_core.xml_to_home(tree)
        piece = home.furniture[0]
        assert len(piece.lightSources) == 1
        assert piece.lightSources[0].color == 0x000000


# ─── walls ──────────────────────────────────────────────────────────────────

class TestChunk18ShelfUnit:
    def test_shelfunit_roundtrip(self):
        h = proj_core.new_home("SU")
        shelf_unit = PieceOfFurniture(
            kind="shelfUnit",
            name="Billy Bookcase",
            x=100, y=50,
            width=80, depth=28, height=202,
        )
        shelf_unit.shelves = [
            Shelf(elevation=50.0),
            Shelf(elevation=100.0),
            Shelf(xLower=0.0, yLower=0.0, zLower=0.0,
                  xUpper=80.0, yUpper=28.0, zUpper=50.0),
        ]
        h.furniture.append(shelf_unit)
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "su.sh3d")
            proj_core.save_home(h, p)
            h2 = proj_core.open_home(p)
        su2 = h2.furniture[0]
        assert su2.kind == "shelfUnit"
        assert su2.name == "Billy Bookcase"
        assert len(su2.shelves) == 3
        assert su2.shelves[0].elevation == pytest.approx(50.0)
        assert su2.shelves[1].elevation == pytest.approx(100.0)
        assert su2.shelves[2].xLower == pytest.approx(0.0)
        assert su2.shelves[2].zUpper == pytest.approx(50.0)


class TestChunk17Properties:
    def test_home_properties_roundtrip(self):
        h = proj_core.new_home("PROPS")
        h.properties = {
            "com.example.FrameWidth": "1329",
            "com.example.FrameHeight": "768",
        }
        h.furnitureVisibleProperties = ["NAME", "WIDTH", "HEIGHT", "VISIBLE"]
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "props.sh3d")
            proj_core.save_home(h, p)
            h2 = proj_core.open_home(p)
        assert h2.properties.get("com.example.FrameWidth") == "1329"
        assert h2.properties.get("com.example.FrameHeight") == "768"
        assert h2.furnitureVisibleProperties == ["NAME", "WIDTH", "HEIGHT", "VISIBLE"]

    def test_wall_properties_roundtrip(self):
        h = proj_core.new_home("WP")
        w = walls_core.add_wall(h, 0, 0, 100, 0)
        w.properties = {"my.wall.key": "wall_value"}
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "wp.sh3d")
            proj_core.save_home(h, p)
            h2 = proj_core.open_home(p)
        assert h2.walls[0].properties.get("my.wall.key") == "wall_value"

    def test_room_properties_roundtrip(self):
        h = proj_core.new_home("RP")
        rooms_core.add_rectangle_room(h, 0, 0, 100, 100, name="Living")
        h.rooms[0].properties = {"room.tag": "lounge"}
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "rp.sh3d")
            proj_core.save_home(h, p)
            h2 = proj_core.open_home(p)
        assert h2.rooms[0].properties.get("room.tag") == "lounge"

    def test_stored_cameras_roundtrip(self):
        # SH3D stores observer/top camera distinction in the element TAG of a
        # stored camera (<observerCamera attribute="storedCamera"> vs
        # <camera attribute="storedCamera">). The `attribute` is always
        # "storedCamera"; the kind must reflect the underlying camera type.
        h = proj_core.new_home("SC")
        top_view = Camera(kind="topCamera", name="Plan overview",
                          x=400, y=600, z=1500, yaw=0, pitch=-1.5, fieldOfView=1.0472)
        obs_view = Camera(kind="observerCamera", name="Kitchen entry",
                          x=200, y=300, z=170, yaw=2.1, pitch=-0.1, fieldOfView=1.0472)
        h.storedCameras.extend([top_view, obs_view])
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "sc.sh3d")
            proj_core.save_home(h, p)
            h2 = proj_core.open_home(p)
        assert len(h2.storedCameras) == 2
        names = {sc.name: sc for sc in h2.storedCameras}
        assert names["Plan overview"].kind == "topCamera"
        assert names["Kitchen entry"].kind == "observerCamera"
        assert names["Plan overview"].x == pytest.approx(400)
        assert names["Kitchen entry"].z == pytest.approx(170)


class TestChunk16Environment:
    def test_env_missing_fields_roundtrip(self):
        h = proj_core.new_home("ENV")
        h.environment.backgroundImageVisibleOnGround3D = True
        h.environment.observerCameraElevationAdjusted = False
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "env.sh3d")
            proj_core.save_home(h, p)
            h2 = proj_core.open_home(p)
        assert h2.environment.backgroundImageVisibleOnGround3D is True
        assert h2.environment.observerCameraElevationAdjusted is False

    def test_video_camera_path_roundtrip(self):
        h = proj_core.new_home("VCP")
        cp_cam = Camera(kind="topCamera", x=100, y=100, z=170,
                        yaw=0, pitch=0, fieldOfView=1.0)
        h.environment.videoCameraPath = [cp_cam]
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "vcp.sh3d")
            proj_core.save_home(h, p)
            h2 = proj_core.open_home(p)
        assert len(h2.environment.videoCameraPath) == 1
        cp2 = h2.environment.videoCameraPath[0]
        assert cp2.x == pytest.approx(100)
        assert cp2.y == pytest.approx(100)


class TestChunk14Polyline:
    def test_polyline_dashpattern_roundtrip(self):
        h = proj_core.new_home("POL")
        ann_core.add_polyline(h, [(0, 0), (100, 0), (100, 100)])
        h.polylines[0].dashStyle = "CUSTOMIZED"
        h.polylines[0].dashPattern = "10 5 2 5"
        h.polylines[0].closedPath = True
        h.polylines[0].visibleIn3D = True
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "pol.sh3d")
            proj_core.save_home(h, p)
            h2 = proj_core.open_home(p)
        pol2 = h2.polylines[0]
        assert pol2.dashStyle == "CUSTOMIZED"
        assert pol2.dashPattern == "10 5 2 5"
        assert pol2.closedPath is True
        assert pol2.visibleIn3D is True


class TestChunk8PieceMissingFields:
    def test_piece_extended_fields_roundtrip(self):
        h = proj_core.new_home("P8")
        f = furn_core.add_piece(h, "Staircase", 100, 100,
                                 width=90, depth=200, height=250)
        f.planIcon = "42"
        f.widthInPlan = 95.0
        f.depthInPlan = 210.0
        f.heightInPlan = 260.0
        f.modelFlags = 1
        f.modelMirrored = True
        f.modelRotation = "0 0 1 0 1 0 -1 0 0"
        f.staircaseCutOutShape = "M0,0 v1 h1 v-1 z"
        f.dropOnTopElevation = 0.5
        f.resizable = False
        f.deformable = False
        f.texturable = False
        f.nameAngle = 0.5
        f.nameXOffset = 5.0
        f.nameYOffset = -10.0
        f.information = "https://example.com"
        f.license = "CC BY 4.0"
        f.price = "299.99"
        f.valueAddedTaxPercentage = "20"
        f.currency = "EUR"
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "p8.sh3d")
            proj_core.save_home(h, p)
            h2 = proj_core.open_home(p)
        f2 = h2.furniture[0]
        assert f2.planIcon == "42"
        assert f2.widthInPlan == pytest.approx(95.0)
        assert f2.depthInPlan == pytest.approx(210.0)
        assert f2.heightInPlan == pytest.approx(260.0)
        assert f2.modelFlags == 1
        assert f2.modelMirrored is True
        assert f2.modelRotation == "0 0 1 0 1 0 -1 0 0"
        assert f2.staircaseCutOutShape == "M0,0 v1 h1 v-1 z"
        assert f2.dropOnTopElevation == pytest.approx(0.5)
        assert f2.resizable is False
        assert f2.deformable is False
        assert f2.texturable is False
        assert f2.nameAngle == pytest.approx(0.5)
        assert f2.nameXOffset == pytest.approx(5.0)
        assert f2.nameYOffset == pytest.approx(-10.0)
        assert f2.information == "https://example.com"
        assert f2.license == "CC BY 4.0"
        assert f2.price == "299.99"
        assert f2.valueAddedTaxPercentage == "20"
        assert f2.currency == "EUR"

    def test_doorwindow_extra_fields_roundtrip(self):
        h = proj_core.new_home("DWX")
        d = furn_core.add_door(h, "BothSidesDoor", 100, 0)
        d.wallCutOutOnBothSides = True
        d.widthDepthDeformable = False
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "dwx.sh3d")
            proj_core.save_home(h, p)
            h2 = proj_core.open_home(p)
        d2 = next(f for f in h2.furniture if f.kind == "doorOrWindow")
        assert d2.wallCutOutOnBothSides is True
        assert d2.widthDepthDeformable is False


class TestChunk7Print:
    def test_print_roundtrip(self):
        h = proj_core.new_home("PR")
        h.printSettings = Print(
            paperWidth=210.0, paperHeight=297.0,
            paperTopMargin=10.0, paperLeftMargin=10.0,
            paperBottomMargin=10.0, paperRightMargin=10.0,
            paperOrientation="PORTRAIT",
            headerFormat="{name}", footerFormat="Page {page}",
            planScale=0.01,
            furniturePrinted=True, planPrinted=True, view3DPrinted=False,
        )
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "pr.sh3d")
            proj_core.save_home(h, p)
            h2 = proj_core.open_home(p)
        ps = h2.printSettings
        assert ps is not None
        assert ps.paperWidth == pytest.approx(210.0)
        assert ps.paperHeight == pytest.approx(297.0)
        assert ps.paperOrientation == "PORTRAIT"
        assert ps.headerFormat == "{name}"
        assert ps.planScale == pytest.approx(0.01)
        assert ps.view3DPrinted is False

    def test_print_with_printed_levels(self):
        h = proj_core.new_home("PRL")
        lvl = lvl_core.add_level(h, "Ground")
        h.printSettings = Print(
            paperWidth=210.0, paperHeight=297.0,
            paperTopMargin=10.0, paperLeftMargin=10.0,
            paperBottomMargin=10.0, paperRightMargin=10.0,
            paperOrientation="LANDSCAPE",
            printedLevels=[lvl.id],
        )
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "prl.sh3d")
            proj_core.save_home(h, p)
            h2 = proj_core.open_home(p)
        ps = h2.printSettings
        assert len(ps.printedLevels) == 1
        assert ps.printedLevels[0] == lvl.id
        assert ps.paperOrientation == "LANDSCAPE"

    def test_no_print_settings(self):
        h = proj_core.new_home("NPR")
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "npr.sh3d")
            proj_core.save_home(h, p)
            h2 = proj_core.open_home(p)
        assert h2.printSettings is None


class TestChunk6FurnitureGroup:
    def test_furnituregroup_roundtrip(self):
        h = proj_core.new_home("GRP")
        grp = FurnitureGroup(name="Kitchen Set")
        grp.furniture.append(
            PieceOfFurniture(name="Worktop", x=300, y=600,
                             width=200, depth=60, height=90)
        )
        grp.furniture.append(
            PieceOfFurniture(name="Hob", x=350, y=600,
                             width=60, depth=60, height=91)
        )
        h.furnitureGroups.append(grp)
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "grp.sh3d")
            proj_core.save_home(h, p)
            h2 = proj_core.open_home(p)
        assert len(h2.furnitureGroups) == 1
        g2 = h2.furnitureGroups[0]
        assert g2.name == "Kitchen Set"
        assert len(g2.furniture) == 2
        names = {f.name for f in g2.furniture}
        assert names == {"Worktop", "Hob"}

    def test_nested_furnituregroup_roundtrip(self):
        h = proj_core.new_home("NGRP")
        inner = FurnitureGroup(name="Inner")
        inner.furniture.append(
            PieceOfFurniture(name="Stool", x=0, y=0, width=40, depth=40, height=45)
        )
        outer = FurnitureGroup(name="Outer")
        outer.furniture.append(inner)
        h.furnitureGroups.append(outer)
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "ngrp.sh3d")
            proj_core.save_home(h, p)
            h2 = proj_core.open_home(p)
        g2 = h2.furnitureGroups[0]
        assert g2.name == "Outer"
        assert len(g2.furniture) == 1
        inner2 = g2.furniture[0]
        assert isinstance(inner2, FurnitureGroup)
        assert inner2.name == "Inner"
        assert len(inner2.furniture) == 1


class TestChunk5TextStyle:
    def test_label_style_roundtrip(self):
        h = proj_core.new_home("TS")
        ann_core.add_label(h, "Hello", 100, 100)
        h.labels[0].style = TextStyle(fontSize=24.0, bold=True, alignment="LEFT")
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "ts.sh3d")
            proj_core.save_home(h, p)
            h2 = proj_core.open_home(p)
        lbl2 = h2.labels[0]
        assert lbl2.style is not None
        assert lbl2.style.fontSize == pytest.approx(24.0)
        assert lbl2.style.bold is True
        assert lbl2.style.alignment == "LEFT"

    def test_room_namestyle_areastyle_roundtrip(self):
        h = proj_core.new_home("TS2")
        rooms_core.add_rectangle_room(h, 0, 0, 500, 400, name="Kitchen", areaVisible=True)
        h.rooms[0].nameStyle = TextStyle(fontSize=18.0, fontName="Arial")
        h.rooms[0].areaStyle = TextStyle(fontSize=12.0, italic=True)
        h.rooms[0].areaAngle = 0.5
        h.rooms[0].areaXOffset = 10.0
        h.rooms[0].areaYOffset = -5.0
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "ts2.sh3d")
            proj_core.save_home(h, p)
            h2 = proj_core.open_home(p)
        r2 = h2.rooms[0]
        assert r2.nameStyle is not None
        assert r2.nameStyle.fontSize == pytest.approx(18.0)
        assert r2.nameStyle.fontName == "Arial"
        assert r2.areaStyle is not None
        assert r2.areaStyle.italic is True
        assert r2.areaAngle == pytest.approx(0.5)
        assert r2.areaXOffset == pytest.approx(10.0)
        assert r2.areaYOffset == pytest.approx(-5.0)

    def test_dimension_lengthstyle_roundtrip(self):
        h = proj_core.new_home("TS3")
        ann_core.add_dimension(h, 0, 0, 100, 0)
        h.dimensionLines[0].lengthStyle = TextStyle(fontSize=10.0)
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "ts3.sh3d")
            proj_core.save_home(h, p)
            h2 = proj_core.open_home(p)
        dl2 = h2.dimensionLines[0]
        assert dl2.lengthStyle is not None
        assert dl2.lengthStyle.fontSize == pytest.approx(10.0)


class TestChunk4MaterialTransformation:
    def test_material_roundtrip(self):
        h = proj_core.new_home("MAT")
        f = furn_core.add_piece(h, "Chair", 100, 100, width=60, depth=60, height=90)
        f.materials = [
            Material(name="body", color=0xFF2244AA, shininess=0.5),
            Material(name="legs", key="leg_key"),
        ]
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "mat.sh3d")
            proj_core.save_home(h, p)
            h2 = proj_core.open_home(p)
        chair2 = h2.furniture[0]
        assert len(chair2.materials) == 2
        assert chair2.materials[0].name == "body"
        assert chair2.materials[0].color == 0xFF2244AA
        assert chair2.materials[0].shininess == pytest.approx(0.5)
        assert chair2.materials[1].key == "leg_key"

    def test_transformation_roundtrip(self):
        h = proj_core.new_home("TR")
        f = furn_core.add_piece(h, "Door3D", 200, 200, width=80, depth=10, height=200)
        f.modelTransformations = [
            Transformation(name="door_hinge", matrix="1 0 0 45 0 1 0 0 0 0 1 0"),
        ]
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "tr.sh3d")
            proj_core.save_home(h, p)
            h2 = proj_core.open_home(p)
        f2 = h2.furniture[0]
        assert len(f2.modelTransformations) == 1
        assert f2.modelTransformations[0].name == "door_hinge"
        assert f2.modelTransformations[0].matrix == "1 0 0 45 0 1 0 0 0 0 1 0"


class TestChunk3LightSource:
    def test_lightsource_roundtrip(self):
        h = proj_core.new_home("LS")
        lamp = furn_core.add_light(h, "Lamp", 100, 100)
        lamp.lightSources = [
            LightSource(x=0.5, y=0.5, z=0.1, color=0xFFFFFFFF, diameter=0.05),
        ]
        lamp.lightSourceMaterials = [LightSourceMaterial(name="bulb")]
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "ls.sh3d")
            proj_core.save_home(h, p)
            h2 = proj_core.open_home(p)
        light2 = next(f for f in h2.furniture if f.kind == "light")
        assert len(light2.lightSources) == 1
        ls = light2.lightSources[0]
        assert ls.x == pytest.approx(0.5)
        assert ls.z == pytest.approx(0.1)
        assert ls.color == 0xFFFFFFFF
        assert ls.diameter == pytest.approx(0.05)
        assert len(light2.lightSourceMaterials) == 1
        assert light2.lightSourceMaterials[0].name == "bulb"

    def test_non_light_has_no_lightsources(self):
        h = proj_core.new_home("LS2")
        p = furn_core.add_piece(h, "Chair", 0, 0, width=50, depth=50, height=90)
        assert p.lightSources == []
        assert p.lightSourceMaterials == []


class TestChunk2Sash:
    def test_sash_roundtrip(self):
        h = proj_core.new_home("SASH")
        d = furn_core.add_door(h, "Door", 100, 0)
        d.sashes = [
            Sash(xAxis=0.0, yAxis=0.5, width=1.0, startAngle=0.0, endAngle=1.5708),
            Sash(xAxis=1.0, yAxis=0.5, width=0.5, startAngle=0.0, endAngle=-1.5708),
        ]
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "sash.sh3d")
            proj_core.save_home(h, p)
            h2 = proj_core.open_home(p)
        door2 = next(f for f in h2.furniture if f.kind == "doorOrWindow")
        assert len(door2.sashes) == 2
        assert door2.sashes[0].xAxis == 0.0
        assert door2.sashes[0].endAngle == pytest.approx(1.5708, abs=1e-4)
        assert door2.sashes[1].xAxis == 1.0
        assert door2.sashes[1].width == 0.5

    def test_non_door_has_no_sashes(self):
        h = proj_core.new_home("S2")
        p = furn_core.add_piece(h, "Chair", 0, 0, width=50, depth=50, height=90)
        assert p.sashes == []


class TestChunk1Baseboard:
    def test_baseboard_roundtrip(self):
        h = proj_core.new_home("BB")
        w = walls_core.add_wall(h, 0, 0, 500, 0)
        w.leftSideBaseboard = Baseboard(thickness=2.5, height=10, color=0xFFFFFFFF)
        w.rightSideBaseboard = Baseboard(thickness=1.5, height=8)
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "bb.sh3d")
            proj_core.save_home(h, p)
            h2 = proj_core.open_home(p)
        bb_left = h2.walls[0].leftSideBaseboard
        bb_right = h2.walls[0].rightSideBaseboard
        assert bb_left is not None
        assert bb_left.thickness == 2.5
        assert bb_left.height == 10
        assert bb_left.color == 0xFFFFFFFF
        assert bb_right is not None
        assert bb_right.thickness == 1.5
        assert bb_right.height == 8
        assert bb_right.color is None

    def test_baseboard_xml_structure(self):
        h = proj_core.new_home("BB2")
        w = walls_core.add_wall(h, 0, 0, 100, 0)
        w.leftSideBaseboard = Baseboard(thickness=3.0, height=12)
        tree = proj_core.home_to_xml(h)
        wall_el = tree.find("wall")
        bb_els = wall_el.findall("baseboard")
        assert len(bb_els) == 1
        assert bb_els[0].get("attribute") == "leftSideBaseboard"
        assert bb_els[0].get("thickness") == "3"
        assert bb_els[0].get("height") == "12"


class TestWalls:
    def test_add_validates_zero_length(self):
        h = proj_core.new_home()
        with pytest.raises(ValueError):
            walls_core.add_wall(h, 0, 0, 0, 0)

    def test_add_inherits_wall_height(self):
        h = proj_core.new_home(); h.wallHeight = 300
        w = walls_core.add_wall(h, 0, 0, 100, 0)
        assert w.height == 300

    def test_rectangle_creates_connected(self):
        h = proj_core.new_home()
        n, e, s, w = walls_core.rectangle(h, 0, 0, 500, 400)
        assert n.wallAtEnd == e.id
        assert e.wallAtStart == n.id
        assert e.wallAtEnd == s.id
        assert w.wallAtEnd == n.id

    def test_delete_strips_references(self):
        h = proj_core.new_home()
        n, e, *_ = walls_core.rectangle(h, 0, 0, 500, 400)
        assert walls_core.delete_wall(h, n.id)
        assert e.wallAtStart is None

    def test_delete_missing(self):
        h = proj_core.new_home()
        assert walls_core.delete_wall(h, "nope") is False

    def test_connect_invalid_at(self):
        h = proj_core.new_home()
        a = walls_core.add_wall(h, 0, 0, 100, 0)
        b = walls_core.add_wall(h, 100, 0, 100, 100)
        with pytest.raises(ValueError):
            walls_core.connect_walls(h, a.id, b.id, at="middle")

    def test_move_updates_only_passed_fields(self):
        h = proj_core.new_home()
        w = walls_core.add_wall(h, 0, 0, 100, 0)
        walls_core.move_wall(h, w.id, xEnd=200)
        assert w.xStart == 0 and w.xEnd == 200

    def test_length_axis_aligned(self):
        w = Wall(xStart=0, yStart=0, xEnd=300, yEnd=400)
        assert walls_core.length(w) == 500


# ─── rooms ──────────────────────────────────────────────────────────────────

class TestRooms:
    def test_requires_3_points(self):
        h = proj_core.new_home()
        with pytest.raises(ValueError):
            rooms_core.add_room(h, [(0,0),(10,0)])

    def test_rectangle_validates_dims(self):
        h = proj_core.new_home()
        with pytest.raises(ValueError):
            rooms_core.add_rectangle_room(h, 0, 0, -1, 100)

    def test_area_square(self):
        r = Room(points=[Point(0,0), Point(10,0), Point(10,10), Point(0,10)])
        assert rooms_core.area(r) == 100

    def test_area_triangle(self):
        r = Room(points=[Point(0,0), Point(10,0), Point(0,10)])
        assert rooms_core.area(r) == 50

    def test_delete_missing(self):
        h = proj_core.new_home()
        assert rooms_core.delete_room(h, "nope") is False


# ─── furniture ──────────────────────────────────────────────────────────────

class TestFurniture:
    def test_kinds_constant(self):
        assert furn_core.KINDS == ("pieceOfFurniture", "doorOrWindow", "light")

    def test_add_validates_dimensions(self):
        h = proj_core.new_home()
        with pytest.raises(ValueError):
            furn_core.add_piece(h, "X", 0, 0, width=0, depth=10, height=10)
        with pytest.raises(ValueError):
            furn_core.add_piece(h, "X", 0, 0, width=10, depth=10, height=-1)

    def test_add_validates_kind(self):
        h = proj_core.new_home()
        with pytest.raises(ValueError):
            furn_core.add_piece(h, "X", 0, 0,
                                  width=10, depth=10, height=10, kind="bogus")

    def test_door_defaults(self):
        h = proj_core.new_home()
        d = furn_core.add_door(h, "D1", 0, 0)
        assert d.kind == "doorOrWindow"
        # wallThickness is intentionally omitted: writing it as 1.0 was
        # suppressing SH3D's auto-bind on load. The piece's own `depth`
        # drives the wall-cut shape, so the attribute stays None unless
        # the caller passes one explicitly.
        assert d.wallThickness is None
        assert d.height == 200

    def test_window_default_elevation(self):
        h = proj_core.new_home()
        w = furn_core.add_window(h, "W1", 0, 0)
        assert w.elevation == 100

    def test_light_defaults(self):
        h = proj_core.new_home()
        L = furn_core.add_light(h, "L", 0, 0)
        assert L.kind == "light"
        assert L.power == 0.5
        assert L.color == 0xFFFFE0

    def test_list_filter_by_kind(self):
        h = proj_core.new_home()
        furn_core.add_piece(h, "Sofa", 0, 0, width=100, depth=50, height=50)
        furn_core.add_door(h, "D", 0, 0)
        items = furn_core.list_furniture(h, kind="doorOrWindow")
        assert len(items) == 1
        assert items[0].name == "D"

    def test_move_only_updates_passed(self):
        h = proj_core.new_home()
        f = furn_core.add_piece(h, "X", 0, 0,
                                  width=10, depth=10, height=10)
        furn_core.move_piece(h, f.id, x=100, angle=1.57)
        assert f.x == 100 and f.y == 0 and f.angle == 1.57


# ─── levels ─────────────────────────────────────────────────────────────────

class TestLevels:
    def test_add_rejects_duplicate(self):
        h = proj_core.new_home()
        lvl_core.add_level(h, "Ground")
        with pytest.raises(ValueError):
            lvl_core.add_level(h, "Ground")

    def test_elevation_index_increments(self):
        h = proj_core.new_home()
        a = lvl_core.add_level(h, "A")
        b = lvl_core.add_level(h, "B")
        assert b.elevationIndex == a.elevationIndex + 1

    def test_delete_detaches_objects(self):
        h = proj_core.new_home()
        l = lvl_core.add_level(h, "L")
        walls_core.add_wall(h, 0, 0, 100, 0, level=l.id)
        rooms_core.add_rectangle_room(h, 0, 0, 100, 100, level=l.id)
        lvl_core.delete_level(h, "L", detach=True)
        assert h.walls[0].level is None
        assert h.rooms[0].level is None

    def test_delete_keep_attached_raises(self):
        h = proj_core.new_home()
        l = lvl_core.add_level(h, "L")
        walls_core.add_wall(h, 0, 0, 100, 0, level=l.id)
        with pytest.raises(ValueError, match="attached"):
            lvl_core.delete_level(h, "L", detach=False)

    def test_select_level(self):
        h = proj_core.new_home()
        l = lvl_core.add_level(h, "L")
        lvl_core.select_level(h, "L")
        assert h.selectedLevel == l.id
        lvl_core.select_level(h, None)
        assert h.selectedLevel is None


# ─── cameras ────────────────────────────────────────────────────────────────

class TestCameras:
    def test_get_validates_kind(self):
        h = proj_core.new_home()
        with pytest.raises(ValueError):
            cam_core.get_camera(h, kind="bogus")

    def test_set_validates_lens(self):
        h = proj_core.new_home()
        with pytest.raises(ValueError):
            cam_core.set_camera(h, lens="MAGIC")

    def test_set_updates(self):
        h = proj_core.new_home()
        cam_core.set_camera(h, kind="observerCamera",
                              x=100, y=200, z=170, yaw=1.57, pitch=0.1)
        assert h.observerCamera.x == 100
        assert h.observerCamera.yaw == 1.57

    def test_activate(self):
        h = proj_core.new_home()
        cam_core.activate_camera(h, "observerCamera")
        assert h.camera == "observerCamera"
        with pytest.raises(ValueError):
            cam_core.activate_camera(h, "magic")


# ─── annotations ────────────────────────────────────────────────────────────

class TestAnnotations:
    def test_dimension_rejects_coincident(self):
        h = proj_core.new_home()
        with pytest.raises(ValueError):
            ann_core.add_dimension(h, 0, 0, 0, 0)

    def test_label_rejects_empty(self):
        h = proj_core.new_home()
        with pytest.raises(ValueError):
            ann_core.add_label(h, "", 0, 0)

    def test_polyline_requires_2_points(self):
        h = proj_core.new_home()
        with pytest.raises(ValueError):
            ann_core.add_polyline(h, [(0, 0)])

    def test_compass_set_surgical(self):
        h = proj_core.new_home()
        ann_core.set_compass(h, x=200, latitude=51.5)
        assert h.compass.x == 200
        assert h.compass.latitude == 51.5
        # y untouched
        assert h.compass.y == 50

    def test_delete_returns_false_for_missing(self):
        h = proj_core.new_home()
        assert ann_core.delete_dimension(h, "nope") is False
        assert ann_core.delete_label(h, "nope") is False
        assert ann_core.delete_polyline(h, "nope") is False


# ─── environment ────────────────────────────────────────────────────────────

class TestEnvironment:
    def test_set_unknown_field(self):
        h = proj_core.new_home()
        with pytest.raises(AttributeError):
            env_core.set_environment(h, fakeField=1)

    def test_photo_size_validates(self):
        h = proj_core.new_home()
        with pytest.raises(ValueError):
            env_core.set_photo_size(h, 0, 300)

    def test_set_drawing_mode(self):
        h = proj_core.new_home()
        env_core.set_environment(h, drawingMode="OUTLINE", wallsAlpha=0.2)
        assert h.environment.drawingMode == "OUTLINE"
        assert h.environment.wallsAlpha == 0.2


# ─── export (SVG) ───────────────────────────────────────────────────────────

class TestExport:
    def test_empty_home_svg_parseable(self):
        h = proj_core.new_home()
        svg = export_core.to_svg(h)
        root = ET.fromstring(svg)
        assert root.tag.endswith("svg")
        assert "viewBox" in root.attrib

    def test_svg_includes_all_groups(self):
        h = proj_core.new_home("Demo")
        walls_core.rectangle(h, 0, 0, 500, 400)
        rooms_core.add_rectangle_room(h, 0, 0, 500, 400, name="Studio")
        furn_core.add_piece(h, "Sofa", 200, 200,
                              width=200, depth=80, height=80)
        furn_core.add_door(h, "Door1", 250, 0)
        furn_core.add_light(h, "Lamp", 250, 200)
        ann_core.add_dimension(h, 0, 0, 500, 0)
        ann_core.add_label(h, "North", 50, 50)
        svg = export_core.to_svg(h)
        root = ET.fromstring(svg)
        ids = {g.get("id") for g in root.findall(".//{*}g")}
        assert {"rooms", "walls", "furniture", "dimensions",
                  "labels", "compass"}.issubset(ids)

    def test_svg_bounds_includes_padding(self):
        h = proj_core.new_home()
        walls_core.add_wall(h, 0, 0, 1000, 0)
        svg = export_core.to_svg(h, padding=100)
        root = ET.fromstring(svg)
        x, y, w, hgt = root.get("viewBox").split()
        # bounds + padding=100 on both sides
        assert float(x) < 0
        assert float(w) > 1000

    def test_export_svg_writes_file(self, tmp_path):
        h = proj_core.new_home()
        walls_core.add_wall(h, 0, 0, 100, 0)
        out = str(tmp_path / "out.svg")
        result = export_core.export_svg(h, out)
        assert result == out
        assert os.path.getsize(out) > 0
        with open(out) as f:
            assert f.read(5) == "<?xml"

    def test_level_filter(self):
        h = proj_core.new_home()
        ground = lvl_core.add_level(h, "Ground")
        first = lvl_core.add_level(h, "First")
        walls_core.add_wall(h, 0, 0, 100, 0, level=ground.id)
        walls_core.add_wall(h, 0, 100, 100, 100, level=first.id)
        svg = export_core.to_svg(h, level=first.id)
        root = ET.fromstring(svg)
        # only one wall polygon under <g id="walls">
        walls_g = root.find(".//{*}g[@id='walls']")
        assert len(walls_g.findall("{*}polygon")) == 1


# ─── session ────────────────────────────────────────────────────────────────

class TestSession:
    def test_new_session(self):
        s = Session.new(name="X")
        assert s.home.name == "X"
        assert s.modified is False

    def test_save_requires_path(self):
        s = Session.new()
        with pytest.raises(ValueError):
            s.save()

    def test_save_writes_file(self, tmp_path):
        s = Session.new(name="X")
        out = str(tmp_path / "s.sh3d")
        s.save(out)
        assert os.path.isfile(out)
        assert s.path == out

    def test_undo_redo_cycle(self):
        s = Session.new()
        s.checkpoint()
        walls_core.add_wall(s.home, 0, 0, 100, 0)
        assert len(s.home.walls) == 1
        assert s.undo()
        assert len(s.home.walls) == 0
        assert s.redo()
        assert len(s.home.walls) == 1

    def test_undo_empty(self):
        s = Session.new()
        assert s.undo() is False

    def test_open(self, tmp_path):
        # save via core, then open via session
        h = proj_core.new_home("Y")
        out = str(tmp_path / "y.sh3d")
        proj_core.save_home(h, out)
        s = Session.open(out)
        assert s.home.name == "Y"
        assert s.path == out

    def test_status_dict(self):
        s = Session.new(name="S")
        st = s.status()
        assert st["name"] == "S"
        assert st["modified"] is False
        assert st["objects"]["walls"] == 0


# ─── backend ────────────────────────────────────────────────────────────────

class TestBackend:
    def test_not_installed_raises(self, monkeypatch):
        monkeypatch.delenv("SWEETHOME3D_BIN", raising=False)
        monkeypatch.delenv("SWEETHOME3D_JAR", raising=False)
        monkeypatch.setattr(backend.shutil, "which", lambda x: None)
        monkeypatch.setattr(backend.os.path, "isfile", lambda x: False)
        with pytest.raises(backend.Sweethome3DNotInstalled):
            backend.find_sweethome3d()

    def test_env_bin_honored(self, monkeypatch, tmp_path):
        fake = tmp_path / "sh3d"
        fake.write_text("#!/bin/sh\n")
        monkeypatch.setenv("SWEETHOME3D_BIN", str(fake))
        assert backend.find_sweethome3d() == [str(fake)]

    def test_env_jar_with_java(self, monkeypatch, tmp_path):
        jar = tmp_path / "SweetHome3D-7.5.jar"
        jar.write_text("x")
        monkeypatch.delenv("SWEETHOME3D_BIN", raising=False)
        monkeypatch.setenv("SWEETHOME3D_JAR", str(jar))
        monkeypatch.setattr(backend.shutil, "which",
                              lambda x: "/usr/bin/java" if x == "java" else None)
        monkeypatch.setattr(backend.os.path, "isfile", lambda p: p == str(jar))
        argv = backend.find_sweethome3d()
        assert argv == ["/usr/bin/java", "-jar", str(jar)]

    def test_version_parses_from_jar(self, monkeypatch, tmp_path):
        jar = tmp_path / "SweetHome3D-7.5.jar"
        jar.write_text("x")
        monkeypatch.setenv("SWEETHOME3D_JAR", str(jar))
        monkeypatch.delenv("SWEETHOME3D_BIN", raising=False)
        monkeypatch.setattr(backend.shutil, "which",
                              lambda x: "/usr/bin/java" if x == "java" else None)
        monkeypatch.setattr(backend.os.path, "isfile", lambda p: p == str(jar))
        assert backend.version() == "7.5"


