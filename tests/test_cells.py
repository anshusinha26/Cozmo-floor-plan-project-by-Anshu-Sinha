"""Wall-driven cell complex segmentation."""

from __future__ import annotations

import numpy as np
import pytest

from cozmo.io.manifest import load_config
from cozmo.io.stray import StrayScan
from cozmo.lidar.cells import build_support, edge_verdict, segment_rooms_cells
from cozmo.lidar.cloud import build_cloud
from cozmo.lidar.ghosts import reject_ghost_faces
from cozmo.lidar.levels import detect_levels
from cozmo.lidar.walls import ManhattanFrame, extract_faces, wall_points
from tests.synth_stray import Door, Scene, one_room, two_rooms, write_synthetic_scan

CFG = load_config("config/gates.yaml")["pipeline"]["lidar"]


def _build(root):
    cloud = build_cloud(StrayScan(root, "lidar"), stride=1)
    levels = detect_levels(cloud, CFG)
    sel = wall_points(cloud, levels, CFG)
    frame = ManhattanFrame.fit(cloud.normals[sel], cloud.points[sel][:, [0, 2]])
    h = cloud.points[sel][:, 1] - levels.floor.height_at(cloud.points[sel][:, [0, 2]])
    faces = extract_faces(frame.to_frame(cloud.points[sel][:, [0, 2]]),
                          frame.rotate_normals(cloud.normals[sel]), h, CFG)
    faces, _, _ = reject_ghost_faces(cloud, levels, frame, faces, CFG)
    return cloud, levels, frame, faces


@pytest.fixture(scope="module")
def two(tmp_path_factory):
    return _build(write_synthetic_scan(tmp_path_factory.mktemp("c") / "two", two_rooms(), n_per_room=24))


@pytest.fixture(scope="module")
def one(tmp_path_factory):
    return _build(write_synthetic_scan(tmp_path_factory.mktemp("c") / "one", one_room(), n_per_room=24))


def test_a_door_does_not_merge_two_rooms(two):
    """Scene: 4x5 and 3x5 rooms sharing a wall with one 0.9 m door."""
    res = segment_rooms_cells(*two, CFG)
    rooms = sorted(res.rooms, key=lambda r: -r.area_m2)
    assert len(rooms) == 2, [(r.id, round(r.area_m2, 2)) for r in res.rooms]
    assert rooms[0].area_m2 == pytest.approx(20.0, rel=0.10)
    assert rooms[1].area_m2 == pytest.approx(15.0, rel=0.10)


def test_a_single_room_stays_one_room(one):
    res = segment_rooms_cells(*one, CFG)
    assert len(res.rooms) == 1
    assert res.rooms[0].area_m2 == pytest.approx(3.6 * 4.8, rel=0.10)


def test_a_wide_opening_merges_into_one_space(tmp_path_factory):
    """A 2.4 m gap is wider than a doorway, so the two halves are one room."""
    scene = Scene(rooms=[(0.0, 0.0, 4.0, 5.0), (4.0, 0.0, 7.0, 5.0)], floor_y=-1.4, height=2.5,
                  doors=[Door(axis=0, pos=4.0, a0=1.2, a1=3.6, height=2.4)])
    built = _build(write_synthetic_scan(tmp_path_factory.mktemp("c") / "wide", scene, n_per_room=24))
    res = segment_rooms_cells(*built, CFG)
    assert len(res.rooms) == 1, [(r.id, round(r.area_m2, 2)) for r in res.rooms]
    assert res.rooms[0].area_m2 == pytest.approx(35.0, rel=0.12)


def test_edge_verdict_cuts_a_wall_and_merges_open_space(two):
    cloud, levels, frame, faces = two
    support = build_support(cloud, levels, frame, CFG)
    shared = [f for f in faces if f.axis == 0]
    wall = min(shared, key=lambda f: f.pos)
    a0, a1 = wall.extent()
    v = edge_verdict(support, wall.axis, wall.pos, a0, a1, CFG)
    assert v.cut and v.supported_share > 0.8
    empty = edge_verdict(support, wall.axis, wall.pos + 1.5, a0, a1, CFG)
    assert not empty.cut


def test_polygons_are_rectilinear_and_ccw(two):
    from shapely.geometry import Polygon as SPoly

    for r in segment_rooms_cells(*two, CFG).rooms:
        poly = np.array(r.polygon_frame)
        edges = np.diff(np.vstack([poly, poly[:1]]), axis=0)
        assert np.all(np.minimum(np.abs(edges[:, 0]), np.abs(edges[:, 1])) < 1e-9)
        assert SPoly(poly).is_valid and SPoly(poly).exterior.is_ccw


def test_segmentation_is_deterministic(two):
    a = [(r.id, round(r.area_m2, 9)) for r in segment_rooms_cells(*two, CFG).rooms]
    b = [(r.id, round(r.area_m2, 9)) for r in segment_rooms_cells(*two, CFG).rooms]
    assert a == b


def test_fully_enclosed_rooms_are_not_flagged_partially_observed(two):
    res = segment_rooms_cells(*two, CFG)
    assert all(not r.partially_observed for r in res.rooms), \
        [(r.id, round(r.perimeter_support, 2)) for r in res.rooms]


def test_a_room_with_an_unobserved_side_is_flagged(tmp_path_factory):
    """One wall missing entirely: the room must be reported as partially observed."""
    scene = Scene(rooms=[(0.0, 0.0, 4.0, 5.0)], floor_y=-1.4, height=2.5, ceiling=False)
    scene.rects = [r for r in scene.rects if not (r.axis == 0 and abs(r.pos - 4.0) < 1e-9)]
    built = _build(write_synthetic_scan(tmp_path_factory.mktemp("c") / "open", scene, n_per_room=24))
    res = segment_rooms_cells(*built, CFG)
    assert any(r.partially_observed for r in res.rooms), \
        [(r.id, round(r.perimeter_support, 2)) for r in res.rooms]
    assert any("partially observed" in w for w in res.warnings)
