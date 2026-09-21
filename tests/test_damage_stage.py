"""The damage stage inside `cozmo run`.

Damage was reachable only through scripts, so a plan from the command line
always carried an empty list. These tests pin the wiring: what `auto` decides,
what each mode writes into the plan, and that the decision is recorded rather
than left for a reader to infer from an empty list.
"""
from __future__ import annotations

import numpy as np
import pytest

from cozmo.contracts.models import DamageClass, Plan
from cozmo.damage.detector import Detection, DummyDetector
from cozmo.damage.frames import DamageFrame
from cozmo.pipeline.damage_stage import (
    DAMAGE_OFF_WARNING,
    DamageMode,
    resolve_damage_mode,
    run_damage_stage,
)
from tests.test_registration import world_two_room_plan

CFG = {"uncertainty": {"ci_level": 0.95}}


def _plan() -> Plan:
    """The shared fixture, with any damage stripped: this stage is what puts it there."""
    return Plan.model_validate(world_two_room_plan()).model_copy(
        update={"damage_regions": [], "concealed_damage_flags": [], "scope_items": []})


def _frames():
    img = np.full((200, 300, 3), 180, dtype=np.uint8)
    img[80:120, 100:160] = 60
    depth = np.full((100, 150), 2.0, dtype=np.float32)
    for i in range(2):
        yield DamageFrame(frame_id=f"f{i}", image=img, depth=depth,
                          intrinsics=(100.0, 100.0, 75.0, 50.0), pose=np.eye(4))


def _detector():
    boxes = {
        f"f{i}": [Detection(DamageClass.water_stain.value, "a water stain on the wall",
                            0.6, (100, 80, 160, 120), f"f{i}")]
        for i in range(2)
    }
    return DummyDetector(boxes)


def test_auto_turns_damage_off_when_the_weights_are_missing() -> None:
    """Off is the safe default, but a silently empty list is indistinguishable
    from a clean room, so the plan has to say which it is."""
    assert resolve_damage_mode("auto", weights_present=False) is DamageMode.off
    assert resolve_damage_mode("auto", weights_present=True) is DamageMode.on


def test_off_records_why_the_damage_lists_are_empty() -> None:
    plan = run_damage_stage(_plan(), DamageMode.off, frames=None, detector=None, cfg=CFG,
                            reason="the damage weights are not installed")
    assert plan.damage_regions == []
    assert any(DAMAGE_OFF_WARNING in w for w in plan.warnings)
    assert any("weights are not installed" in w for w in plan.warnings)


def test_on_writes_regions_flags_and_scope_items_into_the_plan() -> None:
    plan = run_damage_stage(_plan(), DamageMode.on, frames=_frames(), detector=_detector(),
                            cfg=CFG)
    assert plan.damage_regions, "a detected region should reach the plan"
    assert all(r.surface_id for r in plan.damage_regions)
    assert plan.scope_items, "a region should produce a scope item"
    assert not any(DAMAGE_OFF_WARNING in w for w in plan.warnings)
    Plan.from_json_bytes(plan.to_json_bytes())  # round trip revalidates every reference


def test_the_same_input_gives_the_same_plan() -> None:
    a = run_damage_stage(_plan(), DamageMode.on, frames=_frames(), detector=_detector(), cfg=CFG)
    b = run_damage_stage(_plan(), DamageMode.on, frames=_frames(), detector=_detector(), cfg=CFG)
    assert a.to_json_bytes() == b.to_json_bytes()


def test_on_without_weights_is_an_error_rather_than_a_quiet_skip() -> None:
    """`--damage on` is an instruction, so failing it silently would be a lie."""
    with pytest.raises(RuntimeError, match="weights"):
        resolve_damage_mode("on", weights_present=False)
