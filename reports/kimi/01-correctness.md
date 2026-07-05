# Correctness audit — cli-anything-sweethome3d

Generated during tranche I1 (kimi/enhance-harden).

## Severity summary

| Severity | Count | Description |
|----------|-------|-------------|
| Critical | 1 | Parser coerces explicit zero values to defaults, corrupting round-trip and user data. |
| High     | 1 | Light source colour fallback uses bitwise OR with sentinel, returning wrong colour for black (0). |
| Medium   | 0 | — |
| Low      | 0 | — |

## CRIT-1 — `_float_attr` / `_int_attr` results are post-processed with `or default`

**Location:** `cli_anything/sweethome3d/core/project.py` (parser), ~70 occurrences.

**Problem:** After calling `_float_attr(el, attr, default)` or `_int_attr(el, attr, default)`,
the parser repeatedly applies `or default`. In Python, a legitimate value of `0` is falsy,
so any attribute explicitly set to `0` is silently replaced by the default. Examples:

- `Room.nameYOffset` default is `-40`; a room with `nameYOffset="0"` is read as `-40`.
- `PieceOfFurniture.angle` default is `0`; an explicit `angle="0"` is read as `0` (harmless here,
  but the pattern is wrong).
- `Compass.diameter` default is `100`; an explicit `diameter="0"` is read as `100`.
- `Camera.z` default is `1000`; an explicit `z="0"` is read as `1000`.

This breaks `.sh3d` round-trip fidelity and can silently corrupt user data.

**Reproduction:**

```python
from cli_anything.sweethome3d.core.project import read_home
import io
xml = b'''<home version="6005"><room nameYOffset="0"><point x="0" y="0"/><point x="100" y="0"/><point x="100" y="100"/></room></home>'''
home = read_home(io.BytesIO(xml))
assert home.rooms[0].nameYOffset == 0  # fails: reads -40
```

**Fix:** Remove the redundant `or default` everywhere. `_float_attr`/`_int_attr` already return
`default` when the attribute is absent, and return the parsed value (including `0`) when present.

## HIGH-1 — Light source colour fallback corrupts black

**Location:** `cli_anything/sweethome3d/core/project.py` around line 1008.

**Problem:**

```python
color=_color_from_str(ls.get("color")) or 0xFFFFFFFF,
```

`_color_from_str` returns `0` for the colour black (`#00000000` or `#FF000000`). Because `0` is
falsy, the `or 0xFFFFFFFF` turns an explicit black light source into white. The intended fallback
is only for a missing colour attribute (`None`).

**Fix:** Use `if color is None: color = 0xFFFFFFFF` instead of `or`.

