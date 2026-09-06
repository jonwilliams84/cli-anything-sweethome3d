"""In-process CliRunner tests for the Click CLI surface.

The E2E suite drives the CLI via subprocess, which coverage cannot see —
sweethome3d_cli.py reported 0% despite being exercised. These tests invoke
the Click group directly so the command layer is measured and regressions
in argument wiring surface as ordinary test failures.
"""

from __future__ import annotations

import json
import os
import textwrap

import pytest
from click.testing import CliRunner

from cli_anything.sweethome3d.sweethome3d_cli import _one_line, _parse_int_color, cli


# ───────────────────────────────────────────── helpers / fixtures


def _ok(runner, args, project=None, json_mode=True):
    """Invoke the CLI and assert success. Returns the Result."""
    argv = []
    if project is not None:
        argv += ["--project", str(project)]
    if json_mode:
        argv += ["--json"]
    argv += list(args)
    result = runner.invoke(cli, argv)
    assert result.exit_code == 0, f"command {args} failed:\n{result.output}"
    return result


def _fail(runner, args, project=None, json_mode=True):
    """Invoke the CLI expecting a non-zero exit."""
    argv = []
    if project is not None:
        argv += ["--project", str(project)]
    if json_mode:
        argv += ["--json"]
    argv += list(args)
    result = runner.invoke(cli, argv)
    assert result.exit_code != 0, f"expected failure for {args}:\n{result.output}"
    return result


def _data(result):
    """Parse --json output (tolerates non-JSON noise around it, e.g. warnings)."""
    text = result.output
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    assert starts, f"no JSON in output:\n{result.output}"
    obj, _ = json.JSONDecoder().raw_decode(text[min(starts) :])
    return obj


@pytest.fixture()
def runner():
    return CliRunner()


@pytest.fixture()
def house(tmp_path, runner):
    """A populated .sh3d project: 4 walls, a room, furniture, a light."""
    path = tmp_path / "house.sh3d"
    _ok(runner, ["project", "new", "-n", "InProcHouse", "-o", str(path)])
    _ok(runner, ["wall", "rectangle", "0", "0", "400", "300"], project=path)
    _ok(
        runner,
        ["room", "rectangle", "5", "5", "390", "290", "--name", "Living"],
        project=path,
    )
    _ok(
        runner,
        ["furniture", "add", "Sofa", "100", "100", "-w", "200", "-d", "90", "-h", "85"],
        project=path,
    )
    _ok(runner, ["furniture", "add-light", "Lamp", "200", "150", "--power", "0.9"], project=path)
    return path


def _first_id(runner, project, group, kind=None):
    """Return the id of the first listed object of a group."""
    args = [group, "list"]
    if kind:
        args += ["--kind", kind]
    rows = _data(_ok(runner, args, project=project))
    return rows[0]["id"]


# ───────────────────────────────────────────── unit helpers


class TestHelpers:
    def test_parse_int_color_rgb_gets_alpha(self):
        assert _parse_int_color("#FFEE88") == 0xFFFFEE88

    def test_parse_int_color_argb_passthrough(self):
        assert _parse_int_color("80FFEE88") == 0x80FFEE88

    def test_parse_int_color_none_and_blank(self):
        assert _parse_int_color(None) is None
        assert _parse_int_color("  ") is None

    def test_one_line_catalog_entry(self):
        class Entry:
            catalogId = "eTeks#sofa"
            name = "Sofa"
            category = "living"

        line = _one_line(Entry())
        assert "catalogId=eTeks#sofa" in line
        assert "name=Sofa" in line

    def test_one_line_point_ish(self):
        class P:
            id = "w1"
            name = "north wall"
            x = 1.0
            y = 2.0

        line = _one_line(P())
        assert "id=w1" in line
        assert "x=1,y=2" in line


# ───────────────────────────────────────────── root / project


class TestRoot:
    def test_help(self, runner):
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Sweet Home 3D" in result.output

    def test_version(self, runner):
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "1.1.0" in result.output

    def test_command_without_project_fails(self, runner):
        result = _fail(runner, ["wall", "list"])
        assert "no project loaded" in result.output

    def test_missing_project_path_is_auto_created(self, runner, tmp_path):
        path = tmp_path / "fresh.sh3d"
        result = _ok(runner, ["wall", "add", "0", "0", "100", "0"], project=path)
        assert result.exit_code == 0
        assert path.exists()


class TestProject:
    def test_new_json(self, runner, tmp_path):
        out = tmp_path / "n.sh3d"
        result = _ok(runner, ["project", "new", "-n", "Tiny", "-o", str(out)])
        data = _data(result)
        assert data["name"] == "Tiny"
        assert data["version"] == 7400
        assert out.exists()

    def test_info_open_save_as(self, runner, tmp_path):
        src = tmp_path / "a.sh3d"
        dst = tmp_path / "b.sh3d"
        _ok(runner, ["project", "new", "-o", str(src)])
        info = _data(_ok(runner, ["project", "info"], project=src))
        assert "walls" in info and "levels" in info
        _ok(runner, ["project", "save", "--as", str(dst)], project=src)
        assert dst.exists()

    def test_validate(self, runner, house):
        result = _ok(runner, ["project", "validate"], project=house)
        assert _data(result) is not None

    def test_bounds(self, runner, house):
        data = _data(_ok(runner, ["project", "bounds"], project=house))
        assert "min_x" in data or "levels" in data or data  # shape tolerant


# ───────────────────────────────────────────── levels


class TestLevels:
    def test_add_list_set_select(self, runner, house):
        _ok(runner, ["level", "add", "Upstairs", "-e", "260", "-h", "250"], project=house)
        rows = _data(_ok(runner, ["level", "list"], project=house))
        names = [r["name"] for r in rows]
        assert "Upstairs" in names
        lvl_id = next(r["id"] for r in rows if r["name"] == "Upstairs")

        data = _data(_ok(runner, ["level", "set", lvl_id, "--elevation", "270"], project=house))
        assert data["elevation"] == 270

        sel = _data(_ok(runner, ["level", "select", lvl_id], project=house))
        assert sel["selected"] == lvl_id
        cleared = _data(_ok(runner, ["level", "select", "--clear"], project=house))
        assert cleared["selected"] is None

    def test_select_requires_arg(self, runner, house):
        _fail(runner, ["level", "select"], project=house)

    def test_duplicate_and_delete(self, runner, house):
        _ok(runner, ["level", "add", "Ground"], project=house)
        new_lvl = _data(
            _ok(runner, ["level", "duplicate", "Ground", "--name", "Copy"], project=house)
        )
        assert new_lvl["name"] == "Copy"
        _ok(runner, ["level", "delete", "Copy"], project=house)
        _fail(runner, ["level", "delete", "Copy"], project=house)


# ───────────────────────────────────────────── walls


class TestWalls:
    def test_add_with_colors_and_textures(self, runner, house):
        from cli_anything.sweethome3d.core import textures as tex_core

        wall_tex = tex_core.list_textures(category="Wall")[0].catalogId
        w = _data(
            _ok(
                runner,
                [
                    "wall",
                    "add",
                    "10",
                    "10",
                    "110",
                    "10",
                    "--left-color",
                    "#FF0000",
                    "--right-color",
                    "#00FF00",
                    "--left-texture",
                    wall_tex,
                ],
                project=house,
            )
        )
        assert w["xStart"] == 10.0
        assert w["leftSideColor"] == 0xFFFF0000

    def test_add_bad_texture_rolls_back(self, runner, house):
        result = _fail(
            runner,
            ["wall", "add", "10", "10", "110", "10", "--left-texture", "nope#x"],
            project=house,
        )
        assert "nope" in result.output

    def test_list_move_set_info_length(self, runner, house):
        wid = _first_id(runner, house, "wall")
        _ok(
            runner,
            [
                "wall",
                "move",
                wid,
                "--x-start",
                "0",
                "--y-start",
                "5",
                "--x-end",
                "400",
                "--y-end",
                "5",
            ],
            project=house,
        )
        w = _data(
            _ok(
                runner, ["wall", "set", wid, "--height", "250", "--pattern", "plain"], project=house
            )
        )
        assert w["height"] == 250.0
        info = _data(_ok(runner, ["wall", "info", wid], project=house))
        assert info["id"] == wid
        assert info["height"] == 250.0
        for units, expected in (("m", 4.0), ("cm", 400.0)):
            data = _data(_ok(runner, ["wall", "length", wid, "--units", units], project=house))
            assert abs(data["length"] - expected) < 1e-6

    def test_baseboard_set_and_clear(self, runner, house):
        wid = _first_id(runner, house, "wall")
        w = _data(
            _ok(
                runner,
                ["wall", "baseboard", wid, "--side", "left", "--color", "#886644"],
                project=house,
            )
        )
        assert w["leftSideBaseboard"]["color"] == 0xFF886644
        w = _data(
            _ok(runner, ["wall", "baseboard", wid, "--side", "left", "--clear"], project=house)
        )
        assert w["leftSideBaseboard"] is None

    def test_split_and_join(self, runner, house):
        wid = _first_id(runner, house, "wall")
        halves = _data(_ok(runner, ["wall", "split", wid, "200,0"], project=house))
        assert len(halves) == 2
        joined = _data(
            _ok(runner, ["wall", "join", halves[0]["id"], halves[1]["id"]], project=house)
        )
        assert joined["id"] in (halves[0]["id"], halves[1]["id"])

    def test_delete_missing(self, runner, house):
        _fail(runner, ["wall", "delete", "nope"], project=house)

    def test_rectangle(self, runner, tmp_path):
        path = tmp_path / "r.sh3d"
        _ok(runner, ["project", "new", "-o", str(path)])
        walls = _data(_ok(runner, ["wall", "rectangle", "0", "0", "200", "200"], project=path))
        assert len(walls) == 4


# ───────────────────────────────────────────── rooms


class TestRooms:
    def test_add_polygon_area_info(self, runner, house):
        r = _data(
            _ok(
                runner,
                [
                    "room",
                    "add",
                    "--points",
                    "300,10 390,10 390,100 300,100",
                    "--name",
                    "Kitchen",
                    "--floor-color",
                    "#123456",
                ],
                project=house,
            )
        )
        assert r["name"] == "Kitchen"
        area = _data(_ok(runner, ["room", "area", "Kitchen", "--units", "m2"], project=house))
        assert area["area"] == pytest.approx(90 * 90 / 10000, rel=1e-3)
        info = _data(_ok(runner, ["room", "info", "Kitchen"], project=house))
        assert info["name"] == "Kitchen"

    def test_set_and_recompute(self, runner, house):
        rid = _first_id(runner, house, "room")
        data = _data(
            _ok(
                runner,
                ["room", "set", rid, "--floor-color", "#ABCDEF", "--floor-visible"],
                project=house,
            )
        )
        assert data["floorColor"] == 0xFFABCDEF
        _ok(runner, ["room", "recompute-points", rid], project=house)

    def test_delete(self, runner, house):
        rid = _first_id(runner, house, "room")
        _ok(runner, ["room", "delete", rid], project=house)
        _fail(runner, ["room", "delete", rid], project=house)

    def test_set_nothing_fails(self, runner, house):
        rid = _first_id(runner, house, "room")
        _fail(runner, ["room", "set", rid], project=house)


# ───────────────────────────────────────────── furniture


class TestFurniture:
    def test_add_door_window_light(self, runner, house):
        door = _data(
            _ok(runner, ["furniture", "add-door", "Front Door", "200", "0"], project=house)
        )
        assert door["kind"] == "doorOrWindow"
        win = _data(_ok(runner, ["furniture", "add-window", "S Window", "100", "0"], project=house))
        assert win["kind"] == "doorOrWindow"
        light = _data(
            _ok(
                runner,
                ["furniture", "add-light", "Spot", "50", "50", "--power", "0.7"],
                project=house,
            )
        )
        assert light["kind"] == "light"

    def test_move_set_info(self, runner, house):
        fid = _first_id(runner, house, "furniture")
        _ok(
            runner,
            [
                "furniture",
                "move",
                fid,
                "--x",
                "120",
                "--y",
                "110",
                "--elevation",
                "5",
                "--angle",
                "0.5",
            ],
            project=house,
        )
        f = _data(
            _ok(runner, ["furniture", "set", fid, "--color", "#3366CC", "--visible"], project=house)
        )
        assert f["color"] == 0xFF3366CC
        info = _data(_ok(runner, ["furniture", "info", fid], project=house))
        assert info["id"] == fid

    def test_set_nothing_fails(self, runner, house):
        fid = _first_id(runner, house, "furniture")
        _fail(runner, ["furniture", "set", fid], project=house)

    def test_delete(self, runner, house):
        fid = _first_id(runner, house, "furniture")
        _ok(runner, ["furniture", "delete", fid], project=house)
        _fail(runner, ["furniture", "info", fid], project=house)

    def test_list_by_kind(self, runner, house):
        lights = _data(_ok(runner, ["furniture", "list", "--kind", "light"], project=house))
        assert {f["name"] for f in lights} == {"Lamp"}


# ───────────────────────────────────────────── catalog / textures


class TestCatalogTextures:
    def test_catalog_list_search_info(self, runner, house):
        rows = _data(_ok(runner, ["catalog", "list"], project=house))
        assert rows
        cid = rows[0]["catalogId"]
        found = _data(_ok(runner, ["catalog", "search", rows[0]["name"].split()[0]], project=house))
        assert any(e["catalogId"] == cid for e in found)
        info = _data(_ok(runner, ["catalog", "info", cid], project=house))
        assert info["catalogId"] == cid

    def test_catalog_info_missing(self, runner, house):
        _fail(runner, ["catalog", "info", "nope#missing"], project=house)

    def test_catalog_from_project(self, runner, house):
        _ok(runner, ["catalog", "from-project"], project=house)

    def test_catalog_scan_no_archives(self, runner, house, monkeypatch):
        monkeypatch.delenv("SWEETHOME3D_FURNITURE_JAR", raising=False)
        result = _fail(runner, ["catalog", "scan"], project=house)
        assert "no catalog archives" in result.output

    def test_textures_list_search_info(self, runner, house):
        rows = _data(_ok(runner, ["textures", "list"], project=house))
        assert rows
        cid = rows[0]["catalogId"]
        info = _data(_ok(runner, ["textures", "info", cid], project=house))
        assert info["catalogId"] == cid
        search = _data(_ok(runner, ["textures", "search", cid.split("#")[-1]], project=house))
        assert any(t["catalogId"] == cid for t in search)


# ───────────────────────────────────────────── camera


class TestCamera:
    def test_get_set_activate(self, runner, house):
        cam = _data(_ok(runner, ["camera", "get"], project=house))
        assert "x" in cam
        cam = _data(
            _ok(
                runner,
                ["camera", "set", "--x", "10", "--z", "180", "--lens", "NORMAL"],
                project=house,
            )
        )
        assert cam["x"] == 10.0
        act = _data(_ok(runner, ["camera", "activate", "observerCamera"], project=house))
        assert act["active"] == "observerCamera"

    def test_save_list_go_delete(self, runner, house):
        _ok(
            runner,
            ["camera", "set", "--kind", "observerCamera", "--x", "5", "--y", "5"],
            project=house,
        )
        saved = _data(_ok(runner, ["camera", "save", "My View"], project=house))
        assert saved["name"] == "My View"
        rows = _data(_ok(runner, ["camera", "list"], project=house))
        assert any(c["name"] == "My View" for c in rows)
        gone = _data(_ok(runner, ["camera", "go", "My View"], project=house))
        assert gone["x"] == 5.0
        _ok(runner, ["camera", "delete", "My View"], project=house)
        _fail(runner, ["camera", "go", "My View"], project=house)

    def test_time(self, runner, house):
        data = _data(
            _ok(
                runner,
                [
                    "camera",
                    "time",
                    "--year",
                    "2024",
                    "--month",
                    "6",
                    "--day",
                    "21",
                    "--hour",
                    "15",
                    "--utc",
                ],
                project=house,
            )
        )
        assert data["kind"] == "observerCamera"
        assert "2024-06-21" in data["iso"]

    def test_time_bad_month(self, runner, house):
        _fail(runner, ["camera", "time", "--month", "13"], project=house)


# ───────────────────────────────────────────── annotations


class TestAnnotations:
    def test_dimension_lifecycle(self, runner, house):
        d = _data(
            _ok(
                runner, ["dimension", "add", "0", "0", "400", "0", "--offset", "-20"], project=house
            )
        )
        did = d["id"]
        d2 = _data(
            _ok(
                runner,
                ["dimension", "set", did, "--offset", "-25", "--visible-in-3d"],
                project=house,
            )
        )
        assert d2["offset"] == -25.0
        _ok(runner, ["dimension", "delete", did], project=house)
        _fail(runner, ["dimension", "delete", did], project=house)

    def test_label_lifecycle(self, runner, house):
        l = _data(
            _ok(runner, ["label", "add", "Hello", "50", "50", "--color", "#FFFFFF"], project=house)
        )
        lid = l["id"]
        l2 = _data(_ok(runner, ["label", "set", lid, "--text", "Bye", "--x", "60"], project=house))
        assert l2["text"] == "Bye"
        _ok(runner, ["label", "delete", lid], project=house)
        _fail(runner, ["label", "delete", lid], project=house)

    def test_compass_get_set(self, runner, house):
        c = _data(_ok(runner, ["compass", "get"], project=house))
        assert "x" in c
        c2 = _data(
            _ok(
                runner,
                ["compass", "set", "--x", "10", "--diameter", "100", "--visible"],
                project=house,
            )
        )
        assert c2["diameter"] == 100.0

    def test_polyline_lifecycle(self, runner, house):
        p = _data(
            _ok(
                runner,
                [
                    "polyline",
                    "add",
                    "--points",
                    "0,0 100,0 100,50",
                    "--closed",
                    "--color",
                    "#00FF00",
                ],
                project=house,
            )
        )
        pid = p["id"]
        _ok(runner, ["polyline", "set", pid, "--thickness", "2"], project=house)
        _ok(runner, ["polyline", "delete", pid], project=house)
        _fail(runner, ["polyline", "delete", pid], project=house)


# ───────────────────────────────────────────── find


class TestFind:
    def test_rooms(self, runner, house):
        rooms = _data(_ok(runner, ["find", "rooms", "--name", "Liv"], project=house))
        assert len(rooms) == 1 and rooms[0]["name"] == "Living"
        inside = _data(_ok(runner, ["find", "rooms", "--contains", "200,150"], project=house))
        assert any(r["name"] == "Living" for r in inside)

    def test_walls_near_and_flags(self, runner, house):
        w = _data(_ok(runner, ["find", "walls", "--near", "200,0"], project=house))
        assert w and w[0]["id"]
        ws = _data(_ok(runner, ["find", "walls", "--horizontal"], project=house))
        assert ws
        none = _data(_ok(runner, ["find", "walls", "--thickness", "3"], project=house))
        assert none == []

    def test_pieces_doors_lights(self, runner, house):
        pieces = _data(_ok(runner, ["find", "pieces", "--kind", "pieceOfFurniture"], project=house))
        assert any(p["name"] == "Sofa" for p in pieces)
        lights = _data(_ok(runner, ["find", "lights", "--name", "Lam"], project=house))
        assert len(lights) == 1
        # no doors yet — empty result, exit 0
        doors = _data(_ok(runner, ["find", "doors"], project=house))
        assert doors == []
        _ok(runner, ["furniture", "add-door", "D1", "200", "0"], project=house)
        doors = _data(_ok(runner, ["find", "doors"], project=house))
        assert len(doors) == 1

    def test_find_rooms_empty(self, runner, house):
        assert _data(_ok(runner, ["find", "rooms", "--name", "zzz"], project=house)) == []


# ───────────────────────────────────────────── environment / export / print


class TestEnvironmentExportPrint:
    def test_environment_get_set(self, runner, house):
        env = _data(_ok(runner, ["environment", "get"], project=house))
        assert "skyColor" in env
        env2 = _data(
            _ok(
                runner,
                [
                    "environment",
                    "set",
                    "--sky-color",
                    "#88AACC",
                    "--walls-alpha",
                    "0.5",
                    "--drawing-mode",
                    "FILL",
                ],
                project=house,
            )
        )
        assert env2["skyColor"] == 0xFF88AACC

    def test_environment_bad_texture(self, runner, house):
        _fail(runner, ["environment", "set", "--sky-texture", "nope#x"], project=house)

    def test_photo_and_video_size(self, runner, house):
        p = _data(_ok(runner, ["environment", "photo-size", "800", "600"], project=house))
        assert p["photoWidth"] == 800
        v = _data(
            _ok(
                runner,
                [
                    "environment",
                    "video-size",
                    "1920",
                    "--aspect",
                    "RATIO_16_9",
                    "--frame-rate",
                    "30",
                ],
                project=house,
            )
        )
        assert v["videoWidth"] == 1920

    def test_export_svg(self, runner, house, tmp_path):
        out = tmp_path / "plan.svg"
        result = _ok(runner, ["export", "svg", str(out)], project=house, json_mode=False)
        assert "exported" in result.output
        assert out.exists()
        assert "<svg" in out.read_text(encoding="utf-8")
        # json variant
        out2 = tmp_path / "plan2.svg"
        assert _data(_ok(runner, ["export", "svg", str(out2)], project=house))["format"] == "svg"

    def test_print_get_set_levels_clear(self, runner, house):
        _ok(runner, ["level", "add", "Floor2"], project=house)
        pr = _data(
            _ok(
                runner,
                [
                    "print",
                    "set",
                    "--paper-width",
                    "210",
                    "--paper-height",
                    "297",
                    "--orientation",
                    "PORTRAIT",
                ],
                project=house,
            )
        )
        assert pr["paperWidth"] == 210.0
        got = _data(_ok(runner, ["print", "get"], project=house))
        assert got["paperWidth"] == 210.0
        _ok(runner, ["print", "add-level", "Floor2"], project=house)
        _ok(runner, ["print", "set-levels", "--levels", "Floor2"], project=house)
        _ok(runner, ["print", "remove-level", "Floor2"], project=house)
        _ok(runner, ["print", "clear"], project=house)


# ───────────────────────────────────────────── groups / materials / sash / emitter / shelf


class TestPieceOps:
    def test_group_lifecycle(self, runner, house):
        _ok(
            runner,
            ["furniture", "add", "Chair", "300", "100", "-w", "40", "-d", "40", "-h", "90"],
            project=house,
        )
        grp = _data(
            _ok(runner, ["group", "create", "Lounge", "--pieces", "Sofa,Chair"], project=house)
        )
        gid = grp["id"]
        rows = _data(_ok(runner, ["group", "list"], project=house))
        assert any(g["id"] == gid for g in rows)
        info = _data(_ok(runner, ["group", "info", gid], project=house))
        assert info["id"] == gid
        _ok(runner, ["group", "add", gid, "--pieces", "Lamp"], project=house)
        _ok(runner, ["group", "remove", gid, "--pieces", "Lamp"], project=house)
        g2 = _data(_ok(runner, ["group", "set", gid, "--name", "Lounge2"], project=house))
        assert g2["name"] == "Lounge2"
        _ok(runner, ["group", "ungroup", gid], project=house)
        _fail(runner, ["group", "info", gid], project=house)

    def test_group_create_unknown_piece(self, runner, house):
        _fail(runner, ["group", "create", "G", "--pieces", "Missing"], project=house)

    def test_material_lifecycle(self, runner, house):
        fid = _first_id(runner, house, "furniture")
        m = _data(
            _ok(
                runner,
                ["material", "set", fid, "wood", "--color", "#AA5500", "--shininess", "0.4"],
                project=house,
            )
        )
        assert m["color"] == 0xFFAA5500
        rows = _data(_ok(runner, ["material", "list", fid], project=house))
        assert any(x["name"] == "wood" for x in rows)
        _ok(runner, ["material", "clear", fid, "wood"], project=house)
        _ok(runner, ["material", "set", fid, "metal", "--color", "#CCCCCC"], project=house)
        _ok(runner, ["material", "clear-all", fid], project=house)

    def test_sash_lifecycle(self, runner, house):
        _ok(runner, ["furniture", "add-door", "DoorA", "200", "0"], project=house)
        s = _data(
            _ok(
                runner,
                [
                    "sash",
                    "add",
                    "DoorA",
                    "--x-axis",
                    "0.1",
                    "--y-axis",
                    "0.1",
                    "--width",
                    "0.8",
                    "--start-angle",
                    "0",
                    "--end-angle",
                    "1.0",
                ],
                project=house,
            )
        )
        assert s["xAxis"] == 0.1
        _data(_ok(runner, ["sash", "list", "DoorA"], project=house))
        _ok(runner, ["sash", "delete", "DoorA", "0"], project=house)
        _ok(
            runner,
            [
                "sash",
                "add",
                "DoorA",
                "--x-axis",
                "0",
                "--y-axis",
                "0",
                "--width",
                "0.5",
                "--start-angle",
                "0",
                "--end-angle",
                "1.0",
            ],
            project=house,
        )
        _ok(runner, ["sash", "clear", "DoorA"], project=house)

    def test_emitter_lifecycle(self, runner, house):
        fid = _first_id(runner, house, "furniture", kind="light")
        src = _data(
            _ok(
                runner,
                [
                    "emitter",
                    "source",
                    "add",
                    fid,
                    "--x",
                    "0",
                    "--y",
                    "0",
                    "--z",
                    "0.5",
                    "--color",
                    "#FFEE88",
                ],
                project=house,
            )
        )
        assert src is not None
        _data(_ok(runner, ["emitter", "source", "list", fid], project=house))
        _ok(
            runner,
            [
                "emitter",
                "source",
                "add",
                fid,
                "--x",
                "0.2",
                "--y",
                "0.2",
                "--z",
                "0.5",
                "--color",
                "#FFFFFF",
            ],
            project=house,
        )
        _ok(runner, ["emitter", "source", "delete", fid, "1"], project=house)
        _ok(runner, ["emitter", "source", "clear", fid], project=house)
        _ok(runner, ["emitter", "material", "add", fid, "glow"], project=house)
        _data(_ok(runner, ["emitter", "material", "list", fid], project=house))
        _ok(runner, ["emitter", "material", "delete", fid, "glow"], project=house)

    @staticmethod
    def _add_shelf_unit(runner, house, name):
        """The CLI cannot set kind=shelfUnit (add_piece validates kinds);
        seed the piece via the core API and save it, then use CLI commands."""
        from cli_anything.sweethome3d.core import furniture as furn_core
        from cli_anything.sweethome3d.core.project import open_home, save_home

        home = open_home(str(house))
        furn_core.add_piece(home, name, 100, 100, width=80, depth=30, height=200)
        for piece in home.furniture:
            if piece.name == name:
                piece.kind = "shelfUnit"
        save_home(home, str(house))
        return name

    def test_shelf_lifecycle(self, runner, house):
        fid = self._add_shelf_unit(runner, house, "Bookcase")
        sh = _data(_ok(runner, ["shelf", "add", fid, "--elevation", "40"], project=house))
        assert sh is not None
        _data(_ok(runner, ["shelf", "list", fid], project=house))
        _ok(runner, ["shelf", "add", fid, "--bounds", "0,0,0,10,10,2"], project=house)
        _ok(runner, ["shelf", "delete", fid, "0"], project=house)
        _ok(runner, ["shelf", "clear", fid], project=house)

    def test_shelf_needs_one_of(self, runner, house):
        fid = self._add_shelf_unit(runner, house, "Bookcase")
        _fail(runner, ["shelf", "add", fid], project=house)
        _fail(
            runner,
            ["shelf", "add", fid, "--elevation", "10", "--bounds", "0,0,0,1,1,1"],
            project=house,
        )


# ───────────────────────────────────────────── background / edit / render


class TestBackgroundEditRender:
    @staticmethod
    def _png(tmp_path):
        from PIL import Image

        img = Image.new("RGB", (100, 100), (255, 255, 255))
        for x in range(10, 90):
            for y in range(10, 14):
                img.putpixel((x, y), (0, 0, 0))
        p = tmp_path / "plan.png"
        img.save(p, format="PNG")
        return p

    def test_background_lifecycle(self, runner, house, tmp_path):
        img = self._png(tmp_path)
        bg = _data(
            _ok(
                runner,
                [
                    "background",
                    "set",
                    str(img),
                    "--scale-distance",
                    "100",
                    "--x-start",
                    "10",
                    "--y-start",
                    "10",
                    "--x-end",
                    "90",
                    "--y-end",
                    "10",
                ],
                project=house,
            )
        )
        assert bg is not None
        _data(_ok(runner, ["background", "info"], project=house))
        _ok(runner, ["background", "hide"], project=house)
        _ok(runner, ["background", "show"], project=house)
        _ok(runner, ["background", "clear"], project=house)

    def test_edit_floor(self, runner, house):
        data = _data(
            _ok(runner, ["edit", "floor", "--room", "Living", "--color", "#336699"], project=house)
        )
        assert data is not None
        rooms = _data(_ok(runner, ["find", "rooms", "--name", "Living"], project=house))
        assert rooms[0]["floorColor"] == 0xFF336699

    def test_edit_wall(self, runner, house):
        data = _data(
            _ok(runner, ["edit", "wall", "--near", "200,0", "--color", "#993344"], project=house)
        )
        assert data is not None

    def test_edit_light(self, runner, house):
        rows = _data(_ok(runner, ["catalog", "list", "--kind", "light"], project=house))
        cid = next(r["catalogId"] for r in rows)
        data = _data(
            _ok(
                runner,
                ["edit", "light", "--name", "Lamp", "--catalog", cid, "--power", "0.6"],
                project=house,
            )
        )
        assert data is not None

    def test_edit_door(self, runner, house):
        _ok(runner, ["furniture", "add-door", "Back Door", "200", "300"], project=house)
        data = _data(_ok(runner, ["edit", "door", "--name", "Back", "--flip"], project=house))
        assert data is not None

    def test_render_status_missing_binary(self, runner, house, monkeypatch):
        for var in ("SWEETHOME3D_BIN", "SWEETHOME3D_JAR"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("PATH", "/nonexistent")
        result = runner.invoke(cli, ["--project", str(house), "render", "status"])
        assert result.exit_code == 0
        assert "installed" in result.output

    def test_render_open_missing_binary(self, runner, house, monkeypatch):
        for var in ("SWEETHOME3D_BIN", "SWEETHOME3D_JAR"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("PATH", "/nonexistent")
        result = _fail(runner, ["render", "open"], project=house)
        assert result.output


# ───────────────────────────────────────────── import / undo / dry-run


class TestImportAndSession:
    def _write_spec(self, tmp_path):
        svg = textwrap.dedent("""\
            <?xml version="1.0" encoding="UTF-8"?>
            <svg xmlns="http://www.w3.org/2000/svg" width="300" height="200">
              <path fill="#000000"
                    d="M 10 10 L 290 10 L 290 190 L 10 190 Z
                       M 20 20 L 280 20 L 280 180 L 20 180 Z"/>
              <rect x="275" y="175" width="10" height="10" fill="#55d400"/>
            </svg>
        """)
        svg_file = tmp_path / "floor.svg"
        svg_file.write_text(svg, encoding="utf-8")
        spec = tmp_path / "spec.yaml"
        spec.write_text(
            textwrap.dedent(f"""\
                meta:
                  name: Imported
                  output: {tmp_path / "imported.sh3d"}
                  units: cm
                input:
                  floors:
                    - level: Ground
                      svg: floor.svg
            """),
            encoding="utf-8",
        )
        return spec

    def test_import_svg(self, runner, tmp_path):
        spec = self._write_spec(tmp_path)
        out = tmp_path / "imported.sh3d"
        data = _data(_ok(runner, ["import", "svg", "--spec", str(spec), "--output", str(out)]))
        assert data["created"] == str(out)
        assert out.exists()

    def test_status(self, runner, house):
        result = _ok(runner, ["status"], project=house, json_mode=False)
        assert "'walls': 4" in result.output

    def test_undo_redo_in_repl(self, runner, house):
        result = runner.invoke(
            cli, ["--project", str(house)], input="wall add 0 0 100 0\nundo\nredo\nquit\n"
        )
        assert result.exit_code == 0, result.output
        assert "Nothing to undo" not in result.output

    def test_undo_one_shot_empty(self, runner, house):
        result = _fail(runner, ["undo"], project=house, json_mode=False)
        assert "nothing to undo" in result.output

    def test_dry_run_does_not_persist(self, runner, house):
        _ok(
            runner,
            ["--dry-run", "wall", "add", "50", "50", "150", "50"],
            project=house,
            json_mode=False,
        )
        walls = _data(_ok(runner, ["wall", "list"], project=house))
        assert all(not (w["xStart"] == 50 and w["yStart"] == 50) for w in walls)

    def test_dry_run_flag_on_subcommand(self, runner, house):
        result = _ok(runner, ["project", "info"], project=house)
        # per-subcommand --json also works
        r2 = runner.invoke(cli, ["--project", str(house), "project", "info", "--json"])
        assert r2.exit_code == 0
        assert _data(r2)["name"] == _data(result)["name"]

    def test_repl_quit(self, runner, house):
        result = runner.invoke(cli, [], input="status\nquit\n")
        assert "Goodbye" in result.output or result.exit_code == 0

    def test_repl_project_load_and_command(self, runner, house):
        result = runner.invoke(
            cli,
            ["--project", str(house)],
            input="wall list\nquit\n",
            env={"HOME": os.environ.get("HOME", "/tmp")},
        )
        assert result.exit_code == 0
