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
    """The shared fixture, with any damage stripped: this stage is what puts it there.

    The fixture carries wall surfaces for its first room only, so the second
    room gets one here: a room with no wall surface has nothing to attach a
    fallback region to, and these tests are about which room's wall is used.
    """
    d = world_two_room_plan()
    d["damage_regions"], d["concealed_damage_flags"], d["scope_items"] = [], [], []
    have = {s["room_id"] for s in d["surfaces"] if s["type"] == "wall"}
    for room in d["rooms"]:
        if room["id"] not in have and room["walls"]:
            d["surfaces"].append({"id": f"s_{room['id']}_w1", "room_id": room["id"], "type": "wall",
                                  "wall_id": room["walls"][0]["id"],
                                  "area_m2": {"value": 9.0, "ci_low": 8.5, "ci_high": 9.5,
                                              "unit": "m2", "method": "test"}})
    return Plan.model_validate(d)


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


def _frames_for(room_tag: str, n: int = 2):
    img = np.full((200, 300, 3), 180, dtype=np.uint8)
    img[80:120, 100:160] = 60
    for i in range(n):
        yield DamageFrame(frame_id=f"{room_tag}_f{i}", image=img)


def _detector_hitting(frame_ids):
    boxes = {fid: [Detection(DamageClass.crack.value, "a crack in the wall", 0.6,
                             (100, 80, 160, 120), fid)] for fid in frame_ids}
    return DummyDetector(boxes)


def test_a_mark_photographed_in_room_b_is_never_recorded_against_room_a() -> None:
    """Without depth a region falls back to a wall, and it must be a wall of the
    room whose photo it came from. One fallback for the whole property put every
    mark in a four-room capture on the hall."""
    from cozmo.pipeline.damage_stage import run_damage_stage_per_room

    plan = _plan()
    rooms = [r.id for r in plan.rooms]
    room_a, room_b = rooms[0], rooms[1]
    groups = {room_a: list(_frames_for("a")), room_b: list(_frames_for("b"))}
    detector = _detector_hitting(["b_f0", "b_f1"])
    out = run_damage_stage_per_room(plan, groups, detector, CFG)
    assert out.damage_regions, "the mark in room B should reach the plan"
    surfaces = {s.id: s for s in out.surfaces}
    rooms_hit = {surfaces[r.surface_id].room_id for r in out.damage_regions}
    assert rooms_hit == {room_b}
    Plan.from_json_bytes(out.to_json_bytes())


def test_per_room_ids_stay_unique_across_the_property() -> None:
    from cozmo.pipeline.damage_stage import run_damage_stage_per_room

    plan = _plan()
    rooms = [r.id for r in plan.rooms]
    groups = {rooms[0]: list(_frames_for("a")), rooms[1]: list(_frames_for("b"))}
    detector = _detector_hitting(["a_f0", "a_f1", "b_f0", "b_f1"])
    out = run_damage_stage_per_room(plan, groups, detector, CFG)
    ids = [r.id for r in out.damage_regions]
    assert len(ids) == len(set(ids)) and len(ids) >= 2
    referenced = {d for s in out.scope_items for d in s.damage_region_ids}
    assert referenced <= set(ids)
    Plan.from_json_bytes(out.to_json_bytes())


def test_per_room_stage_is_deterministic() -> None:
    from cozmo.pipeline.damage_stage import run_damage_stage_per_room

    def run():
        plan = _plan()
        rooms = [r.id for r in plan.rooms]
        groups = {rooms[0]: list(_frames_for("a")), rooms[1]: list(_frames_for("b"))}
        return run_damage_stage_per_room(plan, groups, _detector_hitting(["a_f0", "a_f1", "b_f1"]), CFG)

    assert run().to_json_bytes() == run().to_json_bytes()
