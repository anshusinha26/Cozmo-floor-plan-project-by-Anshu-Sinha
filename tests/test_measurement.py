"""Measurement is the only way a dimension may appear in output.

These tests pin the invariants the rest of the harness relies on: the interval
must bracket the value, and non-finite numbers are rejected so a NaN can never
be reported as a confident measurement.
"""

import math

import pytest
from pydantic import ValidationError

from cozmo.contracts.models import Measurement


def test_valid_measurement_keeps_fields():
    m = Measurement(value=4.2, ci_low=4.0, ci_high=4.4, unit="m", method="tape")
    assert m.value == 4.2
    assert m.ci_low == 4.0
    assert m.ci_high == 4.4
    assert m.unit == "m"
    assert m.method == "tape"
    assert m.ci_level == 0.95


def test_value_equal_to_bounds_is_allowed():
    m = Measurement(value=1.0, ci_low=1.0, ci_high=1.0, unit="m", method="exact")
    assert m.width == 0.0


def test_ci_low_above_value_rejected():
    with pytest.raises(ValidationError):
        Measurement(value=4.2, ci_low=4.3, ci_high=4.4, unit="m", method="x")


def test_ci_high_below_value_rejected():
    with pytest.raises(ValidationError):
        Measurement(value=4.2, ci_low=4.0, ci_high=4.1, unit="m", method="x")


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
@pytest.mark.parametrize("field", ["value", "ci_low", "ci_high"])
def test_non_finite_rejected(field, bad):
    kwargs = dict(value=1.0, ci_low=0.5, ci_high=1.5, unit="m", method="x")
    kwargs[field] = bad
    with pytest.raises(ValidationError):
        Measurement(**kwargs)


def test_unknown_unit_rejected():
    with pytest.raises(ValidationError):
        Measurement(value=1.0, ci_low=0.5, ci_high=1.5, unit="cm", method="x")


@pytest.mark.parametrize("level", [0.0, 1.0, 1.5, -0.1])
def test_ci_level_must_be_strictly_between_0_and_1(level):
    with pytest.raises(ValidationError):
        Measurement(value=1.0, ci_low=0.5, ci_high=1.5, unit="m", method="x", ci_level=level)


def test_extra_fields_rejected():
    with pytest.raises(ValidationError):
        Measurement(value=1.0, ci_low=0.5, ci_high=1.5, unit="m", method="x", sigma=0.1)


def test_width_and_contains():
    m = Measurement(value=2.0, ci_low=1.5, ci_high=2.5, unit="m", method="x")
    assert m.width == pytest.approx(1.0)
    assert m.contains(1.5)
    assert m.contains(2.5)
    assert not m.contains(2.51)
