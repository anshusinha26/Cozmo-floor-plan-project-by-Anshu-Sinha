"""Stage 1: depth frames to a voxel-downsampled world point cloud with normals.

Normals are computed from the depth image itself (cross product of neighbour
differences in camera space) rather than from a neighbourhood search in the
fused cloud: the depth image already gives a structured grid, so this is both
faster and free of the mixing between surfaces that a radius search causes at
wall corners.

Normals are oriented toward the camera before fusing, so the two faces of a
shared wall (about 10 cm apart, therefore different voxels at 2 cm) keep
opposite normals instead of cancelling.

Memory is bounded by the number of occupied voxels, not by the number of
frames: every batch is quantised and merged into the accumulator, so a 9745
frame scan never materialises its full cloud.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from cozmo.io.stray import Frame, StrayScan

# Voxel index packing: 21 bits per axis around an origin offset, so coordinates
# within about +-20 km at 2 cm fit in one int64 key.
_BITS = 21
_OFF = 1 << (_BITS - 1)
_MASK = (1 << _BITS) - 1


def depth_normals(depth: np.ndarray, fx: float, fy: float, cx: float, cy: float) -> tuple[np.ndarray, np.ndarray]:
    """Per-pixel camera-space normals from a depth image, oriented toward the camera.

    Returns ``(normals, valid)`` where ``normals`` has shape (H, W, 3) and
    ``valid`` marks pixels with four finite depth neighbours on a locally
    continuous surface.
    """
    h, w = depth.shape
    u, v = np.meshgrid(np.arange(w, dtype=np.float64), np.arange(h, dtype=np.float64))
    z = depth.astype(np.float64)
    x = (u - cx) / fx * z
    y = (v - cy) / fy * z
    p = np.stack([x, y, z], axis=-1)

    du = np.zeros_like(p)
    dv = np.zeros_like(p)
    du[:, 1:-1] = p[:, 2:] - p[:, :-2]
    dv[1:-1, :] = p[2:, :] - p[:-2, :]

    ok = np.zeros((h, w), dtype=bool)
    ok[1:-1, 1:-1] = True
    ok &= z > 0
    ok[:, 1:-1] &= (z[:, 2:] > 0) & (z[:, :-2] > 0)
    ok[1:-1, :] &= (z[2:, :] > 0) & (z[:-2, :] > 0)
    # Depth discontinuities (occlusion edges) would create normals that belong
    # to no real surface, so drop neighbours more than 5% of depth apart.
    with np.errstate(invalid="ignore"):
        jump_u = np.zeros((h, w), dtype=bool)
        jump_v = np.zeros((h, w), dtype=bool)
        jump_u[:, 1:-1] = np.abs(z[:, 2:] - z[:, :-2]) > 0.05 * z[:, 1:-1]
        jump_v[1:-1, :] = np.abs(z[2:, :] - z[:-2, :]) > 0.05 * z[1:-1, :]
    ok &= ~(jump_u | jump_v)

    n = np.cross(du, dv)
    norm = np.linalg.norm(n, axis=-1)
    ok &= norm > 1e-12
    with np.errstate(invalid="ignore", divide="ignore"):
        n = n / norm[..., None]
    n = np.nan_to_num(n)
    # Orient toward the camera: the view ray is p, so require dot(n, p) < 0.
    flip = np.einsum("ijk,ijk->ij", n, p) > 0
    n[flip] *= -1.0
    return n, ok


class VoxelGrid:
    """Streaming voxel accumulator: mean point and mean normal per occupied cell."""

    def __init__(self, voxel_m: float) -> None:
        self.voxel = float(voxel_m)
        self._keys = np.zeros(0, dtype=np.int64)
        self._psum = np.zeros((0, 3), dtype=np.float64)
        self._nsum = np.zeros((0, 3), dtype=np.float64)
        self._count = np.zeros(0, dtype=np.int64)

    def _encode(self, points: np.ndarray) -> np.ndarray:
        idx = np.floor(points / self.voxel).astype(np.int64) + _OFF
        if np.any((idx < 0) | (idx > _MASK)):
            raise ValueError("point coordinates out of voxel index range")
        return (idx[:, 0] << (2 * _BITS)) | (idx[:, 1] << _BITS) | idx[:, 2]

    def add(self, points: np.ndarray, normals: np.ndarray) -> None:
        if len(points) == 0:
            return
        keys = np.concatenate([self._keys, self._encode(points)])
        psum = np.concatenate([self._psum, points.astype(np.float64)])
        nsum = np.concatenate([self._nsum, normals.astype(np.float64)])
        count = np.concatenate([self._count, np.ones(len(points), dtype=np.int64)])
        uniq, inv = np.unique(keys, return_inverse=True)
        self._keys = uniq
        self._psum = np.stack([np.bincount(inv, psum[:, i], len(uniq)) for i in range(3)], axis=1)
        self._nsum = np.stack([np.bincount(inv, nsum[:, i], len(uniq)) for i in range(3)], axis=1)
        self._count = np.bincount(inv, count, len(uniq)).astype(np.int64)

    def result(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Mean points, unit mean normals and hit counts, ordered by voxel key (deterministic)."""
        if len(self._keys) == 0:
            return np.zeros((0, 3)), np.zeros((0, 3)), np.zeros(0, dtype=np.int64)
        pts = self._psum / self._count[:, None]
        nrm = self._nsum / self._count[:, None]
        ln = np.linalg.norm(nrm, axis=1)
        good = ln > 1e-9
        nrm[good] /= ln[good, None]
        return pts, nrm, self._count.copy()


@dataclass
class Chunk:
    """A few seconds of trajectory with a subsample of its own points.

    Kept during the single fusing pass so drift correction can estimate a
    per-chunk yaw and height offset without reading every depth frame again.
    """

    t0: float
    t1: float
    frames: list[int]
    centroid: np.ndarray
    points: np.ndarray
    normals: np.ndarray


@dataclass
class Cloud:
    points: np.ndarray  # (N, 3) world metres
    normals: np.ndarray  # (N, 3) unit, oriented toward the observing camera
    counts: np.ndarray  # (N,) depth samples fused into each voxel
    camera_path: np.ndarray = field(default_factory=lambda: np.zeros((0, 3)))
    camera_times: np.ndarray = field(default_factory=lambda: np.zeros(0))
    frame_index: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.int64))
    n_frames_used: int = 0
    chunks: list["Chunk"] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.points)


def frame_points(frame: Frame, min_depth: float, max_depth: float) -> tuple[np.ndarray, np.ndarray]:
    """World points and world normals for one frame, keeping confidence 2 and the depth band."""
    mask = (frame.confidence == 2) & (frame.depth > min_depth) & (frame.depth < max_depth)
    if not mask.any():
        return np.zeros((0, 3)), np.zeros((0, 3))
    normals, valid = depth_normals(frame.depth, frame.fx, frame.fy, frame.cx, frame.cy)
    mask &= valid
    if not mask.any():
        return np.zeros((0, 3)), np.zeros((0, 3))
    pts = frame.unproject(mask)
    nrm = normals[mask] @ frame.R.T
    return pts, nrm


def build_cloud(scan: StrayScan, stride: int = 10, voxel_m: float = 0.02,
                min_depth: float = 0.2, max_depth: float = 4.5,
                pose_fn=None, batch: int = 64, chunk_s: float | None = None,
                chunk_subsample: int = 40000) -> Cloud:
    """Fuse every ``stride``-th frame into a voxel cloud.

    ``pose_fn(frame) -> (R, t)`` lets drift correction substitute corrected
    poses without re-reading the depth images.
    """
    grid = VoxelGrid(voxel_m)
    path: list[np.ndarray] = []
    times: list[float] = []
    idx: list[int] = []
    buf_p: list[np.ndarray] = []
    buf_n: list[np.ndarray] = []
    used = 0
    chunks: list[Chunk] = []
    cur_p: list[np.ndarray] = []
    cur_n: list[np.ndarray] = []
    cur_f: list[int] = []
    cur_t: list[float] = []
    cur_pos: list[np.ndarray] = []

    def close_chunk() -> None:
        if not cur_f:
            return
        pts = np.concatenate(cur_p) if cur_p else np.zeros((0, 3))
        nrm = np.concatenate(cur_n) if cur_n else np.zeros((0, 3))
        if len(pts) > chunk_subsample:
            # Deterministic thinning: every kth point, no RNG.
            step = int(np.ceil(len(pts) / chunk_subsample))
            pts, nrm = pts[::step], nrm[::step]
        chunks.append(Chunk(cur_t[0], cur_t[-1], list(cur_f), np.mean(cur_pos, axis=0), pts, nrm))
        cur_p.clear(); cur_n.clear(); cur_f.clear(); cur_t.clear(); cur_pos.clear()

    for frame in scan.frames(stride=stride):
        if pose_fn is not None:
            frame.R, frame.t = pose_fn(frame)
        p, n = frame_points(frame, min_depth, max_depth)
        if len(p):
            buf_p.append(p)
            buf_n.append(n)
        path.append(frame.t.copy())
        times.append(frame.timestamp)
        idx.append(frame.index)
        used += 1
        if chunk_s is not None:
            if cur_t and frame.timestamp - cur_t[0] > chunk_s:
                close_chunk()
            cur_f.append(frame.index)
            cur_t.append(frame.timestamp)
            cur_pos.append(frame.t.copy())
            if len(p):
                cur_p.append(p)
                cur_n.append(n)
        if len(buf_p) >= batch:
            grid.add(np.concatenate(buf_p), np.concatenate(buf_n))
            buf_p, buf_n = [], []
    if buf_p:
        grid.add(np.concatenate(buf_p), np.concatenate(buf_n))
    if chunk_s is not None:
        close_chunk()
    pts, nrm, cnt = grid.result()
    return Cloud(pts, nrm, cnt, np.array(path), np.array(times), np.array(idx, dtype=np.int64), used, chunks)
