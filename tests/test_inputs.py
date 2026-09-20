"""Input convention: one subfolder per room, tier decides what must be inside."""

from __future__ import annotations

import json

import pytest

from cozmo.io.inputs import InputError, validate_input


def _photo_room(root, name, n=2):
    d = root / name
    d.mkdir(parents=True)
    for i in range(n):
        (d / f"img_{i}.JPG").write_bytes(b"x")
    return d


def test_photo_ok_returns_rooms_sorted(tmp_path):
    _photo_room(tmp_path, "living")
    _photo_room(tmp_path, "hall", 3)
    rooms = validate_input(tmp_path, "photo")
    assert [r.room_id for r in rooms] == ["hall", "living"]
    assert len(rooms[0].files) == 3


def test_photo_needs_two_images(tmp_path):
    _photo_room(tmp_path, "living", 1)
    with pytest.raises(InputError, match="living.*at least 2"):
        validate_input(tmp_path, "photo")


def test_input_must_be_directory_with_room_subfolders(tmp_path):
    f = tmp_path / "clip.mp4"
    f.write_bytes(b"v")
    with pytest.raises(InputError, match="directory"):
        validate_input(f, "video")
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(InputError, match="no room subfolders"):
        validate_input(empty, "video")


def test_video_needs_exactly_one_clip(tmp_path):
    d = tmp_path / "living"
    d.mkdir()
    (d / "a.mp4").write_bytes(b"v")
    (d / "b.mov").write_bytes(b"v")
    with pytest.raises(InputError, match="exactly one"):
        validate_input(tmp_path, "video")
    (d / "b.mov").unlink()
    assert validate_input(tmp_path, "video")[0].files[0].name == "a.mp4"


def _lidar_room(root, name):
    d = root / name
    (d / "rgb").mkdir(parents=True)
    (d / "depth").mkdir()
    (d / "rgb" / "0.png").write_bytes(b"x")
    (d / "depth" / "0.png").write_bytes(b"x")
    (d / "poses.json").write_text(json.dumps([{"t": 0, "pose": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0]}]))
    (d / "intrinsics.json").write_text(json.dumps({"fx": 500.0, "fy": 500.0, "cx": 320.0, "cy": 240.0}))
    return d


def test_lidar_ok_and_missing_intrinsics_fails(tmp_path):
    d = _lidar_room(tmp_path, "living")
    assert validate_input(tmp_path, "lidar")[0].room_id == "living"
    (d / "intrinsics.json").write_text(json.dumps({"fx": 500.0}))
    with pytest.raises(InputError, match="intrinsics.json"):
        validate_input(tmp_path, "lidar")


def test_lidar_empty_poses_fails(tmp_path):
    d = _lidar_room(tmp_path, "living")
    (d / "poses.json").write_text("[]")
    with pytest.raises(InputError, match="poses.json"):
        validate_input(tmp_path, "lidar")
