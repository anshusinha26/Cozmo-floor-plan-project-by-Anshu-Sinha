"""Cross-capture registration and IoU-based room and wall matching."""

from __future__ import annotations

import math

import numpy as np
import pytest

from cozmo.contracts.models import Plan
from cozmo.eval.registration import (
    footprint_mask,
    match_rooms_by_iou,
    match_walls_by_face,
    register_plans,
    transform_xy,
)
from tests.conftest import m, two_room_plan_dict


def world_two_room_plan() -> dict:
    """Two disjoint rooms in one world frame, as the lidar pipeline emits them.

    The shared conftest fixture keeps room-local polygons that overlap, which
    makes registration ill-posed; registration operates on world polygons.
    """
    d = two_room_plan_dict()
    hall = d["rooms"][1]
    hall["polygon"] = [[4.2, 0.0], [5.4, 0.0], [5.4, 3.0], [4.2, 3.0]]
    hall["walls"] = [
        {"id": "h1", "start": [4.2, 0.0], "end": [5.4, 0.0], "length_m": m(1.2), "height_m": m(2.7)},
        {"id": "h2", "start": [5.4, 0.0], "end": [5.4, 3.0], "length_m": m(3.0), "height_m": m(2.7)},
        {"id": "h3", "start": [5.4, 3.0], "end": [4.2, 3.0], "length_m": m(1.2), "height_m": m(2.7)},
        {"id": "h4", "start": [4.2, 3.0], "end": [4.2, 0.0], "length_m": m(3.0), "height_m": m(2.7)},
    ]
    d["stitched_plan"]["footprint_polygon"] = [[0.0, 0.0], [5.4, 0.0], [5.4, 3.0], [0.0, 3.0]]
    return d


def _rotate_plan(d: dict, deg: float, tx: float, ty: float) -> dict:
    """Rotate and translate every coordinate in a plan dict."""
    th = math.radians(deg)
    c, s = math.cos(th), math.sin(th)

    def f(p):
        return [c * p[0] - s * p[1] + tx, s * p[0] + c * p[1] + ty]

    out = dict(d)
    out["rooms"] = []
    for r in d["rooms"]:
        r = dict(r)
        r["polygon"] = [f(p) for p in r["polygon"]]
        r["walls"] = [dict(w, start=f(w["start"]), end=f(w["end"])) for w in r["walls"]]
        out["rooms"].append(r)
    sp = dict(d["stitched_plan"])
    sp["footprint_polygon"] = [f(p) for p in d["stitched_plan"]["footprint_polygon"]]
    out["stitched_plan"] = sp
    return out


def test_register_recovers_a_90_degree_rotation_and_shift():
    a = Plan.model_validate(world_two_room_plan())
    b = Plan.model_validate(_rotate_plan(world_two_room_plan(), 90.0, 3.0, -2.0))
    reg = register_plans(a, b)
    # The registration maps B back into A's frame, so it reports the inverse
    # of the rotation that was applied to B.
    assert reg.rotation_deg == 270
    assert reg.iou > 0.9, reg.iou
    # Applying the transform to b's rooms should land on a's rooms.
    for ra, rb in zip(a.rooms, b.rooms):
        moved = transform_xy(np.array(rb.polygon), reg).mean(axis=0)
        assert np.abs(moved - np.array(ra.polygon).mean(axis=0)).max() < 0.15


def test_register_identity_when_plans_are_identical():
    a = Plan.model_validate(world_two_room_plan())
    reg = register_plans(a, a)
    assert reg.rotation_deg == 0 and reg.iou > 0.95
    assert abs(reg.tx) < 0.06 and abs(reg.ty) < 0.06


def test_footprint_mask_area_matches_room_union_area():
    """The mask rasterises the union of room polygons, not the declared footprint."""
    a = Plan.model_validate(world_two_room_plan())
    mask, _ = footprint_mask(a, cell=0.05)
    assert mask.sum() * 0.05 * 0.05 == pytest.approx(4.0 * 3.0 + 1.2 * 3.0, rel=0.05)


def test_rooms_match_by_iou_not_by_area():
    """Two rooms of equal area must not be swapped; position decides."""
    d = world_two_room_plan()
    d["rooms"][1]["polygon"] = [[5.0, 0.0], [9.0, 0.0], [9.0, 3.0], [5.0, 3.0]]
    d["rooms"][1]["floor_area_m2"] = m(12.0, "m2", 0.5)
    a = Plan.model_validate(d)
    b = Plan.model_validate(_rotate_plan(d, 0.0, 0.0, 0.0))
    reg = register_plans(a, b)
    pairs = match_rooms_by_iou(a, b, reg, min_iou=0.3)
    assert {(p.room_a, p.room_b) for p in pairs} == {("living", "living"), ("hall", "hall")}
    assert all(p.iou > 0.9 for p in pairs)


def test_rooms_below_min_iou_stay_unmatched():
    a = Plan.model_validate(world_two_room_plan())
    d = world_two_room_plan()
    d["rooms"] = d["rooms"][:1]
    d["adjacency"] = []
    d["stitched_plan"]["placements"] = d["stitched_plan"]["placements"][:1]
    d["surfaces"] = [s for s in d["surfaces"] if s["room_id"] == "living"]
    b = Plan.model_validate(d)
    reg = register_plans(a, b)
    pairs = match_rooms_by_iou(a, b, reg, min_iou=0.3)
    assert [p.room_b for p in pairs] == ["living"]


def test_walls_match_by_nearest_parallel_face_despite_vertex_counts():
    a = Plan.model_validate(world_two_room_plan())
    d = world_two_room_plan()
    # Split the south wall of living into two collinear halves: 4 walls becomes 5.
    living = d["rooms"][0]
    living["polygon"] = [[0.0, 0.0], [2.0, 0.0], [4.0, 0.0], [4.0, 3.0], [0.0, 3.0]]
    w = living["walls"]
    half = dict(w[0])
    half["id"] = "w1a"
    half["end"] = [2.0, 0.0]
    half["length_m"] = dict(w[0]["length_m"], value=2.0, ci_low=1.95, ci_high=2.05)
    second = dict(w[0])
    second["id"] = "w1b"
    second["start"] = [2.0, 0.0]
    second["length_m"] = dict(w[0]["length_m"], value=2.0, ci_low=1.95, ci_high=2.05)
    living["walls"] = [half, second] + w[1:]
    d["surfaces"] = [x for x in d["surfaces"] if x.get("wall_id") != "w1"]
    d["damage_regions"] = []
    d["concealed_damage_flags"] = []
    d["scope_items"] = []
    b = Plan.model_validate(d)
    reg = register_plans(a, b)
    pairs, un_a, un_b = match_walls_by_face(a.rooms[0], b.rooms[0], reg, max_offset_m=0.3)
    matched_a = {p.wall_a for p in pairs}
    assert "w2" in matched_a and "w3" in matched_a and "w4" in matched_a
    # The single 4 m wall cannot pair with both halves, so one half is unmatched.
    assert len(un_b) >= 1
    for p in pairs:
        assert p.offset_m <= 0.3


def test_perpendicular_walls_never_match():
    a = Plan.model_validate(world_two_room_plan())
    pairs, _, _ = match_walls_by_face(a.rooms[0], a.rooms[0], register_plans(a, a), max_offset_m=0.3)
    for p in pairs:
        assert p.angle_deg < 1e-6
