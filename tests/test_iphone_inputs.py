"""Input robustness for an iPhone capture: HEIC, .mov, mixed case, any scan folder name."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from cozmo.damage.frames import frames_from_images
from cozmo.io.inputs import InputError, validate_input


def _heic(path, size=(64, 48)):
    """A real HEIC file, written through pillow-heif."""
    import pillow_heif

    arr = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    arr[:, : size[0] // 2] = 200
    heif = pillow_heif.from_pillow(Image.fromarray(arr))
    heif.save(str(path), quality=60)
    return path


def test_heic_photos_are_accepted_and_readable(tmp_path):
    room = tmp_path / "bedroom"
    room.mkdir()
    _heic(room / "IMG_0001.HEIC")
    _heic(room / "IMG_0002.heic")
    spec = validate_input(room, "photo")
    assert [p.name for p in spec.files] == ["IMG_0001.HEIC", "IMG_0002.heic"]
    frames = list(frames_from_images(spec.files))
    assert len(frames) == 2
    assert all(f.image.ndim == 3 and f.image.shape[2] == 3 for f in frames)


def test_mixed_case_extensions_all_count(tmp_path):
    room = tmp_path / "kitchen"
    room.mkdir()
    for name in ("a.JPG", "b.jpeg", "c.PNG", "d.HEIC"):
        (room / name).write_bytes(b"x")
    spec = validate_input(room, "photo")
    assert len(spec.files) == 4


def test_mov_and_hevc_clips_are_accepted(tmp_path):
    for i, name in enumerate(("clip.MOV", "clip.mov", "clip.hevc", "clip.m4v")):
        room = tmp_path / f"room_{i}"
        room.mkdir()
        (room / name).write_bytes(b"v")
        spec = validate_input(room, "video")
        assert [p.name for p in spec.files] == [name]


def test_sidecar_files_do_not_break_a_room(tmp_path):
    """iOS leaves .AAE files and Finder leaves .DS_Store beside the photos."""
    room = tmp_path / "hall"
    room.mkdir()
    (room / "IMG_0001.HEIC").write_bytes(b"x")
    (room / "IMG_0002.HEIC").write_bytes(b"x")
    (room / "IMG_0001.AAE").write_bytes(b"sidecar")
    (room / ".DS_Store").write_bytes(b"junk")
    spec = validate_input(room, "photo")
    assert [p.name for p in spec.files] == ["IMG_0001.HEIC", "IMG_0002.HEIC"]


def test_a_stray_scan_folder_is_recognised_whatever_its_name(tmp_path):
    for name in ("c00a170fe1", "My Scan 2026-09-21", "scan"):
        root = tmp_path / name
        (root / "depth").mkdir(parents=True)
        (root / "confidence").mkdir()
        (root / "depth" / "000000.png").write_bytes(b"d")
        (root / "confidence" / "000000.png").write_bytes(b"c")
        (root / "rgb.mp4").write_bytes(b"v")
        (root / "odometry.csv").write_text(
            "timestamp, frame, x, y, z, qx, qy, qz, qw, fx, fy, cx, cy\n"
            "0.0, 000000, 0, 0, 0, 0, 0, 0, 1, 100, 100, 50, 50\n")
        spec = validate_input(root, "lidar")
        assert spec.n_frames == 1
        assert [p.name for p in validate_input(root, "video").files] == ["rgb.mp4"]


def test_error_messages_say_what_was_found_and_what_is_accepted(tmp_path):
    lonely = tmp_path / "one_photo"
    lonely.mkdir()
    (lonely / "only.HEIC").write_bytes(b"x")
    with pytest.raises(InputError) as e:
        validate_input(lonely, "photo")
    msg = str(e.value)
    assert "at least 2 images" in msg and "only.HEIC" in msg and ".heic" in msg

    empty = tmp_path / "nothing"
    empty.mkdir()
    with pytest.raises(InputError, match="empty"):
        validate_input(empty, "photo")

    two_clips = tmp_path / "two"
    two_clips.mkdir()
    (two_clips / "a.mov").write_bytes(b"v")
    (two_clips / "b.MP4").write_bytes(b"v")
    with pytest.raises(InputError) as e:
        validate_input(two_clips, "video")
    assert "2 video files" in str(e.value) and "a.mov" in str(e.value) and "b.MP4" in str(e.value)

    not_a_scan = tmp_path / "docs"
    not_a_scan.mkdir()
    (not_a_scan / "notes.txt").write_text("hello")
    with pytest.raises(InputError) as e:
        validate_input(not_a_scan, "lidar")
    assert "Stray Scanner export" in str(e.value) and "notes.txt" in str(e.value)
