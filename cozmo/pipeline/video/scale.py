"""Stage 3: metres per SfM unit, per chunk, with no depth sensor.

For a handful of frames in the chunk, run Depth Pro with the focal length
COLMAP estimated, read the metric depth at each sparse observation, and take
the median of metric over SfM depth. The chunk scale is the median of those
per-frame medians.

The per-frame spread is kept, not thrown away: it is the only direct evidence
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


def estimate_chunk_scale(chunk: SfmChunk, frames: FrameSet, runner: DepthProRunner,
                         max_frames: int = 12) -> dict:
    """Set ``chunk.scale_m_per_unit`` and keep the per-frame ratios."""
    pick = np.unique(np.linspace(0, len(chunk) - 1, min(max_frames, len(chunk))).round().astype(int))
    ratios, used, secs = [], [], []
    for i in pick:
        i = int(i)
        t0 = time.perf_counter()
        depth_m, _ = runner.infer(frames.path(chunk.names[i]), focal_px=chunk.focal_px)
        sync(str(runner.device.type))
        secs.append(time.perf_counter() - t0)
        uv, z = chunk.observations(i)
        r = _frame_ratio(depth_m, uv, z)
        if r is not None:
            ratios.append(r)
            used.append(chunk.names[i])
    if not ratios:
        raise ScaleError(f"chunk {chunk.index}: no frame had {MIN_OBSERVATIONS} usable sparse observations")
    arr = np.array(ratios)
    chunk.scale_m_per_unit = float(np.median(arr))
    chunk.scale_frame_ratios = arr
    rel_sd = float(arr.std(ddof=1) / chunk.scale_m_per_unit) if len(arr) > 1 else float("nan")
    out = {"chunk": chunk.index, "n_images": len(chunk), "n_scale_frames": len(arr),
           "focal_px": round(chunk.focal_px, 2),
           "scale_m_per_unit": round(chunk.scale_m_per_unit, 6),
           "scale_rel_sd": None if np.isnan(rel_sd) else round(rel_sd, 4),
           "sec_per_frame": round(float(np.mean(secs)), 3)}
    log.info("chunk %d: scale %.5f m per SfM unit from %d frames, relative sd %s",
             chunk.index, chunk.scale_m_per_unit, len(arr),
             "n/a" if np.isnan(rel_sd) else f"{rel_sd:.1%}")
    return out


def estimate_scales(chunks: list[SfmChunk], frames: FrameSet, device: str,
                    max_frames: int = 12) -> list[dict]:
    runner = DepthProRunner(device)
    return [estimate_chunk_scale(c, frames, runner, max_frames) for c in chunks]
