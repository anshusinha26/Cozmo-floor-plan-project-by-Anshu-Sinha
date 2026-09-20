#!/usr/bin/env python
"""Run the damage module on real captures and report hits, misses and false positives.

    .venv/bin/python scripts/run_damage_eval.py --out fix_loop/../docs/damage_eval

Needs the OWLv2 weights (scripts/fetch_damage_weights.py) and data/, which is
gitignored.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

from cozmo.contracts.models import Plan
from cozmo.damage.detector import Owlv2Detector
from cozmo.damage.frames import frames_from_images, frames_from_stray
from cozmo.damage.pipeline import analyse_damage
from cozmo.io.ground_truth import load_ground_truth
from cozmo.io.manifest import load_config
from cozmo.io.stray import StrayScan

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "docs" / "damage_eval"))
    ap.add_argument("--threshold", type=float, default=0.20)
    ap.add_argument("--stray-stride", type=int, default=120)
    ap.add_argument("--max-lidar-frames", type=int, default=25)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    cfg = load_config(ROOT / "config" / "gates.yaml")["pipeline"]["lidar"]
    detector = Owlv2Detector(threshold=a.threshold)
    report: dict = {"threshold": a.threshold, "cases": []}

    # Case 1: staged damage in bedroom_2_repeat photos. No depth.
    gt = load_ground_truth(ROOT / "benchmarks" / "ground_truth" / "own_bedroom_2_repeat_photo.yaml")
    expected = [(d.damage_class.value, d.wall_id, d.extent_m2_upper_bound) for d in gt.damage]
    photos = sorted((ROOT / "data" / "own" / "bedroom_2_repeat").glob("*.jpeg"))
    plan_path = ROOT / "fix_loop" / "after" / "bench" / "runs" / "c7d28f72c6" / "plan.json"
    plan = Plan.from_json_bytes(plan_path.read_bytes())
    t0 = time.time()
    res = analyse_damage(frames_from_images(photos), plan, detector, cfg,
                         fallback_surface_id=plan.surfaces[0].id)
    found = {}
    for r in res.regions:
        found[r.damage_class.value] = found.get(r.damage_class.value, 0) + 1
    report["cases"].append({
        "name": "own/bedroom_2_repeat photos (staged: one water stain, one crack)",
        "frames": len(photos), "seconds": time.time() - t0,
        "expected": [{"class": c, "wall": w, "extent_upper_bound_m2": e} for c, w, e in expected],
        "detections": res.detections, "regions": res.merged, "per_class": found,
        "hits": sorted({c for c, _, _ in expected} & set(found)),
        "misses": sorted({c for c, _, _ in expected} - set(found)),
        "other_classes_reported": sorted(set(found) - {c for c, _, _ in expected}),
        "all_extents_unbounded": all(r.extent_m2.method == "unbounded_no_metric_depth" for r in res.regions),
        "warnings": res.warnings,
        "flags": [{"rule": f.rule_id, "text": f.rule_text} for f in res.flags],
        "scope_items": [{"description": s.description, "quantity_m2": s.quantity.value} for s in res.scope_items],
    })

    # Case 2: LiDAR scan with depth. No staged damage, so everything found is
    # either real building damage or a false positive.
    for sid in ("c7d28f72c6",):
        scan = StrayScan(ROOT / "data" / "sample" / sid, "lidar")
        run = ROOT / "fix_loop" / "after" / "bench" / "runs" / sid / "plan.json"
        p = Plan.from_json_bytes(run.read_bytes())
        t0 = time.time()
        frames = list(frames_from_stray(scan, stride=a.stray_stride, max_frames=a.max_lidar_frames))
        res = analyse_damage(frames, p, detector, cfg, fallback_surface_id=p.surfaces[0].id)
        per_class = {}
        for r in res.regions:
            per_class[r.damage_class.value] = per_class.get(r.damage_class.value, 0) + 1
        report["cases"].append({
            "name": f"data/sample/{sid} (LiDAR, depth available, no known damage)",
            "frames": len(frames), "seconds": time.time() - t0,
            "expected": "none known; the glass shower screen is a known false-positive hazard",
            "detections": res.detections, "regions": res.merged, "per_class": per_class,
            "bounded_extents": sum(1 for r in res.regions
                                   if r.extent_m2.method != "unbounded_no_metric_depth"),
            "extent_range_m2": [min((r.extent_m2.value for r in res.regions), default=None),
                                max((r.extent_m2.value for r in res.regions), default=None)],
            "warnings": res.warnings,
            "flags": [{"rule": f.rule_id, "text": f.rule_text} for f in res.flags][:10],
        })

    (out / "damage_eval.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
