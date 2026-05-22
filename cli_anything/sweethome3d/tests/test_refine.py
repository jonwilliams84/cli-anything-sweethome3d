"""Unit + E2E tests for the refine pass.

Covers the new CLI surface added by `/cli-anything:refine`:

- textures core + `textures list/search/info`
- find core wired into `find rooms/walls/pieces/doors/lights`
- polyline CLI group
- level set / level select
- room set / room recompute-points
- wall set --left-texture / --right-texture / baseboard
- environment set --sky-texture / --ground-texture / video-size / extras
- dimension set / label set
- camera save / list / delete / go (stored cameras)

Also re-asserts the canonical texture serialization fix:
`<texture attribute="leftSideTexture" ... />` (flat) rather than the
legacy nested `<leftSideTexture><texture .../></leftSideTexture>` wrapper.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from xml.etree import ElementTree as ET

import pytest

from cli_anything.sweethome3d.core import (
    annotations as ann_core,
    find as find_core,
    levels as lvl_core,
    project as proj_core,
    rooms as rooms_core,
    textures as tex_core,
    walls as walls_core,
)
from cli_anything.sweethome3d.core.model import (
    Baseboard,
    Camera,
    Home,
    Level,
    Point,
    Polyline,
    Room,
    Texture,
    Wall,
)
from cli_anything.sweethome3d.core.session import Session


# ───────────────────────────────────────────────── helpers

def _resolve_cli(name):
    force = os.environ.get("CLI_ANYTHING_FORCE_INSTALLED", "").strip() == "1"
    path = shutil.which(name)
    if path:
        return [path]
    if force:
        raise RuntimeError(
            f"{name} not found in PATH. Install with: pip install -e ."
        )
    return [sys.executable, "-m", "cli_anything.sweethome3d"]


CLI = _resolve_cli("cli-anything-sweethome3d")


def _run(args, check=True):
    r = subprocess.run(CLI + args, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise AssertionError(
            f"CLI failed: {args}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
        )
    return r


# ───────────────────────────────────────────────── textures core

class TestTexturesCore:
    def test_catalog_has_26_entries(self):
        all_t = tex_core.list_textures()
        assert len(all_t) == 26

    def test_category_filter(self):
        floors = tex_core.list_textures(category="Floor")
        walls = tex_core.list_textures(category="Wall")
        sky = tex_core.list_textures(category="Sky")
        assert len(floors) == 12  # 12 floor textures
        assert len(walls) == 11
        assert len(sky) == 3
        assert all(t.category == "Floor" for t in floors)
        assert all(t.category == "Sky" for t in sky)

    def test_category_case_insensitive(self):
        upper = tex_core.list_textures(category="Floor")
        lower = tex_core.list_textures(category="floor")
        assert {t.catalogId for t in upper} == {t.catalogId for t in lower}

    def test_query_substring(self):
        hits = tex_core.list_textures(query="brick")
        ids = {t.catalogId for t in hits}
        assert "eTeks#smallBricks" in ids
        assert "eTeks#smallRedBricks" in ids
        assert "eTeks#smallWhiteBricks" in ids
        # No unrelated entries
        assert "eTeks#grass" not in ids

    def test_find_texture_exact(self):
        e = tex_core.find_texture("eTeks#woodenFloor")
        assert e is not None
        assert e.width == 42.5 and e.height == 42.5
        assert tex_core.find_texture("eTeks#nope") is None

    def test_make_texture_unknown_raises(self):
        with pytest.raises(KeyError, match="not found"):
            tex_core.make_texture("eTeks#totallyMadeUp")

    def test_make_texture_uses_catalog_defaults(self):
        t = tex_core.make_texture("eTeks#smallBricks")
        assert t.catalogId == "eTeks#smallBricks"
        assert t.name == "Small bricks"
        assert (t.width, t.height) == (23.0, 14.9)
        assert t.creator == "eTeks"

    def test_make_texture_overrides(self):
        t = tex_core.make_texture("eTeks#grass", width=50, height=50, angle=0.5)
        assert t.width == 50 and t.height == 50 and t.angle == 0.5
        # Identity preserved
        assert t.catalogId == "eTeks#grass"


# ───────────────────────────────────────────────── texture serialization

class TestTextureSerializationFix:
    """Verify the writer now emits SH3D's canonical flat form."""

    def test_wall_texture_writes_attribute_discriminator(self, tmp_path):
        sess = Session.new()
        w = walls_core.add_wall(
            sess.home, 0, 0, 500, 0,
            leftSideTexture=tex_core.make_texture("eTeks#smallBricks"),
            rightSideTexture=tex_core.make_texture("eTeks#roughcast"),
        )
        out = str(tmp_path / "walls.sh3d")
        sess.save(out)
        with zipfile.ZipFile(out) as z:
            xml = z.read("Home.xml").decode()
        # Canonical flat form: <texture attribute="leftSideTexture" .../>
        assert re.search(
            r'<texture\s+attribute="leftSideTexture"[^/]*catalogId="eTeks#smallBricks"',
            xml,
        ), f"missing flat leftSideTexture in:\n{xml}"
        assert re.search(
            r'<texture\s+attribute="rightSideTexture"[^/]*catalogId="eTeks#roughcast"',
            xml,
        )
        # And NOT the old nested wrapper
        assert "<leftSideTexture>" not in xml
        assert "<rightSideTexture>" not in xml

    def test_environment_textures_write_flat(self, tmp_path):
        sess = Session.new()
        sess.home.environment.skyTexture = tex_core.make_texture("eTeks#blueSky")
        sess.home.environment.groundTexture = tex_core.make_texture("eTeks#grass")
        out = str(tmp_path / "env.sh3d")
        sess.save(out)
        with zipfile.ZipFile(out) as z:
            xml = z.read("Home.xml").decode()
        assert re.search(r'<texture\s+attribute="skyTexture"', xml)
        assert re.search(r'<texture\s+attribute="groundTexture"', xml)
        assert "<skyTexture>" not in xml

    def test_room_textures_write_flat(self, tmp_path):
        sess = Session.new()
        rooms_core.add_rectangle_room(
            sess.home, 0, 0, 400, 300,
            floorTexture=tex_core.make_texture("eTeks#woodenFloor"),
            ceilingTexture=tex_core.make_texture("eTeks#roughcast"),
        )
        out = str(tmp_path / "rooms.sh3d")
        sess.save(out)
        with zipfile.ZipFile(out) as z:
            xml = z.read("Home.xml").decode()
        assert re.search(r'<texture\s+attribute="floorTexture"', xml)
        assert re.search(r'<texture\s+attribute="ceilingTexture"', xml)

    def test_round_trip_flat_form(self, tmp_path):
        """Save → load → save preserves textures via the new parser path."""
        sess = Session.new()
        rooms_core.add_rectangle_room(
            sess.home, 0, 0, 400, 300,
            floorTexture=tex_core.make_texture("eTeks#woodenFloor"),
        )
        out = str(tmp_path / "rt.sh3d")
        sess.save(out)
        sess2 = Session.open(out)
        assert sess2.home.rooms[0].floorTexture is not None
        assert sess2.home.rooms[0].floorTexture.catalogId == "eTeks#woodenFloor"

    def test_legacy_wrapper_still_parses(self, tmp_path):
        """Existing files written with the old nested wrapper still load."""
        out = str(tmp_path / "legacy.sh3d")
        # Hand-craft an SH3D ZIP with the legacy wrapper format.
        legacy_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<home version="7400" wallHeight="250" name="Legacy">\n'
            '  <environment>\n'
            '    <skyTexture><texture catalogId="eTeks#blueSky" name="Blue sky"'
            ' width="100" height="41.3"/></skyTexture>\n'
            '  </environment>\n'
            '  <compass x="50" y="50" diameter="100" northDirection="0"/>\n'
            '  <camera attribute="topCamera" lens="PINHOLE" x="0" y="0" z="1000"'
            ' yaw="0" pitch="0" fieldOfView="1"/>\n'
            '  <observerCamera attribute="observerCamera" lens="PINHOLE" x="0"'
            ' y="0" z="170" yaw="0" pitch="0" fieldOfView="1"/>\n'
            '</home>\n'
        )
        with zipfile.ZipFile(out, "w") as z:
            z.writestr("Home.xml", legacy_xml)
        home = proj_core.open_home(out)
        assert home.environment.skyTexture is not None
        assert home.environment.skyTexture.catalogId == "eTeks#blueSky"


# ───────────────────────────────────────────────── find core

def _two_room_home() -> Home:
    h = Home()
    g = lvl_core.add_level(h, "Ground")
    rooms_core.add_rectangle_room(h, 0, 0, 400, 300,
                                   name="Kitchen", level=g.id)
    rooms_core.add_rectangle_room(h, 500, 0, 400, 300,
                                   name="Living", level=g.id)
    walls_core.add_wall(h, 0, 0, 400, 0, thickness=10, level=g.id)
    walls_core.add_wall(h, 0, 0, 0, 300, thickness=10, level=g.id)  # vertical
    from cli_anything.sweethome3d.core import furniture as fc
    fc.add_light(h, "KitchenLight", 200, 150, level=g.id)
    fc.add_light(h, "LivingLight", 700, 150, level=g.id)
    fc.add_door(h, "FrontDoor", 200, 0, level=g.id)
    return h


class TestFindCore:
    def test_find_room_by_name(self):
        h = _two_room_home()
        r = find_core.find_room(h, name="Kitchen")
        assert r is not None and r.name == "Kitchen"

    def test_find_walls_horizontal(self):
        h = _two_room_home()
        hor = find_core.find_walls(h, horizontal=True)
        assert all(w.yStart == w.yEnd for w in hor)
        ver = find_core.find_walls(h, vertical=True)
        assert all(w.xStart == w.xEnd for w in ver)
        # Filters partition the set
        assert {w.id for w in hor} | {w.id for w in ver} == {w.id for w in h.walls}

    def test_find_lights_in_room(self):
        h = _two_room_home()
        kitchen = find_core.find_room(h, name="Kitchen")
        lights = find_core.find_lights(h, in_room=kitchen)
        assert len(lights) == 1
        assert lights[0].name == "KitchenLight"

    def test_find_pieces_near_point(self):
        h = _two_room_home()
        hits = find_core.find_pieces(h, kind="doorOrWindow",
                                       near_point=(200, 0),
                                       max_distance_cm=10)
        assert len(hits) == 1 and hits[0].name == "FrontDoor"


# ───────────────────────────────────────────────── CLI: textures

class TestTexturesCLI:
    def test_list_full(self):
        r = _run(["--json", "textures", "list"])
        data = json.loads(r.stdout)
        assert len(data) == 26
        assert {"catalogId", "name", "category"} <= set(data[0])

    def test_list_filter_floor(self):
        r = _run(["--json", "textures", "list", "--category", "Floor"])
        data = json.loads(r.stdout)
        assert all(t["category"] == "Floor" for t in data)

    def test_search(self):
        r = _run(["--json", "textures", "search", "brick"])
        data = json.loads(r.stdout)
        ids = {t["catalogId"] for t in data}
        assert "eTeks#smallBricks" in ids

    def test_search_no_match_fails(self):
        r = _run(["textures", "search", "xyzzy-not-a-thing"], check=False)
        assert r.returncode != 0

    def test_info_exact(self):
        r = _run(["--json", "textures", "info", "eTeks#blueSky"])
        data = json.loads(r.stdout)
        assert data["catalogId"] == "eTeks#blueSky"
        assert data["category"] == "Sky"


# ───────────────────────────────────────────────── CLI: wall/room/env texture wiring

class TestWallRoomEnvTextureCLI:
    def test_wall_add_with_textures(self, tmp_path):
        sh3d = str(tmp_path / "wt.sh3d")
        _run(["project", "new", "-o", sh3d])
        r = _run(["--project", sh3d, "--json", "wall", "add",
                   "0", "0", "500", "0",
                   "--left-texture", "eTeks#smallBricks",
                   "--right-texture", "eTeks#roughcast"])
        data = json.loads(r.stdout)
        assert data["leftSideTexture"]["catalogId"] == "eTeks#smallBricks"
        assert data["rightSideTexture"]["catalogId"] == "eTeks#roughcast"
        # Verify it persists on reload
        with zipfile.ZipFile(sh3d) as z:
            xml = z.read("Home.xml").decode()
        assert 'attribute="leftSideTexture"' in xml
        assert 'catalogId="eTeks#smallBricks"' in xml

    def test_wall_add_unknown_texture_fails(self, tmp_path):
        sh3d = str(tmp_path / "wt_bad.sh3d")
        _run(["project", "new", "-o", sh3d])
        r = _run(["--project", sh3d, "wall", "add", "0", "0", "100", "0",
                   "--left-texture", "eTeks#nope"],
                  check=False)
        assert r.returncode != 0
        assert "not found" in (r.stderr + r.stdout).lower()

    def test_room_set_with_textures(self, tmp_path):
        sh3d = str(tmp_path / "rt.sh3d")
        _run(["project", "new", "-o", sh3d])
        r = _run(["--project", sh3d, "--json", "room", "rectangle",
                   "0", "0", "400", "300", "-n", "Kitchen"])
        room_id = json.loads(r.stdout)["id"]
        _run(["--project", sh3d, "room", "set", room_id,
               "--floor-texture", "eTeks#woodenFloor",
               "--ceiling-texture", "eTeks#marbleWall",
               "--floor-color", "#FFEEDDCC",
               "--ceiling-flat"])
        # Verify on reload
        sess = Session.open(sh3d)
        room = sess.home.rooms[0]
        assert room.floorTexture and room.floorTexture.catalogId == "eTeks#woodenFloor"
        assert room.ceilingTexture and room.ceilingTexture.catalogId == "eTeks#marbleWall"
        assert room.ceilingFlat is True

    def test_room_set_clear_texture(self, tmp_path):
        sh3d = str(tmp_path / "rt_clear.sh3d")
        _run(["project", "new", "-o", sh3d])
        r = _run(["--project", sh3d, "--json", "room", "rectangle",
                   "0", "0", "400", "300", "-n", "K",
                   "--floor-texture", "eTeks#grass"])
        room_id = json.loads(r.stdout)["id"]
        _run(["--project", sh3d, "room", "set", room_id,
               "--clear-floor-texture"])
        sess = Session.open(sh3d)
        assert sess.home.rooms[0].floorTexture is None

    def test_environment_set_textures(self, tmp_path):
        sh3d = str(tmp_path / "envtex.sh3d")
        _run(["project", "new", "-o", sh3d])
        _run(["--project", sh3d, "environment", "set",
               "--sky-texture", "eTeks#blueSky",
               "--ground-texture", "eTeks#grass",
               "--background-on-ground"])
        sess = Session.open(sh3d)
        env = sess.home.environment
        assert env.skyTexture.catalogId == "eTeks#blueSky"
        assert env.groundTexture.catalogId == "eTeks#grass"
        assert env.backgroundImageVisibleOnGround3D is True


# ───────────────────────────────────────────────── CLI: find

class TestFindCLI:
    def _build_two_room_project(self, tmp_path):
        sh3d = str(tmp_path / "two.sh3d")
        _run(["project", "new", "-o", sh3d])
        _run(["--project", sh3d, "room", "rectangle", "0", "0", "400", "300",
               "-n", "Kitchen"])
        _run(["--project", sh3d, "room", "rectangle", "500", "0", "400", "300",
               "-n", "Living"])
        _run(["--project", sh3d, "wall", "add", "0", "0", "400", "0"])
        _run(["--project", sh3d, "furniture", "add-light", "KitchenLight",
               "200", "150"])
        _run(["--project", sh3d, "furniture", "add-light", "LivingLight",
               "700", "150"])
        _run(["--project", sh3d, "furniture", "add-door", "FrontDoor",
               "200", "0"])
        return sh3d

    def test_find_rooms_by_name(self, tmp_path):
        sh3d = self._build_two_room_project(tmp_path)
        r = _run(["--project", sh3d, "--json", "find", "rooms",
                   "--name", "Kit"])
        data = json.loads(r.stdout)
        assert len(data) == 1 and data[0]["name"] == "Kitchen"

    def test_find_rooms_contains(self, tmp_path):
        sh3d = self._build_two_room_project(tmp_path)
        # Point (700,150) is inside Living
        r = _run(["--project", sh3d, "--json", "find", "rooms",
                   "--contains", "700,150"])
        data = json.loads(r.stdout)
        assert [r["name"] for r in data] == ["Living"]

    def test_find_walls_near(self, tmp_path):
        sh3d = self._build_two_room_project(tmp_path)
        r = _run(["--project", sh3d, "--json", "find", "walls",
                   "--near", "200,5", "--max-distance", "50"])
        data = json.loads(r.stdout)
        assert len(data) == 1

    def test_find_lights_in_room(self, tmp_path):
        sh3d = self._build_two_room_project(tmp_path)
        r = _run(["--project", sh3d, "--json", "find", "lights",
                   "--in-room", "Kitchen"])
        data = json.loads(r.stdout)
        assert len(data) == 1 and data[0]["name"] == "KitchenLight"

    def test_find_doors_near(self, tmp_path):
        sh3d = self._build_two_room_project(tmp_path)
        r = _run(["--project", sh3d, "--json", "find", "doors",
                   "--near", "200,0"])
        data = json.loads(r.stdout)
        assert len(data) >= 1
        assert any(p["name"] == "FrontDoor" for p in data)


# ───────────────────────────────────────────────── CLI: polyline

class TestPolylineCLI:
    def test_add_list_set_delete(self, tmp_path):
        sh3d = str(tmp_path / "p.sh3d")
        _run(["project", "new", "-o", sh3d])
        r = _run(["--project", sh3d, "--json", "polyline", "add",
                   "--points", "0,0 100,100 200,0", "--thickness", "3",
                   "--closed", "--color", "#FF0000"])
        data = json.loads(r.stdout)
        assert data["thickness"] == 3 and data["closedPath"] is True
        pid = data["id"]

        r = _run(["--project", sh3d, "--json", "polyline", "list"])
        ls = json.loads(r.stdout)
        assert len(ls) == 1 and ls[0]["id"] == pid

        _run(["--project", sh3d, "polyline", "set", pid,
               "--start-arrow", "DELTA", "--end-arrow", "OPEN",
               "--dash-style", "DASH"])
        sess = Session.open(sh3d)
        p = sess.home.polylines[0]
        assert p.startArrowStyle == "DELTA"
        assert p.endArrowStyle == "OPEN"
        assert p.dashStyle == "DASH"

        _run(["--project", sh3d, "polyline", "delete", pid])
        sess = Session.open(sh3d)
        assert sess.home.polylines == []

    def test_round_trip_polyline_xml(self, tmp_path):
        sh3d = str(tmp_path / "p_rt.sh3d")
        _run(["project", "new", "-o", sh3d])
        _run(["--project", sh3d, "polyline", "add",
               "--points", "0,0 100,0", "--closed"])
        with zipfile.ZipFile(sh3d) as z:
            xml = z.read("Home.xml").decode()
        root = ET.fromstring(xml)
        polylines = root.findall("polyline")
        assert len(polylines) == 1
        # Two point children
        assert len(polylines[0].findall("point")) == 2


# ───────────────────────────────────────────────── CLI: level set / select

class TestLevelSetSelect:
    def test_level_set_renames(self, tmp_path):
        sh3d = str(tmp_path / "l.sh3d")
        _run(["project", "new", "-o", sh3d])
        r = _run(["--project", sh3d, "--json", "level", "add", "Ground"])
        lid = json.loads(r.stdout)["id"]
        _run(["--project", sh3d, "level", "set", lid,
               "--name", "GF", "--height", "275",
               "--floor-thickness", "20", "--hidden"])
        sess = Session.open(sh3d)
        lvl = sess.home.levels[0]
        assert lvl.name == "GF"
        assert lvl.height == 275
        assert lvl.floorThickness == 20
        assert lvl.visible is False

    def test_level_select(self, tmp_path):
        sh3d = str(tmp_path / "lsel.sh3d")
        _run(["project", "new", "-o", sh3d])
        r = _run(["--project", sh3d, "--json", "level", "add", "G"])
        lid = json.loads(r.stdout)["id"]
        _run(["--project", sh3d, "level", "select", lid])
        sess = Session.open(sh3d)
        assert sess.home.selectedLevel == lid
        _run(["--project", sh3d, "level", "select", "--clear"])
        sess = Session.open(sh3d)
        assert sess.home.selectedLevel is None

    def test_level_set_requires_option(self, tmp_path):
        sh3d = str(tmp_path / "lerr.sh3d")
        _run(["project", "new", "-o", sh3d])
        r = _run(["--project", sh3d, "--json", "level", "add", "G"])
        lid = json.loads(r.stdout)["id"]
        r = _run(["--project", sh3d, "level", "set", lid], check=False)
        assert r.returncode != 0


# ───────────────────────────────────────────────── CLI: camera save/list/go

class TestCameraStored:
    def test_save_list_go_delete(self, tmp_path):
        sh3d = str(tmp_path / "cs.sh3d")
        _run(["project", "new", "-o", sh3d])
        # Move observer so the saved viewpoint is non-default
        _run(["--project", sh3d, "camera", "set",
               "--kind", "observerCamera",
               "--x", "100", "--y", "200", "--z", "175",
               "--yaw", "1.5", "--pitch", "0.2"])
        _run(["--project", sh3d, "camera", "save", "viewA"])

        r = _run(["--project", sh3d, "--json", "camera", "list"])
        names = [c["name"] for c in json.loads(r.stdout)]
        assert names == ["viewA"]

        # Move camera somewhere else, then 'go' back
        _run(["--project", sh3d, "camera", "set",
               "--kind", "observerCamera",
               "--x", "0", "--y", "0", "--z", "0"])
        _run(["--project", sh3d, "camera", "go", "viewA"])
        sess = Session.open(sh3d)
        cam = sess.home.observerCamera
        assert (cam.x, cam.y, cam.z) == (100, 200, 175)
        assert sess.home.camera == "observerCamera"

        _run(["--project", sh3d, "camera", "delete", "viewA"])
        r = _run(["--project", sh3d, "--json", "camera", "list"])
        assert json.loads(r.stdout) == []

    def test_save_rejects_duplicate(self, tmp_path):
        sh3d = str(tmp_path / "csdup.sh3d")
        _run(["project", "new", "-o", sh3d])
        _run(["--project", sh3d, "camera", "save", "dup"])
        r = _run(["--project", sh3d, "camera", "save", "dup"], check=False)
        assert r.returncode != 0

    def test_go_unknown_fails(self, tmp_path):
        sh3d = str(tmp_path / "csgo.sh3d")
        _run(["project", "new", "-o", sh3d])
        r = _run(["--project", sh3d, "camera", "go", "nope"], check=False)
        assert r.returncode != 0


# ───────────────────────────────────────────────── CLI: baseboard

class TestBaseboardCLI:
    def test_baseboard_both_sides(self, tmp_path):
        sh3d = str(tmp_path / "bb.sh3d")
        _run(["project", "new", "-o", sh3d])
        r = _run(["--project", sh3d, "--json", "wall", "add",
                   "0", "0", "500", "0"])
        wid = json.loads(r.stdout)["id"]
        _run(["--project", sh3d, "wall", "baseboard", wid,
               "--side", "both", "--thickness", "1.5", "--height", "12",
               "--color", "#FFFFFFFF"])
        sess = Session.open(sh3d)
        w = sess.home.walls[0]
        assert w.leftSideBaseboard is not None
        assert w.rightSideBaseboard is not None
        assert w.leftSideBaseboard.height == 12
        assert w.leftSideBaseboard.thickness == 1.5

    def test_baseboard_with_texture(self, tmp_path):
        sh3d = str(tmp_path / "bbt.sh3d")
        _run(["project", "new", "-o", sh3d])
        r = _run(["--project", sh3d, "--json", "wall", "add",
                   "0", "0", "500", "0"])
        wid = json.loads(r.stdout)["id"]
        _run(["--project", sh3d, "wall", "baseboard", wid,
               "--side", "left", "--texture", "eTeks#smallWhiteBricks"])
        sess = Session.open(sh3d)
        w = sess.home.walls[0]
        assert w.leftSideBaseboard.texture is not None
        assert w.leftSideBaseboard.texture.catalogId == "eTeks#smallWhiteBricks"
        assert w.rightSideBaseboard is None

    def test_baseboard_clear(self, tmp_path):
        sh3d = str(tmp_path / "bbc.sh3d")
        _run(["project", "new", "-o", sh3d])
        r = _run(["--project", sh3d, "--json", "wall", "add",
                   "0", "0", "500", "0"])
        wid = json.loads(r.stdout)["id"]
        _run(["--project", sh3d, "wall", "baseboard", wid,
               "--side", "both", "--thickness", "1", "--height", "10"])
        _run(["--project", sh3d, "wall", "baseboard", wid,
               "--side", "right", "--clear"])
        sess = Session.open(sh3d)
        w = sess.home.walls[0]
        assert w.leftSideBaseboard is not None
        assert w.rightSideBaseboard is None


# ───────────────────────────────────────────────── CLI: dimension/label set

class TestDimensionLabelSet:
    def test_dimension_set(self, tmp_path):
        sh3d = str(tmp_path / "ds.sh3d")
        _run(["project", "new", "-o", sh3d])
        r = _run(["--project", sh3d, "--json", "dimension", "add",
                   "0", "0", "500", "0", "--offset", "40"])
        did = json.loads(r.stdout)["id"]
        _run(["--project", sh3d, "dimension", "set", did,
               "--offset", "80", "--color", "#FF0000FF",
               "--visible-in-3d", "--end-mark-size", "15"])
        sess = Session.open(sh3d)
        d = sess.home.dimensionLines[0]
        assert d.offset == 80
        assert d.visibleIn3D is True
        assert d.endMarkSize == 15

    def test_label_set(self, tmp_path):
        sh3d = str(tmp_path / "ls.sh3d")
        _run(["project", "new", "-o", sh3d])
        r = _run(["--project", sh3d, "--json", "label", "add",
                   "Hello", "100", "100"])
        lid = json.loads(r.stdout)["id"]
        _run(["--project", sh3d, "label", "set", lid,
               "--text", "World",
               "--angle", "0.5",
               "--outline-color", "#FF000000"])
        sess = Session.open(sh3d)
        l = sess.home.labels[0]
        assert l.text == "World"
        assert abs(l.angle - 0.5) < 1e-6
        assert l.outlineColor is not None


# ───────────────────────────────────────────────── CLI: video-size

class TestEnvironmentVideo:
    def test_video_size(self, tmp_path):
        sh3d = str(tmp_path / "vs.sh3d")
        _run(["project", "new", "-o", sh3d])
        _run(["--project", sh3d, "environment", "video-size", "1280",
               "--aspect", "RATIO_16_9", "--frame-rate", "30",
               "--quality", "2"])
        sess = Session.open(sh3d)
        env = sess.home.environment
        assert env.videoWidth == 1280
        assert env.videoAspectRatio == "RATIO_16_9"
        assert env.videoFrameRate == 30
        assert env.videoQuality == 2


# ───────────────────────────────────────────────── full refine workflow

class TestRefineWorkflow:
    """Build a fully decorated house using only the new commands and verify."""

    def test_decorated_two_room_house(self, tmp_path):
        sh3d = str(tmp_path / "decorated.sh3d")
        _run(["project", "new", "-n", "RefineHouse", "-o", sh3d])

        # Add level
        r = _run(["--project", sh3d, "--json", "level", "add", "Ground"])
        gid = json.loads(r.stdout)["id"]
        _run(["--project", sh3d, "level", "select", gid])

        # Two adjacent rooms with floor textures
        r = _run(["--project", sh3d, "--json", "room", "rectangle",
                   "0", "0", "400", "300",
                   "-n", "Kitchen", "-l", gid,
                   "--floor-texture", "eTeks#stoneTiles",
                   "--ceiling-color", "#FFFFFFFF"])
        kid = json.loads(r.stdout)["id"]

        r = _run(["--project", sh3d, "--json", "room", "rectangle",
                   "400", "0", "500", "300",
                   "-n", "Living", "-l", gid,
                   "--floor-texture", "eTeks#woodenFloor"])
        lid_room = json.loads(r.stdout)["id"]

        # Walls (with brick textures on the outer side)
        for x1, y1, x2, y2 in [(0, 0, 900, 0), (900, 0, 900, 300),
                                  (0, 300, 900, 300), (0, 0, 0, 300),
                                  (400, 0, 400, 300)]:
            _run(["--project", sh3d, "wall", "add",
                   str(x1), str(y1), str(x2), str(y2),
                   "-l", gid,
                   "--left-texture", "eTeks#smallBricks",
                   "--right-texture", "eTeks#roughcast"])

        # Wall ids for baseboards
        wlist = json.loads(_run(["--project", sh3d, "--json",
                                  "wall", "list"]).stdout)
        first_wall = wlist[0]["id"]
        _run(["--project", sh3d, "wall", "baseboard", first_wall,
               "--side", "both", "--thickness", "1", "--height", "10",
               "--color", "#FFFFFFFF"])

        # Polyline decoration
        _run(["--project", sh3d, "polyline", "add",
               "--points", "50,50 350,50 350,250 50,250",
               "--thickness", "2", "--closed", "--color", "#FF888888"])

        # Lights + dimension
        _run(["--project", sh3d, "furniture", "add-light",
               "CeilingK", "200", "150", "-l", gid])
        _run(["--project", sh3d, "furniture", "add-light",
               "CeilingL", "650", "150", "-l", gid])
        r = _run(["--project", sh3d, "--json", "dimension", "add",
                   "0", "0", "900", "0", "--offset", "40", "-l", gid])
        did = json.loads(r.stdout)["id"]
        _run(["--project", sh3d, "dimension", "set", did,
               "--color", "#FF0000FF", "--visible-in-3d"])

        # Environment textures
        _run(["--project", sh3d, "environment", "set",
               "--sky-texture", "eTeks#blueSky",
               "--ground-texture", "eTeks#grass",
               "--all-levels-visible"])

        # Save a stored camera viewpoint for renders
        _run(["--project", sh3d, "camera", "set",
               "--kind", "observerCamera",
               "--x", "200", "--y", "150", "--z", "170",
               "--yaw", "0.5"])
        _run(["--project", sh3d, "camera", "save", "kitchen-view"])

        # Find a wall near the front door point — should match
        r = _run(["--project", sh3d, "--json", "find", "walls",
                   "--near", "450,0"])
        hits = json.loads(r.stdout)
        assert hits  # at least one wall close to the front

        # Find lights in Kitchen room
        r = _run(["--project", sh3d, "--json", "find", "lights",
                   "--in-room", "Kitchen"])
        lights = json.loads(r.stdout)
        assert [l["name"] for l in lights] == ["CeilingK"]

        # Full reload: structural integrity
        sess = Session.open(sh3d)
        assert sess.home.name == "RefineHouse"
        assert len(sess.home.rooms) == 2
        assert len(sess.home.walls) == 5
        assert len(sess.home.polylines) == 1
        assert len(sess.home.storedCameras) == 1
        assert sess.home.environment.skyTexture.catalogId == "eTeks#blueSky"
        assert sess.home.rooms[0].floorTexture is not None
        assert sess.home.walls[0].leftSideBaseboard is not None
        assert sess.home.dimensionLines[0].visibleIn3D is True

        # XML uses canonical flat texture form everywhere
        with zipfile.ZipFile(sh3d) as z:
            xml = z.read("Home.xml").decode()
        attrs_found = set(re.findall(
            r'<texture\s+attribute="(\w+)"', xml))
        assert "leftSideTexture" in attrs_found
        assert "rightSideTexture" in attrs_found
        assert "floorTexture" in attrs_found
        assert "skyTexture" in attrs_found
        assert "groundTexture" in attrs_found
        # No legacy wrappers
        assert "<leftSideTexture>" not in xml
        assert "<floorTexture>" not in xml

        print(f"\n  .sh3d: {sh3d} ({os.path.getsize(sh3d):,} bytes)")
