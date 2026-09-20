"""Stage 3: metres per SfM unit, per chunk, with no depth sensor.

For a handful of frames in the chunk, run Depth Pro with the focal length
COLMAP estimated, read the metric depth at each sparse observation, and take
the median of metric over SfM depth. The chunk scale is the median of those
per-frame medians.

Frame choice matters more than it did in the spike. On the sample scans the
per-frame ratios agreed to about 6%; on close-range handheld room loops they
disagree by a factor of five, and a cross-check against Depth Anything V2 on
the same frames put the correlation of the two models' log ratios at 0.18. Two
independent models drifting in uncorrelated directions means the SfM chunk is
self-consistent and each depth model is independently unreliable on this
content: near, glossy, textureless surfaces give a monocular model almost
nothing to work with. So candidates are ranked by how much a depth model has to
go on, using SfM data only and therefore for free: how many sparse points the
frame carries and how wide a depth range they span.

The per-frame spread is kept, not thrown away. It is the only direct evidence
this tier has about how well its own scale is known, and it feeds the reported
intervals alongside the documented systematic term.
"""

from __future__ import annotations

import logging
import time

import numpy as np

from cozmo.pipeline.video.depth_models import DepthProRunner, sync
from cozmo.pipeline.video.frames import FrameSet
from cozmo.pipeline.video.sfm import SfmChunk

log = logging.getLogger(__name__)

MIN_OBSERVATIONS = 30


class ScaleError(RuntimeError):
    pass


def frame_conditioning(chunk: SfmChunk, i: int, width: int, height: int) -> tuple[int, float]:
    """(usable observations, depth diversity) for one frame, from SfM alone.

    Depth diversity is the 90th over the 10th percentile of sparse depth. A
    frame filled by one flat surface scores near 1 and tells a monocular model
    nothing about absolute distance.
    """
    uv, z = chunk.observations(i)
    if len(z) == 0:
        return 0, 1.0
    u = np.round(uv[:, 0]).astype(int)
    v = np.round(uv[:, 1]).astype(int)
    ok = (u >= 0) & (u < width) & (v >= 0) & (v < height) & (z > 0.05)
    if ok.sum() < MIN_OBSERVATIONS:
        return int(ok.sum()), 1.0
    zs = z[ok]
    lo = float(np.percentile(zs, 10))
    return int(ok.sum()), float(np.percentile(zs, 90) / lo) if lo > 0 else 1.0


def rank_frames(chunk: SfmChunk, width: int, height: int, n_wanted: int,
                pool_factor: int = 2) -> list[int]:
    """Evenly spaced candidates, then the best conditioned ``n_wanted`` of them."""
    n_pool = min(len(chunk), max(n_wanted * pool_factor, n_wanted))
    pool = np.unique(np.linspace(0, len(chunk) - 1, n_pool).round().astype(int))
    scored = []
    for i in pool:
        i = int(i)
        n_obs, div = frame_conditioning(chunk, i, width, height)
        if n_obs < MIN_OBSERVATIONS:
            continue
        # Both terms matter and both saturate, so use the product of their logs.
        scored.append((np.log1p(n_obs) * np.log(max(div, 1.01)), i))
    if not scored:
        return [int(i) for i in pool[:n_wanted]]
    scored.sort(reverse=True)
    return sorted(i for _, i in scored[:n_wanted])


def _frame_ratio(depth_m: np.ndarray, uv: np.ndarray, z_sfm: np.ndarray) -> float | None:
    """Median of metric depth over SfM depth at this frame's sparse points."""
    h, w = depth_m.shape
    u = np.round(uv[:, 0]).astype(int)
    v = np.round(uv[:, 1]).astype(int)
    ok = (u >= 0) & (u < w) & (v >= 0) & (v < h)
    if ok.sum() < MIN_OBSERVATIONS:
        return None
    d = depth_m[v[ok], u[ok]]
    z = z_sfm[ok]
    good = np.isfinite(d) & (d > 0.05) & (z > 0.05)
    if good.sum() < MIN_OBSERVATIONS:
        return None
    return float(np.median(d[good] / z[good]))


def relative_spread(ratios: np.ndarray) -> float:
    """Robust relative spread of the per-frame ratios: MAD over the median."""
    if len(ratios) < 2:
        return float("nan")
    med = float(np.median(ratios))
    if med <= 0:
        return float("nan")
    return float(1.4826 * np.median(np.abs(ratios - med)) / med)


def estimate_chunk_scale(chunk: SfmChunk, frames: FrameSet, runner: DepthProRunner,
                         max_frames: int = 12) -> dict:
    """Set ``chunk.scale_m_per_unit`` and keep the per-frame ratios."""
    pick = rank_frames(chunk, frames.width, frames.height, min(max_frames, len(chunk)))
    ratios, secs = [], []
    for i in pick:
        t0 = time.perf_counter()
        depth_m, _ = runner.infer(frames.path(chunk.names[i]), focal_px=chunk.focal_px)
        sync(runner.device.type)
        secs.append(time.perf_counter() - t0)
        uv, z = chunk.observations(i)
        r = _frame_ratio(depth_m, uv, z)
        if r is not None:
            ratios.append(r)
    if not ratios:
        raise ScaleError(f"chunk {chunk.index}: no frame had {MIN_OBSERVATIONS} usable sparse observations")
    arr = np.array(ratios)
    chunk.scale_m_per_unit = float(np.median(arr))
    chunk.scale_frame_ratios = arr
    spread = relative_spread(arr)
    # Standard error of a median is about 1.25 sigma / sqrt(n).
    sem = 1.2533 * spread / np.sqrt(len(arr)) if np.isfinite(spread) else float("nan")
    out = {"chunk": chunk.index, "n_images": len(chunk), "n_scale_frames": len(arr),
           "focal_px": round(chunk.focal_px, 2),
           "scale_m_per_unit": round(chunk.scale_m_per_unit, 6),
           "scale_rel_spread": None if np.isnan(spread) else round(spread, 4),
           "scale_rel_sem": None if np.isnan(sem) else round(float(sem), 4),
           "ratio_min": round(float(arr.min()), 6), "ratio_max": round(float(arr.max()), 6),
           "sec_per_frame": round(float(np.mean(secs)), 3)}
    log.info("chunk %d: scale %.5f m per SfM unit from %d frames, relative spread %s",
             chunk.index, chunk.scale_m_per_unit, len(arr),
             "n/a" if np.isnan(spread) else f"{spread:.1%}")
    return out


def estimate_scales(chunks: list[SfmChunk], frames: FrameSet, device: str,
                    max_frames: int = 12) -> list[dict]:
    runner = DepthProRunner(device)
    return [estimate_chunk_scale(c, frames, runner, max_frames) for c in chunks]
