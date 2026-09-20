"""Synthetic Stray Scanner scans for tests: rectilinear rooms rendered by ray casting.

Produces the same layout as a real export (depth/, confidence/, odometry.csv,
camera_matrix.csv, an empty rgb.mp4 placeholder) so the pipeline can be tested
end to end without the sample data. Geometry is exact up to a few mm of
seeded noise, so tests can assert on known room sizes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from scipy.spatial.transform import Rotation as Rot

FULL_W, FULL_H = 1920, 1440
DEPTH_W, DEPTH_H = 256, 192
FX = 1596.0
CX, CY = 955.5, 717.7


@dataclass
class Rect:
    """Axis-aligned rectangle: plane ``axis`` = ``pos``, bounded on the other two axes."""

    axis: int
    pos: float
    lo: tuple[float, float]
    hi: tuple[float, float]


@dataclass
class Door:
    """Opening in the wall at x = ``x`` (if ``axis`` == 0) or z = ``z``, spanning ``a0..a1`` along the wall."""

    axis: int
    pos: float
    a0: float
    a1: float
    height: float = 2.0


@dataclass
class Scene:
    rooms: list[tuple[float, float, float, float]]  # (x0, z0, x1, z1)
    floor_y: float = -1.4
    height: float = 2.6
    doors: list[Door] = field(default_factory=list)
    ceiling: bool = True
    rects: list[Rect] = field(init=False)

    def __post_init__(self):
        self.rects = []
        top = self.floor_y + self.height
        for x0, z0, x1, z1 in self.rooms:
            self.rects.append(Rect(1, self.floor_y, (x0, z0), (x1, z1)))
            if self.ceiling:
                self.rects.append(Rect(1, top, (x0, z0), (x1, z1)))
            for axis, pos, lo, hi in ((0, x0, z0, z1), (0, x1, z0, z1), (2, z0, x0, x1), (2, z1, x0, x1)):
                self._wall(axis, pos, lo, hi, top)

    def _wall(self, axis, pos, lo, hi, top):
        # Split around doors on this wall; ``other`` is the in-plane horizontal axis.
        cuts = [(lo, hi)]
        for d in self.doors:
            if d.axis != axis or abs(d.pos - pos) > 1e-9:
                continue
            new = []
            for a, b in cuts:
                if d.a1 <= a or d.a0 >= b:
                    new.append((a, b))
                    continue
                if a < d.a0:
                    new.append((a, d.a0))
                if d.a1 < b:
                    new.append((d.a1, b))
                # lintel above the door
                self.rects.append(self._rect(axis, pos, (max(a, d.a0), self.floor_y + d.height), (min(b, d.a1), top)))
            cuts = new
        for a, b in cuts:
            self.rects.append(self._rect(axis, pos, (a, self.floor_y), (b, top)))

    @staticmethod
    def _rect(axis, pos, lo, hi):
        # For a wall with normal along x, in-plane axes are (z, y); for z, (x, y).
        return Rect(axis, pos, lo, hi)


def _others(axis: int) -> tuple[int, int]:
    return {0: (2, 1), 1: (0, 2), 2: (0, 1)}[axis]


def render_depth(scene: Scene, R: np.ndarray, t: np.ndarray, fx: float, fy: float, cx: float, cy: float,
                 w: int = DEPTH_W, h: int = DEPTH_H) -> np.ndarray:
    u, v = np.meshgrid(np.arange(w, dtype=np.float64), np.arange(h, dtype=np.float64))
    d_cam = np.stack([(u - cx) / fx, (v - cy) / fy, np.ones_like(u)], -1).reshape(-1, 3)
    d_w = d_cam @ R.T
    best = np.full(len(d_w), np.inf)
    for r in scene.rects:
        a1, a2 = _others(r.axis)
        da = d_w[:, r.axis]
        with np.errstate(divide="ignore", invalid="ignore"):
            tt = (r.pos - t[r.axis]) / da
        ok = (da != 0) & (tt > 1e-6) & (tt < best)
        p1 = t[a1] + tt * d_w[:, a1]
        p2 = t[a2] + tt * d_w[:, a2]
        ok &= (p1 >= r.lo[0]) & (p1 <= r.hi[0]) & (p2 >= r.lo[1]) & (p2 <= r.hi[1])
        best = np.where(ok, tt, best)
    depth = np.where(np.isfinite(best), best, 0.0)  # ray z component is 1, so t is the depth
    return depth.reshape(h, w)


def look_at_rotation(yaw: float, pitch: float) -> np.ndarray:
    """Camera-to-world rotation for OpenCV axes (x right, y down, z forward), world y up."""
    f = np.array([np.cos(pitch) * np.cos(yaw), np.sin(pitch), np.cos(pitch) * np.sin(yaw)])
    up = np.array([0.0, 1.0, 0.0])
    x = np.cross(f, up)
    x /= np.linalg.norm(x)
    y = np.cross(f, x)
    return np.stack([x, y, f], axis=1)


def default_trajectory(scene: Scene, n_per_room: int = 24) -> list[tuple[np.ndarray, float, float]]:
    """A realistic-ish capture: walk a loop inside each room looking at the walls, then through each door.

    A handheld capture sweeps the room rather than spinning on the spot, so the
    trajectory follows a rectangle inset from the walls with the camera panning,
    which is what gives near-complete floor coverage.
    """
    cam_y = scene.floor_y + 1.4
    poses = []
    for x0, z0, x1, z1 in scene.rooms:
        inset = min(0.9, 0.3 * min(x1 - x0, z1 - z0))
        cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
        corners = [(x0 + inset, z0 + inset), (x1 - inset, z0 + inset), (x1 - inset, z1 - inset), (x0 + inset, z1 - inset)]
        per_edge = max(n_per_room // 4, 3)
        k = 0
        for a, b in zip(corners, corners[1:] + corners[:1]):
            for s in np.linspace(0.0, 1.0, per_edge, endpoint=False):
                px = a[0] + (b[0] - a[0]) * s
                pz = a[1] + (b[1] - a[1]) * s
                pos = np.array([px, cam_y, pz])
                # Pan outward from the room centre so walls and floor are both covered.
                yaw = np.arctan2(pz - cz, px - cx) + [0.0, 0.7, -0.7][k % 3]
                pitch = [0.0, 0.5, -0.6, -0.3][k % 4]
                poses.append((pos, yaw, pitch))
                k += 1
        for i in range(4):
            poses.append((np.array([cx, cam_y, cz]), i * np.pi / 2, -0.5))
    for d in scene.doors:
        mid = (d.a0 + d.a1) / 2
        for s in np.linspace(-1.2, 1.2, 9):
            if d.axis == 0:
                pos = np.array([d.pos + s, cam_y, mid])
                yaw = 0.0
            else:
                pos = np.array([mid, cam_y, d.pos + s])
                yaw = np.pi / 2
            poses.append((pos, yaw, -0.3))
    return poses


def write_synthetic_scan(root: Path, scene: Scene, seed: int = 0, noise_m: float = 0.003,
                         n_per_room: int = 24, fps: float = 60.0) -> Path:
    root = Path(root)
    (root / "depth").mkdir(parents=True, exist_ok=True)
    (root / "confidence").mkdir(exist_ok=True)
    rng = np.random.default_rng(seed)
    sx = DEPTH_W / FULL_W
    fxd, cxd, cyd = FX * sx, CX * sx, CY * sx
    lines = ["timestamp, frame, x, y, z, qx, qy, qz, qw, fx, fy, cx, cy, distortion_center_x, distortion_center_y"]
    for i, (pos, yaw, pitch) in enumerate(default_trajectory(scene, n_per_room)):
        R = look_at_rotation(yaw, pitch)
        depth = render_depth(scene, R, pos, fxd, fxd, cxd, cyd)
        hit = depth > 0
        depth = depth + rng.normal(0.0, noise_m, depth.shape) * hit
        mm = np.clip(np.round(depth * 1000.0), 0, 65535).astype(np.uint16)
        conf = np.where(hit, 2, 0).astype(np.uint8)
        cv2.imwrite(str(root / "depth" / f"{i:06d}.png"), mm)
        cv2.imwrite(str(root / "confidence" / f"{i:06d}.png"), conf)
        q = Rot.from_matrix(R).as_quat()  # x, y, z, w
        lines.append(f"{i / fps:.6f}, {i:06d}, {pos[0]:.6f}, {pos[1]:.6f}, {pos[2]:.6f}, "
                     f"{q[0]:.8f}, {q[1]:.8f}, {q[2]:.8f}, {q[3]:.8f}, {FX}, {FX}, {CX}, {CY}, , ")
    (root / "odometry.csv").write_text("\n".join(lines) + "\n")
    (root / "camera_matrix.csv").write_text(f"{FX}, 0.0, {CX}\n0.0, {FX}, {CY}\n0.0, 0.0, 1.0")
    (root / "rgb.mp4").write_bytes(b"synthetic placeholder, not a video")
    return root


def one_room() -> Scene:
    return Scene(rooms=[(0.0, 0.0, 3.6, 4.8)], floor_y=-1.48, height=2.6)


def two_rooms() -> Scene:
    # Room A 4 x 5, room B 3 x 5 to its east, door in the shared wall x = 4.
    return Scene(rooms=[(0.0, 0.0, 4.0, 5.0), (4.0, 0.0, 7.0, 5.0)], floor_y=-1.4, height=2.5,
                 doors=[Door(axis=0, pos=4.0, a0=1.5, a1=2.4, height=2.0)])
