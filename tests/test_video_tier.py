"""Video-tier unit tests.

Nothing here downloads a weight file or touches a GPU: the model-bound stages
are exercised through their pure parts (the fits, the gates, the algebra) and
the seam into the plan backend is exercised on a synthetic room.
"""

from __future__ import annotations

import numpy as np
import pytest

from cozmo.io.manifest import load_config
from cozmo.pipeline import pipeline_for
from cozmo.pipeline.video.bridge import BridgeAttempt, _largest_group, umeyama
from cozmo.pipeline.video.dense import normals_from_pointmap, robust_scale_shift
from cozmo.pipeline.video.drift import apply_rotation, wrap_to_quarter
from cozmo.pipeline.video.frames import plan_fps
from cozmo.pipeline.video.intervals import IntervalBudget, build_budget
from cozmo.pipeline.video.probe import VideoInfo, find_video
from cozmo.pipeline.video.scale import relative_spread
from cozmo.pipeline.video.up import fit_floor, rotation_between


def _info(**kw) -> VideoInfo:
    base = dict(path="x.mp4", width=3840, height=2160, fps=30.0, codec="h264",
                duration_s=44.1, rotation_deg=None, size_bytes=1, n_frames=None)
    base.update(kw)
    return VideoInfo(**base)


# --------------------------------------------------------------------- probe

def test_upright_wh_follows_the_rotation_tag():
    assert _info().upright_wh == (3840, 2160)
    assert _info(rotation_deg=-90).upright_wh == (2160, 3840)
    assert _info(rotation_deg=180).upright_wh == (3840, 2160)


def test_find_video_globs_and_refuses_ambiguity(tmp_path):
    (tmp_path / "photo.jpeg").write_bytes(b"")
    (tmp_path / "some_loop.MOV").write_bytes(b"")
    assert find_video(tmp_path).name == "some_loop.MOV"
    (tmp_path / "other.mp4").write_bytes(b"")
    with pytest.raises(Exception):
        find_video(tmp_path)


# -------------------------------------------------------------------- frames

def test_fps_is_lowered_until_the_clip_fits_the_frame_budget():
    assert plan_fps(_info(duration_s=44.1), 10.0, 600) == pytest.approx(10.0)
    # 86 s at 10 fps would be 860 frames, over the budget.
    got = plan_fps(_info(duration_s=86.0), 10.0, 600)
    assert got < 10.0
    assert got * 86.0 == pytest.approx(600.0)


# -------------------------------------------------------------------- bridge

def test_umeyama_recovers_an_exact_similarity():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(8, 3))
    th = 0.7
    R = np.array([[np.cos(th), -np.sin(th), 0], [np.sin(th), np.cos(th), 0], [0, 0, 1]])
    Y = (2.5 * (R @ X.T)).T + np.array([1.0, 2.0, 3.0])
    fit = umeyama(X, Y)
    assert fit.s == pytest.approx(2.5)
    assert fit.rms_m == pytest.approx(0.0, abs=1e-9)
    assert np.allclose(fit.R, R)


def test_umeyama_refuses_degenerate_input():
    with pytest.raises(ValueError):
        umeyama(np.zeros((5, 3)), np.ones((5, 3)))


def test_largest_group_prefers_the_most_frames_not_the_most_chunks():
    # 0-1 bridged and hold 200 frames; 2-3-4 bridged and hold 60.
    group = _largest_group(5, [(0, 1), (2, 3), (3, 4)], [100, 100, 20, 20, 20])
    assert sorted(group) == [0, 1]


def test_an_unbridged_chunk_forms_its_own_group():
    assert _largest_group(3, [], [5, 9, 1]) == [1]


def test_bridge_attempt_records_why_it_was_rejected():
    a = BridgeAttempt(0, 1, False, "implied scales disagree by 40%", 0.01, 0.02, 1.4)
    assert not a.accepted and "disagree" in a.reason


# --------------------------------------------------------------------- dense

def test_robust_scale_shift_ignores_outliers():
    d = np.linspace(1.0, 4.0, 60)
    z = 2.0 * d + 0.5
    z[:6] = 99.0  # a mirror, a moving dog, a blown-out highlight
    a, b = robust_scale_shift(d, z)
    assert a == pytest.approx(2.0, abs=0.05)
    assert b == pytest.approx(0.5, abs=0.1)


def test_normals_of_a_frontal_plane_point_back_at_the_camera():
    h = w = 20
    z = np.full((h, w), 2.0)
    xs = (np.arange(w) - w / 2) / 50.0
    ys = (np.arange(h) - h / 2) / 50.0
    X, Y = np.meshgrid(xs, ys)
    P = np.stack([X * z, Y * z, z], axis=-1)
    n, ok = normals_from_pointmap(P, z)
    assert ok[5:-5, 5:-5].all()
    assert np.allclose(n[ok][:, 2], -1.0, atol=1e-6)


# ----------------------------------------------------------------- up, drift

def test_floor_plane_is_found_through_a_tilt_and_a_wall():
    rng = np.random.default_rng(0)
    th = np.deg2rad(10)
    Rx = np.array([[1, 0, 0], [0, np.cos(th), -np.sin(th)], [0, np.sin(th), np.cos(th)]])
    floor = np.column_stack([rng.uniform(-2, 2, 4000), np.zeros(4000), rng.uniform(-2, 2, 4000)]) @ Rx.T
    wall = np.column_stack([np.full(2000, 2.0), rng.uniform(0, 2.5, 2000), rng.uniform(-2, 2, 2000)]) @ Rx.T
    P = np.vstack([floor, wall])
    N = np.vstack([np.tile([0, 1, 0], (4000, 1)), np.tile([1, 0, 0], (2000, 1))]) @ Rx.T
    cams = np.tile((Rx @ np.array([0.0, 1.0, 0.15]))[None, :], (20, 1))
    g = fit_floor(P, N, cams)
    assert g.method == "ransac_floor_plane"
    up = g.rotation_to_y_up() @ g.normal
    assert up[1] == pytest.approx(1.0, abs=1e-6)


def test_gravity_falls_back_to_the_cameras_when_there_is_no_floor():
    g = fit_floor(np.zeros((10, 3)), np.zeros((10, 3)), np.tile([0.0, 1.0, 0.0], (4, 1)))
    assert g.method.startswith("camera_up_only")


def test_rotation_between_handles_the_antiparallel_case():
    R = rotation_between(np.array([0.0, 1.0, 0.0]), np.array([0.0, -1.0, 0.0]))
    assert np.allclose(R @ np.array([0.0, 1.0, 0.0]), np.array([0.0, -1.0, 0.0]))


def test_yaw_wraps_into_the_quarter_turn_walls_repeat_on():
    assert np.degrees(wrap_to_quarter(np.deg2rad(91))) == pytest.approx(1.0)
    assert np.degrees(wrap_to_quarter(np.deg2rad(-89))) == pytest.approx(1.0)
    assert np.degrees(wrap_to_quarter(np.deg2rad(44))) == pytest.approx(44.0)


def test_apply_rotation_moves_every_chunk_together():
    R = rotation_between(np.array([0.0, 0.0, 1.0]), np.array([0.0, 1.0, 0.0]))
    tf = {0: (np.eye(3), np.zeros(3)), 1: (np.eye(3), np.array([1.0, 0.0, 0.0]))}
    out = apply_rotation(tf, R)
    assert np.allclose(out[0][0], R)
    assert np.allclose(out[1][1], R @ np.array([1.0, 0.0, 0.0]))


# ----------------------------------------------------------------- intervals

def test_scale_spread_is_robust_to_one_wild_frame():
    r = np.array([0.20, 0.21, 0.19, 0.205, 9.0])
    assert relative_spread(r) < 0.1


def test_low_coverage_widens_every_interval_and_warns():
    tight = IntervalBudget(coverage=0.9)
    loose = IntervalBudget(coverage=0.3)
    assert not tight.widened and tight.factor == 1.0
    assert loose.widened and loose.effective_bias > tight.effective_bias
    assert any("fragment" in w for w in loose.warnings())
    assert not tight.warnings()


def test_budget_combines_the_measured_spread_with_the_systematic_term():
    rows = [{"chunk": 0, "n_images": 100, "scale_rel_sem": 0.10, "scale_m_per_unit": 0.20},
            {"chunk": 1, "n_images": 20, "scale_rel_sem": 0.30, "scale_m_per_unit": 0.26},
            {"chunk": 9, "n_images": 99, "scale_rel_sem": 0.99, "scale_m_per_unit": 9.0}]
    b = build_budget(rows, [0, 1], coverage=1.0, cfg={"uncertainty": {}})
    assert b.systematic == 0.03
    # Chunk 9 is not in the group, so it must not reach the budget.
    assert b.scale_sem < 0.2
    assert b.effective_bias > b.systematic
    assert any("disagreed with itself" in n for n in b.notes)


def test_budget_never_reports_tighter_than_the_systematic_term():
    b = build_budget([], [], coverage=1.0, cfg={"uncertainty": {}})
    assert b.effective_bias == pytest.approx(0.03)


# -------------------------------------------------------------------- wiring

def test_the_video_tier_is_registered_and_configured():
    assert pipeline_for("video") == "video"
    cfg = load_config("config/gates.yaml")["pipeline"]["video"]
    assert cfg["sfm"]["min_chunk_images"] == 15
    assert cfg["uncertainty"]["systematic_scale_bias"] == 0.03
    # Wall tolerance must be looser than the LiDAR tier's or 4 cm faces are missed.
    lidar = load_config("config/gates.yaml")["pipeline"]["lidar"]
    assert cfg["wall"]["hist_bin_m"] > lidar["wall"]["hist_bin_m"]
    assert cfg["room"]["snap_m"] > lidar["room"]["snap_m"]
    assert cfg["uncertainty"]["abs_floor_m"] > lidar["uncertainty"]["abs_floor_m"]
