#!/usr/bin/env python
"""Does the damage detector survive a dark room?

Darkens the staged-damage photos by gamma and re-runs detection at each level,
so the answer is measured rather than assumed.

    .venv/bin/python scripts/hazard_lowlight.py
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import cv2
import numpy as np

from cozmo.contracts.models import Plan
from cozmo.damage.detector import Owlv2Detector
from cozmo.damage.filters import CropVerifier
from cozmo.damage.frames import DamageFrame
from cozmo.damage.pipeline import analyse_damage
from cozmo.io.ground_truth import load_ground_truth
from cozmo.io.manifest import load_config

ROOT = Path(__file__).resolve().parent.parent
# Gamma above 1 darkens. 1.8 is a room lit by one lamp; 3.0 is dusk indoors.
LEVELS = {"bright (original)": 1.0, "dim (gamma 1.8)": 1.8, "dark (gamma 3.0)": 3.0}


def darken(img: np.ndarray, gamma: float) -> np.ndarray:
    if gamma == 1.0:
        return img
    lut = np.array([((i / 255.0) ** gamma) * 255 for i in range(256)], dtype=np.uint8)
    return cv2.LUT(img, lut)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "docs" / "damage_eval"))
    ap.add_argument("--threshold", type=float, default=0.15)
    ap.add_argument("--source", default="own",
                    help="own: the staged-damage photos. lidar: RGB frames from a scan, "
                         "used when the staged photos cannot be read")
    ap.add_argument("--scan", default="c7d28f72c6")
    ap.add_argument("--stride", type=int, default=400)
    ap.add_argument("--max-frames", type=int, default=9)
    a = ap.parse_args()
    logging.basicConfig(level=logging.WARNING)
    cfg = load_config(ROOT / "config" / "gates.yaml")["pipeline"]["lidar"]
    gt = load_ground_truth(ROOT / "benchmarks" / "ground_truth" / "own_bedroom_2_repeat_photo.yaml")
    expected = {d.damage_class.value for d in gt.damage}
    plan = Plan.from_json_bytes(
        (ROOT / "fix_loop" / "before" / "bench" / "runs" / "c7d28f72c6" / "plan.json").read_bytes())
    if a.source == "own":
        photos = sorted((ROOT / "data" / "own" / "bedroom_2_repeat").glob("*.jpeg"))
        base = [(p.stem, cv2.imread(str(p)), str(p)) for p in photos]
        base = [(n, img, src) for n, img, src in base if img is not None]
        if not base:
            print("Could not read any staged-damage photo. On macOS these files may carry "
                  "com.apple.quarantine and be blocked; grant access or pass --source lidar.")
            return 2
        expected_here = expected
    else:
        from cozmo.damage.frames import frames_from_stray
        from cozmo.io.stray import StrayScan

        scan = StrayScan(ROOT / "data" / "sample" / a.scan, "lidar")
        base = [(f.frame_id, f.image[..., ::-1].copy(), f.source)
                for f in frames_from_stray(scan, stride=a.stride, max_frames=a.max_frames)]
        expected_here = set()  # no known damage in this property

    detector = Owlv2Detector(threshold=a.threshold)
    verifier = CropVerifier()

    report = {"source": a.source, "expected": sorted(expected_here), "threshold": a.threshold,
              "n_photos": len(base), "levels": []}
    expected = expected_here
    for label, gamma in LEVELS.items():
        frames = []
        mean_luma = []
        for name, bgr0, src in base:
            bgr = bgr0
            scale = 1600 / max(bgr.shape[:2])
            if scale < 1:
                bgr = cv2.resize(bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
            bgr = darken(bgr, gamma)
            mean_luma.append(float(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).mean()))
            frames.append(DamageFrame(frame_id=name, image=bgr[..., ::-1].copy(), source=src))
        res = analyse_damage(frames, plan, detector, cfg,
                             fallback_surface_id=plan.surfaces[0].id, verifier=verifier)
        per_class: dict[str, int] = {}
        for r in res.regions:
            per_class[r.damage_class.value] = per_class.get(r.damage_class.value, 0) + 1
        found = set(per_class)
        report["levels"].append({
            "level": label, "gamma": gamma,
            "mean_brightness_0_255": round(float(np.mean(mean_luma)), 1),
            "regions": res.merged,
            "hits": sorted(expected & found),
            "misses": sorted(expected - found),
            "false_regions": sum(v for k, v in per_class.items() if k not in expected),
            "per_class": per_class,
        })
        print(f"{label:22s} brightness {report['levels'][-1]['mean_brightness_0_255']:5.1f} "
              f"regions {res.merged:3d} false {report['levels'][-1]['false_regions']:3d} "
              f"hits {report['levels'][-1]['hits']} misses {report['levels'][-1]['misses']}")

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"lowlight_{a.source}.json").write_text(json.dumps(report, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
