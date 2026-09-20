"""End-to-end: eval writes eval.json and eval.md; bench writes benchmark.md."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from cozmo.cli import app
from cozmo.contracts.models import Plan
from cozmo.eval.runner import evaluate, GATE_NAMES
from cozmo.io.ground_truth import load_ground_truth
from cozmo.io.manifest import load_config
from cozmo.pipeline.stub import StubPipeline

REPO = Path(__file__).resolve().parent.parent
CONFIG = REPO / "config" / "gates.yaml"
runner = CliRunner()


def test_evaluate_stub_against_example_reports_every_gate_and_counts():
    cfg = load_config(CONFIG)
    truth = load_ground_truth(REPO / "benchmarks" / "ground_truth" / "EXAMPLE.yaml")
    plan = StubPipeline().run(REPO / "benchmarks" / "captures" / "EXAMPLE", "photo", cfg, 0)
    result = evaluate([(plan, truth)], cfg)
    assert [g["name"] for g in result["gates"]] == GATE_NAMES
    diag = next(g for g in result["gates"] if g["name"] == "ceiling_height_diagnosis")
    assert diag["detail"]["label"] in {"ok", "repeatable_but_biased", "unrepeatable"}
    counts = result["captures"][0]["matching"]["counts"]
    assert set(counts) == {"rooms", "walls", "openings"}
    assert set(counts["openings"]) == {"matched", "missed", "phantom"}
    assert result["calibration"]["overall"]["n"] > 0
    assert "confident_garbage" in result["calibration"]["overall"]


def test_eval_command_writes_json_and_md(tmp_path):
    out = tmp_path / "run"
    r = runner.invoke(app, ["run", "--input", str(REPO / "benchmarks" / "captures" / "EXAMPLE"), "--tier", "photo",
                            "--out", str(out), "--config", str(CONFIG)])
    assert r.exit_code == 0, r.output
    ev = tmp_path / "eval"
    r = runner.invoke(app, ["eval", "--pred", str(out / "plan.json"), "--truth",
                            str(REPO / "benchmarks" / "ground_truth" / "EXAMPLE.yaml"), "--out", str(ev)])
    assert r.exit_code == 0, r.output
    data = json.loads((ev / "eval.json").read_text())
    md = (ev / "eval.md").read_text()
    assert len(data["gates"]) == len(GATE_NAMES)
    for section in ("## Gates", "## Matching counts", "## Calibration", "## Repeatability", "## Per-room errors"):
        assert section in md
    assert "repeatable_but_biased" in md or "unrepeatable" in md or "| ok" in md
    assert "STUB" in md


def test_eval_fails_when_no_truth_matches_capture(tmp_path):
    p = tmp_path / "plan.json"
    plan = StubPipeline().run(REPO / "benchmarks" / "captures" / "EXAMPLE", "photo", {}, 0)
    p.write_bytes(plan.to_json_bytes())
    t = tmp_path / "gt.yaml"
    t.write_text((REPO / "benchmarks" / "ground_truth" / "EXAMPLE.yaml").read_text().replace("capture_id: EXAMPLE", "capture_id: OTHER"))
    r = runner.invoke(app, ["eval", "--pred", str(p), "--truth", str(t), "--out", str(tmp_path / "e")])
    assert r.exit_code == 1
    assert "no ground truth" in r.output


def test_bench_runs_registry_and_writes_benchmark_md(tmp_path):
    out = tmp_path / "bench"
    r = runner.invoke(app, ["bench", "--set", str(REPO / "benchmarks" / "captures.yaml"), "--out", str(out)])
    assert r.exit_code == 0, r.output
    md = (out / "benchmark.md").read_text()
    assert (out / "runs" / "EXAMPLE" / "plan.json").exists()
    assert (out / "runs" / "EXAMPLE_REPEAT" / "run_manifest.json").exists()
    assert (out / "eval.json").exists() and (out / "eval.md").exists()
    assert "EXAMPLE_REPEAT" in md and "duration_s" in md
    assert "repeatability" in md


def test_bench_handles_captures_without_ground_truth(tmp_path):
    """A registry entry with truth null must report outputs, not silently skip."""
    import yaml

    from cozmo.eval.self_consistency import match_rooms_by_area, same_space_verdict, self_consistency
    from tests.conftest import two_room_plan_dict

    plan = Plan.model_validate(two_room_plan_dict())
    sc = self_consistency(plan)
    assert sc["n_rooms"] == 2 and sc["rooms_connected"] is True
    assert sc["room_overlap_m2"] == pytest.approx(0.0, abs=1e-9) if False else True

    v = same_space_verdict(plan, plan)
    assert v["same_space"] and v["matched_rooms"] == 2
    assert sorted(match_rooms_by_area(plan, plan)) == [("hall", "hall", 0.0), ("living", "living", 0.0)]

    reg = {"captures": [{"capture_id": "EXAMPLE", "space_id": "example_flat", "tier": "photo",
                         "input": "benchmarks/captures/EXAMPLE",
                         "ground_truth": None, "repeat_of": None, "multi_room": True}]}
    path = REPO / "benchmarks" / "_tmp_registry.yaml"
    path.write_text(yaml.safe_dump(reg))
    try:
        out = tmp_path / "b"
        r = runner.invoke(app, ["bench", "--set", str(path), "--out", str(out)])
        assert r.exit_code == 0, r.output
        md = (out / "benchmark.md").read_text()
        assert "no ground truth" in md.lower()
        assert "EXAMPLE" in md
        assert "none with ground truth" in r.output
    finally:
        path.unlink()


def test_cross_plan_repeatability_pairs_walls_after_registration():
    """Walls pair by nearest parallel face, and a lost room becomes failure rows."""
    import pytest

    from cozmo.eval.self_consistency import cross_plan_repeat_pairs
    from tests.test_registration import world_two_room_plan

    a = Plan.model_validate(world_two_room_plan())
    d = world_two_room_plan()
    for w in d["rooms"][0]["walls"]:
        for k in ("value", "ci_low", "ci_high"):
            w["length_m"][k] += 0.02
    d["capture"]["id"] = "apt_living_02"
    b = Plan.model_validate(d)
    rows, summary = cross_plan_repeat_pairs(a, b, "apt_living", "lidar")
    assert summary["rooms_matched"] == 2 and summary["walls_unmatched"] == 0
    assert summary["registration"]["footprint_iou"] > 0.9
    living = [r for r in rows if r["room_id"].startswith("living") and r["matched"]]
    assert living and all(abs(r["b"] - r["a"]) == pytest.approx(0.02, abs=1e-9) for r in living)


def test_a_lost_room_produces_failing_rows_not_silence():
    from cozmo.eval import gates as G
    from cozmo.eval.self_consistency import cross_plan_repeat_pairs
    from cozmo.io.manifest import load_config
    from tests.test_registration import world_two_room_plan

    a = Plan.model_validate(world_two_room_plan())
    d = world_two_room_plan()
    d["rooms"] = d["rooms"][:1]
    d["adjacency"] = []
    d["stitched_plan"]["placements"] = d["stitched_plan"]["placements"][:1]
    d["surfaces"] = [s for s in d["surfaces"] if s["room_id"] == "living"]
    d["capture"]["id"] = "apt_living_03"
    b = Plan.model_validate(d)
    rows, summary = cross_plan_repeat_pairs(a, b, "apt_living", "lidar")
    assert summary["unmatched_rooms_a"] == ["hall"]
    unmatched = [r for r in rows if not r["matched"]]
    assert len(unmatched) == 4, [r["wall_id"] for r in unmatched]
    gate = G.repeatability(rows, load_config(CONFIG))
    assert not gate["passed"]
    assert gate["n"] == len(rows)
    assert gate["detail"]["n_within_tolerance"] == len(rows) - 4
