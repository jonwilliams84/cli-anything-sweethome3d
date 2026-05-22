"""Focused unit tests for svg_import.py public and internal API."""

from __future__ import annotations

import math
import textwrap
import xml.etree.ElementTree as ET

import pytest

from cli_anything.sweethome3d.core.svg_import import (
    _axis_aligned_oriented,
    _classify_walls_by_envelope,
    _drop_walls_inside_openings,
    _extract_envelope_walls,
    _fit_uniform_affine,
    _grid_snap,
    _snap_opening_to_wall,
    load_spec,
    svg_to_home_multi,
)

# ---------------------------------------------------------------------------
# 1. load_spec – defaults
# ---------------------------------------------------------------------------

def test_load_spec_defaults():
    spec = load_spec(None)
    for section in ("walls", "openings", "rooms", "lights", "environment", "levels", "meta", "alignment"):
        assert section in spec, f"missing section: {section}"
    assert spec["walls"]["external"]["thickness_cm"] == 35
    assert spec["walls"]["internal"]["thickness_cm"] == 14
    assert spec["levels"]["height_cm"] == 240


# ---------------------------------------------------------------------------
# 2. load_spec – partial override
# ---------------------------------------------------------------------------

def test_load_spec_override():
    spec = load_spec({"walls": {"internal": {"thickness_cm": 10}}})
    # Overridden leaf.
    assert spec["walls"]["internal"]["thickness_cm"] == 10
    # Sibling leaf kept from defaults.
    assert spec["walls"]["external"]["thickness_cm"] == 35
    # Deeper defaults survive.
    assert spec["walls"]["height_cm"] == 240


# ---------------------------------------------------------------------------
# 3. _fit_uniform_affine – known similarity transform
# ---------------------------------------------------------------------------

def test_fit_uniform_affine():
    # Transform: scale 2, translate (10, 20)
    s_true, tx_true, ty_true = 2.0, 10.0, 20.0
    src = [(0.0, 0.0), (100.0, 0.0), (50.0, 100.0)]
    dst = [(s_true * x + tx_true, s_true * y + ty_true) for x, y in src]
    s, tx, ty = _fit_uniform_affine(src, dst)
    assert abs(s - s_true) < 1e-9
    assert abs(tx - tx_true) < 1e-9
    assert abs(ty - ty_true) < 1e-9


# ---------------------------------------------------------------------------
# 4. _grid_snap – closes corner gaps
# ---------------------------------------------------------------------------

def test_grid_snap_closes_gaps():
    # An L-shaped corner: one horizontal wall and one vertical wall.
    # Endpoints are offset by 8 cm in the perpendicular direction to simulate
    # the gap that edge-pair extraction leaves before snapping.
    #
    # Ideal corner: H wall at y=100 from x=0..200; V wall at x=200 from y=100..300.
    # We perturb the endpoints slightly:
    h_wall = (0.0, 100.0, 198.0, 102.0, 35.0)   # ends 2 cm short / 2 cm high
    v_wall = (202.0, 98.0, 200.0, 300.0, 35.0)   # starts 2 cm right / 2 cm high

    snapped = _grid_snap([h_wall, v_wall], row_tol=18.0, col_tol=18.0)
    assert len(snapped) == 2

    hw = snapped[0]
    vw = snapped[1]

    # Both walls must now lie on the same canonical row/col grid.
    # The H wall's y1 and y2 should be equal (perfectly horizontal).
    assert abs(hw[1] - hw[3]) < 1e-6, "H wall not axis-aligned after snap"
    # The V wall's x1 and x2 should be equal (perfectly vertical).
    assert abs(vw[0] - vw[2]) < 1e-6, "V wall not axis-aligned after snap"

    # The shared corner: H wall's x-end should match V wall's x-centre and
    # V wall's y-start should match H wall's y-centre.
    h_xe = hw[2]
    v_xc = vw[0]
    assert abs(h_xe - v_xc) < 1e-6, "Corner X coords do not match after grid snap"

    h_yc = hw[1]
    v_ys = vw[1]
    assert abs(h_yc - v_ys) < 1e-6, "Corner Y coords do not match after grid snap"


# ---------------------------------------------------------------------------
# 5. _axis_aligned_oriented – parallel-wall clustering bug
# ---------------------------------------------------------------------------

def test_axis_aligned_oriented_separates_parallel():
    # Two parallel lines at 45°, 20 cm apart in the perpendicular direction.
    # Line A: from (0,0) to (100,100)   → perp ≈ 0
    # Line B: from (14.14, -14.14) to (114.14, 85.86) → perp ≈ 20 cm
    # (shifted by 20/√2 ≈ 14.14 in X, -14.14 in Y so the perpendicular
    #  distance from the origin in the rotated 45° frame is ~20 cm)
    offset = 20.0 / math.sqrt(2)
    segs = [
        (0.0, 0.0, 100.0, 100.0),
        (offset, -offset, 100.0 + offset, 100.0 - offset),
    ]

    # Tight perp tolerance → two separate clusters.
    clusters_tight = _axis_aligned_oriented(
        segs, angle_deg=45.0, angle_tol_deg=5.0, perp_tol_cm=6.0, min_len=1.0
    )
    assert len(clusters_tight) == 2, (
        f"Expected 2 clusters with perp_tol=6, got {len(clusters_tight)}"
    )

    # Loose perp tolerance → one fused cluster.
    clusters_loose = _axis_aligned_oriented(
        segs, angle_deg=45.0, angle_tol_deg=5.0, perp_tol_cm=25.0, min_len=1.0
    )
    assert len(clusters_loose) == 1, (
        f"Expected 1 cluster with perp_tol=25, got {len(clusters_loose)}"
    )


# ---------------------------------------------------------------------------
# 6. _classify_walls_by_envelope
# ---------------------------------------------------------------------------

def test_classify_walls_by_envelope():
    # Outer rectangle 400×300.  tol=25 cm is well inside the 100 cm gap
    # between the internal wall's endpoints and the nearest envelope edge,
    # so the classification is unambiguous.
    outer = [(0.0, 0.0), (400.0, 0.0), (400.0, 300.0), (0.0, 300.0)]

    # 4 outer walls on the envelope edges.
    outer_walls = [
        (0.0,   0.0, 400.0,   0.0, 10.0),   # top edge
        (400.0, 0.0, 400.0, 300.0, 10.0),   # right edge
        (0.0, 300.0, 400.0, 300.0, 10.0),   # bottom edge
        (0.0,   0.0,   0.0, 300.0, 10.0),   # left edge
    ]
    # Internal cross wall: both endpoints are ~100 cm away from the nearest
    # envelope segment, well beyond tol=25 cm → classified as internal.
    internal_wall = (200.0, 100.0, 200.0, 200.0, 10.0)

    walls = outer_walls + [internal_wall]
    result = _classify_walls_by_envelope(walls, outer, tol=25.0)

    assert len(result) == 5
    # First 4 are external → thickness 35
    for i in range(4):
        assert result[i][4] == 35.0, f"Wall {i} should be external (35 cm)"
    # Last one is internal → thickness 14
    assert result[4][4] == 14.0, "Internal wall should be 14 cm"


# ---------------------------------------------------------------------------
# 7. _drop_walls_inside_openings
# ---------------------------------------------------------------------------

def test_drop_walls_inside_openings():
    # Horizontal window centred at (100, 50), width=40, depth=10, angle=0.
    openings = [("window", 100.0, 50.0, 40.0, 10.0, 0.0, "#0000ff")]

    # V wall perpendicular to the window — midpoint at (100, 50) → INSIDE bbox → drop.
    wall_perp = (100.0, 30.0, 100.0, 70.0, 14.0)
    # H wall parallel to the window — midpoint at (100, 50) also inside bbox,
    # but it is PARALLEL (not perpendicular) → must be kept.
    wall_parallel = (80.0, 50.0, 120.0, 50.0, 35.0)
    # V wall outside the bbox entirely → kept regardless.
    wall_outside = (200.0, 30.0, 200.0, 70.0, 14.0)

    result = _drop_walls_inside_openings(
        [wall_perp, wall_parallel, wall_outside], openings, margin=10.0
    )
    result_tuples = [tuple(w) for w in result]

    assert tuple(wall_perp) not in result_tuples, "Perpendicular wall inside opening should be dropped"
    assert tuple(wall_parallel) in result_tuples, "Parallel wall should be kept"
    assert tuple(wall_outside) in result_tuples, "Outside wall should be kept"


# ---------------------------------------------------------------------------
# 8. _snap_opening_to_wall
# ---------------------------------------------------------------------------

def test_snap_opening_to_wall():
    # Horizontal wall at y=100, x from 0 to 300, thickness 35.
    walls = [(0.0, 100.0, 300.0, 100.0, 35.0)]

    # Opening centred 8 cm above the wall centreline, angle=0 (horizontal),
    # width 90 cm.
    cx, cy, angle, opening_width = 150.0, 92.0, 0.0, 90.0
    result = _snap_opening_to_wall(cx, cy, angle, opening_width, walls,
                                    max_perp_distance=60.0)

    assert result is not None, "Opening should snap to the wall"
    snapped_cx, snapped_cy, wall_thickness, wall_angle, wall_length, left_offset, top_offset = result
    # Snapped centre should be ON the wall centreline.
    assert abs(snapped_cy - 100.0) < 1e-6, "Snapped Y should equal wall centreline"
    assert abs(snapped_cx - 150.0) < 1e-6, "Snapped X should equal projected X"
    # Depth returned must equal the wall's thickness.
    assert abs(wall_thickness - 35.0) < 1e-9, "Depth should equal wall thickness"
    # Angle should be 0.0 for a horizontal wall.
    assert abs(wall_angle) < 1e-9, "Wall angle should be 0 for horizontal wall"
    # wall_length should be the full wall length (300 cm).
    assert abs(wall_length - 300.0) < 1e-6, "wall_length should equal wall length"
    # left_offset = u_clamped * L - half_width = 0.5*300 - 45 = 105.
    assert abs(left_offset - 105.0) < 1e-6, "left_offset should be 105 cm"
    # top_offset is always 0.0 for SVG import.
    assert top_offset == 0.0, "top_offset should be 0.0"


# ---------------------------------------------------------------------------
# 9. svg_to_home_multi – minimal 1-floor SVG
# ---------------------------------------------------------------------------

def test_svg_to_home_multi_with_spec(tmp_path):
    # A minimal SVG with one outer rectangle (300×200 cm) drawn as a black
    # path, plus a single green corner-marker rect in the bottom-right corner.
    svg_content = textwrap.dedent("""\
        <?xml version="1.0" encoding="UTF-8"?>
        <svg xmlns="http://www.w3.org/2000/svg" width="300" height="200">
          <!-- Outer building outline as a black-filled rect polygon -->
          <path fill="#000000"
                d="M 10 10 L 290 10 L 290 190 L 10 190 Z
                   M 20 20 L 280 20 L 280 180 L 20 180 Z"/>
          <!-- Green corner marker (bottom-right inner corner) -->
          <rect x="275" y="175" width="10" height="10" fill="#55d400"/>
        </svg>
    """)

    svg_file = tmp_path / "floor.svg"
    svg_file.write_text(svg_content, encoding="utf-8")

    spec = {
        "walls": {
            "extraction": {
                "min_wall_length_cm": 5,
                "axis_tol_cm": 6,
                "thickness_range_cm": [6, 60],
            },
            "join": {"tolerance_cm": 35},
            "grid_snap": {"row_tol_cm": 18, "col_tol_cm": 18},
        }
    }

    home = svg_to_home_multi(
        [("Ground", str(svg_file))],
        spec=spec,
    )

    assert home is not None
    assert len(home.levels) == 1, f"Expected 1 level, got {len(home.levels)}"
    # The rectangular outline (two concentric rectangles as a polygon-with-holes)
    # should yield 4 outer walls (from envelope) plus 0 internal walls (all
    # near-envelope walls are dropped).
    ext_walls = [w for w in home.walls if w.thickness == 35.0]
    int_walls = [w for w in home.walls if w.thickness == 14.0]
    assert len(ext_walls) == 4, (
        f"Expected 4 external walls (35 cm) from rectangle envelope, got {len(ext_walls)}: "
        + str([(w.xStart, w.yStart, w.xEnd, w.yEnd) for w in ext_walls])
    )
    # All external walls must have distinct left/right colours (one side is
    # exterior brick, the other interior plaster).
    for w in ext_walls:
        assert w.leftSideColor != w.rightSideColor, (
            f"External wall should have different inside/outside colours: "
            f"left={w.leftSideColor:#010x} right={w.rightSideColor:#010x}"
        )


# ---------------------------------------------------------------------------
# 10. _extract_envelope_walls — new envelope-tracing function
# ---------------------------------------------------------------------------

def test_extract_envelope_walls_rectangle():
    """A simple 4-vertex rectangle produces 4 walls at external thickness."""
    exterior_color = 0xFFA0522D
    interior_color = 0xFFFFFFFF
    envelope = [(0.0, 0.0), (400.0, 0.0), (400.0, 300.0), (0.0, 300.0)]
    result = _extract_envelope_walls(
        envelope,
        thickness=35.0,
        height=240.0,
        exterior_color=exterior_color,
        interior_color=interior_color,
    )
    assert len(result) == 4, f"Expected 4 envelope walls, got {len(result)}"
    for w in result:
        xs, ys, xe, ye, thick, left_col, right_col = w
        assert thick == 35.0, "Envelope wall thickness must be 35 cm"
        # Each wall should have one exterior and one interior face.
        assert left_col != right_col, "Both sides should have different colours"
        cols = {left_col, right_col}
        assert exterior_color in cols, "Exterior colour missing from wall"
        assert interior_color in cols, "Interior colour missing from wall"


def test_extract_envelope_walls_collinear_merge():
    """Near-collinear consecutive edges are merged into one wall."""
    import math
    tiny_rad = math.radians(0.3)
    p0 = (0.0, 0.0)
    p1 = (200.0, 0.0)
    # p1→p2 is 0.3° off horizontal → should merge with p0→p1
    p2 = (400.0, 200.0 * math.tan(tiny_rad))
    p3 = (200.0, 300.0)
    envelope = [p0, p1, p2, p3]
    result = _extract_envelope_walls(envelope, thickness=35.0, height=240.0)
    # The near-collinear pair (p0→p1 and p1→p2) should merge → ≤ 3 edges.
    assert len(result) <= 3, (
        f"Near-collinear edges not merged: got {len(result)} walls"
    )


def test_extract_envelope_walls_empty():
    """Empty or degenerate polygons return an empty list."""
    assert _extract_envelope_walls([], thickness=35.0, height=240.0) == []
    assert _extract_envelope_walls(
        [(0.0, 0.0), (1.0, 0.0)], thickness=35.0, height=240.0
    ) == []


# ---------------------------------------------------------------------------
# 11. New spec sections — load_spec
# ---------------------------------------------------------------------------

def test_load_spec_has_preferences_section():
    """load_spec returns preferences section with all expected keys."""
    spec = load_spec(None)
    prefs = spec["preferences"]
    for key in ("unit", "language", "currency", "magnetism_enabled",
                "grid_visible", "rulers_visible", "default_font",
                "wall_pattern", "furniture_viewed_from_top",
                "auto_save_delay_minutes", "photo_renderer"):
        assert key in prefs, f"preferences.{key} missing from DEFAULT_SPEC"


def test_load_spec_has_compass_section():
    """load_spec returns compass section with expected keys."""
    spec = load_spec(None)
    comp = spec["compass"]
    for key in ("x", "y", "diameter", "north_direction", "latitude",
                "longitude", "time_zone", "visible"):
        assert key in comp, f"compass.{key} missing from DEFAULT_SPEC"


def test_load_spec_has_print_section():
    """load_spec returns print section with expected keys."""
    spec = load_spec(None)
    prnt = spec["print"]
    for key in ("enabled", "paper_width_mm", "paper_height_mm",
                "paper_orientation", "header_format", "footer_format",
                "plan_scale", "furniture_printed", "plan_printed"):
        assert key in prnt, f"print.{key} missing from DEFAULT_SPEC"


def test_load_spec_has_environment_photo_video():
    """load_spec returns environment.photo and environment.video sub-blocks."""
    spec = load_spec(None)
    env = spec["environment"]
    assert "photo" in env
    assert "video" in env
    assert env["photo"]["width"] == 400
    assert env["video"]["frame_rate"] == 25
    assert env["environment"]["drawing_mode"] == "FILL" if False else env["drawing_mode"] == "FILL"


def test_load_spec_has_walls_baseboard():
    """load_spec returns walls.baseboard sub-block."""
    spec = load_spec(None)
    bb = spec["walls"]["baseboard"]
    assert bb["enabled"] is False
    assert bb["thickness_cm"] == 1.0
    assert bb["height_cm"] == 7.0


def test_load_spec_has_rooms_text_style():
    """load_spec returns rooms.text_style.name and .area sub-blocks."""
    spec = load_spec(None)
    ts = spec["rooms"]["text_style"]
    assert "name" in ts
    assert "area" in ts
    assert ts["name"]["alignment"] == "CENTER"
    assert ts["area"]["font_size"] == 12.0


def test_load_spec_has_furniture_defaults():
    """load_spec returns furniture.defaults sub-block."""
    spec = load_spec(None)
    fd = spec["furniture"]["defaults"]
    assert fd["visible"] is True
    assert fd["movable"] is True
    assert fd["name_visible"] is False
    assert fd["drop_on_top_elevation"] == 1.0


def test_load_spec_has_dimensions_labels():
    """load_spec returns dimensions.text_style and labels sections."""
    spec = load_spec(None)
    assert "dimensions" in spec
    assert "labels" in spec
    assert spec["dimensions"]["text_style"]["font_size"] == 10.0
    assert spec["labels"]["text_style"]["font_size"] == 14.0
    assert "outline_color" in spec["labels"]


# ---------------------------------------------------------------------------
# 12. Enum validation in load_spec
# ---------------------------------------------------------------------------

def test_load_spec_rejects_invalid_unit():
    """Invalid preferences.unit raises ValueError."""
    import pytest as _pytest
    with _pytest.raises(ValueError, match="preferences.unit"):
        load_spec({"preferences": {"unit": "furlongs"}})


def test_load_spec_rejects_invalid_drawing_mode():
    """Invalid environment.drawing_mode raises ValueError."""
    import pytest as _pytest
    with _pytest.raises(ValueError, match="environment.drawing_mode"):
        load_spec({"environment": {"drawing_mode": "WIREFRAME"}})


def test_load_spec_rejects_invalid_photo_aspect_ratio():
    """Invalid environment.photo.aspect_ratio raises ValueError."""
    import pytest as _pytest
    with _pytest.raises(ValueError, match="environment.photo.aspect_ratio"):
        load_spec({"environment": {"photo": {"aspect_ratio": "RATIO_CUSTOM"}}})


def test_load_spec_rejects_invalid_print_orientation():
    """Invalid print.paper_orientation raises ValueError."""
    import pytest as _pytest
    with _pytest.raises(ValueError, match="print.paper_orientation"):
        load_spec({"print": {"paper_orientation": "DIAGONAL"}})


def test_load_spec_rejects_invalid_wall_pattern():
    """Invalid walls.pattern raises ValueError."""
    import pytest as _pytest
    with _pytest.raises(ValueError, match="walls.pattern"):
        load_spec({"walls": {"pattern": "polkaDot"}})


def test_load_spec_accepts_valid_enum_overrides():
    """Valid enum overrides load without error."""
    spec = load_spec({
        "preferences": {"unit": "meter", "wall_pattern": "crossHatch"},
        "environment": {
            "drawing_mode": "FILL_AND_OUTLINE",
            "photo": {"aspect_ratio": "RATIO_16_9"},
            "video": {"aspect_ratio": "RATIO_16_9"},
        },
        "print": {"paper_orientation": "LANDSCAPE"},
    })
    assert spec["preferences"]["unit"] == "meter"
    assert spec["environment"]["drawing_mode"] == "FILL_AND_OUTLINE"
    assert spec["print"]["paper_orientation"] == "LANDSCAPE"


# ---------------------------------------------------------------------------
# 13. Pipeline helpers — new spec fields applied to Home
# ---------------------------------------------------------------------------

def test_svg_to_home_multi_applies_compass(tmp_path):
    """compass spec section is wired onto Home.compass."""
    svg_content = textwrap.dedent("""\
        <?xml version="1.0" encoding="UTF-8"?>
        <svg xmlns="http://www.w3.org/2000/svg" width="300" height="200">
          <path fill="#000000"
                d="M 10 10 L 290 10 L 290 190 L 10 190 Z
                   M 20 20 L 280 20 L 280 180 L 20 180 Z"/>
          <rect x="275" y="175" width="10" height="10" fill="#55d400"/>
        </svg>
    """)
    svg_file = tmp_path / "floor.svg"
    svg_file.write_text(svg_content, encoding="utf-8")

    spec = {
        "compass": {
            "x": 123.0, "y": 456.0, "diameter": 80.0,
            "north_direction": 1.5, "visible": False,
            "time_zone": "Europe/London",
        }
    }
    home = svg_to_home_multi([("Ground", str(svg_file))], spec=spec)
    assert home.compass.x == 123.0
    assert home.compass.y == 456.0
    assert home.compass.diameter == 80.0
    assert abs(home.compass.northDirection - 1.5) < 1e-9
    assert home.compass.visible is False
    assert home.compass.timeZone == "Europe/London"


def test_svg_to_home_multi_applies_preferences(tmp_path):
    """preferences spec section is stored as Home.properties."""
    svg_content = textwrap.dedent("""\
        <?xml version="1.0" encoding="UTF-8"?>
        <svg xmlns="http://www.w3.org/2000/svg" width="300" height="200">
          <path fill="#000000"
                d="M 10 10 L 290 10 L 290 190 L 10 190 Z
                   M 20 20 L 280 20 L 280 180 L 20 180 Z"/>
          <rect x="275" y="175" width="10" height="10" fill="#55d400"/>
        </svg>
    """)
    svg_file = tmp_path / "floor.svg"
    svg_file.write_text(svg_content, encoding="utf-8")

    spec = {
        "preferences": {
            "unit": "meter",
            "magnetism_enabled": False,
            "auto_save_delay_minutes": 5,
            "photo_renderer": "YafarayRenderer",
        }
    }
    home = svg_to_home_multi([("Ground", str(svg_file))], spec=spec)
    assert home.properties.get("extensibleUnit") == "meter"
    assert home.properties.get("magnetismEnabled") == "false"
    # 5 minutes = 300000 ms
    assert home.properties.get("autoSaveDelayForRecovery") == "300000"
    assert home.properties.get("photoRenderer") == "YafarayRenderer"


def test_svg_to_home_multi_applies_environment_photo(tmp_path):
    """environment.photo spec section sets photoWidth/Height/Quality."""
    svg_content = textwrap.dedent("""\
        <?xml version="1.0" encoding="UTF-8"?>
        <svg xmlns="http://www.w3.org/2000/svg" width="300" height="200">
          <path fill="#000000"
                d="M 10 10 L 290 10 L 290 190 L 10 190 Z
                   M 20 20 L 280 20 L 280 180 L 20 180 Z"/>
          <rect x="275" y="175" width="10" height="10" fill="#55d400"/>
        </svg>
    """)
    svg_file = tmp_path / "floor.svg"
    svg_file.write_text(svg_content, encoding="utf-8")

    spec = {
        "environment": {
            "photo": {"width": 1920, "height": 1080, "quality": 2,
                      "aspect_ratio": "RATIO_16_9"},
            "video": {"width": 1280, "frame_rate": 30},
            "drawing_mode": "FILL_AND_OUTLINE",
        }
    }
    home = svg_to_home_multi([("Ground", str(svg_file))], spec=spec)
    assert home.environment.photoWidth == 1920
    assert home.environment.photoHeight == 1080
    assert home.environment.photoQuality == 2
    assert home.environment.photoAspectRatio == "RATIO_16_9"
    assert home.environment.videoWidth == 1280
    assert home.environment.videoFrameRate == 30
    assert home.environment.drawingMode == "FILL_AND_OUTLINE"


def test_svg_to_home_multi_applies_wall_baseboards(tmp_path):
    """walls.baseboard.enabled=True attaches baseboards to all walls."""
    svg_content = textwrap.dedent("""\
        <?xml version="1.0" encoding="UTF-8"?>
        <svg xmlns="http://www.w3.org/2000/svg" width="300" height="200">
          <path fill="#000000"
                d="M 10 10 L 290 10 L 290 190 L 10 190 Z
                   M 20 20 L 280 20 L 280 180 L 20 180 Z"/>
          <rect x="275" y="175" width="10" height="10" fill="#55d400"/>
        </svg>
    """)
    svg_file = tmp_path / "floor.svg"
    svg_file.write_text(svg_content, encoding="utf-8")

    spec = {
        "walls": {
            "baseboard": {
                "enabled": True,
                "thickness_cm": 1.5,
                "height_cm": 8.0,
            }
        }
    }
    home = svg_to_home_multi([("Ground", str(svg_file))], spec=spec)
    # All walls should have baseboards on both sides
    assert len(home.walls) > 0
    for w in home.walls:
        assert w.leftSideBaseboard is not None, "leftSideBaseboard should be set"
        assert w.rightSideBaseboard is not None, "rightSideBaseboard should be set"
        assert abs(w.leftSideBaseboard.thickness - 1.5) < 1e-9
        assert abs(w.leftSideBaseboard.height - 8.0) < 1e-9


def test_svg_to_home_multi_baseboard_disabled_by_default(tmp_path):
    """walls.baseboard.enabled=False (default) leaves walls without baseboards."""
    svg_content = textwrap.dedent("""\
        <?xml version="1.0" encoding="UTF-8"?>
        <svg xmlns="http://www.w3.org/2000/svg" width="300" height="200">
          <path fill="#000000"
                d="M 10 10 L 290 10 L 290 190 L 10 190 Z
                   M 20 20 L 280 20 L 280 180 L 20 180 Z"/>
          <rect x="275" y="175" width="10" height="10" fill="#55d400"/>
        </svg>
    """)
    svg_file = tmp_path / "floor.svg"
    svg_file.write_text(svg_content, encoding="utf-8")

    home = svg_to_home_multi([("Ground", str(svg_file))])
    for w in home.walls:
        assert w.leftSideBaseboard is None, "Default: no baseboards expected"
        assert w.rightSideBaseboard is None


def test_svg_to_home_multi_applies_print_settings(tmp_path):
    """print.enabled=True creates Home.printSettings."""
    svg_content = textwrap.dedent("""\
        <?xml version="1.0" encoding="UTF-8"?>
        <svg xmlns="http://www.w3.org/2000/svg" width="300" height="200">
          <path fill="#000000"
                d="M 10 10 L 290 10 L 290 190 L 10 190 Z
                   M 20 20 L 280 20 L 280 180 L 20 180 Z"/>
          <rect x="275" y="175" width="10" height="10" fill="#55d400"/>
        </svg>
    """)
    svg_file = tmp_path / "floor.svg"
    svg_file.write_text(svg_content, encoding="utf-8")

    spec = {
        "print": {
            "enabled": True,
            "paper_width_mm": 297.0,
            "paper_height_mm": 420.0,
            "paper_orientation": "LANDSCAPE",
            "plan_scale": 0.01,
        }
    }
    home = svg_to_home_multi([("Ground", str(svg_file))], spec=spec)
    assert home.printSettings is not None
    assert abs(home.printSettings.paperWidth - 297.0) < 1e-9
    assert abs(home.printSettings.paperHeight - 420.0) < 1e-9
    assert home.printSettings.paperOrientation == "LANDSCAPE"
    assert abs(home.printSettings.planScale - 0.01) < 1e-9


def test_svg_to_home_multi_print_disabled_by_default(tmp_path):
    """print.enabled=False (default) leaves Home.printSettings as None."""
    svg_content = textwrap.dedent("""\
        <?xml version="1.0" encoding="UTF-8"?>
        <svg xmlns="http://www.w3.org/2000/svg" width="300" height="200">
          <path fill="#000000"
                d="M 10 10 L 290 10 L 290 190 L 10 190 Z
                   M 20 20 L 280 20 L 280 180 L 20 180 Z"/>
          <rect x="275" y="175" width="10" height="10" fill="#55d400"/>
        </svg>
    """)
    svg_file = tmp_path / "floor.svg"
    svg_file.write_text(svg_content, encoding="utf-8")

    home = svg_to_home_multi([("Ground", str(svg_file))])
    assert home.printSettings is None


def test_svg_to_home_multi_applies_new_wall_pattern(tmp_path):
    """walls.new_wall_pattern overrides the wall pattern used for generated walls."""
    svg_content = textwrap.dedent("""\
        <?xml version="1.0" encoding="UTF-8"?>
        <svg xmlns="http://www.w3.org/2000/svg" width="300" height="200">
          <path fill="#000000"
                d="M 10 10 L 290 10 L 290 190 L 10 190 Z
                   M 20 20 L 280 20 L 280 180 L 20 180 Z"/>
          <rect x="275" y="175" width="10" height="10" fill="#55d400"/>
        </svg>
    """)
    svg_file = tmp_path / "floor.svg"
    svg_file.write_text(svg_content, encoding="utf-8")

    spec = {
        "walls": {"new_wall_pattern": "crossHatch"}
    }
    home = svg_to_home_multi([("Ground", str(svg_file))], spec=spec)
    assert len(home.walls) > 0
    for w in home.walls:
        assert w.pattern == "crossHatch", f"Expected crossHatch, got {w.pattern}"
