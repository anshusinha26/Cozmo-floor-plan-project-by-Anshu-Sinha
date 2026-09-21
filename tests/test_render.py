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


def test_damage_regions_are_marked_on_the_plan():
    """A plan that carries damage has to show it, or the PNG contradicts the JSON.

    The marker sits on the wall the region is attached to. Its polygon is in
    surface-local metres, which a floor plan cannot place along the wall
    without the offset, so the plan marks the wall rather than inventing a
    position on it.
    """
    from cozmo.render.plan import damage_markers

    bare = Plan.model_validate(two_room_plan_dict()).model_copy(update={"damage_regions": []})
    assert damage_markers(bare) == [], "no regions, no markers"

    d = two_room_plan_dict()
    surface = d["surfaces"][0]
    # Scope items and flags reference the fixture's own regions, so they go too.
    d["scope_items"] = []
    d["concealed_damage_flags"] = []
    d["damage_regions"] = [{
        "id": "dmg_1", "surface_id": surface["id"], "damage_class": "water_stain",
        "extent_m2": {"value": 0.2, "ci_low": 0.05, "ci_high": 0.5, "unit": "m2",
                      "method": "unbounded_no_metric_depth", "ci_level": 0.95},
        "polygon": [[0.0, 0.0], [0.4, 0.0], [0.4, 0.5], [0.0, 0.5]], "confidence": 0.6,
    }]
    marked = Plan.model_validate(d)
    markers = damage_markers(marked)
    assert len(markers) == 1, "the fixture's own regions were replaced by this one"
    room_id, wall_id, damage_class = markers[0]
    assert room_id == surface["room_id"] and wall_id == surface["wall_id"]
    assert damage_class == "water_stain"
