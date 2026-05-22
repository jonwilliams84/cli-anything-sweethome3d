"""Project health checks — a one-shot sanity sweep.

Agents use this after every batch of mutations to confirm the project
is still loadable / renderable / structurally sound. Each finding has
a code, severity, and human-readable message; ``ok=True`` overall
means nothing failed at WARNING or higher.

Severity levels:
- ``error``   — SH3D will fail to load or render this object correctly
- ``warning`` — looks suspicious; check before rendering
- ``info``    — observed property that's surprising but probably fine
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Optional

from cli_anything.sweethome3d.core.model import (
    FurnitureGroup,
    Home,
    PieceOfFurniture,
)


SEVERITY_ORDER = {"info": 0, "warning": 1, "error": 2}


@dataclass
class Finding:
    code: str        # short stable identifier (e.g. "wall.unlinked")
    severity: str    # error | warning | info
    message: str
    target_id: Optional[str] = None
    target_name: Optional[str] = None
    extra: dict = field(default_factory=dict)


@dataclass
class ValidationReport:
    findings: list[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when no findings reach `warning` severity or higher."""
        return all(SEVERITY_ORDER[f.severity] < 1 for f in self.findings)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "warning"]

    @property
    def infos(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "info"]

    def by_code(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for f in self.findings:
            out[f.code] = out.get(f.code, 0) + 1
        return out


# ─────────────────────── individual checks

def _iter_all_pieces(home: Home) -> Iterable[PieceOfFurniture]:
    """Yield every PieceOfFurniture in the home, including those nested
    inside furniture groups."""
    for f in home.furniture:
        yield f

    def _walk(items):
        for member in items:
            if isinstance(member, FurnitureGroup):
                yield from _walk(member.furniture)
            elif isinstance(member, PieceOfFurniture):
                yield member
    yield from _walk(home.furnitureGroups)


def _check_walls(home: Home) -> list[Finding]:
    out = []
    for w in home.walls:
        # Zero length
        if w.xStart == w.xEnd and w.yStart == w.yEnd:
            out.append(Finding(
                code="wall.zero_length",
                severity="error",
                message="wall endpoints coincide (zero-length wall)",
                target_id=w.id,
            ))
            continue
        # Unlinked (informational at low scale, warning when widespread)
        if not w.wallAtStart and not w.wallAtEnd:
            out.append(Finding(
                code="wall.unlinked",
                severity="info",
                message="wall has no neighbours (no wallAtStart / wallAtEnd)",
                target_id=w.id,
            ))
        # Negative or wildly off-spec thickness
        if w.thickness <= 0:
            out.append(Finding(
                code="wall.bad_thickness",
                severity="error",
                message=f"wall thickness is {w.thickness!r}; must be > 0",
                target_id=w.id,
            ))
    return out


def _polygon_area(points) -> float:
    n = len(points)
    if n < 3:
        return 0.0
    a = 0.0
    for i in range(n):
        j = (i + 1) % n
        a += points[i].x * points[j].y - points[j].x * points[i].y
    return abs(a) / 2.0


def _check_rooms(home: Home) -> list[Finding]:
    out = []
    for r in home.rooms:
        if len(r.points) < 3:
            out.append(Finding(
                code="room.degenerate",
                severity="error",
                message=f"room has {len(r.points)} points (< 3); cannot render",
                target_id=r.id,
                target_name=r.name,
            ))
            continue
        a = _polygon_area(r.points)
        if a < 1.0:  # less than 1 cm²
            out.append(Finding(
                code="room.zero_area",
                severity="error",
                message="room polygon has near-zero area",
                target_id=r.id,
                target_name=r.name,
                extra={"area_cm2": a},
            ))
        elif a < 5000:  # less than 0.5 m²
            out.append(Finding(
                code="room.tiny",
                severity="warning",
                message=f"room area is only {a/10000:.2f} m² "
                         "(likely an importer fragment)",
                target_id=r.id,
                target_name=r.name,
                extra={"area_cm2": a},
            ))
        if not r.name:
            out.append(Finding(
                code="room.unnamed",
                severity="info",
                message="room has no name",
                target_id=r.id,
                extra={"area_cm2": a},
            ))
    return out


def _check_furniture(home: Home) -> list[Finding]:
    out = []
    for f in _iter_all_pieces(home):
        # Bad dimensions
        if f.width <= 0 or f.depth <= 0 or f.height <= 0:
            out.append(Finding(
                code="furniture.bad_size",
                severity="error",
                message=(
                    f"piece has non-positive dimension: "
                    f"w={f.width} d={f.depth} h={f.height}"
                ),
                target_id=f.id,
                target_name=f.name,
            ))
        # Lights with no power
        if f.kind == "light" and (f.power is None or f.power <= 0):
            out.append(Finding(
                code="light.no_power",
                severity="warning",
                message="light piece has no power set (will not illuminate)",
                target_id=f.id,
                target_name=f.name,
            ))
        # Catalog id with no model reference and not in the stock catalog
        if f.catalogId and not f.model:
            from cli_anything.sweethome3d.core._sh3d_catalog_metadata import SH3D_CATALOG
            if f.catalogId not in SH3D_CATALOG:
                out.append(Finding(
                    code="furniture.unknown_catalog",
                    severity="warning",
                    message=(
                        f"catalogId {f.catalogId!r} is not in the bundled "
                        "Furniture.jar and the piece has no embedded model — "
                        "will render as 'damaged' in SH3D"
                    ),
                    target_id=f.id,
                    target_name=f.name,
                    extra={"catalogId": f.catalogId},
                ))
    return out


def _check_levels(home: Home) -> list[Finding]:
    out = []
    valid_ids = {lvl.id for lvl in home.levels}
    if not valid_ids:
        return out  # legacy single-level project, nothing to validate
    for source_label, items in (
        ("wall", home.walls),
        ("room", home.rooms),
        ("furniture", list(_iter_all_pieces(home))),
        ("dimensionLine", home.dimensionLines),
        ("label", home.labels),
        ("polyline", home.polylines),
    ):
        for obj in items:
            level_ref = getattr(obj, "level", None)
            if level_ref and level_ref not in valid_ids:
                out.append(Finding(
                    code=f"{source_label}.dangling_level",
                    severity="error",
                    message=(
                        f"{source_label} references missing level "
                        f"{level_ref!r}"
                    ),
                    target_id=getattr(obj, "id", None),
                    target_name=getattr(obj, "name", None),
                ))
    return out


def _check_doors_bound(home: Home) -> list[Finding]:
    """Doors/windows that don't sit on any wall on their level."""
    out = []
    from cli_anything.sweethome3d.core.svg.geometry import point_to_segment_dist
    for f in _iter_all_pieces(home):
        if f.kind != "doorOrWindow":
            continue
        if f.boundToWall is False:
            continue  # explicitly unbound — user's call
        # Find any wall on the same level whose centerline passes within
        # (piece.width/2 + small margin) of the piece centre.
        radius = max(20.0, f.width / 2 + 5.0)
        hit = False
        for w in home.walls:
            if w.level != f.level:
                continue
            d = point_to_segment_dist(f.x, f.y,
                                        w.xStart, w.yStart, w.xEnd, w.yEnd)
            if d <= radius:
                hit = True
                break
        if not hit:
            out.append(Finding(
                code="door.no_host_wall",
                severity="warning",
                message="doorOrWindow is not adjacent to any wall on its level",
                target_id=f.id,
                target_name=f.name,
                extra={"x": f.x, "y": f.y, "level": f.level},
            ))
    return out


def validate(home: Home, *,
              include_info: bool = True) -> ValidationReport:
    """Run every health check and return a ValidationReport.

    `include_info`=False suppresses purely informational findings
    (unnamed rooms, unlinked walls) — useful when piping into CI gates
    that only care about errors/warnings.
    """
    findings: list[Finding] = []
    findings += _check_walls(home)
    findings += _check_rooms(home)
    findings += _check_furniture(home)
    findings += _check_levels(home)
    findings += _check_doors_bound(home)
    if not include_info:
        findings = [f for f in findings if f.severity != "info"]
    findings.sort(key=lambda f: (-SEVERITY_ORDER[f.severity], f.code))
    return ValidationReport(findings=findings)
