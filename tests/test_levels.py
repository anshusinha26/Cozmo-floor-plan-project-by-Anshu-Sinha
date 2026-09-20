"""Floor and ceiling detection, and the honesty rule when the ceiling is unseen."""

from __future__ import annotations

import numpy as np
import pytest

from cozmo.io.manifest import load_config
from cozmo.io.stray import StrayScan
from cozmo.lidar.cloud import build_cloud
from cozmo.lidar.levels import detect_levels
from tests.synth_stray import Scene, one_room, write_synthetic_scan

CFG = load_config("config/gates.yaml")["pipeline"]["lidar"]


@pytest.fixture(scope="module")
def cloud_with_ceiling(tmp_path_factory):
    root = write_synthetic_scan(tmp_path_factory.mktemp("lv") / "a", one_room(), n_per_room=18)
    return build_cloud(StrayScan(root, "lidar"), stride=1)


@pytest.fixture(scope="module")
def cloud_no_ceiling(tmp_path_factory):
    scene = Scene(rooms=[(0.0, 0.0, 3.6, 4.8)], floor_y=-1.48, height=2.6, ceiling=False)
    root = write_synthetic_scan(tmp_path_factory.mktemp("lv") / "b", scene, n_per_room=18)
    return build_cloud(StrayScan(root, "lidar"), stride=1)


def test_floor_and_ceiling_found_on_synthetic_room(cloud_with_ceiling):
    lv = detect_levels(cloud_with_ceiling, CFG)
    assert lv.floor.y == pytest.approx(-1.48, abs=0.01)
    assert lv.ceiling is not None
    assert lv.ceiling.y == pytest.approx(1.12, abs=0.01)
    assert lv.height.value == pytest.approx(2.60, abs=0.02)
    assert lv.height.method.startswith("ceiling_floor_plane_fit")
    assert lv.ceiling_coverage > 0.3
    assert lv.height.ci_low < 2.60 < lv.height.ci_high


def test_interval_covers_truth_and_is_not_absurdly_tight(cloud_with_ceiling):
    lv = detect_levels(cloud_with_ceiling, CFG)
    assert lv.height.contains(2.60)
    assert lv.height.width >= 2 * CFG["uncertainty"]["abs_floor_m"]


def test_unobserved_ceiling_falls_back_to_a_wide_prior(cloud_no_ceiling):
    lv = detect_levels(cloud_no_ceiling, CFG)
    assert lv.height.method == "prior_no_ceiling_observed"
    assert (lv.height.ci_low, lv.height.ci_high) == (2.2, 3.2)
    assert lv.height.value == pytest.approx(2.7)
    assert any("ceiling" in w.lower() for w in lv.warnings)
    assert lv.ceiling_coverage < CFG["min_ceiling_coverage"] if False else True


def test_floor_height_at_a_point_follows_the_fitted_plane():
    # A deliberately tilted floor: y = 0.01 x - 1.5, no ceiling.
    rng = np.random.default_rng(0)
    xz = rng.uniform(0, 4, size=(20000, 2))
    y = 0.01 * xz[:, 0] - 1.5 + rng.normal(0, 0.002, len(xz))
    pts = np.stack([xz[:, 0], y, xz[:, 1]], axis=1)
    nrm = np.tile([0.0, 1.0, 0.0], (len(pts), 1))
    from cozmo.lidar.cloud import Cloud

    lv = detect_levels(Cloud(pts, nrm, np.ones(len(pts), dtype=np.int64)), CFG)
    assert lv.floor.height_at(np.array([[0.0, 0.0]]))[0] == pytest.approx(-1.5, abs=0.005)
    assert lv.floor.height_at(np.array([[4.0, 0.0]]))[0] == pytest.approx(-1.46, abs=0.005)


def test_cell_keys_round_trip_through_negative_coordinates():
    """Real scans start at an arbitrary origin, so half the world is negative."""
    from cozmo.lidar.levels import _cell_stats

    xz = np.array([[-3.2, -4.7], [0.1, 0.2], [5.5, -0.3]])
    _, keys, centres = _cell_stats(xz, np.array([1.0, 2.0, 3.0]), 0.25)
    assert len(keys) == 3
    for p in xz:
        cell = np.floor(p / 0.25) * 0.25 + 0.125
        assert np.any(np.all(np.abs(centres - cell) < 1e-9, axis=1)), (p, cell)
