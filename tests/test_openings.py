"""Openings: gaps in wall occupancy that free space crosses, and the adjacency they imply."""

from __future__ import annotations

import numpy as np
import pytest

from cozmo.io.manifest import load_config
from cozmo.io.stray import StrayScan
from cozmo.lidar.cloud import build_cloud
from cozmo.lidar.levels import detect_levels
from cozmo.lidar.openings import adjacency_from_openings, find_openings
from cozmo.lidar.rooms import segment_rooms
from cozmo.lidar.walls import ManhattanFrame, extract_faces, wall_points
from tests.synth_stray import two_rooms, write_synthetic_scan

CFG = load_config("config/gates.yaml")["pipeline"]["lidar"]


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = write_synthetic_scan(tmp_path_factory.mktemp("o") / "two", two_rooms(), n_per_room=24)
    cloud = build_cloud(StrayScan(root, "lidar"), stride=1)
    levels = detect_levels(cloud, CFG)
    sel = wall_points(cloud, levels, CFG)
    frame = ManhattanFrame.fit(cloud.normals[sel], cloud.points[sel][:, [0, 2]])
    h = cloud.points[sel][:, 1] - levels.floor.height_at(cloud.points[sel][:, [0, 2]])
    faces = extract_faces(frame.to_frame(cloud.points[sel][:, [0, 2]]), frame.rotate_normals(cloud.normals[sel]), h, CFG)
    rooms = segment_rooms(cloud, levels, frame, faces, CFG)
    return cloud, levels, frame, faces, rooms


def test_finds_the_door_between_the_two_rooms(built):
    cloud, levels, frame, faces, rooms = built
    ops = find_openings(cloud, levels, frame, faces, rooms, CFG)
    assert ops, "no opening found on a scene with one 0.9 m door"
    door = max(ops, key=lambda o: o.width_m if 0.6 < o.width_m < 1.4 else 0.0)
    assert door.width_m == pytest.approx(0.9, abs=0.2)
    assert door.type in ("door", "pass_through")
    assert len(door.room_ids) == 2
    assert door.height_m is None or 1.7 < door.height_m < 2.3


def test_openings_lie_on_a_detected_wall_face(built):
    cloud, levels, frame, faces, rooms = built
    ops = find_openings(cloud, levels, frame, faces, rooms, CFG)
    ids = {id(f) for f in faces}
    for o in ops:
        assert id(o.face) in ids
        a, b = o.face.extent()
        assert a - 0.1 <= o.centre_along <= b + 0.1


def test_adjacency_is_undirected_and_deduplicated(built):
    cloud, levels, frame, faces, rooms = built
    ops = find_openings(cloud, levels, frame, faces, rooms, CFG)
    adj = adjacency_from_openings(ops)
    assert len(adj) == len({tuple(sorted((a, b))) for a, b, _ in adj})
    for a, b, oid in adj:
        assert a != b and oid


def test_no_openings_reported_where_the_wall_is_solid():
    """A wall with no gap must not produce an opening, however the free space looks."""
    from cozmo.lidar.openings import _gaps

    occupied = np.ones(40, dtype=bool)
    assert _gaps(occupied, 0.05, 0.0, 0.6, 2.4) == []
    occupied[10:28] = False  # 0.9 m gap
    gaps = _gaps(occupied, 0.05, 0.0, 0.6, 2.4)
    assert len(gaps) == 1 and gaps[0][1] - gaps[0][0] == pytest.approx(0.9, abs=0.06)
