"""The stub pipeline exists only to exercise the harness and must say so loudly."""

from __future__ import annotations

import logging

import pytest

from cozmo.contracts.models import Measurement, Plan
from cozmo.pipeline.base import Pipeline
from cozmo.pipeline.stub import STUB_WARNING, StubPipeline


@pytest.fixture
def capture_dir(tmp_path):
    d = tmp_path / "apt_living_01"
    (d / "living").mkdir(parents=True)
    (d / "living" / "a.jpg").write_bytes(b"1")
    (d / "living" / "b.jpg").write_bytes(b"2")
    return d


def test_base_pipeline_is_abstract():
    with pytest.raises(TypeError):
        Pipeline()  # type: ignore[abstract]


def test_stub_returns_two_room_plan_marked_as_stub(capture_dir, caplog):
    with caplog.at_level(logging.WARNING, logger="cozmo.pipeline.stub"):
        plan = StubPipeline().run(capture_dir, "photo", {}, seed=0)
    assert isinstance(plan, Plan)
    assert len(plan.rooms) == 2
    assert STUB_WARNING in plan.warnings
    assert any(STUB_WARNING in rec.getMessage() for rec in caplog.records)
    assert plan.capture.id == "apt_living_01"
    assert plan.capture.tier == "photo"


def test_stub_intervals_are_wide_not_point_estimates(capture_dir):
    plan = StubPipeline().run(capture_dir, "photo", {}, seed=0)
    widths = [
        m.width
        for room in plan.rooms
        for m in [room.ceiling_height_m, room.floor_area_m2]
        + [w.length_m for w in room.walls]
        + [o.width_m for o in room.openings]
    ]
    assert widths and all(w > 0 for w in widths)


def test_stub_records_stage_timings(capture_dir):
    p = StubPipeline()
    p.run(capture_dir, "photo", {}, seed=0)
    assert p.stage_timings_s and all(t >= 0 for t in p.stage_timings_s.values())


def test_stub_has_adjacency_via_door_and_surfaces_for_every_room(capture_dir):
    plan = StubPipeline().run(capture_dir, "photo", {}, seed=0)
    assert plan.adjacency and plan.adjacency[0].via_opening_id is not None
    rooms_with_surfaces = {s.room_id for s in plan.surfaces}
    assert rooms_with_surfaces == {r.id for r in plan.rooms}
    assert all(isinstance(p.theta_deg, Measurement) for p in plan.stitched_plan.placements)
