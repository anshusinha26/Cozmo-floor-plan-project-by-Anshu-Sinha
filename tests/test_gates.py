"""Each gate at just-pass and just-fail. Thresholds come from config/gates.yaml."""

from __future__ import annotations

from pathlib import Path

import pytest

from cozmo.contracts.models import Plan
from cozmo.eval import gates as g
from cozmo.io.manifest import load_config
from tests.conftest import two_room_plan_dict

CFG = load_config(Path(__file__).resolve().parent.parent / "config" / "gates.yaml")


def _shape(res):
    assert set(res) >= {"name", "passed", "value", "threshold", "n", "detail"}
    assert isinstance(res["passed"], bool)
    return res


# opening_width: |pred - truth| <= 2 cm on >= 85% of (matched + missed + phantom)

def test_opening_width_just_pass_and_just_fail_on_fraction():
    ok = [(0.80, 0.80)] * 17
    bad = [(0.90, 0.80)]
    r = _shape(g.opening_width(ok + bad * 3, n_missed=0, n_phantom=0, cfg=CFG))
    assert r["passed"] and r["value"] == pytest.approx(0.85) and r["n"] == 20
    r = g.opening_width(ok + bad * 4, n_missed=0, n_phantom=0, cfg=CFG)
    assert not r["passed"] and r["value"] == pytest.approx(16 / 20)


def test_opening_width_missed_and_phantom_count_in_denominator():
    ok = [(0.80, 0.80)] * 17
    r = g.opening_width(ok, n_missed=2, n_phantom=1, cfg=CFG)
    assert r["passed"] and r["n"] == 20 and r["value"] == pytest.approx(0.85)
    r = g.opening_width(ok, n_missed=3, n_phantom=1, cfg=CFG)
    assert not r["passed"] and r["n"] == 21
    assert r["detail"]["missed"] == 3 and r["detail"]["phantom"] == 1


def test_opening_width_tolerance_boundary_inclusive():
    assert g.opening_width([(0.82, 0.80)], 0, 0, CFG)["detail"]["within_tolerance"] == 1
    assert g.opening_width([(0.8201, 0.80)], 0, 0, CFG)["detail"]["within_tolerance"] == 0


# ceiling_height: abs error <= 1.5 cm per room; spread across captures of a space <= 1 cm

def _ch(capture, pred, truth=2.70, space="s", room="r"):
    return {"capture_id": capture, "space_id": space, "room_id": room, "pred": pred, "truth": truth}


def test_ceiling_height_abs_error_boundary():
    assert _shape(g.ceiling_height([_ch("a", 2.715)], CFG))["passed"]
    assert not g.ceiling_height([_ch("a", 2.7151)], CFG)["passed"]


def test_ceiling_height_spread_boundary():
    rows = [_ch("a", 2.700), _ch("b", 2.710)]
    r = g.ceiling_height(rows, CFG)
    assert r["passed"] and r["detail"]["spread"][0]["spread_m"] == pytest.approx(0.01)
    rows = [_ch("a", 2.700), _ch("b", 2.7101)]
    assert not g.ceiling_height(rows, CFG)["passed"]


def test_ceiling_height_diagnosis_labels():
    r = _shape(g.ceiling_height_diagnosis([_ch("a", 2.72), _ch("b", 2.721)], CFG))
    assert r["detail"]["label"] == "repeatable_but_biased" and not r["passed"]
    r = g.ceiling_height_diagnosis([_ch("a", 2.70), _ch("b", 2.72)], CFG)
    assert r["detail"]["label"] == "unrepeatable" and not r["passed"]
    r = g.ceiling_height_diagnosis([_ch("a", 2.705), _ch("b", 2.71)], CFG)
    assert r["detail"]["label"] == "ok" and r["passed"]


# repeatability: |a - b| <= max(1 cm, 0.5% of length) per wall

def _rp(a, b, wall="w1"):
    return {"space_id": "s", "tier": "video", "capture_a": "a", "capture_b": "b", "room_id": "r", "wall_id": wall, "a": a, "b": b}


def test_repeatability_boundaries():
    r = _shape(g.repeatability([_rp(4.000, 4.020)], CFG))  # allowed = max(0.01, 0.005*4.01) = 0.02
    assert r["passed"]
    assert not g.repeatability([_rp(4.000, 4.0201)], CFG)["passed"]
    assert g.repeatability([_rp(1.000, 1.010)], CFG)["passed"]  # 1 cm floor dominates on short walls
    r = g.repeatability([_rp(1.000, 1.0101), _rp(4.0, 4.0, "w2")], CFG)
    assert not r["passed"] and r["detail"]["worst"]["wall_id"] == "w1"


def test_repeatability_with_no_pairs_is_vacuous_and_says_so():
    r = g.repeatability([], CFG)
    assert r["passed"] and r["n"] == 0 and "no repeat" in r["detail"]["note"]


# wall_length_tier: photo 8%, video 3%, lidar max(2 cm, 1%)

def _wl(pred, truth, tier):
    return {"capture_id": "c", "room_id": "r", "wall_id": "w", "pred": pred, "truth": truth, "tier": tier}


@pytest.mark.parametrize(
    "tier,truth,pass_pred,fail_pred",
    [("photo", 4.0, 4.32, 4.3201), ("video", 4.0, 4.12, 4.1201), ("lidar", 1.0, 1.02, 1.0201), ("lidar", 4.0, 4.04, 4.0401)],
)
def test_wall_length_tier_boundaries(tier, truth, pass_pred, fail_pred):
    assert _shape(g.wall_length_tier([_wl(pass_pred, truth, tier)], 0, 0, CFG))["passed"]
    assert not g.wall_length_tier([_wl(fail_pred, truth, tier)], 0, 0, CFG)["passed"]


def test_wall_length_tier_unmatched_truth_wall_fails():
    r = g.wall_length_tier([_wl(4.0, 4.0, "video")], n_unmatched_truth=1, n_unmatched_pred=0, cfg=CFG)
    assert not r["passed"] and r["detail"]["unmatched_truth"] == 1


# footprint: within 8%

def test_footprint_boundaries():
    assert _shape(g.footprint([{"capture_id": "c", "pred": 21.6, "truth": 20.0}], CFG))["passed"]
    assert not g.footprint([{"capture_id": "c", "pred": 21.601, "truth": 20.0}], CFG)["passed"]


# stitch_adjacency: graphs equal

def test_stitch_adjacency_reports_missing_and_spurious():
    row = {"capture_id": "c", "pred": [("living", "hall")], "truth": [("hall", "living")]}
    assert _shape(g.stitch_adjacency([row]))["passed"]
    row = {"capture_id": "c", "pred": [("living", "hall"), ("hall", "bath")], "truth": [("living", "hall"), ("living", "kitchen")]}
    r = g.stitch_adjacency([row])
    assert not r["passed"]
    assert r["detail"]["per_capture"][0]["missing"] == [["kitchen", "living"]]
    assert r["detail"]["per_capture"][0]["spurious"] == [["bath", "hall"]]


# stitch_overlap: total pairwise intersection area <= 0.05 m2

def test_stitch_overlap_boundaries():
    assert _shape(g.stitch_overlap([{"capture_id": "c", "overlap_m2": 0.05}], CFG))["passed"]
    assert not g.stitch_overlap([{"capture_id": "c", "overlap_m2": 0.0501}], CFG)["passed"]


def test_pairwise_overlap_area_from_placements():
    d = two_room_plan_dict()
    plan = Plan.model_validate(d)
    assert g.pairwise_overlap_area(plan) == pytest.approx(0.0)
    d["stitched_plan"]["placements"][1]["tx"] = 3.5  # hall (1.2 x 3.0) now overlaps living by 0.5 x 3.0
    assert g.pairwise_overlap_area(Plan.model_validate(d)) == pytest.approx(1.5)
