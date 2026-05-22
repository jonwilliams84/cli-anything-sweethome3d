"""Dimension lines, labels, polylines, compass — annotation entities."""

from __future__ import annotations

from typing import Optional

from cli_anything.sweethome3d.core.model import (
    Compass,
    DimensionLine,
    Home,
    Label,
    Point,
    Polyline,
)


# ─── dimension lines ────────────────────────────────────────────────────────

def list_dimensions(home: Home, *, level: Optional[str] = None) -> list[DimensionLine]:
    items = home.dimensionLines
    if level is not None:
        items = [d for d in items if d.level == level]
    return list(items)


def add_dimension(home: Home, xStart: float, yStart: float,
                    xEnd: float, yEnd: float, *,
                    offset: float = 0, level: Optional[str] = None,
                    color: Optional[int] = None) -> DimensionLine:
    if (xStart, yStart) == (xEnd, yEnd):
        raise ValueError("dimension start and end coincide")
    d = DimensionLine(xStart=xStart, yStart=yStart, xEnd=xEnd, yEnd=yEnd,
                       offset=offset, level=level, color=color)
    home.dimensionLines.append(d)
    return d


def delete_dimension(home: Home, ident: str) -> bool:
    for d in home.dimensionLines:
        if d.id == ident:
            home.dimensionLines.remove(d)
            return True
    return False


# ─── labels ─────────────────────────────────────────────────────────────────

def list_labels(home: Home, *, level: Optional[str] = None) -> list[Label]:
    items = home.labels
    if level is not None:
        items = [l for l in items if l.level == level]
    return list(items)


def add_label(home: Home, text: str, x: float, y: float, *,
               level: Optional[str] = None,
               angle: float = 0,
               color: Optional[int] = None) -> Label:
    if not text:
        raise ValueError("label text must not be empty")
    l = Label(text=text, x=x, y=y, level=level, angle=angle, color=color)
    home.labels.append(l)
    return l


def delete_label(home: Home, ident: str) -> bool:
    for l in home.labels:
        if l.id == ident:
            home.labels.remove(l)
            return True
    return False


# ─── polylines ──────────────────────────────────────────────────────────────

def list_polylines(home: Home, *, level: Optional[str] = None) -> list[Polyline]:
    items = home.polylines
    if level is not None:
        items = [p for p in items if p.level == level]
    return list(items)


def add_polyline(home: Home, points: list[tuple[float, float]], *,
                   thickness: float = 1,
                   color: Optional[int] = None,
                   closedPath: bool = False,
                   level: Optional[str] = None) -> Polyline:
    if len(points) < 2:
        raise ValueError("a polyline requires at least 2 points")
    p = Polyline(points=[Point(x, y) for x, y in points],
                  thickness=thickness, color=color,
                  closedPath=closedPath, level=level)
    home.polylines.append(p)
    return p


def delete_polyline(home: Home, ident: str) -> bool:
    for p in home.polylines:
        if p.id == ident:
            home.polylines.remove(p)
            return True
    return False


# ─── compass ────────────────────────────────────────────────────────────────

def get_compass(home: Home) -> Compass:
    return home.compass


def set_compass(home: Home, *,
                  x: Optional[float] = None, y: Optional[float] = None,
                  diameter: Optional[float] = None,
                  northDirection: Optional[float] = None,
                  longitude: Optional[float] = None,
                  latitude: Optional[float] = None,
                  timeZone: Optional[str] = None,
                  visible: Optional[bool] = None) -> Compass:
    c = home.compass
    if x is not None: c.x = x
    if y is not None: c.y = y
    if diameter is not None: c.diameter = diameter
    if northDirection is not None: c.northDirection = northDirection
    if longitude is not None: c.longitude = longitude
    if latitude is not None: c.latitude = latitude
    if timeZone is not None: c.timeZone = timeZone
    if visible is not None: c.visible = visible
    return c
