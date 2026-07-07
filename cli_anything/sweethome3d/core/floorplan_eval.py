"""floorplan_eval — deterministic accuracy scoring for floorplan → .sh3d conversion.

The "plan image → .sh3d" USP has to be *measurable* before it can be improved:
how close are the extracted walls / doors / windows / rooms to the truth? This
module is the measuring stick. It compares a predicted Home against a
ground-truth Home and returns per-category metrics plus a single 0–10 score.

It is intentionally self-contained and dependency-light (stdlib only) so it can
serve as a hard verify gate (its own unit tests, and a baseline threshold on a
known fixture). It does NOT read images or call any model — it scores Home
objects, whatever produced them.

Categories & metrics:
  * walls    — greedy endpoint match; recall, precision, mean endpoint error (cm)
  * openings — doors and windows (kind == "doorOrWindow"), classified by name;
               per-class recall, precision, mean centre error (cm)
  * rooms    — centroid match; recall, precision, mean centroid error (cm)

The overall score weights walls 0.4, openings 0.4, rooms 0.2; each category's
sub-score blends F1 with a position-accuracy term (1 - err/tolerance).
"""
from __future__ import annotations
import math
from dataclasses import dataclass

# match tolerances (cm) — beyond these, a candidate pair is not the same object
WALL_TOL_CM = 60.0
OPENING_TOL_CM = 60.0
ROOM_TOL_CM = 150.0


# ---- extraction from a Home -------------------------------------------------
def _all_pieces(home):
    """Every PieceOfFurniture in the home, flattening (possibly nested) groups."""
    out = list(getattr(home, "furniture", []) or [])
    stack = list(getattr(home, "furnitureGroups", []) or [])
    while stack:
        g = stack.pop()
        out += list(getattr(g, "furniture", []) or [])
        stack += list(getattr(g, "furnitureGroups", []) or [])
    return out


def opening_class(piece) -> str:
    """Classify a doorOrWindow piece as 'window' or 'door' from its name."""
    name = (getattr(piece, "name", "") or "").lower()
    if "window" in name:
        return "window"
    if "door" in name:
        return "door"
    return "door"  # sh3d openings default to door-like if unnamed


def extract_walls(home):
    """List of ((xs, ys), (xe, ye)) wall segments."""
    return [((w.xStart, w.yStart), (w.xEnd, w.yEnd)) for w in getattr(home, "walls", []) or []]


def extract_openings(home):
    """List of (cls, x, y) for every door/window piece."""
    out = []
    for p in _all_pieces(home):
        if getattr(p, "kind", "") == "doorOrWindow" or getattr(p, "doorOrWindowFlag", False):
            out.append((opening_class(p), float(getattr(p, "x", 0.0)), float(getattr(p, "y", 0.0))))
    return out


def _room_centroid(room):
    pts = getattr(room, "points", []) or []
    if not pts:
        return (0.0, 0.0)
    xs = [getattr(p, "x", p[0] if isinstance(p, (tuple, list)) else 0.0) for p in pts]
    ys = [getattr(p, "y", p[1] if isinstance(p, (tuple, list)) else 0.0) for p in pts]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def extract_rooms(home):
    """List of (cx, cy) room centroids."""
    return [_room_centroid(r) for r in getattr(home, "rooms", []) or []]


# ---- geometry ---------------------------------------------------------------
def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _seg_distance(s1, s2):
    """Symmetric endpoint distance between two segments (min over both pairings)."""
    (a0, a1), (b0, b1) = s1, s2
    straight = (_dist(a0, b0) + _dist(a1, b1)) / 2
    flipped = (_dist(a0, b1) + _dist(a1, b0)) / 2
    return min(straight, flipped)


def _greedy_match(truth, pred, dist_fn, tol):
    """Greedy nearest-neighbour matching under a tolerance. Returns
    (matches[(i, j, dist)], n_truth, n_pred). Each item matched at most once."""
    pairs = []
    for i, t in enumerate(truth):
        for j, p in enumerate(pred):
            d = dist_fn(t, p)
            if d <= tol:
                pairs.append((d, i, j))
    pairs.sort()
    used_t, used_p, matches = set(), set(), []
    for d, i, j in pairs:
        if i in used_t or j in used_p:
            continue
        used_t.add(i); used_p.add(j); matches.append((i, j, d))
    return matches, len(truth), len(pred)


# ---- scoring ----------------------------------------------------------------
@dataclass
class CategoryScore:
    recall: float
    precision: float
    f1: float
    mean_err_cm: float
    matched: int
    n_truth: int
    n_pred: int
    subscore: float  # 0..1


def _f1(recall, precision):
    return 0.0 if (recall + precision) == 0 else 2 * recall * precision / (recall + precision)


def _category(truth, pred, dist_fn, tol):
    matches, nt, npd = _greedy_match(truth, pred, dist_fn, tol)
    m = len(matches)
    recall = m / nt if nt else (1.0 if npd == 0 else 0.0)
    precision = m / npd if npd else (1.0 if nt == 0 else 0.0)
    f1 = _f1(recall, precision)
    mean_err = sum(d for _, _, d in matches) / m if m else 0.0
    pos_acc = 1.0 - min(mean_err / tol, 1.0) if m else (1.0 if nt == 0 and npd == 0 else 0.0)
    subscore = f1 * (0.6 + 0.4 * pos_acc)  # F1 dominates; position refines it
    return CategoryScore(recall, precision, f1, mean_err, m, nt, npd, subscore)


def score_homes(truth, pred) -> dict:
    """Compare a predicted Home to a ground-truth Home. Returns a metrics dict
    with per-category detail and an overall 0–10 score."""
    walls = _category(extract_walls(truth), extract_walls(pred), _seg_distance, WALL_TOL_CM)

    t_op, p_op = extract_openings(truth), extract_openings(pred)
    op_cats = {}
    for cls in ("door", "window"):
        t = [(x, y) for c, x, y in t_op if c == cls]
        p = [(x, y) for c, x, y in p_op if c == cls]
        op_cats[cls] = _category(t, p, _dist, OPENING_TOL_CM)
    # combined openings subscore = truth-count-weighted mean of door+window
    tot = op_cats["door"].n_truth + op_cats["window"].n_truth
    if tot:
        op_sub = sum(c.subscore * c.n_truth for c in op_cats.values()) / tot
    else:
        op_sub = 1.0 if not (p_op) else 0.0

    rooms = _category(extract_rooms(truth), extract_rooms(pred), _dist, ROOM_TOL_CM)

    overall = 10.0 * (0.4 * walls.subscore + 0.4 * op_sub + 0.2 * rooms.subscore)

    def d(c):
        return {"recall": round(c.recall, 3), "precision": round(c.precision, 3),
                "f1": round(c.f1, 3), "mean_err_cm": round(c.mean_err_cm, 1),
                "matched": c.matched, "n_truth": c.n_truth, "n_pred": c.n_pred,
                "subscore": round(c.subscore, 3)}
    return {
        "score": round(overall, 2),
        "walls": d(walls),
        "openings": {"door": d(op_cats["door"]), "window": d(op_cats["window"]),
                     "subscore": round(op_sub, 3)},
        "rooms": d(rooms),
    }


def score_sh3d(truth_path: str, pred_path: str) -> dict:
    """Load two .sh3d files and score pred against truth."""
    from cli_anything.sweethome3d.core.project import open_home
    return score_homes(open_home(truth_path), open_home(pred_path))


if __name__ == "__main__":
    import json, sys
    if len(sys.argv) != 3:
        print("usage: python -m cli_anything.sweethome3d.core.floorplan_eval TRUTH.sh3d PRED.sh3d", file=sys.stderr)
        sys.exit(2)
    print(json.dumps(score_sh3d(sys.argv[1], sys.argv[2]), indent=2))
