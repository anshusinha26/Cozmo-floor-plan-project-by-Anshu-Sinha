"""CLI contract: outputs written, provenance recorded, byte-identical reruns."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from typer.testing import CliRunner

from cozmo.cli import app
from cozmo.contracts.export_schema import build_schema
from cozmo.contracts.models import Plan
from cozmo.pipeline.stub import STUB_WARNING
from tests.test_contract import assert_no_bare_dimensions

REPO = Path(__file__).resolve().parent.parent
CONFIG = REPO / "config" / "gates.yaml"

runner = CliRunner()


@pytest.fixture
def capture_dir(tmp_path):
    d = tmp_path / "apt_living_01"
    for room in ("living", "hall"):
        (d / room).mkdir(parents=True)
        (d / room / "img_001.jpg").write_bytes(b"jpeg one")
        (d / room / "img_002.jpg").write_bytes(b"jpeg two")
    return d


def _run(capture_dir: Path, out: Path, *extra: str):
    args = ["run", "--input", str(capture_dir), "--tier", "photo", "--out", str(out), "--config", str(CONFIG), *extra]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    return result


def test_schema_command_writes_published_schema(tmp_path):
    out = tmp_path / "plan.schema.json"
    result = runner.invoke(app, ["schema", "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert json.loads(out.read_text()) == build_schema()


def test_run_writes_plan_and_manifest(capture_dir, tmp_path):
    out = tmp_path / "out"
    _run(capture_dir, out)
    plan_path = out / "plan.json"
    manifest_path = out / "run_manifest.json"
    assert plan_path.exists() and manifest_path.exists()

    instance = json.loads(plan_path.read_bytes())
    jsonschema.Draft202012Validator(build_schema()).validate(instance)
    assert_no_bare_dimensions(instance)
    plan = Plan.model_validate(instance)
    assert STUB_WARNING in plan.warnings
    assert plan.capture.tier == "photo"

    man = json.loads(manifest_path.read_text())
    assert [f["path"] for f in man["input"]["files"]] == [
        "hall/img_001.jpg", "hall/img_002.jpg", "living/img_001.jpg", "living/img_002.jpg"
    ]
    assert all(len(f["sha256"]) == 64 for f in man["input"]["files"])
    assert man["input"]["sha256"] == plan.capture.input_manifest_sha256
    assert man["config"]["sha256"] == plan.run.config_sha256
    assert man["git"]["commit"] == plan.run.git_commit
    assert man["seed"] == plan.run.seed == 0
    assert man["stage_timings_s"]
    assert man["duration_s"] >= 0
    assert man["started_at"]
    assert set(man["library_versions"]) >= {"pydantic", "numpy", "shapely", "typer", "pyyaml", "jsonschema", "matplotlib"}
    assert man["config"]["resolved"]["run"]["drift_correction"] is True


def test_run_is_byte_identical_for_same_input_config_seed(capture_dir, tmp_path):
    _run(capture_dir, tmp_path / "a", "--seed", "7")
    _run(capture_dir, tmp_path / "b", "--seed", "7")
    a = (tmp_path / "a" / "plan.json").read_bytes()
    b = (tmp_path / "b" / "plan.json").read_bytes()
    assert a == b
    ma = json.loads((tmp_path / "a" / "run_manifest.json").read_text())
    mb = json.loads((tmp_path / "b" / "run_manifest.json").read_text())
    assert ma["plan_sha256"] == mb["plan_sha256"]
    assert ma["input"]["sha256"] == mb["input"]["sha256"]


def test_seed_and_drift_flag_are_recorded(capture_dir, tmp_path):
    _run(capture_dir, tmp_path / "a", "--seed", "3", "--drift-correction", "off")
    plan = Plan.from_json_bytes((tmp_path / "a" / "plan.json").read_bytes())
    man = json.loads((tmp_path / "a" / "run_manifest.json").read_text())
    assert plan.run.seed == 3
    assert man["config"]["resolved"]["run"]["drift_correction"] is False


def test_run_rejects_unknown_tier(capture_dir, tmp_path):
    result = runner.invoke(app, ["run", "--input", str(capture_dir), "--tier", "sonar", "--out", str(tmp_path / "o")])
    assert result.exit_code != 0


def test_run_rejects_bad_layout(tmp_path):
    d = tmp_path / "cap" / "living"
    d.mkdir(parents=True)
    (d / "only_one.jpg").write_bytes(b"x")
    result = runner.invoke(app, ["run", "--input", str(tmp_path / "cap"), "--tier", "photo", "--out", str(tmp_path / "o"), "--config", str(CONFIG)])
    assert result.exit_code == 1
    assert "at least 2" in result.output


def test_run_rejects_missing_input(tmp_path):
    result = runner.invoke(app, ["run", "--input", str(tmp_path / "nope"), "--tier", "photo", "--out", str(tmp_path / "o")])
    assert result.exit_code != 0


@pytest.mark.parametrize(
    "args",
    [
        ["eval", "--pred", "x.json", "--truth", "y.yaml", "--out", "o"],
        ["bench", "--set", "benchmarks/captures.yaml", "--out", "o"],
        ["render", "--plan", "x.json", "--out", "o"],
    ],
)
def test_unimplemented_commands_fail_loudly(args):
    result = runner.invoke(app, args)
    assert result.exit_code == 2
    assert "not implemented" in result.output.lower()
