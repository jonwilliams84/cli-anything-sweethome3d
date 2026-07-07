# Floorplan PDF → .sh3d — refinement backlog

The pipeline works end-to-end (vector PDF → CubiCasa → `.sh3d` → SunFlow render). The
basic shape is right; this is the punch-list to make it a clean, walk-through-able model.
Each item is bounded and testable (scored by `core/floorplan_eval.py` where relevant) — good
converge-in-cluster units.

## P1 — makes the model actually usable
- [ ] **Openings render** — `polygons_to_home` gives doors/windows placeholder catalog IDs
  (`eTeks#window`), which resolve to no 3D model → SunFlow throws `NullPointerException`.
  Map to REAL Sweet Home 3D catalog IDs (e.g. `eTeks#doorFrame`, `eTeks#window*`) so
  openings render and cut the wall. Add a render smoke-test (cpu_photo on a fixture must not NPE).
- [ ] **Default framing camera + daytime** — a fresh `import pdf` home has no `topCamera`
  set and `time`≈0 (midnight → sun below horizon → blank render). `pdf_to_home` should set a
  fitted 3/4 aerial `topCamera` (bbox-framed, pitch ~0.5) with a sensible daytime `time`.
  (Working recipe proven this session — see git history / the aerial render.)

## P2 — geometry quality
- [ ] **Rooms map to degenerate slivers** — CubiCasa room polygons collapse to near-collinear
  points in `polygons_to_home` (→ no floor renders). Fix the room-polygon mapping (simplify /
  drop <min-area / keep proper exterior ring) so rooms become real floor surfaces.
- [ ] **`wall_source="fused"` over-produces** — union yields ~240 walls vs ~40 (dedup bug).
  Fix the fused dedup so it ≈ the `rooms` wall count plus genuinely-unique model walls.
- [ ] **Drop degenerate/zero-length walls** in `polygons_to_home` (defensive — a zero-length
  wall crashes `Wall3D` geometry). Currently none slip through at 0.17, but guard it.

## P3 — accuracy tuning (needs a fixture)
- [ ] **Ground-truth fixture** — hand-build the correct Bowman GF-Proposed `.sh3d` once, so
  `floorplan_eval.score_homes(truth, pred)` can score runs.
- [ ] **Scored threshold/dpi sweep** — with the fixture, dispatch a converge sweep over
  `CUBICASA_THRESHOLD` / `dpi` / `wall_source` to auto-find the optimum (best manual so far:
  threshold 0.17, dpi ~215).
- [ ] **Glazed-extension under-read** — bifold/patio runs read poorly (mostly glass, folding-door
  symbol not in CubiCasa vocab). Investigate grey→black tuning or a glazing heuristic.

## Notes / provenance
- Best manual result: `CUBICASA_THRESHOLD=0.17`, `dpi≈215`, `wall_source="model"`.
- Model backend is EXTERNAL (CubiCasa5k, CC BY-NC) via `$CUBICASA_HOME` — never vendored.
- Test in the repo `.venv` (opencv + PyMuPDF needed); photo-render tests need `SWEETHOME3D_HOME`.
