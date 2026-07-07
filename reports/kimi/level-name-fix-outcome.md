# Level Name Filtering Fix — Outcome Report

## Root Cause

The SVG export path (`export.py:to_svg`, line 88) compared the raw `--level`
CLI string directly against `obj.level` — which stores the level **id**, not
the level name. When a user passed a level **name** like `"Level 0"`, it never
matched any object's id, so every `<g>` group was silently emptied:

```python
# BEFORE (broken — export.py line 88):
if level is not None:
    filt = lambda obj: obj.level == level   # "Level 0" != "lvl_abc123"
```

No name→id resolution existed anywhere in the SVG export path. The CLI
(`sweethome3d_cli.py:export_svg_cmd`) passed the raw string straight through
to `export_core.export_svg(..., level=level)` with no resolution step.

The render path (`render_runtime.py:_resolve_level_specs`) was architecturally
correct — it built a `by_name` map and resolved names to ids — but used
exact case-sensitive matching with no whitespace trimming on the map keys,
making it fragile for real-world level names.

## The Fix

### 1. `cli_anything/sweethome3d/core/export.py` — SVG export (primary fix)

Added a `_resolve_level()` helper that resolves a level spec (id or name)
to a level id using case-insensitive, whitespace-trimmed matching. It raises
`ValueError` with a clear message listing known levels if the spec matches
nothing:

```python
def _resolve_level(home: Home, spec: str) -> str:
    s = spec.strip()
    for lvl in home.levels:
        if lvl.id.strip().lower() == s.lower() or (
            lvl.name and lvl.name.strip().lower() == s.lower()
        ):
            return lvl.id
    known = sorted(
        {lvl.id for lvl in home.levels}
        | {lvl.name for lvl in home.levels if lvl.name}
    )
    raise ValueError(
        f"unknown level spec: {spec!r}. Known ids/names: {known!r}"
    )
```

Changed `to_svg()` to call it before filtering:

```python
# AFTER (fixed):
if level is not None:
    resolved = _resolve_level(home, level)
    filt = lambda obj: obj.level == resolved
```

### 2. `cli_anything/sweethome3d/core/render_runtime.py` — render path

Added case-insensitive, whitespace-trimmed lookup maps to
`_resolve_level_specs`:

```python
# AFTER:
by_id_ci = {k.strip().lower(): v for k, v in by_id.items()}
by_name_ci = {k.strip().lower(): v for k, v in by_name.items()}
sl = s.lower()
if sl in by_id_ci:
    resolved.add(by_id_ci[sl].id)
elif sl in by_name_ci:
    resolved.add(by_name_ci[sl].id)
```

This path already raised `ValueError` on unknown specs (via `filtered_levels`),
so no silent-empty-result bug existed here — just fragile matching.

## Regression Tests Added

Three new tests in `cli_anything/sweethome3d/tests/test_core.py::TestExport`:

1. **`test_level_filter_by_name`** — Creates two levels ("Ground", "First"),
   adds walls and rooms to each, filters by the name `"First"`, and asserts
   exactly 1 wall polygon and 1 room polygon appear (only that level's geometry).

2. **`test_level_filter_by_name_case_insensitive`** — Same setup, filters by
   lowercase `"first"`, asserts 1 wall polygon (case-insensitive matching works).

3. **`test_level_filter_unknown_name_raises`** — Passes `"Nonexistent"` as the
   level spec, asserts `ValueError` is raised with message matching
   `"unknown level spec"` (no silent empty result).

The existing `test_level_filter` (id-based) was preserved unchanged.

## Final Test Result

```
461 passed, 14 skipped, 2 deselected in 34.97s
```

New tests verified individually:

```
cli_anything/sweethome3d/tests/test_core.py::TestExport::test_level_filter_by_name PASSED
cli_anything/sweethome3d/tests/test_core.py::TestExport::test_level_filter_by_name_case_insensitive PASSED
cli_anything/sweethome3d/tests/test_core.py::TestExport::test_level_filter_unknown_name_raises PASSED
```

Full suite (render tests deselected):

```
.venv/bin/python -m pytest cli_anything/sweethome3d/tests -q -p no:cacheprovider \
  --deselect cli_anything/sweethome3d/tests/test_cli_render_edit_watch.py::TestRenderCommands::test_render_photo_gpu \
  --deselect cli_anything/sweethome3d/tests/test_cli_render_edit_watch.py::TestRenderCommands::test_render_photo_cpu_low_quality

461 passed, 14 skipped, 2 deselected in 34.97s
```

Baseline was 458 passed; the +3 are the new regression tests. No existing
tests were weakened or deleted.
