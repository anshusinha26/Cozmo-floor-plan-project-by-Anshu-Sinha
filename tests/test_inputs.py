"""Input convention: photo is one subfolder per room, video and lidar are one scan folder."""

from __future__ import annotations

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
    spec = validate_input(tmp_path, "photo")
    assert [r.room_id for r in spec.rooms] == ["hall", "living"]
    assert len(spec.rooms[0].files) == 3
    assert len(spec.files) == 5


def test_photo_needs_two_images(tmp_path):
    _photo_room(tmp_path, "living", 1)
    with pytest.raises(InputError, match="living.*at least 2"):
        validate_input(tmp_path, "photo")


def test_input_must_be_a_directory(tmp_path):
    f = tmp_path / "clip.mp4"
    f.write_bytes(b"v")
    with pytest.raises(InputError, match="must be a directory"):
        validate_input(f, "video")
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(InputError, match="no room subfolders"):
        validate_input(empty, "photo")


def test_video_tier_takes_one_clip_per_room_folder(tmp_path):
    d = tmp_path / "bedroom"
    d.mkdir()
    with pytest.raises(InputError, match="one clip or room subfolders"):
        validate_input(d, "video")
    (d / "loop.mp4").write_bytes(b"v")
    spec = validate_input(d, "video")
    assert [p.name for p in spec.files] == ["loop.mp4"]
    assert [r.room_id for r in spec.rooms] == ["bedroom"]
    (d / "second.mov").write_bytes(b"v")
    with pytest.raises(InputError, match="exactly one clip"):
        validate_input(d, "video")


def test_video_tier_on_a_scan_folder_sees_only_rgb(tmp_path):
    d = tmp_path / "scan"
    (d / "depth").mkdir(parents=True)
    (d / "confidence").mkdir()
    (d / "odometry.csv").write_text("timestamp, frame\n")
    with pytest.raises(InputError, match="rgb.mp4"):
        validate_input(d, "video")
    (d / "rgb.mp4").write_bytes(b"v")
    spec = validate_input(d, "video")
    assert [p.name for p in spec.files] == ["rgb.mp4"] and spec.rooms is None


def test_photo_tier_treats_a_folder_of_images_as_one_room(tmp_path):
    d = tmp_path / "kitchen"
    d.mkdir()
    for i in range(3):
        (d / f"k_{i}.jpeg").write_bytes(b"x")
    (d / "kitchen_loop.mp4").write_bytes(b"v")
    spec = validate_input(d, "photo")
    assert [r.room_id for r in spec.rooms] == ["kitchen"]
    # Tier isolation: the clip in the same folder is not a photo-tier file.
    assert all(p.suffix.lower() != ".mp4" for p in spec.files)


def test_missing_input_reported(tmp_path):
    with pytest.raises(InputError, match="not found"):
        validate_input(tmp_path / "nope", "lidar")
