"""The frame interface every tier feeds the damage module.

A frame is an image, and optionally metric depth, intrinsics and a pose. The
optional parts are what separate the tiers: the LiDAR tier supplies all of
them, the video and photo tiers supply the image alone until their
reconstruction lands. The detector runs either way; only the extent changes
from measured to unbounded.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import cv2
import numpy as np

try:  # iPhone stills are HEIC; the plugin teaches Pillow to open them.
    import pillow_heif

    pillow_heif.register_heif_opener()
    HEIF_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only where the wheel is missing
    HEIF_AVAILABLE = False


@dataclass
class DamageFrame:
    frame_id: str
    image: np.ndarray  # (H, W, 3) RGB uint8
    depth: np.ndarray | None = None  # (h, w) metres, may differ in size from image
    intrinsics: tuple[float, float, float, float] | None = None  # fx, fy, cx, cy for depth
    pose: np.ndarray | None = None  # (4, 4) camera to world, OpenCV axes
    source: str | None = None

    @property
    def has_metric_depth(self) -> bool:
        return self.depth is not None and self.intrinsics is not None

    def unproject(self, u: float, v: float) -> np.ndarray | None:
        """World point for an image pixel, or None without depth or pose."""
        if self.depth is None or self.intrinsics is None:
            return None
        dh, dw = self.depth.shape
        ih, iw = self.image.shape[:2]
        du = int(round(u * dw / iw))
        dv = int(round(v * dh / ih))
        if not (0 <= du < dw and 0 <= dv < dh):
            return None
        d = float(self.depth[dv, du])
        if not np.isfinite(d) or d <= 0:
            return None
        fx, fy, cx, cy = self.intrinsics
        p = np.array([(du - cx) / fx * d, (dv - cy) / fy * d, d])
        if self.pose is None:
            return p
        return self.pose[:3, :3] @ p + self.pose[:3, 3]


def frames_from_images(paths: list[Path], max_side: int = 1600) -> Iterator[DamageFrame]:
    """Photo tier and any loose image set. No depth, so extents stay unbounded."""
    for p in sorted(paths):
        img = cv2.imread(str(p))
        if img is None and p.suffix.lower() in (".heic", ".heif"):
            if not HEIF_AVAILABLE:
                raise RuntimeError(
                    f"{p.name} is HEIC and pillow-heif is not installed; run uv sync")
            from PIL import Image

            img = np.asarray(Image.open(p).convert("RGB"))[..., ::-1].copy()
        if img is None:
            continue
        if max(img.shape[:2]) > max_side:
            scale = max_side / max(img.shape[:2])
            img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        yield DamageFrame(frame_id=p.stem, image=img[..., ::-1].copy(), source=str(p))


def frames_from_stray(scan, stride: int = 60, max_frames: int | None = None) -> Iterator[DamageFrame]:
    """LiDAR tier: RGB decoded from rgb.mp4, paired with the depth frame and pose.

    Random seek fails on these HEVC files, so the video is decoded
    sequentially and only the wanted frames are kept.
    """
    od = scan.odometry
    wanted = {int(od["frame"][i]): i for i in range(0, len(od["frame"]), stride)}
    if max_frames is not None:
        wanted = dict(list(wanted.items())[:max_frames])
    cap = cv2.VideoCapture(str(scan.open("rgb.mp4")))
    pos = 0
    try:
        while True:
            ok, bgr = cap.read()
            if not ok:
                break
            i = wanted.get(pos)
            if i is not None:
                # Portrait capture stored rotated: upright is a clockwise quarter turn.
                bgr = cv2.rotate(bgr, cv2.ROTATE_90_CLOCKWISE)
                depth = scan.read_depth(pos)
                conf = scan.read_confidence(pos)
                depth = np.where(conf == 2, depth, 0.0)
                depth = cv2.rotate(depth, cv2.ROTATE_90_CLOCKWISE)
                dh, dw = depth.shape
                # Intrinsics are for the unrotated full frame; after the quarter
                # turn the axes swap, and they are scaled to the depth grid.
                sx, sy = dw / 1440.0, dh / 1920.0
                fx = float(od["fy"][i] * sx)
                fy = float(od["fx"][i] * sy)
                cx = float((1440.0 - od["cy"][i]) * sx)
                cy = float(od["cx"][i] * sy)
                from scipy.spatial.transform import Rotation as Rot

                pose = np.eye(4)
                R = Rot.from_quat(od["q"][i]).as_matrix()
                # Undo the image rotation in the camera frame so rays still match.
                Rz = np.array([[0.0, 1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
                pose[:3, :3] = R @ Rz.T
                pose[:3, 3] = od["t"][i]
                yield DamageFrame(frame_id=f"{pos:06d}", image=bgr[..., ::-1].copy(),
                                  depth=depth, intrinsics=(fx, fy, cx, cy), pose=pose,
                                  source=f"rgb.mp4#{pos}")
            pos += 1
    finally:
        cap.release()
