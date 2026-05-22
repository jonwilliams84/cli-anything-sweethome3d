"""Top-level SVG → Home pipeline.

``svg_to_home_multi`` is the spec-driven entry point: one SVG per floor,
green-marker Procrustes alignment, envelope-based wall classification,
named rooms with floor-colour overrides.

``svg_to_home`` is the legacy single-SVG path: detects floor splits by
x-gaps in the wall path and otherwise mirrors the same shape.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from typing import Optional

from cli_anything.sweethome3d.core.environment import set_environment
from cli_anything.sweethome3d.core.furniture import (
    add_door,
    add_light,
    add_piece,
    add_window,
)
from cli_anything.sweethome3d.core.levels import add_level
from cli_anything.sweethome3d.core.model import (
    Baseboard,
    Compass,
    Home,
    LightSource,
    Print,
    Sash,
    TextStyle,
    Texture,
)
from cli_anything.sweethome3d.core.project import new_home
from cli_anything.sweethome3d.core.rooms import add_room
from cli_anything.sweethome3d.core.walls import add_wall

from cli_anything.sweethome3d.core.svg.align import (
    apply_unit_scale,
    detect_svg_unit_scale,
    extract_corner_markers,
    fit_uniform_affine,
)
from cli_anything.sweethome3d.core.svg.geometry import (
    point_in_polygon,
    point_to_segment_dist,
    polygon_area,
)
from cli_anything.sweethome3d.core.svg.openings import (
    drop_walls_inside_openings,
    extract_lights,
    extract_openings,
    snap_opening_to_wall,
)
from cli_anything.sweethome3d.core.svg.parse import strip_ns
from cli_anything.sweethome3d.core.svg.rooms import (
    extract_room_labels,
    extract_rooms_from_walls,
)
from cli_anything.sweethome3d.core.svg.spec import (
    COLOR_BRICK,
    COLOR_GROUND,
    COLOR_OAK,
    COLOR_SKY,
    COLOR_WHITE,
    hex_to_argb,
    load_spec,
)
from cli_anything.sweethome3d.core.svg.walls import (
    classify_walls_by_envelope,
    collect_wall_subpaths,
    extract_envelope_walls,
    extract_walls,
    link_wall_endpoints,
    polygon_walls,
    snap_wall_angles,
    weld_wall_endpoints,
)


def cluster_by_x(walls, openings, lights, *, min_gap: float = 80.0):
    """Split walls into ≤2 clusters on the X axis.

    Used by the legacy ``svg_to_home`` to detect floors drawn
    side-by-side on a single sheet.
    """
    if not walls:
        return []
    x_intervals = []
    for xs, ys, xe, ye, _ in walls:
        x_intervals.append((min(xs, xe), max(xs, xe)))
    x_intervals.sort()
    cur_lo, cur_hi = x_intervals[0]
    clusters = []
    for lo, hi in x_intervals[1:]:
        if lo - cur_hi > min_gap:
            clusters.append((cur_lo, cur_hi))
            cur_lo, cur_hi = lo, hi
        else:
            cur_hi = max(cur_hi, hi)
    clusters.append((cur_lo, cur_hi))
    return clusters


def svg_to_home(svg_path: str,
                 *, name: Optional[str] = None,
                 wall_thickness_range: tuple[float, float] = (10.0, 60.0),
                 wall_height: float = 240.0,
                 level_height: float = 240.0,
                 multi_level: bool = True) -> Home:
    """Legacy single-SVG entry point.

    Splits floors by detecting >250 cm horizontal gaps in the wall
    path, then runs the same pipeline as ``svg_to_home_multi``. Kept
    for back-compat with users who haven't migrated to per-floor SVGs.
    """
    tree = ET.parse(svg_path)
    root = tree.getroot()
    strip_ns(root)

    walls = extract_walls(root, wall_thickness_range=wall_thickness_range)
    openings = extract_openings(root)
    lights = extract_lights(root)
    wall_subpaths = collect_wall_subpaths(root)

    subpath_x = sorted([
        sum(x for x, _ in p) / len(p) for p in wall_subpaths if p
    ])
    cluster_ranges: list[tuple[float, float]] = []
    if subpath_x and multi_level:
        gaps = []
        for i in range(1, len(subpath_x)):
            if subpath_x[i] - subpath_x[i - 1] > 250:
                gaps.append(i)
        cuts = [0] + gaps + [len(subpath_x)]
        for s, e in zip(cuts[:-1], cuts[1:]):
            cluster_ranges.append((subpath_x[s], subpath_x[e - 1]))
    if len(cluster_ranges) < 2:
        cluster_ranges = []

    by_cluster: dict[int, list[list[tuple[float, float]]]] = {}
    for poly in wall_subpaths:
        if not poly:
            continue
        cx = sum(x for x, _ in poly) / len(poly)
        idx = 0
        if cluster_ranges:
            for i, (lo, hi) in enumerate(cluster_ranges):
                if lo - 200 <= cx <= hi + 200:
                    idx = i; break
        by_cluster.setdefault(idx, []).append(poly)

    MAX_ROOM_VERTICES = 20
    MIN_ROOM_AREA = 5000.0
    interiors_by_cluster: dict[int, list[list[tuple[float, float]]]] = {}
    for c_idx, polys in by_cluster.items():
        good = [
            p for p in polys
            if p and len(p) <= MAX_ROOM_VERTICES
            and polygon_area(p) >= MIN_ROOM_AREA
        ]
        deduped: list[list[tuple[float, float]]] = []
        for p in good:
            cx = sum(x for x, _ in p) / len(p)
            cy = sum(y for _, y in p) / len(p)
            area = polygon_area(p)
            dup = False
            for q in deduped:
                qcx = sum(x for x, _ in q) / len(q)
                qcy = sum(y for _, y in q) / len(q)
                qarea = polygon_area(q)
                if (abs(cx - qcx) < 10 and abs(cy - qcy) < 10
                    and abs(area - qarea) / max(area, qarea) < 0.1):
                    dup = True; break
            if not dup:
                deduped.append(p)
        sorted_polys = sorted(deduped, key=polygon_area, reverse=True)
        interiors_by_cluster[c_idx] = sorted_polys[1:]

    if cluster_ranges:
        clusters: list = list(cluster_ranges)
    elif multi_level:
        clusters = list(cluster_by_x(walls, openings, lights))
        if len(clusters) < 2:
            clusters = [None]
    else:
        clusters = [None]

    home = new_home(name=name)
    LEVEL_NAMES = ["Ground", "1st Floor", "2nd Floor", "3rd Floor"]
    levels = []
    for i, _ in enumerate(clusters):
        lvl_name = LEVEL_NAMES[i] if i < len(LEVEL_NAMES) else f"Level {i}"
        lvl = add_level(home, name=lvl_name,
                         elevation=i * level_height, height=level_height)
        levels.append(lvl)

    DOOR_CATALOG = {
        "external_door": "eTeks#frontDoor",
        "internal_door": "eTeks#doorFrame",
        "patio_door": "eTeks#doubleFrenchWindow126x200",
    }

    def cluster_index(x: float) -> int:
        if clusters == [None]:
            return 0
        for i, (lo, hi) in enumerate(clusters):
            if lo - 10 <= x <= hi + 10:
                return i
        return 0

    cluster_anchor: list[tuple[float, float]] = []
    if clusters == [None]:
        cluster_anchor = [(0.0, 0.0)]
    else:
        for lo, hi in clusters:
            xs_here = []
            ys_here = []
            for xs, ys_, xe, ye, _ in walls:
                if lo - 10 <= (xs + xe) / 2 <= hi + 10:
                    xs_here.extend([xs, xe])
                    ys_here.extend([ys_, ye])
            cluster_anchor.append((
                max(xs_here) if xs_here else 0.0,
                max(ys_here) if ys_here else 0.0,
            ))

    for xs, ys, xe, ye, thick in walls:
        i = cluster_index((xs + xe) / 2)
        ax, ay = cluster_anchor[i]
        add_wall(home, xStart=xs - ax, yStart=ys - ay,
                  xEnd=xe - ax, yEnd=ye - ay,
                  thickness=thick, height=wall_height, level=levels[i].id)

    for kind, cx, cy, width, depth, angle, fill in openings:
        i = cluster_index(cx)
        ax, ay = cluster_anchor[i]
        if kind in DOOR_CATALOG:
            add_door(home, name=kind.replace("_", " ").title(),
                      x=cx - ax, y=cy - ay, width=width, depth=depth, height=200,
                      angle=angle, level=levels[i].id,
                      catalogId=DOOR_CATALOG[kind])
        elif kind == "window":
            add_window(home, name="Window",
                        x=cx - ax, y=cy - ay, width=width, depth=depth, height=120,
                        elevation=100, angle=angle, level=levels[i].id)
        elif kind == "skylight":
            add_piece(home, name="Skylight",
                       x=cx - ax, y=cy - ay,
                       width=width, depth=depth, height=4,
                       angle=angle, level=levels[i].id,
                       elevation=wall_height - 5,
                       catalogId="eTeks#texturableBox",
                       color=0x80CCEEFF)

    for cx, cy, _radius in lights:
        i = cluster_index(cx)
        ax, ay = cluster_anchor[i]
        add_light(home, name="Light", x=cx - ax, y=cy - ay,
                   width=40, depth=40, height=20,
                   level=levels[i].id, elevation=wall_height - 30)

    for i, lvl in enumerate(levels):
        ax, ay = cluster_anchor[i] if clusters != [None] else (0.0, 0.0)
        rooms = interiors_by_cluster.get(i, [])
        for room_poly in rooms:
            pts: list[tuple[float, float]] = []
            for x, y in room_poly:
                lx, ly = x - ax, y - ay
                if not pts or (abs(lx - pts[-1][0]) > 0.01
                                or abs(ly - pts[-1][1]) > 0.01):
                    pts.append((lx, ly))
            if len(pts) >= 3:
                add_room(home, pts, level=lvl.id,
                          floorColor=0xF0E8D8, ceilingColor=0xF8F8F4)

    link_wall_endpoints(home)
    return home


def _text_style_from_cfg(node: dict) -> TextStyle:
    """Build a TextStyle dataclass from a spec text_style sub-dict."""
    return TextStyle(
        fontSize=float(node.get("font_size", 14.0)),
        fontName=node.get("font_name"),
        bold=bool(node.get("bold", False)),
        italic=bool(node.get("italic", False)),
        alignment=node.get("alignment", "CENTER"),
    )


def _baseboard_from_cfg(node: dict) -> Baseboard:
    """Build a Baseboard dataclass from a spec walls.baseboard sub-dict."""
    return Baseboard(
        thickness=float(node.get("thickness_cm", 1.0)),
        height=float(node.get("height_cm", 7.0)),
        color=hex_to_argb(node.get("color")),
        texture=None,   # texture plumbing deferred to catalog-lookup layer
    )


def _sash_from_cfg(node: dict) -> Sash:
    """Build a Sash from a spec sash_defaults entry.

    ``start_angle_deg`` / ``end_angle_deg`` are in degrees (user-friendly);
    model.Sash uses radians internally.
    """
    import math as _math
    return Sash(
        xAxis=float(node.get("x_axis", 0.0)),
        yAxis=float(node.get("y_axis", 0.5)),
        width=float(node.get("width", 1.0)),
        startAngle=_math.radians(float(node.get("start_angle_deg", 0.0))),
        endAngle=_math.radians(float(node.get("end_angle_deg", 90.0))),
    )


def _light_source_from_cfg(node: dict) -> LightSource:
    """Build a LightSource from a spec lights.source_defaults entry."""
    return LightSource(
        x=float(node.get("x", 0.0)),
        y=float(node.get("y", 0.0)),
        z=float(node.get("z", 0.5)),
        color=hex_to_argb(node.get("color", "#FFFFE0")) or 0xFFFFFFE0,
        diameter=float(node["diameter"]) if node.get("diameter") is not None else None,
    )


def _apply_preferences(home: Home, pref_cfg: dict) -> None:
    """Store user-preferences as <property> elements on the Home.

    SH3D keeps preferences outside Home.xml (in a Java Preferences node),
    but embedding them as properties lets tooling and SH3D plugins read
    them from the file. The keys mirror the Java persistence-key names
    documented in 05-user-preferences.md §6.
    """
    mapping = {
        "unit":                        ("extensibleUnit", lambda v: v),
        "language":                    ("language",       lambda v: str(v)),
        "currency":                    ("currency",       lambda v: str(v) if v else ""),
        "vat_enabled":                 ("valueAddedTaxEnabled", lambda v: str(v).lower()),
        "vat_percentage":              ("defaultValueAddedTaxPercentage", lambda v: str(v)),
        "furniture_catalog_tree":      ("furnitureCatalogViewedInTree", lambda v: str(v).lower()),
        "furniture_viewed_from_top":   ("furnitureViewedFromTop", lambda v: str(v).lower()),
        "furniture_icon_size_px":      ("furnitureModelIconSize", lambda v: str(int(v))),
        "room_floor_colored":          ("roomFloorColoredOrTextured", lambda v: str(v).lower()),
        "wall_pattern":                ("wallPattern",    lambda v: str(v)),
        "magnetism_enabled":           ("magnetismEnabled", lambda v: str(v).lower()),
        "grid_visible":                ("gridVisible",    lambda v: str(v).lower()),
        "rulers_visible":              ("rulersVisible",  lambda v: str(v).lower()),
        "default_font":                ("defaultFontName", lambda v: str(v) if v else ""),
        "navigation_panel_visible":    ("navigationPanelVisible", lambda v: str(v).lower()),
        "aerial_view_centered":        ("aerialViewCenteredOnSelectionEnabled", lambda v: str(v).lower()),
        "observer_selected_at_change": ("observerCameraSelectedAtChange", lambda v: str(v).lower()),
        "editing_in_3d_view":          ("editingIn3DViewEnabled", lambda v: str(v).lower()),
        "auto_save_delay_minutes":     ("autoSaveDelayForRecovery",
                                        lambda v: str(int(float(v) * 60_000))),
        "check_updates":               ("checkUpdatesEnabled", lambda v: str(v).lower()),
        "photo_renderer":              ("photoRenderer",  lambda v: str(v) if v else ""),
    }
    for spec_key, (pref_key, transform) in mapping.items():
        value = pref_cfg.get(spec_key)
        if value is not None:
            home.properties[pref_key] = transform(value)


def _apply_compass(home: Home, compass_cfg: dict) -> None:
    """Write compass spec fields onto the Home's Compass object."""
    c = home.compass
    c.x = float(compass_cfg.get("x", c.x))
    c.y = float(compass_cfg.get("y", c.y))
    c.diameter = float(compass_cfg.get("diameter", c.diameter))
    c.northDirection = float(compass_cfg.get("north_direction", c.northDirection))
    c.visible = bool(compass_cfg.get("visible", c.visible))
    lat = compass_cfg.get("latitude")
    if lat is not None:
        c.latitude = float(lat)
    lon = compass_cfg.get("longitude")
    if lon is not None:
        c.longitude = float(lon)
    tz = compass_cfg.get("time_zone")
    if tz is not None:
        c.timeZone = str(tz)


def _apply_print(home: Home, print_cfg: dict) -> None:
    """Create and attach a Print settings object if print.enabled is True."""
    if not print_cfg.get("enabled", False):
        return
    home.printSettings = Print(
        paperWidth=float(print_cfg.get("paper_width_mm", 210.0)),
        paperHeight=float(print_cfg.get("paper_height_mm", 297.0)),
        paperTopMargin=float(print_cfg.get("paper_top_margin_mm", 10.0)),
        paperLeftMargin=float(print_cfg.get("paper_left_margin_mm", 10.0)),
        paperBottomMargin=float(print_cfg.get("paper_bottom_margin_mm", 10.0)),
        paperRightMargin=float(print_cfg.get("paper_right_margin_mm", 10.0)),
        paperOrientation=print_cfg.get("paper_orientation", "PORTRAIT"),
        headerFormat=print_cfg.get("header_format"),
        footerFormat=print_cfg.get("footer_format"),
        planScale=print_cfg.get("plan_scale"),
        furniturePrinted=bool(print_cfg.get("furniture_printed", True)),
        planPrinted=bool(print_cfg.get("plan_printed", True)),
        view3DPrinted=bool(print_cfg.get("view_3d_printed", False)),
    )


def _weld_internal_endpoints(
    walls: list[tuple],
    *,
    tolerance: float = 50.0,
) -> list[tuple]:
    """Merge near-coincident internal wall endpoints with a wider tolerance.

    This is a second weld pass applied AFTER the T-junction envelope snap.
    It catches Case-A failures where two internal partition endpoints landed
    within ``tolerance`` cm of each other but were too far apart for the
    initial 2 cm weld in ``weld_wall_endpoints``.

    Only endpoints from *different* walls are merged. Clusters that span
    both ends of the same wall are skipped (would create zero-length walls).
    The cluster centroid is used as the merged coordinate.
    """
    if not walls:
        return list(walls)

    # Build (wall_idx, end_idx, x, y) list
    ep: list[tuple[int, int, float, float]] = []
    for wi, (xs, ys, xe, ye, _t) in enumerate(walls):
        ep.append((wi, 0, xs, ys))
        ep.append((wi, 1, xe, ye))

    n = len(ep)
    parent = list(range(n))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i in range(n):
        wi_a, _, xa, ya = ep[i]
        for j in range(i + 1, n):
            wi_b, _, xb, yb = ep[j]
            if wi_a == wi_b:
                continue
            if math.hypot(xa - xb, ya - yb) <= tolerance:
                union(i, j)

    clusters: dict[int, list[int]] = {}
    for idx in range(n):
        clusters.setdefault(find(idx), []).append(idx)

    target: dict[int, tuple[float, float]] = {}
    for _root, members in clusters.items():
        wall_ends: dict[int, set[int]] = {}
        for m in members:
            wi, ei, _, _ = ep[m]
            wall_ends.setdefault(wi, set()).add(ei)
        if any(len(ends) == 2 for ends in wall_ends.values()):
            for m in members:
                _, _, xm, ym = ep[m]
                target[m] = (xm, ym)
        else:
            cx = sum(ep[m][2] for m in members) / len(members)
            cy = sum(ep[m][3] for m in members) / len(members)
            for m in members:
                target[m] = (cx, cy)

    out_walls = [list(w) for w in walls]
    for idx, (wi, ei, _, _) in enumerate(ep):
        tx, ty = target[idx]
        if ei == 0:
            out_walls[wi][0] = tx
            out_walls[wi][1] = ty
        else:
            out_walls[wi][2] = tx
            out_walls[wi][3] = ty

    return [
        tuple(w) for w in out_walls
        if math.hypot(w[2] - w[0], w[3] - w[1]) > 1.0
    ]


def _raycast_extend(
    walls: list[tuple],
    env_walls: list[tuple],
    *,
    max_extend_cm: float = 120.0,
    free_ep_tol: float = 2.0,
    env_snap_tol: float = 25.0,
) -> list[tuple]:
    """Extend floating wall endpoints along their wall's own axis until they
    hit another wall (internal or envelope).

    An endpoint is "free" (floating) when no other endpoint lies within
    ``free_ep_tol`` cm of it AND the endpoint is not already within
    ``env_snap_tol`` cm of the envelope (the Case-D corner snap may have
    placed it close to but not exactly on the envelope).  For each free
    endpoint, a ray is cast from that point in the wall's forward and
    backward axis directions.  The first hit on any other wall segment body
    within ``max_extend_cm`` is used as the new endpoint position (Case C).

    Only the shorter of forward/backward is used; if neither hits within
    the budget the endpoint is left as-is (truly orphan — logged to stderr).
    """
    import sys

    all_segs = list(walls) + list(env_walls)

    def _is_free(wi: int, ei: int, pts: list[tuple]) -> bool:
        px = pts[wi][ei * 2]
        py = pts[wi][ei * 2 + 1]
        for wj, w in enumerate(pts):
            if wj == wi:
                continue
            for ej in range(2):
                qx = w[ej * 2]
                qy = w[ej * 2 + 1]
                if math.hypot(px - qx, py - qy) <= free_ep_tol:
                    return False
        # Check if it's within env_snap_tol of the envelope (incl. corners).
        # Endpoints snapped to near-envelope positions by Case-D should not
        # be extended further by the ray-cast pass.
        for xs2, ys2, xe2, ye2, _t2 in env_walls:
            ddx, ddy = xe2 - xs2, ye2 - ys2
            L2 = ddx * ddx + ddy * ddy
            if L2 < 1e-9:
                continue
            t2 = ((px - xs2) * ddx + (py - ys2) * ddy) / L2
            t2c = max(0.0, min(1.0, t2))
            qx2, qy2 = xs2 + t2c * ddx, ys2 + t2c * ddy
            if math.hypot(px - qx2, py - qy2) <= env_snap_tol:
                return False
        return True

    def _ray_hit(ox: float, oy: float, dx: float, dy: float,
                 skip_wi: int, max_dist: float) -> tuple[float, float] | None:
        """Cast a ray from (ox,oy) in direction (dx,dy); return closest
        intersection with any wall segment within max_dist, or None."""
        best_dist = max_dist
        best_pt: tuple[float, float] | None = None
        L_ray = math.hypot(dx, dy)
        if L_ray < 1e-9:
            return None
        rdx, rdy = dx / L_ray, dy / L_ray

        for wj, seg in enumerate(all_segs):
            if wj == skip_wi:
                continue
            xs2, ys2, xe2, ye2 = seg[0], seg[1], seg[2], seg[3]
            sdx, sdy = xe2 - xs2, ye2 - ys2
            # Solve: (ox + t*rdx, oy + t*rdy) = (xs2 + s*sdx, ys2 + s*sdy)
            denom = rdx * sdy - rdy * sdx
            if abs(denom) < 1e-9:
                continue  # parallel
            fx, fy = xs2 - ox, ys2 - oy
            t_ray = (fx * sdy - fy * sdx) / denom
            s_seg = (fx * rdy - fy * rdx) / denom
            if t_ray < free_ep_tol or t_ray > best_dist:
                continue
            if s_seg < -0.01 or s_seg > 1.01:
                continue
            best_dist = t_ray
            best_pt = (ox + t_ray * rdx, oy + t_ray * rdy)
        return best_pt

    walls_list = [list(w) for w in walls]
    # Use tuples for read-only lookups inside _is_free
    walls_tup = [tuple(w) for w in walls_list]

    for wi, w in enumerate(walls_list):
        for ei in range(2):
            if not _is_free(wi, ei, walls_tup):
                continue
            px = w[ei * 2]
            py = w[ei * 2 + 1]
            # Wall direction (from start to end)
            wdx = w[2] - w[0]
            wdy = w[3] - w[1]
            wlen = math.hypot(wdx, wdy)
            if wlen < 1e-6:
                continue
            # ei==0 → we're at the start, extend backward (negative direction)
            # ei==1 → we're at the end, extend forward (positive direction)
            fwd = (wdx / wlen, wdy / wlen) if ei == 1 else (-wdx / wlen, -wdy / wlen)

            hit = _ray_hit(px, py, fwd[0], fwd[1], wi, max_extend_cm)
            if hit is not None:
                walls_list[wi][ei * 2]     = hit[0]
                walls_list[wi][ei * 2 + 1] = hit[1]
                # Refresh the lookup tuple after mutation
                walls_tup[wi] = tuple(walls_list[wi])
            else:
                print(
                    f"  truly-orphan endpoint wall[{wi}][{ei}]="
                    f"({px:.1f},{py:.1f})",
                    file=sys.stderr,
                )

    return [
        tuple(w) for w in walls_list
        if math.hypot(w[2] - w[0], w[3] - w[1]) > 1.0
    ]


def svg_to_home_multi(svg_files=None,
                       *, name: Optional[str] = None,
                       wall_height: float = 240.0,
                       level_height: float = 240.0,
                       wall_thickness_range: tuple[float, float] = (10.0, 60.0),
                       scales: Optional[list[float]] = None,
                       spec=None) -> Home:
    """Build a Home with one level per supplied SVG file.

    ``svg_files`` is an iterable of ``(level_name, svg_path)`` pairs
    (or just paths; default names ``"Ground"``, ``"1st Floor"``...).
    If ``svg_files`` is None, the floors come from ``spec.input.floors``.

    Each SVG is parsed independently; green-marker Procrustes aligns
    non-canonical floors onto the first floor's coords. Walls are
    classified external/internal by position on the building envelope.
    Rooms are named via the SVG's ``<text>`` labels and coloured via
    ``rooms.by_level.<level>.overrides``.
    """
    DEFAULT_NAMES = ["Ground", "1st Floor", "2nd Floor", "3rd Floor"]

    cfg = load_spec(spec)

    if svg_files is None:
        floors = (cfg.get("input") or {}).get("floors") or []
        if not floors:
            raise ValueError(
                "svg_files=None requires spec.input.floors to be set"
            )
        base_dir = cfg.get("_base_dir") or ""
        import os.path
        svg_files = [
            (f.get("level"),
             os.path.join(base_dir, f.get("svg"))
             if base_dir and not os.path.isabs(f.get("svg"))
             else f.get("svg"))
            for f in floors
        ]
    if name is None:
        name = (cfg.get("meta") or {}).get("name")

    pairs: list[tuple[str, str]] = []
    for i, item in enumerate(svg_files):
        if isinstance(item, str):
            pairs.append((DEFAULT_NAMES[i] if i < len(DEFAULT_NAMES) else f"Level {i}", item))
        else:
            pairs.append(tuple(item))

    home = new_home(name=name)

    # Resolve overridable values from the spec.
    walls_cfg = cfg["walls"]
    ext_cfg, int_cfg = walls_cfg["external"], walls_cfg["internal"]
    col_outside_ext = hex_to_argb(ext_cfg["color_outside"]) or COLOR_BRICK
    col_inside_ext  = hex_to_argb(ext_cfg["color_inside"])  or COLOR_WHITE
    col_internal    = hex_to_argb(int_cfg["color"])         or COLOR_WHITE
    envelope_tol    = float(walls_cfg["classify"]["envelope_tol_cm"])
    ext_min_raw     = float(walls_cfg["classify"]["external_min_raw_thick_cm"])
    # New: effective wall pattern (new_wall_pattern overrides pattern when set)
    _new_wp = walls_cfg.get("new_wall_pattern")
    wall_pattern = _new_wp if _new_wp is not None else walls_cfg.get("pattern", "hatchUp")

    op_cfg = cfg["openings"]
    op_catalogs = op_cfg["catalogs"]
    op_color_by_kind = {k: hex_to_argb(v) for k, v in op_cfg["colors"].items()}
    # New: global sash defaults for doors/windows without catalog sash data
    sash_defaults = [_sash_from_cfg(s) for s in (op_cfg.get("sash_defaults") or [])]

    lights_cfg = cfg["lights"]
    # New: default light sources for fixtures without catalog source data
    light_source_defaults = [
        _light_source_from_cfg(ls) for ls in (lights_cfg.get("source_defaults") or [])
    ]

    rooms_cfg = cfg["rooms"]
    ceiling_col = hex_to_argb(rooms_cfg["ceiling_color"]) or 0xFFF8F8F4

    # New: furniture defaults
    furn_defaults = (cfg.get("furniture") or {}).get("defaults") or {}
    furn_visible       = bool(furn_defaults.get("visible", True))
    furn_movable       = bool(furn_defaults.get("movable", True))
    furn_name_visible  = bool(furn_defaults.get("name_visible", False))
    furn_drop_top_elev = float(furn_defaults.get("drop_on_top_elevation", 1.0))

    def pick_catalog(kind: str, width: float) -> tuple[str, str]:
        family = "window" if kind in ("window", "skylight") else "door"
        node = op_catalogs.get(kind) or {}
        cat = node.get("default", "")
        for variant in (node.get("variants") or []):
            thresh = variant.get("if_width_cm_gte")
            if thresh is not None and width >= float(thresh):
                cat = variant.get("catalog", cat)
        return cat, family

    def opening_color(kind: str) -> Optional[int]:
        return op_color_by_kind.get(kind)

    def floor_color_for(name_str: str, lvl_name: str) -> int:
        node = rooms_cfg["by_level"].get(lvl_name)
        if not node:
            return COLOR_OAK
        overrides = node.get("overrides") or {}
        for k, v in overrides.items():
            if k.lower() == (name_str or "").lower():
                col = hex_to_argb(v)
                if col is not None:
                    return col
        return hex_to_argb(node.get("default_floor")) or COLOR_OAK

    # First pass: extract green markers per SVG so we can fit each floor
    # onto the canonical (first floor's) marker set.
    parsed_roots: list[tuple[ET.Element,
                              list[tuple[float, float]],
                              list[tuple[float, float, float, float]]]] = []
    canonical_centres: Optional[list[tuple[float, float]]] = None
    for i, (lvl_name, svg_path) in enumerate(pairs):
        tree = ET.parse(svg_path)
        root = tree.getroot()
        strip_ns(root)
        unit_scale = (scales[i] if scales and i < len(scales)
                      else detect_svg_unit_scale(root))
        apply_unit_scale(root, unit_scale)
        markers = extract_corner_markers(root)
        centres_raw = [((m[0] + m[2]) / 2, (m[1] + m[3]) / 2) for m in markers]
        centres = sorted(centres_raw, key=lambda c: (c[1], c[0]))
        if canonical_centres is None and centres:
            canonical_centres = centres
        parsed_roots.append((root, centres, markers))

    # Second pass: apply the Procrustes fit + run the full extraction
    # pipeline per floor.
    extracted: list[tuple[
        str, list, list, list, list[list[tuple[float, float]]], list
    ]] = []
    for i, (lvl_name, svg_path) in enumerate(pairs):
        root, centres, _orig_markers = parsed_roots[i]
        if (canonical_centres and centres
                and len(centres) == len(canonical_centres)
                and len(centres) >= 1
                and centres != canonical_centres):
            s, tx, ty = fit_uniform_affine(centres, canonical_centres)
            existing = root.get("transform", "")
            root.set("transform",
                       (f"matrix({s} 0 0 {s} {tx} {ty}) {existing}").strip())

        walls = extract_walls(root, wall_thickness_range=wall_thickness_range,
                              internal_thickness=float(int_cfg["thickness_cm"]))
        walls = snap_wall_angles(walls)
        openings = extract_openings(root)
        walls = drop_walls_inside_openings(walls, openings)
        lights = extract_lights(root)
        subpaths = collect_wall_subpaths(root)
        labels = extract_room_labels(root)

        outer_envelope = max(subpaths, key=polygon_area) if subpaths else None

        # Drop internal walls whose midpoint is within envelope_tol of any
        # envelope edge — these are the inner faces of external walls and
        # will be replaced by envelope-traced walls (extract_envelope_walls).
        if outer_envelope and len(outer_envelope) >= 2:
            env_segs = [
                (outer_envelope[k], outer_envelope[(k + 1) % len(outer_envelope)])
                for k in range(len(outer_envelope))
            ]
            def _near_envelope(xs, ys, xe, ye):
                mx, my = (xs + xe) / 2.0, (ys + ye) / 2.0
                for (ex1, ey1), (ex2, ey2) in env_segs:
                    if point_to_segment_dist(mx, my, ex1, ey1, ex2, ey2) <= envelope_tol:
                        return True
                return False
            walls = [
                (xs, ys, xe, ye, t)
                for xs, ys, xe, ye, t in walls
                if not _near_envelope(xs, ys, xe, ye)
            ]

        # Keep this floor if there are internal walls OR an envelope polygon
        # (the envelope alone will provide the external walls).
        if not walls and outer_envelope is None:
            continue

        # Interior subpaths (everything except the outer envelope) are the
        # SVG-drawn room polygons used as seeds for the floor regions.
        interior_subpaths = [
            sp for sp in subpaths
            if sp is not outer_envelope and len(sp) >= 3
            and polygon_area(sp) >= 5000.0
        ]

        extracted.append((lvl_name, walls, openings, lights, labels,
                            outer_envelope, interior_subpaths))

    if not extracted:
        return home

    for i, (lvl_name, walls, openings, lights, labels, outer_env,
             interior_subpaths) in enumerate(extracted):
        # Anchor: use the outermost bounding coordinates across both internal
        # walls and the envelope polygon so the origin is consistent.
        xs_all = [v for w in walls for v in (w[0], w[2])]
        ys_all = [v for w in walls for v in (w[1], w[3])]
        if outer_env:
            xs_all += [p[0] for p in outer_env]
            ys_all += [p[1] for p in outer_env]
        if not xs_all:
            # Degenerate — no walls and no envelope; skip this floor.
            continue
        ax, ay = max(xs_all), max(ys_all)

        lvl = add_level(home, name=lvl_name,
                         elevation=i * level_height, height=level_height)

        # Compute envelope wall tuples FIRST so we can T-join internal wall
        # endpoints onto envelope wall bodies before adding anything to the home.
        env_wall_tuples: list[tuple] = []
        if outer_env is not None:
            env_wall_tuples = extract_envelope_walls(
                outer_env,
                level_id=lvl.id,
                thickness=float(ext_cfg["thickness_cm"]),
                height=wall_height,
                exterior_color=col_outside_ext,
                interior_color=col_inside_ext,
            )

        # --- T-junction resolution -------------------------------------------
        # Internals frequently end ~½·external_thickness short of the envelope
        # centreline (the SVG draws partitions touching the INNER face of the
        # external wall, which sat ~10-20 cm inboard of the new 35 cm envelope
        # centreline).  Project any internal endpoint within T_JOIN_TOL cm of
        # an envelope wall body onto that wall's centreline.  Internals that
        # cluster on the same floating point are projected together so a whole
        # T-junction snaps cleanly even when several partitions share the end.
        T_JOIN_TOL = 30.0  # cm — covers ½ of a 35cm wall + drift
        # Additional tolerance for snapping to the nearest point on an envelope
        # segment when the projection falls just beyond the segment's endpoint
        # (i.e. the internal wall aims at a corner rather than the body).
        CORNER_SNAP_TOL = 25.0  # cm

        env_5: list[tuple] = [
            (xs, ys, xe, ye, thick)
            for xs, ys, xe, ye, thick, _lc, _rc in env_wall_tuples
        ]

        # Pre-compute envelope corner set for Case-D corner snap.
        # (used as fallback when the unclamped projection falls outside [0,1])
        env_corners: list[tuple[float, float]] = []
        for xs2, ys2, xe2, ye2, _t2 in env_5:
            env_corners.append((xs2, ys2))
            env_corners.append((xe2, ye2))
        # De-duplicate corners (many are shared between adjacent envelope walls).
        _seen_corners: set[tuple[int, int]] = set()
        _unique_corners: list[tuple[float, float]] = []
        for _ecx, _ecy in env_corners:
            _key = (round(_ecx), round(_ecy))
            if _key not in _seen_corners:
                _seen_corners.add(_key)
                _unique_corners.append((_ecx, _ecy))
        env_corners = _unique_corners

        # Cluster internal endpoints (1cm tolerance) and project each cluster
        # to the nearest envelope wall body if within T_JOIN_TOL.
        walls_list = [list(w) for w in walls]
        endpoint_refs: list[tuple[int, int]] = []  # (wall_idx, end_idx 0|1)
        endpoints: list[tuple[float, float]] = []
        for wi, w in enumerate(walls_list):
            endpoints.append((w[0], w[1])); endpoint_refs.append((wi, 0))
            endpoints.append((w[2], w[3])); endpoint_refs.append((wi, 1))

        # Union-find clustering by COINCIDENT_TOL
        COINCIDENT_TOL = 1.5
        parent = list(range(len(endpoints)))
        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i
        def union(i, j):
            ri, rj = find(i), find(j)
            if ri != rj: parent[ri] = rj
        for i in range(len(endpoints)):
            for j in range(i + 1, len(endpoints)):
                if math.hypot(endpoints[i][0] - endpoints[j][0],
                               endpoints[i][1] - endpoints[j][1]) <= COINCIDENT_TOL:
                    union(i, j)

        # Group cluster -> list of endpoint indices
        clusters: dict[int, list[int]] = {}
        for i in range(len(endpoints)):
            clusters.setdefault(find(i), []).append(i)

        n_t_joined = 0
        n_floating = 0
        for cluster_indices in clusters.values():
            cx = sum(endpoints[i][0] for i in cluster_indices) / len(cluster_indices)
            cy = sum(endpoints[i][1] for i in cluster_indices) / len(cluster_indices)
            # Find nearest envelope wall body (t strictly within [0, 1])
            best_dist = T_JOIN_TOL
            best_proj: tuple[float, float] | None = None
            for xs2, ys2, xe2, ye2, _t2 in env_5:
                ddx, ddy = xe2 - xs2, ye2 - ys2
                L2sq = ddx * ddx + ddy * ddy
                if L2sq < 1e-9: continue
                t2 = ((cx - xs2) * ddx + (cy - ys2) * ddy) / L2sq
                if t2 < 0.0 or t2 > 1.0: continue
                qx2, qy2 = xs2 + t2 * ddx, ys2 + t2 * ddy
                d = math.hypot(cx - qx2, cy - qy2)
                if d < best_dist:
                    # Skip if the cluster is ALREADY on this envelope wall body
                    if d < 0.5: continue
                    best_dist = d
                    best_proj = (qx2, qy2)

            # Case D: projection fell just beyond a segment endpoint (t slightly
            # outside [0, 1]).  Find the nearest point on the FULL envelope
            # polygon (clamped projection onto each segment) within
            # CORNER_SNAP_TOL.  Using the clamped projection ensures the snap
            # target is always a real point ON the envelope (at a corner or body),
            # which is required for SH3D room-face traversal to close properly.
            if best_proj is None:
                for xs2, ys2, xe2, ye2, _t2 in env_5:
                    ddx, ddy = xe2 - xs2, ye2 - ys2
                    L2sq = ddx * ddx + ddy * ddy
                    if L2sq < 1e-9: continue
                    t2 = ((cx - xs2) * ddx + (cy - ys2) * ddy) / L2sq
                    t2c = max(0.0, min(1.0, t2))
                    qx2, qy2 = xs2 + t2c * ddx, ys2 + t2c * ddy
                    d = math.hypot(cx - qx2, cy - qy2)
                    if d < 0.5 or d >= CORNER_SNAP_TOL:
                        continue
                    if d >= best_dist:
                        continue
                    best_dist = d
                    best_proj = (qx2, qy2)

            if best_proj is not None:
                for idx in cluster_indices:
                    wi, ei = endpoint_refs[idx]
                    walls_list[wi][ei * 2]     = best_proj[0]
                    walls_list[wi][ei * 2 + 1] = best_proj[1]
                    n_t_joined += 1
            elif best_dist > T_JOIN_TOL - 0.01:
                # Not near any envelope wall AND not within reach
                # Check if this cluster is alone (no other internal endpoint nearby) -> floating
                nearby_internals = 0
                for j in range(len(endpoints)):
                    if find(j) == find(cluster_indices[0]): continue
                    if math.hypot(endpoints[j][0] - cx, endpoints[j][1] - cy) < COINCIDENT_TOL + 0.5:
                        nearby_internals += 1
                if nearby_internals == 0 and len(cluster_indices) == 1:
                    n_floating += 1

        walls = [tuple(w) for w in walls_list
                 if math.hypot(w[2] - w[0], w[3] - w[1]) > 1.0]

        # --- Post-T-join weld: snap remaining internal-to-internal near-misses ---
        # After T-join some diagonal/angled partition endpoints may still float
        # within ~50 cm of another internal endpoint (too far for the initial
        # weld_wall_endpoints pass but reachable after T-join repositioning).
        # Run a second weld pass with a wider tolerance.
        INTERNAL_WELD_TOL = 50.0  # cm — Case A fix
        walls = _weld_internal_endpoints(walls, tolerance=INTERNAL_WELD_TOL)

        # --- Ray-cast extension for truly-orphan endpoints -------------------
        # For any endpoint still floating (not within 2 cm of another endpoint
        # and not within 2 cm of an envelope segment), cast a ray along the
        # wall's own axis in both directions and extend to the first hit on any
        # other wall within MAX_EXTEND_CM.
        MAX_EXTEND_CM = 120.0  # cm — Case C fix
        walls = _raycast_extend(walls, env_5, max_extend_cm=MAX_EXTEND_CM,
                                 env_snap_tol=CORNER_SNAP_TOL)

        # --- Drop walls whose endpoints are STILL both truly orphan ----------
        # After every snap pass, any wall still floating in mid-air is a
        # spurious artifact (long ghost lines past the building outline).
        # A wall is dropped only if BOTH its endpoints are floating w.r.t.
        # every OTHER wall (self-match excluded) and every envelope segment.
        def _ep_anchored(px, py, skip_idx):
            for k, ow in enumerate(walls):
                if k == skip_idx: continue
                if math.hypot(px - ow[0], py - ow[1]) < 3.0: return True
                if math.hypot(px - ow[2], py - ow[3]) < 3.0: return True
                ddx, ddy = ow[2] - ow[0], ow[3] - ow[1]
                L2 = ddx*ddx + ddy*ddy
                if L2 < 1: continue
                t = ((px - ow[0])*ddx + (py - ow[1])*ddy) / L2
                if 0 < t < 1:
                    qx, qy = ow[0] + t*ddx, ow[1] + t*ddy
                    if math.hypot(px - qx, py - qy) < 3.0: return True
            for ow in env_5:
                ddx, ddy = ow[2] - ow[0], ow[3] - ow[1]
                L2 = ddx*ddx + ddy*ddy
                if L2 < 1: continue
                t = ((px - ow[0])*ddx + (py - ow[1])*ddy) / L2
                t = max(0.0, min(1.0, t))
                qx, qy = ow[0] + t*ddx, ow[1] + t*ddy
                if math.hypot(px - qx, py - qy) < 3.0: return True
            return False
        kept = []
        n_dropped = 0
        for wi, w in enumerate(walls):
            xs_, ys_, xe_, ye_, t_ = w
            if (_ep_anchored(xs_, ys_, wi)
                    or _ep_anchored(xe_, ye_, wi)):
                kept.append(w)
            else:
                n_dropped += 1
        walls = kept

        import sys
        print(f't-junctions resolved: {n_t_joined}  floating endpoints: {n_floating}  '
              f'orphan walls dropped: {n_dropped}',
              file=sys.stderr)

        # Add internal walls (all extracted walls are 14 cm after the
        # envelope-drop step above).
        for xs, ys, xe, ye, thick in walls:
            add_wall(home, xStart=xs - ax, yStart=ys - ay,
                      xEnd=xe - ax, yEnd=ye - ay,
                      thickness=thick, height=wall_height, level=lvl.id,
                      leftSideColor=col_internal, rightSideColor=col_internal,
                      pattern=wall_pattern)

        # Add external envelope walls.
        for xs, ys, xe, ye, thick, left_col, right_col in env_wall_tuples:
            add_wall(home, xStart=xs - ax, yStart=ys - ay,
                      xEnd=xe - ax, yEnd=ye - ay,
                      thickness=thick, height=wall_height, level=lvl.id,
                      leftSideColor=left_col, rightSideColor=right_col,
                      pattern=wall_pattern)

        # Build a combined wall list (internal + envelope) for opening snapping.
        # Envelope tuples have 7 fields; trim to the 5 that snap_opening_to_wall expects.
        all_walls_for_snap = list(walls) + env_5

        for kind, cx, cy, width, depth, angle, _fill in openings:
            snapped = False
            wall_length = None
            left_offset = None
            top_offset = None
            if kind != "skylight":
                snap = snap_opening_to_wall(cx, cy, angle, width, all_walls_for_snap)
                if snap is not None:
                    cx, cy, depth, angle, wall_length, left_offset, top_offset = snap
                    snapped = True
                    # Make openings slightly thicker than the host wall (1 cm
                    # protrusion each side) so cuts render cleanly with no
                    # hairline mismatch at the wall faces.
                    depth = depth + 2.0
                else:
                    # Explicit unbind so SH3D doesn't load with bind=True but no
                    # host wall.  Clamp depth to nearest standard wall thickness
                    # (+2 cm protrusion) so orphans don't render as slivers.
                    standard_thicknesses = [
                        float(int_cfg["thickness_cm"]),
                        float(ext_cfg["thickness_cm"]),
                    ]
                    depth = min(standard_thicknesses, key=lambda t: abs(t - depth)) + 2.0
            catalog_id, family = pick_catalog(kind, width)
            piece_color = opening_color(kind)
            extra = {}
            if piece_color is not None:
                extra["color"] = piece_color
            if snapped:
                extra["boundToWall"] = True
                extra["wallDistance"] = 0.0
                extra["wallWidth"]  = wall_length
                extra["wallLeft"]   = left_offset
            elif kind != "skylight":
                extra["boundToWall"] = False
            if family == "door":
                door_height_cm = 200.0
                if snapped:
                    extra["wallTop"]    = top_offset
                    extra["wallHeight"] = door_height_cm
                piece = add_door(home,
                                  name=kind.replace("_", " ").title(),
                                  x=cx - ax, y=cy - ay,
                                  width=width, depth=depth, height=door_height_cm,
                                  angle=angle, level=lvl.id,
                                  catalogId=catalog_id, **extra)
                # Attach sash defaults if catalog provided no sashes
                if sash_defaults and not piece.sashes:
                    import copy
                    piece.sashes = [copy.copy(s) for s in sash_defaults]
                # Apply furniture-level defaults
                piece.visible     = furn_visible
                piece.movable     = furn_movable
                piece.nameVisible = furn_name_visible
            elif family == "window":
                win_height_cm = 120.0
                win_elevation_cm = 100.0
                if snapped:
                    extra["wallTop"]    = wall_height - win_elevation_cm - win_height_cm
                    extra["wallHeight"] = win_height_cm
                piece = add_window(home, name="Window",
                                    x=cx - ax, y=cy - ay,
                                    width=width, depth=depth, height=win_height_cm,
                                    elevation=win_elevation_cm, angle=angle, level=lvl.id,
                                    catalogId=catalog_id, **extra)
                # Attach sash defaults if catalog provided no sashes
                if sash_defaults and not piece.sashes:
                    import copy
                    piece.sashes = [copy.copy(s) for s in sash_defaults]
                # Apply furniture-level defaults
                piece.visible     = furn_visible
                piece.movable     = furn_movable
                piece.nameVisible = furn_name_visible
            elif kind == "skylight":
                piece = add_piece(home, name="Skylight",
                                   x=cx - ax, y=cy - ay,
                                   width=width, depth=depth, height=4,
                                   angle=angle, level=lvl.id,
                                   elevation=wall_height - 5,
                                   catalogId="eTeks#texturableBox",
                                   color=0x80CCEEFF)
                piece.visible     = furn_visible
                piece.movable     = furn_movable
                piece.nameVisible = furn_name_visible

        for cx, cy, _r in lights:
            light_piece = add_light(home, name="Light",
                                     x=cx - ax, y=cy - ay,
                                     width=40, depth=40, height=20,
                                     level=lvl.id, elevation=wall_height - 30)
            # Attach light source defaults if catalog provided no sources
            if light_source_defaults and not light_piece.lightSources:
                import copy
                light_piece.lightSources = [copy.copy(ls) for ls in light_source_defaults]
            # Apply furniture-level defaults
            light_piece.visible     = furn_visible
            light_piece.movable     = furn_movable
            light_piece.nameVisible = furn_name_visible
            light_piece.dropOnTopElevation = furn_drop_top_elev

        # ── Rooms: SVG-drawn polygon seeds, snapped to welded wall centrelines.
        # The SVG wall path uses evenodd fill, so each room shows up as an
        # interior subpath.  We re-project each polygon vertex onto the
        # nearest wall centreline so the room boundary follows the rebuilt
        # wall geometry instead of drifting against the old positions.
        if rooms_cfg.get("auto_rooms", True):
            min_area = float(
                (rooms_cfg.get("detection") or {}).get("min_area_cm2", 5000.0)
            )

            def _snap_pt_to_walls(px: float, py: float, walls5,
                                   *, tol: float = 100.0
                                   ) -> tuple[float, float, bool]:
                """Project (px,py) onto the nearest wall centreline within tol.

                Returns (qx, qy, hit) — hit=True if a wall was found within tol.
                """
                best_d = tol
                best_pt = (px, py)
                hit = False
                for xs, ys, xe, ye, _t in walls5:
                    ddx, ddy = xe - xs, ye - ys
                    L2 = ddx * ddx + ddy * ddy
                    if L2 < 1e-6:
                        continue
                    u = ((px - xs) * ddx + (py - ys) * ddy) / L2
                    u = max(0.0, min(1.0, u))
                    qx, qy = xs + u * ddx, ys + u * ddy
                    d = math.hypot(px - qx, py - qy)
                    if d < best_d:
                        best_d = d
                        best_pt = (qx, qy)
                        hit = True
                return best_pt[0], best_pt[1], hit

            def _simplify_collinear(pts, *, tol: float = 5.0):
                """Drop interior points whose perpendicular distance to the
                line between their neighbours is < tol. Removes the kinks
                that make wall-snapped polygons look wavy."""
                if len(pts) < 3:
                    return pts
                out = [pts[0]]
                for i in range(1, len(pts) - 1):
                    a = out[-1]; b = pts[i]; c = pts[i + 1]
                    abx, aby = b[0] - a[0], b[1] - a[1]
                    acx, acy = c[0] - a[0], c[1] - a[1]
                    L = math.hypot(acx, acy)
                    if L < 1e-6:
                        continue
                    # Perpendicular distance b from segment ac.
                    perp = abs(abx * acy - aby * acx) / L
                    if perp > tol:
                        out.append(b)
                out.append(pts[-1])
                return out

            # Snap each SVG room polygon to the welded walls. Polygon points
            # land on the wall centrelines. Drop points that DIDN'T find any
            # wall within tol — those are SVG drawing artefacts (curve handles,
            # bezier control points) that produce the wavy room outlines.
            # Then simplify out collinear/near-collinear vertices for clean
            # rectilinear room shapes.
            room_polys: list[list[tuple[float, float]]] = []
            for raw_poly in interior_subpaths:
                snapped: list[tuple[float, float]] = []
                for px, py in raw_poly:
                    qx, qy, hit = _snap_pt_to_walls(px, py, all_walls_for_snap)
                    if not hit:
                        continue  # drop floating control points
                    if not snapped or math.hypot(qx - snapped[-1][0],
                                                  qy - snapped[-1][1]) > 2.0:
                        snapped.append((qx, qy))
                snapped = _simplify_collinear(snapped, tol=5.0)
                if len(snapped) >= 2 and math.hypot(
                        snapped[0][0] - snapped[-1][0],
                        snapped[0][1] - snapped[-1][1]) < 1.0:
                    snapped.pop()
                if len(snapped) >= 3 and abs(polygon_area(snapped)) >= min_area:
                    room_polys.append(snapped)

            # Backstop with auto-rooms for any face the SVG didn't draw.
            auto_face_polys = extract_rooms_from_walls(
                all_walls_for_snap,
                level_id=lvl.id,
                envelope=outer_env,
                min_area_cm2=min_area,
            )
            for face_pts in auto_face_polys:
                fcx = sum(p[0] for p in face_pts) / len(face_pts)
                fcy = sum(p[1] for p in face_pts) / len(face_pts)
                already_covered = any(
                    point_in_polygon(fcx, fcy, p) for p in room_polys
                )
                if not already_covered:
                    room_polys.append(list(face_pts))

            # Offset labels into home coordinate space (subtract anchor).
            anchored_labels = [(n, lx - ax, ly - ay) for n, lx, ly in labels]

            for face_pts in room_polys:
                # Convert from raw wall space to home space (subtract anchor)
                offset_pts = [(x - ax, y - ay) for x, y in face_pts]
                # Deduplicate consecutive identical points
                clean: list[tuple[float, float]] = []
                for pt in offset_pts:
                    if not clean or (abs(pt[0] - clean[-1][0]) > 0.01
                                     or abs(pt[1] - clean[-1][1]) > 0.01):
                        clean.append(pt)
                if len(clean) >= 2 and clean[0] == clean[-1]:
                    clean.pop()
                if len(clean) < 3:
                    continue

                # Match labels to this room by point-in-polygon.
                # When multiple labels land inside, pick the longest text
                # (typically the most descriptive name).
                matched_labels = [
                    name_str
                    for name_str, lx, ly in anchored_labels
                    if point_in_polygon(lx, ly, clean)
                ]
                room_name: Optional[str] = None
                if matched_labels:
                    room_name = max(matched_labels, key=len)

                floor_col = floor_color_for(room_name or "", lvl_name)
                add_room(home, clean, level=lvl.id, name=room_name,
                          floorColor=floor_col, ceilingColor=ceiling_col,
                          areaVisible=(room_name is not None))

            # Warn about any labels that didn't land inside any auto-room.
            added_rooms_pts = [
                [(p.x, p.y) for p in r.points]
                for r in home.rooms
                if r.level == lvl.id
            ]
            for name_str, lx, ly in anchored_labels:
                matched = any(
                    point_in_polygon(lx, ly, rpts)
                    for rpts in added_rooms_pts
                )
                if not matched:
                    import sys
                    print(
                        f"warning: label {name_str!r} at ({lx:.1f},{ly:.1f})"
                        f" didn't match any auto-room on {lvl_name!r}",
                        file=sys.stderr,
                    )

    link_wall_endpoints(home)

    # ── Environment (existing + new extended fields) ──────────────────────────
    env_cfg = cfg.get("environment", {})
    sky_col = hex_to_argb(env_cfg.get("sky_color"))    or COLOR_SKY
    ground_col = hex_to_argb(env_cfg.get("ground_color")) or COLOR_GROUND
    env_kwargs: dict = dict(skyColor=sky_col, groundColor=ground_col)
    env_kwargs["wallsAlpha"] = float(env_cfg.get("walls_alpha", 0))
    env_kwargs["drawingMode"] = env_cfg.get("drawing_mode", "FILL")
    env_kwargs["allLevelsVisible"] = bool(env_cfg.get("all_levels_visible", False))
    env_kwargs["observerCameraElevationAdjusted"] = bool(
        env_cfg.get("observer_camera_elevation_adjusted", True))
    env_kwargs["backgroundImageVisibleOnGround3D"] = bool(
        env_cfg.get("background_image_visible_on_ground", False))
    env_kwargs["subpartSizeUnderLight"] = float(
        env_cfg.get("subpart_size_under_light", 0))
    light_col = hex_to_argb(env_cfg.get("light_color"))
    if light_col is not None:
        env_kwargs["lightColor"] = light_col
    ceil_light_col = hex_to_argb(env_cfg.get("ceiling_light_color"))
    if ceil_light_col is not None:
        env_kwargs["ceilingLightColor"] = ceil_light_col
    # Photo settings
    photo_cfg = env_cfg.get("photo") or {}
    env_kwargs["photoWidth"]       = int(photo_cfg.get("width", 400))
    env_kwargs["photoHeight"]      = int(photo_cfg.get("height", 300))
    env_kwargs["photoAspectRatio"] = photo_cfg.get("aspect_ratio", "VIEW_3D_RATIO")
    env_kwargs["photoQuality"]     = int(photo_cfg.get("quality", 0))
    # Video settings
    video_cfg = env_cfg.get("video") or {}
    env_kwargs["videoWidth"]       = int(video_cfg.get("width", 320))
    env_kwargs["videoAspectRatio"] = video_cfg.get("aspect_ratio", "RATIO_4_3")
    env_kwargs["videoQuality"]     = int(video_cfg.get("quality", 0))
    env_kwargs["videoFrameRate"]   = int(video_cfg.get("frame_rate", 25))
    env_kwargs["videoSpeed"]       = float(video_cfg.get("speed", 240.0))
    set_environment(home, **env_kwargs)

    # ── Compass ───────────────────────────────────────────────────────────────
    compass_cfg = cfg.get("compass") or {}
    if compass_cfg:
        _apply_compass(home, compass_cfg)

    # ── Print settings ────────────────────────────────────────────────────────
    print_cfg = cfg.get("print") or {}
    if print_cfg:
        _apply_print(home, print_cfg)

    # ── Preferences as Home properties ────────────────────────────────────────
    pref_cfg = cfg.get("preferences") or {}
    if pref_cfg:
        _apply_preferences(home, pref_cfg)

    # ── Wall baseboards (applied retroactively after all walls are added) ──────
    bb_cfg = (cfg.get("walls") or {}).get("baseboard") or {}
    if bb_cfg.get("enabled", False):
        bb = _baseboard_from_cfg(bb_cfg)
        for w in home.walls:
            # Only add baseboard if not already set (catalog walls may have their own)
            if w.leftSideBaseboard is None:
                import copy
                w.leftSideBaseboard = copy.copy(bb)
            if w.rightSideBaseboard is None:
                import copy
                w.rightSideBaseboard = copy.copy(bb)

    # ── Room text styles (applied retroactively after all rooms are added) ──────
    ts_cfg = (cfg.get("rooms") or {}).get("text_style") or {}
    if ts_cfg:
        name_ts_cfg = ts_cfg.get("name") or {}
        area_ts_cfg = ts_cfg.get("area") or {}
        name_ts = _text_style_from_cfg(name_ts_cfg) if name_ts_cfg else None
        area_ts = _text_style_from_cfg(area_ts_cfg) if area_ts_cfg else None
        for r in home.rooms:
            if name_ts is not None and r.nameStyle is None:
                import copy
                r.nameStyle = copy.copy(name_ts)
            if area_ts is not None and r.areaStyle is None:
                import copy
                r.areaStyle = copy.copy(area_ts)

    return home
