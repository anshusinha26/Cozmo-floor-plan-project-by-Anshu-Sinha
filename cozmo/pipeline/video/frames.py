"""Stage 1: video file to a directory of upright, blur-filtered jpg frames.

Decoding goes through the ffmpeg binary that imageio-ffmpeg ships, not OpenCV.
Two reasons. OpenCV's seek is unreliable on phone HEVC (the sample scan's
rgb.mp4 reports 1715 frames and decodes 1714, and random seeks land on the
wrong frame), and OpenCV would hand back full 4K frames for Python to shrink.
ffmpeg does the frame rate reduction and the scaling inside the decode graph,
so a 3840x2160 frame never reaches this process.

ffmpeg applies the container rotation tag by itself, so phone video comes out
upright with no help. ``rotation="auto"`` leaves that alone. An explicit angle
turns autorotation off and rotates by hand: Stray Scanner's rgb.mp4 carries no
rotation tag and needs 90.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from cozmo.pipeline.video.probe import VideoInfo, ffmpeg_exe, probe

log = logging.getLogger(__name__)

ROTATIONS = ("auto", "0", "90", "180", "270")
# transpose=1 is 90 clockwise, transpose=2 is 90 counter-clockwise.
_TRANSPOSE = {"0": "", "90": "transpose=1", "180": "transpose=1,transpose=1", "270": "transpose=2"}


class FrameError(RuntimeError):
    pass


@dataclass
class FrameSet:
    dir: Path
    names: list[str]
    times_s: np.ndarray
    width: int
    height: int
    fps_used: float
    rotation: str
    info: VideoInfo
    n_decoded: int
    n_dropped_blur: int
    blur_scores: np.ndarray = field(default_factory=lambda: np.zeros(0))

    def __len__(self) -> int:
        return len(self.names)

    def path(self, name: str) -> Path:
        return self.dir / name

    def summary(self) -> dict:
        return {"video": self.info.path, "decoded": self.n_decoded, "kept": len(self.names),
                "dropped_blur": self.n_dropped_blur, "fps_used": round(self.fps_used, 3),
                "frame_wh": [self.width, self.height], "rotation": self.rotation,
                "duration_s": round(self.info.duration_s, 2),
                "source_wh": [self.info.width, self.info.height],
                "source_fps": round(self.info.fps, 3), "codec": self.info.codec,
                "rotation_tag": self.info.rotation_deg}


def plan_fps(info: VideoInfo, target_fps: float, max_frames: int) -> float:
    """Target rate, lowered until the clip fits the frame budget."""
    if info.duration_s <= 0:
        return target_fps
    return float(min(target_fps, max_frames / info.duration_s))


def _scale_filter(long_side: int) -> str:
    # Long side to long_side, short side to an even number so h264 style
    # encoders and the jpg writer both stay happy. -2 keeps the aspect ratio.
    return (f"scale='if(gt(iw,ih),{long_side},-2)':'if(gt(iw,ih),-2,{long_side})'"
            f":flags=area")


def decode(video: Path, out_dir: Path, target_fps: float = 10.0, long_side: int = 1280,
           max_frames: int = 600, rotation: str = "auto") -> tuple[list[str], float, VideoInfo]:
    """Write upright, downscaled jpgs into ``out_dir``. Returns names, fps used, probe info."""
    if rotation not in ROTATIONS:
        raise FrameError(f"rotation must be one of {ROTATIONS}, got {rotation!r}")
    video = Path(video)
    info = probe(video)
    fps = plan_fps(info, target_fps, max_frames)
    if fps < target_fps:
        log.info("%s: %.1f s at %.1f fps would exceed the %d frame budget; decoding at %.2f fps",
                 video.name, info.duration_s, target_fps, max_frames, fps)

    out_dir = Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    chain = [f"fps={fps:.6f}"]
    pre: list[str] = []
    if rotation != "auto":
        pre = ["-noautorotate"]
        if _TRANSPOSE[rotation]:
            chain.append(_TRANSPOSE[rotation])
    chain.append(_scale_filter(long_side))

    cmd = [ffmpeg_exe(), "-v", "error", "-y", *pre, "-i", str(video),
           "-vf", ",".join(chain), "-qscale:v", "2", "-f", "image2",
           str(out_dir / "f%05d.jpg")]
    log.info("decoding %s: %s", video.name, " ".join(cmd[-6:]))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise FrameError(f"ffmpeg failed on {video}: {r.stderr.strip()[:400]}")
    names = sorted(p.name for p in out_dir.glob("f*.jpg"))
    if not names:
        raise FrameError(f"ffmpeg wrote no frames for {video}")
    return names, fps, info


def blur_scores(dir_: Path, names: list[str]) -> np.ndarray:
    """Variance of the Laplacian per frame, read one file at a time."""
    import cv2

    out = np.empty(len(names), dtype=np.float64)
    for i, n in enumerate(names):
        g = cv2.imread(str(Path(dir_) / n), cv2.IMREAD_GRAYSCALE)
        if g is None:
            out[i] = -1.0
            continue
        out[i] = float(cv2.Laplacian(g, cv2.CV_64F).var())
    return out


def extract(video: Path, out_dir: Path, target_fps: float = 10.0, long_side: int = 1280,
            max_frames: int = 600, rotation: str = "auto", drop_blur_frac: float = 0.20) -> FrameSet:
    """Decode, score blur, delete the blurriest ``drop_blur_frac`` of the frames."""
    import cv2

    names, fps, info = decode(video, out_dir, target_fps, long_side, max_frames, rotation)
    n_decoded = len(names)
    scores = blur_scores(out_dir, names)
    times = np.arange(n_decoded, dtype=np.float64) / fps

    keep = np.ones(n_decoded, dtype=bool)
    if 0.0 < drop_blur_frac < 1.0 and n_decoded > 5:
        thr = float(np.quantile(scores, drop_blur_frac))
        keep = scores >= thr
    for n, k in zip(names, keep):
        if not k:
            (Path(out_dir) / n).unlink()
    kept = [n for n, k in zip(names, keep) if k]

    probe_img = cv2.imread(str(Path(out_dir) / kept[0]))
    h, w = probe_img.shape[:2]
    log.info("%s: decoded %d frames at %.2f fps, kept %d after the blur filter, %dx%d",
             Path(video).name, n_decoded, fps, len(kept), w, h)
    return FrameSet(dir=Path(out_dir), names=kept, times_s=times[keep], width=w, height=h,
                    fps_used=fps, rotation=rotation, info=info, n_decoded=n_decoded,
                    n_dropped_blur=n_decoded - len(kept), blur_scores=scores[keep])
