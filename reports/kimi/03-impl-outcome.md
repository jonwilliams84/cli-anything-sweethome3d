# 03 — Safe Refinement Implementation Outcome

## Summary
This document records the safe, behaviour-preserving refactors applied to `cli_anything/sweethome3d/core/designer.py`, per the audit in `reports/kimi/03-refine.md`. All changes are dead-code removals verified by grep across the entire codebase. No public API or observable output was changed.

## Baseline Test Result (before any changes)
```
458 passed, 14 skipped, 2 deselected in 36.24s
```
All green — no failures.

## Dead Code Removed (grep-verified zero callers before each deletion)

| Method | Original Line(s) | Callers Found | Lines Removed | Commit |
|---|---|---|---|---|
| `_seg_intersection` | 196–210 | None | 16 | `ac2d6f4` |
| `_save_legacy` + `_to_sh3d_xml` | ~1567–1670 | None (internal chain only) | 104 | `114e31e` |
| `_xml_escape` | 1693–1702 | None | 10 | `cf52257` |
| `_make_thumbnail_png` | 1569–1583 | None | 15 | `a17162d` |

### Grep verification (run before each deletion)
```
$ grep -rn '_seg_intersection' cli_anything/ --include='*.py'
cli_anything/sweethome3d/core/designer.py:196:    def _seg_intersection(
→ definition only, zero callers ✅

$ grep -rn '_save_legacy\|_to_sh3d_xml' cli_anything/ --include='*.py'
cli_anything/sweethome3d/core/designer.py:1567:    def _save_legacy(
cli_anything/sweethome3d/core/designer.py:1578:        xml = self._to_sh3d_xml()
cli_anything/sweethome3d/core/designer.py:1584:    def _to_sh3d_xml(
→ only internal call _save_legacy→_to_sh3d_xml, zero external callers ✅

$ grep -rn '_xml_escape' cli_anything/ --include='*.py'
cli_anything/sweethome3d/core/designer.py:1694:def _xml_escape(s: str) -> str:
→ definition only, zero callers ✅

$ grep -rn '_make_thumbnail_png' cli_anything/ --include='*.py'
cli_anything/sweethome3d/core/designer.py:1569:    def _make_thumbnail_png(self) -> bytes:
→ definition only, zero callers ✅
```

### Post-deletion verification (final state)
```
$ grep -n '_seg_intersection\|_save_legacy\|_to_sh3d_xml\|_xml_escape\|_make_thumbnail_png' cli_anything/sweethome3d/core/designer.py
(no output — all five methods confirmed removed)
```

## Changes Applied (in order, safest first)

### 1. Deleted `_seg_intersection()` — commit `ac2d6f4`
- **Message:** "refactor: remove dead _seg_intersection() — zero callers"
- Private method at lines 196–210 that computed segment intersections. Never called anywhere.
- **Test result after deletion:** 458 passed, 14 skipped, 2 deselected ✅

### 2. Deleted `_save_legacy()` and `_to_sh3d_xml()` — commit `114e31e`
- **Message:** "refactor: remove dead _save_legacy() and _to_sh3d_xml() — zero external callers"
- `_save_legacy`: private method, zero callers. Its only purpose was to call `_to_sh3d_xml()` and write a legacy .sh3d zip.
- `_to_sh3d_xml`: its ONLY caller was `_save_legacy` (line 1578). After deleting `_save_legacy`, it became dead code too.
- **Test result after deletion:** 458 passed, 14 skipped, 2 deselected ✅

### 3. Deleted `_xml_escape()` — commit `cf52257`
- **Message:** "refactor: remove dead _xml_escape() — zero callers"
- Custom XML/HTML escape function at lines 1693–1702. Zero callers found across entire codebase. The audit's suggestion to replace with `html.escape()` was moot — the function was never used, so deletion is safer than replacement.
- **Test result after deletion:** 458 passed, 14 skipped, 2 deselected ✅

### 4. Deleted `_make_thumbnail_png()` — commit `a17162d`
- **Message:** "refactor: remove dead _make_thumbnail_png() — zero callers"
- Private method at lines 1569–1583 that created a 1×1 white PNG. Zero callers found across entire codebase. The audit's "deduplication" suggestion for `_make_thumbnail_png` / `_make_placeholder_png` reduced to simple dead-code removal since only `_make_placeholder_png` was ever called (once, in `_render_png` fallback).
- **Test result after deletion:** 458 passed, 14 skipped, 2 deselected ✅

## Changes Skipped / Justified as Too Risky

| Item | Reason |
|---|---|
| Replace `_xml_escape()` with `html.escape(s, quote=True)` | Not needed — `_xml_escape` had zero callers. Deleting it is safer than replacing a dead function. |
| Deduplicate `_make_thumbnail_png` / `_make_placeholder_png` | Not applicable — `_make_thumbnail_png` was dead code (zero callers). The remaining `_make_placeholder_png` has exactly one caller (`_render_png` fallback) and no duplicate to merge with. No refactoring needed. |

## Final Test Result
```
458 passed, 14 skipped, 2 deselected in 34.98s
```
All green — no failures, no weakened or deleted tests. The two render tests remain deselected as required (they need a render host).

## Git Log (commits on this branch)
```
$ git log --oneline -6
a17162d refactor: remove dead _make_thumbnail_png() — zero callers
cf52257 refactor: remove dead _xml_escape() — zero callers
114e31e refactor: remove dead _save_legacy() and _to_sh3d_xml() — zero external callers
ac2d6f4 refactor: remove dead _seg_intersection() — zero callers
7e744a7 fix(project): preserve explicit zero float attrs — I1 WIP (sweep stopped by Jon)
b390a66 fix(project): preserve explicit zero values when parsing float attributes
```

## Line Savings Summary
| Method | Lines Removed |
|---|---|
| `_seg_intersection` | 16 |
| `_save_legacy` + `_to_sh3d_xml` | 104 |
| `_xml_escape` | 10 |
| `_make_thumbnail_png` | 15 |
| **Total** | **145 lines removed** |

## Behaviour Preservation
- No public API changed. All removed methods were private (`_`-prefixed) with zero callers.
- No `.sh3d` output changed. The removed methods were never invoked during normal operation.
- No test modifications. Tests remain unchanged; all 458 pass.
