"""Input convention for `cozmo run`.

* photo: a directory with one subfolder per room (the room id), each holding
  2 or more images (jpg, jpeg, png, heic).
* video and lidar: ONE Stray Scanner scan folder covering the whole property
  (see :mod:`cozmo.io.stray`); the pipeline segments rooms itself.

Tier isolation: the video tier may open only rgb.mp4, the lidar tier may read
everything, the photo tier only image files. ``InputSpec.files`` is the set a
tier may read, and it is also what gets hashed into the run manifest.

Validation is structural only. No pixels are decoded here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from cozmo.io.stray import StrayScan

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".heic"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}


class InputError(ValueError):
    """Bad capture layout. Message names what is wrong."""


@dataclass
class RoomInput:
    room_id: str
    files: list[Path] = field(default_factory=list)


@dataclass
class InputSpec:
    tier: str
    root: Path
    files: list[Path]
    rooms: list[RoomInput] | None = None  # photo tier only
    n_frames: int | None = None  # lidar tier only
    skipped: list[str] = field(default_factory=list)  # subfolders that hold no room


def _visible(paths):
    return sorted(p for p in paths if not p.name.startswith("."))


def looks_like_scan(root: Path) -> bool:
    """True for a Stray Scanner export folder (odometry.csv, or depth/ and confidence/)."""
    return (root / "odometry.csv").is_file() or ((root / "depth").is_dir() and (root / "confidence").is_dir())


def _photo(root: Path) -> InputSpec:
    if not root.is_dir():
        raise InputError(f"photo input must be a directory with one subfolder per room: {root}")
    if looks_like_scan(root):
        # Tier isolation: depth/ holds png files, so without this check the photo
        # tier would silently read LiDAR depth maps as if they were room photos.
        raise InputError(f"{root} is a scan folder; the photo tier may not read scan data")
    subdirs = _visible(p for p in root.iterdir() if p.is_dir())
    if not subdirs:
        raise InputError(f"no room subfolders under {root}")
    rooms, skipped = [], []
    for d in subdirs:
        imgs = _visible(p for p in d.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXT)
        if len(imgs) < 2:
            # A capture folder often carries things that are not rooms: a
            # measurements pdf, a folder of screenshots. Naming them and moving
            # on beats refusing the whole capture over one of them.
            skipped.append(f"{d.name} ({len(imgs)} image(s), needs at least 2)")
            continue
        rooms.append(RoomInput(d.name, imgs))
    if not rooms:
        raise InputError(f"no room folder under {root} has enough images; skipped: "
                         f"{', '.join(skipped) if skipped else 'none'}")
    return InputSpec("photo", root, [f for r in rooms for f in r.files], rooms=rooms,
                     skipped=skipped)


def _video(root: Path) -> InputSpec:
    """A Stray Scanner folder (rgb.mp4) or any folder holding exactly one video file.

    Either way the spec lists the one video, so tier isolation holds: the video
    tier never sees depth, odometry or the still photos sitting beside the clip.
    """
    if not root.is_dir():
        raise InputError(f"video input must be a folder holding one video: {root}")
    if looks_like_scan(root):
        scan = StrayScan(root, "video")
        if not scan.open("rgb.mp4").is_file():
            raise InputError(f"video tier needs rgb.mp4 in {root}")
        return InputSpec("video", root, scan.files())
    vids = _visible(p for p in root.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXT)
    if len(vids) > 1:
        raise InputError(f"{root} holds {len(vids)} video files: {', '.join(p.name for p in vids)}")
    if vids:
        return InputSpec("video", root, vids)

    # A property captured as one clip per room, the same layout the photo tier
    # takes. Each room is reconstructed on its own and the rooms are stitched.
    rooms, skipped = [], []
    for d in _visible(p for p in root.iterdir() if p.is_dir()):
        sub = _visible(p for p in d.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXT)
        if len(sub) == 1:
            rooms.append(RoomInput(d.name, sub))
        else:
            skipped.append(f"{d.name} ({len(sub)} video(s), needs exactly 1)")
    if rooms:
        return InputSpec("video", root, [f for r in rooms for f in r.files], rooms=rooms,
                         skipped=skipped)
    raise InputError(f"no video file in {root}, and no subfolder holds exactly one "
                     f"(looked for {', '.join(sorted(VIDEO_EXT))})"
                     + (f"; skipped: {', '.join(skipped)}" if skipped else ""))


def _lidar(root: Path) -> InputSpec:
    if not root.is_dir():
        raise InputError(f"lidar input must be a scan folder: {root}")
    scan = StrayScan(root, "lidar")
    for name in ("odometry.csv",):
        if not (root / name).is_file():
            raise InputError(f"lidar tier needs {name} in {root}")
    for sub in ("depth", "confidence"):
        if not (root / sub).is_dir():
            raise InputError(f"lidar tier needs {sub}/ in {root}")
    n_depth = sum(1 for p in (root / "depth").glob("*.png"))
    n_conf = sum(1 for p in (root / "confidence").glob("*.png"))
    if n_depth == 0:
        raise InputError(f"lidar tier: depth/ has no png frames in {root}")
    if n_depth != n_conf:
        raise InputError(f"lidar tier: depth/ has {n_depth} frames but confidence/ has {n_conf}")
    try:
        n = scan.n_frames
    except ValueError as e:
        raise InputError(f"lidar tier: {e}") from e
    if n == 0:
        raise InputError("lidar tier: odometry.csv has no rows")
    if n > n_depth:
        raise InputError(f"lidar tier: odometry.csv has {n} rows but only {n_depth} depth frames")
    return InputSpec("lidar", root, scan.files(), n_frames=n)


_BY_TIER = {"photo": _photo, "video": _video, "lidar": _lidar}


def validate_input(input_path: Path, tier: str) -> InputSpec:
    input_path = Path(input_path)
    if tier not in _BY_TIER:
        raise InputError(f"unknown tier {tier!r}")
    if not input_path.exists():
        raise InputError(f"input not found: {input_path}")
    return _BY_TIER[tier](input_path)
