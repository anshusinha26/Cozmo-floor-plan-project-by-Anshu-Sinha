"""Stage 5: dense metric point cloud from monocular depth fitted to SfM points.

Depth Anything V2 Metric Indoor runs on the keyframes. Its absolute scale is
about 35% high and that is fine here: each depth map is fitted to the SfM
sparse depths of its own frame with a robust scale and shift, so only the
*shape* of the prediction survives. The sparse depths are converted to metres
first using the chunk's own scale from stage 3, which makes the fit metric.

Cross-frame consistency. A per-frame fit lets the implied scale wobble by a few
percent from frame to frame, and that wobble is what turned a wall into a fan
of parallel lines in spike 2 (4.35 cm RMS against 0.96 for LiDAR). The fix is
cheap: fit every frame in the chunk, take the median scale, pull each frame's
scale back to within a tolerance of it, then re-solve only the shift against
that frame's own sparse points. No extra network passes.

The fitted depth maps are kept, so fusing is separate from predicting. Drift
correction changes where a chunk sits, and re-fusing from the cache costs a
second instead of another pass over the network. At the decimated resolution a
cached map is under half a megabyte.

Normals come from the unprojected point map, not from a neighbourhood search in
the fused cloud, so the two faces of one wall keep opposite normals and corners
do not mix.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import numpy as np

from cozmo.lidar.cloud import Cloud, VoxelGrid
from cozmo.pipeline.video.depth_models import DepthAnythingRunner, sync
from cozmo.pipeline.video.frames import FrameSet
from cozmo.pipeline.video.sfm import SfmChunk

log = logging.getLogger(__name__)

MIN_OBSERVATIONS = 30
Transforms = dict[int, tuple[np.ndarray, np.ndarray]]


def robust_scale_shift(d: np.ndarray, z: np.ndarray, iters: int = 8) -> tuple[float, float]:
    """Huber-reweighted least squares for ``a * d + b ~ z``."""
    A = np.stack([d, np.ones_like(d)], 1)
    w = np.ones_like(d)
    ab = np.array([1.0, 0.0])
    for _ in range(iters):
        ab = np.linalg.lstsq(A * w[:, None], z * w, rcond=None)[0]
        r = A @ ab - z
        s = 1.4826 * np.median(np.abs(r - np.median(r))) + 1e-6
        w = 1.0 / np.sqrt(1.0 + (r / (1.345 * s)) ** 2)
    return float(ab[0]), float(ab[1])


def undistorted_rays(chunk: SfmChunk, width: int, height: int) -> tuple[np.ndarray, np.ndarray]:
    """Normalised, undistortion-corrected x and y per pixel for this chunk's camera.

    One shared SIMPLE_RADIAL camera per clip, so this is computed once per chunk
    and reused for every frame of it.
    """
    import cv2

    f, cx, cy = (float(chunk.cam_params[0]), float(chunk.cam_params[1]), float(chunk.cam_params[2]))
    k1 = float(chunk.cam_params[3]) if len(chunk.cam_params) > 3 else 0.0
    # COLMAP's SIMPLE_RADIAL (f, cx, cy, k) is OpenCV's pinhole with fx = fy = f
    # and only k1 non-zero.
    K = np.array([[f, 0.0, cx], [0.0, f, cy], [0.0, 0.0, 1.0]])
    dist = np.array([k1, 0.0, 0.0, 0.0], dtype=np.float64)
    u, v = np.meshgrid(np.arange(width, dtype=np.float32), np.arange(height, dtype=np.float32))
    pts = np.stack([u.ravel(), v.ravel()], 1).reshape(-1, 1, 2)
    out = cv2.undistortPoints(pts, K, dist).reshape(height, width, 2)
    return out[..., 0].astype(np.float64), out[..., 1].astype(np.float64)


def normals_from_pointmap(P: np.ndarray, z: np.ndarray, jump_frac: float = 0.05) -> tuple[np.ndarray, np.ndarray]:
    """Per-pixel normals from a camera-space point map, oriented toward the camera.

    Same construction as the LiDAR tier's ``depth_normals``, but taken from the
    already undistorted point map rather than re-derived from a pinhole, so the
    radial term reaches the normals as well as the points.
    """
    h, w = z.shape
    du = np.zeros_like(P)
    dv = np.zeros_like(P)
    du[:, 1:-1] = P[:, 2:] - P[:, :-2]
    dv[1:-1, :] = P[2:, :] - P[:-2, :]

    ok = np.zeros((h, w), dtype=bool)
    ok[1:-1, 1:-1] = True
    ok &= z > 0
    ok[:, 1:-1] &= (z[:, 2:] > 0) & (z[:, :-2] > 0)
    ok[1:-1, :] &= (z[2:, :] > 0) & (z[:-2, :] > 0)
    with np.errstate(invalid="ignore"):
        jump_u = np.zeros((h, w), dtype=bool)
        jump_v = np.zeros((h, w), dtype=bool)
        jump_u[:, 1:-1] = np.abs(z[:, 2:] - z[:, :-2]) > jump_frac * z[:, 1:-1]
        jump_v[1:-1, :] = np.abs(z[2:, :] - z[:-2, :]) > jump_frac * z[1:-1, :]
    ok &= ~(jump_u | jump_v)

    n = np.cross(du, dv)
    norm = np.linalg.norm(n, axis=-1)
    ok &= norm > 1e-12
    with np.errstate(invalid="ignore", divide="ignore"):
        n = n / norm[..., None]
    n = np.nan_to_num(n)
    n[np.einsum("ijk,ijk->ij", n, P) > 0] *= -1.0
    return n, ok


@dataclass
class Keyframe:
    chunk: int
    i: int
    zmap: np.ndarray          # (h, w) float16 metric depth, 0 where unusable


@dataclass
class DenseBuild:
    """Fitted depth maps plus everything needed to fuse them at any chunk placement."""

    keyframes: list[Keyframe]
    rays: dict[int, tuple[np.ndarray, np.ndarray]]
    chunks: list[SfmChunk]
    group: list[int]
    stats: dict = field(default_factory=dict)
    camera_up: np.ndarray = field(default_factory=lambda: np.zeros((0, 3)))

    def fuse(self, transforms: Transforms, voxel_m: float = 0.03,
             max_depth_m: float = 8.0, min_depth_m: float = 0.25,
             batch_frames: int = 8, only: set[int] | None = None) -> Cloud:
        """Unproject cached keyframes at the given chunk placements and voxelise.

        ``only`` restricts the fuse to a subset of chunks, which the drift step
        uses to read one chunk's wall directions on its own.
        """
        grid = VoxelGrid(voxel_m)
        buf_p: list[np.ndarray] = []
        buf_n: list[np.ndarray] = []
        n_points = 0

        def flush() -> None:
            nonlocal buf_p, buf_n
            if buf_p:
                grid.add(np.concatenate(buf_p), np.concatenate(buf_n))
                buf_p, buf_n = [], []

        for kf in self.keyframes:
            if only is not None and kf.chunk not in only:
                continue
            chunk = self.chunks[kf.chunk]
            R_g, t_g = transforms[kf.chunk]
            s = float(chunk.scale_m_per_unit)
            rays_x, rays_y = self.rays[kf.chunk]
            zmap = kf.zmap.astype(np.float64)
            valid = (zmap > min_depth_m) & (zmap < max_depth_m)
            zmap = np.where(valid, zmap, 0.0)
            P = np.stack([rays_x * zmap, rays_y * zmap, zmap], axis=-1)
            nrm, nok = normals_from_pointmap(P, zmap)
            keep = valid & nok
            if not keep.any():
                continue
            M = chunk.cam_from_world[kf.i]
            Rc, tc = M[:3, :3], M[:3, 3]
            Pw = (P[keep] - tc) @ Rc * s
            Nw = nrm[keep] @ Rc
            buf_p.append(Pw @ R_g.T + t_g)
            buf_n.append(Nw @ R_g.T)
            n_points += int(keep.sum())
            if len(buf_p) >= batch_frames:
                flush()
        flush()

        pts, nrm, cnt = grid.result()
        path, times, ups = self.camera_path(transforms, only)
        cloud = Cloud(points=pts, normals=nrm, counts=cnt, camera_path=path, camera_times=times,
                      frame_index=np.arange(len(path), dtype=np.int64),
                      n_frames_used=len(self.keyframes), chunks=[])
        if only is None:
            self.stats["points_before_voxel"] = n_points
            self.stats["voxels"] = int(len(pts))
            self.camera_up = ups
        return cloud

    def camera_path(self, transforms: Transforms,
                    only: set[int] | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Every registered camera of the group, in metres, plus each camera's up vector."""
        pts, times, ups = [], [], []
        for ci in (self.group if only is None else [c for c in self.group if c in only]):
            chunk = self.chunks[ci]
            R_g, t_g = transforms[ci]
            s = float(chunk.scale_m_per_unit)
            for i in range(len(chunk)):
                M = chunk.cam_from_world[i]
                c = (-M[:3, :3].T @ M[:3, 3]) * s
                pts.append(R_g @ c + t_g)
                times.append(float(chunk.times_s[i]))
                ups.append(R_g @ (-M[1, :3]))   # camera y points down in OpenCV axes
        if not pts:
            return np.zeros((0, 3)), np.zeros(0), np.zeros((0, 3))
        t = np.array(times, dtype=np.float64)
        order = np.argsort(np.where(np.isfinite(t), t, np.inf), kind="stable")
        return np.array(pts)[order], t[order], np.array(ups)[order]


def _select_keyframes(chunks: list[SfmChunk], group: list[int], max_frames: int) -> dict[int, np.ndarray]:
    """Spread the keyframe budget over the group in proportion to chunk size."""
    sizes = {i: len(chunks[i]) for i in group}
    total = sum(sizes.values())
    out: dict[int, np.ndarray] = {}
    for i in group:
        n = max(2, int(round(max_frames * sizes[i] / total))) if total else 2
        out[i] = np.unique(np.linspace(0, sizes[i] - 1, min(n, sizes[i])).round().astype(int))
    return out


def build(chunks: list[SfmChunk], group: list[int], frames: FrameSet, device: str,
          max_keyframes: int = 80, pixel_stride: int = 2, min_depth_m: float = 0.25,
          max_depth_m: float = 8.0, scale_tolerance: float = 0.08) -> DenseBuild:
    """Predict and fit a metric depth map per keyframe. No fusing happens here."""
    runner = DepthAnythingRunner(device)
    picks = _select_keyframes(chunks, group, max_keyframes)
    keyframes: list[Keyframe] = []
    rays: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    per_chunk, secs = [], []

    for ci in group:
        chunk = chunks[ci]
        s_chunk = float(chunk.scale_m_per_unit)
        maps: dict[int, np.ndarray] = {}
        fits: dict[int, tuple[float, float]] = {}
        sparse: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        for i in picks[ci]:
            i = int(i)
            t0 = time.perf_counter()
            dep, _ = runner.infer(frames.path(chunk.names[i]))
            sync(device)
            secs.append(time.perf_counter() - t0)
            uv, z = chunk.observations(i)
            h, w = dep.shape
            u = np.round(uv[:, 0]).astype(int)
            v = np.round(uv[:, 1]).astype(int)
            ok = (u >= 0) & (u < w) & (v >= 0) & (v < h)
            d = dep[v[ok], u[ok]]
            zm = z[ok] * s_chunk
            good = np.isfinite(d) & (d > 0.05) & (zm > min_depth_m)
            if good.sum() < MIN_OBSERVATIONS:
                continue
            maps[i] = dep.astype(np.float32)
            sparse[i] = (d[good], zm[good])
            fits[i] = robust_scale_shift(d[good], zm[good])
        if not fits:
            per_chunk.append({"chunk": ci, "keyframes": 0,
                              "note": "no keyframe carried enough sparse depth to fit"})
            continue

        a_med = float(np.median([a for a, _ in fits.values()]))
        lo, hi = a_med * (1 - scale_tolerance), a_med * (1 + scale_tolerance)
        n_clamped = 0
        rx, ry = undistorted_rays(chunk, frames.width, frames.height)
        rays[ci] = (rx[::pixel_stride, ::pixel_stride], ry[::pixel_stride, ::pixel_stride])
        for i, dep in maps.items():
            a, b = fits[i]
            a_new = float(np.clip(a, lo, hi))
            if a_new != a:
                n_clamped += 1
                d_good, zm_good = sparse[i]
                b = float(np.median(zm_good - a_new * d_good))
            zmap = (a_new * dep + b)[::pixel_stride, ::pixel_stride]
            zmap = np.where(np.isfinite(zmap) & (zmap > min_depth_m) & (zmap < max_depth_m), zmap, 0.0)
            keyframes.append(Keyframe(chunk=ci, i=i, zmap=zmap.astype(np.float16)))
        per_chunk.append({"chunk": ci, "keyframes": len(maps), "scale_median": round(a_med, 4),
                          "n_scale_clamped": n_clamped,
                          "chunk_scale_m_per_unit": round(s_chunk, 6)})

    stats = {"keyframes": len(keyframes), "per_chunk": per_chunk, "pixel_stride": pixel_stride,
             "sec_per_frame": round(float(np.mean(secs)), 3) if secs else None,
             "cached_depth_mb": round(sum(k.zmap.nbytes for k in keyframes) / 1e6, 1)}
    log.info("dense: %d keyframes fitted, %.1f MB of cached depth, %.2f s per frame",
             len(keyframes), stats["cached_depth_mb"], stats["sec_per_frame"] or 0.0)
    return DenseBuild(keyframes=keyframes, rays=rays, chunks=chunks, group=group, stats=stats)
