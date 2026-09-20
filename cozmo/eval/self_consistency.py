"""Checks that need no ground truth, and cross-capture comparison of two plans.

Without tape measurements nothing here says a plan is *correct*. It says
whether a plan is internally coherent (rooms do not overlap, every room is
reachable, walls close) and whether two captures of the same space agree.
Both are reported as such: agreement between two wrong reconstructions is
still agreement, never accuracy.
"""

from __future__ import annotations

from typing import Any

from shapely.geometry import Polygon as SPoly

from cozmo.contracts.models import Plan
from cozmo.eval.matching import cyclic_wall_assignment


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
    """Greedy nearest floor area, best pairs first. Only for captures of one space.

    Room ids are per-capture inventions here (the pipeline numbers rooms by
    size), so area is the only stable handle without ground truth. Pairs whose
    areas differ by more than the tolerance are left unmatched rather than
    forced.
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


def cross_plan_repeat_pairs(plan_a: Plan, plan_b: Plan, space_id: str, tier: str) -> list[dict[str, Any]]:
    """Per-wall rows for the repeatability gate, from two captures of one space."""
    rows = []
    for ra_id, rb_id, _ in match_rooms_by_area(plan_a, plan_b):
        ra = next(r for r in plan_a.rooms if r.id == ra_id)
        rb = next(r for r in plan_b.rooms if r.id == rb_id)
        la = [w.length_m.value for w in ra.walls]
        lb = [w.length_m.value for w in rb.walls]
        assign = cyclic_wall_assignment(la, lb)
        for ia, ib in assign.pairs:
            rows.append({
                "space_id": space_id, "tier": tier,
                "capture_a": plan_a.capture.id, "capture_b": plan_b.capture.id,
                "room_id": f"{ra_id}~{rb_id}", "wall_id": f"{ra.walls[ia].id}~{rb.walls[ib].id}",
                "a": la[ia], "b": lb[ib],
            })
    return rows


def same_space_verdict(plan_a: Plan, plan_b: Plan) -> dict[str, Any]:
    """Evidence that two captures really are the same property, before trusting agreement.

    Repeatability across two different places is meaningless, so this is
    checked and reported rather than assumed from the registry.
    """
    fa = plan_a.stitched_plan.footprint_area_m2.value
    fb = plan_b.stitched_plan.footprint_area_m2.value
    ratio = min(fa, fb) / max(fa, fb) if max(fa, fb) else 0.0
    matched = match_rooms_by_area(plan_a, plan_b)
    n_min = min(len(plan_a.rooms), len(plan_b.rooms))
    share = len(matched) / n_min if n_min else 0.0
    confident = ratio >= 0.75 and share >= 0.5
    return {
        "footprint_area_ratio": float(ratio),
        "matched_rooms": len(matched),
        "rooms_a": len(plan_a.rooms),
        "rooms_b": len(plan_b.rooms),
        "matched_share": float(share),
        "same_space": bool(confident),
        "basis": "footprint areas within 25% and at least half the rooms pairing by area",
        "note": "Agreement between two captures is repeatability, not accuracy. Both can be wrong together.",
    }
