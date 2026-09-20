"""Where every interval in a video-tier plan comes from.

The LiDAR tier's uncertainty model has a statistical part (how well each wall
face's position is known, which the face residual already carries) and a
systematic part, a depth scale bias that scales with the measured length. This
tier reuses that machinery and replaces the systematic part, because its scale
comes from somewhere else entirely.

Three terms combine in quadrature into one effective scale bias:

* **Systematic, 3%.** Spike 2 measured the LiDAR-free scale to 1.1% on
  c00a170fe1 and 1.3% on c7d28f72c6. The tier claims 3%, wider than either
  measurement, and stays there until it is calibrated against tape. Two scans
  of one device do not earn a tight claim.
* **Measured scale spread.** Stage 3 takes the median of per-frame scale ratios
  in each chunk. The standard error of that median, about 1.25 sigma over the
  square root of the frame count, is a direct read-out of how much the depth
  model disagreed with itself on this particular capture. On close-range
  handheld room loops it is large, and it should be.
* **Chunk disagreement.** When a group holds several chunks, each brings its own
  scale. Their spread about the group median is error that no single number
  removes.

On top of that, coverage. If less than ``min_coverage`` of the video reached the
output, every interval is multiplied by ``low_coverage_factor`` and the plan
carries a warning. A plan built from a third of a room is not entitled to the
same interval as one built from all of it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

SYSTEMATIC_SCALE_BIAS = 0.03
MIN_COVERAGE = 0.60
LOW_COVERAGE_FACTOR = 1.6
ABS_FLOOR_M = 0.03


@dataclass
class IntervalBudget:
    systematic: float = SYSTEMATIC_SCALE_BIAS
    scale_sem: float = 0.0
    chunk_spread: float = 0.0
    coverage: float = 1.0
    min_coverage: float = MIN_COVERAGE
    low_coverage_factor: float = LOW_COVERAGE_FACTOR
    abs_floor_m: float = ABS_FLOOR_M
    notes: list[str] = field(default_factory=list)

    @property
    def widened(self) -> bool:
        return self.coverage < self.min_coverage

    @property
    def factor(self) -> float:
        return self.low_coverage_factor if self.widened else 1.0

    @property
    def effective_bias(self) -> float:
        """The number that goes into the backend as ``depth_scale_bias``."""
        base = np.sqrt(self.systematic ** 2 + self.scale_sem ** 2 + self.chunk_spread ** 2)
        return float(base * self.factor)

    def apply(self, uncertainty: dict) -> dict:
        out = dict(uncertainty)
        out["depth_scale_bias"] = self.effective_bias
        out["abs_floor_m"] = max(float(uncertainty.get("abs_floor_m", 0.0)),
                                 self.abs_floor_m * self.factor)
        return out

    def warnings(self) -> list[str]:
        w = list(self.notes)
        if self.widened:
            w.append(
                f"Only {self.coverage:.0%} of the video reached the output, under the "
                f"{self.min_coverage:.0%} this tier expects; every interval is widened by "
                f"{self.low_coverage_factor:.1f}x and the plan should be read as a fragment")
        return w

    def summary(self) -> dict:
        return {"systematic": round(self.systematic, 4),
                "scale_sem": round(self.scale_sem, 4),
                "chunk_spread": round(self.chunk_spread, 4),
                "coverage": round(self.coverage, 4),
                "min_coverage": self.min_coverage,
                "widened": self.widened,
                "widening_factor": round(self.factor, 3),
                "effective_depth_scale_bias": round(self.effective_bias, 4),
                "abs_floor_m": round(max(self.abs_floor_m * self.factor, 0.0), 4)}


def build_budget(scale_rows: list[dict], group: list[int], coverage: float, cfg: dict) -> IntervalBudget:
    """Combine the measured scale evidence for the chunks that reached the output."""
    unc = cfg.get("uncertainty", {})
    rows = [r for r in scale_rows if r["chunk"] in group]
    sems = [r["scale_rel_sem"] for r in rows if r.get("scale_rel_sem") is not None]
    scales = [r["scale_m_per_unit"] for r in rows if r.get("scale_m_per_unit")]
    # Weight the group's scale standard errors by chunk size: a 15 frame chunk
    # should not set the interval for a 120 frame one.
    weights = np.array([r["n_images"] for r in rows if r.get("scale_rel_sem") is not None], dtype=float)
    sem = float(np.average(sems, weights=weights)) if sems and weights.sum() else 0.0
    if len(scales) > 1:
        med = float(np.median(scales))
        spread = float(1.4826 * np.median(np.abs(np.array(scales) - med)) / med) if med else 0.0
    else:
        spread = 0.0
    notes = []
    if sem > 0.05:
        notes.append(f"Monocular depth disagreed with itself across frames on this capture: the "
                     f"weighted standard error of the per-chunk scale is {sem:.1%}, which is "
                     f"carried into every interval")
    return IntervalBudget(
        systematic=float(unc.get("systematic_scale_bias", SYSTEMATIC_SCALE_BIAS)),
        scale_sem=sem, chunk_spread=spread, coverage=float(coverage),
        min_coverage=float(unc.get("min_coverage", MIN_COVERAGE)),
        low_coverage_factor=float(unc.get("low_coverage_factor", LOW_COVERAGE_FACTOR)),
        abs_floor_m=float(unc.get("abs_floor_m", ABS_FLOOR_M)), notes=notes)
