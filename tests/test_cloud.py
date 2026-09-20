"""Point cloud stage: normals from depth, voxel downsample, camera path."""

from __future__ import annotations

import numpy as np
import pytest

from cozmo.io.stray import StrayScan
from cozmo.lidar.cloud import VoxelGrid, build_cloud, depth_normals
from tests.synth_stray import one_room, write_synthetic_scan


@pytest.fixture(scope="module")
def synth(tmp_path_factory):
    return write_synthetic_scan(tmp_path_factory.mktemp("cloud") / "one", one_room(), n_per_room=18)


def test_depth_normals_of_a_frontal_plane_point_at_the_camera():
    d = np.full((20, 30), 2.0, dtype=np.float32)
    n, valid = depth_normals(d, fx=100.0, fy=100.0, cx=15.0, cy=10.0)
    inner = valid.copy()
    assert inner.sum() > 0
    assert np.allclose(n[inner][:, 2], -1.0, atol=1e-6)


def test_depth_normals_of_a_slanted_plane_recover_the_plane_normal():
    """Exact check: z-depth of a plane, so any error is the normal estimator's own."""
    h, w, fx, fy, cx, cy = 40, 40, 60.0, 60.0, 19.5, 19.5
    n0 = np.array([0.3, -0.5, -0.81])
    n0 /= np.linalg.norm(n0)
    p0 = np.array([0.0, 0.0, 2.0])
    u, v = np.meshgrid(np.arange(w, dtype=np.float64), np.arange(h, dtype=np.float64))
    r = np.stack([(u - cx) / fx, (v - cy) / fy, np.ones_like(u)], -1)
    d = (n0 @ p0) / (r @ n0)
    n, valid = depth_normals(d.astype(np.float32), fx, fy, cx, cy)
    assert valid.sum() > 1000
    assert np.abs(n[valid] @ n0).min() > 0.9999


def test_depth_normals_rotate_into_the_world_frame():
    d = np.full((20, 20), 2.0, dtype=np.float32)
    n, valid = depth_normals(d, 100.0, 100.0, 9.5, 9.5)
    # Camera looking straight down: camera z maps to world -y, so the frontal
    # plane's normal (camera -z) becomes world +y (up).
    R = np.array([[1.0, 0, 0], [0, 0, -1.0], [0, 1.0, 0]])
    nw = n[valid] @ R.T
    assert np.allclose(nw[:, 1], 1.0, atol=1e-6)


def test_voxel_grid_averages_within_cells_and_is_order_independent():
    g = VoxelGrid(0.02)
    p = np.array([[0.001, 0.0, 0.0], [0.019, 0.0, 0.0], [0.5, 0.5, 0.5]])
    n = np.array([[0.0, 1.0, 0.0], [0.0, 1.0, 0.0], [1.0, 0.0, 0.0]])
    g.add(p, n)
    pts, nrm, cnt = g.result()
    assert len(pts) == 2
    g2 = VoxelGrid(0.02)
    g2.add(p[::-1], n[::-1])
    pts2, _, cnt2 = g2.result()
    assert np.allclose(pts, pts2) and np.array_equal(np.sort(cnt), np.sort(cnt2))
    assert cnt.sum() == 3


def test_voxel_grid_result_is_sorted_so_output_is_deterministic():
    g = VoxelGrid(0.05)
    rng = np.random.default_rng(0)
    p = rng.normal(size=(500, 3))
    n = np.tile([0.0, 1.0, 0.0], (500, 1))
    g.add(p, n)
    pts, _, _ = g.result()
    keys = np.floor(pts / 0.05).astype(np.int64)
    order = np.lexsort((keys[:, 2], keys[:, 1], keys[:, 0]))
    assert np.array_equal(order, np.arange(len(pts)))


def test_build_cloud_on_synthetic_room_recovers_extent_and_normals(synth):
    scan = StrayScan(synth, "lidar")
    cloud = build_cloud(scan, stride=1, voxel_m=0.02, min_depth=0.2, max_depth=4.5)
    # Synthetic room spans x 0..3.6, z 0..4.8, floor y = -1.48, ceiling 1.12.
    assert cloud.points[:, 0].min() == pytest.approx(0.0, abs=0.06)
    assert cloud.points[:, 0].max() == pytest.approx(3.6, abs=0.06)
    assert cloud.points[:, 2].max() == pytest.approx(4.8, abs=0.06)
    assert cloud.points[:, 1].min() == pytest.approx(-1.48, abs=0.05)
    vertical = np.abs(cloud.normals[:, 1]) > 0.9
    horizontal = np.abs(cloud.normals[:, 1]) < 0.2
    assert vertical.sum() > 1000 and horizontal.sum() > 1000
    assert len(cloud.camera_path) == scan.n_frames
    assert cloud.n_frames_used == scan.n_frames


def test_build_cloud_is_deterministic(synth):
    scan = StrayScan(synth, "lidar")
    a = build_cloud(scan, stride=3, voxel_m=0.02)
    b = build_cloud(scan, stride=3, voxel_m=0.02)
    assert np.array_equal(a.points, b.points) and np.array_equal(a.normals, b.normals)
