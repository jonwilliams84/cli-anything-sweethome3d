"""Refinement round 3 — coverage for previously untested core modules.

Targets:
    * core/backup.py        (timestamped snapshot / restore helpers)
    * core/renderer.py      (pure-stdlib PNG floor-plan renderer)
    * core/find.py          (remaining filter branches)
    * core/levels.py        (delete / duplicate / property edge cases)
    * core/modify_rooms.py  (validation + subprocess error paths, mocked)
    * core/render_runtime.py(pure helpers: validation, comma stripping, alpha scan)
    * tools/cubicasa_runner.py (path sanitisation + startup failure paths)

No external binaries or .sh3d fixtures are required — everything runs with
the stdlib plus mocks of the subprocess boundary.
"""

from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path
from unittest import mock

import pytest

from cli_anything.sweethome3d.core import backup as backup_mod
from cli_anything.sweethome3d.core import find as find_mod
from cli_anything.sweethome3d.core import levels as lvl_core
from cli_anything.sweethome3d.core import modify_rooms as mr_mod
from cli_anything.sweethome3d.core import render_runtime as rr_mod
from cli_anything.sweethome3d.core.model import (
    Home,
    Level,
    PieceOfFurniture,
    Point,
    Room,
    Wall,
)
from cli_anything.sweethome3d.core.renderer import (
    _encode_png_rgb,
    _hex_to_rgb,
    _make_transform,
    _render_stdlib,
    render_floorplan,
)
from cli_anything.sweethome3d.tools import cubicasa_runner


# ─── backup ─────────────────────────────────────────────────────────────────


class TestBackup:
    def test_backup_missing_source_is_noop(self, tmp_path):
        src = tmp_path / "missing.sh3d"
        assert backup_mod.backup(src) == src
        assert backup_mod.list_backups(src) == []

    def test_backup_creates_sorted_snapshots(self, tmp_path):
        src = tmp_path / "home.sh3d"
        src.write_bytes(b"v1")
        stamps = iter(["20260101T000001Z", "20260101T000002Z"])
        with mock.patch.object(backup_mod, "_stamp", side_effect=lambda: next(stamps)):
            snap1 = backup_mod.backup(src)
            src.write_bytes(b"v2")
            snap2 = backup_mod.backup(src)
        assert snap1.exists() and snap1.read_bytes() == b"v1"
        assert snap1.parent == tmp_path / "home.backups"
        assert snap1.suffix == ".sh3d"
        assert backup_mod.list_backups(src) == [snap1, snap2]

    def test_backup_prunes_beyond_keep(self, tmp_path):
        src = tmp_path / "home.sh3d"
        src.write_bytes(b"x")
        stamps = iter(f"20260101T0000{n:02d}Z" for n in range(4))
        with mock.patch.object(backup_mod, "_stamp", side_effect=lambda: next(stamps)):
            snaps = [backup_mod.backup(src, keep=2) for _ in range(4)]
        for s in snaps[:-2]:
            assert not s.exists()
        remaining = backup_mod.list_backups(src)
        assert len(remaining) == 2
        assert remaining == snaps[-2:]

    def test_restore_latest(self, tmp_path):
        src = tmp_path / "home.sh3d"
        src.write_bytes(b"original")
        with mock.patch.object(backup_mod, "_stamp", return_value="20260101T000001Z"):
            snap = backup_mod.backup(src)
        src.write_bytes(b"edited")
        restored = backup_mod.restore_latest(src)
        assert restored == snap
        assert src.read_bytes() == b"original"
        # restore takes a redo snapshot of the edited state first
        assert len(backup_mod.list_backups(src)) == 2

    def test_restore_latest_without_backups(self, tmp_path):
        src = tmp_path / "none.sh3d"
        src.write_bytes(b"x")
        assert backup_mod.restore_latest(src) is None

    def test_restore_latest_missing_source(self, tmp_path):
        src = tmp_path / "ghost.sh3d"
        assert backup_mod.restore_latest(src) is None

    def test_restore_at_named_snapshot(self, tmp_path):
        src = tmp_path / "home.sh3d"
        src.write_bytes(b"v1")
        stamps = iter(["20260101T000001Z", "20260101T000002Z"])
        with mock.patch.object(backup_mod, "_stamp", side_effect=lambda: next(stamps)):
            snap1 = backup_mod.backup(src)
            src.write_bytes(b"v2")
            snap2 = backup_mod.backup(src)
        assert snap2.read_bytes() == b"v2"
        # restore by bare name
        assert backup_mod.restore_at(src, snap1.name) == snap1
        assert src.read_bytes() == b"v1"
        # restore by absolute path
        src.write_bytes(b"v3")
        assert backup_mod.restore_at(src, snap2) == snap2
        assert src.read_bytes() == b"v2"

    def test_restore_at_missing_snapshot_raises(self, tmp_path):
        src = tmp_path / "home.sh3d"
        src.write_bytes(b"x")
        with pytest.raises(FileNotFoundError):
            backup_mod.restore_at(src, "no-such.snapshot.sh3d")


# ─── renderer (pure-stdlib PNG path) ────────────────────────────────────────


class _FakeLevel:
    def __init__(self):
        self.rooms = [
            {
                "polygon": [(0, 0), (400, 0), (400, 300), (0, 300)],
                "label": "Kitchen",
                "floor_color": "#D8C6A4",
            }
        ]
        self.walls = [
            {"start": (0, 0), "end": (400, 0), "is_envelope": True},
            {"start": (400, 0), "end": (400, 300), "is_envelope": False},
        ]
        self.openings = [
            {"x": 200, "y": 0, "kind": "door"},
            {"x": 300, "y": 0, "kind": "window"},
        ]


class _FakeDesigner:
    name = "Fake Home"

    def __init__(self):
        self._levels = [_FakeLevel()]


class _EmptyDesigner:
    name = "Empty"

    def __init__(self):
        self._levels = [_FakeLevel()]  # level with no geometry
        self._levels[0].rooms = []
        self._levels[0].walls = []
        self._levels[0].openings = []


class TestRenderer:
    def test_hex_to_rgb(self):
        assert _hex_to_rgb("#FF0000") == (255, 0, 0)
        assert _hex_to_rgb("00FF80") == (0, 255, 128)
        assert _hex_to_rgb("FFF") == (200, 200, 200)  # unsupported → default

    def test_make_transform_empty_designer(self):
        tf = _make_transform(_EmptyDesigner(), 100, 100, 10)
        assert tf(50, 50) == (10, 10)

    def test_encode_png_rgb_minimal(self):
        png = _encode_png_rgb(bytearray(b"\x00\x00\x00" * 4), 2, 2)
        assert png[:8] == b"\x89PNG\r\n\x1a\n"

    def test_render_stdlib_writes_png(self, tmp_path):
        out = tmp_path / "plan.png"
        _render_stdlib(_FakeDesigner(), out, 120, 90, 10)
        data = out.read_bytes()
        assert data[:8] == b"\x89PNG\r\n\x1a\n"

    def test_render_floorplan_public_api(self, tmp_path):
        out = tmp_path / "sub" / "plan.png"
        result = render_floorplan(_FakeDesigner(), out, canvas_width=200, canvas_height=150)
        assert result == out
        assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


# ─── find.py — remaining branches ───────────────────────────────────────────


def _unit_home() -> Home:
    """Two levels, a room on each, walls, a door and a light."""
    home = Home()
    l0 = Level(name="Ground")
    l1 = Level(name="First")
    home.levels.extend([l0, l1])

    home.rooms.append(
        Room(
            points=[Point(0, 0), Point(400, 0), Point(400, 300), Point(0, 300)],
            level=l0.id,
            name="Kitchen",
        )
    )
    home.rooms.append(
        Room(
            points=[Point(500, 0), Point(900, 0), Point(900, 300), Point(500, 300)],
            level=l0.id,
            name="Living",
        )
    )

    w_linked_a = Wall(0, 0, 400, 0, level=l0.id)
    w_linked_b = Wall(400, 0, 400, 300, level=l0.id)
    w_linked_a.wallAtEnd = w_linked_b.id
    w_linked_b.wallAtStart = w_linked_a.id
    home.walls.extend([w_linked_a, w_linked_b, Wall(0, 300, 0, 0, level=l0.id)])

    home.furniture.append(
        PieceOfFurniture(
            name="FrontDoor",
            x=200,
            y=0,
            width=90,
            height=200,
            depth=10,
            level=l0.id,
            kind="doorOrWindow",
            catalogId="DOOR-01",
        )
    )
    home.furniture.append(
        PieceOfFurniture(
            name="KitchenLight",
            x=200,
            y=150,
            width=30,
            height=15,
            depth=30,
            level=l0.id,
            kind="light",
            catalogId="LIGHT-01",
        )
    )
    return home


class TestFindBranches:
    def test_find_level_no_name_multi_level_returns_none(self):
        assert find_mod.find_level(_unit_home()) is None

    def test_find_level_single_level_returns_it(self):
        home = Home()
        only = Level(name="Solo")
        home.levels.append(only)
        assert find_mod.find_level(home) is only

    def test_find_level_exact_beats_substring(self):
        home = _unit_home()
        ground2 = Level(name="ground floor")
        home.levels.append(ground2)
        assert find_mod.find_level(home, name="Ground") is home.levels[0]

    def test_find_level_ambiguous_returns_none(self):
        home = Home()
        home.levels.extend([Level(name="Floor A"), Level(name="Floor B")])
        assert find_mod.find_level(home, name="floor") is None

    def test_level_filter_type_error(self):
        with pytest.raises(TypeError):
            find_mod._level_id_filter(_unit_home(), 42)

    def test_level_filter_accepts_level_object(self):
        home = _unit_home()
        assert find_mod._level_id_filter(home, home.levels[0]) == home.levels[0].id

    def test_level_filter_passes_through_unknown_str(self):
        assert find_mod._level_id_filter(_unit_home(), "some-level-id") == "some-level-id"

    def test_find_room_contains_point(self):
        home = _unit_home()
        room = find_mod.find_room(home, contains_point=(700, 150))
        assert room is not None and room.name == "Living"

    def test_find_room_contains_point_miss(self):
        assert find_mod.find_room(_unit_home(), contains_point=(450, 150)) is None

    def test_find_wall_near_point_picks_closest(self):
        home = _unit_home()
        w = find_mod.find_wall(home, near_point=(200, 4))
        assert w is not None and (w.xStart, w.yStart) == (0, 0)

    def test_find_wall_beyond_max_distance(self):
        assert find_mod.find_wall(_unit_home(), near_point=(200, 500)) is None

    def test_find_wall_ambiguous_no_point(self):
        assert find_mod.find_wall(_unit_home()) is None

    def test_find_walls_unlinked_filter(self):
        home = _unit_home()
        assert len(find_mod.find_walls(home, unlinked=True)) == 1
        assert len(find_mod.find_walls(home, unlinked=False)) == 2

    def test_find_walls_thickness(self):
        home = _unit_home()
        assert len(find_mod.find_walls(home, thickness=7.5)) == 3
        assert find_mod.find_walls(home, thickness=20) == []

    def test_find_room_walls_side_filters(self):
        home = _unit_home()
        kitchen = find_mod.find_room(home, name="Kitchen")
        assert kitchen is not None
        all_sides = find_mod.find_room_walls(home, kitchen)
        assert len(all_sides) == 3
        assert len(find_mod.find_room_walls(home, kitchen, side="north")) == 1
        assert len(find_mod.find_room_walls(home, kitchen, side="east")) == 1
        assert len(find_mod.find_room_walls(home, kitchen, side="west")) == 1
        assert find_mod.find_room_walls(home, kitchen, side="south") == []

    def test_find_pieces_catalog_and_room(self):
        home = _unit_home()
        kitchen = find_mod.find_room(home, name="Kitchen")
        assert find_mod.find_pieces(home, catalog="light") == [
            p for p in home.furniture if p.name == "KitchenLight"
        ]
        kitchen_names = [p.name for p in find_mod.find_pieces(home, in_room=kitchen)]
        assert "KitchenLight" in kitchen_names
        living = find_mod.find_room(home, name="Living")
        assert find_mod.find_pieces(home, in_room=living) == []

    def test_find_pieces_near_point_sorted(self):
        home = _unit_home()
        pieces = find_mod.find_pieces(home, near_point=(200, 140), max_distance_cm=500)
        assert next(p.name for p in pieces) == "KitchenLight"

    def test_find_door_and_light_shortcuts(self):
        home = _unit_home()
        assert [d.name for d in find_mod.find_doors(home)] == ["FrontDoor"]
        assert find_mod.find_door(home).name == "FrontDoor"
        assert find_mod.find_light(home).name == "KitchenLight"
        assert find_mod.find_door(home, name="nope") is None
        assert find_mod.find_light(home, name="nope") is None


# ─── levels.py — edge cases ─────────────────────────────────────────────────


class TestLevelsEdgeCases:
    def test_add_level_duplicate_name_raises(self):
        home = _unit_home()
        with pytest.raises(ValueError, match="already exists"):
            lvl_core.add_level(home, "Ground")

    def test_add_level_increments_elevation_index(self):
        home = _unit_home()
        home.levels[1].elevationIndex = 5
        lvl = lvl_core.add_level(home, "Attic")
        assert lvl.elevationIndex == 6

    def test_delete_level_refuses_when_attached(self):
        home = _unit_home()
        with pytest.raises(ValueError, match="attached objects"):
            lvl_core.delete_level(home, "Ground", detach=False)
        assert len(home.levels) == 2

    def test_delete_level_detaches(self):
        home = _unit_home()
        assert lvl_core.delete_level(home, "Ground", detach=True) is True
        assert len(home.levels) == 1
        assert all(w.level is None for w in home.walls)

    def test_delete_level_unknown(self):
        assert lvl_core.delete_level(_unit_home(), "Nope") is False

    def test_set_level_properties_unknown_field(self):
        with pytest.raises(AttributeError, match="unknown level field"):
            lvl_core.set_level_properties(_unit_home(), "Ground", no_such_field=1)

    def test_set_level_properties_unknown_level(self):
        with pytest.raises(KeyError):
            lvl_core.set_level_properties(_unit_home(), "Nope", name="X")

    def test_duplicate_level_flags_and_offsets(self):
        home = _unit_home()
        lvl = lvl_core.duplicate_level(
            home,
            "Ground",
            new_name="Copy",
            elevation=-250,
            offset_x=100,
            offset_y=50,
            include_rooms=False,
            include_furniture=False,
            include_annotations=False,
        )
        assert lvl.name == "Copy" and lvl.elevation == -250
        assert len(home.walls) == 6  # 3 originals + 3 copies
        copied = [w for w in home.walls if w.level == lvl.id]
        originals = [w for w in home.walls if w.level != lvl.id]
        for nw, ow in zip(copied, originals, strict=False):
            assert nw.xStart == ow.xStart + 100
            assert nw.yStart == ow.yStart + 50
        assert len(home.rooms) == 2 and len(home.furniture) == 2

    def test_duplicate_level_remaps_wall_links(self):
        home = _unit_home()
        lvl = lvl_core.duplicate_level(home, "Ground", new_name="Copy")
        copied = [w for w in home.walls if w.level == lvl.id]
        ids = {w.id for w in copied}
        for w in copied:
            assert w.wallAtStart is None or w.wallAtStart in ids
            assert w.wallAtEnd is None or w.wallAtEnd in ids

    def test_duplicate_level_name_clash(self):
        with pytest.raises(ValueError, match="already exists"):
            lvl_core.duplicate_level(_unit_home(), "Ground", new_name="First")

    def test_duplicate_level_unknown_source(self):
        with pytest.raises(KeyError):
            lvl_core.duplicate_level(_unit_home(), "Nope", new_name="X")

    def test_select_level(self):
        home = _unit_home()
        assert lvl_core.select_level(home, "First") is home.levels[1]
        assert home.selectedLevel == home.levels[1].id
        assert lvl_core.select_level(home, None) is None
        assert home.selectedLevel is None
        with pytest.raises(KeyError):
            lvl_core.select_level(home, "Nope")


# ─── modify_rooms.py — validation + subprocess error paths (mocked) ────────


class TestModifyRoomsValidation:
    def test_missing_source_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            mr_mod.modify_rooms(str(tmp_path / "missing.sh3d"), {"rooms": []})

    def test_run_validated_rejects_relative_executable(self):
        with pytest.raises(RuntimeError, match="non-absolute"):
            mr_mod._run_validated(["java", "-version"])

    def test_run_validated_rejects_missing_executable(self, tmp_path):
        ghost = tmp_path / "no-such-binary"
        with pytest.raises(RuntimeError, match="not found"):
            mr_mod._run_validated([str(ghost)])

    def test_run_validated_runs_real_binary(self, tmp_path):
        exe = tmp_path / "echo.sh"
        exe.write_text("#!/bin/sh\necho ok\n")
        exe.chmod(0o755)
        result = mr_mod._run_validated([str(exe)])
        assert result.returncode == 0

    def test_java_bin_missing(self, tmp_path):
        with pytest.raises(RuntimeError, match="bundled java not found"):
            mr_mod._java_bin(tmp_path)

    def test_build_classpath_without_jars(self, tmp_path):
        with pytest.raises(RuntimeError, match="No .jar files"):
            mr_mod._build_classpath(tmp_path, tmp_path / "classes")

    def test_build_classpath_includes_jars_and_classes(self, tmp_path):
        (tmp_path / "lib").mkdir()
        (tmp_path / "lib" / "b.jar").write_bytes(b"")
        (tmp_path / "lib" / "a.jar").write_bytes(b"")
        cp = mr_mod._build_classpath(tmp_path, tmp_path / "classes")
        assert cp.endswith(str(tmp_path / "classes"))
        assert cp.index("a.jar") < cp.index("b.jar")  # sorted

    def test_needs_compile(self, tmp_path):
        src = tmp_path / "Src.java"
        src.write_text("class Src {}")
        cls = tmp_path / "Src.class"
        assert mr_mod._needs_compile(src, cls) is True  # class missing
        cls.write_text("")
        assert mr_mod._needs_compile(src, cls) is False  # fresh
        st = cls.stat()
        os.utime(cls, (st.st_atime, st.st_mtime - 100))  # class older than src
        assert mr_mod._needs_compile(src, cls) is True

    def test_modify_rooms_java_failure_raises(self, tmp_path):
        src = tmp_path / "home.sh3d"
        src.write_bytes(b"PK\x03\x04fake")
        fake_home = tmp_path / "sh3d"
        (fake_home / "lib").mkdir(parents=True)
        (fake_home / "lib" / "x.jar").write_bytes(b"")
        fake_exe = tmp_path / "java"
        fake_exe.write_text("#!/bin/sh\nexit 2\n")
        fake_exe.chmod(0o755)

        with (
            mock.patch.object(
                mr_mod, "_ensure_compiled", return_value=(fake_home, tmp_path / "classes")
            ),
            mock.patch.object(mr_mod, "_java_bin", return_value=fake_exe),
            mock.patch.object(mr_mod, "_run_validated") as run,
        ):
            run.return_value = mock.Mock(returncode=2, stdout="", stderr="boom")
            with pytest.raises(RuntimeError, match="exited with code 2"):
                mr_mod.modify_rooms(str(src), {"rooms": []})
        # backup of the source was taken before the failed edit
        assert backup_mod.list_backups(src)

    def test_modify_rooms_missing_output_raises(self, tmp_path):
        src = tmp_path / "home.sh3d"
        src.write_bytes(b"PK\x03\x04fake")
        fake_home = tmp_path / "sh3d"
        (fake_home / "lib").mkdir(parents=True)
        (fake_home / "lib" / "x.jar").write_bytes(b"")
        fake_exe = tmp_path / "java"
        fake_exe.write_text("#!/bin/sh\nexit 0\n")
        fake_exe.chmod(0o755)

        with (
            mock.patch.object(
                mr_mod, "_ensure_compiled", return_value=(fake_home, tmp_path / "classes")
            ),
            mock.patch.object(mr_mod, "_java_bin", return_value=fake_exe),
            mock.patch.object(mr_mod, "_run_validated") as run,
        ):
            run.return_value = mock.Mock(returncode=0, stdout="{}", stderr="")
            with pytest.raises(RuntimeError, match="output file not found"):
                mr_mod.modify_rooms(str(src), {"rooms": []}, out_path=str(tmp_path / "out.sh3d"))

    @staticmethod
    def _fake_java_writing_output():
        def fake_run(cmd, timeout=None):
            out_path = cmd[cmd.index("--out") + 1]
            Path(out_path).write_bytes(b"new-bytes")

            class R:
                returncode = 0
                stdout = "log line\n" + json.dumps({"rooms_modified": 3})
                stderr = ""

            return R()

        return fake_run

    def test_modify_rooms_success_in_place(self, tmp_path):
        src = tmp_path / "home.sh3d"
        src.write_bytes(b"old-bytes")
        fake_home = tmp_path / "sh3d"
        (fake_home / "lib").mkdir(parents=True)
        (fake_home / "lib" / "x.jar").write_bytes(b"")
        fake_exe = tmp_path / "java"
        fake_exe.write_text("#!/bin/sh\nexit 0\n")
        fake_exe.chmod(0o755)

        with (
            mock.patch.object(
                mr_mod, "_ensure_compiled", return_value=(fake_home, tmp_path / "classes")
            ),
            mock.patch.object(mr_mod, "_java_bin", return_value=fake_exe),
            mock.patch.object(
                mr_mod, "_run_validated", side_effect=self._fake_java_writing_output()
            ),
        ):
            result = mr_mod.modify_rooms(str(src), {"rooms": [{}]})

        assert result["rooms_modified"] == 3
        assert Path(result["output"]) == src
        assert src.read_bytes() == b"new-bytes"

    def test_modify_rooms_success_to_explicit_out(self, tmp_path):
        src = tmp_path / "home.sh3d"
        src.write_bytes(b"old-bytes")
        out = tmp_path / "out.sh3d"
        fake_home = tmp_path / "sh3d"
        (fake_home / "lib").mkdir(parents=True)
        (fake_home / "lib" / "x.jar").write_bytes(b"")
        fake_exe = tmp_path / "java"
        fake_exe.write_text("#!/bin/sh\nexit 0\n")
        fake_exe.chmod(0o755)

        with (
            mock.patch.object(
                mr_mod, "_ensure_compiled", return_value=(fake_home, tmp_path / "classes")
            ),
            mock.patch.object(mr_mod, "_java_bin", return_value=fake_exe),
            mock.patch.object(
                mr_mod, "_run_validated", side_effect=self._fake_java_writing_output()
            ),
        ):
            result = mr_mod.modify_rooms(str(src), {"rooms": []}, out_path=str(out))

        assert out.read_bytes() == b"new-bytes"
        assert src.read_bytes() == b"old-bytes"  # source untouched


# ─── render_runtime.py — pure helpers ───────────────────────────────────────


class TestRenderRuntimeHelpers:
    def test_validate_executable_rejects_relative(self):
        with pytest.raises(ValueError, match="Refusing to execute"):
            rr_mod._validate_executable(Path("java"))

    def test_validate_executable_rejects_missing(self, tmp_path):
        with pytest.raises(ValueError, match="non-existent"):
            rr_mod._validate_executable(tmp_path / "nope")

    def test_validate_executable_accepts_real_file(self, tmp_path):
        exe = tmp_path / "tool"
        exe.write_text("#!/bin/sh\n")
        assert rr_mod._validate_executable(exe) == str(exe)

    def test_validate_file_arg_missing(self, tmp_path):
        with pytest.raises(ValueError, match="File not found"):
            rr_mod._validate_file_arg(str(tmp_path / "nope.sh3d"))

    def test_validate_file_arg_resolves(self, tmp_path):
        f = tmp_path / "home.sh3d"
        f.write_bytes(b"x")
        assert rr_mod._validate_file_arg(str(f)) == str(f)

    @staticmethod
    def _home_with_levels():
        home = Home()
        home.levels.extend([Level(name="Ground"), Level(name="First")])
        return home

    def test_resolve_level_specs_by_name_and_id(self):
        home = self._home_with_levels()
        resolved = rr_mod._resolve_level_specs(home, ["ground", home.levels[1].id])
        assert resolved == {home.levels[0].id, home.levels[1].id}

    def test_resolve_level_specs_ignores_empty(self):
        home = self._home_with_levels()
        assert rr_mod._resolve_level_specs(home, ["", "  "]) == set()

    def test_resolve_level_specs_unknown_raises(self):
        home = self._home_with_levels()
        with pytest.raises(ValueError, match="unknown level"):
            rr_mod._resolve_level_specs(home, ["Basement"])

    def test_remove_thousands_commas(self):
        assert rr_mod._remove_thousands_commas("v 1,350.1787 2.5") == "v 1350.1787 2.5"
        assert rr_mod._remove_thousands_commas("a,b") == "a,b"  # not digits
        assert rr_mod._remove_thousands_commas("1,2,3") == "123"

    def test_strip_obj_commas_rewrites_file(self, tmp_path):
        obj = tmp_path / "scene.obj"
        obj.write_text("v 1,350.1787 0.0 2.5\nvn 0.0 1,000.0 0.0\nf 1 2 3\n")
        rr_mod._strip_obj_commas(obj)
        content = obj.read_text()
        assert "1,350" not in content and "1,000" not in content
        assert "f 1 2 3" in content

    def test_strip_obj_commas_noop_when_unchanged(self, tmp_path):
        obj = tmp_path / "clean.obj"
        obj.write_text("v 1.0 2.0 3.0\n")
        before = obj.read_text()
        rr_mod._strip_obj_commas(obj)
        assert obj.read_text() == before

    def test_strip_obj_commas_missing_file_noop(self, tmp_path):
        rr_mod._strip_obj_commas(tmp_path / "nope.obj")  # must not raise

    @staticmethod
    def _sh3d_with_xml(xml: str, path: Path) -> str:
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("Home.xml", xml)
        return str(path)

    def test_needs_export_preprocessing_positive(self, tmp_path):
        p = self._sh3d_with_xml('<home><environment wallsAlpha="0.5"/></home>', tmp_path / "a.sh3d")
        assert rr_mod._needs_export_preprocessing(p) is True

    def test_needs_export_preprocessing_zero_alpha(self, tmp_path):
        p = self._sh3d_with_xml('<home><environment wallsAlpha="0"/></home>', tmp_path / "b.sh3d")
        assert rr_mod._needs_export_preprocessing(p) is False

    def test_needs_export_preprocessing_no_environment(self, tmp_path):
        p = self._sh3d_with_xml("<home/>", tmp_path / "c.sh3d")
        assert rr_mod._needs_export_preprocessing(p) is False

    def test_needs_export_preprocessing_bad_zip(self, tmp_path):
        p = tmp_path / "bad.sh3d"
        p.write_bytes(b"not a zip")
        assert rr_mod._needs_export_preprocessing(str(p)) is False

    def test_copy_with_walls_alpha_zeroed(self, tmp_path):
        src = tmp_path / "src.sh3d"
        with zipfile.ZipFile(src, "w") as z:
            z.writestr("Home.xml", '<home><environment wallsAlpha="0.7"/></home>')
        dst = tmp_path / "dst.sh3d"
        rr_mod._copy_with_walls_alpha_zeroed(str(src), str(dst))
        with zipfile.ZipFile(dst) as z:
            xml = z.read("Home.xml").decode()
        assert 'wallsAlpha="0.7"' not in xml


# ─── cubicasa_runner.py — sanitisation + startup failures ──────────────────


class TestCubicasaRunner:
    def test_sanitize_path_accepts_clean_paths(self):
        assert cubicasa_runner._sanitize_path("/tmp/plan.png", "input") == "/tmp/plan.png"

    def test_sanitize_path_rejects_empty(self):
        with pytest.raises(ValueError, match="empty or contains NUL"):
            cubicasa_runner._sanitize_path("", "input")

    def test_sanitize_path_rejects_nul(self):
        with pytest.raises(ValueError, match="empty or contains NUL"):
            cubicasa_runner._sanitize_path("plan\x00.png", "input")

    @pytest.mark.parametrize(
        "bad",
        ["a|b", "a;b", "a&b", "a`b`", "a$b", "a<b", "a>b", "a\\b", "a\nb"],
    )
    def test_sanitize_path_rejects_metacharacters(self, bad):
        with pytest.raises(ValueError, match="shell metacharacters"):
            cubicasa_runner._sanitize_path(bad, "input")

    def test_main_requires_sanitised_input_first(self):
        with pytest.raises(ValueError, match="input"):
            cubicasa_runner.main("bad|path", "out.json")

    def test_main_requires_cubicasa_home(self, monkeypatch):
        monkeypatch.delenv("CUBICASA_HOME", raising=False)
        with pytest.raises(SystemExit, match="CUBICASA_HOME"):
            cubicasa_runner.main("in.png", "out.json")

    def test_main_rejects_missing_cubicasa_home_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CUBICASA_HOME", str(tmp_path / "no-such-dir"))
        with pytest.raises(SystemExit, match="CUBICASA_HOME"):
            cubicasa_runner.main("in.png", "out.json")
