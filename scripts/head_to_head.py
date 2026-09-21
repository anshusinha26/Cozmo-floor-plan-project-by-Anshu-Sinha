#!/usr/bin/env python
"""Render the head-to-head table.

    .venv/bin/python scripts/head_to_head.py [--eval eval.json] [--tier photo] [--out PATH]

Our column comes from an evaluation result, not from plan.json directly. A
rival dimension names truth walls (A, C); our wall ids are per-run inventions
(w1, w2), so the two can only be lined up through the eval's own wall
matching, which is what --eval carries. Without it the table prints the rival
against tape and says our column is not available.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cozmo.eval.head_to_head import (build_rows, load_spec, matched_lengths, render_markdown,
                                     summarize)

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", default=str(ROOT / "benchmarks" / "head_to_head" / "arplan3d.yaml"))
    ap.add_argument("--eval", dest="eval_path", default=None,
                    help="an eval.json, for example docs/benchmark/eval.json")
    ap.add_argument("--tier", default="photo")
    ap.add_argument("--out", default=str(ROOT / "docs" / "head_to_head.md"))
    a = ap.parse_args()

    lengths: dict[tuple[str, str], float] = {}
    if a.eval_path:
        lengths = matched_lengths(json.loads(Path(a.eval_path).read_text(encoding="utf-8")), a.tier)

    spec = load_spec(Path(a.spec))
    rows = build_rows(spec, ROOT / "benchmarks" / "ground_truth", lengths, a.tier)
    summary = summarize(rows, spec["comparison"]["tie_threshold_m"])
    md = render_markdown(spec, rows, summary)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
