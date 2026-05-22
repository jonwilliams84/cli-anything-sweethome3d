"""Discover catalog ids from real sources — installed .sh3f libraries
and pieces already used inside an open .sh3d project.

The existing :mod:`catalog` and :mod:`_sh3d_catalog_metadata` modules
hard-code a curated subset of stock SH3D entries. Real homes drawn by
real designers lean heavily on community contributions
(``petersmolik-door1``, ``katorlegaz-exterior-door-01``,
``geantick-garagedoor``, …) which never appear in the curated list. This
module fills that gap by reading two real sources:

- **Furniture .jar / .sh3f files** — Java properties files following the
  ``id#N=…``, ``name#N=…`` indexed convention. SH3D's `Furniture.jar`
  contains `DefaultFurnitureCatalog.properties` and `.sh3f` plugin
  libraries contain `PluginFurnitureCatalog.properties`. Same format.
- **A loaded .sh3d project's furniture list** — every piece already
  carries its `catalogId`, `model`, and `icon` from when it was first
  added in SH3D, so an open project is itself a catalog of "ids that
  work, with their real model paths".
"""

from __future__ import annotations

import os
import zipfile
from dataclasses import dataclass, field
from typing import Optional

from cli_anything.sweethome3d.core.model import Home


@dataclass
class ScanEntry:
    catalogId: str
    name: Optional[str] = None
    category: Optional[str] = None
    kind: str = "pieceOfFurniture"  # pieceOfFurniture | doorOrWindow | light
    width: Optional[float] = None
    depth: Optional[float] = None
    height: Optional[float] = None
    model: Optional[str] = None
    icon: Optional[str] = None
    creator: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    source: Optional[str] = None     # which .jar / .sh3f / project the entry came from


# ─────────────────────── properties parsing

def parse_catalog_properties(text: str) -> list[ScanEntry]:
    """Parse a Java `*.properties` catalog file (DefaultFurnitureCatalog
    or PluginFurnitureCatalog format) into ScanEntry objects.

    The format uses indexed keys: ``id#1=…``, ``name#1=…``, ``category#1=…``,
    `width#1=…`, … Empty lines and ``#``-prefixed comments are ignored
    (with the exception of the `key#N=value` pattern that uses `#` as a
    legitimate separator between key and index).
    """
    by_index: dict[str, dict[str, str]] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        # Detect the index separator: a literal `#` followed by digits, then `=`
        # so we don't confuse it with leading-`#` comments.
        if "=" not in line:
            continue
        if line.startswith("#") and "#" not in line[1:].split("=", 1)[0]:
            # Pure comment (no embedded index marker)
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if "#" not in key:
            # Catalog-level metadata (id, name, description, version, …)
            # — we keep these under the synthetic index "_meta"
            by_index.setdefault("_meta", {})[key] = value
            continue
        base, _, idx = key.rpartition("#")
        if not idx.isdigit():
            continue
        by_index.setdefault(idx, {})[base] = value

    out: list[ScanEntry] = []
    for idx, props in by_index.items():
        if idx == "_meta":
            continue
        if "id" not in props:
            continue
        kind = "pieceOfFurniture"
        if props.get("doorOrWindow", "false").lower() == "true":
            kind = "doorOrWindow"
        elif props.get("light", "false").lower() == "true" or "power" in props:
            # SH3D's catalog flags lights via `light#N=true` or an embedded
            # `power#N=…`; either way means it's a light.
            kind = "light"

        def _float(name: str) -> Optional[float]:
            v = props.get(name)
            if v is None:
                return None
            try:
                return float(v)
            except ValueError:
                return None

        out.append(ScanEntry(
            catalogId=props["id"],
            name=props.get("name"),
            category=props.get("category"),
            kind=kind,
            width=_float("width"),
            depth=_float("depth"),
            height=_float("height"),
            model=props.get("model"),
            icon=props.get("icon"),
            creator=props.get("creator"),
            tags=[t.strip() for t in props.get("tags", "").split(",") if t.strip()],
        ))
    return out


def _read_catalog_properties_from_archive(path: str) -> tuple[Optional[str], Optional[str]]:
    """Return (catalog_text, manifest_id) read from a .jar or .sh3f archive.

    Looks for the canonical entry names in priority order. Returns
    (None, None) when neither file exists in the archive.
    """
    if not zipfile.is_zipfile(path):
        return None, None
    candidates = (
        "PluginFurnitureCatalog.properties",
        "com/eteks/sweethome3d/io/DefaultFurnitureCatalog.properties",
        "DefaultFurnitureCatalog.properties",
    )
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        for name in candidates:
            if name in names:
                return z.read(name).decode("utf-8", errors="replace"), name
    return None, None


def scan_catalog_archive(path: str) -> list[ScanEntry]:
    """Extract catalog entries from a Furniture.jar or `.sh3f` library."""
    text, _ = _read_catalog_properties_from_archive(path)
    if text is None:
        return []
    entries = parse_catalog_properties(text)
    src = os.path.basename(path)
    for e in entries:
        e.source = src
    return entries


# ─────────────────────── library directory discovery

def find_sh3f_directories() -> list[str]:
    """Return existing directories where SH3D stores user-installed
    `.sh3f` plugin libraries. Mirrors SH3D's PluginManager search path.
    """
    candidates = [
        # Linux / generic Unix
        os.path.expanduser("~/.eteks/sweethome3d/furniture"),
        os.path.expanduser("~/.eteks/sweethome3d/plugins"),
        # macOS
        os.path.expanduser(
            "~/Library/Application Support/eTeks/Sweet Home 3D/furniture"),
        os.path.expanduser(
            "~/Library/Application Support/eTeks/Sweet Home 3D/plugins"),
        # Windows (when run under WSL)
        os.path.expanduser(
            "~/AppData/Roaming/eTeks/Sweet Home 3D/furniture"),
    ]
    return [c for c in candidates if os.path.isdir(c)]


def find_installed_catalog_archives() -> list[str]:
    """All catalog-bearing archives on disk: bundled Furniture.jar plus
    every `.sh3f` in the user's plugin directories."""
    from cli_anything.sweethome3d.core._sh3d_catalog_metadata import find_furniture_jar
    archives = []
    jar = find_furniture_jar()
    if jar:
        archives.append(jar)
    for d in find_sh3f_directories():
        for name in sorted(os.listdir(d)):
            if name.lower().endswith(".sh3f"):
                archives.append(os.path.join(d, name))
    return archives


def scan_all() -> list[ScanEntry]:
    """Aggregate entries from every installed catalog source.

    Deduplication strategy: first occurrence of a catalogId wins, so the
    bundled `Furniture.jar` takes precedence over user-installed `.sh3f`
    plugins for matching ids (rare in practice).
    """
    seen: dict[str, ScanEntry] = {}
    for path in find_installed_catalog_archives():
        for entry in scan_catalog_archive(path):
            seen.setdefault(entry.catalogId, entry)
    return list(seen.values())


# ─────────────────────── from-project enumeration

def from_project(home: Home) -> list[ScanEntry]:
    """Enumerate every unique catalogId actually used by pieces in `home`.

    Returns each id with the metadata SH3D needs to re-render the piece —
    `model`, `icon`, `name`, plus inferred kind from the piece's `kind`
    field. Particularly useful for inspecting community-catalog ids that
    don't appear in the curated `_sh3d_catalog_metadata.SH3D_CATALOG`.
    """
    out: dict[str, ScanEntry] = {}
    for f in home.furniture:
        if not f.catalogId:
            continue
        if f.catalogId in out:
            continue
        out[f.catalogId] = ScanEntry(
            catalogId=f.catalogId,
            name=f.name,
            kind=f.kind,
            width=f.width,
            depth=f.depth,
            height=f.height,
            model=f.model,
            icon=f.icon,
            creator=f.creator,
            source="project",
        )
    # Also walk groups
    from cli_anything.sweethome3d.core.model import FurnitureGroup, PieceOfFurniture

    def _walk(items):
        for member in items:
            if isinstance(member, FurnitureGroup):
                _walk(member.furniture)
            elif isinstance(member, PieceOfFurniture):
                if member.catalogId and member.catalogId not in out:
                    out[member.catalogId] = ScanEntry(
                        catalogId=member.catalogId,
                        name=member.name,
                        kind=member.kind,
                        width=member.width,
                        depth=member.depth,
                        height=member.height,
                        model=member.model,
                        icon=member.icon,
                        creator=member.creator,
                        source="project",
                    )
    _walk(home.furnitureGroups)
    return list(out.values())
