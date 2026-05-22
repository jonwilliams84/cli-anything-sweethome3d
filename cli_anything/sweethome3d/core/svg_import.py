"""Backwards-compatible shim for the SVG importer.

The implementation now lives in :mod:`cli_anything.sweethome3d.core.svg`,
split into ``parse``, ``geometry``, ``align``, ``walls``, ``openings``,
``rooms``, ``spec`` and ``pipeline`` modules. This file preserves the
historical import path so existing callers (CLI, tests, user scripts)
keep working unchanged.

For new code prefer ``from cli_anything.sweethome3d.core.svg import
svg_to_home_multi`` — the underscore-prefixed internals re-exported
here are not part of the public API.
"""

from __future__ import annotations

# Public entry points -------------------------------------------------------
from cli_anything.sweethome3d.core.svg.pipeline import (
    svg_to_home,
    svg_to_home_multi,
    cluster_by_x as _cluster_by_x,
)
from cli_anything.sweethome3d.core.svg.spec import (
    DEFAULT_SPEC as _DEFAULT_SPEC,
    deep_merge as _deep_merge,
    hex_to_argb as _hex_to_argb,
    load_spec,
    COLOR_BRICK as _COLOR_BRICK,
    COLOR_WHITE as _COLOR_WHITE,
    COLOR_RAL_7019 as _COLOR_RAL_7019,
    COLOR_SKY as _COLOR_SKY,
    COLOR_GROUND as _COLOR_GROUND,
    COLOR_OAK as _COLOR_OAK,
    COLOR_CARPET_BEIGE as _COLOR_CARPET_BEIGE,
    COLOR_CARPET_DARK as _COLOR_CARPET_DARK,
)

# Lower-level helpers, re-exported for legacy callers / tests.
from cli_anything.sweethome3d.core.svg.parse import (
    apply as _apply,
    classify_fill as _classify_fill,
    is_wall_fill as _is_wall_fill,
    mul as _mul,
    parse_path as _parse_path,
    parse_transform as _parse_transform,
    style_value as _style_value,
    strip_ns as _strip_ns,
    walk_path as _walk_path,
    IDENT as _IDENT,
    PATH_ARGS as _PATH_ARGS,
)
from cli_anything.sweethome3d.core.svg.geometry import (
    polygon_area as _polygon_area,
    point_in_polygon as _point_in_polygon,
    point_to_segment_dist as _point_to_segment_dist,
)
from cli_anything.sweethome3d.core.svg.align import (
    CORNER_MARKER as _CORNER_MARKER,
    apply_unit_scale as _apply_unit_scale,
    detect_svg_unit_scale as _detect_svg_unit_scale,
    extract_corner_markers as _extract_corner_markers,
    fit_uniform_affine as _fit_uniform_affine,
)
from cli_anything.sweethome3d.core.svg.openings import (
    DOOR_GREEN as _DOOR_GREEN,
    DOOR_MAGENTA as _DOOR_MAGENTA,
    DOOR_RED as _DOOR_RED,
    LIGHT_YELLOW as _LIGHT_YELLOW,
    SKYLIGHT_CYAN as _SKYLIGHT_CYAN,
    WINDOW_BLUE as _WINDOW_BLUE,
    drop_walls_inside_openings as _drop_walls_inside_openings,
    extract_lights as _extract_lights,
    extract_openings as _extract_openings,
    rect_center_local as _rect_center_local,
    snap_opening_to_wall as _snap_opening_to_wall,
)
from cli_anything.sweethome3d.core.svg.rooms import (
    auto_rooms_overlap_labelled as _auto_rooms_overlap_labelled,
    extract_room_labels as _extract_room_labels,
    extract_rooms_from_walls as _extract_rooms_from_walls,
    floor_color_for as _floor_color_for,
)
from cli_anything.sweethome3d.core.svg.walls import (
    Edge as _Edge,
    axis_aligned as _axis_aligned,
    axis_aligned_oriented as _axis_aligned_oriented,
    classify_walls_by_envelope as _classify_walls_by_envelope,
    close_corners as _close_corners,
    collect_wall_segments as _collect_wall_segments,
    collect_wall_subpaths as _collect_wall_subpaths,
    extract_envelope_walls as _extract_envelope_walls,
    extract_walls as _extract_walls,
    grid_snap as _grid_snap,
    join_walls as _join_walls,
    link_wall_endpoints as _link_wall_endpoints,
    overlap as _overlap,
    pair_edges as _pair_edges,
    polygon_walls as _polygon_walls,
    project_segment as _project_segment,
    snap_wall_angles as _snap_wall_angles,
    walls_from_pairs_at_angle as _walls_from_pairs_at_angle,
    weld_wall_endpoints as _weld_wall_endpoints,
)

__all__ = ["svg_to_home", "svg_to_home_multi", "load_spec"]
