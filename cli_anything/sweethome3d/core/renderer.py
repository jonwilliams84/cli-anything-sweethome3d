"""Floor-plan PNG renderer — pure Python, no Pillow required.

Renders a Designer instance to a PNG file using only stdlib (zlib, struct).
Produces a simple but readable 2-D floor-plan image.

If Pillow is installed it is used automatically for better quality (anti-aliasing,
nicer text). Otherwise falls back to the pure-stdlib path which produces a
valid but lower-quality PNG.
"""

from __future__ import annotations

import math
import os
import struct
import zlib
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from cli_anything.sweethome3d.core.designer import Designer, _Level

# -------------------------------------------------------------------------
# Public entry point
# -------------------------------------------------------------------------

def render_floorplan(
    designer: "Designer",
    path: Path,
    *,
    canvas_width: int = 1200,
    canvas_height: int = 900,
    margin: int = 40,
    dpi: int = 96,
) -> Path:
    """Render a 2-D floor-plan of *designer* to *path* (PNG).

    Parameters
    ----------
    designer      : Designer instance to render
    path          : output file path (.png)
    canvas_width  : pixel width of the output image
    canvas_height : pixel height of the output image
    margin        : pixel margin around the floor-plan
    dpi           : dots per inch (metadata only, not used for layout)

    Returns
    -------
    The resolved output path.

    Example
    -------
    >>> from cli_anything.sweethome3d.core.renderer import render_floorplan
    >>> render_floorplan(designer, Path("Home.png"), canvas_width=1600, canvas_height=1200)
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Try Pillow first
    try:
        _render_with_pillow(designer, path, canvas_width, canvas_height, margin)
        return path
    except ImportError:
        pass

    # Fall back to SVG → PNG via cairosvg
    try:
        import cairosvg  # type: ignore
        svg = designer._to_svg()
        cairosvg.svg2png(bytestring=svg.encode(), write_to=str(path),
                         output_width=canvas_width, output_height=canvas_height)
        return path
    except ImportError:
        pass

    # Pure stdlib fallback
    _render_stdlib(designer, path, canvas_width, canvas_height, margin)
    return path


# -------------------------------------------------------------------------
# Pillow renderer
# -------------------------------------------------------------------------

def _render_with_pillow(
    designer: "Designer",
    path: Path,
    width: int,
    height: int,
    margin: int,
) -> None:
    from PIL import Image, ImageDraw, ImageFont  # type: ignore

    img = Image.new("RGB", (width, height), color=(248, 248, 240))
    draw = ImageDraw.Draw(img)

    transform = _make_transform(designer, width, height, margin)

    # Rooms (filled polygons)
    for lv in designer._levels:
        for r in lv.rooms:
            pts = [transform(p[0], p[1]) for p in r["polygon"]]
            raw = r.get("floor_color") or "#ddd8c4"
            fill = _hex_to_rgb(raw)
            if len(pts) >= 3:
                draw.polygon(pts, fill=fill, outline=(120, 120, 100))
            # Label
            label = r.get("label", "")
            if label and len(pts) >= 3:
                cx = sum(p[0] for p in pts) // len(pts)
                cy = sum(p[1] for p in pts) // len(pts)
                try:
                    font = ImageFont.truetype("arial.ttf", 14)
                except (IOError, OSError):
                    font = ImageFont.load_default()
                draw.text((cx, cy), label, fill=(50, 50, 50), font=font, anchor="mm")

    # Walls
    for lv in designer._levels:
        for w in lv.walls:
            sx, sy = transform(w["start"][0], w["start"][1])
            ex, ey = transform(w["end"][0], w["end"][1])
            is_env = w.get("is_envelope", False)
            color = (30, 30, 30) if is_env else (80, 80, 80)
            lw = 4 if is_env else 2
            draw.line([(sx, sy), (ex, ey)], fill=color, width=lw)

    # Openings
    for lv in designer._levels:
        for o in lv.openings:
            cx, cy = transform(o["x"], o["y"])
            is_door = o["kind"] == "door"
            color = (220, 120, 40) if is_door else (70, 140, 220)
            r = 8
            draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)], fill=color)

    # Title
    try:
        title_font = ImageFont.truetype("arial.ttf", 18)
    except (IOError, OSError):
        title_font = ImageFont.load_default()
    draw.text((margin, 10), designer.name, fill=(30, 30, 30), font=title_font)

    img.save(str(path), "PNG", dpi=(96, 96))


def _make_transform(designer: "Designer", width: int, height: int, margin: int):
    """Return a callable (x_cm, y_cm) → (px, py)."""
    all_pts = []
    for lv in designer._levels:
        for w in lv.walls:
            all_pts.append(w["start"])
            all_pts.append(w["end"])
        for r in lv.rooms:
            all_pts.extend(r["polygon"])

    if not all_pts:
        return lambda x, y: (margin, margin)

    min_x = min(p[0] for p in all_pts)
    min_y = min(p[1] for p in all_pts)
    max_x = max(p[0] for p in all_pts)
    max_y = max(p[1] for p in all_pts)

    drawable_w = width - 2 * margin
    drawable_h = height - 2 * margin
    span_x = max(max_x - min_x, 1.0)
    span_y = max(max_y - min_y, 1.0)
    scale = min(drawable_w / span_x, drawable_h / span_y)

    def transform(x: float, y: float):
        return (
            int(margin + (x - min_x) * scale),
            int(margin + (y - min_y) * scale),
        )

    return transform


def _hex_to_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    if len(h) == 6:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    return (200, 200, 200)


# -------------------------------------------------------------------------
# Pure-stdlib PNG renderer
# -------------------------------------------------------------------------

def _render_stdlib(
    designer: "Designer",
    path: Path,
    width: int,
    height: int,
    margin: int,
) -> None:
    """Write a minimal but valid PNG using only zlib + struct."""

    # Build a pixel buffer (RGB, 3 bytes per pixel)
    pixels = bytearray(width * height * 3)
    # Background: #f8f8f0
    for i in range(width * height):
        pixels[i * 3]     = 248
        pixels[i * 3 + 1] = 248
        pixels[i * 3 + 2] = 240

    transform = _make_transform(designer, width, height, margin)

    def set_px(x: int, y: int, r: int, g: int, b: int):
        if 0 <= x < width and 0 <= y < height:
            off = (y * width + x) * 3
            pixels[off]     = r
            pixels[off + 1] = g
            pixels[off + 2] = b

    def draw_line(x0, y0, x1, y1, r, g, b, thick=1):
        """Bresenham with optional thickness."""
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        x, y = x0, y0
        while True:
            for tx in range(-thick // 2, thick // 2 + 1):
                for ty in range(-thick // 2, thick // 2 + 1):
                    set_px(x + tx, y + ty, r, g, b)
            if x == x1 and y == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x += sx
            if e2 < dx:
                err += dx
                y += sy

    def draw_circle(cx, cy, rad, r, g, b):
        for dx in range(-rad, rad + 1):
            for dy in range(-rad, rad + 1):
                if dx * dx + dy * dy <= rad * rad:
                    set_px(cx + dx, cy + dy, r, g, b)

    # Draw rooms (simple grey fill — no polygon fill in stdlib path)
    # For stdlib we just draw the room polygon outlines
    for lv in designer._levels:
        for room in lv.rooms:
            pts = [transform(p[0], p[1]) for p in room["polygon"]]
            n = len(pts)
            for i in range(n):
                x0, y0 = pts[i]
                x1, y1 = pts[(i + 1) % n]
                draw_line(x0, y0, x1, y1, 140, 120, 90, thick=1)

    # Draw walls
    for lv in designer._levels:
        for w in lv.walls:
            sx, sy = transform(w["start"][0], w["start"][1])
            ex, ey = transform(w["end"][0], w["end"][1])
            is_env = w.get("is_envelope", False)
            if is_env:
                draw_line(sx, sy, ex, ey, 20, 20, 20, thick=3)
            else:
                draw_line(sx, sy, ex, ey, 70, 70, 70, thick=2)

    # Draw openings
    for lv in designer._levels:
        for o in lv.openings:
            cx, cy = transform(o["x"], o["y"])
            if o["kind"] == "door":
                draw_circle(cx, cy, 6, 220, 120, 40)
            else:
                draw_circle(cx, cy, 5, 70, 140, 220)

    # Encode as PNG
    png_bytes = _encode_png_rgb(pixels, width, height)
    path.write_bytes(png_bytes)


def _encode_png_rgb(pixels: bytearray, width: int, height: int) -> bytes:
    """Encode raw RGB pixels as PNG bytes."""

    def chunk(ctype: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(ctype + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + ctype + data + struct.pack(">I", crc)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))

    # Build raw image data (filter byte 0 = None per row)
    raw = bytearray()
    row_bytes = width * 3
    for row in range(height):
        raw += b"\x00"
        start = row * row_bytes
        raw += pixels[start:start + row_bytes]

    idat = chunk(b"IDAT", zlib.compress(bytes(raw), level=6))
    iend = chunk(b"IEND", b"")

    return sig + ihdr + idat + iend
