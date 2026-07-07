"""Tests for floorplan_eval — the deterministic ruler must itself be trustworthy.

These build synthetic Home objects with KNOWN differences and assert the scorer
reacts correctly: perfect match = 10, position error degrades the score, a
missing/extra object degrades recall/precision, and doors vs windows are scored
in the right bucket.
"""
import copy
import pytest

from cli_anything.sweethome3d.core.model import Home, Wall, PieceOfFurniture, Room, Point
from cli_anything.sweethome3d.core import floorplan_eval as fe


def _opening(name, x, y):
    return PieceOfFurniture(name=name, x=x, y=y, width=80, depth=10, height=200, kind="doorOrWindow")


def _house():
    """A small but complete home: 4 walls (a box), 1 door, 1 window, 1 room."""
    h = Home()
    h.walls += [Wall(0, 0, 400, 0), Wall(400, 0, 400, 300),
                Wall(400, 300, 0, 300), Wall(0, 300, 0, 0)]
    h.furniture += [_opening("Front door", 200, 0), _opening("Kitchen window", 400, 150)]
    h.rooms.append(Room(points=[Point(0, 0), Point(400, 0), Point(400, 300), Point(0, 300)]))
    return h


def test_identical_scores_ten():
    h = _house()
    r = fe.score_homes(h, copy.deepcopy(h))
    assert r["score"] == 10.0
    assert r["walls"]["recall"] == 1.0 and r["walls"]["precision"] == 1.0
    assert r["openings"]["door"]["recall"] == 1.0
    assert r["openings"]["window"]["recall"] == 1.0
    assert r["rooms"]["recall"] == 1.0


def test_extraction_counts():
    h = _house()
    assert len(fe.extract_walls(h)) == 4
    ops = fe.extract_openings(h)
    assert sorted(c for c, _, _ in ops) == ["door", "window"]
    assert len(fe.extract_rooms(h)) == 1


def test_window_vs_door_classification():
    assert fe.opening_class(_opening("Double small window", 0, 0)) == "window"
    assert fe.opening_class(_opening("Gray sliding door", 0, 0)) == "door"
    assert fe.opening_class(_opening("French window", 0, 0)) == "window"


def test_small_wall_shift_keeps_match_but_lowers_score():
    truth = _house()
    pred = copy.deepcopy(truth)
    pred.walls[0] = Wall(0, 20, 400, 20)  # shift one wall 20 cm (within 60 cm tol)
    r = fe.score_homes(truth, pred)
    assert r["walls"]["recall"] == 1.0          # still matched
    assert r["walls"]["mean_err_cm"] > 0        # but error registered
    assert r["walls"]["subscore"] < 1.0
    assert r["score"] < 10.0


def test_large_wall_shift_breaks_match():
    truth = _house()
    pred = copy.deepcopy(truth)
    pred.walls[0] = Wall(0, 500, 400, 500)  # 500 cm away → beyond tol, unmatched
    r = fe.score_homes(truth, pred)
    assert r["walls"]["recall"] == 0.75         # 3 of 4 matched
    assert r["walls"]["matched"] == 3


def test_missing_door_lowers_recall():
    truth = _house()
    pred = copy.deepcopy(truth)
    pred.furniture = [p for p in pred.furniture if "door" not in p.name.lower()]
    r = fe.score_homes(truth, pred)
    assert r["openings"]["door"]["recall"] == 0.0
    assert r["openings"]["window"]["recall"] == 1.0
    assert r["score"] < 10.0


def test_extra_wall_lowers_precision():
    truth = _house()
    pred = copy.deepcopy(truth)
    pred.walls.append(Wall(1000, 1000, 1200, 1000))  # spurious ghost wall far away
    r = fe.score_homes(truth, pred)
    assert r["walls"]["recall"] == 1.0
    assert r["walls"]["precision"] == pytest.approx(4 / 5)


def test_empty_homes_do_not_crash():
    r = fe.score_homes(Home(), Home())
    assert isinstance(r["score"], float)


def test_score_monotonic_with_error():
    truth = _house()
    near, far = copy.deepcopy(truth), copy.deepcopy(truth)
    near.walls[0] = Wall(0, 10, 400, 10)
    far.walls[0] = Wall(0, 40, 400, 40)
    assert fe.score_homes(truth, near)["score"] > fe.score_homes(truth, far)["score"]
