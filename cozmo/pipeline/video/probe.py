"""Container facts about a video file, read before any decoding happens.

ffprobe is preferred when it is on PATH because it emits JSON. imageio-ffmpeg
ships ffmpeg but not ffprobe, so the fallback parses ``ffmpeg -i`` stderr,
which is enough for resolution, fps, codec, duration and the rotation tag.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

VIDEO_SUFFIXES = (".mp4", ".mov", ".m4v", ".avi", ".mkv", ".MP4", ".MOV")


class ProbeError(RuntimeError):
    pass


@dataclass(frozen=True)
class VideoInfo:
    path: str
    width: int
    height: int
    fps: float
    codec: str
    duration_s: float
    rotation_deg: int | None
    size_bytes: int
    n_frames: int | None

    @property
    def upright_wh(self) -> tuple[int, int]:
        """Resolution after ffmpeg applies the container rotation tag."""
        if self.rotation_deg is not None and abs(self.rotation_deg) % 180 == 90:
            return self.height, self.width
        return self.width, self.height

    def as_dict(self) -> dict:
        d = asdict(self)
        d["upright_wh"] = list(self.upright_wh)
        return d


def find_video(folder: Path) -> Path:
    """The single video file in a capture folder. Globbed, never assumed by name."""
    folder = Path(folder)
    if folder.is_file():
        return folder
    hits = sorted({p for s in VIDEO_SUFFIXES for p in folder.glob(f"*{s}")})
    if not hits:
        raise ProbeError(f"no video file in {folder} (looked for {', '.join(VIDEO_SUFFIXES)})")
    if len(hits) > 1:
        raise ProbeError(f"{folder} holds {len(hits)} video files: {', '.join(p.name for p in hits)}")
    return hits[0]


def ffmpeg_exe() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def _probe_json(path: Path) -> VideoInfo:
    cmd = [shutil.which("ffprobe"), "-v", "error", "-select_streams", "v:0", "-of", "json",
           "-show_entries",
           "stream=width,height,r_frame_rate,codec_name,duration,nb_frames:"
           "stream_side_data=rotation:stream_tags=rotate:format=duration,size",
           str(path)]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    d = json.loads(out)
    if not d.get("streams"):
        raise ProbeError(f"{path} has no video stream")
    s, fm = d["streams"][0], d.get("format", {})
    num, den = s["r_frame_rate"].split("/")
    rot = None
    for sd in s.get("side_data_list") or []:
        if "rotation" in sd:
            rot = int(round(float(sd["rotation"])))
    if rot is None and (s.get("tags") or {}).get("rotate"):
        rot = int(round(float(s["tags"]["rotate"])))
    nb = s.get("nb_frames")
    return VideoInfo(
        path=str(path), width=int(s["width"]), height=int(s["height"]),
        fps=float(num) / float(den) if float(den) else 0.0, codec=str(s["codec_name"]),
        duration_s=float(s.get("duration") or fm.get("duration") or 0.0),
        rotation_deg=rot, size_bytes=int(fm.get("size") or path.stat().st_size),
        n_frames=int(nb) if nb and str(nb).isdigit() else None,
    )


_RE_STREAM = re.compile(r"Stream #\d+:\d+.*?Video:\s*(\w+).*?,\s*(\d+)x(\d+)[^,]*,.*?([\d.]+)\s*fps", re.S)
_RE_DUR = re.compile(r"Duration:\s*(\d+):(\d+):([\d.]+)")
_RE_ROT = re.compile(r"rotate\s*:\s*(-?\d+)|displaymatrix: rotation of (-?[\d.]+) degrees")


def _probe_ffmpeg(path: Path) -> VideoInfo:
    err = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(path)],
                         capture_output=True, text=True).stderr
    m = _RE_STREAM.search(err)
    if not m:
        raise ProbeError(f"could not read a video stream out of {path}")
    codec, w, h, fps = m.group(1), int(m.group(2)), int(m.group(3)), float(m.group(4))
    dm = _RE_DUR.search(err)
    dur = (int(dm.group(1)) * 3600 + int(dm.group(2)) * 60 + float(dm.group(3))) if dm else 0.0
    rm = _RE_ROT.search(err)
    rot = int(round(float(rm.group(1) or rm.group(2)))) if rm else None
    return VideoInfo(path=str(path), width=w, height=h, fps=fps, codec=codec, duration_s=dur,
                     rotation_deg=rot, size_bytes=path.stat().st_size, n_frames=None)


def probe(path: Path) -> VideoInfo:
    path = Path(path)
    if not path.exists():
        raise ProbeError(f"video not found: {path}")
    if shutil.which("ffprobe"):
        try:
            return _probe_json(path)
        except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError, ValueError):
            pass
    return _probe_ffmpeg(path)


def probe_table(paths: list[Path]) -> str:
    """One row per video: resolution, fps, codec, duration, rotation tag, size."""
    head = f"{'file':<26} {'resolution':<11} {'fps':>6} {'codec':<6} {'duration':>9} {'rotation':>8} {'size':>9} {'upright':<11}"
    rows = [head, "-" * len(head)]
    for p in paths:
        i = probe(p)
        uw, uh = i.upright_wh
        rows.append(f"{Path(i.path).name:<26} {i.width}x{i.height:<6} {i.fps:>6.2f} {i.codec:<6} "
                    f"{i.duration_s:>8.1f}s {str(i.rotation_deg):>8} {i.size_bytes / 1e6:>7.0f}MB {uw}x{uh:<6}")
    return "\n".join(rows)
