"""Metric extent of a detection, and what to say when it cannot be measured.

With depth, the box is projected onto the wall plane. That projection is an
upper bound: the box bounds the mark, it is not the mark. A colour-contrast
mask inside the box gives the estimate, and the reported Measurement runs
between the two, which is honest about a quantity whose true edge is a matter
of judgement even with a tape in hand.

Without depth there is no scale at all, so the region is emitted with an
explicitly unbounded extent rather than a number the caller might trust.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from cozmo.contracts.models import Measurement

UNBOUNDED_METHOD = "unbounded_no_metric_depth"


@dataclass
class ExtentResult:
    measurement: Measurement | None
    bounded: bool
    upper_bound_m2: float | None = None
    estimate_m2: float | None = None
    note: str = ""


def contrast_fraction(image: np.ndarray, box: tuple[float, float, float, float]) -> float:
    """Share of the box that differs from the box's own background colour.

    A plain threshold on lightness against the box median: damage is what
    stands out from the surface it sits on. Crude, and the interval reflects
    that; its job is to give a lower estimate against the box upper bound.
    """
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    h, w = image.shape[:2]
    x0, y0 = max(x0, 0), max(y0, 0)
    x1, y1 = min(x1, w), min(y1, h)
    if x1 - x0 < 4 or y1 - y0 < 4:
        return 1.0
    patch = image[y0:y1, x0:x1]
    lab = cv2.cvtColor(patch, cv2.COLOR_RGB2LAB).astype(np.float32)
    med = np.median(lab.reshape(-1, 3), axis=0)
    dist = np.linalg.norm(lab - med, axis=-1)
    thr = max(float(np.percentile(dist, 70)), 8.0)
    frac = float((dist > thr).mean())
    return min(max(frac, 0.05), 1.0)


def box_area_m2(frame, box: tuple[float, float, float, float]) -> float | None:
    """Area of the box projected onto the surface, from depth at its centre.

    Uses the pinhole relation directly: at depth d a pixel spans d / f metres.
    Foreshortening is not corrected, so an oblique view over-reads, which
    keeps this on the upper-bound side.
    """
    if not frame.has_metric_depth:
        return None
    x0, y0, x1, y1 = box
    cx_px, cy_px = (x0 + x1) / 2, (y0 + y1) / 2
    p = frame.unproject(cx_px, cy_px)
    if p is None:
        return None
    dh, dw = frame.depth.shape
    ih, iw = frame.image.shape[:2]
    du, dv = int(round(cx_px * dw / iw)), int(round(cy_px * dh / ih))
    if not (0 <= du < dw and 0 <= dv < dh):
        return None
    d = float(frame.depth[dv, du])
    if not np.isfinite(d) or d <= 0:
        return None
    fx, fy, _, _ = frame.intrinsics
    # Box size in depth-image pixels, converted to metres at that depth.
    w_px = (x1 - x0) * dw / iw
    h_px = (y1 - y0) * dh / ih
    return float((w_px * d / fx) * (h_px * d / fy))


def estimate_extent(frame, detection, cfg: dict) -> ExtentResult:
    unc = cfg.get("uncertainty", {})
    ci_level = unc.get("ci_level", 0.95)
    upper = box_area_m2(frame, detection.box)
    if upper is None:
        return ExtentResult(
            measurement=None, bounded=False,
            note="no metric depth for this frame, so the damaged area has no scale")
    frac = contrast_fraction(frame.image, detection.box)
    estimate = upper * frac
    value = (estimate + upper) / 2
    m = Measurement(value=value, ci_low=min(estimate, value), ci_high=max(upper, value),
                    unit="m2", method="box_on_surface_upper_bound_with_contrast_mask",
                    ci_level=ci_level)
    return ExtentResult(measurement=m, bounded=True, upper_bound_m2=upper, estimate_m2=estimate,
                        note=f"contrast mask covers {frac:.0%} of the detection box")
