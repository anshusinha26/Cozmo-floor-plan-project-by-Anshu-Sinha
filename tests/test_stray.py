"""Stray Scanner reader: parsing, intrinsics scaling, tier isolation, floor regression."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from cozmo.io.inputs import InputError, validate_input
from cozmo.io.stray import StrayScan, TierViolation
from tests.synth_stray import one_room, write_synthetic_scan

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "sample" / "c00a170fe1"


@pytest.fixture(scope="module")
def synth(tmp_path_factory):
    return write_synthetic_scan(tmp_path_factory.mktemp("scan") / "synth", one_room(), n_per_room=12)


def test_odometry_parsed_with_stripped_headers(synth):
    scan = StrayScan(synth, "lidar")
    od = scan.odometry
    assert od["frame"][0] == 0 and od["frame"].dtype.kind == "i"
    assert od["t"].shape == (scan.n_frames, 3) and od["q"].shape == (scan.n_frames, 4)
    assert np.all(od["timestamp"][1:] > od["timestamp"][:-1])


def test_frames_scale_intrinsics_to_depth_resolution(synth):
    scan = StrayScan(synth, "lidar")
    f = next(scan.frames(stride=1))
    assert f.depth.shape == (192, 256) and f.depth.dtype == np.float32
    assert f.fx == pytest.approx(1596.0 * 256 / 1920)
    assert f.cx == pytest.approx(955.5 * 256 / 1920)
    assert f.confidence.max() == 2
    assert np.abs(np.linalg.det(f.R) - 1.0) < 1e-6


def test_stride_and_file_list(synth):
    scan = StrayScan(synth, "lidar")
    n = sum(1 for _ in scan.frames(stride=5))
    assert n == (scan.n_frames + 4) // 5
    names = {p.relative_to(synth).as_posix() for p in scan.files()}
    assert "odometry.csv" in names and "depth/000000.png" in names and "rgb.mp4" in names


def test_video_tier_may_only_open_rgb(synth):
    scan = StrayScan(synth, "video")
    assert [p.name for p in scan.files()] == ["rgb.mp4"]
    with pytest.raises(TierViolation):
        _ = scan.odometry
    with pytest.raises(TierViolation):
        next(scan.frames(stride=1))
    with pytest.raises(TierViolation):
        scan.open("depth/000000.png")


def test_validate_input_lidar_and_video_layouts(synth, tmp_path):
    spec = validate_input(synth, "lidar")
    assert spec.n_frames == StrayScan(synth, "lidar").n_frames and spec.rooms is None
    spec = validate_input(synth, "video")
    assert [p.name for p in spec.files] == ["rgb.mp4"]
    bad = tmp_path / "bad"
    (bad / "depth").mkdir(parents=True)
    (bad / "confidence").mkdir()
    (bad / "odometry.csv").write_text("timestamp, frame\n")
    with pytest.raises(InputError, match="depth"):
        validate_input(bad, "lidar")
    with pytest.raises(InputError, match="rgb.mp4"):
        validate_input(bad, "video")


def test_photo_tier_rejects_scan_layout(synth):
    # Without the scan-folder check the photo tier would read depth png files as room images.
    with pytest.raises(InputError, match="may not read scan data"):
        validate_input(synth, "photo")


@pytest.mark.skipif(not SAMPLE.exists(), reason="sample data not present")
def test_real_scan_floor_peak_near_minus_1_48():
    """Regression for the unprojection convention: floor of c00a170fe1 is a sharp peak at y = -1.48 m."""
    scan = StrayScan(SAMPLE, "lidar")
    ys = []
    for f in scan.frames(stride=20):
        m = (f.confidence == 2) & (f.depth > 0.2) & (f.depth < 4.5)
        p = f.unproject(m)
        ys.append(p[:, 1])
    ys = np.concatenate(ys)
    h, e = np.histogram(ys, bins=np.arange(-3.0, 3.0, 0.01))
    peak = e[np.argmax(h)]
    assert abs(peak - (-1.48)) <= 0.02, peak
