"""Tests for the model/room-contour fusion layer in pdf_import.

These tests verify that:
  (a) polygons_to_home accepts override_walls and builds a Home from them,
  (b) openings from a synthetic model prediction are still bound to those walls,
  (c) the resulting wall network is clean and stub-free,
  (d) pdf_to_home default wall_source stays 'model' for backward compatibility.

No model, GPU, or PDF is required.
"""
from __future__ import annotations

import math

import pytest

from cli_anything.sweethome3d.core import pdf_import as pi


def _endpoint_distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _assert_no_floating_stubs(walls, tol_cm: float = 1.5):
    """Every wall endpoint must meet at least one other endpoint."""
    endpoints = []
    for w in walls:
        x0, y0, x1, y1, _ = w
        endpoints.append((x0, y0))
        endpoints.append((x1, y1))
    stubs = []
    for i, p_i in enumerate(endpoints):
        if not any(
            j != i and _endpoint_distance(p_i, p_j) <= tol_cm
            for j, p_j in enumerate(endpoints)
        ):
            stubs.append(p_i)
    assert not stubs, f"Floating stub endpoints: {stubs[:5]}\nwalls={walls}"


def _synthetic_clean_walls():
    """Stub-free 2-room box: outer perimeter split at the shared divider."""
    return [
        # outer box, top and bottom split at x=100 so every endpoint meets another
        (0.0, 0.0, 100.0, 0.0, 15.0),    # top-left
        (100.0, 0.0, 200.0, 0.0, 15.0),  # top-right
        (200.0, 0.0, 200.0, 100.0, 15.0),  # right
        (200.0, 100.0, 100.0, 100.0, 15.0),  # bottom-right
        (100.0, 100.0, 0.0, 100.0, 15.0),    # bottom-left
        (0.0, 100.0, 0.0, 0.0, 15.0),    # left
        # internal shared divider
        (100.0, 0.0, 100.0, 100.0, 15.0),
    ]


def _synthetic_pred_openings_only():
    """Model prediction with no walls (model missed them) but two openings."""
    return {
        "w": 400,
        "h": 300,
        "walls": [],
        "openings": [
            # window on the top outer wall, centred at x=150
            {"points": [[130, -5], [170, -5], [170, 10], [130, 10]], "class": 1},
            # door on the shared divider, y=40..70
            {"points": [[95, 40], [105, 40], [105, 70], [95, 70]], "class": 2},
        ],
        "rooms": [],
    }


def test_polygons_to_home_override_walls_stub_free_and_openings_bound():
    """override_walls replaces pred['walls']; openings still bind to them."""
    override_walls = _synthetic_clean_walls()
    pred = _synthetic_pred_openings_only()
    home = pi.polygons_to_home(
        pred, cm_per_px=1.0, min_wall_cm=10, weld_cm=8,
        override_walls=override_walls,
    )

    # Walls should equal the clean override set (after welding/rounding).
    assert len(home.walls) == len(override_walls), (
        f"Expected {len(override_walls)} walls, got {len(home.walls)}: {home.walls}"
    )
    _assert_no_floating_stubs(
        [(w.xStart, w.yStart, w.xEnd, w.yEnd, w.thickness) for w in home.walls],
        tol_cm=2.0,
    )

    # Openings are bound to override walls.
    dw = [f for f in home.furniture if f.kind == "doorOrWindow"]
    assert len(dw) == 2, f"Expected 2 openings, got {len(dw)}"
    assert all(f.boundToWall for f in dw), "All openings should be boundToWall"

    # Window should be on the top wall (y≈0).
    window = next(f for f in dw if "window" in (f.name or "").lower())
    assert abs(window.y) < 5.0, f"Window should sit on top wall, got y={window.y}"

    # Door should be on the shared divider (x≈100).
    door = next(f for f in dw if "door" in (f.name or "").lower())
    assert abs(door.x - 100.0) < 10.0, f"Door should sit on divider, got x={door.x}"


def test_polygons_to_home_override_walls_ignores_pred_walls():
    """When override_walls is supplied, pred['walls'] is ignored entirely."""
    override_walls = [(0.0, 0.0, 100.0, 0.0, 15.0), (100.0, 0.0, 100.0, 80.0, 15.0)]
    pred = {
        "w": 200,
        "h": 200,
        "walls": [
            # These bogus walls should be ignored.
            {"points": [[0, 0], [200, 0], [200, 10], [0, 10]], "class": 2},
        ],
        "openings": [],
        "rooms": [],
    }
    home = pi.polygons_to_home(pred, cm_per_px=1.0, override_walls=override_walls)
    assert len(home.walls) == len(override_walls)
    segs = [(round(w.xStart, 1), round(w.yStart, 1),
             round(w.xEnd, 1), round(w.yEnd, 1)) for w in home.walls]
    # close_corners may shift endpoints by half-thickness when not snapped;
    # just assert the horizontal wall is present and the bogus 200cm wall is gone.
    assert any(s[1] == 0.0 and s[3] == 0.0 for s in segs)
    assert not any(s[2] - s[0] > 150 for s in segs)


def test_pdf_to_home_default_wall_source_is_model():
    """pdf_to_home signature default keeps wall_source='model' for back-compat."""
    import inspect
    sig = inspect.signature(pi.pdf_to_home)
    assert sig.parameters["wall_source"].default == "model", (
        "wall_source default must remain 'model'"
    )


def test_room_contours_guard_skips_without_cv2():
    """If cv2 is absent, room_contours raises ImportError (not a crash)."""
    # The module already imports cv2 via pytest.importorskip in other tests,
    # but we can verify the helper guard directly.
    try:
        import cv2  # noqa: F401
    except ImportError:
        with pytest.raises(ImportError):
            pi._require_cv2()
