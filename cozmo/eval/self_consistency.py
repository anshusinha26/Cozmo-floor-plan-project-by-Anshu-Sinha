"""Checks that need no ground truth, and cross-capture comparison of two plans.

Without tape measurements nothing here says a plan is *correct*. It says
whether a plan is internally coherent (rooms do not overlap, every room is
reachable, walls close) and whether two captures of the same space agree.
Both are reported as such: agreement between two wrong reconstructions is
still agreement, never accuracy.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from shapely.geometry import Polygon as SPoly

from cozmo.contracts.models import Plan
from cozmo.eval.registration import (
    DEFAULT_MIN_IOU,
    DEFAULT_WALL_OFFSET_M,
    match_rooms_by_iou,
    match_walls_by_face,
    register_plans,
)


def self_consistency(plan: Plan) -> dict[str, Any]:
    polys = [SPoly(r.polygon) for r in plan.rooms]
    overlap = 0.0
    for i in range(len(polys)):
        for j in range(i + 1, len(polys)):
            overlap += polys[i].intersection(polys[j]).area
    room_ids = [r.id for r in plan.rooms]
    edges = {(a.room_a, a.room_b) for a in plan.adjacency}
    seen = set()
    if room_ids:
        stack = [room_ids[0]]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            for a, b in edges:
                if a == cur and b not in seen:
                    stack.append(b)
                if b == cur and a not in seen:
                    stack.append(a)
    sum_rooms = sum(r.floor_area_m2.value for r in plan.rooms)
    return {
        "n_rooms": len(plan.rooms),
        "n_walls": sum(len(r.walls) for r in plan.rooms),
        "n_openings": sum(len(r.openings) for r in plan.rooms),
        "room_overlap_m2": float(overlap),
        "footprint_area_m2": plan.stitched_plan.footprint_area_m2.value,
        "sum_room_area_m2": float(sum_rooms),
        "area_ratio_sum_over_footprint": float(sum_rooms / plan.stitched_plan.footprint_area_m2.value)
        if plan.stitched_plan.footprint_area_m2.value else None,
        "rooms_connected": len(seen) == len(room_ids),
        "isolated_rooms": sorted(set(room_ids) - seen),
        "ceiling_from_prior": [r.id for r in plan.rooms if r.ceiling_height_m.method.startswith("prior")],
    }


def match_rooms_by_area(plan_a: Plan, plan_b: Plan, rel_tolerance: float = 0.25) -> list[tuple[str, str, float]]:
    """Kept only for the ceiling of what area alone can do. Not used for scoring.

    Superseded by registration plus polygon IoU: two rooms of similar size in
    different corners of a flat pair happily under an area rule, which turns an
    eval artefact into a reconstruction failure.
    """
    cands = []
    for ra in plan_a.rooms:
        for rb in plan_b.rooms:
            aa, ab = ra.floor_area_m2.value, rb.floor_area_m2.value
            denom = max(aa, ab)
            rel = abs(aa - ab) / denom if denom else 1.0
            if rel <= rel_tolerance:
                cands.append((rel, ra.id, rb.id))
    cands.sort()
    used_a: set[str] = set()
    used_b: set[str] = set()
    out = []
    for rel, a, b in cands:
        if a in used_a or b in used_b:
            continue
        used_a.add(a)
        used_b.add(b)
        out.append((a, b, float(rel)))
    return out


def cross_plan_repeat_pairs(plan_a: Plan, plan_b: Plan, space_id: str, tier: str,
                            min_iou: float = DEFAULT_MIN_IOU,
                            max_offset_m: float = DEFAULT_WALL_OFFSET_M) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Per-wall rows for the repeatability gate, after registering the two plans.

    Rooms are paired by polygon IoU and walls by nearest parallel face. Rooms
    and walls with no counterpart are returned as failure rows with an infinite
    difference, so a capture that simply loses a room cannot score well by
    reporting fewer things.
    """
    reg = register_plans(plan_a, plan_b)
    room_pairs = match_rooms_by_iou(plan_a, plan_b, reg, min_iou=min_iou)
    rooms_a = {r.id: r for r in plan_a.rooms}
    rooms_b = {r.id: r for r in plan_b.rooms}
    rows: list[dict[str, Any]] = []
    n_walls_matched = n_walls_unmatched = 0

    def row(room_id: str, wall_id: str, a: float, b: float, matched: bool) -> dict[str, Any]:
        return {"space_id": space_id, "tier": tier,
                "capture_a": plan_a.capture.id, "capture_b": plan_b.capture.id,
                "room_id": room_id, "wall_id": wall_id, "a": a, "b": b, "matched": matched}

    for rp in room_pairs:
        ra, rb = rooms_a[rp.room_a], rooms_b[rp.room_b]
        pairs, un_a, un_b = match_walls_by_face(ra, rb, reg, max_offset_m=max_offset_m)
        for wp in pairs:
            rows.append(row(f"{rp.room_a}~{rp.room_b}", f"{wp.wall_a}~{wp.wall_b}",
                            wp.length_a, wp.length_b, True))
        n_walls_matched += len(pairs)
        for wid in un_a:
            rows.append(row(f"{rp.room_a}~{rp.room_b}", f"{wid}~none",
                            next(w.length_m.value for w in ra.walls if w.id == wid), float("nan"), False))
        for wid in un_b:
            rows.append(row(f"{rp.room_a}~{rp.room_b}", f"none~{wid}",
                            float("nan"), next(w.length_m.value for w in rb.walls if w.id == wid), False))
        n_walls_unmatched += len(un_a) + len(un_b)

    matched_a = {rp.room_a for rp in room_pairs}
    matched_b = {rp.room_b for rp in room_pairs}
    unmatched_rooms_a = [r.id for r in plan_a.rooms if r.id not in matched_a]
    unmatched_rooms_b = [r.id for r in plan_b.rooms if r.id not in matched_b]
    for rid in unmatched_rooms_a:
        for w in rooms_a[rid].walls:
            rows.append(row(f"{rid}~none", f"{w.id}~none", w.length_m.value, float("nan"), False))
    for rid in unmatched_rooms_b:
        for w in rooms_b[rid].walls:
            rows.append(row(f"none~{rid}", f"none~{w.id}", float("nan"), w.length_m.value, False))

    summary = {
        "registration": {"rotation_deg": reg.rotation_deg, "tx": reg.tx, "ty": reg.ty, "footprint_iou": reg.iou},
        "rooms_a": len(plan_a.rooms), "rooms_b": len(plan_b.rooms),
        "rooms_matched": len(room_pairs),
        "room_iou": [round(rp.iou, 3) for rp in room_pairs],
        "unmatched_rooms_a": unmatched_rooms_a,
        "unmatched_rooms_b": unmatched_rooms_b,
        "walls_matched": n_walls_matched,
        "walls_unmatched": n_walls_unmatched,
        "min_iou": min_iou, "max_wall_offset_m": max_offset_m,
    }
    return rows, summary


def observed_in_both(plan_a: Plan, plan_b: Plan, tol_m: float = 0.05,
                     tol_deg: float = 2.0) -> dict[str, Any]:
    """Agreement over the walls both captures actually saw.

    This is a secondary statistic and never the gate. The gate scores every
    wall, including those only one capture observed, because a pipeline that
    reports fewer things must not score better. But when two captures cover
    different parts of a building, that strict number says more about coverage
    than about the pipeline, so the agreement over the shared walls is reported
    beside it, clearly labelled.
    """
    reg = register_plans(plan_a, plan_b)
    rows, _ = cross_plan_repeat_pairs(plan_a, plan_b, "", "")
    matched = [r for r in rows if r["matched"]]
    diffs = [abs(r["a"] - r["b"]) for r in matched]
    within = [d for d in diffs if d <= tol_m]
    face = _face_agreement()
    return {
        "label": "secondary statistic, not the gate",
        "face_agreement": face,
        "walls_observed_in_both": len(matched),
        "walls_total_rows": len(rows),
        "median_abs_difference_m": float(np.median(diffs)) if diffs else None,
        "within_tolerance_m": tol_m,
        "n_within_tolerance": len(within),
        "share_within_tolerance": (len(within) / len(matched)) if matched else None,
        "registration_footprint_iou": float(reg.iou),
        "note": ("Walls seen by only one capture are excluded here and included in the gate. "
                 "Agreement on shared walls does not show the plans agree."),
    }


def _face_agreement() -> dict[str, Any] | None:
    """Wall-face agreement measured by the fix-loop evidence, if it is present.

    Polygon edges and wall faces are different things. Two captures can put the
    same wall in the same place to two centimetres and still cut it into
    different polygon edges, so both numbers are reported and neither is
    allowed to stand for the other.
    """
    path = Path(__file__).resolve().parents[2] / "fix_loop" / "evidence" / "evidence.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
        a = data["a_wall_face_repeatability"]
    except (ValueError, KeyError):
        return None
    shares = {k: v for k, v in a.items() if k.endswith("_matched_share")}
    return {
        "median_offset_m": a.get("median_offset_m_matched"),
        "matched_share_by_capture": shares,
        "source": "fix_loop/evidence/evidence.json, regenerated by fix_loop/evidence_run.py",
    }


def same_space_verdict(plan_a: Plan, plan_b: Plan) -> dict[str, Any]:
    """Evidence that two captures really are the same property, before trusting agreement.

    Repeatability across two different places is meaningless, so this is
    checked and reported rather than assumed from the registry. The check is
    the registered footprint IoU plus the share of rooms that pair by IoU.
    """
    reg = register_plans(plan_a, plan_b)
    matched = match_rooms_by_iou(plan_a, plan_b, reg)
    n_min = min(len(plan_a.rooms), len(plan_b.rooms))
    share = len(matched) / n_min if n_min else 0.0
    fa = plan_a.stitched_plan.footprint_area_m2.value
    fb = plan_b.stitched_plan.footprint_area_m2.value
    ratio = min(fa, fb) / max(fa, fb) if max(fa, fb) else 0.0
    confident = reg.iou >= 0.5 and share >= 0.5
    return {
        "footprint_iou_after_registration": float(reg.iou),
        "registration": {"rotation_deg": reg.rotation_deg, "tx": reg.tx, "ty": reg.ty},
        "footprint_area_ratio": float(ratio),
        "matched_rooms": len(matched),
        "rooms_a": len(plan_a.rooms),
        "rooms_b": len(plan_b.rooms),
        "matched_share": float(share),
        "same_space": bool(confident),
        "basis": "registered footprint IoU at least 0.5 and at least half the rooms pairing by polygon IoU",
        "note": "Agreement between two captures is repeatability, not accuracy. Both can be wrong together.",
    }
