"""Damage module: extent, merging, rules, scope items. No model weights needed."""

from __future__ import annotations

import numpy as np
import pytest

from cozmo.contracts.models import DamageClass, Plan
from cozmo.damage.detector import Detection, DummyDetector
from cozmo.damage.extent import UNBOUNDED_METHOD, box_area_m2, contrast_fraction, estimate_extent
from cozmo.damage.frames import DamageFrame
from cozmo.damage.pipeline import analyse_damage
from cozmo.damage.rules import RULES, scope_for
from tests.test_registration import world_two_room_plan

CFG = {"uncertainty": {"ci_level": 0.95}}


def _plan() -> Plan:
    return Plan.model_validate(world_two_room_plan())


def _frame(frame_id="f0", with_depth=True, depth_value=2.0):
    img = np.full((200, 300, 3), 180, dtype=np.uint8)
    img[80:120, 100:160] = 60  # a dark patch to give the contrast mask something
    if not with_depth:
        return DamageFrame(frame_id=frame_id, image=img)
    depth = np.full((100, 150), depth_value, dtype=np.float32)
    pose = np.eye(4)
    return DamageFrame(frame_id=frame_id, image=img, depth=depth,
                       intrinsics=(100.0, 100.0, 75.0, 50.0), pose=pose)


def test_box_area_uses_the_pinhole_relation():
    f = _frame(depth_value=2.0)
    # A 60 x 40 image-pixel box is 30 x 20 depth pixels. At fx 100 and 2 m
    # that is 0.6 m x 0.4 m, so 0.24 m2.
    area = box_area_m2(f, (100, 80, 160, 120))
    assert area == pytest.approx(0.24, rel=0.02)
    assert box_area_m2(f, (100, 80, 160, 120)) > box_area_m2(_frame(depth_value=1.0), (100, 80, 160, 120))


def test_extent_interval_runs_from_mask_estimate_to_box_upper_bound():
    f = _frame()
    det = Detection(DamageClass.water_stain.value, "a water stain on the wall", 0.5, (100, 80, 160, 120), "f0")
    r = estimate_extent(f, det, CFG)
    assert r.bounded
    assert r.measurement.ci_low <= r.measurement.value <= r.measurement.ci_high
    assert r.measurement.ci_high == pytest.approx(r.upper_bound_m2, rel=1e-6)
    assert r.estimate_m2 <= r.upper_bound_m2


def test_without_depth_the_extent_is_unbounded_and_says_so():
    f = _frame(with_depth=False)
    det = Detection(DamageClass.crack.value, "a crack in the wall", 0.4, (10, 10, 60, 60), "f0")
    r = estimate_extent(f, det, CFG)
    assert not r.bounded and r.measurement is None and "no metric depth" in r.note

    plan = _plan()
    dets = {"f0": [det]}
    res = analyse_damage([f], plan, DummyDetector(dets), CFG, fallback_surface_id=plan.surfaces[0].id)
    assert len(res.regions) == 1
    assert res.regions[0].extent_m2.method == UNBOUNDED_METHOD
    assert res.regions[0].extent_m2.ci_high >= 4.0
    assert any("unbounded" in w for w in res.warnings)


def test_contrast_fraction_is_between_zero_and_one():
    img = np.full((60, 60, 3), 200, dtype=np.uint8)
    img[20:40, 20:40] = 20
    assert 0.0 < contrast_fraction(img, (0, 0, 60, 60)) <= 1.0
    flat = np.full((60, 60, 3), 200, dtype=np.uint8)
    assert contrast_fraction(flat, (0, 0, 60, 60)) <= 1.0


def test_the_same_mark_seen_twice_becomes_one_region():
    plan = _plan()
    box = (100, 80, 160, 120)
    dets = {
        "f0": [Detection(DamageClass.water_stain.value, "p", 0.4, box, "f0")],
        "f1": [Detection(DamageClass.water_stain.value, "p", 0.5, box, "f1")],
    }
    frames = [_frame("f0"), _frame("f1")]
    res = analyse_damage(frames, plan, DummyDetector(dets), CFG, fallback_surface_id=plan.surfaces[0].id)
    assert res.detections == 2 and res.merged == 1
    assert res.regions[0].confidence > 0.5  # agreement across frames nudges it up


def test_two_different_classes_stay_separate():
    plan = _plan()
    dets = {"f0": [Detection(DamageClass.water_stain.value, "p", 0.4, (100, 80, 160, 120), "f0"),
                   Detection(DamageClass.crack.value, "p", 0.4, (100, 80, 160, 120), "f0")]}
    res = analyse_damage([_frame("f0")], plan, DummyDetector(dets), CFG,
                         fallback_surface_id=plan.surfaces[0].id, use_multiview_filter=False)
    assert res.merged == 2


def test_rules_fire_with_evidence_and_never_assert_certainty():
    ceiling_stain = {"damage_class": DamageClass.water_stain.value, "surface_type": "ceiling"}
    fired = [r for r in RULES if r.applies(ceiling_stain)]
    assert [r.id for r in fired] == ["CD-01"]
    assert all(0.0 < r.confidence < 0.8 for r in RULES)
    assert all(r.text and r.id for r in RULES)

    low_stain = {"damage_class": DamageClass.water_stain.value, "surface_type": "wall",
                 "height_above_floor_m": 0.3}
    assert "CD-02" in [r.id for r in RULES if r.applies(low_stain)]
    high_stain = {"damage_class": DamageClass.water_stain.value, "surface_type": "wall",
                  "height_above_floor_m": 1.8}
    assert "CD-02" not in [r.id for r in RULES if r.applies(high_stain)]


def test_mould_always_flags_a_hidden_source():
    assert "CD-05" in [r.id for r in RULES if r.applies({"damage_class": DamageClass.mould.value,
                                                         "surface_type": "wall"})]


def test_scope_items_carry_propagated_intervals_and_a_minimum():
    plan = _plan()
    dets = {"f0": [Detection(DamageClass.water_stain.value, "p", 0.6, (100, 80, 160, 120), "f0")]}
    res = analyse_damage([_frame("f0")], plan, DummyDetector(dets), CFG,
                         fallback_surface_id=plan.surfaces[0].id, use_multiview_filter=False)
    assert res.scope_items
    item = res.scope_items[0]
    assert item.quantity.ci_low <= item.quantity.value <= item.quantity.ci_high
    assert item.quantity.value >= 0.25  # the table's minimum for a wall stain
    assert item.damage_region_ids == [res.regions[0].id]
    assert "repaint" in item.description.lower()


def test_scope_lookup_falls_back_to_any_surface():
    assert scope_for(DamageClass.mould.value, "ceiling") is not None
    assert scope_for(DamageClass.water_stain.value, "ceiling").quantity_factor == 2.0
    assert scope_for("not_a_class", "wall") is None


def test_result_is_contract_valid_when_spliced_into_a_plan():
    plan = _plan()
    dets = {"f0": [Detection(DamageClass.water_stain.value, "p", 0.6, (100, 80, 160, 120), "f0")]}
    res = analyse_damage([_frame("f0")], plan, DummyDetector(dets), CFG,
                         fallback_surface_id=plan.surfaces[0].id, use_multiview_filter=False)
    spliced = plan.model_copy(update={"damage_regions": res.regions,
                                      "concealed_damage_flags": res.flags,
                                      "scope_items": res.scope_items})
    Plan.model_validate(spliced.model_dump(mode="json"))
