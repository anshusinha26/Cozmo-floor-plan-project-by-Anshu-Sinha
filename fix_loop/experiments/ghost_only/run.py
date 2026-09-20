"""Falsifier: drop ghost faces only, keep erosion segmentation, re-score the repeat pair.

If room counts converge and the repeatability gate moves most of the way to
the declared prediction, the cell complex is unnecessary.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from cozmo.contracts.models import Plan  # noqa: E402
from cozmo.eval import gates as G  # noqa: E402
from cozmo.eval.self_consistency import cross_plan_repeat_pairs, same_space_verdict  # noqa: E402
from cozmo.io.manifest import load_config  # noqa: E402

OUT = Path(__file__).resolve().parent
PAIR = ("1a8384c3f6", "c7d28f72c6")
SCANS = ["c00a170fe1", *PAIR]


def main() -> int:
    runs = OUT / "runs"
    for sid in SCANS:
        d = runs / sid
        if (d / "plan.json").exists():
            continue
        cmd = [str(ROOT / ".venv" / "bin" / "python"), "-m", "cozmo.cli", "run",
               "--input", str(ROOT / "data" / "sample" / sid), "--tier", "lidar",
               "--out", str(d), "--seed", "0"]
        print(" ".join(cmd), flush=True)
        subprocess.run(cmd, check=True, cwd=ROOT, capture_output=True)

    cfg = load_config(ROOT / "config" / "gates.yaml")
    plans = {s: Plan.from_json_bytes((runs / s / "plan.json").read_bytes()) for s in SCANS}
    a, b = plans[PAIR[0]], plans[PAIR[1]]
    rows, summary = cross_plan_repeat_pairs(a, b, "sample_apartment", "lidar")
    gate = G.repeatability(rows, cfg)
    matched = [r for r in rows if r["matched"]]
    result = {
        "experiment": "ghost_only",
        "description": "ghost-face rejection on, erosion segmentation unchanged",
        "rooms": {s: len(p.rooms) for s, p in plans.items()},
        "ghost_warnings": {s: [w for w in p.warnings if "Dropped" in w] for s, p in plans.items()},
        "same_space": same_space_verdict(a, b),
        "matching": summary,
        "gate": {"passed": gate["passed"], "n": gate["n"], "value": gate["value"],
                 "n_within_tolerance": gate["detail"]["n_within_tolerance"],
                 "share_within_tolerance": gate["detail"]["share_within_tolerance"]},
        "median_abs_edge_length_difference_m": None,
    }
    if matched:
        import numpy as np
        result["median_abs_edge_length_difference_m"] = float(
            np.median([abs(r["a"] - r["b"]) for r in matched]))
    (OUT / "result.json").write_text(json.dumps(result, indent=2, default=float) + "\n")
    print(json.dumps(result, indent=2, default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main())
