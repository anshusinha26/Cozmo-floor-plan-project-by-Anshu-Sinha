"""Evaluation runner: match, gate, calibrate, and write eval.json plus eval.md.

One call evaluates any number of (plan, ground truth) pairs together, because
two gates (ceiling spread, repeatability) only exist across captures of the
same space. Per-capture results keep their own matching counts so nothing is
averaged away.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cozmo import __version__
from cozmo.contracts.models import Plan
from cozmo.eval import gates as G
from cozmo.eval.calibration import CalItem, calibration_table
from cozmo.eval.matching import MatchResult, match_plan
from cozmo.eval.repeatability import repeat_pairs
from cozmo.io.ground_truth import GroundTruth

GATE_NAMES = [
    "opening_width",
    "ceiling_height",
    "ceiling_height_diagnosis",
    "repeatability",
    "wall_length_tier",
    "footprint",
    "stitch_adjacency",
    "stitch_overlap",
]


def evaluate_capture(plan: Plan, truth: GroundTruth, cfg: dict[str, Any]) -> dict[str, Any]:
    """Per-capture matching, error tables and calibration items (not yet gated)."""
    tier = plan.capture.tier
    tu = truth.truth_uncertainty_m
    match: MatchResult = match_plan(plan, truth, cfg)
    pred_rooms = {r.id: r for r in plan.rooms}
    items: list[CalItem] = []
    rooms_table = []
    walls_table = []
    openings_table = []
    ceiling_rows = []
    wall_rows = []
    repeat_walls: dict[tuple[str, str], float] = {}

    for rm in match.rooms:
        pr = pred_rooms[rm.room_id]
        tr = truth.room(rm.room_id)
        items.append(CalItem(tier, "ceiling_height", pr.ceiling_height_m, tr.ceiling_height_m, tu))
        ceiling_rows.append({"capture_id": plan.capture.id, "space_id": truth.space_id, "room_id": rm.room_id,
                             "pred": pr.ceiling_height_m.value, "truth": tr.ceiling_height_m})
        row = {"room_id": rm.room_id,
               "ceiling_pred": pr.ceiling_height_m.value, "ceiling_truth": tr.ceiling_height_m,
               "ceiling_abs_error": abs(pr.ceiling_height_m.value - tr.ceiling_height_m),
               "floor_area_pred": pr.floor_area_m2.value, "floor_area_truth": tr.floor_area_m2,
               "floor_area_abs_error": None, "walls_matched": len(rm.wall_pairs),
               "walls_unmatched_truth": rm.unmatched_truth_walls, "walls_unmatched_pred": rm.unmatched_pred_walls,
               "wall_order_reversed": rm.reversed}
        if tr.floor_area_m2 is not None:
            items.append(CalItem(tier, "floor_area", pr.floor_area_m2, tr.floor_area_m2, tu))
            row["floor_area_abs_error"] = abs(pr.floor_area_m2.value - tr.floor_area_m2)
        rooms_table.append(row)
        for wp in rm.wall_pairs:
            items.append(CalItem(tier, "wall_length", wp.pred_length, wp.truth_length_m, tu))
            wall_rows.append({"capture_id": plan.capture.id, "room_id": rm.room_id, "wall_id": wp.truth_id,
                              "pred": wp.pred_length.value, "truth": wp.truth_length_m, "tier": tier})
            repeat_walls[(rm.room_id, wp.truth_id)] = wp.pred_length.value
            walls_table.append({"room_id": rm.room_id, "truth_wall": wp.truth_id, "pred_wall": wp.pred_id,
                                "truth": wp.truth_length_m, "pred": wp.pred_length.value,
                                "ci_low": wp.pred_length.ci_low, "ci_high": wp.pred_length.ci_high,
                                "abs_error": abs(wp.pred_length.value - wp.truth_length_m)})
        for op in rm.opening_pairs:
            if op.truth.width_m is None or op.truth.height_m is None:
                continue  # present_unmeasured: nothing to score against
            items.append(CalItem(tier, "opening_width", op.pred.width_m, op.truth.width_m, tu))
            items.append(CalItem(tier, "opening_height", op.pred.height_m, op.truth.height_m, tu))
            measured = op.truth.width_m is not None
            openings_table.append({"room_id": rm.room_id, "truth_opening": op.truth_id, "pred_opening": op.pred_id,
                                   "wall_id": op.truth_wall_id, "centre_distance_m": op.centre_distance_m,
                                   "measured": measured,
                                   "width_truth": op.truth.width_m, "width_pred": op.pred.width_m.value,
                                   "width_abs_error": abs(op.pred.width_m.value - op.truth.width_m) if measured else None,
                                   "height_truth": op.truth.height_m, "height_pred": op.pred.height_m.value})

    fp_truth = truth.footprint_area()
    fp = {"pred": plan.stitched_plan.footprint_area_m2.value, "truth": fp_truth,
          "truth_source": "footprint_area_m2" if truth.footprint_area_m2 is not None else "sum of room floor areas"}
    if fp_truth is not None:
        items.append(CalItem(tier, "footprint_area", plan.stitched_plan.footprint_area_m2, fp_truth))

    counts = match.counts()
    return {
        "capture_id": plan.capture.id,
        "space_id": truth.space_id,
        "tier": tier,
        "pipeline_version": plan.run.pipeline_version,
        "warnings": list(plan.warnings),
        "matching": match.to_dict(),
        "rooms": rooms_table,
        "walls": walls_table,
        "openings": openings_table,
        "footprint": fp,
        "adjacency": {"pred": [[a.room_a, a.room_b] for a in plan.adjacency],
                      "truth": [[a.room_a, a.room_b] for a in truth.adjacency]},
        "overlap_m2_geometric": G.pairwise_overlap_area(plan),
        "overlap_m2_claimed": plan.stitched_plan.overlap_area_m2.value,
        "_gate_inputs": {
            # Openings marked present_unmeasured are neither hits nor phantoms:
            # there is no tape reading to be right or wrong about.
            "opening_matched": [(op.pred.width_m.value, op.truth.width_m)
                                for op in match.all_opening_pairs() if op.truth.width_m is not None],
            "opening_missed": counts["openings"]["missed"],
            "opening_phantom": counts["openings"]["phantom"],
            "ceiling_rows": ceiling_rows,
            "wall_rows": wall_rows,
            "walls_unmatched_truth": counts["walls"]["unmatched_truth"],
            "truth_uncertainty_m": tu,
            "walls_unmatched_pred": counts["walls"]["unmatched_pred"],
            "repeat": {"capture_id": plan.capture.id, "space_id": truth.space_id, "tier": tier, "walls": repeat_walls},
        },
        "_cal_items": items,
    }


def evaluate(pairs: list[tuple[Plan, GroundTruth]], cfg: dict[str, Any]) -> dict[str, Any]:
    caps = [evaluate_capture(p, t, cfg) for p, t in pairs]
    gi = [c["_gate_inputs"] for c in caps]
    opening_matched = [m for g in gi for m in g["opening_matched"]]
    gates = [
        G.opening_width(opening_matched, sum(g["opening_missed"] for g in gi), sum(g["opening_phantom"] for g in gi), cfg),
        G.ceiling_height([r for g in gi for r in g["ceiling_rows"]], cfg),
        G.ceiling_height_diagnosis([r for g in gi for r in g["ceiling_rows"]], cfg),
        G.repeatability(repeat_pairs([g["repeat"] for g in gi]), cfg),
        G.wall_length_tier([r for g in gi for r in g["wall_rows"]],
                           sum(g["walls_unmatched_truth"] for g in gi), sum(g["walls_unmatched_pred"] for g in gi), cfg),
        G.footprint([{"capture_id": c["capture_id"], "pred": c["footprint"]["pred"], "truth": c["footprint"]["truth"]}
                     for c in caps if c["footprint"]["truth"] is not None], cfg),
        G.stitch_adjacency([{"capture_id": c["capture_id"], "pred": c["adjacency"]["pred"], "truth": c["adjacency"]["truth"]}
                            for c in caps]),
        G.stitch_overlap([{"capture_id": c["capture_id"], "overlap_m2": c["overlap_m2_geometric"]} for c in caps], cfg),
    ]
    assert [g["name"] for g in gates] == GATE_NAMES
    items = [it for c in caps for it in c["_cal_items"]]
    for c in caps:
        c.pop("_gate_inputs")
        c.pop("_cal_items")
    return {
        "cozmo_version": __version__,
        "n_captures": len(caps),
        "summary": {"passed": all(g["passed"] for g in gates),
                    "n_passed": sum(1 for g in gates if g["passed"]), "n_gates": len(gates),
                    "ceiling_height_diagnosis": gates[2]["detail"]["label"],
                    "stub_output": any("STUB" in w.upper() for c in caps for w in c["warnings"])},
        "gates": gates,
        "captures": caps,
        "calibration": calibration_table(items),
    }


# ------------------------------------------------------------------ reporting

def _f(x: Any, nd: int = 3) -> str:
    if x is None:
        return "n/a"
    if isinstance(x, bool):
        return "yes" if x else "no"
    if isinstance(x, float):
        return f"{x:.{nd}f}"
    return str(x)


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join(_f(v) for v in r) + " |")
    return "\n".join(out)


def _cal_rows(table: dict[str, Any]) -> list[list[Any]]:
    rows = []
    for k, v in table.items():
        rows.append([k, v["n"], _f(v["coverage"]), _f(v["mean_width_pct"], 1), v["outside"], v["confident_garbage"]])
    return rows


def render_eval_md(result: dict[str, Any]) -> str:
    s = result["summary"]
    md = [f"# Evaluation report", "",
          f"Captures: {result['n_captures']}. Gates passed: {s['n_passed']}/{s['n_gates']}. "
          f"Overall: {'PASS' if s['passed'] else 'FAIL'}. Ceiling diagnosis: **{s['ceiling_height_diagnosis']}**.", ""]
    if s["stub_output"]:
        md += ["**WARNING: at least one evaluated plan came from the STUB PIPELINE. These numbers say nothing about reconstruction quality.**", ""]

    md += ["## Gates", ""]
    rows = []
    for g in result["gates"]:
        note = g["detail"].get("note", "")
        if g["name"] == "ceiling_height_diagnosis":
            note = f"label: {g['detail']['label']}" + (f"; {note}" if note else "")
        rows.append([g["name"], "PASS" if g["passed"] else "FAIL", _f(g["value"], 4), _f(g["threshold"], 4), g["n"], note])
    md += [_table(["gate", "result", "value", "threshold", "n", "note"], rows), ""]

    md += ["## Matching counts", ""]
    rows = []
    for c in result["captures"]:
        k = c["matching"]["counts"]
        rows.append([c["capture_id"], c["tier"],
                     f"{k['rooms']['matched']}/{k['rooms']['missing']}/{k['rooms']['phantom']}",
                     f"{k['walls']['matched']}/{k['walls']['unmatched_truth']}/{k['walls']['unmatched_pred']}",
                     f"{k['openings']['matched']}/{k['openings']['missed']}/{k['openings']['phantom']}"])
    md += [_table(["capture", "tier", "rooms matched/missing/phantom", "walls matched/unmatched truth/unmatched pred",
                   "openings matched/missed/phantom"], rows), ""]

    md += ["## Per-room errors", ""]
    for c in result["captures"]:
        md += [f"### {c['capture_id']} ({c['tier']}, {c['pipeline_version']})", ""]
        md += [_table(["room", "ceiling pred", "ceiling truth", "abs err", "floor area pred", "floor area truth", "abs err", "wall order reversed"],
                      [[r["room_id"], r["ceiling_pred"], r["ceiling_truth"], r["ceiling_abs_error"], r["floor_area_pred"],
                        r["floor_area_truth"], r["floor_area_abs_error"], r["wall_order_reversed"]] for r in c["rooms"]]), ""]
        if c["walls"]:
            md += ["Walls:", "", _table(["room", "truth wall", "pred wall", "truth m", "pred m", "ci low", "ci high", "abs err"],
                                        [[w["room_id"], w["truth_wall"], w["pred_wall"], w["truth"], w["pred"], w["ci_low"], w["ci_high"], w["abs_error"]] for w in c["walls"]]), ""]
        if c["openings"]:
            md += ["Openings:", "", _table(["room", "truth", "pred", "wall", "centre dist", "width truth", "width pred", "abs err"],
                                           [[o["room_id"], o["truth_opening"], o["pred_opening"], o["wall_id"], o["centre_distance_m"], o["width_truth"], o["width_pred"], o["width_abs_error"]] for o in c["openings"]]), ""]
        m = c["matching"]
        missed = [o for r in m["rooms"] for o in r["missed_openings"]]
        phantom = [o for r in m["rooms"] for o in r["phantom_openings"]]
        md += [f"Missing rooms: {m['missing_rooms'] or 'none'}. Phantom rooms: {m['phantom_rooms'] or 'none'}. "
               f"Missed openings: {missed or 'none'}. Phantom openings: {phantom or 'none'}.", ""]
        fp = c["footprint"]
        md += [f"Footprint: pred {_f(fp['pred'])} m2, truth {_f(fp['truth'])} m2 ({fp['truth_source']}). "
               f"Room overlap (geometric): {_f(c['overlap_m2_geometric'])} m2.", ""]
        if c["warnings"]:
            md += ["Warnings: " + "; ".join(c["warnings"]), ""]

    cal = result["calibration"]
    md += ["## Calibration", "",
           "Coverage target is the nominal ci_level (0.95). Confident garbage = truth outside the interval and interval narrower than the per-quantity median width.", ""]
    hdr = ["group", "n", "coverage", "mean width % of value", "outside", "confident garbage"]
    md += ["Overall:", "", _table(hdr, _cal_rows({"all": cal["overall"]})), ""]
    md += ["By tier:", "", _table(hdr, _cal_rows(cal["by_tier"])), ""]
    md += ["By quantity:", "", _table(hdr, _cal_rows(cal["by_quantity"])), ""]
    md += ["By tier and quantity:", "", _table(hdr, _cal_rows(cal["by_tier_quantity"])), ""]

    md += ["## Repeatability", ""]
    rep = next(g for g in result["gates"] if g["name"] == "repeatability")
    if rep["n"] == 0:
        md += [rep["detail"].get("note", "no data"), ""]
    else:
        md += [_table(["space", "tier", "capture a", "capture b", "room", "wall", "a", "b", "diff", "allowed", "ok"],
                      [[r["space_id"], r["tier"], r["capture_a"], r["capture_b"], r["room_id"], r["wall_id"], r["a"], r["b"], r["diff_m"], r["allowed_m"], r["ok"]]
                       for r in rep["detail"]["per_wall"]]), ""]
        w = rep["detail"]["worst"]
        md += [f"Worst case: {w['capture_a']} vs {w['capture_b']} {w['room_id']}/{w['wall_id']} diff {_f(w['diff_m'])} m against allowed {_f(w['allowed_m'])} m.", ""]

    diag = next(g for g in result["gates"] if g["name"] == "ceiling_height_diagnosis")
    md += ["## Ceiling height diagnosis", "",
           _table(["space", "room", "captures", "spread m", "mean error m", "label"],
                  [[p["space_id"], p["room_id"], p["n_captures"], p["spread_m"], p["mean_error_m"], p["label"]] for p in diag["detail"]["per_space"]]), ""]
    if diag["detail"].get("note"):
        md += [diag["detail"]["note"], ""]
    return "\n".join(md)


def write_eval(result: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    j = out_dir / "eval.json"
    m = out_dir / "eval.md"
    j.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    m.write_text(render_eval_md(result), encoding="utf-8")
    return j, m
