"""Manhattan alignment and wall face extraction."""

from __future__ import annotations

import numpy as np
import pytest

from cozmo.io.manifest import load_config
from cozmo.io.stray import StrayScan
from cozmo.lidar.cloud import Cloud, build_cloud
from cozmo.lidar.levels import detect_levels
from cozmo.lidar.walls import ManhattanFrame, dominant_yaw, extract_faces, wall_points
from tests.synth_stray import two_rooms, write_synthetic_scan

CFG = load_config("config/gates.yaml")["pipeline"]["lidar"]


@pytest.fixture(scope="module")
def two_room_cloud(tmp_path_factory):
    root = write_synthetic_scan(tmp_path_factory.mktemp("w") / "two", two_rooms(), n_per_room=20)
    return build_cloud(StrayScan(root, "lidar"), stride=1)


def _axis_aligned_normals(angles_deg, n=500):
    ang = np.radians(np.repeat(angles_deg, n))
    return np.stack([np.cos(ang), np.zeros_like(ang), np.sin(ang)], axis=1)


def test_dominant_yaw_is_modulo_90_degrees():
    # Four wall directions of one rectangular room rotated by 12 degrees.
    n = _axis_aligned_normals([12.0, 102.0, 192.0, 282.0])
    assert np.degrees(dominant_yaw(n, np.ones(len(n)))) == pytest.approx(12.0, abs=0.5)


def test_dominant_yaw_ignores_a_minority_of_diagonal_walls():
    n = np.concatenate([_axis_aligned_normals([5.0, 95.0], 800), _axis_aligned_normals([50.0], 100)])
    assert np.degrees(dominant_yaw(n, np.ones(len(n)))) == pytest.approx(5.0, abs=1.0)


def test_manhattan_frame_round_trips_points():
    f = ManhattanFrame(yaw=np.radians(17.0), origin=np.array([1.0, -2.0]))
    xz = np.array([[0.0, 0.0], [3.0, 4.0], [-1.0, 2.0]])
    assert np.allclose(f.to_world(f.to_frame(xz)), xz, atol=1e-12)


def test_wall_points_exclude_floor_and_near_ceiling(two_room_cloud):
    lv = detect_levels(two_room_cloud, CFG)
    sel = wall_points(two_room_cloud, lv, CFG)
    y = two_room_cloud.points[sel][:, 1]
    assert (y > lv.floor.y + 0.29).all()
    assert (np.abs(two_room_cloud.normals[sel][:, 1]) < CFG["horizontal_normal_cos"]).all()
    assert sel.sum() > 2000


def _faces_of(cloud):
    lv = detect_levels(cloud, CFG)
    sel = wall_points(cloud, lv, CFG)
    frame = ManhattanFrame.fit(cloud.normals[sel], cloud.points[sel][:, [0, 2]])
    return extract_faces(frame.to_frame(cloud.points[sel][:, [0, 2]]),
                         frame.rotate_normals(cloud.normals[sel]), CFG)


def test_extract_faces_finds_both_outer_walls_and_the_shared_wall(two_room_cloud):
    """Scene: room A x 0..4, room B x 4..7, both z 0..5, shared wall at x = 4.

    The Manhattan yaw is only defined modulo 90 degrees, so the two axes may
    come out swapped. The test checks the geometry, not which axis is which.
    """
    faces = _faces_of(two_room_cloud)
    by_axis = {a: sorted(f.pos for f in faces if f.axis == a) for a in (0, 1)}
    spans = {a: (max(p) - min(p)) if len(p) > 1 else 0.0 for a, p in by_axis.items()}
    long_axis = max(spans, key=spans.get)
    short_axis = 1 - long_axis
    assert spans[long_axis] == pytest.approx(7.0, abs=0.08)
    assert spans[short_axis] == pytest.approx(5.0, abs=0.08)
    long_pos = by_axis[long_axis]
    assert len(long_pos) >= 3
    gaps = sorted(round(b - a, 2) for a, b in zip(long_pos, long_pos[1:]))
    assert gaps[-2:] == pytest.approx([3.0, 4.0], abs=0.08)


def test_face_segments_cover_the_wall_and_stop_at_its_ends(two_room_cloud):
    faces = _faces_of(two_room_cloud)
    by_axis = {a: [f for f in faces if f.axis == a] for a in (0, 1)}
    spans = {a: (max(f.pos for f in fs) - min(f.pos for f in fs)) if len(fs) > 1 else 0.0 for a, fs in by_axis.items()}
    long_axis = max(spans, key=spans.get)
    # Faces perpendicular to the long axis are the 5 m end walls.
    end_wall = min(by_axis[long_axis], key=lambda f: f.pos)
    assert end_wall.length() == pytest.approx(5.0, abs=0.08)
    assert end_wall.n_points > 200 and end_wall.resid_std < 0.03
    side_wall = min(by_axis[1 - long_axis], key=lambda f: f.pos)
    assert side_wall.length() == pytest.approx(7.0, abs=0.08)


def test_extract_faces_is_deterministic(two_room_cloud):
    lv = detect_levels(two_room_cloud, CFG)
    sel = wall_points(two_room_cloud, lv, CFG)
    frame = ManhattanFrame.fit(two_room_cloud.normals[sel], two_room_cloud.points[sel][:, [0, 2]])
    xz = frame.to_frame(two_room_cloud.points[sel][:, [0, 2]])
    nr = frame.rotate_normals(two_room_cloud.normals[sel])
    a = [(f.axis, round(f.pos, 9), f.segments) for f in extract_faces(xz, nr, CFG)]
    b = [(f.axis, round(f.pos, 9), f.segments) for f in extract_faces(xz, nr, CFG)]
    assert a == b
