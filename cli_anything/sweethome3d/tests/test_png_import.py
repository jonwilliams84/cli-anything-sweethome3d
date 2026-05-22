"""Unit tests for png_import.png_to_svg.

Two mandatory tests specified in the task brief:
  (a) A synthetic 100×100 PNG with one black wall rect → ≥1 subpath in output.
  (b) A PNG with one red rect inside the wall → <rect fill="#ff0000"/> in SVG.

Additional sanity checks for colour classification, component bbox extraction,
and the Douglas-Peucker simplification helper.
"""

from __future__ import annotations

import io
import os
import tempfile
import xml.etree.ElementTree as ET

import pytest

# ── Optional import guard — skip whole module if PIL / numpy not available ──
PIL = pytest.importorskip("PIL", reason="PIL not installed")
numpy = pytest.importorskip("numpy", reason="numpy not installed")

from PIL import Image
import numpy as np

from cli_anything.sweethome3d.core.png_import import (
    _black_mask,
    _blue_mask,
    _component_bboxes,
    _cyan_mask,
    _dp_simplify,
    _label_components,
    _magenta_mask,
    _marker_green_mask,
    _polygon_area_rc,
    _pure_green_mask,
    _red_mask,
    _to_rgb,
    _yellow_mask,
    png_to_svg,
)


# ════════════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════════════

def _make_png(pixels: np.ndarray) -> str:
    """Save an H×W×3 uint8 array as a temporary PNG file.  Returns the path."""
    img = Image.fromarray(pixels.astype(np.uint8), mode="RGB")
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    img.save(path)
    return path


def _make_output_path() -> str:
    """Return a temporary path for the generated SVG."""
    fd, path = tempfile.mkstemp(suffix=".svg")
    os.close(fd)
    return path


# ════════════════════════════════════════════════════════════════════════════
# Test (a): synthetic 100×100 PNG with one wall rect → ≥1 subpath
# ════════════════════════════════════════════════════════════════════════════

class TestWallSubpath:
    """Task requirement (a): a synthetic PNG with one black wall rect must
    produce at least one <path> subpath in the output SVG."""

    def test_single_wall_rect_produces_subpath(self):
        """100×100 PNG: 10 px thick black border rect → ≥1 wall subpath."""
        pixels = np.ones((100, 100, 3), dtype=np.uint8) * 255  # white background
        # Draw a 10-px thick black border (hollow rectangle)
        pixels[10:90, 10:90] = 255  # interior stays white
        pixels[10:12, 10:90] = 0    # top wall
        pixels[88:90, 10:90] = 0    # bottom wall
        pixels[10:90, 10:12] = 0    # left wall
        pixels[10:90, 88:90] = 0    # right wall

        png_path = _make_png(pixels)
        svg_path = _make_output_path()
        try:
            meta = png_to_svg(png_path, svg_path, cm_per_pixel=1.0)

            # Check meta
            assert meta["width_px"] == 100
            assert meta["height_px"] == 100
            assert meta["walls_extracted"] >= 1, (
                f"Expected ≥1 wall subpath, got {meta['walls_extracted']}"
            )

            # Parse SVG and find path elements
            tree = ET.parse(svg_path)
            root = tree.getroot()
            # Strip namespace if present
            for el in root.iter():
                if "}" in el.tag:
                    el.tag = el.tag.split("}", 1)[1]

            paths = root.findall(".//path")
            assert len(paths) >= 1, "Expected ≥1 <path> in output SVG"

            # The path must have fill-rule="evenodd" and fill="#000000"
            wall_paths = [
                p for p in paths
                if p.get("fill-rule") == "evenodd"
                and p.get("fill") == "#000000"
            ]
            assert wall_paths, (
                "Expected a <path fill-rule='evenodd' fill='#000000'> for walls"
            )

            # The path d attribute must contain at least one M…Z subpath
            d_attr = wall_paths[0].get("d", "")
            import re
            m_count = len(re.findall(r"\bM\b", d_attr))
            assert m_count >= 1, f"Expected ≥1 M command in wall path, got {m_count}"

        finally:
            os.unlink(png_path)
            if os.path.exists(svg_path):
                os.unlink(svg_path)


# ════════════════════════════════════════════════════════════════════════════
# Test (b): PNG with red rect inside wall → <rect fill="#ff0000"/> in SVG
# ════════════════════════════════════════════════════════════════════════════

class TestRedRectOpening:
    """Task requirement (b): a PNG with a red rect inside the wall region
    must produce a <rect fill="#ff0000"/> in the output SVG."""

    def test_red_rect_produces_opening(self):
        """80×80 PNG with black walls + one red rect → red rect in SVG."""
        pixels = np.ones((80, 80, 3), dtype=np.uint8) * 255

        # Black outer wall (10 px thick border)
        pixels[5:75, 5:75] = 255   # interior white
        pixels[5:8, 5:75] = 0      # top
        pixels[72:75, 5:75] = 0    # bottom
        pixels[5:75, 5:8] = 0      # left
        pixels[5:75, 72:75] = 0    # right

        # Red rect in the top wall (external door)
        pixels[5:8, 25:45] = [247, 0, 0]  # red — mimics PNG anti-aliasing

        png_path = _make_png(pixels)
        svg_path = _make_output_path()
        try:
            meta = png_to_svg(png_path, svg_path, cm_per_pixel=1.0)

            assert meta["red_doors"] >= 1, (
                f"Expected ≥1 red door component, got {meta['red_doors']}"
            )

            # Parse SVG
            tree = ET.parse(svg_path)
            root = tree.getroot()
            for el in root.iter():
                if "}" in el.tag:
                    el.tag = el.tag.split("}", 1)[1]

            rects = root.findall(".//rect")
            red_rects = [
                r for r in rects
                if (r.get("fill") or "").lower() in ("#ff0000", "#ff0000")
            ]
            assert red_rects, (
                "Expected ≥1 <rect fill='#ff0000'> in output SVG for red door"
            )

        finally:
            os.unlink(png_path)
            if os.path.exists(svg_path):
                os.unlink(svg_path)


# ════════════════════════════════════════════════════════════════════════════
# Colour mask unit tests
# ════════════════════════════════════════════════════════════════════════════

class TestColourMasks:
    """Verify that each colour mask correctly identifies its target hue."""

    def _single_pixel(self, rgb: tuple[int, int, int]) -> np.ndarray:
        """3×3 image with the given colour in the centre."""
        arr = np.ones((3, 3, 3), dtype=np.uint8) * 255
        arr[1, 1] = rgb
        return arr

    def test_black_mask(self):
        arr = self._single_pixel((0, 0, 0))
        m = _black_mask(arr)
        assert m[1, 1], "Black pixel not detected"
        assert not m[0, 0], "White pixel falsely detected as black"

    def test_red_mask(self):
        arr = self._single_pixel((247, 0, 0))
        assert _red_mask(arr)[1, 1]

    def test_magenta_mask(self):
        arr = self._single_pixel((255, 0, 255))
        assert _magenta_mask(arr)[1, 1]

    def test_blue_mask(self):
        arr = self._single_pixel((0, 0, 255))
        assert _blue_mask(arr)[1, 1]

    def test_cyan_mask(self):
        arr = self._single_pixel((0, 255, 255))
        assert _cyan_mask(arr)[1, 1]

    def test_yellow_mask(self):
        arr = self._single_pixel((255, 255, 0))
        assert _yellow_mask(arr)[1, 1]

    def test_pure_green_mask(self):
        arr = self._single_pixel((0, 255, 0))
        assert _pure_green_mask(arr)[1, 1]

    def test_marker_green_mask(self):
        # #55d400 = (85, 212, 0)
        arr = self._single_pixel((85, 212, 0))
        assert _marker_green_mask(arr)[1, 1]

    def test_white_not_detected(self):
        arr = self._single_pixel((255, 255, 255))
        assert not _black_mask(arr)[1, 1]
        assert not _red_mask(arr)[1, 1]
        assert not _magenta_mask(arr)[1, 1]
        assert not _blue_mask(arr)[1, 1]
        assert not _cyan_mask(arr)[1, 1]
        assert not _yellow_mask(arr)[1, 1]
        assert not _pure_green_mask(arr)[1, 1]
        assert not _marker_green_mask(arr)[1, 1]


# ════════════════════════════════════════════════════════════════════════════
# Component labelling + bbox
# ════════════════════════════════════════════════════════════════════════════

class TestComponentBbox:
    """Verify _component_bboxes correctly labels and bounds connected regions."""

    def test_single_component(self):
        mask = np.zeros((10, 10), dtype=bool)
        mask[2:5, 3:7] = True  # 3×4 = 12 pixels
        bboxes = _component_bboxes(mask, min_area=1)
        assert len(bboxes) == 1
        b = bboxes[0]
        assert b["ymin"] == 2 and b["ymax"] == 4
        assert b["xmin"] == 3 and b["xmax"] == 6
        assert b["area"] == 12

    def test_two_components(self):
        mask = np.zeros((20, 20), dtype=bool)
        mask[1:4, 1:4] = True   # top-left blob
        mask[15:18, 15:18] = True  # bottom-right blob
        bboxes = _component_bboxes(mask, min_area=1)
        assert len(bboxes) == 2

    def test_min_area_filter(self):
        mask = np.zeros((10, 10), dtype=bool)
        mask[0, 0] = True   # single pixel — too small
        mask[2:5, 2:5] = True  # 9 pixels — large enough
        bboxes = _component_bboxes(mask, min_area=5)
        assert len(bboxes) == 1
        assert bboxes[0]["area"] == 9


# ════════════════════════════════════════════════════════════════════════════
# Douglas-Peucker
# ════════════════════════════════════════════════════════════════════════════

class TestDPSimplify:
    """Basic smoke tests for the DP simplification."""

    def test_line_simplifies_to_endpoints(self):
        # Collinear points on a horizontal line should simplify to just 2
        pts = [(0, i * 10) for i in range(10)]  # (row=0, col=0..90)
        result = _dp_simplify(pts, epsilon=1.0)
        assert len(result) == 2
        assert result[0] == pts[0]
        assert result[-1] == pts[-1]

    def test_right_angle_keeps_corner(self):
        # L-shaped path: start → corner → end
        pts = [(0, 0), (0, 10), (0, 50), (10, 50), (20, 50)]
        result = _dp_simplify(pts, epsilon=0.5)
        # The corner at (0,50)→(10,50) should be preserved
        assert len(result) >= 3

    def test_too_few_points_unchanged(self):
        pts = [(0, 0), (5, 5)]
        result = _dp_simplify(pts, epsilon=1.0)
        assert result == pts


# ════════════════════════════════════════════════════════════════════════════
# End-to-end meta fields
# ════════════════════════════════════════════════════════════════════════════

class TestPngToSvgMeta:
    """Verify that png_to_svg returns a complete metadata dict."""

    def test_meta_keys_present(self):
        # Minimal white PNG with a small black rect
        pixels = np.ones((30, 30, 3), dtype=np.uint8) * 255
        pixels[5:25, 5:25] = [0, 0, 0]  # solid black square

        png_path = _make_png(pixels)
        svg_path = _make_output_path()
        try:
            meta = png_to_svg(png_path, svg_path, cm_per_pixel=1.0)
            expected_keys = {
                "width_px", "height_px", "cm_per_pixel",
                "walls_extracted", "openings", "lights", "markers",
                "red_doors", "magenta_doors", "windows",
                "patio_doors", "skylights",
            }
            assert expected_keys <= set(meta.keys()), (
                f"Missing keys: {expected_keys - set(meta.keys())}"
            )
            assert meta["width_px"] == 30
            assert meta["height_px"] == 30
            assert meta["cm_per_pixel"] == 1.0
        finally:
            os.unlink(png_path)
            if os.path.exists(svg_path):
                os.unlink(svg_path)

    def test_scale_propagated_to_svg(self):
        """When cm_per_pixel=2.0, the SVG viewBox should double in size."""
        pixels = np.ones((20, 40, 3), dtype=np.uint8) * 255

        png_path = _make_png(pixels)
        svg_path = _make_output_path()
        try:
            png_to_svg(png_path, svg_path, cm_per_pixel=2.0)
            tree = ET.parse(svg_path)
            root = tree.getroot()
            # Strip ns
            for el in root.iter():
                if "}" in el.tag:
                    el.tag = el.tag.split("}", 1)[1]
            # width should be 40 * 2 = 80, height 20 * 2 = 40
            w_attr = root.get("width", "")
            h_attr = root.get("height", "")
            assert "80" in w_attr, f"Unexpected width: {w_attr}"
            assert "40" in h_attr, f"Unexpected height: {h_attr}"
        finally:
            os.unlink(png_path)
            if os.path.exists(svg_path):
                os.unlink(svg_path)
