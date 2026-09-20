"""Calibration maths on synthetic data with known coverage."""

from __future__ import annotations

import pytest

from cozmo.contracts.models import Measurement
from cozmo.eval.calibration import CalItem, calibration_table, summarize
from cozmo.eval.repeatability import repeat_pairs


def _item(truth, value, half, tier="video", quantity="wall_length"):
    m = Measurement(value=value, ci_low=value - half, ci_high=value + half, unit="m", method="t")
    return CalItem(tier=tier, quantity=quantity, pred=m, truth=truth)


def test_coverage_and_width_on_synthetic_items():
    items = [_item(2.0, 2.0, 0.1) for _ in range(95)]           # inside, width 0.2 = 10% of value
    items += [_item(2.0, 2.5, 0.1) for _ in range(5)]           # outside, same width
    row = summarize(items)
    assert row["n"] == 100
    assert row["coverage"] == pytest.approx(0.95)
    assert row["mean_width_pct"] == pytest.approx(0.2 / 2.0 * 100 * 95 / 100 + 0.2 / 2.5 * 100 * 5 / 100)
    assert row["outside"] == 5


def test_confident_garbage_counts_narrow_and_wrong_only():
    wide_ok = [_item(2.0, 2.0, 0.5) for _ in range(10)]       # width 1.0
    narrow_ok = [_item(2.0, 2.0, 0.05) for _ in range(10)]    # width 0.1
    narrow_wrong = [_item(2.0, 3.0, 0.05) for _ in range(3)]  # outside, narrower than median
    wide_wrong = [_item(2.0, 3.0, 0.5) for _ in range(2)]     # outside, not narrower than median
    row = summarize(wide_ok + narrow_ok + narrow_wrong + wide_wrong)
    assert row["outside"] == 5
    assert row["confident_garbage"] == 3


def test_table_breaks_down_by_tier_and_quantity():
    items = [_item(2.0, 2.0, 0.1, "photo", "wall_length"), _item(2.7, 2.9, 0.05, "photo", "ceiling_height"),
             _item(2.0, 2.0, 0.1, "lidar", "wall_length")]
    t = calibration_table(items)
    assert t["overall"]["n"] == 3
    assert set(t["by_tier"]) == {"photo", "lidar"}
    assert t["by_quantity"]["ceiling_height"]["coverage"] == 0.0
    assert t["by_tier_quantity"]["photo/wall_length"]["n"] == 1


def test_empty_table_is_explicit():
    t = calibration_table([])
    assert t["overall"]["n"] == 0 and t["overall"]["coverage"] is None


def test_repeat_pairs_join_same_space_and_tier_on_truth_wall_id():
    caps = [
        {"capture_id": "a", "space_id": "s", "tier": "video", "walls": {("r", "east"): 4.00, ("r", "north"): 5.0}},
        {"capture_id": "b", "space_id": "s", "tier": "video", "walls": {("r", "east"): 4.02}},
        {"capture_id": "c", "space_id": "s", "tier": "photo", "walls": {("r", "east"): 4.10}},
        {"capture_id": "d", "space_id": "other", "tier": "video", "walls": {("r", "east"): 4.10}},
    ]
    pairs = repeat_pairs(caps)
    assert len(pairs) == 1
    p = pairs[0]
    assert (p["capture_a"], p["capture_b"], p["wall_id"]) == ("a", "b", "east")
    assert (p["a"], p["b"]) == (4.00, 4.02)
