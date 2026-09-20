"""Fix loop 2: camera-height scale, levelled bridging, single-room fitting.

Model free. What is under test is the algebra and the decisions, not the
networks: whether a scale derived from a known camera height is right, whether a
bridge between two upright chunks reduces to a yaw and a slide, and whether a
room can always be fitted around a camera path.
"""

from __future__ import annotations

import numpy as np
import pytest

from cozmo.io.manifest import load_config
from cozmo.lidar.walls import ManhattanFrame, WallFace
from cozmo.pipeline.video.bridge import planar, yaw_matrix, yaw_of
from cozmo.pipeline.video.height_prior import height_prior_scale
from cozmo.pipeline.video.scale_solve import solve
from cozmo.pipeline.video.singleroom import as_room_result, fit_single_room

CFG = load_config("config/gates.yaml")["pipeline"]["video"]


def _room_points(width=4.0, depth=3.0, height=2.7, n=4000, seed=0):
    """Floor, ceiling and four walls, with normals, in a y-up metric frame."""
    rng = np.random.default_rng(seed)
    floor = np.column_stack([rng.uniform(0, width, n), np.zeros(n), rng.uniform(0, depth, n)])
    fn = np.tile([0.0, 1.0, 0.0], (n, 1))
    walls, wn = [], []
    for axis, pos, nrm in ((0, 0.0, [1, 0, 0]), (0, width, [-1, 0, 0]),
                           (2, 0.0, [0, 0, 1]), (2, depth, [0, 0, -1])):
        p = np.zeros((n, 3))
        p[:, 1] = rng.uniform(0.0, height, n)
        p[:, axis] = pos
        p[:, 2 if axis == 0 else 0] = rng.uniform(0, depth if axis == 0 else width, n)
        walls.append(p)
        wn.append(np.tile(nrm, (n, 1)))
    return np.vstack([floor] + walls), np.vstack([fn] + wn)


# ------------------------------------------------------------- height prior

def test_the_height_prior_rescales_a_room_to_the_right_size():
    """A room reconstructed at the wrong scale, put right by the camera height."""
    points, normals = _room_points()
    cams = np.column_stack([np.linspace(1, 3, 30), np.full(30, 1.45), np.full(30, 1.5)])
    ups = np.tile([0.0, 1.0, 0.0], (30, 1))
    # The reconstruction came out 1.9 times too big, as bedroom_2 did in loop 1.
    wrong = 1.9
    new, measured, frac = height_prior_scale(points * wrong, normals, cams * wrong, ups,
                                             current_scale=0.20 * wrong, target_height_m=1.40)
    assert measured == pytest.approx(1.45 * wrong, abs=0.05)
    assert new == pytest.approx(0.20 * 1.40 / 1.45, rel=0.05)
    assert frac > 0.5


def test_the_height_prior_declines_when_there_is_no_floor():
    points, normals = _room_points()
    above = points[:, 1] > 1.0          # walls only, no floor to fit
    new, _, _ = height_prior_scale(points[above], normals[above], np.zeros((0, 3)),
                                   np.zeros((0, 3)), 0.2, 1.40)
    assert new is None


# ---------------------------------------------------------- levelled bridge

def test_a_levelled_bridge_keeps_only_the_yaw_and_the_slide():
    theta = np.deg2rad(37.0)
    R = yaw_matrix(theta)
    tilt = np.array([[1, 0, 0], [0, np.cos(0.04), -np.sin(0.04)], [0, np.sin(0.04), np.cos(0.04)]])
    Rp, tp, tilt_deg, vertical = planar(tilt @ R, np.array([1.2, 0.4, -2.0]))
    assert np.degrees(yaw_of(Rp)) == pytest.approx(37.0, abs=0.5)
    assert tilt_deg == pytest.approx(np.degrees(0.04), abs=0.5)
    assert vertical == pytest.approx(0.4)
    assert tp[1] == 0.0 and tp[0] == 1.2 and tp[2] == -2.0


# ------------------------------------------------------------- scale solve

def test_the_solve_follows_the_prior_and_overrules_the_depth_model():
    s = solve([0, 1], {0: 0.20, 1: 0.21}, {0: 0.10, 1: 0.40}, [(0, 1, 0.0)])
    assert s.scales[0] == pytest.approx(0.20, rel=0.05)
    assert s.scales[1] == pytest.approx(0.21, rel=0.05)
    assert s.residuals["depth_pro"] > 0.5      # the depth model is left disagreeing
    assert s.residuals["height_prior"] < 0.05


def test_the_solve_falls_back_to_the_depth_model_without_a_prior():
    s = solve([0], {0: None}, {0: 0.33}, [])
    assert s.scales[0] == pytest.approx(0.33, rel=1e-6)


def test_a_bridge_pulls_two_chunks_towards_each_other():
    apart = solve([0, 1], {0: 0.20, 1: 0.30}, {}, [])
    together = solve([0, 1], {0: 0.20, 1: 0.30}, {}, [(0, 1, 0.0)])
    assert abs(np.log(together.scales[0] / together.scales[1])) < \
           abs(np.log(apart.scales[0] / apart.scales[1]))


# --------------------------------------------------------- single-room fit

def _face(axis, pos, a, b, top=2.4, n=800):
    return WallFace(axis=axis, pos=pos, segments=[(a, b)], n_points=n, resid_std=0.03,
                    sign=1.0, y_top=top, y_bottom=0.1)


def _path(x0=0.6, x1=3.4, z0=0.6, z1=2.4, n=40):
    t = np.linspace(0, 1, n)
    return np.column_stack([x0 + (x1 - x0) * np.abs(np.sin(3 * t)), z0 + (z1 - z0) * t])


def test_the_room_reaches_the_outermost_supported_faces():
    faces = [_face(0, 0.0, 0.0, 3.0), _face(0, 4.0, 0.0, 3.0),
             _face(1, 0.0, 0.0, 4.0), _face(1, 3.0, 0.0, 4.0),
             _face(0, 2.0, 0.5, 2.5, top=0.9)]      # a counter, too short to be a wall
    fit = fit_single_room(faces, _path(), CFG)
    assert fit.shape == "rectangle"
    assert fit.n_supported == 4
    assert fit.area_m2 == pytest.approx(12.0, abs=0.1)


def test_a_side_with_no_face_is_closed_by_assumption_and_flagged():
    faces = [_face(0, 0.0, 0.0, 3.0), _face(1, 0.0, 0.0, 4.0), _face(1, 3.0, 0.0, 4.0)]
    fit = fit_single_room(faces, _path(), CFG, margin_m=0.35)
    assert fit.n_supported == 3
    assert any("no supported wall face" in w for w in fit.warnings)
    assert any("not measured" in a for a in fit.assumptions)


def test_single_room_fitting_never_returns_nothing():
    """The whole point: loop 1 produced no plan at all on two of six clips."""
    fit = fit_single_room([], _path(), CFG)
    assert fit.n_supported == 0
    assert fit.area_m2 > 0
    assert len(fit.polygon_frame) == 4


def test_furniture_height_faces_cannot_set_a_wall():
    low = [_face(0, -1.0, 0.0, 3.0, top=0.8), _face(0, 5.0, 0.0, 3.0, top=0.8)]
    fit = fit_single_room(low, _path(), CFG)
    assert fit.n_supported == 0        # nothing tall enough counted


def test_the_fit_converts_to_what_the_plan_backend_expects():
    faces = [_face(0, 0.0, 0.0, 3.0), _face(0, 4.0, 0.0, 3.0),
             _face(1, 0.0, 0.0, 4.0), _face(1, 3.0, 0.0, 4.0)]
    fit = fit_single_room(faces, _path(), CFG)
    frame = ManhattanFrame(yaw=0.0, origin=np.zeros(2))
    rooms = as_room_result(fit, frame, cell_m=0.05)
    assert len(rooms.rooms) == 1
    room = rooms.rooms[0]
    assert room.mask.any() and room.mask.shape == rooms.grid.shape
    assert room.area_m2 == pytest.approx(12.0, abs=0.1)
    # The mask has to agree with the polygon, or ceiling measurement reads the wrong points.
    assert room.mask.mean() == pytest.approx(12.0 / (rooms.grid.shape[0] * rooms.grid.shape[1] *
                                                     0.05 ** 2), rel=0.15)


# ------------------------------------------- regressions from the first run

def test_fusing_skips_chunks_that_were_never_placed():
    """Every chunk is fitted, only the bridged group is placed.

    The first after-run died on this with KeyError(0), whose message is the bare
    string '0', so the failure surfaced as `error: 0`.
    """
    from cozmo.pipeline.video.dense import DenseBuild, Keyframe
    from cozmo.pipeline.video.sfm import SfmChunk

    chunks = []
    for i in range(3):
        c = SfmChunk(index=i, names=["f.jpg"], times_s=np.zeros(1),
                     cam_from_world=np.eye(4)[None, ...], obs_uv=np.zeros((0, 2)),
                     obs_z=np.zeros(0), obs_off=np.array([0, 0]), xyz=np.zeros((0, 3)),
                     focal_px=500.0, cam_params=np.array([500.0, 4.0, 4.0, 0.0]), cam_wh=(9, 9),
                     mean_reproj_err_px=0.5)
        c.scale_m_per_unit = 0.2
        chunks.append(c)
    ax = (np.arange(9) - 4) / 500.0
    rx, ry = np.meshgrid(ax, ax)
    build = DenseBuild(
        keyframes=[Keyframe(chunk=i, i=0, zmap=np.full((9, 9), 3.0, np.float16)) for i in range(3)],
        rays={i: (rx, ry) for i in range(3)}, chunks=chunks, group=[1],
        scale_at_fit={i: 0.2 for i in range(3)})
    cloud = build.fuse({1: (np.eye(3), np.zeros(3))}, voxel_m=0.05)
    assert len(cloud.points) > 0
    assert len(cloud.camera_path) == 1      # only the placed chunk contributes


def test_a_planar_fit_pins_the_turn_even_for_cameras_walking_in_a_line():
    """A 3D similarity on four cameras in a line leaves the roll free.

    That is how two chunks standing on the same floor came out 164 degrees apart
    about which way was down. Solving in the floor plane removes the freedom.
    """
    from cozmo.pipeline.video.bridge import umeyama_2d

    theta = 0.9
    Rot = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])
    line = np.column_stack([np.linspace(0, 1.5, 4), np.zeros(4)])
    target = (Rot @ line.T).T + np.array([1.0, 2.0])
    scale, yaw, t, rms = umeyama_2d(line, target)
    assert yaw == pytest.approx(theta, abs=1e-9)
    assert scale == pytest.approx(1.0, abs=1e-9)
    assert rms == pytest.approx(0.0, abs=1e-9)


def test_the_planar_fit_recovers_scale_and_shift_together():
    from cozmo.pipeline.video.bridge import umeyama_2d

    rng = np.random.default_rng(3)
    X = rng.normal(size=(8, 2))
    theta = -0.4
    Rot = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])
    Y = (2.5 * (Rot @ X.T)).T + np.array([-1.0, 4.0])
    scale, yaw, t, rms = umeyama_2d(X, Y)
    assert (scale, yaw) == (pytest.approx(2.5), pytest.approx(theta))
    assert t == pytest.approx(np.array([-1.0, 4.0]))
    assert rms < 1e-9


def test_mapanything_is_stood_up_before_it_is_compared():
    """MapAnything does not know which way is down, so its frame is aligned first."""
    from cozmo.pipeline.video.bridge import gravity_align

    tilt = np.deg2rad(20.0)
    Rx = np.array([[1, 0, 0], [0, np.cos(tilt), -np.sin(tilt)], [0, np.sin(tilt), np.cos(tilt)]])
    poses = np.tile(np.eye(4), (5, 1, 1))
    for p in poses:
        p[:3, :3] = Rx @ np.diag([1.0, -1.0, -1.0])   # camera y points down
    R = gravity_align(poses)
    up_world = -poses[0, :3, 1]
    assert (R @ up_world)[1] == pytest.approx(1.0, abs=1e-6)
