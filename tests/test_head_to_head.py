"""Head-to-head table: rival against tape now, ours once the tiers land."""

from __future__ import annotations

from pathlib import Path

import pytest

from cozmo.eval.head_to_head import build_rows, load_spec, render_markdown, summarize

REPO = Path(__file__).resolve().parent.parent
SPEC = REPO / "benchmarks" / "head_to_head" / "arplan3d.yaml"
GT = REPO / "benchmarks" / "ground_truth"


def test_spec_loads_and_names_its_protocol_and_screenshots():
    spec = load_spec(SPEC)
    assert spec["rival"]["name"] == "AR Plan 3D"
    assert "casual" in spec["rival"]["protocol"]
    assert spec["comparison"]["tie_threshold_m"] == 0.015
    assert any(e["name"] == "magicplan" for e in spec["not_compared"])


def test_rows_pick_up_tape_values_and_leave_our_column_empty():
    rows = build_rows(load_spec(SPEC), GT)
    assert len(rows) == 6
    b1 = [r for r in rows if r.room_id == "bedroom_1"]
    assert {r.dimension for r in b1} == {"short_pair", "long_pair"}
    short = next(r for r in b1 if r.dimension == "short_pair")
    assert short.truth_m == pytest.approx(3.6576)
    assert short.rival_m == pytest.approx(3.41)
    assert short.rival_error == pytest.approx(0.2476, abs=1e-4)
    assert short.ours_m is None and short.our_error is None
    assert short.verdict(0.015) == "not yet"


def test_kitchen_walls_map_individually():
    rows = [r for r in build_rows(load_spec(SPEC), GT) if r.room_id == "kitchen"]
    assert len(rows) == 4
    by_dim = {r.dimension: r for r in rows}
    assert by_dim["short_wall_1"].truth_m == pytest.approx(2.6924)
    assert by_dim["long_wall_2"].truth_m == pytest.approx(3.6028)
    assert by_dim["long_wall_2"].rival_error == pytest.approx(0.1872, abs=1e-4)


def test_verdict_uses_the_tie_threshold():
    from cozmo.eval.head_to_head import Row

    r = Row("r", "d", ["A"], truth_m=3.0, rival_m=3.10, ours_m=3.09)
    assert r.verdict(0.015) == "tie"
    assert r.verdict(0.005) == "ours"
    worse = Row("r", "d", ["A"], truth_m=3.0, rival_m=3.01, ours_m=3.20)
    assert worse.verdict(0.015) == "theirs"


def test_summary_reports_not_yet_until_our_column_is_filled():
    rows = build_rows(load_spec(SPEC), GT)
    s = summarize(rows, 0.015)
    assert s["n_scored"] == 0 and s["not_yet"] == 6 and s["beat_or_tie_pct"] is None
    md = render_markdown(load_spec(SPEC), rows, s)
    assert "no tier has produced plans" in md
    assert "magicplan" in md
    assert "Their error against tape" in md


def test_summary_counts_wins_ties_and_losses_once_ours_exists():
    from cozmo.eval.head_to_head import Row

    rows = [Row("r", "a", ["A"], 3.0, 3.20, 3.01),
            Row("r", "b", ["B"], 3.0, 3.02, 3.19),
            Row("r", "c", ["C"], 3.0, 3.05, 3.045)]
    s = summarize(rows, 0.015)
    assert (s["ours"], s["theirs"], s["tie"]) == (1, 1, 1)
    assert s["beat_or_tie_pct"] == pytest.approx(200 / 3, abs=0.1)
