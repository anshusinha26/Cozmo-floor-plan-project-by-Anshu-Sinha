"""Output contract for a Cozmo plan.

Every model here is a pydantic v2 model with ``extra="forbid"`` so an unknown
key is a hard error rather than silently ignored. The contract is versioned via
``SCHEMA_VERSION`` and published as JSON Schema by ``cozmo schema``.

Design rule for the whole codebase: no dimension is ever a bare float. Anything
with a physical unit is a :class:`Measurement` carrying a confidence interval,
because the harness scores calibration and a bare number has no interval to
score.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "1.0.0"

Unit = Literal["m", "m2", "deg"]


class _Strict(BaseModel):
    """Shared config: forbid unknown keys, reject NaN and inf everywhere."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Measurement(_Strict):
    """A value with a calibrated confidence interval.

    ``ci_low <= value <= ci_high`` is enforced so an interval can never exclude
    its own point estimate. ``ci_level`` is the nominal coverage of the
    interval; the evaluation harness compares it to empirical coverage.
    """

    value: float
    ci_low: float
    ci_high: float
    unit: Unit
    method: str = Field(description="How the value was obtained, e.g. scale_from_door_prior")
    ci_level: float = Field(default=0.95, gt=0.0, lt=1.0)

    @model_validator(mode="after")
    def _interval_brackets_value(self) -> "Measurement":
        if not (self.ci_low <= self.value <= self.ci_high):
            raise ValueError(
                f"interval [{self.ci_low}, {self.ci_high}] must bracket value {self.value}"
            )
        return self

    @property
    def width(self) -> float:
        return self.ci_high - self.ci_low

    def contains(self, truth: float) -> bool:
        """True when a ground-truth value lies inside the stated interval (inclusive)."""
        return self.ci_low <= truth <= self.ci_high
