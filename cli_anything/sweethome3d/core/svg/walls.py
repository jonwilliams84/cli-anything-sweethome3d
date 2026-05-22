"""Wall extraction pipeline: from raw SVG path segments to a list of
``(xStart, yStart, xEnd, yEnd, thickness)`` tuples ready to add to a
``Home``.

Pipeline (see ``extract_walls``):
  1. Walk all wall-fill path segments
  2. Cluster axis-aligned + 45°/135° edges
  3. Pair parallel edges by thickness range → walls
  4. Close corners (extend endpoints to nearby perpendicular centrelines)
  5. Join walls (union-find clustering of endpoints)
  6. Grid-snap (canonical rows/columns)
  7. Re-attach diagonals to nearest axis-aligned endpoint
  8. Assign internal thickness to ALL extracted walls (14 cm default)

External walls are NOT produced by ``extract_walls``. Instead,
``extract_envelope_walls`` traces the building-outline polygon emitted by
``collect_wall_subpaths`` and produces one wall per polygon edge at the
external thickness (35 cm). ``svg_to_home_multi`` then drops any
edge-pair-extracted wall whose midpoint is within ``envelope_tol_cm`` of
an envelope edge (inner faces of exterior walls), and adds the envelope
walls separately.

``classify_walls_by_envelope`` is retained for back-compatibility with
tests and scripts that use the old per-wall classification path; it is no
longer called from ``svg_to_home_multi``.

``link_wall_endpoints`` sets ``wallAtStart`` / ``wallAtEnd`` on the
Home's walls after they're built.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from cli_anything.sweethome3d.core.model import Home
from cli_anything.sweethome3d.core.svg.geometry import (
    point_to_segment_dist,
    polygon_area,
)
from cli_anything.sweethome3d.core.svg.parse import (
    IDENT,
    apply,
    is_wall_fill,
    mul,
    parse_path,
    parse_transform,
    walk_path,
)


@dataclass
class Edge:
    x1: float
    y1: float
    x2: float
    y2: float


def project_segment(x1, y1, x2, y2, angle_deg):
    """Project a segment onto an axis at ``angle_deg``.

    Returns ``(perp_avg, t_lo, t_hi)``: perp_avg is the segment's
    average perpendicular distance from the origin in the rotated
    frame, and ``t_lo..t_hi`` are the projection extents along the
    direction. Used by ``axis_aligned_oriented`` for arbitrary-angle
    edge extraction (45° diagonals etc.).
    """
    rad = math.radians(angle_deg)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    t1 = x1 * cos_a + y1 * sin_a
    t2 = x2 * cos_a + y2 * sin_a
    p1 = -x1 * sin_a + y1 * cos_a
    p2 = -x2 * sin_a + y2 * cos_a
    return (p1 + p2) / 2, min(t1, t2), max(t1, t2)


def axis_aligned_oriented(segs, angle_deg: float,
                            angle_tol_deg: float, perp_tol_cm: float,
                            min_len: float):
    """Like ``axis_aligned`` but for an arbitrary line direction.

    Returns clusters of ``(perp, t_lo, t_hi)`` where perp is the line's
    perpendicular offset from the origin. ``angle_tol_deg`` controls
    which segments count as "this direction"; ``perp_tol_cm`` controls
    when two collinear segments merge into one line. Splitting these
    two tolerances is critical — collapsing them caused parallel walls
    < tol cm apart to fuse into one phantom line.
    """
    candidates = []
    for x1, y1, x2, y2 in segs:
        dx, dy = x2 - x1, y2 - y1
        if math.hypot(dx, dy) < min_len:
            continue
        seg_ang = math.degrees(math.atan2(dy, dx))
        diff = (seg_ang - angle_deg) % 180
        if diff > 90:
            diff -= 180
        if abs(diff) > angle_tol_deg:
            continue
        candidates.append(project_segment(x1, y1, x2, y2, angle_deg))

    candidates.sort(key=lambda c: c[0])
    clusters: list[list[tuple[float, float, float]]] = []
    for s in candidates:
        if clusters and abs(clusters[-1][-1][0] - s[0]) <= perp_tol_cm:
            clusters[-1].append(s)
        else:
            clusters.append([s])

    merged: list[tuple[float, float, float]] = []
    for cluster in clusters:
        cluster.sort(key=lambda s: s[1])
        cur_p_sum = cluster[0][0]; cur_p_n = 1
        cur_lo, cur_hi = cluster[0][1], cluster[0][2]
        for perp, lo, hi in cluster[1:]:
            if lo <= cur_hi + perp_tol_cm:
                cur_p_sum += perp; cur_p_n += 1
                cur_hi = max(cur_hi, hi); cur_lo = min(cur_lo, lo)
            else:
                merged.append((cur_p_sum / cur_p_n, cur_lo, cur_hi))
                cur_p_sum = perp; cur_p_n = 1
                cur_lo, cur_hi = lo, hi
        merged.append((cur_p_sum / cur_p_n, cur_lo, cur_hi))
    return merged


def walls_from_pairs_at_angle(pairs, angle_deg: float):
    """Convert ``pair_edges`` output for a non-axial direction back
    into walls in the original coordinate frame.
    """
    rad = math.radians(angle_deg)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    out = []
    for perp, t_lo, t_hi, thick in pairs:
        xs = t_lo * cos_a - perp * sin_a
        ys = t_lo * sin_a + perp * cos_a
        xe = t_hi * cos_a - perp * sin_a
        ye = t_hi * sin_a + perp * cos_a
        out.append((xs, ys, xe, ye, thick))
    return out


def axis_aligned(segs, axis: str, axis_tol: float, min_len: float):
    """Snap near-axis-aligned segments to a clean horizontal/vertical
    form, then merge adjacent / overlapping collinear segments.

    Returns ``(a_mid, b_lo, b_hi)`` tuples where ``a_mid`` is the
    perpendicular coordinate and ``b_lo..b_hi`` is the axis extent.
    """
    out = []
    for x1, y1, x2, y2 in segs:
        dx, dy = abs(x2 - x1), abs(y2 - y1)
        if math.hypot(dx, dy) < min_len:
            continue
        if axis == "h" and dy <= axis_tol and dx > axis_tol:
            yavg = (y1 + y2) / 2
            out.append((yavg, min(x1, x2), max(x1, x2)))
        elif axis == "v" and dx <= axis_tol and dy > axis_tol:
            xavg = (x1 + x2) / 2
            out.append((xavg, min(y1, y2), max(y1, y2)))

    out.sort(key=lambda s: s[0])
    clusters: list[list[tuple[float, float, float]]] = []
    for s in out:
        if clusters and abs(clusters[-1][-1][0] - s[0]) <= axis_tol:
            clusters[-1].append(s)
        else:
            clusters.append([s])

    merged: list[tuple[float, float, float]] = []
    for cluster in clusters:
        cluster.sort(key=lambda s: s[1])
        cur_perp_sum = cluster[0][0]
        cur_perp_n = 1
        cur_lo, cur_hi = cluster[0][1], cluster[0][2]
        for perp, lo, hi in cluster[1:]:
            if lo <= cur_hi + axis_tol:
                cur_perp_sum += perp
                cur_perp_n += 1
                cur_hi = max(cur_hi, hi)
                cur_lo = min(cur_lo, lo)
            else:
                merged.append((cur_perp_sum / cur_perp_n, cur_lo, cur_hi))
                cur_perp_sum = perp; cur_perp_n = 1
                cur_lo, cur_hi = lo, hi
        merged.append((cur_perp_sum / cur_perp_n, cur_lo, cur_hi))
    return merged


def overlap(a1, a2, b1, b2) -> float:
    return max(0.0, min(a2, b2) - max(a1, b1))


def pair_edges(edges, thick_lo: float, thick_hi: float, min_overlap: float,
                *, axis_tol: float = 5.0):
    """Enumerate every ``(edge_a, edge_b)`` pair within the wall-thickness
    range and emit one wall per overlap region. A long edge with
    multiple short partners therefore yields multiple wall sections —
    the previous greedy-pair logic would have consumed it after a
    single match.

    Returns list of ``(centre, lo, hi, thickness)``.
    """
    raw_walls = []
    for i, (perp_a, lo_a, hi_a) in enumerate(edges):
        for j in range(i + 1, len(edges)):
            perp_b, lo_b, hi_b = edges[j]
            thick = abs(perp_b - perp_a)
            if not (thick_lo <= thick <= thick_hi):
                continue
            ov_lo = max(lo_a, lo_b)
            ov_hi = min(hi_a, hi_b)
            if ov_hi - ov_lo < min_overlap:
                continue
            raw_walls.append(((perp_a + perp_b) / 2, ov_lo, ov_hi, thick))

    raw_walls.sort(key=lambda w: w[0])
    clusters: list[list[tuple[float, float, float, float]]] = []
    for w in raw_walls:
        if clusters and abs(clusters[-1][-1][0] - w[0]) <= axis_tol:
            clusters[-1].append(w)
        else:
            clusters.append([w])

    out: list[tuple[float, float, float, float]] = []
    for cluster in clusters:
        cluster.sort(key=lambda w: w[1])
        cur = cluster[0]
        for centre, lo, hi, thick in cluster[1:]:
            if lo <= cur[2] + axis_tol:  # touches or overlaps
                cur = (
                    (cur[0] + centre) / 2,
                    min(cur[1], lo),
                    max(cur[2], hi),
                    max(cur[3], thick),
                )
            else:
                out.append(cur)
                cur = (centre, lo, hi, thick)
        out.append(cur)
    return out


def collect_wall_segments(svg_root: ET.Element) -> list[tuple[float, float, float, float]]:
    """Walk the SVG tree and return wall-path segments in absolute coords."""
    segs: list[tuple[float, float, float, float]] = []

    def visit(el: ET.Element, parent_xform):
        my_xform = mul(parent_xform, parse_transform(el.get("transform", "")))
        if el.tag == "path" and is_wall_fill(el):
            cmds = parse_path(el.get("d", ""))
            for x1, y1, x2, y2 in walk_path(cmds):
                p1 = apply(my_xform, x1, y1)
                p2 = apply(my_xform, x2, y2)
                segs.append((p1[0], p1[1], p2[0], p2[1]))
        for child in el:
            visit(child, my_xform)

    visit(svg_root, IDENT)
    return segs


def collect_wall_subpaths(svg_root: ET.Element) -> list[list[tuple[float, float]]]:
    """Return each wall-polygon subpath as a list of ``(x, y)`` vertices.

    The wall path's outer perimeter is the longest closed subpath;
    smaller subpaths are interior room cut-outs. Callers typically pick
    the largest subpath per floor as the building outline.
    """
    subpaths: list[list[tuple[float, float]]] = []

    def visit(el: ET.Element, parent_xform):
        my_xform = mul(parent_xform, parse_transform(el.get("transform", "")))
        if el.tag == "path" and is_wall_fill(el):
            cmds = parse_path(el.get("d", ""))
            current: list[tuple[float, float]] = []
            x = y = sx = sy = 0.0
            for cmd, args in cmds:
                if cmd == "M":
                    if current:
                        subpaths.append([apply(my_xform, *p) for p in current])
                    x, y = args; sx, sy = x, y
                    current = [(x, y)]
                elif cmd == "m":
                    if current:
                        subpaths.append([apply(my_xform, *p) for p in current])
                    x += args[0]; y += args[1]; sx, sy = x, y
                    current = [(x, y)]
                elif cmd == "L":
                    x, y = args[0], args[1]; current.append((x, y))
                elif cmd == "l":
                    x += args[0]; y += args[1]; current.append((x, y))
                elif cmd == "H":
                    x = args[0]; current.append((x, y))
                elif cmd == "h":
                    x += args[0]; current.append((x, y))
                elif cmd == "V":
                    y = args[0]; current.append((x, y))
                elif cmd == "v":
                    y += args[0]; current.append((x, y))
                elif cmd in ("Z", "z"):
                    x, y = sx, sy
                    if current:
                        subpaths.append([apply(my_xform, *p) for p in current])
                        current = []
                elif cmd in ("C", "S", "Q"):
                    x, y = args[-2], args[-1]; current.append((x, y))
                elif cmd in ("c", "s", "q"):
                    x += args[-2]; y += args[-1]; current.append((x, y))
            if current:
                subpaths.append([apply(my_xform, *p) for p in current])
        for child in el:
            visit(child, my_xform)

    visit(svg_root, IDENT)
    return subpaths


def close_corners(walls, *, snap_distance: float):
    """Extend each wall endpoint to the nearest perpendicular-wall
    centreline. Each endpoint tracks its best-distance separately so
    the first match isn't pinned to the original coordinate (the bug
    that made this a no-op for a long time).
    """
    h_walls = [(i, w) for i, w in enumerate(walls) if w[1] == w[3]]
    v_walls = [(i, w) for i, w in enumerate(walls) if w[0] == w[2]]

    closed = list(walls)
    for i, (xs, ys, xe, ye, thick) in h_walls:
        best_xs = xs
        best_xs_dist = float("inf")
        best_xe = xe
        best_xe_dist = float("inf")
        snapped_start = snapped_end = False
        for _, (vx, vys, vxe, vye, _vt) in v_walls:
            if not (min(vys, vye) - snap_distance <= ys <= max(vys, vye) + snap_distance):
                continue
            d_start = abs(vx - xs)
            if d_start <= snap_distance and d_start < best_xs_dist:
                best_xs = vx; best_xs_dist = d_start; snapped_start = True
            d_end = abs(vx - xe)
            if d_end <= snap_distance and d_end < best_xe_dist:
                best_xe = vx; best_xe_dist = d_end; snapped_end = True
        if not snapped_start:
            best_xs -= thick / 2
        if not snapped_end:
            best_xe += thick / 2
        if best_xs <= best_xe:
            closed[i] = (best_xs, ys, best_xe, ye, thick)
    for i, (xs, ys, xe, ye, thick) in v_walls:
        best_ys = ys
        best_ys_dist = float("inf")
        best_ye = ye
        best_ye_dist = float("inf")
        snapped_start = snapped_end = False
        for _, (vx, hy, _vxe, _hy2, _ht) in h_walls:
            if not (min(vx, _vxe) - snap_distance <= xs <= max(vx, _vxe) + snap_distance):
                continue
            d_start = abs(hy - ys)
            if d_start <= snap_distance and d_start < best_ys_dist:
                best_ys = hy; best_ys_dist = d_start; snapped_start = True
            d_end = abs(hy - ye)
            if d_end <= snap_distance and d_end < best_ye_dist:
                best_ye = hy; best_ye_dist = d_end; snapped_end = True
        if not snapped_start:
            best_ys -= thick / 2
        if not snapped_end:
            best_ye += thick / 2
        if best_ys <= best_ye:
            closed[i] = (xs, best_ys, xe, best_ye, thick)
    return closed


def snap_wall_angles(walls, *, angle_tol_deg: float = 8.0):
    """Snap each wall's direction to the nearest 0° / 45° / 90° / 135°.

    Edge-pair extraction already emits axis-aligned walls, so in
    practice this is a tiny correction. The 45° branch is insurance.
    """
    out = []
    for xs, ys, xe, ye, t in walls:
        dx, dy = xe - xs, ye - ys
        length = math.hypot(dx, dy)
        if length < 1e-6:
            continue
        ang = math.degrees(math.atan2(dy, dx))
        snap_ang = round(ang / 45.0) * 45.0
        if abs(ang - snap_ang) <= angle_tol_deg:
            rad = math.radians(snap_ang)
            xe = xs + length * math.cos(rad)
            ye = ys + length * math.sin(rad)
        out.append((xs, ys, xe, ye, t))
    return out


def grid_snap(walls, *, row_tol: float = 18.0, col_tol: float = 18.0):
    """Snap walls to a global row/column grid.

    Cluster every H wall's y-midpoint into canonical rows, every V
    wall's x-midpoint into canonical cols. Then snap each H wall's
    y values to its row canonical and its x endpoints to the nearest
    column line. After grid-snap, every wall is axis-aligned AND
    every wall endpoint sits at a (col, row) intersection.
    """
    H, V, D = [], [], []
    for i, (xs, ys, xe, ye, _t) in enumerate(walls):
        dx, dy = abs(xe - xs), abs(ye - ys)
        if dx >= max(1.0, dy * 4):
            H.append((i, (ys + ye) / 2))
        elif dy >= max(1.0, dx * 4):
            V.append((i, (xs + xe) / 2))
        else:
            D.append(i)

    def cluster(pairs, tol):
        pairs_sorted = sorted(pairs, key=lambda p: p[1])
        out_clusters: list[list[tuple[int, float]]] = []
        for idx, v in pairs_sorted:
            if out_clusters and abs(out_clusters[-1][-1][1] - v) <= tol:
                out_clusters[-1].append((idx, v))
            else:
                out_clusters.append([(idx, v)])
        return out_clusters

    row_canon: dict[int, float] = {}
    for c in cluster(H, row_tol):
        canon = sum(v for _, v in c) / len(c)
        for idx, _ in c:
            row_canon[idx] = canon
    col_canon: dict[int, float] = {}
    for c in cluster(V, col_tol):
        canon = sum(v for _, v in c) / len(c)
        for idx, _ in c:
            col_canon[idx] = canon

    rows = sorted(set(row_canon.values()))
    cols = sorted(set(col_canon.values()))

    def nearest_within(value, options, tol):
        if not options:
            return value
        best = min(options, key=lambda v: abs(v - value))
        return best if abs(best - value) <= tol else value

    end_tol = col_tol * 2.5

    out = list(walls)
    for i, (xs, ys, xe, ye, t) in enumerate(walls):
        if i in row_canon:
            cy = row_canon[i]
            nxs = nearest_within(xs, cols, end_tol)
            nxe = nearest_within(xe, cols, end_tol)
            out[i] = (nxs, cy, nxe, cy, t)
        elif i in col_canon:
            cx = col_canon[i]
            nys = nearest_within(ys, rows, end_tol)
            nye = nearest_within(ye, rows, end_tol)
            out[i] = (cx, nys, cx, nye, t)
    return out


def join_walls(walls, *, join_tolerance: float = 35.0,
                external_threshold: float = 20.0):
    """Cluster nearby wall endpoints and snap each cluster to one point.

    Mirrors SH3D's "Join walls" command. When a cluster contains
    external walls (thickness ≥ ``external_threshold``), the target
    point is computed using only those externals — internal partitions
    get pulled onto the external grid.
    """
    if not walls:
        return []
    endpoints = []
    for i, (xs, ys, xe, ye, _) in enumerate(walls):
        endpoints.append((i, 0, xs, ys))
        endpoints.append((i, 1, xe, ye))

    parent = list(range(len(endpoints)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for a in range(len(endpoints)):
        wa, _, xa, ya = endpoints[a]
        for b in range(a + 1, len(endpoints)):
            wb, _, xb, yb = endpoints[b]
            if wa == wb:
                continue
            if math.hypot(xa - xb, ya - yb) <= join_tolerance:
                union(a, b)

    clusters: dict[int, list[int]] = {}
    for idx in range(len(endpoints)):
        clusters.setdefault(find(idx), []).append(idx)

    def is_horiz(w):
        return abs(w[1] - w[3]) < 1.0

    def is_vert(w):
        return abs(w[0] - w[2]) < 1.0

    targets: dict[int, tuple[float, float]] = {}
    for root, members in clusters.items():
        member_walls_idx = {endpoints[m][0] for m in members}
        all_member_walls = [walls[w] for w in member_walls_idx]
        ext_member_walls = [w for w in all_member_walls
                              if w[4] >= external_threshold]
        anchor_walls = ext_member_walls or all_member_walls
        h_anchors = [w for w in anchor_walls if is_horiz(w)]
        v_anchors = [w for w in anchor_walls if is_vert(w)]
        if h_anchors and v_anchors:
            avg_y = sum((h[1] + h[3]) / 2 for h in h_anchors) / len(h_anchors)
            avg_x = sum((v[0] + v[2]) / 2 for v in v_anchors) / len(v_anchors)
            targets[root] = (avg_x, avg_y)
        elif h_anchors:
            avg_y = sum((h[1] + h[3]) / 2 for h in h_anchors) / len(h_anchors)
            xs = [endpoints[m][2] for m in members]
            targets[root] = (sum(xs) / len(xs), avg_y)
        elif v_anchors:
            avg_x = sum((v[0] + v[2]) / 2 for v in v_anchors) / len(v_anchors)
            ys = [endpoints[m][3] for m in members]
            targets[root] = (avg_x, sum(ys) / len(ys))
        else:
            xs = [endpoints[m][2] for m in members]
            ys = [endpoints[m][3] for m in members]
            targets[root] = (sum(xs) / len(xs), sum(ys) / len(ys))

    out = [list(w) for w in walls]
    for idx, (wi, ei, _, _) in enumerate(endpoints):
        tx, ty = targets[find(idx)]
        if ei == 0:
            out[wi][0] = tx; out[wi][1] = ty
        else:
            out[wi][2] = tx; out[wi][3] = ty

    cleaned = []
    for xs, ys, xe, ye, t in out:
        if math.hypot(xe - xs, ye - ys) > 1:
            cleaned.append((xs, ys, xe, ye, t))
    return cleaned


def classify_walls_by_envelope(walls, outer_polygon, *,
                                 tol: float = 25.0,
                                 external_thickness: float = 35.0,
                                 internal_thickness: float = 14.0):
    """Classify each wall as external (one side faces outside) or
    internal (both sides face other rooms) by testing the outer-envelope
    polygon.

    An external wall has ONE side inside the polygon and the OTHER
    outside. An internal partition has BOTH sides inside (each face
    looks into a different room). Earlier we tested "both endpoints
    near the envelope" — but an interior partition can have both ends
    touching the envelope and still be internal (e.g. a wall in the
    south-side jog where the front door sits).

    The midpoint-nudge approach gets it right: offset the wall midpoint
    a few cm along its two perpendicular normals; if exactly ONE nudge
    point lies inside the polygon, the wall is external.
    """
    if not outer_polygon or len(outer_polygon) < 3:
        return walls

    # Nudge must be LARGER than half the external wall thickness so both
    # test points leave the wall material — otherwise they both land
    # inside the wall AND inside the envelope polygon, and every wall
    # reads as internal. Using external_thickness as the floor.
    nudge = max(external_thickness * 0.75, tol)

    out = []
    seen_keys: set[tuple] = set()
    for xs, ys, xe, ye, _t in walls:
        mx, my = (xs + xe) / 2, (ys + ye) / 2
        dx, dy = xe - xs, ye - ys
        L = math.hypot(dx, dy) or 1.0
        # SH3D Y-down left normal: (dy, -dx) / |dir|
        lnx, lny = dy / L, -dx / L
        left_pt  = (mx + lnx * nudge, my + lny * nudge)
        right_pt = (mx - lnx * nudge, my - lny * nudge)
        from cli_anything.sweethome3d.core.svg.geometry import point_in_polygon
        left_in  = point_in_polygon(left_pt[0],  left_pt[1],  outer_polygon)
        right_in = point_in_polygon(right_pt[0], right_pt[1], outer_polygon)
        external = left_in != right_in
        new_t = external_thickness if external else internal_thickness
        # Dedup: after reclassification two walls may collapse to identical
        # (coords, thickness) tuples — drop the second occurrence.
        key = (round(xs), round(ys), round(xe), round(ye), int(round(new_t)))
        key_rev = (round(xe), round(ye), round(xs), round(ys), int(round(new_t)))
        canon = min(key, key_rev)
        if canon in seen_keys:
            continue
        seen_keys.add(canon)
        out.append((xs, ys, xe, ye, new_t))
    return out


def extract_walls(svg_root: ET.Element,
                    *, wall_thickness_range=(6.0, 80.0),
                    min_wall_length: float = 8.0,
                    axis_tol: float = 6.0,
                    close_corners_enabled: bool = True,
                    join_walls_enabled: bool = True,
                    external_threshold: float = 18.0,
                    external_thickness: float = 35.0,
                    internal_thickness: float = 14.0):
    """Full wall-extraction pipeline. See module docstring for stages.

    All extracted walls receive ``internal_thickness`` regardless of their
    raw measured thickness. External walls are produced separately via
    ``extract_envelope_walls``.
    """
    all_segs = collect_wall_segments(svg_root)
    horiz = axis_aligned(all_segs, "h", axis_tol, min_wall_length)
    vert = axis_aligned(all_segs, "v", axis_tol, min_wall_length)
    lo, hi = wall_thickness_range
    lo = min(lo, 6.0)
    walls = []
    for centre, x_lo, x_hi, thick in pair_edges(horiz, lo, hi,
                                                   min_wall_length,
                                                   axis_tol=axis_tol):
        walls.append((x_lo, centre, x_hi, centre, thick))
    for centre, y_lo, y_hi, thick in pair_edges(vert, lo, hi,
                                                   min_wall_length,
                                                   axis_tol=axis_tol):
        walls.append((centre, y_lo, centre, y_hi, thick))

    diagonals: list[tuple[float, float, float, float, float]] = []
    for diag_angle in (45.0, 135.0):
        diag_lines = axis_aligned_oriented(
            all_segs, diag_angle,
            angle_tol_deg=15.0, perp_tol_cm=axis_tol,
            min_len=min_wall_length,
        )
        diag_pairs = pair_edges(diag_lines, lo, hi, min_wall_length,
                                  axis_tol=axis_tol)
        diagonals.extend(walls_from_pairs_at_angle(diag_pairs, diag_angle))

    if close_corners_enabled and walls:
        max_thick = max(w[4] for w in walls)
        walls = close_corners(walls, snap_distance=max_thick * 2)
    if join_walls_enabled and walls:
        sorted_t = sorted(w[4] for w in walls)
        median_t = sorted_t[len(sorted_t) // 2]
        walls = join_walls(walls,
                            join_tolerance=max(min(median_t * 2, 40.0), 35.0),
                            external_threshold=external_threshold)
        walls = grid_snap(walls)

    if diagonals:
        all_axis_endpoints = []
        for xs, ys, xe, ye, _t in walls:
            all_axis_endpoints.append((xs, ys))
            all_axis_endpoints.append((xe, ye))
        snap_tol = 40.0
        snapped_diag = []
        for xs, ys, xe, ye, t in diagonals:
            def nearest(px, py):
                if not all_axis_endpoints:
                    return px, py
                best = min(all_axis_endpoints,
                            key=lambda p: (p[0] - px) ** 2 + (p[1] - py) ** 2)
                if math.hypot(best[0] - px, best[1] - py) <= snap_tol:
                    return best
                return px, py
            xs, ys = nearest(xs, ys)
            xe, ye = nearest(xe, ye)
            snapped_diag.append((xs, ys, xe, ye, t))
        walls = walls + snapped_diag

    # Assign internal thickness to all extracted walls.  External walls
    # are no longer produced here — they come from extract_envelope_walls().
    walls = [
        (xs, ys, xe, ye, internal_thickness)
        for xs, ys, xe, ye, t in walls
    ]

    # Deduplication: drop walls whose endpoints (rounded to 1 cm) and
    # thickness are identical to a previously-seen wall.  Duplicate walls
    # arise when pair_edges emits the same wall from overlapping edge
    # clusters (e.g. the three copies of the y≈−702.8 horizontal).
    seen_keys: set[tuple[float, float, float, float, int]] = set()
    deduped_walls = []
    for xs, ys, xe, ye, t in walls:
        key = (round(xs), round(ys), round(xe), round(ye), int(round(t)))
        # Normalise direction so (A→B) and (B→A) map to the same key.
        key_rev = (round(xe), round(ye), round(xs), round(ys), int(round(t)))
        canon = min(key, key_rev)
        if canon not in seen_keys:
            seen_keys.add(canon)
            deduped_walls.append((xs, ys, xe, ye, t))

    deduped_walls = weld_wall_endpoints(deduped_walls)
    return deduped_walls


def weld_wall_endpoints(walls, *, tolerance: float = 2.0):
    """Merge near-coincident wall endpoints so SH3D auto-room detection fires.

    SH3D's ``Plan → Create rooms automatically`` only recognises closed
    loops when wall endpoints share *exactly* the same coordinates.  Sub-
    pixel near-misses (e.g. 0.3 cm after grid-snap rounding) silently
    break it.

    Algorithm (union-find on endpoints):
    1. Collect every endpoint ``(x, y)`` with a reference to its wall
       index and which end (0 = start, 1 = end).
    2. Union any two endpoints from *different* walls whose Euclidean
       distance ≤ ``tolerance``.
    3. For each cluster compute the centroid (mean X, mean Y).
    4. Rewrite each wall's endpoint to the cluster centroid.
    5. Skip clusters that contain BOTH ends of the same wall to avoid
       zero-length walls.
    6. Drop any wall whose length drops to ≤ 1 cm after welding.
    """
    if not walls:
        return list(walls)

    # --- 1. Collect all endpoints ----------------------------------------
    # ep[i] = (wall_index, end_index, x, y)
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

    # --- 2. Union near-coincident endpoints from different walls ----------
    for i in range(n):
        wi_a, _, xa, ya = ep[i]
        for j in range(i + 1, n):
            wi_b, _, xb, yb = ep[j]
            if wi_a == wi_b:
                continue  # same wall — never fuse start to end
            if math.hypot(xa - xb, ya - yb) <= tolerance:
                union(i, j)

    # --- 3. Build clusters ------------------------------------------------
    clusters: dict[int, list[int]] = {}
    for idx in range(n):
        clusters.setdefault(find(idx), []).append(idx)

    # --- 4. Compute centroid, skipping clusters that span both ends of the
    #         same wall (would zero-length it).
    target: dict[int, tuple[float, float]] = {}
    for root, members in clusters.items():
        # Check: does this cluster contain both endpoints of any single wall?
        wall_ends: dict[int, set[int]] = {}
        for m in members:
            wi, ei, _, _ = ep[m]
            wall_ends.setdefault(wi, set()).add(ei)
        if any(len(ends) == 2 for ends in wall_ends.values()):
            # Skip — centroid would collapse a wall to a point.
            for m in members:
                _, _, xm, ym = ep[m]
                target[m] = (xm, ym)  # keep original coords
        else:
            cx = sum(ep[m][2] for m in members) / len(members)
            cy = sum(ep[m][3] for m in members) / len(members)
            for m in members:
                target[m] = (cx, cy)

    # --- 5. Rewrite endpoints and drop zero-length walls ------------------
    out_walls = [list(w) for w in walls]
    for idx, (wi, ei, _, _) in enumerate(ep):
        tx, ty = target[idx]
        if ei == 0:
            out_walls[wi][0] = tx
            out_walls[wi][1] = ty
        else:
            out_walls[wi][2] = tx
            out_walls[wi][3] = ty

    welded = [
        tuple(w) for w in out_walls
        if math.hypot(w[2] - w[0], w[3] - w[1]) > 1.0
    ]

    # --- 6. T-junction snapping: snap isolated endpoints onto wall edges ----
    # After endpoint-to-endpoint welding some internal wall endpoints may still
    # float a few mm away from an external wall's body (not its endpoints).
    # Project each "free" endpoint onto any wall edge within ``tolerance``.
    # "Free" = the endpoint is in a cluster of size 1 (no neighbour welded to it).
    free_eps: list[tuple[int, int]] = []  # (wall_idx, end_idx)
    # Rebuild a quick cluster-size lookup from the rewritten welded list.
    # We re-run a tiny O(n²) check on the final list (which is small).
    n_w = len(welded)
    for wi in range(n_w):
        for ei in range(2):
            px = welded[wi][ei * 2]
            py = welded[wi][ei * 2 + 1]
            is_free = True
            for wj in range(n_w):
                if wj == wi:
                    continue
                for ej in range(2):
                    qx = welded[wj][ej * 2]
                    qy = welded[wj][ej * 2 + 1]
                    if math.hypot(px - qx, py - qy) <= tolerance:
                        is_free = False
                        break
                if not is_free:
                    break
            if is_free:
                free_eps.append((wi, ei))

    if free_eps:
        welded_mut = [list(w) for w in welded]
        for wi, ei in free_eps:
            px = welded_mut[wi][ei * 2]
            py = welded_mut[wi][ei * 2 + 1]
            best_dist = tolerance
            best_proj = None
            for wj, (xs2, ys2, xe2, ye2, _t2) in enumerate(welded):
                if wj == wi:
                    continue
                dx2, dy2 = xe2 - xs2, ye2 - ys2
                L2sq = dx2 * dx2 + dy2 * dy2
                if L2sq < 1e-9:
                    continue
                t = ((px - xs2) * dx2 + (py - ys2) * dy2) / L2sq
                # Only snap to the body of the wall, not near its endpoints
                # (those would already have been caught by ep-to-ep welding).
                if t < 0.05 or t > 0.95:
                    continue
                qx2, qy2 = xs2 + t * dx2, ys2 + t * dy2
                d = math.hypot(px - qx2, py - qy2)
                if d < best_dist:
                    best_dist = d
                    best_proj = (qx2, qy2)
            if best_proj is not None:
                welded_mut[wi][ei * 2]     = best_proj[0]
                welded_mut[wi][ei * 2 + 1] = best_proj[1]
        welded = [
            tuple(w) for w in welded_mut
            if math.hypot(w[2] - w[0], w[3] - w[1]) > 1.0
        ]

    return welded


def _signed_area_2d(pts: list[tuple[float, float]]) -> float:
    """Signed shoelace area.  Positive = CCW in standard (Y-up) math coords.
    In SH3D's Y-down screen space positive = CW visually."""
    n = len(pts)
    if n < 3:
        return 0.0
    a = 0.0
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return a / 2.0


def extract_envelope_walls(
    envelope: list[tuple[float, float]],
    level_id=None,
    *,
    thickness: float = 35.0,
    height: float = 240.0,
    exterior_color: int = 0xFFA0522D,
    interior_color: int = 0xFFFFFFFF,
    min_edge_length: float = 5.0,
    collinear_angle_tol_deg: float = 1.0,
) -> list[tuple]:
    """Trace the building-envelope polygon and emit one wall-tuple per edge.

    Returns a list of ``(xs, ys, xe, ye, thickness, left_color, right_color)``
    7-tuples consumed by ``svg_to_home_multi`` when calling ``add_wall``.

    Algorithm
    ---------
    1. Close the polygon (ensure last vertex == first).
    2. Merge near-collinear consecutive edges (angle change <
       ``collinear_angle_tol_deg``).
    3. Drop edges shorter than ``min_edge_length``.
    4. For each remaining edge decide which side is exterior via a
       point-in-polygon test: nudge the midpoint one ``thickness`` step
       toward the *right-side normal* and test against the polygon.  If
       the nudged point is inside → right = interior, left = exterior;
       else left = interior.
    5. Emit one tuple per edge with colours assigned accordingly.

    Both axis-aligned and diagonal edges are handled identically — SH3D
    supports non-orthogonal walls without special treatment.
    """
    if not envelope or len(envelope) < 3:
        return []

    # --- 1. Close polygon ---------------------------------------------------
    pts = list(envelope)
    if pts[-1] != pts[0]:
        pts.append(pts[0])

    # --- 2. Simplify: merge near-collinear consecutive edges ----------------
    def edge_angle(p1, p2):
        return math.atan2(p2[1] - p1[1], p2[0] - p1[0])

    simplified = [pts[0]]
    for i in range(1, len(pts) - 1):
        prev = simplified[-1]
        cur  = pts[i]
        nxt  = pts[i + 1]
        # Skip degenerate zero-length sub-edges before computing angle
        if math.hypot(cur[0] - prev[0], cur[1] - prev[1]) < 1e-6:
            continue
        if math.hypot(nxt[0] - cur[0], nxt[1] - cur[1]) < 1e-6:
            simplified.append(cur)
            continue
        ang_in  = edge_angle(prev, cur)
        ang_out = edge_angle(cur,  nxt)
        diff_deg = math.degrees(abs(ang_out - ang_in)) % 360.0
        if diff_deg > 180.0:
            diff_deg = 360.0 - diff_deg
        if diff_deg < collinear_angle_tol_deg:
            # Near-collinear — absorb cur into the current run (skip it).
            continue
        simplified.append(cur)
    simplified.append(pts[-1])  # closing vertex (== pts[0])

    # --- 3. Drop short edges ------------------------------------------------
    edges: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for i in range(len(simplified) - 1):
        p1, p2 = simplified[i], simplified[i + 1]
        if math.hypot(p2[0] - p1[0], p2[1] - p1[1]) >= min_edge_length:
            edges.append((p1, p2))

    if not edges:
        return []

    # --- 4 & 5. Assign colours per edge via point-in-polygon test ----------
    # Use the open polygon (no repeated first vertex) for PIP.
    open_poly = simplified[:-1]
    # Nudge > half the wall thickness so the test point leaves the wall material.
    nudge = thickness + 1.0

    out: list[tuple] = []
    for (x1, y1), (x2, y2) in edges:
        dx, dy = x2 - x1, y2 - y1
        L = math.hypot(dx, dy) or 1.0
        mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0

        # SH3D Y-down convention (com.eteks.sweethome3d.model.Wall.getLeftSidePoints):
        # For wall direction (dx, dy), the LEFT-side normal is (-dy, +dx)/L.
        # This is a 90° CCW rotation in standard math coords, which appears CW
        # on the Y-down screen.  Step from midpoint toward the left-normal and
        # test whether that probe lands inside the building polygon.
        # If it does → left side faces interior → leftSideColor = interior_color.
        lnx, lny = -dy / L, dx / L
        lpt_x = mx + lnx * nudge
        lpt_y = my + lny * nudge

        from cli_anything.sweethome3d.core.svg.geometry import point_in_polygon
        left_inside = point_in_polygon(lpt_x, lpt_y, open_poly)

        # SH3D's leftSideColor paints the face on the opposite side of the
        # left-normal in the 3D view. Empirically: if probe lands inside the
        # polygon, the brick (exterior) should be on the LEFT slot.
        if left_inside:
            left_col, right_col = exterior_color, interior_color
        else:
            left_col, right_col = interior_color, exterior_color

        out.append((x1, y1, x2, y2, thickness, left_col, right_col))

    return out


def link_wall_endpoints(home: Home, *, tol: float = 6.0) -> None:
    """Set ``wallAtStart`` / ``wallAtEnd`` on every wall that shares an
    endpoint with another wall on the same level. Checks all four
    endpoint-meeting combinations (SS, SE, ES, EE) — without this
    SH3D leaves overlapping rectangles at corners instead of mitering.
    """
    walls = home.walls
    for i, a in enumerate(walls):
        for j, b in enumerate(walls):
            if i == j or a.level != b.level:
                continue
            if (abs(a.xStart - b.xStart) <= tol
                    and abs(a.yStart - b.yStart) <= tol
                    and a.wallAtStart is None):
                a.wallAtStart = b.id
            if (abs(a.xStart - b.xEnd) <= tol
                    and abs(a.yStart - b.yEnd) <= tol
                    and a.wallAtStart is None):
                a.wallAtStart = b.id
            if (abs(a.xEnd - b.xStart) <= tol
                    and abs(a.yEnd - b.yStart) <= tol
                    and a.wallAtEnd is None):
                a.wallAtEnd = b.id
            if (abs(a.xEnd - b.xEnd) <= tol
                    and abs(a.yEnd - b.yEnd) <= tol
                    and a.wallAtEnd is None):
                a.wallAtEnd = b.id


def polygon_walls(polygons: list[list[tuple[float, float]]],
                    *, external_thickness: float = 35.0,
                    internal_thickness: float = 14.0,
                    min_edge_length: float = 8.0,
                    max_room_vertices: int = 20,
                    min_room_area: float = 5000.0):
    """Legacy: generate walls by walking each wall-fill subpath's edges.

    Kept for back-compat with the original ``svg_to_home`` flow; the
    multi-floor entry point uses ``extract_walls`` instead.
    """
    good = [
        p for p in polygons
        if p and len(p) <= max_room_vertices and polygon_area(p) >= min_room_area
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
    if not deduped:
        return [], []
    sorted_polys = sorted(deduped, key=polygon_area, reverse=True)
    outer = sorted_polys[0]
    interiors = sorted_polys[1:]

    def edge_key(p1, p2):
        a = (round(p1[0]), round(p1[1]))
        b = (round(p2[0]), round(p2[1]))
        return (a, b) if a < b else (b, a)

    edge_map: dict[tuple, tuple[float, float, float, float, float]] = {}

    def emit_edges(poly, thickness):
        n = len(poly)
        for j in range(n):
            p1 = poly[j]
            p2 = poly[(j + 1) % n]
            dx, dy = p2[0] - p1[0], p2[1] - p1[1]
            if math.hypot(dx, dy) < min_edge_length:
                continue
            key = edge_key(p1, p2)
            existing = edge_map.get(key)
            if existing is None or thickness > existing[4]:
                edge_map[key] = (p1[0], p1[1], p2[0], p2[1], thickness)

    emit_edges(outer, external_thickness)
    for poly in interiors:
        emit_edges(poly, internal_thickness)

    return list(edge_map.values()), interiors
