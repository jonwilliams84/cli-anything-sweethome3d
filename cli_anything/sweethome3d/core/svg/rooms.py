"""Room-label extraction + name-driven floor-colour mapping.

Inkscape duplicates ``<text>`` elements on save (one per font weight),
so we collapse near-duplicates by lowercase name + rounded position.
Dimension strings like ``"60.75 m² (8.41 × 7.68)"`` are filtered out.

``extract_rooms_from_walls`` performs planar-subdivision face traversal on the
welded wall graph so that every enclosed interior face becomes a SH3D Room.
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from typing import Optional

from cli_anything.sweethome3d.core.svg.parse import (
    IDENT,
    apply,
    mul,
    parse_transform,
)
from cli_anything.sweethome3d.core.svg.spec import (
    COLOR_CARPET_BEIGE,
    COLOR_CARPET_DARK,
    COLOR_OAK,
)


def extract_room_labels(svg_root: ET.Element) -> list[tuple[str, float, float]]:
    """Find textual room labels in the SVG with their absolute positions.

    Used to colour rooms based on their name (Master gets dark grey
    carpet, landing gets beige, etc.). Skips numeric-only labels and
    area annotations like ``"60.75 m²"``.
    """
    def first_float(s):
        if not s:
            return 0.0
        for p in re.split(r"[\s,]+", s.strip()):
            try:
                return float(p)
            except ValueError:
                continue
        return 0.0

    out: list[tuple[str, float, float]] = []
    seen: set[tuple[str, int, int]] = set()

    def visit(el, parent_xform):
        my_xform = mul(parent_xform, parse_transform(el.get("transform", "")))
        if el.tag == "text":
            parts = []
            for t in el.iter("tspan"):
                if t.text:
                    parts.append(t.text.strip())
            if el.text:
                parts.append(el.text.strip())
            txt = " ".join(p for p in parts if p)
            if not txt or "m²" in txt or re.match(r"^[\d.,\s×x]+$", txt):
                pass
            else:
                x = first_float(el.get("x"))
                y = first_float(el.get("y"))
                for t in el.iter("tspan"):
                    if t.get("x"):
                        x = first_float(t.get("x"))
                    if t.get("y"):
                        y = first_float(t.get("y"))
                    break
                ax, ay = apply(my_xform, x, y)
                key = (txt.lower(), round(ax), round(ay))
                if key not in seen:
                    seen.add(key)
                    out.append((txt, ax, ay))
        for child in el:
            visit(child, my_xform)

    visit(svg_root, IDENT)
    return out


def floor_color_for(name: str, level_name: str) -> int:
    """Hard-coded fallback. The spec-driven path in ``pipeline`` uses
    ``rooms.by_level`` overrides instead and only falls back to this
    when no spec is supplied.
    """
    lname = (name or "").lower()
    if level_name.lower() != "ground":
        if "master" in lname or "wardrobe" in lname or "ensuite" in lname:
            return COLOR_CARPET_DARK
        return COLOR_CARPET_BEIGE
    return COLOR_OAK


# ---------------------------------------------------------------------------
# Closed-loop auto-room extraction via planar-subdivision face traversal
# ---------------------------------------------------------------------------

def _signed_area(pts: list[tuple[float, float]]) -> float:
    """Signed area of a polygon (shoelace). Positive = CCW in standard math
    coords (Y-up); in SH3D's Y-down screen space CCW here = CW visually."""
    n = len(pts)
    if n < 3:
        return 0.0
    a = 0.0
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return a / 2.0


def extract_rooms_from_walls(
    walls,
    level_id: Optional[str] = None,
    *,
    envelope: Optional[list[tuple[float, float]]] = None,
    min_area_cm2: float = 5000.0,
) -> list[list[tuple[float, float]]]:
    """Walk the welded wall graph and return one polygon per interior face.

    Algorithm (planar-subdivision half-edge traversal):
    1. Build a graph: each wall yields two directed half-edges (A→B and B→A).
    2. At each node sort incident outgoing half-edges by angle.
    3. For each half-edge the *next clockwise* edge at the destination is
       the one that comes immediately after the reverse direction in the
       sorted adjacency list.
    4. Traverse faces by following next-clockwise links until we return to
       the start half-edge.
    5. Discard the single outer (unbounded) face — identified as the face
       with the largest absolute area or with negative signed area in our
       coordinate convention.
    6. Filter faces by ``min_area_cm2`` and (optionally) by requiring the
       face centroid to lie inside ``envelope``.

    Returns a list of ``[(x, y), ...]`` polygon point lists, one per
    interior face.  Points are in the original wall coordinate space (not
    offset-adjusted).
    """
    if not walls:
        return []

    # --- 1. Collect unique nodes -----------------------------------------
    # Round to 2 decimal places so near-identical welded endpoints share
    # the same node key without requiring exact float equality.
    PREC = 2

    def snap(v: float) -> float:
        return round(v, PREC)

    def node_key(x: float, y: float) -> tuple[float, float]:
        return (snap(x), snap(y))

    # Map node_key → integer node id
    node_ids: dict[tuple[float, float], int] = {}
    nodes: list[tuple[float, float]] = []

    def get_node(x: float, y: float) -> int:
        k = node_key(x, y)
        if k not in node_ids:
            node_ids[k] = len(nodes)
            nodes.append(k)
        return node_ids[k]

    # --- 2. Build half-edges ---------------------------------------------
    # Each wall (A, B) yields half-edges (A→B) and (B→A).
    # Half-edge = (from_node, to_node, he_index)
    half_edges: list[tuple[int, int]] = []  # (src, dst)

    for xs, ys, xe, ye, _t in walls:
        a = get_node(xs, ys)
        b = get_node(xe, ye)
        if a == b:
            continue  # degenerate — skip zero-length walls
        half_edges.append((a, b))  # forward
        half_edges.append((b, a))  # reverse

    if not half_edges:
        return []

    n_he = len(half_edges)

    # For each node build a sorted list of outgoing half-edge indices by angle
    adj: dict[int, list[int]] = {}
    for he_idx, (src, dst) in enumerate(half_edges):
        adj.setdefault(src, []).append(he_idx)

    for src, he_list in adj.items():
        nx, ny = nodes[src]
        he_list.sort(key=lambda i: math.atan2(
            nodes[half_edges[i][1]][1] - ny,
            nodes[half_edges[i][1]][0] - nx,
        ))

    # --- 3. next-clockwise twin ------------------------------------------
    # For half-edge he=(u→v) the next-CW half-edge at v is:
    # - find the reverse (v→u) in v's sorted adjacency list
    # - the entry BEFORE it in that list (wrapping around)
    # This traces interior faces (the face to the left of each half-edge in
    # a Y-down coordinate system).

    # Build a fast lookup: (src, dst) → he_index
    he_lookup: dict[tuple[int, int], int] = {}
    for i, (s, d) in enumerate(half_edges):
        he_lookup[(s, d)] = i

    def next_he(he_idx: int) -> int:
        """Return the next half-edge index when traversing an interior face."""
        src, dst = half_edges[he_idx]
        # The reverse half-edge is (dst → src)
        # Find its position in dst's adjacency list
        dlist = adj[dst]
        rev_he = he_lookup[(dst, src)]
        pos = dlist.index(rev_he)
        # Next-CW = position BEFORE reverse in CCW-sorted list (mod n)
        # (our atan2 sort is CCW; stepping back one gives CW next-edge)
        next_pos = (pos - 1) % len(dlist)
        return dlist[next_pos]

    # --- 4. Traverse all faces ------------------------------------------
    visited: set[int] = set()
    faces: list[list[tuple[float, float]]] = []

    for start in range(n_he):
        if start in visited:
            continue
        face_pts: list[tuple[float, float]] = []
        cur = start
        face_he: list[int] = []
        # Guard against infinite loops (shouldn't happen in a planar graph,
        # but protect against degenerate inputs)
        limit = n_he + 2
        steps = 0
        while cur not in visited and steps < limit:
            visited.add(cur)
            face_he.append(cur)
            src, _dst = half_edges[cur]
            face_pts.append(nodes[src])
            cur = next_he(cur)
            steps += 1

        if len(face_pts) >= 3:
            faces.append(face_pts)

    if not faces:
        return []

    # --- 5. Discard the outer (unbounded) face ---------------------------
    # In SH3D's Y-down coordinate space the outer face is the one with
    # the *largest absolute area*.  We also discard faces with fewer than
    # 3 unique vertices.
    def abs_area(pts: list[tuple[float, float]]) -> float:
        return abs(_signed_area(pts))

    faces.sort(key=abs_area, reverse=True)
    # The largest face is the outer unbounded face — drop it.
    interior_faces = faces[1:]

    # --- 6. Filter by area and envelope ----------------------------------
    result: list[list[tuple[float, float]]] = []
    for pts in interior_faces:
        area = abs_area(pts)
        if area < min_area_cm2:
            continue
        if envelope is not None and len(envelope) >= 3:
            from cli_anything.sweethome3d.core.svg.geometry import point_in_polygon
            cx = sum(x for x, _ in pts) / len(pts)
            cy = sum(y for _, y in pts) / len(pts)
            if not point_in_polygon(cx, cy, envelope):
                continue
        result.append(pts)

    return result


def _polygon_centroid_and_area(
    pts: list[tuple[float, float]],
) -> tuple[float, float, float]:
    """Return (cx, cy, abs_area) for a polygon."""
    n = len(pts)
    if n < 3:
        return 0.0, 0.0, 0.0
    a = cx = cy = 0.0
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    a *= 0.5
    if abs(a) < 1e-9:
        cx_ = sum(x for x, _ in pts) / n
        cy_ = sum(y for _, y in pts) / n
        return cx_, cy_, 0.0
    cx /= 6 * a
    cy /= 6 * a
    return cx, cy, abs(a)


def auto_rooms_overlap_labelled(
    auto_pts: list[tuple[float, float]],
    labelled_rooms_pts: list[list[tuple[float, float]]],
    *,
    overlap_threshold: float = 0.5,
) -> bool:
    """Return True if the auto-room polygon significantly overlaps any labelled room.

    .. deprecated::
        No longer used by the pipeline. All rooms now come from
        ``extract_rooms_from_walls`` (auto-rooms) and names are attached via
        ``extract_room_labels`` + point-in-polygon. Kept for backwards
        compatibility with any external callers.

    Uses a centroid-in-polygon test as a fast approximation:
    - If the auto-room's centroid falls inside a labelled polygon, they overlap.
    - If a labelled room's centroid falls inside the auto-room polygon, they overlap.
    An area-ratio guard prevents accepting tiny shared corners as "overlapping".
    """
    from cli_anything.sweethome3d.core.svg.geometry import point_in_polygon

    if not auto_pts or not labelled_rooms_pts:
        return False

    acx, acy, auto_area = _polygon_centroid_and_area(auto_pts)
    if auto_area < 1.0:
        return False

    for lab_pts in labelled_rooms_pts:
        lcx, lcy, lab_area = _polygon_centroid_and_area(lab_pts)
        if lab_area < 1.0:
            continue
        # Centroid of auto inside labelled, or vice-versa
        if point_in_polygon(acx, acy, lab_pts):
            ratio = min(auto_area, lab_area) / max(auto_area, lab_area)
            if ratio >= overlap_threshold:
                return True
        if point_in_polygon(lcx, lcy, auto_pts):
            ratio = min(auto_area, lab_area) / max(auto_area, lab_area)
            if ratio >= overlap_threshold:
                return True
    return False
