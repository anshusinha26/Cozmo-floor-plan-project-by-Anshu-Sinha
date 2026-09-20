#!/usr/bin/env python
"""Render the head-to-head table.

    .venv/bin/python scripts/head_to_head.py [--plans DIR] [--out PATH]

With --plans pointing at a directory of run outputs, our column is filled from
the plans found there. Without it, the table prints the rival against tape and
says our column is not yet available.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from cozmo.contracts.models import Plan
from cozmo.eval.head_to_head import build_rows, load_spec, render_markdown, summarize

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", default=str(ROOT / "benchmarks" / "head_to_head" / "arplan3d.yaml"))
    ap.add_argument("--plans", default=None, help="directory of run outputs, each with plan.json")
    ap.add_argument("--tier", default="photo")
    ap.add_argument("--out", default=str(ROOT / "docs" / "head_to_head.md"))
    a = ap.parse_args()

    plans: dict[str, Plan] = {}
    if a.plans:
        for p in sorted(Path(a.plans).rglob("plan.json")):
            plan = Plan.from_json_bytes(p.read_bytes())
            for room in plan.rooms:
                plans.setdefault(room.id, plan)

    spec = load_spec(Path(a.spec))
    rows = build_rows(spec, ROOT / "benchmarks" / "ground_truth", plans, a.tier)
    summary = summarize(rows, spec["comparison"]["tie_threshold_m"])
    md = render_markdown(spec, rows, summary)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
