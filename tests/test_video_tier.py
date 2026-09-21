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


# ----------------------------------------------------------------- the seam

def _box_room(width: float = 4.0, depth: float = 3.0, height: float = 2.7,
              wall_thickness: float = 0.12, noise_m: float = 0.04, step: float = 0.04):
    """A rectangular room as the video tier would hand it over: points, normals, path.

    Noise is set to the wall spread spike 2 measured for this tier, 4 cm, so the
    test exercises the backend at the tolerance the tier actually ships with.
    """
    rng = np.random.default_rng(7)
    pts, nrm = [], []

    def face(axis: int, pos: float, normal_sign: float, lo: float, hi: float):
        a = np.arange(lo, hi, step)
        y = np.arange(0.02, height, step)
        A, Y = np.meshgrid(a, y)
        P = np.zeros((A.size, 3))
        P[:, axis] = pos + rng.normal(0, noise_m, A.size)
        P[:, 1] = Y.ravel()
        P[:, 2 if axis == 0 else 0] = A.ravel()
        n = np.zeros((A.size, 3))
        n[:, axis] = normal_sign
        pts.append(P)
        nrm.append(n)

    # Inner faces look inward; outer faces of the same walls look outward.
    face(0, 0.0, 1.0, 0.0, depth)
    face(0, -wall_thickness, -1.0, 0.0, depth)
    face(0, width, -1.0, 0.0, depth)
    face(0, width + wall_thickness, 1.0, 0.0, depth)
    face(2, 0.0, 1.0, 0.0, width)
    face(2, -wall_thickness, -1.0, 0.0, width)
    face(2, depth, -1.0, 0.0, width)
    face(2, depth + wall_thickness, 1.0, 0.0, width)

    gx, gz = np.meshgrid(np.arange(0, width, step), np.arange(0, depth, step))
    flat = np.column_stack([gx.ravel(), np.zeros(gx.size), gz.ravel()])
    pts.append(flat + rng.normal(0, 0.005, flat.shape) * np.array([0, 1, 0]))
    nrm.append(np.tile([0.0, 1.0, 0.0], (len(flat), 1)))
    ceil = flat.copy()
    ceil[:, 1] = height
    pts.append(ceil)
    nrm.append(np.tile([0.0, -1.0, 0.0], (len(ceil), 1)))

    t = np.linspace(0, 1, 60)
    path = np.column_stack([width / 2 + 0.8 * np.cos(2 * np.pi * t),
                            np.full(60, 1.4),
                            depth / 2 + 0.6 * np.sin(2 * np.pi * t)])
    return np.vstack(pts), np.vstack(nrm), path


def test_the_adapter_turns_a_synthetic_room_into_a_one_room_plan(tmp_path):
    """The seam into the LiDAR backend works on video-tier shaped input.

    Model free on purpose: no weights, no GPU, no COLMAP. What is under test is
    that points, normals and a camera path with this tier's configuration and
    noise come out as a plan with the right room and the right wall lengths.
    """
    from cozmo.pipeline.video.adapter import plan_from_cloud
    from cozmo.pipeline.video.drift import YawSnapModel
    from cozmo.pipeline.video.pipeline import VideoPipeline

    points, normals, path = _box_room(width=4.0, depth=3.0)
    config = load_config("config/gates.yaml")
    config["run"] = {"pipeline": "video", "drift_correction": True, "video_rotation": "auto"}
    capture = tmp_path / "synthetic_room"
    capture.mkdir()
    (capture / "clip.mp4").write_bytes(b"not decoded by this test")

    pipeline = VideoPipeline()
    pipeline.input_manifest_sha256 = "0" * 64
    built = plan_from_cloud(points, normals, path, np.linspace(0, 6, len(path)), len(path),
                            capture, "video", config, 0, pipeline,
                            IntervalBudget(coverage=1.0), YawSnapModel({"applied": True, "per_chunk": []}),
                            warnings=[], assumptions=[])

    plan = built.plan
    assert len(plan.rooms) == 1, [r.id for r in plan.rooms]
    room = plan.rooms[0]
    lengths = sorted(w.length_m.value for w in room.walls)
    assert len(lengths) == 4, lengths
    # A rectangle: two walls near 3 m and two near 4 m.
    assert lengths[0] == pytest.approx(3.0, abs=0.25) and lengths[1] == pytest.approx(3.0, abs=0.25)
    assert lengths[2] == pytest.approx(4.0, abs=0.25) and lengths[3] == pytest.approx(4.0, abs=0.25)
    assert room.ceiling_height_m.value == pytest.approx(2.7, abs=0.1)
    # Every measurement carries an interval, and none is tighter than the floor.
    for w in room.walls:
        assert w.length_m.ci_low < w.length_m.value < w.length_m.ci_high
        assert w.length_m.width / 2 >= 0.03


def test_a_fragment_reports_a_wider_interval_than_a_full_capture(tmp_path):
    """Same geometry, different coverage: the fragment must not claim as much."""
    from cozmo.pipeline.video.adapter import plan_from_cloud
    from cozmo.pipeline.video.drift import YawSnapModel
    from cozmo.pipeline.video.pipeline import VideoPipeline

    points, normals, path = _box_room()
    config = load_config("config/gates.yaml")
    config["run"] = {"pipeline": "video", "drift_correction": True, "video_rotation": "auto"}
    capture = tmp_path / "synthetic_room"
    capture.mkdir()
    (capture / "clip.mp4").write_bytes(b"")

    widths = []
    for coverage in (1.0, 0.25):
        pipeline = VideoPipeline()
        pipeline.input_manifest_sha256 = "0" * 64
        built = plan_from_cloud(points, normals, path, np.linspace(0, 6, len(path)), len(path),
                                capture, "video", config, 0, pipeline,
                                IntervalBudget(coverage=coverage), YawSnapModel({"applied": True, "per_chunk": []}),
                                warnings=[], assumptions=[])
        widths.append(max(w.length_m.width for w in built.plan.rooms[0].walls))
    assert widths[1] > widths[0]


# --------------------------------------------------------- dense unprojection

def _one_frame_build(scale: float, camera_centre_sfm: np.ndarray, depth_m: float, n: int = 9):
    """A DenseBuild holding one camera and one constant-depth map.

    The camera looks down +z with no rotation, so a pixel at the principal point
    must land exactly ``depth_m`` metres in front of the camera's metric centre.
    """
    from cozmo.pipeline.video.dense import DenseBuild, Keyframe
    from cozmo.pipeline.video.sfm import SfmChunk

    M = np.eye(4)
    M[:3, 3] = -camera_centre_sfm          # R = I, so t = -centre
    chunk = SfmChunk(index=0, names=["f00001.jpg"], times_s=np.zeros(1),
                     cam_from_world=M[None, ...], obs_uv=np.zeros((0, 2), np.float32),
                     obs_z=np.zeros(0, np.float32), obs_off=np.array([0, 0]),
                     xyz=np.zeros((0, 3)), focal_px=500.0,
                     cam_params=np.array([500.0, n / 2, n / 2, 0.0]), cam_wh=(n, n),
                     mean_reproj_err_px=0.5, scale_m_per_unit=scale)
    ax = (np.arange(n) - (n - 1) / 2) / 500.0
    rays_x, rays_y = np.meshgrid(ax, ax)
    build = DenseBuild(keyframes=[Keyframe(chunk=0, i=0, zmap=np.full((n, n), depth_m, np.float16))],
                       rays={0: (rays_x, rays_y)}, chunks=[chunk], group=[0])
    return build, chunk


def test_fused_points_sit_at_their_metric_depth_from_the_camera():
    """The depth map is metric and the pose is in SfM units, so the pose gets scaled.

    Scaling the points instead silently shrinks every one of them toward its own
    camera centre by a factor of s, which leaves the camera path correct and the
    geometry collapsed. This caught exactly that.
    """
    scale, depth = 0.2, 3.0
    centre_sfm = np.array([10.0, 0.0, 0.0])
    build, _ = _one_frame_build(scale, centre_sfm, depth)
    cloud = build.fuse({0: (np.eye(3), np.zeros(3))}, voxel_m=0.01)

    centre_m = scale * centre_sfm
    assert np.allclose(cloud.camera_path[0], centre_m)
    assert len(cloud.points) > 0
    # Every point is depth metres in front of the camera, along +z.
    offsets = cloud.points - centre_m
    assert offsets[:, 2] == pytest.approx(depth, abs=0.02)
    assert np.abs(offsets[:, :2]).max() < 0.05
    # The cloud must be at the right distance, not squashed onto the camera.
    assert np.linalg.norm(offsets, axis=1).min() == pytest.approx(depth, abs=0.02)


def test_a_chunk_transform_moves_the_fused_points_with_it():
    """The group transform is applied in metres, after the pose conversion."""
    build, _ = _one_frame_build(0.2, np.array([10.0, 0.0, 0.0]), 3.0)
    shift = np.array([5.0, -1.0, 2.0])
    a = build.fuse({0: (np.eye(3), np.zeros(3))}, voxel_m=0.01)
    b = build.fuse({0: (np.eye(3), shift)}, voxel_m=0.01)
    assert np.allclose(np.sort(b.points, axis=0) - np.sort(a.points, axis=0), shift, atol=1e-3)


def test_the_scale_gate_widens_to_the_chunks_own_measured_error():
    """A chunk whose scale is known to 12% cannot be held to a 15% agreement."""
    from cozmo.pipeline.video.bridge import scale_standard_error
    from cozmo.pipeline.video.sfm import SfmChunk

    def chunk(ratios):
        c = SfmChunk(index=0, names=[], times_s=np.zeros(0), cam_from_world=np.zeros((0, 4, 4)),
                     obs_uv=np.zeros((0, 2)), obs_z=np.zeros(0), obs_off=np.array([0]),
                     xyz=np.zeros((0, 3)), focal_px=1.0, cam_params=np.zeros(4), cam_wh=(1, 1),
                     mean_reproj_err_px=0.0)
        c.scale_frame_ratios = np.array(ratios)
        c.scale_m_per_unit = float(np.median(ratios))
        return c

    tight = chunk([0.200, 0.201, 0.199, 0.200, 0.202, 0.198] * 2)
    loose = chunk([0.20, 0.28, 0.14, 0.31, 0.11, 0.22] * 2)
    assert scale_standard_error(tight) < 0.01
    assert scale_standard_error(loose) > 0.08
    # A chunk with no scale frames yet must not claim a spurious precision.
    assert scale_standard_error(chunk([0.2])) == 0.0


def test_an_impossible_camera_height_is_reported_as_a_scale_error():
    """A monocular scale error is invisible in the plan: a room scaled by 1.9 looks
    like a bigger room. The camera height is the one quantity with a known answer."""
    from cozmo.pipeline.video.adapter import camera_height_check

    class _Floor:
        def height_at(self, xz):
            return np.zeros(len(xz))

    class _Levels:
        floor = _Floor()

    def path(y):
        return np.column_stack([np.zeros(10), np.full(10, y), np.zeros(10)])

    h, warn = camera_height_check(path(1.45), _Levels(), np.zeros((0, 3)))
    assert h == pytest.approx(1.45) and warn is None
    h, warn = camera_height_check(path(2.61), _Levels(), np.zeros((0, 3)))
    assert h == pytest.approx(2.61) and warn and "1.8x" in warn
    h, warn = camera_height_check(path(0.43), _Levels(), np.zeros((0, 3)))
    assert warn and "0.3x" in warn
    assert camera_height_check(np.zeros((0, 3)), _Levels(), np.zeros((0, 3)))[1] is None
