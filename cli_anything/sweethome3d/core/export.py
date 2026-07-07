"""Export — top-down SVG plan from a Home model.

This is the harness's introspection surface: every other write command can be
verified by exporting the plan as SVG and visually inspecting it.

The render pipeline for photorealistic output (perspective 3D) lives in
``core.render`` and requires the real Sweet Home 3D binary.
"""

from __future__ import annotations

import math
import os
from xml.etree import ElementTree as ET

from cli_anything.sweethome3d.core.model import Home


def _color_to_svg(color: int | None, default: str) -> str:
    if color is None:
        return default
    rgb = color & 0xFFFFFF
    return f"#{rgb:06X}"


def _bounds(home: Home) -> tuple[float, float, float, float]:
    """Return (xMin, yMin, xMax, yMax) in SH3D centimetre coordinates.

    Considers walls, rooms, and furniture positions. Falls back to a
    100×100 region centred on origin when the home is empty.
    """
    xs: list[float] = []
    ys: list[float] = []
    for w in home.walls:
        xs.extend([w.xStart, w.xEnd])
        ys.extend([w.yStart, w.yEnd])
    for r in home.rooms:
        for p in r.points:
            xs.append(p.x); ys.append(p.y)
    for f in home.furniture:
        # bounding circle of the rotated piece; good enough for framing
        rad = max(f.width, f.depth) / 2
        xs.extend([f.x - rad, f.x + rad])
        ys.extend([f.y - rad, f.y + rad])
    for d in home.dimensionLines:
        xs.extend([d.xStart, d.xEnd])
        ys.extend([d.yStart, d.yEnd])
    for lbl in home.labels:
        xs.append(lbl.x); ys.append(lbl.y)
    if not xs:
        return -50, -50, 50, 50
    return min(xs), min(ys), max(xs), max(ys)


def _wall_polygon(w) -> list[tuple[float, float]]:
    """Compute the 4-corner polygon of a wall in plan-view coordinates."""
    dx = w.xEnd - w.xStart
    dy = w.yEnd - w.yStart
    L = math.hypot(dx, dy)
    if L == 0:
        return [(w.xStart, w.yStart)] * 4
    # unit normal (left side)
    nx = -dy / L
    ny = dx / L
    t = w.thickness / 2
    return [
        (w.xStart + nx * t, w.yStart + ny * t),
        (w.xEnd   + nx * t, w.yEnd   + ny * t),
        (w.xEnd   - nx * t, w.yEnd   - ny * t),
        (w.xStart - nx * t, w.yStart - ny * t),
    ]


def _furniture_polygon(f) -> list[tuple[float, float]]:
    """Footprint of a piece of furniture (rotated rectangle)."""
    hw, hd = f.width / 2, f.depth / 2
    cos_a = math.cos(f.angle)
    sin_a = math.sin(f.angle)
    corners = [(-hw, -hd), (hw, -hd), (hw, hd), (-hw, hd)]
    return [(f.x + cx * cos_a - cy * sin_a,
              f.y + cx * sin_a + cy * cos_a)
             for cx, cy in corners]


def _resolve_level(home: Home, spec: str) -> str:
    """Resolve a level spec (id or name) to a level id.

    Matching is whitespace-trimmed and case-insensitive on both id and name.
    Raises ValueError if the spec matches no level.
    """
    s = spec.strip()
    for lvl in home.levels:
        if lvl.id.strip().lower() == s.lower() or (lvl.name and lvl.name.strip().lower() == s.lower()):
            return lvl.id
    known = sorted({lvl.id for lvl in home.levels} | {lvl.name for lvl in home.levels if lvl.name})
    raise ValueError(
        f"unknown level spec: {spec!r}. Known ids/names: {known!r}"
    )


def to_svg(home: Home, *,
           padding: float = 50,
           scale: float = 1.0,
           level: str | None = None) -> str:
    """Render the home plan to an SVG string.

    `padding` is the surrounding margin in cm.
    `scale` is a unit multiplier (1.0 = 1 cm per SVG unit).
    `level` filters to a single level (accepts a level id or name);
    None shows the unfiltered top level.
    """
    if level is not None:
        resolved = _resolve_level(home, level)
        filt = lambda obj: obj.level == resolved  # noqa: E731
    else:
        filt = lambda obj: True  # noqa: E731

    xMin, yMin, xMax, yMax = _bounds(home)
    xMin -= padding; yMin -= padding
    xMax += padding; yMax += padding
    width = (xMax - xMin) * scale
    height = (yMax - yMin) * scale

    svg = ET.Element("svg", {
        "xmlns": "http://www.w3.org/2000/svg",
        "viewBox": f"{xMin} {yMin} {xMax - xMin} {yMax - yMin}",
        "width": str(width),
        "height": str(height),
    })
    # title for accessibility/inspection
    title = ET.SubElement(svg, "title")
    title.text = home.name or "Sweet Home 3D plan"

    # background
    ET.SubElement(svg, "rect", {
        "x": str(xMin), "y": str(yMin),
        "width": str(xMax - xMin), "height": str(yMax - yMin),
        "fill": "#FAFAFA",
    })

    # rooms (floor polygons)
    g_rooms = ET.SubElement(svg, "g", {"id": "rooms"})
    for r in home.rooms:
        if not filt(r) or not r.points:
            continue
        fill = _color_to_svg(r.floorColor, "#E8E8E8")
        points_str = " ".join(f"{p.x},{p.y}" for p in r.points)
        ET.SubElement(g_rooms, "polygon", {
            "points": points_str,
            "fill": fill, "stroke": "#888", "stroke-width": "1",
            "fill-opacity": "0.6",
        })
        if r.name:
            cx = sum(p.x for p in r.points) / len(r.points)
            cy = sum(p.y for p in r.points) / len(r.points)
            label = ET.SubElement(g_rooms, "text", {
                "x": str(cx), "y": str(cy),
                "text-anchor": "middle", "font-size": "30",
                "font-family": "sans-serif", "fill": "#333",
            })
            label.text = r.name

    # collect doorOrWindow footprints — used both as a wall-mask and as
    # opening overlays. Pre-compute polygons once.
    openings: list[tuple[object, list[tuple[float, float]]]] = []
    for f in home.furniture:
        if not filt(f) or f.kind != "doorOrWindow":
            continue
        openings.append((f, _furniture_polygon(f)))

    # walls (filled rectangles for thickness) with openings cut out via mask
    g_walls = ET.SubElement(svg, "g", {"id": "walls"})
    wall_polys: list[tuple[object, list[tuple[float, float]]]] = [
        (w, _wall_polygon(w)) for w in home.walls if filt(w)
    ]

    mask_id = "walls-cutout"
    if openings and wall_polys:
        defs = ET.SubElement(svg, "defs")
        mask = ET.SubElement(defs, "mask", {
            "id": mask_id,
            "maskUnits": "userSpaceOnUse",
            "x": str(xMin), "y": str(yMin),
            "width": str(xMax - xMin), "height": str(yMax - yMin),
        })
        # White = keep, black = cut. Paint each wall white, each opening black.
        for _, poly in wall_polys:
            ET.SubElement(mask, "polygon", {
                "points": " ".join(f"{x},{y}" for x, y in poly),
                "fill": "white",
            })
        for _, poly in openings:
            ET.SubElement(mask, "polygon", {
                "points": " ".join(f"{x},{y}" for x, y in poly),
                "fill": "black",
            })
        g_walls.set("mask", f"url(#{mask_id})")

    for w, poly in wall_polys:
        fill = _color_to_svg(w.leftSideColor, "#444")
        ET.SubElement(g_walls, "polygon", {
            "points": " ".join(f"{x},{y}" for x, y in poly), "fill": fill,
            "stroke": "#222", "stroke-width": "0.5",
        })

    # openings — rendered ON TOP of the (now-cut) walls so the user sees
    # the door/window glass/frame. Drawn with thinner stroke so the cut-out
    # is visually clear.
    g_open = ET.SubElement(svg, "g", {"id": "openings"})
    for f, poly in openings:
        is_window = (f.elevation is not None and f.elevation > 0)
        color = "#BFE0FF" if is_window else "#FFF6E0"
        fill = _color_to_svg(f.color, color)
        ET.SubElement(g_open, "polygon", {
            "points": " ".join(f"{x},{y}" for x, y in poly),
            "fill": fill, "fill-opacity": "0.85",
            "stroke": "#3A6FB0" if is_window else "#7A5A2A",
            "stroke-width": "0.6",
        })

    # furniture (non-opening pieces only)
    g_furn = ET.SubElement(svg, "g", {"id": "furniture"})
    for f in home.furniture:
        if not filt(f) or f.kind == "doorOrWindow":
            continue
        if f.kind == "light":
            ET.SubElement(g_furn, "circle", {
                "cx": str(f.x), "cy": str(f.y),
                "r": str(max(f.width, f.depth) / 2),
                "fill": _color_to_svg(f.color, "#FFEB99"),
                "stroke": "#C8A52A", "stroke-width": "1",
            })
        else:
            poly = _furniture_polygon(f)
            fill = _color_to_svg(f.color, "#C8A878")
            ET.SubElement(g_furn, "polygon", {
                "points": " ".join(f"{x},{y}" for x, y in poly), "fill": fill,
                "stroke": "#555", "stroke-width": "0.7",
            })
            if f.name and f.nameVisible:
                label = ET.SubElement(g_furn, "text", {
                    "x": str(f.x), "y": str(f.y),
                    "text-anchor": "middle", "font-size": "10",
                    "font-family": "sans-serif", "fill": "#222",
                })
                label.text = f.name

    # dimension lines
    g_dims = ET.SubElement(svg, "g", {"id": "dimensions"})
    for d in home.dimensionLines:
        if not filt(d):
            continue
        color = _color_to_svg(d.color, "#0066CC")
        ET.SubElement(g_dims, "line", {
            "x1": str(d.xStart), "y1": str(d.yStart),
            "x2": str(d.xEnd),   "y2": str(d.yEnd),
            "stroke": color, "stroke-width": "0.8",
        })

    # labels
    g_lbl = ET.SubElement(svg, "g", {"id": "labels"})
    for lbl in home.labels:
        if not filt(lbl):
            continue
        text = ET.SubElement(g_lbl, "text", {
            "x": str(lbl.x), "y": str(lbl.y),
            "font-size": "12", "font-family": "sans-serif",
            "fill": _color_to_svg(lbl.color, "#222"),
            "transform": f"rotate({math.degrees(lbl.angle)} {lbl.x} {lbl.y})"
                          if lbl.angle else None,
        })
        # remove transform attr if it was None
        if not lbl.angle:
            text.attrib.pop("transform", None)
        text.text = lbl.text

    # compass marker
    if home.compass.visible:
        cx, cy, dia = home.compass.x, home.compass.y, home.compass.diameter
        g_comp = ET.SubElement(svg, "g", {"id": "compass"})
        ET.SubElement(g_comp, "circle", {
            "cx": str(cx), "cy": str(cy),
            "r": str(dia / 2),
            "fill": "none", "stroke": "#999", "stroke-width": "0.8",
        })
        # north arrow rotated by northDirection
        sin_a = math.sin(home.compass.northDirection)
        cos_a = math.cos(home.compass.northDirection)
        nx = cx - sin_a * (dia / 2 - 5)
        ny = cy - cos_a * (dia / 2 - 5)
        ET.SubElement(g_comp, "line", {
            "x1": str(cx), "y1": str(cy),
            "x2": str(nx), "y2": str(ny),
            "stroke": "#C00", "stroke-width": "1.5",
        })

    return ET.tostring(svg, encoding="unicode")


def export_svg(home: Home, output_path: str, **kwargs) -> str:
    """Render plan to SVG, write to `output_path`, return the path."""
    out_dir = os.path.dirname(output_path) or "."
    os.makedirs(out_dir, exist_ok=True)
    svg = to_svg(home, **kwargs)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write(svg)
    return output_path
