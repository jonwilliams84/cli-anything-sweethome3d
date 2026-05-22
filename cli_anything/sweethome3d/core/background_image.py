"""Background plan image — calibrate a PNG/JPG against the home or a level.

SH3D's "Plan > Import background image" workflow loads a raster floorplan,
asks the user to click two points and supply the real-world distance
between them, and stores the result as a `<backgroundImage>` element
inside `<home>` (or inside a `<level>` for per-floor backgrounds).

This module:
- copies the image bytes into the .sh3d ZIP via the Session's content
  queue, picking the next available content-entry id
- builds the `BackgroundImage` dataclass with the calibration the caller
  provides
- attaches it to `home.backgroundImage` (home root) or to a level's
  `backgroundImage` (per-floor overlay)
"""

from __future__ import annotations

import os
from typing import Optional

from cli_anything.sweethome3d.core.model import BackgroundImage, Home, Level
from cli_anything.sweethome3d.core.project import next_content_id


def _resolve_level(home: Home, ident: str) -> Level:
    lvl = home.find_level(ident)
    if lvl is None:
        raise KeyError(f"level not found: {ident}")
    return lvl


def _read_image_bytes(path: str) -> bytes:
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    with open(path, "rb") as f:
        data = f.read()
    if not data:
        raise ValueError(f"background image is empty: {path}")
    return data


def set_background(home: Home, *,
                     image_path: str,
                     scale_distance_cm: float,
                     scale_x_start: float,
                     scale_y_start: float,
                     scale_x_end: float,
                     scale_y_end: float,
                     x_origin: float = 0,
                     y_origin: float = 0,
                     visible: bool = True,
                     level: Optional[str] = None,
                     session_add_content=None
                     ) -> tuple[BackgroundImage, dict[str, bytes]]:
    """Attach a background image to the home or to a level.

    Returns ``(BackgroundImage, extra_content)`` — the dataclass plus a
    ``{entry_name: bytes}`` map that callers must hand to ``Session.save``
    (via ``session_add_content``) so the PNG lands inside the ZIP.

    When ``session_add_content`` is provided, the bytes are queued into the
    session and the returned ``extra_content`` is empty. The split exists so
    pure-Python callers can build a home without a session.
    """
    if scale_distance_cm <= 0:
        raise ValueError("scale_distance_cm must be positive")
    if (scale_x_start == scale_x_end) and (scale_y_start == scale_y_end):
        raise ValueError(
            "scale line endpoints are identical — pick two distinct points"
        )
    data = _read_image_bytes(image_path)
    entry = next_content_id(home)
    bg = BackgroundImage(
        image=entry,
        scaleDistance=scale_distance_cm,
        scaleDistanceXStart=scale_x_start,
        scaleDistanceYStart=scale_y_start,
        scaleDistanceXEnd=scale_x_end,
        scaleDistanceYEnd=scale_y_end,
        xOrigin=x_origin,
        yOrigin=y_origin,
        visible=visible,
    )
    if level is None:
        home.backgroundImage = bg
    else:
        _resolve_level(home, level).backgroundImage = bg
    if session_add_content is not None:
        session_add_content(entry, data)
        return bg, {}
    return bg, {entry: data}


def clear_background(home: Home, *,
                       level: Optional[str] = None) -> bool:
    """Drop the home's or a level's background image. Returns True when
    something was actually cleared."""
    if level is None:
        if home.backgroundImage is None:
            return False
        home.backgroundImage = None
        return True
    lvl = _resolve_level(home, level)
    if lvl.backgroundImage is None:
        return False
    lvl.backgroundImage = None
    return True


def set_visibility(home: Home, *,
                     visible: bool,
                     level: Optional[str] = None) -> BackgroundImage:
    """Toggle a background image's visibility without dropping it."""
    if level is None:
        if home.backgroundImage is None:
            raise ValueError("no home-level background image to toggle")
        home.backgroundImage.visible = visible
        return home.backgroundImage
    lvl = _resolve_level(home, level)
    if lvl.backgroundImage is None:
        raise ValueError(f"level {lvl.name!r} has no background image")
    lvl.backgroundImage.visible = visible
    return lvl.backgroundImage


def get_background(home: Home, *,
                     level: Optional[str] = None) -> Optional[BackgroundImage]:
    """Return the home-level or per-level background image (None if unset)."""
    if level is None:
        return home.backgroundImage
    return _resolve_level(home, level).backgroundImage
