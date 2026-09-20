"""Ghost-face rejection keeps walls somebody stood beside and drops the rest."""

from __future__ import annotations

import numpy as np
import pytest

from cozmo.io.manifest import load_config
from cozmo.io.stray import StrayScan
from cozmo.lidar.cloud import build_cloud
from cozmo.lidar.ghosts import face_support, observed_mask, reject_ghost_faces
from cozmo.lidar.levels import detect_levels
from cozmo.lidar.walls import ManhattanFrame, WallFace, extract_faces, wall_points
from tests.synth_stray import two_rooms, write_synthetic_scan

CFG = load_config("config/gates.yaml")["pipeline"]["lidar"]


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = write_synthetic_scan(tmp_path_factory.mktemp("g") / "two", two_rooms(), n_per_room=20)
    cloud = build_cloud(StrayScan(root, "lidar"), stride=1)
    levels = detect_levels(cloud, CFG)
    sel = wall_points(cloud, levels, CFG)
    frame = ManhattanFrame.fit(cloud.normals[sel], cloud.points[sel][:, [0, 2]])
    h = cloud.points[sel][:, 1] - levels.floor.height_at(cloud.points[sel][:, [0, 2]])
    faces = extract_faces(frame.to_frame(cloud.points[sel][:, [0, 2]]),
                          frame.rotate_normals(cloud.normals[sel]), h, CFG)
    return cloud, levels, frame, faces


def test_real_walls_are_all_kept(built):
    cloud, levels, frame, faces = built
    kept, ghosts, report = reject_ghost_faces(cloud, levels, frame, faces, CFG)
    assert report["n_rejected"] == 0, [(g.axis, g.pos) for g in ghosts]
    assert len(kept) == len(faces)


def test_a_face_far_outside_the_observed_area_is_rejected(built):
    cloud, levels, frame, faces = built
    ghost = WallFace(axis=0, pos=float(max(f.pos for f in faces if f.axis == 0) + 9.0),
                     segments=[(0.0, 3.0)], n_points=500, resid_std=0.01, y_top=2.4)
    kept, ghosts, report = reject_ghost_faces(cloud, levels, frame, faces + [ghost], CFG)
    assert [g.pos for g in ghosts] == [ghost.pos]
    assert report["n_kept"] == len(faces)


def test_support_is_a_share_not_a_boolean(built):
    cloud, levels, frame, faces = built
    mask, origin = observed_mask(cloud, levels, frame, 0.05)
    shares = [face_support(f, mask, origin, 0.05) for f in faces]
    assert all(0.0 <= s <= 1.0 for s in shares)
    assert min(shares) > 0.5


def test_rejection_can_be_switched_off(built):
    cloud, levels, frame, faces = built
    cfg = {**CFG, "ghost": {"enabled": False}}
    kept, ghosts, report = reject_ghost_faces(cloud, levels, frame, faces, cfg)
    assert len(kept) == len(faces) and not ghosts and report == {"enabled": False}
