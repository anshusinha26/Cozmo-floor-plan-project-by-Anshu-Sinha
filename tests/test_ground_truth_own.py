"""Ground truth for the hand-measured captures: tape uncertainty and unmeasured openings."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from cozmo.io.ground_truth import GroundTruth, load_ground_truth, load_registry

REPO = Path(__file__).resolve().parent.parent
GT = REPO / "benchmarks" / "ground_truth"


def _minimal(**room):
    base = {"capture_id": "x", "space_id": "s", "tier": "photo", "device": "d",
            "measured_with": "tape", "measured_on": "2026-01-01",
            "rooms": [{"id": "r", "ceiling_height_m": 2.97, **room}]}
    return GroundTruth.model_validate(base)


def test_truth_uncertainty_defaults_to_zero_and_is_carried():
    gt = _minimal(walls=[{"id": "A", "length_m": 3.6}])
    assert gt.truth_uncertainty_m == 0.0
    gt2 = GroundTruth.model_validate({**gt.model_dump(mode="json"), "truth_uncertainty_m": 0.013})
    assert gt2.truth_uncertainty_m == 0.013


def test_unmeasured_opening_carries_no_dimensions():
    gt = _minimal(walls=[{"id": "A", "length_m": 3.6}],
                  openings=[{"id": "w1", "type": "window", "wall_id": "A", "present_unmeasured": True}])
    assert gt.rooms[0].unmeasured_openings()[0].id == "w1"
    assert gt.rooms[0].measured_openings() == []
    with pytest.raises(ValidationError, match="carry no dimensions"):
        _minimal(walls=[{"id": "A", "length_m": 3.6}],
                 openings=[{"id": "w1", "type": "window", "wall_id": "A", "present_unmeasured": True,
                            "width_m": 1.0, "height_m": 1.0, "offset_along_wall_m": 0.5}])


def test_a_measured_opening_still_needs_its_dimensions():
    with pytest.raises(ValidationError, match="present_unmeasured"):
        _minimal(walls=[{"id": "A", "length_m": 3.6}],
                 openings=[{"id": "d1", "type": "door", "wall_id": "A", "width_m": 0.91}])


def test_score_walls_can_be_switched_off_for_open_plan_rooms():
    gt = _minimal(walls=[], score_walls=False)
    assert gt.rooms[0].score_walls is False and gt.rooms[0].walls == []


def test_own_ground_truth_files_load_and_agree_with_the_registry():
    reg = load_registry(REPO / "benchmarks" / "captures.yaml")
    own = [c for c in reg.captures if c.ground_truth and "own" in c.input]
    assert own, "own captures should be registered"
    for c in own:
        assert (REPO / c.input).is_dir(), c.input
        gt = load_ground_truth(REPO / c.ground_truth)
        assert gt.capture_id == c.capture_id
        assert gt.truth_uncertainty_m == pytest.approx(0.013)
        for r in gt.rooms:
            assert r.ceiling_height_m == pytest.approx(2.9718)


def test_bedroom_1_matches_the_tape_readings():
    gt = load_ground_truth(GT / "own_bedroom_1_photo.yaml")
    room = gt.room("bedroom_1")
    assert [w.id for w in room.walls] == ["A", "B", "C", "D"]
    assert [round(w.length_m, 4) for w in room.walls] == [3.6576, 3.9116, 3.6576, 3.9116]
    door = next(o for o in room.openings if o.type == "door")
    assert (round(door.width_m, 4), round(door.height_m, 4)) == (0.9144, 1.9812)
    assert {o.wall_id for o in room.unmeasured_openings()} == {"C", "D"}


def test_hall_is_not_scored_on_walls_and_keeps_its_doors():
    gt = load_ground_truth(GT / "own_hall_photo.yaml")
    hall = gt.room("hall")
    assert hall.score_walls is False and hall.walls == []
    assert len(hall.openings) == 3
    assert {o.wall_id for o in hall.openings} == {"A", "B", "F"}


def test_home_capture_covers_every_room_and_the_adjacency_graph():
    gt = load_ground_truth(GT / "own_home_photo.yaml")
    assert {r.id for r in gt.rooms} == {"hall", "bedroom_1", "bedroom_2", "kitchen"}
    edges = {tuple(sorted((a.room_a, a.room_b))) for a in gt.adjacency}
    assert edges == {("bedroom_1", "hall"), ("bedroom_2", "hall"), ("hall", "kitchen")}


def test_tape_uncertainty_is_used_in_the_coverage_check():
    """A reading known to the nearest inch cannot judge a tighter interval."""
    from cozmo.contracts.models import Measurement
    from cozmo.eval.calibration import CalItem, summarize

    pred = Measurement(value=3.650, ci_low=3.645, ci_high=3.655, unit="m", method="t")
    near_miss = CalItem("photo", "wall_length", pred, 3.6576, 0.013)
    assert near_miss.covered()
    assert summarize([near_miss])["coverage"] == 1.0
    strict = CalItem("photo", "wall_length", pred, 3.6576, 0.0)
    assert not strict.covered()
    real_miss = CalItem("photo", "wall_length", pred, 3.90, 0.013)
    assert not real_miss.covered()


def test_unmeasured_openings_are_not_missed_and_not_phantom():
    from cozmo.contracts.models import Measurement, Opening, Room
    from cozmo.eval.matching import match_room
    from cozmo.io.ground_truth import GTOpening, GTRoom, GTWall

    def m(v, unit="m"):
        return Measurement(value=v, ci_low=v - 0.05, ci_high=v + 0.05, unit=unit, method="t")

    truth = GTRoom(id="r", ceiling_height_m=2.97,
                   walls=[GTWall(id="A", length_m=3.6576), GTWall(id="B", length_m=3.9116),
                          GTWall(id="C", length_m=3.6576), GTWall(id="D", length_m=3.9116)],
                   openings=[GTOpening(id="win_c", type="window", wall_id="C", present_unmeasured=True)])
    pred = Room(id="r", label="r", polygon=[(0.0, 0.0), (3.66, 0.0), (3.66, 3.91), (0.0, 3.91)],
                walls=[
                    dict(id="w1", start=(0.0, 0.0), end=(3.66, 0.0), length_m=m(3.66), height_m=m(2.97)),
                    dict(id="w2", start=(3.66, 0.0), end=(3.66, 3.91), length_m=m(3.91), height_m=m(2.97)),
                    dict(id="w3", start=(3.66, 3.91), end=(0.0, 3.91), length_m=m(3.66), height_m=m(2.97)),
                    dict(id="w4", start=(0.0, 3.91), end=(0.0, 0.0), length_m=m(3.91), height_m=m(2.97)),
                ],
                ceiling_height_m=m(2.97), floor_area_m2=m(14.3, "m2"), openings=[])
    rm = match_room(pred, truth)
    assert rm.missed_openings == [] and rm.phantom_openings == []


def test_open_plan_rooms_are_not_scored_on_walls():
    from cozmo.contracts.models import Measurement, Room
    from cozmo.eval.matching import match_room
    from cozmo.io.ground_truth import GTOpening, GTRoom

    def m(v, unit="m"):
        return Measurement(value=v, ci_low=v - 0.05, ci_high=v + 0.05, unit=unit, method="t")

    truth = GTRoom(id="hall", ceiling_height_m=2.97, score_walls=False, walls=[],
                   openings=[GTOpening(id="d", type="door", wall_id="A", offset_along_wall_m=0.0,
                                       width_m=0.9144, height_m=1.9812)])
    pred = Room(id="hall", label="hall", polygon=[(0.0, 0.0), (5.0, 0.0), (5.0, 3.0), (0.0, 3.0)],
                walls=[dict(id="w1", start=(0.0, 0.0), end=(5.0, 0.0), length_m=m(5.0), height_m=m(2.97))],
                ceiling_height_m=m(2.97), floor_area_m2=m(15.0, "m2"), openings=[])
    rm = match_room(pred, truth)
    assert rm.scored_walls is False
    assert rm.wall_pairs == [] and rm.unmatched_truth_walls == [] and rm.unmatched_pred_walls == []
