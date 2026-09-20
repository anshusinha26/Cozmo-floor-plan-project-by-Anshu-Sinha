"""Input convention for `cozmo run`.

* photo: a directory of 2 or more images, which is one room named after the
  folder, or a directory of such folders, which is several rooms.
* video: a directory holding exactly one clip, which is one room, or a
  directory of such folders. A Stray Scanner scan folder also counts, and
  there only rgb.mp4 is readable.
* lidar: ONE Stray Scanner scan folder covering the whole property (see
  :mod:`cozmo.io.stray`); the pipeline segments rooms itself.

Tier isolation: the video tier may open only rgb.mp4, the lidar tier may read
everything, the photo tier only image files. ``InputSpec.files`` is the set a
tier may read, and it is also what gets hashed into the run manifest.

Validation is structural only. No pixels are decoded here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from cozmo.io.stray import StrayScan

# iPhones produce HEIC stills and HEVC .mov clips by default, and the
# extension case depends on how the files were transferred, so everything is
# compared lower-cased.
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".heic", ".heif"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".hevc"}
KNOWN_JUNK = {".ds_store", ".thumbs.db", ".aae"}  # Finder and iOS sidecar files


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


def _visible(paths):
    """Sorted, skipping dotfiles and the sidecar files phones leave behind."""
    return sorted(p for p in paths
                  if not p.name.startswith(".") and p.suffix.lower() not in KNOWN_JUNK)


def _describe_contents(root: Path, limit: int = 6) -> str:
    """What is actually in a folder, for an error message that helps."""
    try:
        names = [p.name for p in _visible(root.iterdir())][:limit]
    except OSError:
        return "unreadable"
    if not names:
        return "empty"
    more = "" if len(names) < limit else ", ..."
    return ", ".join(names) + more


def looks_like_scan(root: Path) -> bool:
    """True for a Stray Scanner export folder (odometry.csv, or depth/ and confidence/)."""
    return (root / "odometry.csv").is_file() or ((root / "depth").is_dir() and (root / "confidence").is_dir())


def _images_in(folder: Path) -> list[Path]:
    return _visible(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXT)


def _clips_in(folder: Path) -> list[Path]:
    return _visible(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXT)


def _photo(root: Path) -> InputSpec:
    if not root.is_dir():
        raise InputError(f"photo input must be a directory: {root}")
    if looks_like_scan(root):
        # Tier isolation: depth/ holds png files, so without this check the photo
        # tier would silently read LiDAR depth maps as if they were room photos.
        raise InputError(f"{root} is a scan folder; the photo tier may not read scan data")
    own = _images_in(root)
    if own:
        # A folder of photos is one room, named after the folder.
        if len(own) < 2:
            raise InputError(
                f"room {root.name!r}: photo tier needs at least 2 images, found {len(own)}. "
                f"Accepted: {', '.join(sorted(IMAGE_EXT))}, any case. Folder holds: "
                f"{_describe_contents(root)}")
        rooms = [RoomInput(root.name, own)]
        return InputSpec("photo", root, own, rooms=rooms)
    subdirs = _visible(p for p in root.iterdir() if p.is_dir())
    if not subdirs:
        raise InputError(
            f"no images and no room subfolders under {root}. The photo tier wants either a folder "
            f"of 2 or more images ({', '.join(sorted(IMAGE_EXT))}, any case) or a folder of such "
            f"folders. Folder holds: {_describe_contents(root)}")
    rooms = []
    for d in subdirs:
        imgs = _images_in(d)
        if len(imgs) < 2:
            raise InputError(
                f"room {d.name!r}: photo tier needs at least 2 images, found {len(imgs)}. "
                f"Folder holds: {_describe_contents(d)}")
        rooms.append(RoomInput(d.name, imgs))
    return InputSpec("photo", root, [f for r in rooms for f in r.files], rooms=rooms)


def _video(root: Path) -> InputSpec:
    if not root.is_dir():
        raise InputError(f"video input must be a directory: {root}")
    if looks_like_scan(root):
        scan = StrayScan(root, "video")
        if not scan.open("rgb.mp4").is_file():
            raise InputError(f"video tier needs rgb.mp4 in {root}")
        return InputSpec("video", root, scan.files())
    clips = _clips_in(root)
    if len(clips) == 1:
        return InputSpec("video", root, clips, rooms=[RoomInput(root.name, clips)])
    if len(clips) > 1:
        raise InputError(
            f"room {root.name!r}: video tier needs exactly one clip, found {len(clips)}: "
            f"{', '.join(p.name for p in clips)}. Put one room's clip in one folder")
    subdirs = _visible(p for p in root.iterdir() if p.is_dir())
    if not subdirs:
        raise InputError(
            f"video tier needs one clip or room subfolders in {root}. Accepted clip types: "
            f"{', '.join(sorted(VIDEO_EXT))}, any case. Folder holds: {_describe_contents(root)}")
    rooms = []
    for d in subdirs:
        c = _clips_in(d)
        if len(c) != 1:
            raise InputError(
                f"room {d.name!r}: video tier needs exactly one clip, found {len(c)}. "
                f"Folder holds: {_describe_contents(d)}")
        rooms.append(RoomInput(d.name, c))
    return InputSpec("video", root, [f for r in rooms for f in r.files], rooms=rooms)


def _lidar(root: Path) -> InputSpec:
    """A Stray Scanner export, whatever the folder is called.

    Stray names the folder after the scan id, and people rename it. Nothing
    here depends on the name: the layout is what identifies the format.
    """
    if not root.is_dir():
        raise InputError(f"lidar input must be a scan folder: {root}")
    scan = StrayScan(root, "lidar")
    for name in ("odometry.csv",):
        if not (root / name).is_file():
            raise InputError(
                f"lidar tier needs {name} in {root}. This should be a Stray Scanner export folder "
                f"holding rgb.mp4, depth/, confidence/ and odometry.csv; the folder may be named "
                f"anything. Folder holds: {_describe_contents(root)}")
    for sub in ("depth", "confidence"):
        if not (root / sub).is_dir():
            raise InputError(
                f"lidar tier needs {sub}/ in {root}. Folder holds: {_describe_contents(root)}")
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
