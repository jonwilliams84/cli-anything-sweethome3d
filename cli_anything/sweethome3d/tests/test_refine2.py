"""Tests for the 2026-05-22 refine pass v2.

Covers:
- furniture groups (group/ungroup/list/info/add/remove/delete/set)
- per-piece materials (material list/set/clear/clear-all)
- door/window sashes (sash list/add/delete/clear)
- light emitters (emitter source/material add/list/delete/clear)
- shelf-unit shelves (shelf list/add/delete/clear)
- background plan image (background set/clear/show/hide/info)
- print settings (print get/set/clear/add-level/remove-level/set-levels)
- stored-camera kind preservation bug fix

Each domain has:
- a core-level test confirming XML round-trip
- a CLI subprocess test using the installed `cli-anything-sweethome3d` command
"""

from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
import sys
import zipfile
from xml.etree import ElementTree as ET

import pytest

from cli_anything.sweethome3d.core import (
    background_image as bg_core,
    catalog_scan as catalog_scan_core,
    find as find_core,
    furniture as furn_core,
    furniture_groups as group_core,
    levels as lvl_core,
    light_emitters as light_core,
    materials as mat_core,
    print_settings as print_core,
    project as proj_core,
    rooms as rooms_core,
    sashes as sash_core,
    shelves as shelf_core,
    validate as validate_core,
    walls as walls_core,
)
from cli_anything.sweethome3d.core.model import (
    Camera,
    Home,
    LightSource,
    LightSourceMaterial,
    Material,
    PieceOfFurniture,
    Sash,
    Shelf,
    Texture,
)
from cli_anything.sweethome3d.core.session import Session


# ─────────────────────────────────────── CLI resolution

def _resolve_cli(name):
    force = os.environ.get("CLI_ANYTHING_FORCE_INSTALLED", "").strip() == "1"
    path = shutil.which(name)
    if path:
        return [path]
    if force:
        raise RuntimeError(f"{name} not found in PATH. Install with: pip install -e .")
    return [sys.executable, "-m", "cli_anything.sweethome3d"]


CLI = _resolve_cli("cli-anything-sweethome3d")


def _run(args, check=True):
    r = subprocess.run(CLI + args, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise AssertionError(
            f"CLI failed: {args}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
        )
    return r


# ─────────────────────────────────────── tiny PNG generator

def _png_bytes(width: int = 8, height: int = 8) -> bytes:
    """Build a valid 1-byte-per-pixel greyscale PNG without Pillow.

    Tests only need a parseable PNG so the .sh3d ZIP carries something
    SH3D's BackgroundImage reader will accept.
    """
    import zlib

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)  # 8-bit greyscale
    raw = b"".join(b"\x00" + b"\x80" * width for _ in range(height))
    idat = zlib.compress(raw)
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


# ──────────────────────────────────────────────────── furniture groups: core

class TestFurnitureGroupsCore:
    def _seed_home(self) -> Home:
        h = proj_core.new_home("GroupTest")
        furn_core.add_piece(h, "Sofa", 100, 200, width=200, depth=90, height=80)
        furn_core.add_piece(h, "Chair", 300, 200, width=60, depth=60, height=90)
        furn_core.add_piece(h, "Table", 200, 300, width=120, depth=80, height=72)
        return h

    def test_create_moves_pieces_into_group(self):
        h = self._seed_home()
        grp = group_core.create_group(h, "DiningSet",
                                        piece_idents=["Chair", "Table"])
        # Top-level home.furniture should only contain Sofa now
        assert [p.name for p in h.furniture] == ["Sofa"]
        # Group holds the moved members
        assert len(grp.furniture) == 2
        assert grp.name == "DiningSet"
        assert h.furnitureGroups == [grp]

    def test_create_bounds_recomputed(self):
        h = self._seed_home()
        grp = group_core.create_group(h, "DiningSet",
                                        piece_idents=["Chair", "Table"])
        # Chair: x=300±30, y=200±30 → x range [270,330], y range [170,230]
        # Table: x=200±60, y=300±40 → x range [140,260], y range [260,340]
        # Union: x [140,330] → centre 235, width 190
        #        y [170,340] → centre 255, depth 170
        assert grp.x == pytest.approx(235.0)
        assert grp.y == pytest.approx(255.0)
        assert grp.width == pytest.approx(190.0)
        assert grp.depth == pytest.approx(170.0)

    def test_create_rejects_empty(self):
        h = self._seed_home()
        with pytest.raises(ValueError):
            group_core.create_group(h, "Empty", piece_idents=[])

    def test_create_rejects_unknown_piece(self):
        h = self._seed_home()
        with pytest.raises(KeyError):
            group_core.create_group(h, "Bad", piece_idents=["Nonexistent"])

    def test_ungroup_releases_pieces(self):
        h = self._seed_home()
        grp = group_core.create_group(h, "DiningSet",
                                        piece_idents=["Chair", "Table"])
        released = group_core.ungroup(h, grp.id)
        assert len(released) == 2
        assert [p.name for p in h.furniture] == ["Sofa", "Chair", "Table"]
        assert h.furnitureGroups == []

    def test_add_to_existing_group(self):
        h = self._seed_home()
        grp = group_core.create_group(h, "Set", piece_idents=["Chair"])
        group_core.add_to_group(h, "Set", ["Table"])
        assert len(grp.furniture) == 2
        assert [p.name for p in h.furniture] == ["Sofa"]

    def test_remove_from_group(self):
        h = self._seed_home()
        grp = group_core.create_group(h, "Set", piece_idents=["Chair", "Table"])
        group_core.remove_from_group(h, "Set", ["Chair"])
        assert [p.name for p in grp.furniture] == ["Table"]
        assert any(p.name == "Chair" for p in h.furniture)

    def test_delete_group_drops_members(self):
        h = self._seed_home()
        group_core.create_group(h, "Set", piece_idents=["Chair", "Table"])
        deleted = group_core.delete_group(h, "Set")
        assert len(deleted) == 2
        assert h.furnitureGroups == []
        # Members are NOT returned to home.furniture (use ungroup for that)
        assert [p.name for p in h.furniture] == ["Sofa"]

    def test_set_group_properties(self):
        h = self._seed_home()
        grp = group_core.create_group(h, "Set", piece_idents=["Chair", "Table"])
        group_core.set_group_properties(h, grp.id, name="Renamed",
                                          visible=False, price="500.00")
        assert grp.name == "Renamed"
        assert grp.visible is False
        assert grp.price == "500.00"

    def test_set_unknown_field_raises(self):
        h = self._seed_home()
        grp = group_core.create_group(h, "Set", piece_idents=["Chair"])
        with pytest.raises(AttributeError):
            group_core.set_group_properties(h, grp.id, bogus="x")

    def test_round_trip_group_xml(self, tmp_path):
        h = self._seed_home()
        group_core.create_group(h, "DiningSet",
                                  piece_idents=["Chair", "Table"])
        p = str(tmp_path / "grp.sh3d")
        proj_core.save_home(h, p)
        h2 = proj_core.open_home(p)
        assert len(h2.furnitureGroups) == 1
        assert h2.furnitureGroups[0].name == "DiningSet"
        assert len(h2.furnitureGroups[0].furniture) == 2


# ──────────────────────────────────────────────────── furniture groups: CLI

class TestFurnitureGroupsCLI:
    def test_create_list_ungroup(self, tmp_path):
        sh3d = str(tmp_path / "g.sh3d")
        _run(["project", "new", "-o", sh3d])
        _run(["--project", sh3d, "furniture", "add", "Chair",
               "300", "200", "--width", "60", "--depth", "60", "--height", "90"])
        _run(["--project", sh3d, "furniture", "add", "Table",
               "200", "300", "--width", "120", "--depth", "80", "--height", "72"])
        r = _run(["--project", sh3d, "--json", "group", "create", "Dining",
                   "--pieces", "Chair,Table"])
        grp = json.loads(r.stdout)
        assert grp["name"] == "Dining"
        assert len(grp["furniture"]) == 2
        r = _run(["--project", sh3d, "--json", "group", "list"])
        assert json.loads(r.stdout)[0]["name"] == "Dining"
        _run(["--project", sh3d, "group", "ungroup", "Dining"])
        sess = Session.open(sh3d)
        assert sess.home.furnitureGroups == []
        assert len(sess.home.furniture) == 2

    def test_set_renames(self, tmp_path):
        sh3d = str(tmp_path / "gs.sh3d")
        _run(["project", "new", "-o", sh3d])
        _run(["--project", sh3d, "furniture", "add", "Chair",
               "0", "0", "--width", "60", "--depth", "60", "--height", "90"])
        _run(["--project", sh3d, "group", "create", "Set", "--pieces", "Chair"])
        _run(["--project", sh3d, "group", "set", "Set",
               "--name", "Renamed", "--hidden"])
        sess = Session.open(sh3d)
        grp = sess.home.furnitureGroups[0]
        assert grp.name == "Renamed"
        assert grp.visible is False

    def test_delete_removes_members(self, tmp_path):
        sh3d = str(tmp_path / "gd.sh3d")
        _run(["project", "new", "-o", sh3d])
        _run(["--project", sh3d, "furniture", "add", "Chair",
               "0", "0", "--width", "60", "--depth", "60", "--height", "90"])
        _run(["--project", sh3d, "furniture", "add", "Table",
               "100", "0", "--width", "100", "--depth", "60", "--height", "72"])
        _run(["--project", sh3d, "group", "create", "Set",
               "--pieces", "Chair,Table"])
        _run(["--project", sh3d, "group", "delete", "Set"])
        sess = Session.open(sh3d)
        assert sess.home.furnitureGroups == []
        assert sess.home.furniture == []


# ──────────────────────────────────────────────────── materials: core

class TestMaterialsCore:
    def _seed(self) -> Home:
        h = proj_core.new_home("M")
        furn_core.add_piece(h, "Sofa", 100, 100,
                              width=200, depth=90, height=80)
        return h

    def test_set_creates_material(self):
        h = self._seed()
        mat = mat_core.set_material(h, "Sofa", "Cushion",
                                      color=0xFF8080FF, shininess=0.4)
        assert mat.name == "Cushion"
        assert mat.color == 0xFF8080FF
        assert mat.shininess == pytest.approx(0.4)
        piece = h.find_furniture("Sofa")
        assert piece.materials == [mat]

    def test_set_updates_existing(self):
        h = self._seed()
        mat_core.set_material(h, "Sofa", "Cushion", color=0xFFAABBCC)
        mat_core.set_material(h, "Sofa", "Cushion", shininess=0.8)
        piece = h.find_furniture("Sofa")
        assert len(piece.materials) == 1
        assert piece.materials[0].color == 0xFFAABBCC
        assert piece.materials[0].shininess == pytest.approx(0.8)

    def test_set_clear_color(self):
        h = self._seed()
        mat_core.set_material(h, "Sofa", "Cushion", color=0xFFAABBCC)
        mat_core.set_material(h, "Sofa", "Cushion", clear_color=True)
        assert h.find_furniture("Sofa").materials[0].color is None

    def test_set_with_texture(self):
        h = self._seed()
        mat = mat_core.set_material(h, "Sofa", "Cushion",
                                      texture_id="eTeks#marbleWall")
        assert mat.texture is not None
        assert mat.texture.catalogId == "eTeks#marbleWall"

    def test_clear_material(self):
        h = self._seed()
        mat_core.set_material(h, "Sofa", "Cushion", color=0xFFAABBCC)
        mat_core.set_material(h, "Sofa", "Frame", color=0xFF112233)
        ok = mat_core.clear_material(h, "Sofa", "Cushion")
        assert ok is True
        assert [m.name for m in h.find_furniture("Sofa").materials] == ["Frame"]

    def test_clear_all(self):
        h = self._seed()
        mat_core.set_material(h, "Sofa", "Cushion", color=0xFFAABBCC)
        mat_core.set_material(h, "Sofa", "Frame", color=0xFF112233)
        n = mat_core.clear_all_materials(h, "Sofa")
        assert n == 2
        assert h.find_furniture("Sofa").materials == []

    def test_round_trip_xml(self, tmp_path):
        h = self._seed()
        mat_core.set_material(h, "Sofa", "Cushion",
                                color=0xFFAABBCC, shininess=0.5,
                                texture_id="eTeks#marbleWall")
        p = str(tmp_path / "m.sh3d")
        proj_core.save_home(h, p)
        h2 = proj_core.open_home(p)
        piece = h2.find_furniture("Sofa")
        assert len(piece.materials) == 1
        m = piece.materials[0]
        assert m.name == "Cushion"
        assert m.color == 0xFFAABBCC
        assert m.shininess == pytest.approx(0.5)
        assert m.texture is not None
        assert m.texture.catalogId == "eTeks#marbleWall"


# ──────────────────────────────────────────────────── materials: CLI

class TestMaterialsCLI:
    def test_set_list_clear(self, tmp_path):
        sh3d = str(tmp_path / "mc.sh3d")
        _run(["project", "new", "-o", sh3d])
        _run(["--project", sh3d, "furniture", "add", "Sofa",
               "0", "0", "--width", "200", "--depth", "90", "--height", "80"])
        _run(["--project", sh3d, "material", "set", "Sofa", "Cushion",
               "--color", "#AABBCC", "--shininess", "0.4"])
        r = _run(["--project", sh3d, "--json", "material", "list", "Sofa"])
        mats = json.loads(r.stdout)
        assert len(mats) == 1
        assert mats[0]["name"] == "Cushion"
        _run(["--project", sh3d, "material", "clear", "Sofa", "Cushion"])
        r = _run(["--project", sh3d, "--json", "material", "list", "Sofa"])
        assert json.loads(r.stdout) == []

    def test_set_with_texture_cli(self, tmp_path):
        sh3d = str(tmp_path / "mt.sh3d")
        _run(["project", "new", "-o", sh3d])
        _run(["--project", sh3d, "furniture", "add", "Sofa",
               "0", "0", "--width", "200", "--depth", "90", "--height", "80"])
        _run(["--project", sh3d, "material", "set", "Sofa", "Cushion",
               "--texture", "eTeks#marbleWall"])
        sess = Session.open(sh3d)
        mat = sess.home.find_furniture("Sofa").materials[0]
        assert mat.texture.catalogId == "eTeks#marbleWall"


# ──────────────────────────────────────────────────── sashes: core

class TestSashesCore:
    def _door_home(self) -> Home:
        h = proj_core.new_home("S")
        furn_core.add_door(h, "Door", 100, 100,
                             width=80, depth=10, height=200)
        return h

    def test_add_sash(self):
        h = self._door_home()
        sash = sash_core.add_sash(h, "Door",
                                    xAxis=0, yAxis=0, width=1.0,
                                    startAngle=0, endAngle=1.5)
        assert sash.xAxis == 0
        assert sash.endAngle == pytest.approx(1.5)
        assert len(h.find_furniture("Door").sashes) == 1

    def test_add_sash_rejects_non_door(self):
        h = proj_core.new_home("S")
        furn_core.add_piece(h, "Sofa", 0, 0,
                              width=200, depth=90, height=80)
        with pytest.raises(ValueError):
            sash_core.add_sash(h, "Sofa", xAxis=0, yAxis=0, width=1,
                                startAngle=0, endAngle=1)

    def test_add_sash_rejects_bad_fraction(self):
        h = self._door_home()
        with pytest.raises(ValueError):
            sash_core.add_sash(h, "Door", xAxis=5, yAxis=0, width=1,
                                startAngle=0, endAngle=1)

    def test_delete_sash(self):
        h = self._door_home()
        sash_core.add_sash(h, "Door", xAxis=0, yAxis=0, width=1.0,
                             startAngle=0, endAngle=1.5)
        sash_core.add_sash(h, "Door", xAxis=0.5, yAxis=0, width=0.5,
                             startAngle=0, endAngle=1.0)
        removed = sash_core.delete_sash(h, "Door", 0)
        assert removed.xAxis == 0
        assert len(h.find_furniture("Door").sashes) == 1

    def test_clear_sashes(self):
        h = self._door_home()
        sash_core.add_sash(h, "Door", xAxis=0, yAxis=0, width=1.0,
                             startAngle=0, endAngle=1.5)
        sash_core.add_sash(h, "Door", xAxis=0.5, yAxis=0, width=0.5,
                             startAngle=0, endAngle=1.0)
        assert sash_core.clear_sashes(h, "Door") == 2

    def test_round_trip(self, tmp_path):
        h = self._door_home()
        sash_core.add_sash(h, "Door", xAxis=0.0, yAxis=0.0, width=0.95,
                             startAngle=0, endAngle=1.5707)
        p = str(tmp_path / "s.sh3d")
        proj_core.save_home(h, p)
        h2 = proj_core.open_home(p)
        sashes = h2.find_furniture("Door").sashes
        assert len(sashes) == 1
        assert sashes[0].width == pytest.approx(0.95)
        assert sashes[0].endAngle == pytest.approx(1.5707)


# ──────────────────────────────────────────────────── sashes: CLI

class TestSashesCLI:
    def test_add_list_delete(self, tmp_path):
        sh3d = str(tmp_path / "scli.sh3d")
        _run(["project", "new", "-o", sh3d])
        _run(["--project", sh3d, "furniture", "add-door", "Door",
               "0", "0"])
        _run(["--project", sh3d, "sash", "add", "Door",
               "--x-axis", "0", "--y-axis", "0", "--width", "1.0",
               "--start-angle", "0", "--end-angle", "1.5"])
        r = _run(["--project", sh3d, "--json", "sash", "list", "Door"])
        sashes = json.loads(r.stdout)
        assert len(sashes) == 1
        _run(["--project", sh3d, "sash", "delete", "Door", "0"])
        r = _run(["--project", sh3d, "--json", "sash", "list", "Door"])
        assert json.loads(r.stdout) == []

    def test_clear(self, tmp_path):
        sh3d = str(tmp_path / "sc.sh3d")
        _run(["project", "new", "-o", sh3d])
        _run(["--project", sh3d, "furniture", "add-door", "Door", "0", "0"])
        for _ in range(3):
            _run(["--project", sh3d, "sash", "add", "Door",
                   "--x-axis", "0", "--y-axis", "0", "--width", "0.5",
                   "--start-angle", "0", "--end-angle", "1.0"])
        _run(["--project", sh3d, "sash", "clear", "Door"])
        sess = Session.open(sh3d)
        assert sess.home.find_furniture("Door").sashes == []

    def test_rejects_non_door(self, tmp_path):
        sh3d = str(tmp_path / "srej.sh3d")
        _run(["project", "new", "-o", sh3d])
        _run(["--project", sh3d, "furniture", "add", "Sofa",
               "0", "0", "--width", "200", "--depth", "90", "--height", "80"])
        r = _run(["--project", sh3d, "sash", "add", "Sofa",
                   "--x-axis", "0", "--y-axis", "0", "--width", "1",
                   "--start-angle", "0", "--end-angle", "1"], check=False)
        assert r.returncode != 0


# ──────────────────────────────────────────────────── emitters: core

class TestLightEmittersCore:
    def _light_home(self) -> Home:
        h = proj_core.new_home("L")
        furn_core.add_light(h, "Lamp", 100, 100,
                              width=20, depth=20, height=20)
        return h

    def test_add_source(self):
        h = self._light_home()
        src = light_core.add_source(h, "Lamp", x=0, y=0, z=0.5,
                                      color=0xFFFFFF80, diameter=2.0)
        assert src.z == pytest.approx(0.5)
        assert src.diameter == 2.0
        assert len(h.find_furniture("Lamp").lightSources) == 1

    def test_add_source_rejects_non_light(self):
        h = proj_core.new_home("L")
        furn_core.add_piece(h, "Chair", 0, 0,
                              width=60, depth=60, height=90)
        with pytest.raises(ValueError):
            light_core.add_source(h, "Chair", x=0, y=0, z=0,
                                    color=0xFFFFFFFF)

    def test_clear_sources(self):
        h = self._light_home()
        light_core.add_source(h, "Lamp", x=0, y=0, z=0.5, color=0xFFFFFFFF)
        light_core.add_source(h, "Lamp", x=0.5, y=0, z=0.5, color=0xFFFFFFFF)
        assert light_core.clear_sources(h, "Lamp") == 2

    def test_add_emissive_material(self):
        h = self._light_home()
        m = light_core.add_material(h, "Lamp", "Shade")
        assert m.name == "Shade"
        assert h.find_furniture("Lamp").lightSourceMaterials == [m]

    def test_duplicate_material_rejected(self):
        h = self._light_home()
        light_core.add_material(h, "Lamp", "Shade")
        with pytest.raises(ValueError):
            light_core.add_material(h, "Lamp", "Shade")

    def test_delete_material(self):
        h = self._light_home()
        light_core.add_material(h, "Lamp", "Shade")
        light_core.add_material(h, "Lamp", "Bulb")
        assert light_core.delete_material(h, "Lamp", "Shade") is True
        names = [m.name for m in h.find_furniture("Lamp").lightSourceMaterials]
        assert names == ["Bulb"]

    def test_round_trip(self, tmp_path):
        h = self._light_home()
        light_core.add_source(h, "Lamp", x=0, y=0, z=0.5,
                                color=0xFFFFFF80, diameter=2.5)
        light_core.add_material(h, "Lamp", "Shade")
        p = str(tmp_path / "le.sh3d")
        proj_core.save_home(h, p)
        h2 = proj_core.open_home(p)
        piece = h2.find_furniture("Lamp")
        assert len(piece.lightSources) == 1
        assert piece.lightSources[0].diameter == pytest.approx(2.5)
        assert [m.name for m in piece.lightSourceMaterials] == ["Shade"]


# ──────────────────────────────────────────────────── emitters: CLI

class TestLightEmittersCLI:
    def test_source_add_list_delete(self, tmp_path):
        sh3d = str(tmp_path / "ec.sh3d")
        _run(["project", "new", "-o", sh3d])
        _run(["--project", sh3d, "furniture", "add-light", "Lamp",
               "100", "100"])
        _run(["--project", sh3d, "emitter", "source", "add", "Lamp",
               "--x", "0", "--y", "0", "--z", "0.5",
               "--color", "#FFFFFF", "--diameter", "2.5"])
        r = _run(["--project", sh3d, "--json", "emitter", "source", "list", "Lamp"])
        srcs = json.loads(r.stdout)
        assert len(srcs) == 1
        assert srcs[0]["diameter"] == pytest.approx(2.5)
        _run(["--project", sh3d, "emitter", "source", "delete", "Lamp", "0"])
        r = _run(["--project", sh3d, "--json", "emitter", "source", "list", "Lamp"])
        assert json.loads(r.stdout) == []

    def test_material_add_delete(self, tmp_path):
        sh3d = str(tmp_path / "em.sh3d")
        _run(["project", "new", "-o", sh3d])
        _run(["--project", sh3d, "furniture", "add-light", "Lamp",
               "100", "100"])
        _run(["--project", sh3d, "emitter", "material", "add", "Lamp", "Shade"])
        r = _run(["--project", sh3d, "--json", "emitter", "material", "list", "Lamp"])
        mats = json.loads(r.stdout)
        assert [m["name"] for m in mats] == ["Shade"]
        _run(["--project", sh3d, "emitter", "material", "delete", "Lamp", "Shade"])
        r = _run(["--project", sh3d, "--json", "emitter", "material", "list", "Lamp"])
        assert json.loads(r.stdout) == []


# ──────────────────────────────────────────────────── shelves: core

class TestShelvesCore:
    def _shelf_home(self) -> Home:
        h = proj_core.new_home("Sh")
        piece = furn_core.add_piece(h, "Bookcase", 0, 0,
                                      width=80, depth=30, height=180,
                                      kind="pieceOfFurniture")
        # Manually mark as shelfUnit since add_piece validates kinds
        piece.kind = "shelfUnit"
        return h

    def test_add_flat_shelf(self):
        h = self._shelf_home()
        sh = shelf_core.add_flat_shelf(h, "Bookcase", 45.0)
        assert sh.elevation == 45.0
        assert h.find_furniture("Bookcase").shelves == [sh]

    def test_add_box_shelf(self):
        h = self._shelf_home()
        sh = shelf_core.add_box_shelf(h, "Bookcase",
                                        xLower=-30, yLower=-10, zLower=0,
                                        xUpper=30, yUpper=10, zUpper=20)
        assert sh.zUpper == 20

    def test_add_box_shelf_rejects_bad_bounds(self):
        h = self._shelf_home()
        with pytest.raises(ValueError):
            shelf_core.add_box_shelf(h, "Bookcase",
                                       xLower=0, yLower=0, zLower=0,
                                       xUpper=0, yUpper=10, zUpper=10)

    def test_rejects_non_shelf_unit(self):
        h = proj_core.new_home("Sh")
        furn_core.add_piece(h, "Sofa", 0, 0,
                              width=200, depth=90, height=80)
        with pytest.raises(ValueError):
            shelf_core.add_flat_shelf(h, "Sofa", 40)

    def test_clear(self):
        h = self._shelf_home()
        shelf_core.add_flat_shelf(h, "Bookcase", 30)
        shelf_core.add_flat_shelf(h, "Bookcase", 60)
        assert shelf_core.clear_shelves(h, "Bookcase") == 2

    def test_round_trip(self, tmp_path):
        h = self._shelf_home()
        shelf_core.add_flat_shelf(h, "Bookcase", 45.0)
        shelf_core.add_box_shelf(h, "Bookcase",
                                   xLower=-30, yLower=-10, zLower=60,
                                   xUpper=30, yUpper=10, zUpper=120)
        p = str(tmp_path / "sh.sh3d")
        proj_core.save_home(h, p)
        h2 = proj_core.open_home(p)
        shelves = h2.find_furniture("Bookcase").shelves
        assert len(shelves) == 2
        flat = [s for s in shelves if s.elevation is not None]
        box = [s for s in shelves if s.elevation is None]
        assert flat[0].elevation == pytest.approx(45.0)
        assert box[0].zUpper == pytest.approx(120)


# ──────────────────────────────────────────────────── background: core

class TestBackgroundImageCore:
    def test_set_attaches_and_returns_bytes(self, tmp_path):
        h = proj_core.new_home("B")
        png_path = str(tmp_path / "plan.png")
        with open(png_path, "wb") as f:
            f.write(_png_bytes())
        bg, extra = bg_core.set_background(
            h, image_path=png_path,
            scale_distance_cm=200,
            scale_x_start=10, scale_y_start=10,
            scale_x_end=110, scale_y_end=10,
        )
        assert h.backgroundImage is bg
        assert bg.scaleDistance == 200
        assert bg.image in extra
        assert extra[bg.image][:8] == b"\x89PNG\r\n\x1a\n"

    def test_set_validation_rejects_zero_scale(self, tmp_path):
        h = proj_core.new_home("B")
        png_path = str(tmp_path / "p.png")
        with open(png_path, "wb") as f:
            f.write(_png_bytes())
        with pytest.raises(ValueError):
            bg_core.set_background(h, image_path=png_path,
                                     scale_distance_cm=0,
                                     scale_x_start=0, scale_y_start=0,
                                     scale_x_end=1, scale_y_end=1)

    def test_set_rejects_identical_endpoints(self, tmp_path):
        h = proj_core.new_home("B")
        png_path = str(tmp_path / "p.png")
        with open(png_path, "wb") as f:
            f.write(_png_bytes())
        with pytest.raises(ValueError):
            bg_core.set_background(h, image_path=png_path,
                                     scale_distance_cm=100,
                                     scale_x_start=10, scale_y_start=10,
                                     scale_x_end=10, scale_y_end=10)

    def test_set_per_level(self, tmp_path):
        h = proj_core.new_home("B")
        from cli_anything.sweethome3d.core import levels as lvl_core
        lvl = lvl_core.add_level(h, "Ground")
        png_path = str(tmp_path / "p.png")
        with open(png_path, "wb") as f:
            f.write(_png_bytes())
        bg, _ = bg_core.set_background(h, image_path=png_path,
                                          scale_distance_cm=100,
                                          scale_x_start=0, scale_y_start=0,
                                          scale_x_end=100, scale_y_end=0,
                                          level="Ground")
        assert h.backgroundImage is None
        assert lvl.backgroundImage is bg

    def test_clear(self, tmp_path):
        h = proj_core.new_home("B")
        png_path = str(tmp_path / "p.png")
        with open(png_path, "wb") as f:
            f.write(_png_bytes())
        bg_core.set_background(h, image_path=png_path,
                                  scale_distance_cm=100,
                                  scale_x_start=0, scale_y_start=0,
                                  scale_x_end=100, scale_y_end=0)
        assert bg_core.clear_background(h) is True
        assert bg_core.clear_background(h) is False  # already empty
        assert h.backgroundImage is None

    def test_round_trip(self, tmp_path):
        h = proj_core.new_home("B")
        png_path = str(tmp_path / "plan.png")
        with open(png_path, "wb") as f:
            f.write(_png_bytes())
        bg, extra = bg_core.set_background(
            h, image_path=png_path,
            scale_distance_cm=200,
            scale_x_start=10, scale_y_start=10,
            scale_x_end=110, scale_y_end=10,
            x_origin=5, y_origin=5,
        )
        sh3d = str(tmp_path / "bg.sh3d")
        proj_core.save_home(h, sh3d, extra_content=extra)
        # Confirm the PNG entry is inside the ZIP
        with zipfile.ZipFile(sh3d) as z:
            assert bg.image in z.namelist()
            assert z.read(bg.image)[:8] == b"\x89PNG\r\n\x1a\n"
        h2 = proj_core.open_home(sh3d)
        assert h2.backgroundImage is not None
        assert h2.backgroundImage.scaleDistance == 200
        assert h2.backgroundImage.xOrigin == 5


# ──────────────────────────────────────────────────── background: CLI

class TestBackgroundImageCLI:
    def test_set_via_cli_embeds_png(self, tmp_path):
        sh3d = str(tmp_path / "bg.sh3d")
        png_path = str(tmp_path / "plan.png")
        with open(png_path, "wb") as f:
            f.write(_png_bytes())
        _run(["project", "new", "-o", sh3d])
        r = _run(["--project", sh3d, "--json", "background", "set", png_path,
                   "--scale-distance", "200",
                   "--x-start", "10", "--y-start", "10",
                   "--x-end", "110", "--y-end", "10"])
        bg = json.loads(r.stdout)
        assert bg["scaleDistance"] == 200
        # PNG must be in the ZIP
        with zipfile.ZipFile(sh3d) as z:
            assert bg["image"] in z.namelist()
            assert z.read(bg["image"])[:8] == b"\x89PNG\r\n\x1a\n"

    def test_show_hide_clear(self, tmp_path):
        sh3d = str(tmp_path / "bgvis.sh3d")
        png_path = str(tmp_path / "plan.png")
        with open(png_path, "wb") as f:
            f.write(_png_bytes())
        _run(["project", "new", "-o", sh3d])
        _run(["--project", sh3d, "background", "set", png_path,
               "--scale-distance", "200",
               "--x-start", "0", "--y-start", "0",
               "--x-end", "100", "--y-end", "0"])
        _run(["--project", sh3d, "background", "hide"])
        sess = Session.open(sh3d)
        assert sess.home.backgroundImage.visible is False
        _run(["--project", sh3d, "background", "show"])
        sess = Session.open(sh3d)
        assert sess.home.backgroundImage.visible is True
        _run(["--project", sh3d, "background", "clear"])
        sess = Session.open(sh3d)
        assert sess.home.backgroundImage is None

    def test_clear_no_image_fails(self, tmp_path):
        sh3d = str(tmp_path / "bgempty.sh3d")
        _run(["project", "new", "-o", sh3d])
        r = _run(["--project", sh3d, "background", "clear"], check=False)
        assert r.returncode != 0


# ──────────────────────────────────────────────────── print: core

class TestPrintSettingsCore:
    def test_set_creates_defaults(self):
        h = proj_core.new_home("P")
        pr = print_core.set_print(h, paperWidth=297, paperHeight=420)
        assert pr.paperWidth == 297
        assert pr.paperOrientation == "PORTRAIT"

    def test_set_validates_orientation(self):
        h = proj_core.new_home("P")
        with pytest.raises(ValueError):
            print_core.set_print(h, paperOrientation="SIDEWAYS")

    def test_set_validates_positive(self):
        h = proj_core.new_home("P")
        with pytest.raises(ValueError):
            print_core.set_print(h, paperWidth=-10)

    def test_add_remove_levels(self):
        from cli_anything.sweethome3d.core import levels as lvl_core
        h = proj_core.new_home("P")
        g = lvl_core.add_level(h, "Ground")
        u = lvl_core.add_level(h, "Upper")
        print_core.add_printed_level(h, "Ground")
        print_core.add_printed_level(h, "Upper")
        assert h.printSettings.printedLevels == [g.id, u.id]
        print_core.remove_printed_level(h, "Upper")
        assert h.printSettings.printedLevels == [g.id]

    def test_set_levels_replaces(self):
        from cli_anything.sweethome3d.core import levels as lvl_core
        h = proj_core.new_home("P")
        g = lvl_core.add_level(h, "Ground")
        u = lvl_core.add_level(h, "Upper")
        print_core.add_printed_level(h, "Ground")
        print_core.set_printed_levels(h, ["Upper"])
        assert h.printSettings.printedLevels == [u.id]

    def test_clear(self):
        h = proj_core.new_home("P")
        print_core.set_print(h, paperWidth=210)
        assert print_core.clear_print(h) is True
        assert h.printSettings is None

    def test_round_trip(self, tmp_path):
        from cli_anything.sweethome3d.core import levels as lvl_core
        h = proj_core.new_home("P")
        lvl_core.add_level(h, "Ground")
        print_core.set_print(h, paperWidth=297, paperHeight=420,
                              paperOrientation="LANDSCAPE",
                              headerFormat="Page $page", planScale=50,
                              furniturePrinted=False)
        print_core.add_printed_level(h, "Ground")
        p = str(tmp_path / "p.sh3d")
        proj_core.save_home(h, p)
        h2 = proj_core.open_home(p)
        assert h2.printSettings is not None
        pr = h2.printSettings
        assert pr.paperWidth == 297
        assert pr.paperHeight == 420
        assert pr.paperOrientation == "LANDSCAPE"
        assert pr.headerFormat == "Page $page"
        assert pr.planScale == 50
        assert pr.furniturePrinted is False
        assert len(pr.printedLevels) == 1


# ──────────────────────────────────────────────────── print: CLI

class TestPrintSettingsCLI:
    def test_set_get_clear(self, tmp_path):
        sh3d = str(tmp_path / "p.sh3d")
        _run(["project", "new", "-o", sh3d])
        _run(["--project", sh3d, "print", "set",
               "--paper-width", "297", "--paper-height", "420",
               "--orientation", "LANDSCAPE",
               "--header-format", "Plan rev $page"])
        r = _run(["--project", sh3d, "--json", "print", "get"])
        pr = json.loads(r.stdout)
        assert pr["paperWidth"] == 297
        assert pr["paperOrientation"] == "LANDSCAPE"
        assert pr["headerFormat"] == "Plan rev $page"
        _run(["--project", sh3d, "print", "clear"])
        r = _run(["--project", sh3d, "print", "get"], check=False)
        assert r.returncode != 0

    def test_level_filter(self, tmp_path):
        sh3d = str(tmp_path / "pl.sh3d")
        _run(["project", "new", "-o", sh3d])
        _run(["--project", sh3d, "level", "add", "Ground"])
        _run(["--project", sh3d, "level", "add", "Upper"])
        _run(["--project", sh3d, "print", "set",
               "--paper-width", "210", "--paper-height", "297"])
        _run(["--project", sh3d, "print", "add-level", "Ground"])
        _run(["--project", sh3d, "print", "add-level", "Upper"])
        r = _run(["--project", sh3d, "--json", "print", "get"])
        pr = json.loads(r.stdout)
        assert len(pr["printedLevels"]) == 2
        _run(["--project", sh3d, "print", "remove-level", "Upper"])
        r = _run(["--project", sh3d, "--json", "print", "get"])
        pr = json.loads(r.stdout)
        assert len(pr["printedLevels"]) == 1


# ──────────────────────────────────────────────────── stored camera kind fix

class TestStoredCameraKindFix:
    """Stored cameras must round-trip with their `kind` preserved.

    Before the fix, the writer always tagged stored cameras as <camera>
    regardless of whether they captured the top or observer view, and the
    reader set `kind="storedCamera"` (which isn't a valid Camera kind).
    """

    def test_observer_view_keeps_observer_kind(self, tmp_path):
        h = proj_core.new_home("CK")
        h.storedCameras.append(Camera(
            kind="observerCamera", name="Kitchen entry",
            x=100, y=200, z=170, yaw=2.1, pitch=-0.1,
        ))
        p = str(tmp_path / "ck.sh3d")
        proj_core.save_home(h, p)
        h2 = proj_core.open_home(p)
        assert h2.storedCameras[0].kind == "observerCamera"

        # Also verify the XML uses <observerCamera>
        with zipfile.ZipFile(p) as z:
            xml = z.read("Home.xml").decode()
        root = ET.fromstring(xml)
        obs_stored = [c for c in root.findall("observerCamera")
                       if c.get("attribute") == "storedCamera"]
        assert len(obs_stored) == 1

    def test_top_view_keeps_top_kind(self, tmp_path):
        h = proj_core.new_home("CK")
        h.storedCameras.append(Camera(
            kind="topCamera", name="Plan overview",
            x=400, y=600, z=1500, yaw=0, pitch=-1.5,
        ))
        p = str(tmp_path / "ck.sh3d")
        proj_core.save_home(h, p)
        h2 = proj_core.open_home(p)
        assert h2.storedCameras[0].kind == "topCamera"

        with zipfile.ZipFile(p) as z:
            xml = z.read("Home.xml").decode()
        root = ET.fromstring(xml)
        cam_stored = [c for c in root.findall("camera")
                       if c.get("attribute") == "storedCamera"]
        assert len(cam_stored) == 1

    def test_cli_save_preserves_kind(self, tmp_path):
        # camera save defaults to --kind observerCamera, so the stored
        # snapshot should come back as observerCamera after a roundtrip.
        sh3d = str(tmp_path / "ckcli.sh3d")
        _run(["project", "new", "-o", sh3d])
        _run(["--project", sh3d, "camera", "set",
               "--kind", "observerCamera",
               "--x", "100", "--y", "100", "--z", "170"])
        _run(["--project", sh3d, "camera", "save", "kitchen"])
        sess = Session.open(sh3d)
        assert sess.home.storedCameras[0].kind == "observerCamera"

        # Now save a top-camera view
        _run(["--project", sh3d, "camera", "save", "overview",
               "--kind", "topCamera"])
        sess = Session.open(sh3d)
        top_view = next(c for c in sess.home.storedCameras
                         if c.name == "overview")
        assert top_view.kind == "topCamera"

    def test_camera_name_with_slashes(self, tmp_path):
        # SH3D auto-names stored cameras with a DD/MM/YY HH:MM:SS timestamp
        # (slashes and spaces). Verify save/list/go/delete all handle them.
        sh3d = str(tmp_path / "slash.sh3d")
        weird_name = "15/05/26 14:21:43"
        _run(["project", "new", "-o", sh3d])
        _run(["--project", sh3d, "camera", "set",
               "--kind", "observerCamera",
               "--x", "200", "--y", "300", "--z", "175"])
        _run(["--project", sh3d, "camera", "save", weird_name])

        r = _run(["--project", sh3d, "--json", "camera", "list"])
        names = [c["name"] for c in json.loads(r.stdout)]
        assert names == [weird_name]

        # Roundtrip preserves the slash-bearing name byte-for-byte
        sess = Session.open(sh3d)
        assert sess.home.storedCameras[0].name == weird_name

        # `camera go` and `camera delete` round-trip the same name
        _run(["--project", sh3d, "camera", "set", "--kind", "observerCamera",
               "--x", "0", "--y", "0", "--z", "0"])
        _run(["--project", sh3d, "camera", "go", weird_name])
        sess = Session.open(sh3d)
        assert sess.home.observerCamera.x == 200

        _run(["--project", sh3d, "camera", "delete", weird_name])
        r = _run(["--project", sh3d, "--json", "camera", "list"])
        assert json.loads(r.stdout) == []


# ──────────────────────────────────────────────────── find walls --unlinked

class TestFindWallsUnlinked:
    """A wall is `unlinked` when neither endpoint connects to another wall
    (no wallAtStart and no wallAtEnd). Useful for surfacing import failures."""

    def test_core_filter(self):
        h = proj_core.new_home("U")
        # Connected rectangle (4 walls all link)
        walls_core.rectangle(h, 0, 0, 500, 400)
        # Plus one free-floating wall
        free = walls_core.add_wall(h, 800, 800, 1000, 800)
        all_walls = find_core.find_walls(h)
        assert len(all_walls) == 5
        unlinked = find_core.find_walls(h, unlinked=True)
        assert len(unlinked) == 1
        assert unlinked[0].id == free.id
        linked = find_core.find_walls(h, unlinked=False)
        assert {w.id for w in linked} == {w.id for w in all_walls if w.id != free.id}

    def test_cli_unlinked_filter(self, tmp_path):
        sh3d = str(tmp_path / "u.sh3d")
        _run(["project", "new", "-o", sh3d])
        _run(["--project", sh3d, "wall", "rectangle", "0", "0", "500", "400"])
        # Single floating wall — won't auto-link to the rectangle's walls
        _run(["--project", sh3d, "wall", "add", "800", "800", "1000", "800"])
        r = _run(["--project", sh3d, "--json", "find", "walls", "--unlinked"])
        walls = json.loads(r.stdout)
        assert len(walls) == 1
        assert walls[0]["xStart"] == 800


# ──────────────────────────────────────────────────── catalog scan + from-project

class TestCatalogScan:
    def test_parse_properties_basic(self):
        text = """
# header comment ignored
id=PluginCatalog
name=Test plugin

id#1=acme#chairThing
name#1=Acme chair
category#1=Lounge
width#1=45
depth#1=50
height#1=90
creator#1=Acme
tags#1=Office, Adjustable

id#2=acme#sliderDoor
name#2=Slider
doorOrWindow#2=true
width#2=200
depth#2=6
height#2=210

id#3=acme#deskLamp
name#3=Desk lamp
light#3=true
width#3=15
depth#3=15
height#3=40
"""
        entries = catalog_scan_core.parse_catalog_properties(text)
        assert len(entries) == 3
        by_id = {e.catalogId: e for e in entries}
        assert by_id["acme#chairThing"].kind == "pieceOfFurniture"
        assert by_id["acme#chairThing"].tags == ["Office", "Adjustable"]
        assert by_id["acme#sliderDoor"].kind == "doorOrWindow"
        assert by_id["acme#deskLamp"].kind == "light"

    def test_parse_skips_comment_lines(self):
        # `#` at column 0 (no embedded index) is a comment
        text = "# Real comment\nid#1=x\nname#1=X\n"
        entries = catalog_scan_core.parse_catalog_properties(text)
        assert [e.catalogId for e in entries] == ["x"]

    def test_from_project_dedupes(self):
        h = proj_core.new_home("P")
        furn_core.add_piece(h, "Sofa", 0, 0,
                              width=200, depth=90, height=80,
                              catalogId="eTeks#sofa")
        furn_core.add_piece(h, "Sofa2", 300, 0,
                              width=200, depth=90, height=80,
                              catalogId="eTeks#sofa")  # duplicate id
        furn_core.add_piece(h, "Chair", 0, 200,
                              width=45, depth=50, height=90,
                              catalogId="eTeks#chair")
        entries = catalog_scan_core.from_project(h)
        ids = sorted(e.catalogId for e in entries)
        assert ids == ["eTeks#chair", "eTeks#sofa"]
        assert all(e.source == "project" for e in entries)

    def test_from_project_walks_groups(self):
        h = proj_core.new_home("P")
        furn_core.add_piece(h, "Sofa", 0, 0,
                              width=200, depth=90, height=80,
                              catalogId="eTeks#sofa")
        furn_core.add_piece(h, "Chair", 300, 0,
                              width=45, depth=50, height=90,
                              catalogId="eTeks#chair")
        from cli_anything.sweethome3d.core import furniture_groups as group_core
        group_core.create_group(h, "Set", piece_idents=["Sofa", "Chair"])
        # Both Sofa and Chair now live inside the group, not top-level
        assert h.furniture == []
        entries = catalog_scan_core.from_project(h)
        ids = sorted(e.catalogId for e in entries)
        assert ids == ["eTeks#chair", "eTeks#sofa"]

    def test_cli_from_project(self, tmp_path):
        sh3d = str(tmp_path / "cf.sh3d")
        _run(["project", "new", "-o", sh3d])
        _run(["--project", sh3d, "furniture", "add", "Sofa",
               "0", "0", "--width", "200", "--depth", "90", "--height", "80",
               "--catalog-id", "eTeks#sofa"])
        _run(["--project", sh3d, "furniture", "add-door", "Door", "100", "0"])
        r = _run(["--project", sh3d, "--json", "catalog", "from-project"])
        entries = json.loads(r.stdout)
        ids = sorted(e["catalogId"] for e in entries)
        assert "eTeks#sofa" in ids
        assert "eTeks#doorFrame" in ids   # default door catalog id

    def test_cli_from_project_kind_filter(self, tmp_path):
        sh3d = str(tmp_path / "cfk.sh3d")
        _run(["project", "new", "-o", sh3d])
        _run(["--project", sh3d, "furniture", "add", "Sofa",
               "0", "0", "--width", "200", "--depth", "90", "--height", "80",
               "--catalog-id", "eTeks#sofa"])
        _run(["--project", sh3d, "furniture", "add-door", "Door", "100", "0"])
        r = _run(["--project", sh3d, "--json", "catalog", "from-project",
                   "--kind", "doorOrWindow"])
        entries = json.loads(r.stdout)
        assert all(e["kind"] == "doorOrWindow" for e in entries)
        assert {e["catalogId"] for e in entries} == {"eTeks#doorFrame"}


# ──────────────────────────────────────────────────── project validate

class TestValidateCore:
    def test_clean_project_is_clean(self):
        h = proj_core.new_home("V")
        walls_core.rectangle(h, 0, 0, 500, 400)
        rooms_core.add_rectangle_room(h, 5, 5, 490, 390, name="Room")
        report = validate_core.validate(h, include_info=False)
        assert report.ok
        assert report.errors == []
        assert report.warnings == []

    def test_unlinked_walls_are_info(self):
        h = proj_core.new_home("V")
        walls_core.add_wall(h, 0, 0, 500, 0)   # free-floating
        report = validate_core.validate(h)
        codes = report.by_code()
        assert codes.get("wall.unlinked", 0) == 1

    def test_tiny_room_warning(self):
        h = proj_core.new_home("V")
        # 10cm × 10cm = 100 cm² = 0.01 m²
        rooms_core.add_rectangle_room(h, 0, 0, 10, 10, name="speck")
        report = validate_core.validate(h)
        codes = report.by_code()
        assert codes.get("room.tiny", 0) == 1

    def test_degenerate_room_is_error(self):
        h = proj_core.new_home("V")
        # Bypass add_room's validation by constructing directly
        from cli_anything.sweethome3d.core.model import Point, Room
        h.rooms.append(Room(points=[Point(0, 0), Point(10, 0)], name="line"))
        report = validate_core.validate(h)
        assert any(f.code == "room.degenerate" for f in report.errors)
        assert not report.ok

    def test_unknown_catalog_warning(self):
        h = proj_core.new_home("V")
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            furn_core.add_piece(h, "Mystery", 0, 0,
                                  width=50, depth=50, height=50,
                                  catalogId="madeup#widget")
        report = validate_core.validate(h)
        assert any(f.code == "furniture.unknown_catalog"
                    for f in report.warnings)

    def test_light_no_power_warning(self):
        h = proj_core.new_home("V")
        furn_core.add_light(h, "Dark", 0, 0, power=0)  # explicitly zero
        report = validate_core.validate(h)
        assert any(f.code == "light.no_power" for f in report.warnings)

    def test_dangling_level_error(self):
        h = proj_core.new_home("V")
        lvl_core.add_level(h, "Ground")
        w = walls_core.add_wall(h, 0, 0, 100, 0)
        w.level = "ghost-level-id"
        report = validate_core.validate(h)
        assert any(f.code == "wall.dangling_level" for f in report.errors)

    def test_real_example_validates_clean(self):
        """The bundled example .sh3d should validate clean (errors=0, warnings=0)."""
        ex_path = os.path.join(os.path.dirname(__file__),
                                 "..", "..", "..", "examples",
                                 "Home-Clean-Base-RAL.sh3d")
        ex_path = os.path.abspath(ex_path)
        if not os.path.isfile(ex_path):
            pytest.skip("example file not present")
        h = proj_core.open_home(ex_path)
        report = validate_core.validate(h, include_info=False)
        assert report.ok, f"unexpected findings: {report.findings}"


class TestValidateCLI:
    def test_clean_human_output(self, tmp_path):
        sh3d = str(tmp_path / "v.sh3d")
        _run(["project", "new", "-o", sh3d])
        _run(["--project", sh3d, "wall", "rectangle", "0", "0", "500", "400"])
        r = _run(["--project", sh3d, "project", "validate", "--no-info"])
        assert "✓" in r.stdout
        assert "clean" in r.stdout

    def test_json_summary(self, tmp_path):
        sh3d = str(tmp_path / "vj.sh3d")
        _run(["project", "new", "-o", sh3d])
        _run(["--project", sh3d, "wall", "add", "0", "0", "500", "0"])
        r = _run(["--project", sh3d, "--json", "project", "validate"])
        report = json.loads(r.stdout)
        assert report["ok"] is True
        assert report["summary"]["infos"] >= 1

    def test_exit_code_on_error(self, tmp_path):
        sh3d = str(tmp_path / "ve.sh3d")
        _run(["project", "new", "-o", sh3d])
        # Inject a degenerate room directly via Session to bypass CLI guards
        sess = Session.open(sh3d)
        from cli_anything.sweethome3d.core.model import Point, Room
        sess.home.rooms.append(Room(points=[Point(0, 0)], name="bad"))
        sess.save()
        r = _run(["--project", sh3d, "project", "validate"], check=False)
        assert r.returncode != 0


# ──────────────────────────────────────────────────── measurement helpers

class TestProjectBounds:
    def test_bounds_calculation(self, tmp_path):
        sh3d = str(tmp_path / "b.sh3d")
        _run(["project", "new", "-o", sh3d])
        _run(["--project", sh3d, "wall", "add", "0", "0", "500", "0"])
        _run(["--project", sh3d, "wall", "add", "500", "0", "500", "400"])
        r = _run(["--project", sh3d, "--json", "project", "bounds"])
        b = json.loads(r.stdout)
        assert b["width_cm"] == 500
        assert b["depth_cm"] == 400
        assert b["width_m"] == 5.0
        assert b["depth_m"] == 4.0


class TestRoomAreaAndInfo:
    def test_area_cli_m2(self, tmp_path):
        sh3d = str(tmp_path / "a.sh3d")
        _run(["project", "new", "-o", sh3d])
        _run(["--project", sh3d, "room", "rectangle",
               "0", "0", "500", "400", "--name", "R"])
        r = _run(["--project", sh3d, "--json", "room", "area", "R"])
        out = json.loads(r.stdout)
        assert out["area"] == pytest.approx(20.0)  # 5m × 4m = 20 m²
        assert out["units"] == "m2"

    def test_area_cli_ft2(self, tmp_path):
        sh3d = str(tmp_path / "af.sh3d")
        _run(["project", "new", "-o", sh3d])
        _run(["--project", sh3d, "room", "rectangle",
               "0", "0", "500", "400", "--name", "R"])
        r = _run(["--project", sh3d, "--json", "room", "area", "R", "--units", "ft2"])
        out = json.loads(r.stdout)
        # 20 m² ≈ 215.28 ft²
        assert out["area"] == pytest.approx(215.28, abs=0.5)

    def test_info_aggregates(self, tmp_path):
        sh3d = str(tmp_path / "i.sh3d")
        _run(["project", "new", "-o", sh3d])
        _run(["--project", sh3d, "wall", "rectangle", "0", "0", "500", "400"])
        _run(["--project", sh3d, "room", "rectangle",
               "0", "0", "500", "400", "--name", "R"])
        _run(["--project", sh3d, "furniture", "add", "Sofa",
               "250", "200", "--width", "100", "--depth", "50", "--height", "80"])
        r = _run(["--project", sh3d, "--json", "room", "info", "R"])
        info = json.loads(r.stdout)
        assert info["area_m2"] == pytest.approx(20.0)
        assert info["perimeter_m"] == pytest.approx(18.0)
        assert info["furniture_inside"] == 1
        assert info["bounding_walls"] == 4


class TestWallLengthAndInfo:
    def test_length_units(self, tmp_path):
        sh3d = str(tmp_path / "wl.sh3d")
        _run(["project", "new", "-o", sh3d])
        r = _run(["--project", sh3d, "--json", "wall", "add",
                   "0", "0", "300", "400"])  # 3-4-5 triangle: length 500
        wid = json.loads(r.stdout)["id"]
        r = _run(["--project", sh3d, "--json", "wall", "length", wid])
        assert json.loads(r.stdout)["length"] == pytest.approx(500.0)
        r = _run(["--project", sh3d, "--json", "wall", "length", wid, "--units", "m"])
        assert json.loads(r.stdout)["length"] == pytest.approx(5.0)

    def test_info_angle(self, tmp_path):
        sh3d = str(tmp_path / "wi.sh3d")
        _run(["project", "new", "-o", sh3d])
        r = _run(["--project", sh3d, "--json", "wall", "add",
                   "0", "0", "100", "100"])
        wid = json.loads(r.stdout)["id"]
        r = _run(["--project", sh3d, "--json", "wall", "info", wid])
        info = json.loads(r.stdout)
        assert info["angle_deg"] == pytest.approx(45.0)
        assert info["midpoint"]["x"] == pytest.approx(50)
        assert info["linked"]["is_unlinked"] is True


class TestFurnitureInfo:
    def test_info_includes_materials(self, tmp_path):
        sh3d = str(tmp_path / "fi.sh3d")
        _run(["project", "new", "-o", sh3d])
        _run(["--project", sh3d, "furniture", "add", "Sofa",
               "0", "0", "--width", "200", "--depth", "90", "--height", "80",
               "--catalog-id", "eTeks#sofa"])
        _run(["--project", sh3d, "material", "set", "Sofa", "Cushion",
               "--color", "#AABBCC"])
        r = _run(["--project", sh3d, "--json", "furniture", "info", "Sofa"])
        info = json.loads(r.stdout)
        assert info["name"] == "Sofa"
        assert len(info["materials"]) == 1
        assert info["materials"][0]["name"] == "Cushion"


class TestFindRoomsExtensions:
    def test_unnamed_filter(self, tmp_path):
        sh3d = str(tmp_path / "fr.sh3d")
        _run(["project", "new", "-o", sh3d])
        _run(["--project", sh3d, "room", "rectangle",
               "0", "0", "500", "400", "--name", "Named"])
        _run(["--project", sh3d, "room", "rectangle", "600", "0", "200", "200"])
        r = _run(["--project", sh3d, "--json", "find", "rooms", "--unnamed"])
        rooms = json.loads(r.stdout)
        assert len(rooms) == 1
        assert rooms[0]["name"] is None

    def test_area_range_filter(self, tmp_path):
        sh3d = str(tmp_path / "ar.sh3d")
        _run(["project", "new", "-o", sh3d])
        _run(["--project", sh3d, "room", "rectangle",
               "0", "0", "100", "100", "--name", "Tiny"])     # 1 m²
        _run(["--project", sh3d, "room", "rectangle",
               "0", "200", "500", "400", "--name", "Big"])    # 20 m²
        r = _run(["--project", sh3d, "--json", "find", "rooms",
                   "--area-max", "5"])
        rooms = json.loads(r.stdout)
        assert [r["name"] for r in rooms] == ["Tiny"]
        r = _run(["--project", sh3d, "--json", "find", "rooms",
                   "--area-min", "10"])
        rooms = json.loads(r.stdout)
        assert [r["name"] for r in rooms] == ["Big"]


# ──────────────────────────────────────────────────── camera time

class TestCameraTime:
    def test_natural_date_converts_to_millis(self, tmp_path):
        sh3d = str(tmp_path / "ct.sh3d")
        _run(["project", "new", "-o", sh3d])
        r = _run(["--project", sh3d, "--json", "camera", "time",
                   "--year", "2024", "--month", "7", "--day", "21",
                   "--hour", "14", "--utc"])
        out = json.loads(r.stdout)
        # 2024-07-21 14:00 UTC → 1721570400000 ms
        assert out["time_ms"] == 1721570400000
        assert "2024-07-21T14:00:00+00:00" in out["iso"]

        # And the camera now carries that time
        sess = Session.open(sh3d)
        assert sess.home.observerCamera.time == 1721570400000

    def test_topcamera_kind(self, tmp_path):
        sh3d = str(tmp_path / "ctt.sh3d")
        _run(["project", "new", "-o", sh3d])
        _run(["--project", sh3d, "camera", "time", "--kind", "topCamera",
               "--year", "2024", "--month", "12", "--day", "21",
               "--hour", "8", "--utc"])
        sess = Session.open(sh3d)
        assert sess.home.topCamera.time is not None
        assert sess.home.observerCamera.time is None

    def test_rejects_invalid_date(self, tmp_path):
        sh3d = str(tmp_path / "ctb.sh3d")
        _run(["project", "new", "-o", sh3d])
        r = _run(["--project", sh3d, "camera", "time",
                   "--month", "13", "--day", "1", "--hour", "12"],
                  check=False)
        assert r.returncode != 0


# ──────────────────────────────────────────────────── level duplicate

class TestLevelDuplicateCore:
    def test_walls_duplicate_with_links(self):
        h = proj_core.new_home("L")
        src = lvl_core.add_level(h, "Ground")
        walls_created = walls_core.rectangle(h, 0, 0, 500, 400, level=src.id)
        # Confirm 4 walls all linked
        assert all(w.wallAtStart and w.wallAtEnd for w in walls_created)
        new_lvl = lvl_core.duplicate_level(h, "Ground", new_name="Upper")
        on_upper = [w for w in h.walls if w.level == new_lvl.id]
        assert len(on_upper) == 4
        # All neighbour links should point to OTHER walls on Upper (not Ground)
        upper_ids = {w.id for w in on_upper}
        for w in on_upper:
            if w.wallAtStart:
                assert w.wallAtStart in upper_ids
            if w.wallAtEnd:
                assert w.wallAtEnd in upper_ids

    def test_elevation_defaults_to_stacking(self):
        h = proj_core.new_home("L")
        src = lvl_core.add_level(h, "Ground")  # elevation=0, height=250, floor=12
        new_lvl = lvl_core.duplicate_level(h, "Ground", new_name="Upper")
        assert new_lvl.elevation == pytest.approx(262)  # 0 + 250 + 12

    def test_offset_translates_geometry(self):
        h = proj_core.new_home("L")
        src = lvl_core.add_level(h, "Ground")
        walls_core.add_wall(h, 0, 0, 100, 0, level=src.id)
        new_lvl = lvl_core.duplicate_level(h, "Ground",
                                              new_name="Annexe",
                                              offset_x=1000, offset_y=500)
        upper_walls = [w for w in h.walls if w.level == new_lvl.id]
        assert upper_walls[0].xStart == 1000
        assert upper_walls[0].yStart == 500

    def test_skip_furniture_flag(self):
        h = proj_core.new_home("L")
        src = lvl_core.add_level(h, "Ground")
        furn_core.add_piece(h, "Sofa", 100, 100,
                              width=200, depth=90, height=80,
                              level=src.id)
        new_lvl = lvl_core.duplicate_level(h, "Ground", new_name="Upper",
                                              include_furniture=False)
        upper_furn = [f for f in h.furniture if f.level == new_lvl.id]
        assert upper_furn == []

    def test_rejects_duplicate_name(self):
        h = proj_core.new_home("L")
        lvl_core.add_level(h, "Ground")
        with pytest.raises(ValueError):
            lvl_core.duplicate_level(h, "Ground", new_name="Ground")

    def test_rejects_unknown_source(self):
        h = proj_core.new_home("L")
        with pytest.raises(KeyError):
            lvl_core.duplicate_level(h, "Phantom", new_name="X")


class TestLevelDuplicateCLI:
    def test_duplicate_cli(self, tmp_path):
        sh3d = str(tmp_path / "ld.sh3d")
        _run(["project", "new", "-o", sh3d])
        _run(["--project", sh3d, "level", "add", "Ground"])
        _run(["--project", sh3d, "wall", "rectangle",
               "0", "0", "500", "400", "--level", "Ground"])
        r = _run(["--project", sh3d, "--json", "level", "duplicate",
                   "Ground", "--name", "Upper"])
        new_lvl = json.loads(r.stdout)
        assert new_lvl["name"] == "Upper"

        # Find walls on Upper
        r = _run(["--project", sh3d, "--json", "find", "walls",
                   "--level", "Upper"])
        upper = json.loads(r.stdout)
        assert len(upper) == 4

    def test_duplicate_with_explicit_elevation(self, tmp_path):
        sh3d = str(tmp_path / "lde.sh3d")
        _run(["project", "new", "-o", sh3d])
        _run(["--project", sh3d, "level", "add", "Ground"])
        _run(["--project", sh3d, "wall", "add", "0", "0", "100", "0",
               "--level", "Ground"])
        r = _run(["--project", sh3d, "--json", "level", "duplicate",
                   "Ground", "--name", "Basement", "--elevation", "-250"])
        assert json.loads(r.stdout)["elevation"] == -250


# ──────────────────────────────────────────────────── multi-domain workflow

class TestRefine2Workflow:
    """End-to-end: build a fully-decorated room with all v2 surfaces."""

    def test_full_decorated_room(self, tmp_path):
        sh3d = str(tmp_path / "decorated.sh3d")
        png_path = str(tmp_path / "plan.png")
        with open(png_path, "wb") as f:
            f.write(_png_bytes(32, 32))

        # Project + a level + a room
        _run(["project", "new", "-n", "Studio", "-o", sh3d])
        _run(["--project", sh3d, "level", "add", "Ground"])
        _run(["--project", sh3d, "wall", "rectangle",
               "0", "0", "500", "400", "--level", "Ground"])
        _run(["--project", sh3d, "room", "rectangle",
               "5", "5", "490", "390", "--name", "Lounge",
               "--level", "Ground"])

        # Background image, calibrated
        _run(["--project", sh3d, "background", "set", png_path,
               "--scale-distance", "500",
               "--x-start", "0", "--y-start", "0",
               "--x-end", "32", "--y-end", "0"])

        # Print settings
        _run(["--project", sh3d, "print", "set",
               "--paper-width", "297", "--paper-height", "420",
               "--orientation", "LANDSCAPE", "--plan-scale", "100"])
        _run(["--project", sh3d, "print", "add-level", "Ground"])

        # Furniture: sofa + chair → group, with material overrides
        _run(["--project", sh3d, "furniture", "add", "Sofa",
               "100", "200", "--width", "200", "--depth", "90", "--height", "80"])
        _run(["--project", sh3d, "furniture", "add", "Chair",
               "350", "200", "--width", "60", "--depth", "60", "--height", "90"])
        _run(["--project", sh3d, "group", "create", "SeatingSet",
               "--pieces", "Sofa,Chair"])
        _run(["--project", sh3d, "material", "set", "Sofa", "Cushion",
               "--color", "#AABBCC", "--shininess", "0.4"])

        # Door with sash
        _run(["--project", sh3d, "furniture", "add-door", "EntryDoor",
               "250", "5", "--width", "80"])
        _run(["--project", sh3d, "sash", "add", "EntryDoor",
               "--x-axis", "0", "--y-axis", "0", "--width", "0.95",
               "--start-angle", "0", "--end-angle", "1.5707"])

        # Light with emitter source
        _run(["--project", sh3d, "furniture", "add-light", "Ceiling",
               "250", "200", "--elevation", "240"])
        _run(["--project", sh3d, "emitter", "source", "add", "Ceiling",
               "--x", "0", "--y", "0", "--z", "0.5",
               "--color", "#FFFFCC", "--diameter", "3.0"])

        # Confirm everything survived round-trip
        sess = Session.open(sh3d)
        h = sess.home
        assert h.backgroundImage is not None
        assert h.backgroundImage.scaleDistance == 500
        assert h.printSettings is not None
        assert h.printSettings.paperOrientation == "LANDSCAPE"
        assert len(h.furnitureGroups) == 1
        assert h.furnitureGroups[0].name == "SeatingSet"
        assert len(h.furnitureGroups[0].furniture) == 2
        sofa_in_group = next(p for p in h.furnitureGroups[0].furniture
                               if isinstance(p, PieceOfFurniture)
                               and p.name == "Sofa")
        assert len(sofa_in_group.materials) == 1
        assert sofa_in_group.materials[0].color == 0xFFAABBCC
        door = h.find_furniture("EntryDoor")
        assert len(door.sashes) == 1
        assert door.sashes[0].width == pytest.approx(0.95)
        lamp = h.find_furniture("Ceiling")
        assert len(lamp.lightSources) == 1
        assert lamp.lightSources[0].diameter == pytest.approx(3.0)

        # PNG embedded
        with zipfile.ZipFile(sh3d) as z:
            assert h.backgroundImage.image in z.namelist()
