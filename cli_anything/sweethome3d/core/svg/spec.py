"""Spec defaults, deep-merge, and YAML/JSON loader for the SVG importer.

The default spec is the canonical source of truth for every tunable in
the importer pipeline; user YAML/JSON files override leaves and unknown
keys emit a warning so typos like ``wals.internal.color`` are caught
early. Loaders also tag the merged dict with ``_base_dir`` so relative
SVG paths in ``input.floors`` resolve against the spec file.
"""

from __future__ import annotations

import warnings
from typing import Optional

# ────────────────────────────────────────────────── colour palette
# ARGB ints with alpha=FF baked in. The Home writer preserves alpha
# for walls and environment colours (only the piece-color writer
# forces alpha=FF). 0x00xxxxxx would render fully transparent.
COLOR_BRICK    = 0xFFA0522D   # external wall outside — sienna/brick red-brown
COLOR_WHITE    = 0xFFFFFFFF   # wall plaster (internal walls, internal face of externals)
COLOR_RAL_7019 = 0xFF4D4F47   # grey-brown — windows, external doors, garage
COLOR_SKY      = 0xFFCEEDFD   # pale daytime sky
COLOR_GROUND   = 0xFF7CB342   # grass green
COLOR_OAK      = 0xFF9C7A4D   # warm oak floorboards
COLOR_CARPET_BEIGE = 0xFFD8C6A4  # neutral beige carpet
COLOR_CARPET_DARK  = 0xFF3A3A3D  # dark charcoal/grey carpet

# ────────────────────────────────────────────────── enum value sets
# Used for validation: unknown enum values raise a clear ValueError.

_VALID_UNITS = {
    "centimeter", "millimeter", "meter",
    "inch", "inch_fraction", "inch_decimals", "foot_decimals",
}
_VALID_WALL_PATTERNS = {
    "hatchUp", "hatchDown", "crossHatch",
    "reversedHatchUp", "reversedHatchDown", "reversedCrossHatch",
    "foreground", "background",
}
_VALID_PHOTO_ASPECT_RATIOS = {
    "FREE_RATIO", "VIEW_3D_RATIO", "RATIO_4_3", "RATIO_3_2",
    "RATIO_16_9", "RATIO_2_1", "RATIO_24_10", "SQUARE_RATIO",
}
_VALID_VIDEO_ASPECT_RATIOS = {
    "RATIO_4_3", "RATIO_16_9", "RATIO_24_10",
}
_VALID_DRAWING_MODES = {"FILL", "OUTLINE", "FILL_AND_OUTLINE"}
_VALID_LENS_TYPES = {"PINHOLE", "NORMAL", "FISHEYE", "SPHERICAL"}
_VALID_PRINT_ORIENTATIONS = {"PORTRAIT", "LANDSCAPE", "REVERSE_LANDSCAPE"}
_VALID_TEXT_ALIGNMENTS = {"LEFT", "CENTER", "RIGHT"}


def hex_to_argb(s) -> Optional[int]:
    """Parse '#RRGGBB' / '#AARRGGBB' / int into a 32-bit ARGB integer.

    Returns None for None/empty input. Forces alpha=FF when only 6 hex
    digits are given (the project writer preserves alpha for walls and
    environment, so 6-digit input would otherwise render as transparent).
    """
    if s is None:
        return None
    if isinstance(s, int):
        return s if (s >> 24) & 0xFF else (0xFF << 24) | s
    s = s.strip().lstrip("#")
    if not s:
        return None
    v = int(s, 16)
    if len(s) <= 6:
        v = 0xFF000000 | v
    return v


# Built-in defaults — every leaf in here is overridable by user YAML.
DEFAULT_SPEC: dict = {
    "meta": {"name": None, "output": None, "units": "cm"},
    "input": {"floors": []},   # accepts [{level, svg}, ...] from user spec
    "alignment": {
        "marker_color": "#55d400",
        "anchor": "wall_se_corner",
        "unit_scale": "auto",
    },
    # ── Walls ─────────────────────────────────────────────────────────────────
    "walls": {
        "pattern": "hatchUp",               # plan-view fill pattern for all walls
        "height_cm": 240,                   # default 3D wall height
        "classify": {
            "envelope_tol_cm": 25,
            "external_min_raw_thick_cm": 18,
        },
        "external": {
            "thickness_cm": 35,
            "color_outside": "#A0522D",
            "color_inside":  "#FFFFFF",
            "texture_outside": None,
            "texture_inside":  None,
        },
        "internal": {
            "thickness_cm": 14,
            "color": "#FFFFFF",
            "texture": None,
        },
        "extraction": {
            "min_wall_length_cm": 8,
            "axis_tol_cm": 6,
            "thickness_range_cm": [6, 60],
            "angles_deg": [0, 90, 45, 135],
            "diagonal_angle_tol_deg": 15,
            "snap_diagonal_endpoints_cm": 40,
        },
        "join": {"tolerance_cm": 35, "external_priority": True},
        "grid_snap": {"row_tol_cm": 18, "col_tol_cm": 18},
        "link_endpoints": {"tolerance_cm": 6},
        # ── New: wall baseboard defaults ──────────────────────────────────────
        # Enables skirting boards on all generated walls. Maps to
        # Wall.leftSideBaseboard and Wall.rightSideBaseboard (model.Baseboard).
        "baseboard": {
            "enabled": False,               # set True to attach baseboards to all walls
            "thickness_cm": 1.0,            # baseboard depth / protrusion from wall face (cm)
            "height_cm": 7.0,               # baseboard height above floor (cm)
            "color": None,                  # baseboard colour (#RRGGBB) or null = inherit wall colour
            "texture": None,                # baseboard texture catalog-id or null
        },
        # ── New: separate pattern for newly drawn walls ────────────────────────
        "new_wall_pattern": None,           # null = inherit walls.pattern; set to override new-wall pattern
    },
    # ── Openings (doors / windows) ────────────────────────────────────────────
    "openings": {
        "kinds": {
            "#ff0000": "external_door",
            "#ff00ff": "internal_door",
            "#00ff00": "patio_door",
            "#0000ff": "window",
            "#00ffff": "skylight",
        },
        "catalogs": {
            "external_door": {
                "default": "eTeks#frontDoor",
                "variants": [{"if_width_cm_gte": 120, "catalog": "eTeks#garageDoor"}],
            },
            "internal_door": {"default": "eTeks#doorFrame"},
            "patio_door":   {"default": "eTeks#doubleFrenchWindow126x200"},
            "window": {
                "default": "eTeks#fixedWindow85x123",
                "variants": [{"if_width_cm_gte": 200, "catalog": "eTeks#doubleWindow126x163"}],
            },
            "skylight": {
                "default": "eTeks#texturableBox",
                "height_cm": 4,
                "color": "#80CCEEFF",
                "ceiling_offset_cm": 5,
            },
        },
        "colors": {
            "external_door": "#4D4F47",
            "internal_door": None,
            "patio_door":   "#4D4F47",
            "window":        "#4D4F47",
            "skylight":      "#80CCEEFF",
        },
        "snap": {"max_perp_distance_cm": 60, "drop_inside_opening": True, "drop_margin_cm": 10},
        "defaults": {
            "door_height_cm": 200, "window_height_cm": 120,
            "window_elevation_cm": 100, "bound_to_wall": True,
            "wall_distance_cm": 0,
        },
        # ── New: global sash defaults ──────────────────────────────────────────
        # Applied to doors/windows that have no catalog sash data.
        # Each entry maps to model.Sash. Coordinates are fractions of the opening (0–1).
        # Example: [{x_axis: 0, y_axis: 0.5, width: 1.0, start_angle_deg: 0, end_angle_deg: 90}]
        "sash_defaults": [],                # list of {x_axis, y_axis, width, start_angle_deg, end_angle_deg}
    },
    # ── Lights ────────────────────────────────────────────────────────────────
    "lights": {
        "fill_color": "#ffff00", "catalog": "eTeks#pendantLamp",
        "width_cm": 40, "depth_cm": 40, "height_cm": 20,
        "elevation_below_ceiling_cm": 30, "default_color": "#FFFFE0",
        # ── New: default light source positions ───────────────────────────────
        # Applied to light fixtures whose catalog entry has no built-in sources.
        # Positions are in the model's local coordinate space (0–1 normalised).
        # Example: [{x: 0, y: 0, z: 0.5, color: "#FFFFE0", diameter: 5}]
        "source_defaults": [],              # list of {x, y, z, color, diameter}
    },
    # ── Rooms ─────────────────────────────────────────────────────────────────
    "rooms": {
        "ceiling_color": "#F8F8F4",
        "auto_rooms": True,   # generate closed-loop rooms from wall graph
        "detection": {"min_area_cm2": 5000, "max_vertices": 200,
                       "dedupe_centroid_cm": 10},
        "by_level": {
            "Ground":    {"default_floor": "#9C7A4D", "overrides": {}},
            "1st Floor": {"default_floor": "#D8C6A4",
                            "overrides": {
                                "Master": "#3A3A3D",
                                "Master ensuite": "#3A3A3D",
                                "wardrobe": "#3A3A3D",
                            }},
        },
        # ── New: default text styles for room name and area labels ─────────────
        # Maps to Room.nameStyle and Room.areaStyle (model.TextStyle).
        "text_style": {
            "name": {                        # TextStyle for the room name label
                "font_size": 18.0,          # font size in points
                "font_name": None,          # font family or null (uses SH3D default)
                "bold": False,              # bold text
                "italic": False,            # italic text
                "alignment": "CENTER",      # LEFT | CENTER | RIGHT
            },
            "area": {                        # TextStyle for the area label
                "font_size": 12.0,          # font size in points
                "font_name": None,          # font family or null
                "bold": False,
                "italic": False,
                "alignment": "CENTER",
            },
        },
    },
    # ── Environment ────────────────────────────────────────────────────────────
    "environment": {
        "sky_color": "#CEEDFD",             # sky colour (RRGGBB)
        "ground_color": "#7CB342",          # ground colour (RRGGBB)
        "walls_alpha": 0,                   # wall transparency in 3D: 0=opaque, 1=invisible
        "sky_texture": None,                # sky texture catalog-id or null
        "ground_texture": None,             # ground texture catalog-id or null
        # ── New: extended environment colours and modes ────────────────────────
        "light_color": None,                # ambient sunlight colour (#RRGGBB or null)
        "ceiling_light_color": None,        # ceiling light colour for rendering (#RRGGBB or null)
        "drawing_mode": "FILL",             # how 3D surfaces render: FILL|OUTLINE|FILL_AND_OUTLINE
        "all_levels_visible": False,        # show all levels simultaneously in 3D view
        "observer_camera_elevation_adjusted": True,  # auto-adjust camera Z when navigating between levels
        "background_image_visible_on_ground": False, # project background image onto 3D ground plane
        "subpart_size_under_light": 0,      # accurate-lighting subpart size (cm); 0 = disabled
        # ── New: photo render settings (per-home, stored in <environment>) ──────
        "photo": {
            "width": 400,                   # rendered photo width (pixels)
            "height": 300,                  # rendered photo height (pixels)
            "aspect_ratio": "VIEW_3D_RATIO",  # FREE_RATIO|VIEW_3D_RATIO|RATIO_4_3|RATIO_3_2|RATIO_16_9|RATIO_2_1|RATIO_24_10|SQUARE_RATIO
            "quality": 0,                   # render quality: 0=fast … 3=best (global illumination)
        },
        # ── New: video render settings (per-home, stored in <environment>) ──────
        "video": {
            "width": 320,                   # video frame width (pixels)
            "aspect_ratio": "RATIO_4_3",    # RATIO_4_3 | RATIO_16_9 | RATIO_24_10
            "quality": 0,                   # render quality: 0=fast … 3=best
            "frame_rate": 25,               # output frame rate (fps)
            "speed": 240.0,                 # camera path traversal speed (cm/s)
        },
    },
    # ── Levels ────────────────────────────────────────────────────────────────
    "levels": {"thickness_cm": 12, "height_cm": 240, "ceiling_height_cm": 240},
    # ── Preferences (SH3D File → Preferences dialogue) ────────────────────────
    # These are application-level settings. Since they live outside Home.xml in SH3D,
    # the pipeline stores them as <property> elements on <home> so they travel with
    # the file. SH3D will load them and offer to apply them.
    "preferences": {
        "unit": "centimeter",               # centimeter|millimeter|meter|inch|inch_fraction|inch_decimals|foot_decimals
        "language": "en",                   # ISO 639 code (en, fr, de, es, …)
        "currency": None,                   # ISO 4217 code (EUR, USD, GBP, …) or null to hide prices
        "vat_enabled": False,               # apply VAT to furniture prices
        "vat_percentage": 0.20,             # default VAT rate (e.g. 0.20 = 20%)
        "furniture_catalog_tree": True,     # True=tree-by-category, False=flat searchable list
        "furniture_viewed_from_top": True,  # True=rendered top-view icon, False=catalog PNG icon
        "furniture_icon_size_px": 128,      # top-view icon resolution (px): 128|256|512|1024
        "room_floor_colored": True,         # True=colour/texture fill in plan, False=monochrome grey
        "wall_pattern": "hatchUp",          # display pattern for ALL existing walls in plan view
        "magnetism_enabled": True,          # snap cursor to walls, furniture, grid lines
        "grid_visible": True,               # show background grid in plan view
        "rulers_visible": True,             # show ruler bars along plan view edges
        "default_font": None,               # font family for new labels and dimension text (null=system default)
        "navigation_panel_visible": True,   # show 3D navigation arrow overlay
        "aerial_view_centered": False,      # re-centre aerial camera on selection automatically
        "observer_selected_at_change": True, # select observer camera in plan view when it moves in 3D
        "editing_in_3d_view": False,        # allow direct object editing inside the 3D view
        "auto_save_delay_minutes": 10,      # recovery auto-save interval in minutes (0 = disabled)
        "check_updates": False,             # contact SH3D update server at startup (false = good for CI)
        "photo_renderer": None,             # null = built-in SunFlow; "YafarayRenderer" = YafaRay plugin
    },
    # ── Compass ───────────────────────────────────────────────────────────────
    # Maps to <compass> element in Home.xml (model.Compass).
    # Geographic position is used for sun-position calculations in photo render.
    "compass": {
        "x": 50.0,                          # compass rose centre X in plan (cm)
        "y": 50.0,                          # compass rose centre Y in plan (cm)
        "diameter": 100.0,                  # compass rose diameter (cm)
        "north_direction": 0.0,             # clockwise angle from plan-up to geographic north (rad)
        "latitude": None,                   # geographic latitude (rad); null = not set
        "longitude": None,                  # geographic longitude (rad); null = not set
        "time_zone": None,                  # Java timezone ID, e.g. "Europe/London"; null = not set
        "visible": True,                    # show compass rose in plan view
    },
    # ── Print settings ────────────────────────────────────────────────────────
    # Maps to <print> element in Home.xml (model.Print). All margin values in mm.
    "print": {
        "enabled": False,                   # set True to embed <print> in the Home.xml output
        "paper_width_mm": 210.0,            # paper width (mm); A4 = 210
        "paper_height_mm": 297.0,           # paper height (mm); A4 = 297
        "paper_top_margin_mm": 10.0,        # top margin (mm)
        "paper_left_margin_mm": 10.0,       # left margin (mm)
        "paper_bottom_margin_mm": 10.0,     # bottom margin (mm)
        "paper_right_margin_mm": 10.0,      # right margin (mm)
        "paper_orientation": "PORTRAIT",    # PORTRAIT | LANDSCAPE | REVERSE_LANDSCAPE
        "header_format": None,              # header text format, e.g. "{name}" or null
        "footer_format": None,              # footer text format, e.g. "Page {page}" or null
        "plan_scale": None,                 # print scale factor, e.g. 0.01 = 1:100; null = auto
        "furniture_printed": True,          # include furniture list table in printout
        "plan_printed": True,               # include floor plan view in printout
        "view_3d_printed": False,           # include 3D rendered view in printout
    },
    # ── Dimension line text style ─────────────────────────────────────────────
    # Default TextStyle applied to the length annotation of generated dimension lines.
    # Maps to DimensionLine.lengthStyle (model.TextStyle).
    "dimensions": {
        "text_style": {
            "font_size": 10.0,              # font size in points
            "font_name": None,              # font family or null (uses SH3D default)
            "bold": False,                  # bold text
            "italic": False,                # italic text
            "alignment": "CENTER",          # LEFT | CENTER | RIGHT
        },
    },
    # ── Label text style ──────────────────────────────────────────────────────
    # Default TextStyle and outline for standalone <label> elements.
    # Maps to Label.style (model.TextStyle) and Label.outlineColor.
    "labels": {
        "text_style": {
            "font_size": 14.0,              # font size in points
            "font_name": None,              # font family or null
            "bold": False,                  # bold text
            "italic": False,                # italic text
            "alignment": "CENTER",          # LEFT | CENTER | RIGHT
        },
        "outline_color": None,              # outline colour for label text (#RRGGBB or null)
    },
    # ── Furniture defaults ────────────────────────────────────────────────────
    # Per-piece defaults applied to all generated furniture when not set by catalog.
    # Maps to PieceOfFurniture fields (model.PieceOfFurniture).
    "furniture": {
        "defaults": {
            "visible": True,                # piece is visible in 3D view
            "movable": True,                # piece can be moved interactively in plan
            "name_visible": False,          # show furniture name label in plan view
            "drop_on_top_elevation": 1.0,   # fraction of height for drop-on-top (1.0=sits on top)
        },
    },
}


def deep_merge(base: dict, override) -> dict:
    """Deep-merge ``override`` into ``base``.

    Precedence rules
    ----------------
    * **dict + dict**: merged key-by-key (override wins for present keys;
      missing keys keep the base value).
    * **list-of-dicts + list-of-dicts**: position-merge — for each index,
      a dict-merge runs; if the override is shorter the base's trailing
      items are kept. Designed for catalog ``variants`` so overriding
      the first entry doesn't wipe the rest.
    * **anything else**: override replaces base wholesale (including
      ``None`` overrides and same-type primitives).
    """
    if not isinstance(override, dict):
        return override
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        elif (k in out and isinstance(out[k], list) and isinstance(v, list)
              and out[k] and v and isinstance(out[k][0], dict)
              and isinstance(v[0], dict)):
            merged_list = [deep_merge(out[k][i] if i < len(out[k]) else {}, v[i])
                            for i in range(len(v))]
            for i in range(len(v), len(out[k])):
                merged_list.append(out[k][i])
            out[k] = merged_list
        else:
            out[k] = v
    return out


def _validate_enum(value, valid_set, key_path: str):
    """Raise ValueError if ``value`` is not None and not in ``valid_set``."""
    if value is not None and value not in valid_set:
        raise ValueError(
            f"spec key '{key_path}': invalid value {value!r}. "
            f"Valid values: {sorted(valid_set)}"
        )


def _validate_enums(cfg: dict):
    """Run all enum-constraint checks on a fully-merged spec dict."""
    pref = cfg.get("preferences") or {}
    _validate_enum(pref.get("unit"), _VALID_UNITS, "preferences.unit")
    _validate_enum(pref.get("wall_pattern"), _VALID_WALL_PATTERNS, "preferences.wall_pattern")

    walls = cfg.get("walls") or {}
    _validate_enum(walls.get("pattern"), _VALID_WALL_PATTERNS, "walls.pattern")
    _validate_enum(walls.get("new_wall_pattern"), _VALID_WALL_PATTERNS | {None}, "walls.new_wall_pattern")

    env = cfg.get("environment") or {}
    _validate_enum(env.get("drawing_mode"), _VALID_DRAWING_MODES, "environment.drawing_mode")
    photo = env.get("photo") or {}
    _validate_enum(photo.get("aspect_ratio"), _VALID_PHOTO_ASPECT_RATIOS, "environment.photo.aspect_ratio")
    video = env.get("video") or {}
    _validate_enum(video.get("aspect_ratio"), _VALID_VIDEO_ASPECT_RATIOS, "environment.video.aspect_ratio")

    prnt = cfg.get("print") or {}
    _validate_enum(prnt.get("paper_orientation"), _VALID_PRINT_ORIENTATIONS, "print.paper_orientation")

    for section, key in (
        ("rooms.text_style.name", "alignment"),
        ("rooms.text_style.area", "alignment"),
        ("dimensions.text_style", "alignment"),
        ("labels.text_style", "alignment"),
    ):
        parts = section.split(".")
        node = cfg
        for p in parts:
            node = (node or {}).get(p)
        _validate_enum((node or {}).get(key), _VALID_TEXT_ALIGNMENTS, f"{section}.{key}")


def load_spec(spec) -> dict:
    """Resolve a spec (path / dict / None) to a fully-merged dict.

    ``spec`` may be:
      - ``None``: returns the built-in defaults.
      - ``dict``: merged over defaults.
      - ``str`` path: YAML or JSON file, parsed and merged over defaults.

    When a path is passed, the file's directory is stored as
    ``_base_dir`` so relative SVG paths in ``input.floors`` resolve
    against the spec file rather than the caller's cwd.

    Unknown keys at the top level or one level deep trigger a warning so
    typos like ``wals.internal.color`` get caught at load time.
    Enum-typed keys (unit, drawing_mode, etc.) raise ValueError if given
    an unrecognised value.
    """
    def _validate(node, defaults, prefix=""):
        if not isinstance(node, dict):
            return
        for k, v in node.items():
            full = f"{prefix}.{k}" if prefix else k
            if k not in defaults:
                warnings.warn(f"unknown spec key: {full}")
            elif isinstance(v, dict) and isinstance(defaults.get(k), dict):
                _validate(v, defaults[k], full)

    if spec is None:
        merged = dict(DEFAULT_SPEC)
        _validate_enums(merged)
        return merged
    if isinstance(spec, str):
        import os
        with open(spec, "r", encoding="utf-8") as fh:
            text = fh.read()
        if spec.lower().endswith(".json"):
            import json
            data = json.loads(text)
        else:
            import yaml
            data = yaml.safe_load(text) or {}
        _validate(data, DEFAULT_SPEC)
        merged = deep_merge(DEFAULT_SPEC, data)
        _validate_enums(merged)
        merged["_base_dir"] = os.path.dirname(os.path.abspath(spec))
        return merged
    if isinstance(spec, dict):
        _validate(spec, DEFAULT_SPEC)
        merged = deep_merge(DEFAULT_SPEC, spec)
        _validate_enums(merged)
        return merged
    raise TypeError(
        f"spec must be None, dict, or path string — got {type(spec).__name__}"
    )
