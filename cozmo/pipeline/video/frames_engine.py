"""Iteration 2: reconstruct a clip the way the photo tier reconstructs a room.

The first iteration of fix loop 2 showed that the scale cue is no longer what
limits this tier. On the same rooms, with the same camera-height prior and the
same single-room fitter, nine stills through MapAnything gave wall errors around
1% while fifty seconds of video through COLMAP gave 53% and 66%. The difference
is what builds the geometry.

So this engine decodes the clip, takes a spread of sharp frames across it, and
hands them to the photo tier's room reconstruction. Only the video file is read,
so tier isolation is unchanged, and the SfM engine stays selectable for the case
it is still needed: a walk through a whole property, which this engine would
reconstruct as one space.
"""

from __future__ import annotations

import logging

import numpy as np

log = logging.getLogger(__name__)

DEFAULT_FRAMES = 16
MAX_FRAMES = 24


def select_spread_frames(blur_scores: np.ndarray, n: int = DEFAULT_FRAMES,
                         max_frames: int = MAX_FRAMES, min_gap_fraction: float = 0.4) -> list[int]:
    """``n`` sharp frames spread across the clip, no two of them near neighbours.

    Sharpness alone would cluster on whatever part of the clip was held
    steadiest, and a reconstruction needs views that differ. So the clip is cut
    into equal windows and the sharpest frame in each is taken, with a minimum
    spacing enforced so a window's pick cannot sit next to the previous one's.
    """
    total = len(blur_scores)
    n = int(min(max(n, 2), max_frames, total))
    if total <= n:
        return list(range(total))
    edges = np.linspace(0, total, n + 1).round().astype(int)
    min_gap = max(1, int(min_gap_fraction * total / n))
    picks: list[int] = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        window = list(range(int(lo), int(hi)))
        if not window:
            continue
        for idx in sorted(window, key=lambda i: -blur_scores[i]):
            if not picks or idx - picks[-1] >= min_gap:
                picks.append(idx)
                break
        else:
            picks.append(max(window, key=lambda i: blur_scores[i]))
    out = sorted(set(picks))
    log.info("frames engine: %d frames chosen from %d, median sharpness %.1f against %.1f overall",
             len(out), total, float(np.median(blur_scores[out])), float(np.median(blur_scores)))
    return out


WHOLE_PROPERTY_WARNING = (
    "This clip was reconstructed as one space. The frames engine builds a single room from a "
    "single clip, so a walk through several rooms comes out as one room covering all of them. "
    "Capture one clip per room, or run this capture with --video-engine sfm"
)
