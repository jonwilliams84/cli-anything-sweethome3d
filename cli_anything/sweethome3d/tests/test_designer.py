"""Unit tests for the SweetHome3D Designer API.

All tests are pure Python — no SweetHome3D installation required.
Run with:
    pytest cli_anything/sweethome3d/tests/test_designer.py -v
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

from cli_anything.sweethome3d.core.designer import (
    Designer, WallHandle, RoomHandle,
    _dist, _pt_to_seg_dist, _polygon_area, _pt_in_polygon, _polygon_centroid,
)


# ─────────────────────────── Geometry helpers ────────────────────────────────

class TestGeometryHelpers:
    def test_dist(self):
        assert abs(_dist((0, 0), (3, 4)) - 5.0) < 1e-9

    def test_pt_to_seg_dist_midpoint(self):
        d, cp = _pt_to_seg_dist((5, 0), (0, 0), (10, 0))
        assert d < 1e-9
        assert abs(cp[0] - 5) < 1e-9

    def test_pt_to_seg_dist_clamped(self):
        d, cp = _pt_to_seg_dist((15, 0), (0, 0), (10, 0))
        assert abs(cp[0] - 10) < 1e-9  # clamped to end

    def test_polygon_area(self):
        square = [(0, 0), (10, 0), (10, 10), (0, 10)]
        assert abs(abs(_polygon_area(square)) - 100.0) < 1e-9

    def test_pt_in_polygon_inside(self):
        poly = [(0, 0), (100, 0), (100, 100), (0, 100)]
        assert _pt_in_polygon((50, 50), poly)

    def test_pt_in_polygon_outside(self):
        poly = [(0, 0), (100, 0), (100, 100), (0, 100)]
        assert not _pt_in_polygon((200, 200), poly)

    def test_polygon_centroid(self):
        cx, cy = _polygon_centroid([(0, 0), (100, 0), (100, 100), (0, 100)])
        assert abs(cx - 50) < 1e-9
        assert abs(cy - 50) < 1e-9


# ─────────────────────────── Designer creation ───────────────────────────────

class TestDesignerCreation:
    def test_create_default(self):
        d = Designer()
        assert d.name == "Home"
        assert d.unit == "CENTIMETER"

    def test_create_named(self):
        d = Designer(name="My House")
        assert d.name == "My House"

    def test_no_levels_initially(self):
        d = Designer()
        assert d._levels == []


# ─────────────────────────── Level management ────────────────────────────────

class TestLevels:
    def test_add_level(self):
        d = Designer()
        lv = d.add_level("Ground Floor")
        assert lv.name == "Ground Floor"
        assert lv.floor_height == 0.0
        assert lv.ceiling_height == 250.0
        assert len(d._levels) == 1

    def test_add_multiple_levels(self):
        d = Designer()
        g = d.add_level("Ground", floor_height=0)
        f = d.add_level("First",  floor_height=250)
        assert len(d._levels) == 2
        assert g.idx == 0
        assert f.idx == 1

    def test_resolve_level_none_returns_first(self):
        d = Designer()
        lv = d.add_level("Ground")
        assert d._resolve_level(None) is lv

    def test_resolve_level_by_int(self):
        d = Designer()
        d.add_level("Ground")
        f = d.add_level("First")
        assert d._resolve_level(1) is f

    def test_resolve_level_invalid_int(self):
        d = Designer()
        d.add_level("Ground")
        with pytest.raises(IndexError, match="out of range"):
            d._resolve_level(5)

    def test_resolve_level_no_levels(self):
        d = Designer()
        with pytest.raises(ValueError, match="No levels"):
            d._resolve_level(None)


# ─────────────────────────── Envelope ────────────────────────────────────────

class TestEnvelope:
    def _make(self):
        d = Designer()
        g = d.add_level("Ground")
        return d, g

    def test_envelope_creates_4_walls(self):
        d, g = self._make()
        ids = d.envelope(g, width=1000, depth=800)
        assert len(ids) == 4
        assert len(g.walls) == 4

    def test_envelope_wall_ids_returned(self):
        d, g = self._make()
        ids = d.envelope(g, width=500, depth=400)
        wall_ids = {w["id"] for w in g.walls}
        for wid in ids:
            assert wid in wall_ids

    def test_envelope_walls_are_envelope(self):
        d, g = self._make()
        d.envelope(g, width=500, depth=400)
        assert all(w["is_envelope"] for w in g.walls)

    def test_envelope_facing_labels(self):
        d, g = self._make()
        d.envelope(g, width=500, depth=400)
        facings = {w["facing"] for w in g.walls}
        assert facings == {"north", "east", "south", "west"}

    def test_envelope_dimensions(self):
        d, g = self._make()
        d.envelope(g, width=1000, depth=800)
        north = next(w for w in g.walls if w["facing"] == "north")
        assert abs(north["start"][0] - 0) < 1
        assert abs(north["end"][0] - 1000) < 1

    def test_envelope_with_offset(self):
        d, g = self._make()
        d.envelope(g, width=500, depth=400, x_offset=100, y_offset=50)
        north = next(w for w in g.walls if w["facing"] == "north")
        assert abs(north["start"][0] - 100) < 1
        assert abs(north["start"][1] - 50) < 1

    def test_envelope_thickness(self):
        d, g = self._make()
        d.envelope(g, width=500, depth=400, thickness=25)
        assert all(w["thickness"] == 25 for w in g.walls)

    def test_validate_after_envelope(self):
        d, g = self._make()
        d.envelope(g, width=1000, depth=800)
        report = d.validate()
        assert report["envelope_closed"] == [True]


# ─────────────────────────── Partitions ──────────────────────────────────────

class TestPartitions:
    def _make_with_envelope(self):
        d = Designer()
        g = d.add_level("Ground")
        d.envelope(g, width=1000, depth=800)
        return d, g

    def test_partition_adds_wall(self):
        d, g = self._make_with_envelope()
        wid = d.partition(g, (500, 0), (500, 800))
        assert any(w["id"] == wid for w in g.walls)

    def test_partition_not_envelope(self):
        d, g = self._make_with_envelope()
        wid = d.partition(g, (500, 0), (500, 800))
        w = next(x for x in g.walls if x["id"] == wid)
        assert not w["is_envelope"]

    def test_partition_default_thickness(self):
        d, g = self._make_with_envelope()
        wid = d.partition(g, (500, 0), (500, 800))
        w = next(x for x in g.walls if x["id"] == wid)
        assert w["thickness"] == 10.0

    def test_partition_custom_thickness(self):
        d, g = self._make_with_envelope()
        wid = d.partition(g, (500, 0), (500, 800), thickness=15)
        w = next(x for x in g.walls if x["id"] == wid)
        assert w["thickness"] == 15.0

    def test_partition_orphan_raises(self):
        d, g = self._make_with_envelope()
        with pytest.raises(ValueError, match="doesn't touch"):
            d.partition(g, (500, 100), (500, 700))  # endpoints don't touch envelope

    def test_partition_requires_start_and_end(self):
        d, g = self._make_with_envelope()
        with pytest.raises(ValueError, match="requires both"):
            d.partition(g)

    def test_partition_snap_to(self):
        d, g = self._make_with_envelope()
        north = d.wall_facing("north", level=g)
        # snap_to should project start onto north wall
        wid = d.partition(g, (500, 5), (500, 800), snap_to=north)
        w = next(x for x in g.walls if x["id"] == wid)
        # After snap, start y should be 0 (north wall y)
        assert abs(w["start"][1] - 0.0) < 5.0

    def test_validate_with_good_partition(self):
        d, g = self._make_with_envelope()
        d.partition(g, (500, 0), (500, 800))
        report = d.validate()
        assert not report["orphan_endpoints"]

    def test_validate_detects_orphan(self):
        d, g = self._make_with_envelope()
        # Add a wall that doesn't touch anything (fake directly)
        g.walls.append({
            "id": "orphan-wall",
            "start": [200, 200],
            "end": [200, 600],
            "thickness": 10,
            "is_envelope": False,
            "facing": None,
            "level_id": g.id,
        })
        report = d.validate()
        assert any(o["wall_id"] == "orphan-wall" for o in report["orphan_endpoints"])


# ─────────────────────────── Rooms ───────────────────────────────────────────

class TestRooms:
    def _make(self):
        d = Designer()
        g = d.add_level("Ground")
        d.envelope(g, width=1000, depth=800)
        return d, g

    def test_room_returns_handle(self):
        d, g = self._make()
        h = d.room(g, polygon=[(0,0),(500,0),(500,400),(0,400)], label="Living")
        assert isinstance(h, RoomHandle)

    def test_room_stored(self):
        d, g = self._make()
        d.room(g, polygon=[(0,0),(500,0),(500,400),(0,400)], label="Kitchen")
        assert len(g.rooms) == 1
        assert g.rooms[0]["label"] == "Kitchen"

    def test_room_area(self):
        d, g = self._make()
        d.room(g, polygon=[(0,0),(500,0),(500,400),(0,400)], label="Living")
        r = g.rooms[0]
        # 500 × 400 = 200000 cm² = 20.0 m²
        assert abs(r["area_m2"] - 20.0) < 0.1

    def test_room_floor_color(self):
        d, g = self._make()
        d.room(g, polygon=[(0,0),(100,0),(100,100),(0,100)],
               label="Test", floor_color="#FF0000")
        assert g.rooms[0]["floor_color"] == "#FF0000"

    def test_room_too_few_points(self):
        d, g = self._make()
        with pytest.raises(ValueError, match="at least 3"):
            d.room(g, polygon=[(0,0),(100,0)], label="Bad")

    def test_multiple_rooms(self):
        d, g = self._make()
        d.room(g, polygon=[(0,0),(500,0),(500,400),(0,400)], label="A")
        d.room(g, polygon=[(500,0),(1000,0),(1000,400),(500,400)], label="B")
        assert len(g.rooms) == 2

    def test_validate_unnamed_room(self):
        d, g = self._make()
        d.room(g, polygon=[(0,0),(100,0),(100,100),(0,100)])
        report = d.validate()
        assert len(report["rooms_unnamed"]) == 1

    def test_validate_named_room_ok(self):
        d, g = self._make()
        d.room(g, polygon=[(0,0),(100,0),(100,100),(0,100)], label="Named")
        report = d.validate()
        assert report["rooms_unnamed"] == []


# ─────────────────────────── Openings ────────────────────────────────────────

class TestOpenings:
    def _make(self):
        d = Designer()
        g = d.add_level("Ground")
        d.envelope(g, width=1000, depth=800)
        return d, g

    def test_add_external_door(self):
        d, g = self._make()
        north = d.wall_facing("north", level=g)
        oid = d.add_external_door(g, wall=north, position_along=0.5)
        assert len(g.openings) == 1
        assert g.openings[0]["kind"] == "door"
        assert g.openings[0]["id"] == oid

    def test_add_external_door_position(self):
        d, g = self._make()
        north = d.wall_facing("north", level=g)
        d.add_external_door(g, wall=north, position_along=0.25)
        o = g.openings[0]
        # Position along north wall (0,0)→(1000,0) at 25% = x=250
        assert abs(o["x"] - 250) < 1

    def test_add_external_door_by_id(self):
        d, g = self._make()
        north_wall = g._wall_facing("north")
        d.add_external_door(g, wall=north_wall["id"], position_along=0.5)
        assert len(g.openings) == 1

    def test_add_external_door_no_wall_raises(self):
        d, g = self._make()
        with pytest.raises(ValueError, match="requires a wall"):
            d.add_external_door(g, position_along=0.5)

    def test_add_external_door_invalid_position(self):
        d, g = self._make()
        north = d.wall_facing("north", level=g)
        with pytest.raises(ValueError, match=r"\[0\.0, 1\.0\]"):
            d.add_external_door(g, wall=north, position_along=1.5)

    def test_add_window(self):
        d, g = self._make()
        south = d.wall_facing("south", level=g)
        oid = d.add_window(g, wall=south, position_along=0.5)
        o = g.openings[0]
        assert o["kind"] == "window"
        assert o["sill_height"] == 90.0

    def test_add_internal_door(self):
        d, g = self._make()
        d.partition(g, (500, 0), (500, 800))
        part = next(w for w in g.walls if not w["is_envelope"])
        oid = d.add_internal_door(g, wall=part["id"], position_along=0.5)
        assert g.openings[0]["kind"] == "door"

    def test_list_openings(self):
        d, g = self._make()
        north = d.wall_facing("north", level=g)
        south = d.wall_facing("south", level=g)
        d.add_external_door(g, wall=north, position_along=0.3)
        d.add_window(g, wall=south, position_along=0.5)
        openings = d.list_openings(g)
        assert len(openings) == 2
        kinds = {o["kind"] for o in openings}
        assert kinds == {"door", "window"}


# ─────────────────────────── Spatial selectors ───────────────────────────────

class TestSpatialSelectors:
    def _make(self):
        d = Designer()
        g = d.add_level("Ground")
        d.envelope(g, width=1000, depth=800)
        d.room(g, polygon=[(0,0),(500,0),(500,400),(0,400)], label="Living Room")
        d.room(g, polygon=[(500,0),(1000,0),(1000,400),(500,400)], label="Kitchen")
        return d, g

    def test_wall_facing_north(self):
        d, g = self._make()
        h = d.wall_facing("north", level=g)
        assert isinstance(h, WallHandle)
        w = g._find_wall(h._id)
        assert w["facing"] == "north"

    def test_wall_facing_south(self):
        d, g = self._make()
        h = d.wall_facing("south", level=g)
        w = g._find_wall(h._id)
        assert w["facing"] == "south"

    def test_wall_facing_east(self):
        d, g = self._make()
        h = d.wall_facing("east", level=g)
        w = g._find_wall(h._id)
        assert w["facing"] == "east"

    def test_wall_facing_west(self):
        d, g = self._make()
        h = d.wall_facing("west", level=g)
        w = g._find_wall(h._id)
        assert w["facing"] == "west"

    def test_wall_facing_invalid_direction(self):
        d, g = self._make()
        with pytest.raises(ValueError, match="Unknown direction"):
            d.wall_facing("northeast", level=g)

    def test_wall_facing_no_envelope(self):
        d = Designer()
        g = d.add_level("Ground")
        with pytest.raises(ValueError, match="No envelope wall"):
            d.wall_facing("north", level=g)

    def test_room_at(self):
        d, g = self._make()
        h = d.room_at(g, x=250, y=200)
        assert isinstance(h, RoomHandle)
        r = g.rooms[0]
        assert h._id == r["id"]

    def test_room_at_right_room(self):
        d, g = self._make()
        h = d.room_at(g, x=750, y=200)
        # Should be Kitchen (right half)
        r = next(x for x in g.rooms if x["id"] == h._id)
        assert r["label"] == "Kitchen"

    def test_room_at_not_found(self):
        d, g = self._make()
        with pytest.raises(ValueError, match="No room found"):
            d.room_at(g, x=2000, y=2000)

    def test_room_named(self):
        d, g = self._make()
        h = d.room_named("Kitchen", level=g)
        assert isinstance(h, RoomHandle)
        r = next(x for x in g.rooms if x["id"] == h._id)
        assert r["label"] == "Kitchen"

    def test_room_named_case_insensitive(self):
        d, g = self._make()
        h = d.room_named("living room", level=g)
        assert h._id is not None

    def test_room_named_not_found(self):
        d, g = self._make()
        with pytest.raises(ValueError, match="No room named"):
            d.room_named("Garage", level=g)


# ─────────────────────────── Furniture ───────────────────────────────────────

class TestFurniture:
    def _make(self):
        d = Designer()
        g = d.add_level("Ground")
        d.envelope(g, width=1000, depth=800)
        return d, g

    def test_place_furniture(self):
        d, g = self._make()
        fid = d.place_furniture(g, catalog_id="SOFA_3_SEATS", x=100, y=200)
        assert len(g.furniture) == 1
        assert g.furniture[0]["catalog_id"] == "SOFA_3_SEATS"

    def test_place_furniture_position(self):
        d, g = self._make()
        d.place_furniture(g, catalog_id="DESK", x=300, y=400, rotation_deg=45)
        f = g.furniture[0]
        assert f["x"] == 300.0
        assert f["y"] == 400.0
        assert f["rotation_deg"] == 45.0

    def test_place_furniture_unknown_id(self):
        d, g = self._make()
        with pytest.raises(ValueError, match="Unknown catalog_id"):
            d.place_furniture(g, catalog_id="FLYING_CARPET", x=0, y=0)

    def test_place_furniture_label(self):
        d, g = self._make()
        d.place_furniture(g, catalog_id="DINING_TABLE_4", x=100, y=100, label="My Table")
        assert g.furniture[0]["label"] == "My Table"

    def test_place_multiple_furniture(self):
        d, g = self._make()
        d.place_furniture(g, catalog_id="SOFA_3_SEATS", x=100, y=200)
        d.place_furniture(g, catalog_id="COFFEE_TABLE", x=200, y=250)
        assert len(g.furniture) == 2

    def test_list_catalog_furniture_all(self):
        d = Designer()
        ids = d.list_catalog_furniture()
        assert len(ids) > 10
        assert "SOFA_3_SEATS" in ids
        assert "KING_BED" in ids

    def test_list_catalog_furniture_category(self):
        d = Designer()
        kitchen = d.list_catalog_furniture("kitchen")
        assert "OVEN" in kitchen
        assert "REFRIGERATOR" in kitchen
        assert "SOFA_3_SEATS" not in kitchen

    def test_list_catalog_furniture_invalid_category(self):
        d = Designer()
        with pytest.raises(ValueError, match="Unknown category"):
            d.list_catalog_furniture("spacecraft")


# ─────────────────────────── Introspection ───────────────────────────────────

class TestIntrospection:
    def _make_complete(self):
        d = Designer(name="Test House")
        g = d.add_level("Ground")
        d.envelope(g, width=1000, depth=800)
        d.room(g, polygon=[(0,0),(1000,0),(1000,800),(0,800)], label="Open Plan")
        d.place_furniture(g, catalog_id="SOFA_3_SEATS", x=100, y=100)
        return d, g

    def test_describe(self):
        d, g = self._make_complete()
        state = d.describe()
        assert state["name"] == "Test House"
        assert state["level_count"] == 1
        assert state["levels"][0]["wall_count"] == 4
        assert state["levels"][0]["room_count"] == 1

    def test_describe_is_json_serialisable(self):
        d, g = self._make_complete()
        state = d.describe()
        dumped = json.dumps(state)
        loaded = json.loads(dumped)
        assert loaded["name"] == "Test House"

    def test_list_walls(self):
        d, g = self._make_complete()
        walls = d.list_walls(g)
        assert len(walls) == 4
        for w in walls:
            assert "id" in w
            assert "start" in w
            assert "end" in w
            assert "thickness" in w
            assert "facing" in w

    def test_list_rooms(self):
        d, g = self._make_complete()
        rooms = d.list_rooms(g)
        assert len(rooms) == 1
        assert rooms[0]["label"] == "Open Plan"
        assert rooms[0]["area_m2"] > 0

    def test_list_openings_empty(self):
        d, g = self._make_complete()
        openings = d.list_openings(g)
        assert openings == []

    def test_list_openings_with_door(self):
        d, g = self._make_complete()
        north = d.wall_facing("north", level=g)
        d.add_external_door(g, wall=north, position_along=0.5)
        openings = d.list_openings(g)
        assert len(openings) == 1

    def test_list_catalog_furniture(self):
        d = Designer()
        ids = d.list_catalog_furniture()
        assert isinstance(ids, list)
        assert len(ids) > 20


# ─────────────────────────── Validate ────────────────────────────────────────

class TestValidate:
    def test_validate_empty_designer(self):
        d = Designer()
        report = d.validate()
        assert report["envelope_closed"] == []
        assert report["orphan_endpoints"] == []
        assert report["wall_count_per_level"] == {}

    def test_validate_no_envelope(self):
        d = Designer()
        d.add_level("Ground")
        report = d.validate()
        assert report["envelope_closed"] == [False]
        assert any("no envelope" in w.lower() for w in report["warnings"])

    def test_validate_complete_house(self):
        d = Designer()
        g = d.add_level("Ground")
        d.envelope(g, width=1000, depth=800)
        d.partition(g, (500, 0), (500, 800))
        d.room(g, polygon=[(0,0),(500,0),(500,800),(0,800)], label="Left")
        d.room(g, polygon=[(500,0),(1000,0),(1000,800),(500,800)], label="Right")

        report = d.validate()
        assert report["envelope_closed"] == [True]
        assert report["orphan_endpoints"] == []
        assert report["rooms_unnamed"] == []
        assert report["wall_count_per_level"] == {"Ground": 5}

    def test_validate_returns_dict_with_all_keys(self):
        d = Designer()
        report = d.validate()
        assert "envelope_closed" in report
        assert "orphan_endpoints" in report
        assert "t_join_failures" in report
        assert "rooms_unnamed" in report
        assert "wall_count_per_level" in report
        assert "warnings" in report

    def test_validate_warns_about_no_rooms(self):
        d = Designer()
        g = d.add_level("Ground")
        d.envelope(g, width=1000, depth=800)
        report = d.validate()
        assert any("no rooms" in w.lower() for w in report["warnings"])

    def test_validate_warns_about_no_furniture(self):
        d = Designer()
        g = d.add_level("Ground")
        d.envelope(g, width=1000, depth=800)
        d.room(g, polygon=[(0,0),(1000,0),(1000,800),(0,800)], label="Hall")
        report = d.validate()
        assert any("no furniture" in w.lower() for w in report["warnings"])

    def test_validate_is_json_serialisable(self):
        d = Designer()
        g = d.add_level("Ground")
        d.envelope(g, width=1000, depth=800)
        report = d.validate()
        dumped = json.dumps(report)
        assert isinstance(dumped, str)


# ─────────────────────────── to_spec / from_spec ─────────────────────────────

class TestSpecRoundTrip:
    def _make_rich(self):
        d = Designer(name="Spec Test")
        g = d.add_level("Ground", floor_height=0, ceiling_height=250)
        d.envelope(g, width=1000, depth=800)
        d.partition(g, (500, 0), (500, 800))
        d.room(g, polygon=[(0,0),(500,0),(500,800),(0,800)], label="Left Room",
               floor_color="#CCBBAA")
        d.room(g, polygon=[(500,0),(1000,0),(1000,800),(500,800)], label="Right Room")
        north = d.wall_facing("north", level=g)
        d.add_external_door(g, wall=north, position_along=0.3, label="Front")
        d.add_window(g, wall=d.wall_facing("south", g), position_along=0.5)
        d.place_furniture(g, catalog_id="SOFA_3_SEATS", x=100, y=200, label="Sofa")
        return d, g

    def test_to_spec_structure(self):
        d, _ = self._make_rich()
        spec = d.to_spec()
        assert spec["spec_version"] == "1.0"
        assert "meta" in spec
        assert "levels" in spec
        assert spec["meta"]["name"] == "Spec Test"

    def test_to_spec_is_json_serialisable(self):
        d, _ = self._make_rich()
        spec = d.to_spec()
        dumped = json.dumps(spec)
        reloaded = json.loads(dumped)
        assert reloaded["meta"]["name"] == "Spec Test"

    def test_from_spec_name(self):
        d, _ = self._make_rich()
        spec = d.to_spec()
        d2 = Designer.from_spec(spec)
        assert d2.name == "Spec Test"

    def test_from_spec_levels(self):
        d, _ = self._make_rich()
        spec = d.to_spec()
        d2 = Designer.from_spec(spec)
        assert len(d2._levels) == len(d._levels)
        assert d2._levels[0].name == "Ground"

    def test_from_spec_walls(self):
        d, g = self._make_rich()
        spec = d.to_spec()
        d2 = Designer.from_spec(spec)
        g2 = d2._levels[0]
        assert len(g2.walls) == len(g.walls)

    def test_from_spec_rooms(self):
        d, g = self._make_rich()
        spec = d.to_spec()
        d2 = Designer.from_spec(spec)
        g2 = d2._levels[0]
        assert len(g2.rooms) == len(g.rooms)
        labels = [r["label"] for r in g2.rooms]
        assert "Left Room" in labels

    def test_from_spec_openings(self):
        d, g = self._make_rich()
        spec = d.to_spec()
        d2 = Designer.from_spec(spec)
        g2 = d2._levels[0]
        assert len(g2.openings) == len(g.openings)

    def test_from_spec_furniture(self):
        d, g = self._make_rich()
        spec = d.to_spec()
        d2 = Designer.from_spec(spec)
        g2 = d2._levels[0]
        assert len(g2.furniture) == len(g.furniture)
        assert g2.furniture[0]["catalog_id"] == "SOFA_3_SEATS"

    def test_from_spec_validate(self):
        d, _ = self._make_rich()
        spec = d.to_spec()
        d2 = Designer.from_spec(spec)
        report = d2.validate()
        assert report["envelope_closed"] == [True]

    def test_from_spec_bad_input(self):
        with pytest.raises(TypeError, match="expects a dict"):
            Designer.from_spec("not a dict")

    def test_from_spec_spatial_selectors_work(self):
        d, g = self._make_rich()
        spec = d.to_spec()
        d2 = Designer.from_spec(spec)
        g2 = d2._levels[0]
        north = d2.wall_facing("north", level=g2)
        assert isinstance(north, WallHandle)

    def test_round_trip_via_json_string(self):
        d, _ = self._make_rich()
        spec_json = json.dumps(d.to_spec())
        spec = json.loads(spec_json)
        d2 = Designer.from_spec(spec)
        report = d2.validate()
        assert report["envelope_closed"] == [True]

    def test_round_trip_via_temp_file(self):
        d, _ = self._make_rich()
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w",
                                         delete=False, encoding="utf-8") as fh:
            json.dump(d.to_spec(), fh)
            tmp_path = fh.name
        try:
            with open(tmp_path, encoding="utf-8") as fh:
                spec = json.load(fh)
            d2 = Designer.from_spec(spec)
            assert d2.name == d.name
        finally:
            os.unlink(tmp_path)


# ─────────────────────────── SH3D export ─────────────────────────────────────

class TestSH3DExport:
    def _make_simple(self):
        d = Designer(name="Export Test")
        g = d.add_level("Ground")
        d.envelope(g, width=800, depth=600)
        d.room(g, polygon=[(0,0),(800,0),(800,600),(0,600)], label="Hall")
        north = d.wall_facing("north", level=g)
        d.add_external_door(g, wall=north, position_along=0.5)
        d.place_furniture(g, catalog_id="SOFA_3_SEATS", x=200, y=300)
        return d

    def test_save_creates_file(self):
        d = self._make_simple()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "Home.sh3d"
            d.save(out)
            assert out.exists()
            assert out.stat().st_size > 0

    def test_save_is_zip(self):
        d = self._make_simple()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "Home.sh3d"
            d.save(out)
            assert zipfile.is_zipfile(out)

    def test_save_contains_home_xml(self):
        d = self._make_simple()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "Home.sh3d"
            d.save(out)
            with zipfile.ZipFile(out) as zf:
                assert "Home.xml" in zf.namelist()

    def test_save_xml_has_walls(self):
        d = self._make_simple()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "Home.sh3d"
            d.save(out)
            with zipfile.ZipFile(out) as zf:
                xml = zf.read("Home.xml").decode("utf-8")
            assert "<wall " in xml

    def test_save_xml_has_room(self):
        d = self._make_simple()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "Home.sh3d"
            d.save(out)
            with zipfile.ZipFile(out) as zf:
                xml = zf.read("Home.xml").decode("utf-8")
            assert "Hall" in xml

    def test_save_xml_has_door(self):
        d = self._make_simple()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "Home.sh3d"
            d.save(out)
            with zipfile.ZipFile(out) as zf:
                xml = zf.read("Home.xml").decode("utf-8")
            assert "doorOrWindow" in xml

    def test_save_xml_has_furniture(self):
        d = self._make_simple()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "Home.sh3d"
            d.save(out)
            with zipfile.ZipFile(out) as zf:
                xml = zf.read("Home.xml").decode("utf-8")
            # save() now goes through save_home() which uses the real SH3D
            # catalog IDs (eTeks#...) rather than the Designer-friendly aliases.
            # SOFA_3_SEATS → eTeks#sofa via _CATALOG_ALIAS.
            assert "eTeks#sofa" in xml

    def test_save_with_render_creates_png(self):
        d = self._make_simple()
        with tempfile.TemporaryDirectory() as tmp:
            out_sh3d = Path(tmp) / "Home.sh3d"
            out_png  = Path(tmp) / "Home.png"
            d.save(out_sh3d, render_png=out_png)
            assert out_png.exists()
            # Check it's a valid PNG (starts with PNG signature)
            sig = out_png.read_bytes()[:8]
            assert sig == b"\x89PNG\r\n\x1a\n"

    def test_save_multilevel(self):
        d = Designer(name="Two Storey")
        g = d.add_level("Ground", floor_height=0)
        f = d.add_level("First",  floor_height=250)
        d.envelope(g, width=800, depth=600)
        d.envelope(f, width=800, depth=600)
        d.room(g, polygon=[(0,0),(800,0),(800,600),(0,600)], label="Ground Hall")
        d.room(f, polygon=[(0,0),(800,0),(800,600),(0,600)], label="Landing")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "TwoStorey.sh3d"
            d.save(out)
            with zipfile.ZipFile(out) as zf:
                xml = zf.read("Home.xml").decode("utf-8")
            assert "<level " in xml
            assert "Ground Hall" in xml
            assert "Landing" in xml


# ─────────────────────────── CLI __main__ ────────────────────────────────────

class TestCLIMain:
    def _make_spec(self) -> dict:
        d = Designer(name="CLI Test")
        g = d.add_level("Ground")
        d.envelope(g, width=800, depth=600)
        d.room(g, polygon=[(0,0),(800,0),(800,600),(0,600)], label="Living")
        return d.to_spec()

    def test_cli_validate_exit_0_on_valid(self, tmp_path):
        spec_path = tmp_path / "spec.json"
        spec_path.write_text(json.dumps(self._make_spec()), encoding="utf-8")

        from cli_anything.sweethome3d.core.__main__ import main
        import pytest
        with pytest.raises(SystemExit) as exc:
            main(["--spec", str(spec_path), "--validate"])
        assert exc.value.code == 0

    def test_cli_describe_exit_0(self, tmp_path):
        spec_path = tmp_path / "spec.json"
        spec_path.write_text(json.dumps(self._make_spec()), encoding="utf-8")

        from cli_anything.sweethome3d.core.__main__ import main
        import pytest
        with pytest.raises(SystemExit) as exc:
            main(["--spec", str(spec_path), "--describe"])
        assert exc.value.code == 0

    def test_cli_out_creates_sh3d(self, tmp_path, capsys):
        spec_path = tmp_path / "spec.json"
        spec_path.write_text(json.dumps(self._make_spec()), encoding="utf-8")
        out_path  = tmp_path / "Out.sh3d"

        from cli_anything.sweethome3d.core.__main__ import main
        main(["--spec", str(spec_path), "--out", str(out_path)])
        assert out_path.exists()

    def test_cli_missing_spec_exits(self):
        from cli_anything.sweethome3d.core.__main__ import main
        with pytest.raises(SystemExit) as exc:
            main(["--out", "Home.sh3d"])
        assert exc.value.code != 0

    def test_cli_nonexistent_spec_exits(self, tmp_path):
        from cli_anything.sweethome3d.core.__main__ import main
        with pytest.raises(SystemExit) as exc:
            main(["--spec", str(tmp_path / "ghost.json"), "--out", str(tmp_path / "out.sh3d")])
        assert exc.value.code != 0
