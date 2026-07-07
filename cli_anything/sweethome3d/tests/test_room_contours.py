"""
Tests for pdf_import.room_contours — OpenCV room-contour extraction layer.

These tests verify that:
  (a) room_contours correctly identifies rooms in a synthetic multi-room floorplan,
  (b) the returned walls form a CLOSED rectilinear network (every wall endpoint meets
      another wall endpoint — no floating stubs), and
  (c) room polygons are rectilinear.

The synthetic floorplan is built in-memory using PIL/numpy (no external fixture needed).
Tests skip cleanly if OpenCV is not installed (pytest.importorskip).
"""

from __future__ import annotations

import math
import os
import tempfile

import numpy as np
import pytest

# ── Optional import guard — skip whole module if cv2 not available ──
cv2 = pytest.importorskip("cv2", reason="opencv-python-headless not installed")

from PIL import Image

from cli_anything.sweethome3d.core import pdf_import as pi


# ════════════════════════════════════════════════════════════════════════════
# Synthetic floorplan factory
# ════════════════════════════════════════════════════════════════════════════

def _draw_floorplan_two_rooms(out_path: str, size_px: int = 200):
    """
    Draw a two-room floorplan and save as PNG.

    Layout (pixel coords, size_px×size_px):
      - Outer border: 10 px inset from edges, 6 px thick.
      - Vertical internal divider at x = size_px/2, 6 px thick.

    Result: 2 rooms (left + right).
    """
    arr = np.ones((size_px, size_px, 3), dtype=np.uint8) * 255
    wall = 6
    inset = 10
    mid = size_px // 2

    def _fill(x0, y0, x1, y1):
        arr[y0:y1, x0:x1] = (0, 0, 0)

    H = size_px
    W = size_px
    # Outer walls
    _fill(inset, inset, W - inset, inset + wall)           # top
    _fill(inset, H - inset - wall, W - inset, H - inset)   # bottom
    _fill(inset, inset, inset + wall, H - inset)            # left
    _fill(W - inset - wall, inset, W - inset, H - inset)   # right
    # Internal divider
    _fill(mid - wall // 2, inset, mid + wall // 2, H - inset)

    Image.fromarray(arr).save(out_path)
    return out_path


def _draw_floorplan_three_rooms(out_path: str, size_px: int = 300):
    """
    Draw a three-room floorplan: two side-by-side rooms on top, one wide room below.

    Layout:
      - Top-left room:  x ∈ [10, 150),  y ∈ [10, 150)
      - Top-right room: x ∈ [150, 290], y ∈ [10, 150)
      - Bottom room:    x ∈ [10, 290], y ∈ [150, 290]
      - Wall thickness: 6 px
    """
    arr = np.ones((size_px, size_px, 3), dtype=np.uint8) * 255
    wall = 6
    inset = 10
    mid_x = size_px // 2
    mid_y = size_px // 2

    def _fill(x0, y0, x1, y1):
        arr[y0:y1, x0:x1] = (0, 0, 0)

    H = size_px
    W = size_px
    # Outer border
    _fill(inset, inset, W - inset, inset + wall)
    _fill(inset, H - inset - wall, W - inset, H - inset)
    _fill(inset, inset, inset + wall, H - inset)
    _fill(W - inset - wall, inset, W - inset, H - inset)
    # Horizontal internal divider (top vs bottom rooms)
    _fill(inset, mid_y - wall // 2, W - inset, mid_y + wall // 2)
    # Vertical internal divider (top-left vs top-right)
    _fill(mid_x - wall // 2, inset, mid_x + wall // 2, mid_y + wall // 2)

    Image.fromarray(arr).save(out_path)
    return out_path


def _make_temp_png(pixels: np.ndarray) -> str:
    """Save an H×W×3 uint8 array as a temp PNG. Returns the path."""
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    Image.fromarray(pixels.astype(np.uint8), mode="RGB").save(path)
    return path


# ════════════════════════════════════════════════════════════════════════════
# Assertion helpers
# ════════════════════════════════════════════════════════════════════════════

def _endpoint_distance(a, b):
    """Euclidean distance between two (x, y) points."""
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _all_wall_endpoints(walls):
    """Collect all wall endpoints."""
    pts = []
    for w in walls:
        x0, y0, x1, y1, _ = w
        pts.append((x0, y0))
        pts.append((x1, y1))
    return pts


def assert_no_floating_stubs(walls, tol_cm: float = 1.5):
    """
    Assert that every wall endpoint coincides (within ``tol_cm``) with at
    least one OTHER wall endpoint — i.e. no floating stubs.
    """
    endpoints = _all_wall_endpoints(walls)
    stubs = []
    for i, p_i in enumerate(endpoints):
        neighbours = sum(
            1 for j, p_j in enumerate(endpoints) if j != i
            and _endpoint_distance(p_i, p_j) <= tol_cm
        )
        if neighbours == 0:
            stubs.append(p_i)

    assert not stubs, (
        f"Found {len(stubs)} floating stub endpoint(s): {stubs[:5]}\n"
        f"Full walls: {walls}"
    )


def assert_rectilinear_polygon(poly, tol_deg: float = 8.0):
    """
    Assert that a room polygon is approximately rectilinear.
    All interior angles should be ≈ 90° (checked via dot product of edge vectors).
    """
    if len(poly) < 4:
        raise AssertionError(f"Polygon with <4 vertices is degenerate: {poly}")

    for i in range(len(poly)):
        p_prev = poly[i - 1]
        p_curr = poly[i]
        p_next = poly[(i + 1) % len(poly)]

        v1 = (p_curr[0] - p_prev[0], p_curr[1] - p_prev[1])
        v2 = (p_next[0] - p_curr[0], p_next[1] - p_curr[1])

        len1 = math.hypot(*v1)
        len2 = math.hypot(*v2)
        if len1 < 1e-6 or len2 < 1e-6:
            continue

        dot = abs(v1[0] * v2[0] + v1[1] * v2[1]) / (len1 * len2)
        angle_deg = math.degrees(math.acos(min(1.0, dot)))

        # A rectilinear room has corners at ~0° (straight run) or ~90° (turn).
        # We accept either: angle should be near 0° or near 90°.
        near_zero = angle_deg <= tol_deg
        near_ninety = abs(angle_deg - 90.0) <= tol_deg

        assert near_zero or near_ninety, (
            f"Non-rectilinear angle at {poly[i]}: {angle_deg:.1f}° "
            f"(expected ≈0° or ≈90°, within {tol_deg}°). v1={v1}, v2={v2}."
        )


# ════════════════════════════════════════════════════════════════════════════
# Tests — two-room floorplan
# ════════════════════════════════════════════════════════════════════════════

class TestTwoRoomFloorplan:
    """room_contours on a 2-room synthetic floorplan."""

    def test_finds_two_rooms(self, tmp_path):
        png = tmp_path / "2room.png"
        _draw_floorplan_two_rooms(str(png), size_px=200)
        result = pi.room_contours(str(png), cm_per_px=0.5)
        assert len(result["rooms"]) == 2, (
            f"Expected 2 rooms, got {len(result['rooms'])}: {result['rooms']}"
        )

    def test_walls_form_closed_network(self, tmp_path):
        png = tmp_path / "2room.png"
        _draw_floorplan_two_rooms(str(png), size_px=200)
        result = pi.room_contours(str(png), cm_per_px=0.5)
        assert_no_floating_stubs(result["walls"], tol_cm=2.0)

    def test_room_polygons_are_rectilinear(self, tmp_path):
        png = tmp_path / "2room.png"
        _draw_floorplan_two_rooms(str(png), size_px=200)
        result = pi.room_contours(str(png), cm_per_px=0.5)
        for room in result["rooms"]:
            assert_rectilinear_polygon(room)

    def test_walls_reasonable_extent(self, tmp_path):
        """Wall network should span the image (cm_per_px=0.5 on 200px → 100cm)."""
        png = tmp_path / "2room.png"
        _draw_floorplan_two_rooms(str(png), size_px=200)
        result = pi.room_contours(str(png), cm_per_px=0.5)
        all_x = [c for w in result["walls"] for c in (w[0], w[2])]
        all_y = [c for w in result["walls"] for c in (w[1], w[3])]
        assert 80 <= (max(all_x) - min(all_x)) <= 110, "unexpected x extent"
        assert 80 <= (max(all_y) - min(all_y)) <= 110, "unexpected y extent"

    def test_image_size_reported(self, tmp_path):
        png = tmp_path / "2room.png"
        _draw_floorplan_two_rooms(str(png), size_px=200)
        result = pi.room_contours(str(png), cm_per_px=0.5)
        assert result["image_size_px"] == (200, 200)


# ════════════════════════════════════════════════════════════════════════════
# Tests — three-room floorplan
# ════════════════════════════════════════════════════════════════════════════

class TestThreeRoomFloorplan:
    """room_contours on a 3-room synthetic floorplan."""

    def test_finds_three_rooms(self, tmp_path):
        png = tmp_path / "3room.png"
        _draw_floorplan_three_rooms(str(png), size_px=300)
        result = pi.room_contours(str(png), cm_per_px=0.5)
        assert len(result["rooms"]) == 3, (
            f"Expected 3 rooms, got {len(result['rooms'])}: {result['rooms']}"
        )

    def test_walls_form_closed_network(self, tmp_path):
        png = tmp_path / "3room.png"
        _draw_floorplan_three_rooms(str(png), size_px=300)
        result = pi.room_contours(str(png), cm_per_px=0.5)
        assert_no_floating_stubs(result["walls"], tol_cm=2.0)

    def test_room_polygons_are_rectilinear(self, tmp_path):
        png = tmp_path / "3room.png"
        _draw_floorplan_three_rooms(str(png), size_px=300)
        result = pi.room_contours(str(png), cm_per_px=0.5)
        for room in result["rooms"]:
            assert_rectilinear_polygon(room)

    def test_internal_dividers_present(self, tmp_path):
        """3-room plan: outer box (4 walls) + horizontal + vertical dividers.
        walls_from_rooms de-duplicates shared edges: the outer perimeter is
        traced once per room, so each shared edge appears once.  For this
        layout the unique wall segments number 11 (verified empirically).
        """
        png = tmp_path / "3room.png"
        _draw_floorplan_three_rooms(str(png), size_px=300)
        result = pi.room_contours(str(png), cm_per_px=0.5)
        assert 8 <= len(result["walls"]) <= 14, (
            f"Expected 8–14 walls, got {len(result['walls'])}: {result['walls']}"
        )


# ════════════════════════════════════════════════════════════════════════════
# walls_from_rooms unit tests (no image needed)
# ════════════════════════════════════════════════════════════════════════════

class TestWallsFromRooms:
    """Direct unit tests for walls_from_rooms()."""

    def test_single_room_produces_box(self):
        """A single rectilinear room → 4 outer walls."""
        room = [(0, 0), (100, 0), (100, 80), (0, 80)]
        walls = pi.walls_from_rooms([room])
        assert len(walls) == 4
        assert_no_floating_stubs(walls, tol_cm=1.0)

    def test_two_adjacent_rooms(self):
        """Two side-by-side rooms sharing a vertical wall.
        Each room's outer edges plus the one shared edge = 7 unique walls:
        - left room outer: top, bottom, left, right(shared)
        - right room outer: top, bottom, right, left(shared)
        Deduplication leaves: top, bottom, left, right(shared), right_outer = 7.
        """
        left  = [(0, 0), (100, 0), (100, 80), (0, 80)]
        right = [(100, 0), (200, 0), (200, 80), (100, 80)]
        walls = pi.walls_from_rooms([left, right])
        assert len(walls) == 7, f"Expected 7, got {len(walls)}: {walls}"
        assert_no_floating_stubs(walls, tol_cm=1.0)

    def test_three_rooms_closed_network(self):
        """Three rooms forming a top-left + top-right + bottom L-shape.
        walls_from_rooms produces 11 unique walls (empirically verified).
        All endpoints meet another wall endpoint (no stubs).
        """
        top_left  = [(0, 0), (100, 0), (100, 100), (0, 100)]
        top_right = [(100, 0), (200, 0), (200, 100), (100, 100)]
        bottom    = [(0, 100), (200, 100), (200, 200), (0, 200)]
        walls = pi.walls_from_rooms([top_left, top_right, bottom])
        assert 9 <= len(walls) <= 13, f"Expected 9–13, got {len(walls)}: {walls}"
        assert_no_floating_stubs(walls, tol_cm=1.0)

    def test_no_stubs_on_simple_box(self):
        """Four walls forming a box: each endpoint has exactly one neighbour."""
        box = [(10, 10), (90, 10), (90, 70), (10, 70)]
        walls = pi.walls_from_rooms([box])
        assert_no_floating_stubs(walls, tol_cm=1.0)

    def test_degenerate_zero_length_skipped(self):
        """Zero-length edges (repeated points) are silently skipped."""
        degenerate = [(0, 0), (0, 0), (100, 0), (100, 80), (0, 80)]
        walls = pi.walls_from_rooms([degenerate])
        assert len(walls) == 4

    def test_walls_have_correct_format(self):
        """Return type is (x0, y0, x1, y1, thickness) with numeric values."""
        room = [(0, 0), (50, 0), (50, 40), (0, 40)]
        walls = pi.walls_from_rooms([room])
        assert len(walls) == 4
        for w in walls:
            assert len(w) == 5
            x0, y0, x1, y1, thickness = w
            # All values must be numeric (int or float)
            assert isinstance(x0, (int, float))
            assert isinstance(thickness, (int, float))
            assert thickness == 15.0


# ════════════════════════════════════════════════════════════════════════════
# Error / edge-case handling
# ════════════════════════════════════════════════════════════════════════════

class TestRoomContoursEdgeCases:
    """Error handling and edge cases."""

    def test_missing_file_raises_FileNotFoundError(self, tmp_path):
        fake = tmp_path / "does_not_exist.png"
        with pytest.raises(FileNotFoundError):
            pi.room_contours(str(fake), cm_per_px=1.0)

    def test_all_black_image_raises_RuntimeError(self, tmp_path):
        """An all-black image has no interior pixels → no rooms found."""
        arr = np.zeros((100, 100, 3), dtype=np.uint8)
        png_path = _make_temp_png(arr)
        with pytest.raises(RuntimeError, match=r"no interior room pixels|no rooms"):
            pi.room_contours(png_path, cm_per_px=1.0, wall_thresh=200)

    def test_valid_network_at_different_thresholds(self, tmp_path):
        """Both very low and very high thresholds should produce a valid network."""
        # Simple single-room box
        arr = np.ones((100, 100, 3), dtype=np.uint8) * 255
        arr[10:14, :] = 0
        arr[86:90, :] = 0
        arr[:, 10:14] = 0
        arr[:, 86:90] = 0
        png_path = _make_temp_png(arr)

        # wall_thresh=5: very dark threshold
        r_low = pi.room_contours(png_path, cm_per_px=1.0, wall_thresh=5)
        assert len(r_low["rooms"]) >= 1
        assert_no_floating_stubs(r_low["walls"])

        # wall_thresh=254: nearly everything is "wall"
        r_high = pi.room_contours(png_path, cm_per_px=1.0, wall_thresh=254)
        assert len(r_high["rooms"]) >= 1
        assert_no_floating_stubs(r_high["walls"])

    def test_cm_per_px_scales_coordinates(self, tmp_path):
        """Doubling cm_per_px doubles the output wall coordinates."""
        arr = np.ones((100, 100, 3), dtype=np.uint8) * 255
        arr[10:15, :] = 0
        arr[:, 10:15] = 0
        arr[85:90, :] = 0
        arr[:, 85:90] = 0
        png_path = _make_temp_png(arr)

        r_half = pi.room_contours(png_path, cm_per_px=0.5)
        r_full = pi.room_contours(png_path, cm_per_px=1.0)

        def max_extent(walls):
            xs = [c for w in walls for c in (w[0], w[2])]
            return max(xs) - min(xs)

        ratio = max_extent(r_half["walls"]) / max_extent(r_full["walls"])
        assert abs(ratio - 0.5) < 0.05, (
            f"cm_per_px scaling incorrect: ratio={ratio:.3f}, expected 0.5"
        )
