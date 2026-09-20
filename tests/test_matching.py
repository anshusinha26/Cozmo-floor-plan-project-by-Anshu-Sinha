"""Matching: rooms by id, walls by cyclic order, openings by offset within a gate."""

from __future__ import annotations

import pytest

from cozmo.contracts.models import Measurement, Opening, Plan, Room, Wall
from cozmo.eval.matching import cyclic_wall_assignment, match_plan, match_room
from cozmo.io.ground_truth import GTOpening, GTRoom, GTWall, GroundTruth
from tests.conftest import two_room_plan_dict


def _m(v, unit="m", half=0.05):
    return Measurement(value=v, ci_low=v - half, ci_high=v + half, unit=unit, method="t")


def _room(room_id, lengths, openings=(), height=2.7):
    """CCW rectangle-ish room with given wall lengths (geometry is not used by matching)."""
    walls = []
    x = 0.0
    for i, L in enumerate(lengths):
        walls.append(Wall(id=f"w{i + 1}", start=(x, 0.0), end=(x + L, 0.0), length_m=_m(L), height_m=_m(height)))
        x += L
    return Room(
        id=room_id,
        label=room_id,
        polygon=[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)],
        walls=walls,
        ceiling_height_m=_m(height),
        floor_area_m2=_m(10.0, "m2"),
        openings=list(openings),
    )


def _opening(oid, wall_id, offset, width=0.8):
    return Opening(
        id=oid, type="door", wall_id=wall_id, offset_along_wall_m=_m(offset), width_m=_m(width),
        height_m=_m(2.0), sill_height_m=None, detection_confidence=0.5,
    )


def test_cyclic_assignment_recovers_reversed_and_rotated_order():
    truth = [4.0, 5.0, 4.2, 5.3]
    # Predicted list: reversed direction, rotated by two, with noise.
    pred = [4.21, 5.01, 4.02, 5.29]  # this is truth reversed ([5.3, 4.2, 5.0, 4.0]) rotated
    a = cyclic_wall_assignment(pred, truth)
    assert a.reversed is True
    assert sorted(a.pairs) == sorted([(0, 2), (1, 1), (2, 0), (3, 3)])
    assert a.total_error == pytest.approx(0.01 + 0.01 + 0.02 + 0.01, abs=1e-9)


def test_cyclic_assignment_with_extra_predicted_wall_reports_unmatched():
    truth = [4.0, 5.0, 4.2]
    pred = [5.0, 4.2, 9.9, 4.0]  # one extra wall (9.9) inserted after the run of three
    a = cyclic_wall_assignment(pred, truth)
    assert len(a.pairs) == 3
    matched_pred = {p for p, _ in a.pairs}
    assert 2 not in matched_pred


def test_match_room_handles_reversed_offsets_and_counts_missed_and_phantom():
    # Truth: clockwise from door wall; pred is CCW so the direction is reversed.
    truth_room = GTRoom(
        id="living",
        ceiling_height_m=2.7,
        floor_area_m2=20.0,
        walls=[GTWall(id="east", length_m=4.0), GTWall(id="south", length_m=5.0),
               GTWall(id="west", length_m=4.0), GTWall(id="north", length_m=5.0)],
        openings=[
            GTOpening(id="door", type="door", wall_id="east", offset_along_wall_m=3.0, width_m=0.8, height_m=2.0),
            GTOpening(id="win", type="window", wall_id="north", offset_along_wall_m=2.0, width_m=1.0, height_m=1.0),
        ],
    )
    # Pred CCW: south(5), east(4), north(5), west(4). Door on east at reversed offset:
    # truth center = 3.4 from truth start; pred center = 4.0 - 3.4 = 0.6, so offset 0.2 width 0.8.
    pred = _room(
        "living",
        [5.0, 4.0, 5.0, 4.0],
        openings=[_opening("p_door", "w2", 0.2), _opening("p_extra", "w1", 1.0)],
    )
    rm = match_room(pred, truth_room, opening_gate_m=0.5)
    assert rm.reversed is True
    assert {(p.pred_id, p.truth_id) for p in rm.wall_pairs} == {("w1", "south"), ("w2", "east"), ("w3", "north"), ("w4", "west")}
    assert [(p.pred_id, p.truth_id) for p in rm.opening_pairs] == [("p_door", "door")]
    assert rm.missed_openings == ["win"]
    assert rm.phantom_openings == ["p_extra"]


def test_match_plan_reports_missing_and_phantom_rooms_and_never_drops_openings():
    plan = Plan.model_validate(two_room_plan_dict())  # rooms living (1 opening) and hall (0)
    truth = GroundTruth(
        capture_id="c", space_id="s", tier="video", device="d", measured_with="tape", measured_on="2026-01-01",
        rooms=[
            GTRoom(id="living", ceiling_height_m=2.7, walls=[GTWall(id=f"t{i}", length_m=L) for i, L in enumerate([3.0, 4.0, 3.0, 4.0])]),
            GTRoom(id="kitchen", ceiling_height_m=2.7, walls=[GTWall(id="k1", length_m=2.0)],
                   openings=[GTOpening(id="k_door", type="door", wall_id="k1", offset_along_wall_m=0.5, width_m=0.8, height_m=2.0)]),
        ],
    )
    res = match_plan(plan, truth, {"matching": {"opening_offset_gate_m": 0.5}})
    assert res.missing_rooms == ["kitchen"]
    assert res.phantom_rooms == ["hall"]
    c = res.counts()
    assert c["openings"] == {"matched": 0, "missed": 1, "phantom": 1}
    assert c["rooms"] == {"matched": 1, "missing": 1, "phantom": 1}
