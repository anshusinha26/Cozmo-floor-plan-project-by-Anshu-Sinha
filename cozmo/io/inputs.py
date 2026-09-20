"""Input convention for `cozmo run`.

Input is a directory with one subfolder per room; the subfolder name is the
room id. What must be inside depends on the tier:

* photo: 2 or more images (jpg, jpeg, png, heic)
* video: exactly one clip (mp4, mov)
* lidar: rgb/, depth/, poses.json, intrinsics.json

Validation is structural only. No pixels are decoded here; that is the
pipeline's job, and this task ships no reconstruction.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".heic"}
VIDEO_EXT = {".mp4", ".mov"}
INTRINSIC_KEYS = ("fx", "fy", "cx", "cy")


class InputError(ValueError):
    """Bad capture layout. Message names the room and what is wrong."""


@dataclass
class RoomInput:
    room_id: str
    files: list[Path] = field(default_factory=list)


def _visible(paths):
    return sorted(p for p in paths if not p.name.startswith("."))


def _files_with_ext(folder: Path, exts: set[str]) -> list[Path]:
    return _visible(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in exts)


def _photo(room: Path) -> RoomInput:
    imgs = _files_with_ext(room, IMAGE_EXT)
    if len(imgs) < 2:
        raise InputError(f"room {room.name!r}: photo tier needs at least 2 images, found {len(imgs)}")
    return RoomInput(room.name, imgs)


def _video(room: Path) -> RoomInput:
    clips = _files_with_ext(room, VIDEO_EXT)
    if len(clips) != 1:
        raise InputError(f"room {room.name!r}: video tier needs exactly one clip (mp4/mov), found {len(clips)}")
    return RoomInput(room.name, clips)


def _load_json(path: Path, room: str):
    if not path.is_file():
        raise InputError(f"room {room!r}: missing {path.name}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise InputError(f"room {room!r}: {path.name} is not valid JSON ({e.msg})") from e


def _lidar(room: Path) -> RoomInput:
    files: list[Path] = []
    for sub in ("rgb", "depth"):
        d = room / sub
        if not d.is_dir():
            raise InputError(f"room {room.name!r}: lidar tier needs {sub}/ directory")
        frames = _visible(p for p in d.iterdir() if p.is_file())
        if not frames:
            raise InputError(f"room {room.name!r}: {sub}/ is empty")
        files.extend(frames)
    poses = _load_json(room / "poses.json", room.name)
    if not isinstance(poses, list) or not poses:
        raise InputError(f"room {room.name!r}: poses.json must be a non-empty list of poses")
    intr = _load_json(room / "intrinsics.json", room.name)
    missing = [k for k in INTRINSIC_KEYS if not isinstance(intr.get(k) if isinstance(intr, dict) else None, (int, float))]
    if missing:
        raise InputError(f"room {room.name!r}: intrinsics.json missing numeric keys {missing}")
    files += [room / "poses.json", room / "intrinsics.json"]
    return RoomInput(room.name, files)


_BY_TIER = {"photo": _photo, "video": _video, "lidar": _lidar}


def validate_input(input_path: Path, tier: str) -> list[RoomInput]:
    input_path = Path(input_path)
    if tier not in _BY_TIER:
        raise InputError(f"unknown tier {tier!r}")
    if not input_path.is_dir():
        raise InputError(f"input must be a directory with one subfolder per room: {input_path}")
    rooms = _visible(p for p in input_path.iterdir() if p.is_dir())
    if not rooms:
        raise InputError(f"no room subfolders under {input_path}")
    return [_BY_TIER[tier](r) for r in rooms]
