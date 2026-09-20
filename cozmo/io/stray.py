"""Stray Scanner export reader with tier isolation.

Layout of one scan folder (one per property)::

    rgb.mp4            1920x1440 HEVC, 60 fps, portrait stored rotated
    depth/NNNNNN.png   256x192 uint16 millimetres, one per video frame
    confidence/NNNNNN.png  uint8 in {0, 1, 2}
    odometry.csv       timestamp, frame, x, y, z, qx, qy, qz, qw, fx, fy, cx, cy (+ empty columns)
    camera_matrix.csv  intrinsics for 1920x1440 (per-frame values in odometry.csv are preferred)
    imu.csv

Poses are camera-to-world, quaternion order x, y, z, w. Camera axes follow
OpenCV (x right, y down, z forward); world y is up and gravity aligned.

Tier isolation is enforced here, not by convention: every file access goes
through :meth:`StrayScan.open`, which raises :class:`TierViolation` when the
tier is not allowed to read that file. lidar may read everything, video only
rgb.mp4, photo nothing from a scan folder (photo captures use a different
layout). The same rule decides which files are hashed into the run manifest,
so provenance never touches data the tier could not have used.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Iterator

import cv2
import numpy as np
from scipy.spatial.transform import Rotation as Rot

FULL_RES = (1920, 1440)


class TierViolation(PermissionError):
    """A tier tried to read a file it is not allowed to see."""


@dataclass
class Frame:
    index: int
    timestamp: float
    t: np.ndarray  # (3,) camera position in world
    R: np.ndarray  # (3, 3) camera-to-world rotation
    fx: float
    fy: float
    cx: float
    cy: float
    depth: np.ndarray  # (H, W) float32 metres, 0 where invalid
    confidence: np.ndarray  # (H, W) uint8

    def unproject(self, mask: np.ndarray) -> np.ndarray:
        """World-frame points for masked pixels: OpenCV pinhole then p_w = R p_c + t."""
        v, u = np.nonzero(mask)
        d = self.depth[v, u].astype(np.float64)
        pc = np.stack([(u - self.cx) / self.fx * d, (v - self.cy) / self.fy * d, d], axis=1)
        return pc @ self.R.T + self.t


def _visible_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file() and not p.name.startswith("."))


class StrayScan:
    def __init__(self, root: Path, tier: str) -> None:
        self.root = Path(root)
        self.tier = tier
        if tier not in ("lidar", "video", "photo"):
            raise ValueError(f"unknown tier {tier!r}")

    # ------------------------------------------------------------ isolation

    def allowed(self, rel: str) -> bool:
        rel = Path(rel).as_posix()
        if self.tier == "lidar":
            return True
        if self.tier == "video":
            return rel == "rgb.mp4"
        return False

    def open(self, rel: str) -> Path:
        """Return the absolute path after checking the tier may read it."""
        if not self.allowed(rel):
            raise TierViolation(f"tier {self.tier!r} may not read {rel!r}")
        return self.root / rel

    def files(self) -> list[Path]:
        """Files this tier is allowed to read; this is what gets hashed for provenance."""
        return [p for p in _visible_files(self.root) if self.allowed(p.relative_to(self.root).as_posix())]

    # ------------------------------------------------------------- odometry

    @cached_property
    def odometry(self) -> dict[str, np.ndarray]:
        path = self.open("odometry.csv")
        with open(path, "r", encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh)
            header = [h.strip() for h in next(reader)]
            rows = [r for r in reader if r and r[0].strip()]
        col = {h: i for i, h in enumerate(header)}
        need = ["timestamp", "frame", "x", "y", "z", "qx", "qy", "qz", "qw", "fx", "fy", "cx", "cy"]
        missing = [k for k in need if k not in col]
        if missing:
            raise ValueError(f"odometry.csv missing columns {missing}")

        def column(name, dtype=np.float64):
            return np.array([r[col[name]].strip() for r in rows], dtype=dtype)

        return {
            "timestamp": column("timestamp"),
            "frame": column("frame", np.int64),
            "t": np.stack([column("x"), column("y"), column("z")], axis=1),
            "q": np.stack([column("qx"), column("qy"), column("qz"), column("qw")], axis=1),
            "fx": column("fx"), "fy": column("fy"), "cx": column("cx"), "cy": column("cy"),
        }

    @property
    def n_frames(self) -> int:
        return int(len(self.odometry["frame"]))

    # ---------------------------------------------------------------- frames

    def read_depth(self, frame: int) -> np.ndarray:
        img = cv2.imread(str(self.open(f"depth/{frame:06d}.png")), cv2.IMREAD_UNCHANGED)
        if img is None or img.dtype != np.uint16:
            raise ValueError(f"depth/{frame:06d}.png missing or not uint16")
        return img.astype(np.float32) / 1000.0

    def read_confidence(self, frame: int) -> np.ndarray:
        img = cv2.imread(str(self.open(f"confidence/{frame:06d}.png")), cv2.IMREAD_UNCHANGED)
        if img is None:
            raise ValueError(f"confidence/{frame:06d}.png missing")
        return img

    def frames(self, stride: int = 10) -> Iterator[Frame]:
        od = self.odometry
        for i in range(0, self.n_frames, stride):
            frame = int(od["frame"][i])
            depth = self.read_depth(frame)
            conf = self.read_confidence(frame)
            h, w = depth.shape
            sx, sy = w / FULL_RES[0], h / FULL_RES[1]
            yield Frame(
                index=frame,
                timestamp=float(od["timestamp"][i]),
                t=od["t"][i].copy(),
                R=Rot.from_quat(od["q"][i]).as_matrix(),
                fx=float(od["fx"][i] * sx), fy=float(od["fy"][i] * sy),
                cx=float(od["cx"][i] * sx), cy=float(od["cy"][i] * sy),
                depth=depth,
                confidence=conf,
            )
