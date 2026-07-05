# Tranche A3 — Refinement, Ergonomics, Performance & Coverage Audit

> **Scope**: behaviour-preserving improvements only. Every suggestion includes a de-risking strategy.
> **Branch**: `kimi/enhance-harden`

---

## 1. Findings

### 1.1 Duplication & Dead Code

#### [dup] `_to_sh3d_xml()` duplicates serialization logic already in `project.py`
- **Location**: `designer.py:1600–1687` (88 lines) vs `project.py:295–878` (~580 lines of XML serialisation)
- **Issue**: `_to_sh3d_xml()` re-implements wall/room/opening/furniture XML emission that `project.py` already handles via `_home_to_xml()`. The legacy method is marked "fallback" but is never called by the public API — only reachable via `_save_legacy()` which itself is private.
- **Risk**: Low — it's a private method with no external callers.

#### [dup] PNG placeholder generation duplicated across two methods
- **Location**: `designer.py:1688–1702` (`_make_thumbnail_png`) and `designer.py:1719–1738` (`_make_placeholder_png`)
- **Issue**: Both build minimal PNGs from scratch using `struct` + `zlib`. `_make_thumbnail_png()` creates a 1×1 white PNG; `_make_placeholder_png(w, h)` creates an arbitrary-size grey PNG. The chunk-building logic is copy-pasted with minor differences (one uses nested `chunk()`, the other uses `make_chunk()`).
- **Lines**: ~30 lines of duplicated PNG byte-construction logic.

#### [dup] `_xml_escape()` in designer.py duplicates standard library
- **Location**: `designer.py:1798–1804`
- **Issue**: Manual XML escaping (`&`, `"`, `<`, `>`) that could use `html.escape(s, quote=True)` from stdlib. Not a correctness issue but unnecessary custom code.

#### [dead] `_save_legacy()` is unreachable dead code
- **Location**: `designer.py:1585–1600`
- **Issue**: Private method, never called by any public API path. The docstring says "retained for one release as a fallback" but no test or caller references it.

#### [dead] `_to_sh3d_xml()` is dead code (only called by `_save_legacy()`)
- **Location**: `designer.py:1600–1687`
- **Issue**: Only reachable through `_save_legacy()`, which itself is dead. 88 lines of unused XML generation.

#### [dup] Lazy import pattern repeated in `_to_home()`
- **Location**: `designer.py:1363–1402`
- **Issue**: The global-variable lazy-import cache (`_HOME_PIPELINE_IMPORTED`, `_add_level_fn`, etc.) is a manual singleton pattern that could be replaced by a simple module-level import or `functools.lru_cache`. The 15-line boilerplate for each of 9 imports is fragile.

---

### 1.2 Structure — Over-large Modules/Functions

#### [structure] `designer.py` is 1836 lines — the largest module by far
- **Location**: `cli_anything/sweethome3d/core/designer.py` (1836 lines)
- **Breakdown**:
  - Lines 1–257: Module docstring, imports, `_CATALOG` dict (~100 entries), `_CATALOG_ALIAS` dict (~60 entries), helper functions (`_all_catalog_ids`, `_real_catalog_id`, `_dist`, `_pt_to_seg_dist`, `_polygon_centroid`)
  - Lines 258–423: Data classes (`WallHandle`, `RoomHandle`, `_Level`) — ~165 lines
  - Lines 424–1739: `Designer` class — ~1315 lines (the bulk)
  - Lines 1740–1836: Module-level helpers + `__main__`

- **Proposed decomposition** (behaviour-preserving):
  1. **Extract `_CATALOG` and `_CATALOG_ALIAS`** → new file `cli_anything/sweethome3d/core/catalog_ids.py` (~170 lines). This is pure data with no logic.
  2. **Extract `_Level`, `WallHandle`, `RoomHandle`** → new file `cli_anything/sweethome3d/core/designer_models.py` (~165 lines). These are self-contained data classes.
  3. **Extract helper functions** (`_dist`, `_pt_to_seg_dist`, `_polygon_centroid`, `_xml_escape`, `_color_int`) → new file `cli_anything/sweethome3d/core/designer_utils.py` (~80 lines). Pure functions, no state.
  4. **Split `Designer._to_home()`** (lines 1363–1539, ~177 lines) into per-entity builder methods: `_build_levels()`, `_build_walls()`, `_build_rooms()`, `_build_openings()`, `_build_furniture()`. Each is a coherent unit.
  5. **Split `Designer.validate()`** (lines 1174–1299, ~126 lines) into: `_validate_envelope()`, `_validate_orphans()`, `_validate_rooms()`, `_collect_warnings()`.

#### [structure] `project.py` is 1594 lines — second largest
- **Location**: `cli_anything/sweethome3d/core/project.py`
- **Key large functions**:
  - `_home_to_xml()` (lines ~295–878): ~580 lines of XML serialisation. Could be split by entity type (walls, rooms, furniture, etc.) into helper methods.
  - `xml_to_home()` (lines ~1171–1460): ~290 lines of XML parsing. Same decomposition opportunity.

#### [structure] `render_runtime.py` is 754 lines
- **Location**: `cli_anything/sweethome3d/core/render_runtime.py`
- Contains Java compilation logic, OBJ extraction, and render pipeline — naturally cohesive but could benefit from splitting the "Java compilation" concern from the "render execution" concern.

---

### 1.3 Readability & Types

#### [types] Missing type hints on module-level helpers in designer.py
- **Location**: `designer.py:177` (`_dist`), `designer.py:182` (`_pt_to_seg_dist`), `designer.py:200` (`_polygon_centroid`)
- **Issue**: These have no type annotations. `_dist(a: Pt, b: Pt) -> float` has a hint but `Pt` is not imported/defined in the visible scope (uses `tuple[float, float]` internally).

#### [types] `_Level.to_dict()` / `from_dict()` lack return/input type precision
- **Location**: `designer.py:391–423`
- **Issue**: Returns `dict` with no TypedDict or Protocol. The round-trip contract is implicit.

#### [types] Magic numbers throughout designer.py
- **Locations**: 
  - `_SNAP_TOL = 8.0` (line ~450) — documented but the multiplier `2.5` in validate() (line ~1247) is magic
  - Wall thickness defaults: `20.0` (exterior), `10.0` (partition) scattered across multiple methods
  - PNG dimensions: `800`, `600`, margin `20` in `_to_svg()` and `_make_placeholder_png()`
  - Color hex values: `"#ddd8c4"`, `"#888"`, `"#222"`, `"#555"` in SVG output

#### [types] Inconsistent naming: `level` vs `lv` vs `lvl`
- **Location**: Throughout `designer.py` — loop variables use `lv`, but parameters use `level`. The `_Level` class uses `idx` internally but the Designer uses positional indexing.

#### [docstrings] Missing docstrings on public API methods
- **Methods with thin/missing docs**: 
  - `Designer.add_level()` (line 454): has params but no return description
  - `Designer.wall_facing()` (line 952): brief, no example
  - `Designer.room_at()` (line 984): brief, no example
  - `Designer.list_catalog_furniture()` (line 1144): present but could include the full catalog structure

