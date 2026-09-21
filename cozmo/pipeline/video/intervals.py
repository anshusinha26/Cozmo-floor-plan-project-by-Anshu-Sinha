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
    height_prior: float = 0.0
    scale_sem: float = 0.0
    chunk_spread: float = 0.0
    coverage: float = 1.0
    min_coverage: float = MIN_COVERAGE
    low_coverage_factor: float = LOW_COVERAGE_FACTOR
    abs_floor_m: float = ABS_FLOOR_M
    unsupported_sides: int = 0
    notes: list[str] = field(default_factory=list)

    def with_unsupported_sides(self, n: int) -> "IntervalBudget":
        """A room side closed by assumption is not a measured side."""
        out = IntervalBudget(**{k: v for k, v in self.__dict__.items() if k != "unsupported_sides"})
        out.unsupported_sides = int(n)
        return out

    @property
    def widened(self) -> bool:
        return self.coverage < self.min_coverage

    @property
    def factor(self) -> float:
        f = self.low_coverage_factor if self.widened else 1.0
        # Each side closed by the rectangle assumption rather than measured adds
        # a quarter again to every interval in the room.
        return f * (1.0 + 0.25 * self.unsupported_sides)

    @property
    def effective_bias(self) -> float:
        """The number that goes into the backend as ``depth_scale_bias``."""
        # Fix loop 2: the per-frame standard error understated the real scale
        # error tenfold, so the scale term is the larger of the height prior's
        # own uncertainty and how far the two scale methods ended up apart.
        scale_term = max(self.height_prior, self.scale_sem)
        base = np.sqrt(self.systematic ** 2 + scale_term ** 2 + self.chunk_spread ** 2)
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
                "height_prior": round(self.height_prior, 4),
                "scale_sem": round(self.scale_sem, 4),
                "unsupported_sides": self.unsupported_sides,
                "chunk_spread": round(self.chunk_spread, 4),
                "coverage": round(self.coverage, 4),
                "min_coverage": self.min_coverage,
                "widened": self.widened,
                "widening_factor": round(self.factor, 3),
                "effective_depth_scale_bias": round(self.effective_bias, 4),
                "abs_floor_m": round(max(self.abs_floor_m * self.factor, 0.0), 4)}


def build_budget(scale_rows: list[dict], group: list[int], coverage: float, cfg: dict,
                 height_prior_rel: float = 0.0, method_disagreement: float = 0.0) -> IntervalBudget:
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
    # Fix loop 2: the scale term is the larger of the prior's own uncertainty and
    # how far the prior and the depth model ended up apart, never the per-frame
    # spread on its own.
    if method_disagreement:
        notes.append(f"The camera-height prior and the monocular depth scale disagree by "
                     f"{method_disagreement:.0%} on this capture; the wider of that and the "
                     f"prior's own uncertainty sets the scale term in every interval")
    return IntervalBudget(
        systematic=float(unc.get("systematic_scale_bias", SYSTEMATIC_SCALE_BIAS)),
        height_prior=float(max(height_prior_rel, method_disagreement)),
        scale_sem=sem, chunk_spread=spread, coverage=float(coverage),
        min_coverage=float(unc.get("min_coverage", MIN_COVERAGE)),
        low_coverage_factor=float(unc.get("low_coverage_factor", LOW_COVERAGE_FACTOR)),
        abs_floor_m=float(unc.get("abs_floor_m", ABS_FLOOR_M)), notes=notes)


# --------------------------------------------------------------------------
# Interval sanity
# --------------------------------------------------------------------------

MIN_POSITIVE_M = 0.01
UNRELIABLE = ("{what} is reported with an interval wider than the value itself "
              "({value:.2f} {unit}, plus or minus {half:.2f}). It is an unreliable measurement: "
              "the reconstruction constrains it barely or not at all")


def _clamp_measurement(m, what: str, warnings: list[str]):
    """No length or area may have a negative bound, and a value swamped by its
    own interval has to say so.

    Fix loop 2 produced wall lengths reported as 318 cm with a lower bound of
    minus 685. A negative wall is not a bound, it is a sign the interval machinery
    was asked for a number it did not have, and printing it invites the reader to
    average two nonsenses into a false sense of a range.
    """
    if m is None or m.unit not in ("m", "m2"):
        return m
    lo = max(m.ci_low, MIN_POSITIVE_M if m.value > 0 else 0.0)
    hi = max(m.ci_high, lo)
    half = (hi - lo) / 2
    if half >= abs(m.value) and m.value > 0:
        warnings.append(UNRELIABLE.format(what=what, value=m.value, unit=m.unit, half=half))
    if lo == m.ci_low and hi == m.ci_high:
        return m
    return m.model_copy(update={"ci_low": lo, "ci_high": hi})


def clamp_plan_intervals(plan, warnings: list[str]):
    """Walk every measurement in a plan, clamp the impossible ones, warn on the
    ones too wide to mean anything. Returns the plan with the warnings added."""
    notes: list[str] = []
    rooms = []
    for room in plan.rooms:
        walls = [w.model_copy(update={
            "length_m": _clamp_measurement(w.length_m, f"{room.id} {w.id} length", notes),
            "height_m": _clamp_measurement(w.height_m, f"{room.id} {w.id} height", notes)})
            for w in room.walls]
        openings = [o.model_copy(update={
            "width_m": _clamp_measurement(o.width_m, f"{o.id} width", notes),
            "height_m": _clamp_measurement(o.height_m, f"{o.id} height", notes),
            "offset_along_wall_m": _clamp_measurement(o.offset_along_wall_m, f"{o.id} offset", notes)})
            for o in room.openings]
        rooms.append(room.model_copy(update={
            "walls": walls, "openings": openings,
            "ceiling_height_m": _clamp_measurement(room.ceiling_height_m,
                                                   f"{room.id} ceiling height", notes),
            "floor_area_m2": _clamp_measurement(room.floor_area_m2, f"{room.id} floor area", notes)}))
    surfaces = [s.model_copy(update={"area_m2": _clamp_measurement(s.area_m2, f"{s.id} area", notes)})
                for s in plan.surfaces]
    st = plan.stitched_plan
    stitched = st.model_copy(update={
        "footprint_area_m2": _clamp_measurement(st.footprint_area_m2, "footprint area", notes),
        "overlap_area_m2": st.overlap_area_m2})
    seen: set[str] = set()
    unique = [n for n in notes if not (n in seen or seen.add(n))]
    return plan.model_copy(update={"rooms": rooms, "surfaces": surfaces,
                                   "stitched_plan": stitched,
                                   "warnings": list(plan.warnings) + list(warnings) + unique})
