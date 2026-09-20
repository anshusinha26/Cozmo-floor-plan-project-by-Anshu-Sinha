"""Ground-truth YAML and the benchmark registry load and cross-check."""

from __future__ import annotations

from pathlib import Path

import pytest

from cozmo.io.ground_truth import GroundTruth, load_ground_truth, load_registry

REPO = Path(__file__).resolve().parent.parent


def test_example_ground_truth_loads():
    gt = load_ground_truth(REPO / "benchmarks" / "ground_truth" / "EXAMPLE.yaml")
    assert gt.capture_id == "EXAMPLE"
    assert gt.tier == "photo"
    living = gt.room("living")
    assert living.walls[0].id == gt.main_door_wall_id("living")
    assert living.opening_ids()


def test_ground_truth_opening_must_reference_wall():
    with pytest.raises(ValueError, match="wall_id"):
        GroundTruth.model_validate(
            {
                "capture_id": "x",
                "space_id": "s",
                "tier": "video",
                "device": "d",
                "measured_with": "tape",
                "measured_on": "2026-09-21",
                "rooms": [
                    {
                        "id": "r",
                        "ceiling_height_m": 2.7,
                        "floor_area_m2": 10.0,
                        "walls": [{"id": "w1", "length_m": 4.0}],
                        "openings": [{"id": "o1", "type": "door", "wall_id": "w9", "offset_along_wall_m": 1.0, "width_m": 0.8, "height_m": 2.0}],
                    }
                ],
            }
        )


def test_registry_lists_example_captures_with_existing_paths():
    reg = load_registry(REPO / "benchmarks" / "captures.yaml")
    ids = [c.capture_id for c in reg.captures]
    assert "EXAMPLE" in ids and "EXAMPLE_REPEAT" in ids
    for c in reg.captures:
        if c.ground_truth is not None:
            assert (REPO / c.ground_truth).is_file(), c.ground_truth
    sample = [c for c in reg.captures if c.ground_truth is None]
    assert sample, "sample lidar scans should be registered with truth null"
    assert all(c.tier == "lidar" for c in sample)
    rep = reg.by_id("EXAMPLE_REPEAT")
    assert rep.repeat_of == "EXAMPLE"
    assert rep.space_id == reg.by_id("EXAMPLE").space_id
