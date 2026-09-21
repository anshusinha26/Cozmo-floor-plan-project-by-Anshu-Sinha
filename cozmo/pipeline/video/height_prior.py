"""Metric scale from the capture protocol instead of from a depth model.

Fix loop 2. The tier's only source of absolute scale was Depth Pro's depth at
the SfM sparse points, and that source is a per-chunk bias rather than noise:
the six clips of loop 1 put the camera between 0.43 m and 2.61 m above their own
reconstructed floor, where a walking person holds a phone between about 1.1 and
1.8 m up.

The camera height is the one quantity in this pipeline whose answer is known
before the capture starts, because the protocol says where to hold the phone. So
each chunk gets the scale that makes its own median camera height equal H. This
is an assumption, not a measurement, it is declared in ``plan.assumptions``, and
its uncertainty flows into every interval.

Two scales are then available per chunk, one from the prior and one from Depth
Pro. Their disagreement is evidence about how wrong the depth model was, and it
sets the interval floor: a plan can never claim to be tighter than the gap
between its two ways of measuring the same thing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from cozmo.pipeline.video.sfm import SfmChunk
from cozmo.pipeline.video.up import fit_floor

log = logging.getLogger(__name__)

DEFAULT_CAMERA_HEIGHT_M = 1.40
DEFAULT_CAMERA_HEIGHT_SIGMA_M = 0.12
MIN_FLOOR_POINTS = 200


@dataclass
class ChunkLevel:
    """A chunk standing upright on its own floor, at its own metric scale."""

    chunk: int
    scale: float
    rotation: np.ndarray          # takes the chunk's SfM frame to y-up
    translation: np.ndarray       # puts that chunk's floor at y = 0
    measured_height_m: float      # camera above its own floor, before rescaling
    floor_inlier_fraction: float
    method: str

    @property
    def transform(self) -> tuple[np.ndarray, np.ndarray]:
        return self.rotation, self.translation


@dataclass
class ChunkScale:
    """Everything known about one chunk's metre per SfM unit."""

    chunk: int
    depth_pro: float | None
    height_prior: float | None
    floor_inlier_fraction: float
    n_cameras: int
    method: str
    disagreement: float | None = None   # |prior / depth_pro - 1|

    @property
    def best(self) -> float:
        return self.height_prior if self.height_prior is not None else float(self.depth_pro)

    def summary(self) -> dict:
        return {"chunk": self.chunk,
                "depth_pro": None if self.depth_pro is None else round(self.depth_pro, 6),
                "height_prior": None if self.height_prior is None else round(self.height_prior, 6),
                "chosen": round(self.best, 6), "method": self.method,
                "floor_inlier_fraction": round(self.floor_inlier_fraction, 3),
                "n_cameras": self.n_cameras,
                "disagreement": None if self.disagreement is None else round(self.disagreement, 4)}


def chunk_cloud(build, chunk_index: int, transforms, voxel_m: float = 0.05, coarse: int = 3):
    """The chunk's own fused points and cameras, at whatever scale it currently has.

    Decimated: this is used to find a floor plane, which needs a surface's
    direction, not its detail.
    """
    return build.fuse(transforms, voxel_m=voxel_m, only={chunk_index}, coarse=coarse)


def height_prior_scale(points: np.ndarray, normals: np.ndarray, camera_path: np.ndarray,
                       camera_up: np.ndarray, current_scale: float, target_height_m: float,
                       max_tilt_deg: float = 30.0, seed: int = 0) -> tuple[float | None, float, float]:
    """Rescale so the median camera sits ``target_height_m`` above this chunk's floor.

    The cloud arrives at ``current_scale``; heights scale linearly with it, so the
    correction is a ratio. Returns (new scale, measured height at current scale,
    floor inlier fraction), and None when no floor could be fitted.
    """
    if len(points) < MIN_FLOOR_POINTS or len(camera_path) == 0:
        return None, float("nan"), 0.0
    g = fit_floor(points, normals, camera_up, max_tilt_deg=max_tilt_deg, seed=seed)
    if not g.method.startswith("ransac"):
        return None, float("nan"), g.inlier_fraction
    n = g.normal
    height = float(np.median(camera_path @ n) - g.offset_m)
    if not np.isfinite(height) or height <= 0.05:
        return None, height, g.inlier_fraction
    return float(current_scale * target_height_m / height), height, g.inlier_fraction


def level_chunks(build, chunks: list[SfmChunk], group: list[int],
                 target_height_m: float = DEFAULT_CAMERA_HEIGHT_M, max_tilt_deg: float = 30.0,
                 seed: int = 0, voxel_m: float = 0.05, coarse: int = 3
                 ) -> tuple[list[ChunkLevel], list[ChunkScale]]:
    """Stand every chunk upright on its own floor and scale it to the height prior.

    Each chunk is fused alone, so its floor plane is fitted from its own points
    rather than from a group that may be wrongly assembled. Afterwards every
    chunk is metric, y is up, and the floor is y = 0, which is what lets the
    bridge drop from a similarity to a yaw and a translation.
    """
    from cozmo.pipeline.video.up import rotation_between

    levels: list[ChunkLevel] = []
    scales: list[ChunkScale] = []
    identity = {c: (np.eye(3), np.zeros(3)) for c in group}
    for ci in group:
        chunk = chunks[ci]
        s0 = float(chunk.scale_m_per_unit)
        cloud = chunk_cloud(build, ci, identity, voxel_m=voxel_m, coarse=coarse)
        ups = build.camera_path(identity, only={ci})[2]
        if len(cloud.points) < MIN_FLOOR_POINTS or len(cloud.camera_path) == 0:
            levels.append(ChunkLevel(ci, s0, np.eye(3), np.zeros(3), float("nan"), 0.0,
                                     "depth_pro_only_too_few_points"))
            scales.append(ChunkScale(ci, s0, None, 0.0, len(cloud.camera_path),
                                     "depth_pro_only_too_few_points"))
            continue
        g = fit_floor(cloud.points, cloud.normals, ups, max_tilt_deg=max_tilt_deg, seed=seed)
        R = rotation_between(g.normal, np.array([0.0, 1.0, 0.0]))
        height = float(np.median(cloud.camera_path @ g.normal) - g.offset_m)
        usable = g.method.startswith("ransac") and np.isfinite(height) and height > 0.05
        if not usable:
            levels.append(ChunkLevel(ci, s0, R, np.array([0.0, -g.offset_m, 0.0]), height,
                                     g.inlier_fraction, "depth_pro_only_no_floor_plane"))
            scales.append(ChunkScale(ci, s0, None, g.inlier_fraction, len(cloud.camera_path),
                                     "depth_pro_only_no_floor_plane"))
            log.warning("chunk %d: no usable floor plane, keeping the Depth Pro scale %.5f", ci, s0)
            continue
        s1 = float(s0 * target_height_m / height)
        # The cloud rescales with the chunk, so the floor offset moves with it.
        t = np.array([0.0, -g.offset_m * s1 / s0, 0.0])
        levels.append(ChunkLevel(ci, s1, R, t, height, g.inlier_fraction, "camera_height_prior"))
        scales.append(ChunkScale(ci, s0, s1, g.inlier_fraction, len(cloud.camera_path),
                                 "camera_height_prior",
                                 disagreement=abs(s1 / s0 - 1.0) if s0 else None))
        log.info("chunk %d: camera sat %.2f m above its own floor, so scale %.5f becomes %.5f "
                 "for a %.2f m prior (%.0f%% change)", ci, height, s0, s1, target_height_m,
                 100 * abs(s1 / s0 - 1.0))
    return levels, scales


def apply_scales(chunks: list[SfmChunk], rows: list[ChunkScale]) -> None:
    for r in rows:
        chunks[r.chunk].scale_m_per_unit = r.best


def scale_disagreement(rows: list[ChunkScale]) -> float:
    """Median |prior / depth_pro - 1| over the chunks that have both."""
    vals = [r.disagreement for r in rows if r.disagreement is not None]
    return float(np.median(vals)) if vals else 0.0
