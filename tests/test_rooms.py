"""Room segmentation: grid occupancy, watershed split at doorways, polygons."""

from __future__ import annotations

import numpy as np
import pytest
from shapely.geometry import Polygon as SPoly

from cozmo.io.manifest import load_config
from cozmo.io.stray import StrayScan
from cozmo.lidar.cloud import build_cloud
from cozmo.lidar.levels import detect_levels
from cozmo.lidar.rooms import Grid, segment_rooms
from cozmo.lidar.walls import ManhattanFrame, extract_faces, wall_points
from tests.synth_stray import one_room, two_rooms, write_synthetic_scan

CFG = load_config("config/gates.yaml")["pipeline"]["lidar"]


def _pipeline_upto_rooms(root):
    scan = StrayScan(root, "lidar")
    cloud = build_cloud(scan, stride=1)
    levels = detect_levels(cloud, CFG)
    sel = wall_points(cloud, levels, CFG)
    frame = ManhattanFrame.fit(cloud.normals[sel], cloud.points[sel][:, [0, 2]])
    faces = extract_faces(frame.to_frame(cloud.points[sel][:, [0, 2]]),
                          frame.rotate_normals(cloud.normals[sel]),
                          cloud.points[sel][:, 1] - levels.floor.height_at(cloud.points[sel][:, [0, 2]]),
                          CFG)
    return segment_rooms(cloud, levels, frame, faces, CFG)


@pytest.fixture(scope="module")
def two_room_result(tmp_path_factory):
    root = write_synthetic_scan(tmp_path_factory.mktemp("r") / "two", two_rooms(), n_per_room=20)
    return _pipeline_upto_rooms(root)


@pytest.fixture(scope="module")
def one_room_result(tmp_path_factory):
    root = write_synthetic_scan(tmp_path_factory.mktemp("r") / "one", one_room(), n_per_room=20)
    return _pipeline_upto_rooms(root)


def test_grid_maps_world_to_cells_and_back():
    g = Grid(origin=np.array([-1.0, 2.0]), cell=0.02, shape=(100, 200))
    ij = g.to_cell(np.array([[-1.0, 2.0], [-0.99, 2.03]]))
    assert ij[0].tolist() == [0, 0] and ij[1].tolist() == [0, 1]
    assert np.allclose(g.to_world(np.array([[0, 0]])), [[-0.99, 2.01]])


def test_single_room_stays_one_room_with_the_right_area(one_room_result):
    rooms = one_room_result.rooms
    assert len(rooms) == 1
    assert rooms[0].area_m2 == pytest.approx(3.6 * 4.8, rel=0.08)
    assert rooms[0].kind == "room"


def test_doorway_splits_two_rooms_and_areas_are_right(two_room_result):
    rooms = sorted(two_room_result.rooms, key=lambda r: -r.area_m2)
    assert len(rooms) == 2, [r.area_m2 for r in two_room_result.rooms]
    assert rooms[0].area_m2 == pytest.approx(20.0, rel=0.08)
    assert rooms[1].area_m2 == pytest.approx(15.0, rel=0.08)
    assert not SPoly(rooms[0].polygon_world).intersects(SPoly(rooms[1].polygon_world).buffer(-0.05))


def test_room_polygons_are_rectilinear_ccw_and_snapped(two_room_result):
    for r in two_room_result.rooms:
        poly = np.array(r.polygon_frame)
        assert len(poly) >= 4
        edges = np.diff(np.vstack([poly, poly[:1]]), axis=0)
        # every edge is axis aligned
        assert np.all(np.minimum(np.abs(edges[:, 0]), np.abs(edges[:, 1])) < 1e-9)
        assert SPoly(poly).is_valid
        assert SPoly(poly).exterior.is_ccw


def test_rooms_are_deterministic(two_room_result, tmp_path_factory):
    root = write_synthetic_scan(tmp_path_factory.mktemp("r2") / "two", two_rooms(), n_per_room=20)
    again = _pipeline_upto_rooms(root)
    a = sorted((r.id, round(r.area_m2, 6)) for r in two_room_result.rooms)
    b = sorted((r.id, round(r.area_m2, 6)) for r in again.rooms)
    assert a == b


def test_tiny_components_do_not_become_rooms(two_room_result):
    assert all(r.area_m2 >= CFG["room"]["min_area_m2"] for r in two_room_result.rooms)
