#!/usr/bin/env python
"""Measure what each precision filter is worth, one at a time.

    .venv/bin/python scripts/damage_ablation.py

Detections are computed once per frame and reused for every configuration, so
the differences between rows are the filters and nothing else.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

from cozmo.contracts.models import Plan
from cozmo.damage.detector import Owlv2Detector
from cozmo.damage.filters import CropVerifier, NullVerifier
from cozmo.damage.frames import frames_from_images, frames_from_stray
from cozmo.damage.pipeline import analyse_damage
from cozmo.io.ground_truth import load_ground_truth
from cozmo.io.manifest import load_config
from cozmo.io.stray import StrayScan

ROOT = Path(__file__).resolve().parent.parent
STAGES = [
    ("raw", dict(use_distractor_filter=False, use_geometry_filter=False, use_multiview_filter=False)),
    ("1 distractors", dict(use_distractor_filter=True, use_geometry_filter=False, use_multiview_filter=False)),
    ("2 +geometry", dict(use_distractor_filter=True, use_geometry_filter=True, use_multiview_filter=False)),
    ("3 +multiview", dict(use_distractor_filter=True, use_geometry_filter=True, use_multiview_filter=True)),
    ("4 +verifier", dict(use_distractor_filter=True, use_geometry_filter=True, use_multiview_filter=True,
                         verify=True)),
]


class Cached:
    """Replays detections computed once, so filters are the only variable."""

    def __init__(self, raw: dict, threshold: float) -> None:
        self.raw = raw
        self.threshold = threshold

    def detect(self, image, frame_id):
        import copy

        return [copy.copy(d) for d in self.raw.get(frame_id, []) if d.confidence >= self.threshold]


def run_case(name: str, frames, plan, raw, cfg, expected: set[str], threshold: float,
             verifier, floor_y=None) -> dict:
    rows = []
    for label, kwargs in STAGES:
        kw = dict(kwargs)
        want_verifier = kw.pop("verify", False)
        t0 = time.time()
        res = analyse_damage(frames, plan, Cached(raw, threshold), cfg, floor_y=floor_y,
                             fallback_surface_id=plan.surfaces[0].id,
                             verifier=verifier if want_verifier else NullVerifier(), **kw)
        per_class = {}
        for r in res.regions:
            per_class[r.damage_class.value] = per_class.get(r.damage_class.value, 0) + 1
        found = set(per_class)
        rows.append({
            "stage": label,
            "regions": res.merged,
            "hits": sorted(expected & found),
            "misses": sorted(expected - found),
            "false_regions": sum(v for k, v in per_class.items() if k not in expected),
            "per_class": per_class,
            "seconds": round(time.time() - t0, 1),
            "rejections": res.stats.reasons,
        })
    return {"case": name, "frames": len(frames), "threshold": threshold, "expected": sorted(expected),
            "stages": rows}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "docs" / "damage_eval"))
    ap.add_argument("--thresholds", default="0.15,0.20,0.25")
    ap.add_argument("--stray-stride", type=int, default=120)
    ap.add_argument("--max-lidar-frames", type=int, default=25)
    ap.add_argument("--no-verifier", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    cfg = load_config(ROOT / "config" / "gates.yaml")["pipeline"]["lidar"]
    detector = Owlv2Detector(threshold=0.05, use_distractors=True)
    verifier = NullVerifier() if a.no_verifier else CropVerifier()

    plan = Plan.from_json_bytes(
        (ROOT / "fix_loop" / "after" / "bench" / "runs" / "c7d28f72c6" / "plan.json").read_bytes())

    gt = load_ground_truth(ROOT / "benchmarks" / "ground_truth" / "own_bedroom_2_repeat_photo.yaml")
    expected_photo = {d.damage_class.value for d in gt.damage}
    photos = sorted((ROOT / "data" / "own" / "bedroom_2_repeat").glob("*.jpeg"))
    photo_frames = list(frames_from_images(photos))
    raw_photo = {f.frame_id: detector.detect(f.image, f.frame_id) for f in photo_frames}

    scan = StrayScan(ROOT / "data" / "sample" / "c7d28f72c6", "lidar")
    lidar_frames = list(frames_from_stray(scan, stride=a.stray_stride, max_frames=a.max_lidar_frames))
    raw_lidar = {f.frame_id: detector.detect(f.image, f.frame_id) for f in lidar_frames}

    report = {"cases": []}
    for thr in [float(x) for x in a.thresholds.split(",")]:
        report["cases"].append(run_case(
            f"own/bedroom_2_repeat photos, threshold {thr}", photo_frames, plan, raw_photo, cfg,
            expected_photo, thr, verifier))
        report["cases"].append(run_case(
            f"data/sample/c7d28f72c6 lidar, threshold {thr}", lidar_frames, plan, raw_lidar, cfg,
            set(), thr, verifier))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "ablation.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    for case in report["cases"]:
        print(f"\n== {case['case']} ({case['frames']} frames, expected {case['expected']})")
        print(f"{'stage':16s} {'regions':>8s} {'false':>6s}  hits / misses")
        for r in case["stages"]:
            print(f"{r['stage']:16s} {r['regions']:8d} {r['false_regions']:6d}  "
                  f"{r['hits']} / {r['misses']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
