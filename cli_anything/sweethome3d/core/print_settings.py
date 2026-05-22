"""Print settings — paper size, margins, headers, level filtering.

SH3D's File > Page Setup dialog stores its configuration as a `<print>`
element inside the `<home>` document. The data layer already reads and
writes the full `Print` dataclass; this module is the thin CRUD surface.

All distances are in mm to match SH3D's own field labels (paperWidth=210
for A4 portrait, paperHeight=297, default margins=10mm).
"""

from __future__ import annotations

from typing import Iterable, Optional

from cli_anything.sweethome3d.core.model import Home, Print


_ORIENTATIONS = ("PORTRAIT", "LANDSCAPE", "REVERSE_LANDSCAPE")


# Sensible defaults that mirror SH3D's own first-time-print dialog values
# so callers can call `set_print` with just the fields they want to tweak.
_DEFAULT_PRINT = dict(
    paperWidth=210.0,
    paperHeight=297.0,
    paperTopMargin=10.0,
    paperLeftMargin=10.0,
    paperBottomMargin=10.0,
    paperRightMargin=10.0,
    paperOrientation="PORTRAIT",
)


def get_print(home: Home) -> Optional[Print]:
    """Return current print settings (None when none configured)."""
    return home.printSettings


def set_print(home: Home, **fields) -> Print:
    """Create or update the home's print settings.

    Unknown keys raise AttributeError. Validates `paperOrientation` against
    SH3D's canonical values; positive paper sizes / margins enforced.
    """
    pr = home.printSettings
    if pr is None:
        pr = Print(**_DEFAULT_PRINT)
        home.printSettings = pr
    for k, v in fields.items():
        if not hasattr(pr, k):
            raise AttributeError(f"unknown print field: {k!r}")
        if k == "paperOrientation" and v not in _ORIENTATIONS:
            raise ValueError(
                f"paperOrientation must be one of {_ORIENTATIONS}, got {v!r}"
            )
        if k in {"paperWidth", "paperHeight"} and v <= 0:
            raise ValueError(f"{k} must be positive")
        if k.startswith("paper") and k.endswith("Margin") and v < 0:
            raise ValueError(f"{k} must be non-negative")
        setattr(pr, k, v)
    return pr


def clear_print(home: Home) -> bool:
    """Drop print settings entirely. Returns True if something was removed."""
    if home.printSettings is None:
        return False
    home.printSettings = None
    return True


def _resolve_level_id(home: Home, ident: str) -> str:
    lvl = home.find_level(ident)
    if lvl is None:
        raise KeyError(f"level not found: {ident}")
    return lvl.id


def add_printed_level(home: Home, ident: str) -> Print:
    """Include a level in the printout (idempotent)."""
    if home.printSettings is None:
        home.printSettings = Print(**_DEFAULT_PRINT)
    lvl_id = _resolve_level_id(home, ident)
    if lvl_id not in home.printSettings.printedLevels:
        home.printSettings.printedLevels.append(lvl_id)
    return home.printSettings


def remove_printed_level(home: Home, ident: str) -> Print:
    """Exclude a level from the printout."""
    if home.printSettings is None:
        raise ValueError("no print settings configured")
    lvl_id = _resolve_level_id(home, ident)
    if lvl_id in home.printSettings.printedLevels:
        home.printSettings.printedLevels.remove(lvl_id)
    return home.printSettings


def set_printed_levels(home: Home,
                         idents: Iterable[str]) -> Print:
    """Replace the printed-levels list with the given idents (order preserved)."""
    if home.printSettings is None:
        home.printSettings = Print(**_DEFAULT_PRINT)
    home.printSettings.printedLevels = [
        _resolve_level_id(home, ident) for ident in idents
    ]
    return home.printSettings
