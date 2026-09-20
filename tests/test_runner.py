"""End-to-end: eval writes eval.json and eval.md; bench writes benchmark.md."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from cozmo.cli import app
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
