"""Calibration of stated intervals against ground truth.

Scored separately from accuracy because a pipeline can be wrong and honest
(wide interval that covers the truth) or wrong and confident. The second is
what "confident garbage" counts: truth outside the interval AND the interval
narrower than the median for that quantity type. The median is per quantity
because widths in m2 and widths in m are not comparable.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import median
from typing import Any

from cozmo.contracts.models import Measurement


@dataclass
class CalItem:
    tier: str
    quantity: str  # wall_length, ceiling_height, opening_width, opening_height, floor_area, footprint_area, ...
    pred: Measurement
    truth: float


def _median_width_by_quantity(items: list[CalItem]) -> dict[str, float]:
    widths: dict[str, list[float]] = defaultdict(list)
    for it in items:
        widths[it.quantity].append(it.pred.width)
    return {q: median(w) for q, w in widths.items()}


def summarize(items: list[CalItem], median_width: dict[str, float] | None = None) -> dict[str, Any]:
    """One calibration row. ``median_width`` lets a sub-group use the global per-quantity median."""
    if not items:
        return {"n": 0, "coverage": None, "mean_width_pct": None, "outside": 0, "confident_garbage": 0,
                "nominal_level": None}
    med = median_width or _median_width_by_quantity(items)
    inside = sum(1 for it in items if it.pred.contains(it.truth))
    outside = len(items) - inside
    garbage = sum(
        1 for it in items if not it.pred.contains(it.truth) and it.pred.width < med[it.quantity]
    )
    pct = [it.pred.width / abs(it.pred.value) * 100.0 for it in items if it.pred.value]
    return {
        "n": len(items),
        "coverage": inside / len(items),
        "mean_width_pct": sum(pct) / len(pct) if pct else None,
        "outside": outside,
        "confident_garbage": garbage,
        "nominal_level": sorted({it.pred.ci_level for it in items}),
    }


def calibration_table(items: list[CalItem]) -> dict[str, Any]:
    med = _median_width_by_quantity(items)
    by_tier: dict[str, list[CalItem]] = defaultdict(list)
    by_q: dict[str, list[CalItem]] = defaultdict(list)
    by_tq: dict[str, list[CalItem]] = defaultdict(list)
    for it in items:
        by_tier[it.tier].append(it)
        by_q[it.quantity].append(it)
        by_tq[f"{it.tier}/{it.quantity}"].append(it)
    return {
        "overall": summarize(items, med),
        "by_tier": {k: summarize(v, med) for k, v in sorted(by_tier.items())},
        "by_quantity": {k: summarize(v, med) for k, v in sorted(by_q.items())},
        "by_tier_quantity": {k: summarize(v, med) for k, v in sorted(by_tq.items())},
        "median_width_by_quantity": med,
    }
