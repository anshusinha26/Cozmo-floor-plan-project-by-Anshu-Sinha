"""Renderer writes a PNG; run embeds its relative path in the plan."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from cozmo.cli import app
from cozmo.contracts.models import Plan
from cozmo.render.plan import render_plan_png
from tests.conftest import two_room_plan_dict
from tests.test_cli import CONFIG

runner = CliRunner()


def test_render_plan_png_writes_png(tmp_path):
    plan = Plan.model_validate(two_room_plan_dict())
    out = render_plan_png(plan, tmp_path / "plan.png")
    data = out.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"


def test_run_writes_plan_png_and_records_it(tmp_path):
    cap = tmp_path / "cap"
    for room in ("living", "hall"):
        (cap / room).mkdir(parents=True)
        (cap / room / "a.jpg").write_bytes(b"1")
        (cap / room / "b.jpg").write_bytes(b"2")
    out = tmp_path / "out"
    r = runner.invoke(app, ["run", "--input", str(cap), "--tier", "photo", "--out", str(out), "--config", str(CONFIG), "--pipeline", "stub"])
    assert r.exit_code == 0, r.output
    assert (out / "plan.png").exists()
    assert json.loads((out / "plan.json").read_text())["renders"]["plan_png"] == "plan.png"


def test_render_command_wraps_same_function(tmp_path):
    p = tmp_path / "plan.json"
    p.write_bytes(Plan.model_validate(two_room_plan_dict()).to_json_bytes())
    r = runner.invoke(app, ["render", "--plan", str(p), "--out", str(tmp_path / "r")])
    assert r.exit_code == 0, r.output
    assert (tmp_path / "r" / "plan.png").exists()
