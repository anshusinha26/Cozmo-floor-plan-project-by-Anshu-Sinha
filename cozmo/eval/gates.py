"""Pass/fail gates over matched measurements.

Every gate returns the same dict shape so eval.json and eval.md can render
them uniformly::

    {"name", "passed": bool, "value": float, "threshold": float, "n": int, "detail": dict}

Design choices worth defending:

* Denominators include what was not found. A missed opening or an unmatched
  truth wall is a failure, not an exclusion, so a pipeline cannot pass by
  predicting less.
* Boundaries are inclusive with a 1e-9 epsilon. The epsilon only absorbs
  floating point rounding at the boundary (4.0 * 1.08 is not exactly 4.32)
  and has no physical meaning.
* Gates with no data (no repeat captures, no openings) pass vacuously but say
  so in ``detail["note"]`` and carry ``n == 0`` so a report cannot hide an
  empty evaluation behind a green tick.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from shapely.geometry import Polygon as ShapelyPolygon

from cozmo.contracts.models import Plan

EPS = 1e-9


def _gate(name: str, passed: bool, value: float, threshold: float, n: int, detail: dict[str, Any]) -> dict[str, Any]:
    """One gate result.

    ``status`` is what a reader should believe: PASS, FAIL, or NOT EVALUATED
    when there was nothing to score. A gate with no data is not a gate that
    passed, and printing PASS beside n = 0 has told more than one reader that
    something was checked when nothing was. ``passed`` stays for callers that
    aggregate, and is False for an unevaluated gate so it can never lift a
    summary count.
    """
    evaluated = int(n) > 0
    return {"name": name, "passed": bool(passed) and evaluated, "evaluated": evaluated,
            "status": ("PASS" if passed else "FAIL") if evaluated else "NOT EVALUATED",
            "value": float(value), "threshold": float(threshold), "n": int(n), "detail": detail}


def _cfg(cfg: dict[str, Any], gate: str) -> dict[str, Any]:
    return (cfg.get("gates") or {}).get(gate) or {}


# ---------------------------------------------------------------- opening_width

def opening_width(matched: list[tuple[float, float]], n_missed: int, n_phantom: int, cfg: dict[str, Any]) -> dict[str, Any]:
    """|pred - truth| <= tolerance on at least min_pass_fraction of openings.

    Denominator = matched + missed + phantom. A missed opening is a width the
    pipeline failed to report, a phantom is a width it invented; both are
    wrong widths for scoring purposes.
    """
    c = _cfg(cfg, "opening_width")
    tol = float(c.get("tolerance_m", 0.02))
    min_frac = float(c.get("min_pass_fraction", 0.85))
    errors = [abs(p - t) for p, t in matched]
    within = sum(1 for e in errors if e <= tol + EPS)
    n = len(matched) + n_missed + n_phantom
    frac = within / n if n else 1.0
    detail = {
        "tolerance_m": tol,
        "within_tolerance": within,
        "matched": len(matched),
        "missed": n_missed,
        "phantom": n_phantom,
        "errors_m": errors,
    }
    if n == 0:
        detail["note"] = "no openings in either the truth or the prediction"
    return _gate("opening_width", frac + EPS >= min_frac, frac, min_frac, n, detail)


# --------------------------------------------------------------- ceiling_height

def _spreads(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Spread (max - min of predictions) per (space_id, room_id) seen in more than one capture."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[(r["space_id"], r["room_id"])].append(r)
    out = []
    for (space, room), rs in sorted(groups.items()):
        if len(rs) < 2:
            continue
        preds = [r["pred"] for r in rs]
        out.append({"space_id": space, "room_id": room, "captures": [r["capture_id"] for r in rs],
                    "spread_m": max(preds) - min(preds)})
    return out


def ceiling_height(rows: list[dict[str, Any]], cfg: dict[str, Any]) -> dict[str, Any]:
    """Per-room absolute error <= tolerance, and spread across repeat captures <= spread tolerance.

    ``rows``: {capture_id, space_id, room_id, pred, truth}. ``value`` is the
    worst absolute error; spread results sit in ``detail["spread"]`` and also
    gate the pass so a room that is consistently off and a room that wanders
    both fail here (the diagnosis gate says which).
    """
    c = _cfg(cfg, "ceiling_height")
    tol = float(c.get("tolerance_m", 0.015))
    spread_tol = float(c.get("spread_tolerance_m", 0.01))
    per_room = [
        {**{k: r[k] for k in ("capture_id", "space_id", "room_id", "pred", "truth")},
         "abs_error_m": abs(r["pred"] - r["truth"]),
         "ok": abs(r["pred"] - r["truth"]) <= tol + EPS}
        for r in rows
    ]
    spreads = _spreads(rows)
    for s in spreads:
        s["ok"] = s["spread_m"] <= spread_tol + EPS
    worst = max((r["abs_error_m"] for r in per_room), default=0.0)
    passed = all(r["ok"] for r in per_room) and all(s["ok"] for s in spreads)
    detail = {"tolerance_m": tol, "spread_tolerance_m": spread_tol, "per_room": per_room, "spread": spreads}
    if not rows:
        detail["note"] = "no room matched between prediction and truth"
    return _gate("ceiling_height", passed, worst, tol, len(rows), detail)


def ceiling_height_diagnosis(rows: list[dict[str, Any]], cfg: dict[str, Any]) -> dict[str, Any]:
    """Label the ceiling-height failure mode per space, and overall.

    * unrepeatable: spread across captures > small_spread_m (the pipeline
      does not even agree with itself; calibration cannot fix that)
    * repeatable_but_biased: spread small but |mean error| > biased_mean_m
      (a systematic scale or offset problem; fixable, and the sign says how)
    * ok: neither

    A space seen once has spread 0 by construction, so it can only be
    labelled ok or biased; that limit is stated in detail. Both failure
    labels fail the gate. ``value`` is the worst |mean error| so the number
    is comparable to the ceiling_height tolerance.
    """
    c = _cfg(cfg, "ceiling_height_diagnosis")
    small_spread = float(c.get("small_spread_m", 0.01))
    biased_mean = float(c.get("biased_mean_m", 0.015))
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[(r["space_id"], r["room_id"])].append(r)
    per_space = []
    rank = {"ok": 0, "repeatable_but_biased": 1, "unrepeatable": 2}
    for (space, room), rs in sorted(groups.items()):
        preds = [r["pred"] for r in rs]
        errs = [r["pred"] - r["truth"] for r in rs]
        spread = max(preds) - min(preds)
        mean_err = sum(errs) / len(errs)
        if spread > small_spread + EPS:
            label = "unrepeatable"
        elif abs(mean_err) > biased_mean + EPS:
            label = "repeatable_but_biased"
        else:
            label = "ok"
        per_space.append({"space_id": space, "room_id": room, "n_captures": len(rs), "spread_m": spread,
                          "mean_error_m": mean_err, "label": label,
                          "single_capture": len(rs) == 1})
    label = max((p["label"] for p in per_space), key=lambda l: rank[l], default="ok")
    worst_mean = max((abs(p["mean_error_m"]) for p in per_space), default=0.0)
    detail = {"label": label, "small_spread_m": small_spread, "biased_mean_m": biased_mean, "per_space": per_space}
    if any(p["single_capture"] for p in per_space):
        detail["note"] = "spaces seen once have spread 0 by construction and cannot be labelled unrepeatable"
    return _gate("ceiling_height_diagnosis", label == "ok", worst_mean, biased_mean, len(rows), detail)


# ---------------------------------------------------------------- repeatability

def repeatability(pairs: list[dict[str, Any]], cfg: dict[str, Any]) -> dict[str, Any]:
    """Two captures of one space at one tier agree per wall within max(abs, rel * length).

    ``pairs``: {space_id, tier, capture_a, capture_b, room_id, wall_id, a, b}.
    The 1 cm floor exists because 0.5% of a short wall is below tape
    resolution; ``value`` is the worst ratio |a - b| / allowed so 1.0 is the
    threshold for every wall regardless of length.
    """
    c = _cfg(cfg, "repeatability")
    abs_tol = float(c.get("abs_tolerance_m", 0.01))
    rel_tol = float(c.get("rel_tolerance", 0.005))
    table = []
    for p in pairs:
        # A wall with no counterpart in the other capture is the worst kind of
        # disagreement, so it fails outright instead of being dropped from the
        # denominator. Callers mark those rows with matched=False.
        if not p.get("matched", True) or math.isnan(p["a"]) or math.isnan(p["b"]):
            table.append({**p, "diff_m": math.inf, "allowed_m": abs_tol, "ratio": math.inf, "ok": False})
            continue
        diff = abs(p["a"] - p["b"])
        allowed = max(abs_tol, rel_tol * (p["a"] + p["b"]) / 2.0)
        table.append({**p, "diff_m": diff, "allowed_m": allowed, "ratio": diff / allowed if allowed else math.inf,
                      "ok": diff <= allowed + EPS})
    worst = max(table, key=lambda r: (r["ratio"], not r["ok"]), default=None)
    detail: dict[str, Any] = {"abs_tolerance_m": abs_tol, "rel_tolerance": rel_tol, "per_wall": table, "worst": worst}
    if not pairs:
        detail["note"] = "no repeat captures of the same space at this tier"
    value = worst["ratio"] if worst else 0.0
    n_ok = sum(1 for r in table if r["ok"])
    detail["n_within_tolerance"] = n_ok
    detail["share_within_tolerance"] = n_ok / len(table) if table else 1.0
    return _gate("repeatability", all(r["ok"] for r in table), value, 1.0, len(table), detail)


# ------------------------------------------------------------- wall_length_tier

def _tier_allowed(truth: float, tier: str, cfg: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    t = (_cfg(cfg, "wall_length_tier").get(tier) or {})
    abs_tol = float(t.get("abs_tolerance_m", 0.0))
    rel_tol = float(t.get("rel_tolerance", 0.0))
    return max(abs_tol, rel_tol * truth), t


def wall_length_tier(rows: list[dict[str, Any]], n_unmatched_truth: int, n_unmatched_pred: int, cfg: dict[str, Any]) -> dict[str, Any]:
    """Per matched wall |pred - truth| <= tier budget; any unmatched truth wall fails.

    Budgets: photo and video are relative, lidar is max(abs, rel) and marked
    PROVISIONAL in config. ``value`` is the worst ratio error / allowed.
    An unmatched truth wall is a length the pipeline did not report, which is
    an error larger than any budget, so it fails the gate rather than being
    excluded from it.
    """
    table = []
    for r in rows:
        allowed, t = _tier_allowed(r["truth"], r["tier"], cfg)
        err = abs(r["pred"] - r["truth"])
        table.append({**r, "abs_error_m": err, "rel_error": err / r["truth"] if r["truth"] else math.inf,
                      "allowed_m": allowed, "ratio": err / allowed if allowed else math.inf,
                      "ok": err <= allowed + EPS, "budget": t})
    worst = max((r["ratio"] for r in table), default=0.0)
    passed = all(r["ok"] for r in table) and n_unmatched_truth == 0
    detail = {"per_wall": table, "unmatched_truth": n_unmatched_truth, "unmatched_pred": n_unmatched_pred,
              "budgets": _cfg(cfg, "wall_length_tier")}
    if not rows and n_unmatched_truth == 0:
        detail["note"] = "no walls were scored at this tier"
    return _gate("wall_length_tier", passed, worst, 1.0, len(rows) + n_unmatched_truth, detail)


# ------------------------------------------------------------------- footprint

def footprint(rows: list[dict[str, Any]], cfg: dict[str, Any]) -> dict[str, Any]:
    """Stitched footprint area within rel_tolerance of truth, per capture."""
    rel = float(_cfg(cfg, "footprint").get("rel_tolerance", 0.08))
    table = []
    for r in rows:
        err = abs(r["pred"] - r["truth"]) / r["truth"] if r["truth"] else math.inf
        table.append({**r, "rel_error": err, "ok": err <= rel + EPS})
    worst = max((r["rel_error"] for r in table), default=0.0)
    detail: dict[str, Any] = {"per_capture": table}
    if not rows:
        detail["note"] = ("no capture has a tape-measured footprint: the hall was not "
                          "measured wall by wall, so the only multi-room property has no "
                          "truth footprint to compare against")
    return _gate("footprint", all(r["ok"] for r in table), worst, rel, len(table), detail)


# ------------------------------------------------------------ stitch_adjacency

def _edges(pairs) -> set[tuple[str, str]]:
    return {tuple(sorted((a, b))) for a, b in pairs}


def stitch_adjacency(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Predicted adjacency graph equals truth graph (undirected, ignoring via opening).

    ``value`` is the total number of missing plus spurious edges; threshold 0.
    """
    table = []
    total = 0
    for r in rows:
        p, t = _edges(r["pred"]), _edges(r["truth"])
        missing = sorted(list(e) for e in t - p)
        spurious = sorted(list(e) for e in p - t)
        total += len(missing) + len(spurious)
        table.append({"capture_id": r["capture_id"], "missing": missing, "spurious": spurious,
                      "ok": not missing and not spurious})
    return _gate("stitch_adjacency", total == 0, total, 0.0, len(rows), {"per_capture": table})


# -------------------------------------------------------------- stitch_overlap

def place_polygon(polygon, placement) -> list[tuple[float, float]]:
    """Apply a placement (rotate theta about the room origin, then translate)."""
    th = math.radians(placement.theta_deg.value)
    c, s = math.cos(th), math.sin(th)
    return [(c * x - s * y + placement.tx, s * x + c * y + placement.ty) for x, y in polygon]


def placed_rooms(plan: Plan) -> dict[str, list[tuple[float, float]]]:
    by_room = {p.room_id: p for p in plan.stitched_plan.placements}
    return {r.id: place_polygon(r.polygon, by_room[r.id]) for r in plan.rooms}


def pairwise_overlap_area(plan: Plan) -> float:
    """Sum of pairwise intersection areas of placed room polygons, from geometry not from the plan's own claim."""
    polys = [ShapelyPolygon(p) for p in placed_rooms(plan).values()]
    total = 0.0
    for i in range(len(polys)):
        for j in range(i + 1, len(polys)):
            total += polys[i].intersection(polys[j]).area
    return total


def stitch_overlap(rows: list[dict[str, Any]], cfg: dict[str, Any]) -> dict[str, Any]:
    """Total pairwise room overlap per capture <= max_overlap_m2 (rooms must not share floor)."""
    max_overlap = float(_cfg(cfg, "stitch_overlap").get("max_overlap_m2", 0.05))
    table = [{**r, "ok": r["overlap_m2"] <= max_overlap + EPS} for r in rows]
    worst = max((r["overlap_m2"] for r in table), default=0.0)
    return _gate("stitch_overlap", all(r["ok"] for r in table), worst, max_overlap, len(table), {"per_capture": table})
