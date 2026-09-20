#!/usr/bin/env python
"""Build a photo-tier capture folder from a video, for cross-tier comparison.

    scripts/frames_to_photo_capture.py data/sample/c00a170fe1 runs/photo_from_video 8 --rotation 90

Takes evenly spaced frames, keeps the sharpest one near each target position, and
writes them as one room folder. The result is a photo-tier capture whose images
came from a clip, which is a fair way to ask what the photo tier does with the
same scene, and it is labelled as derived so nobody mistakes it for a photo shoot.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cozmo.pipeline.video import frames as frames_mod  # noqa: E402
from cozmo.pipeline.video.probe import find_video  # noqa: E402


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("capture")
    ap.add_argument("out")
    ap.add_argument("n", type=int, nargs="?", default=8)
    ap.add_argument("--rotation", default="auto")
    ap.add_argument("--room", default=None, help="room folder name, default the capture's")
    ap.add_argument("--fps", type=float, default=4.0)
    a = ap.parse_args(argv[1:])

    capture = Path(a.capture)
    video = find_video(capture)
    room = a.room or capture.name
    work = Path(a.out) / "_frames"
    fs = frames_mod.extract(video, work, target_fps=a.fps, long_side=1280, max_frames=400,
                            rotation=a.rotation, drop_blur_frac=0.0)

    scores = fs.blur_scores
    targets = np.linspace(0, len(fs) - 1, a.n + 2)[1:-1]      # avoid the very ends
    half = max(1, len(fs) // (2 * a.n))
    picked: list[int] = []
    for t in targets:
        lo, hi = max(0, int(t) - half), min(len(fs), int(t) + half + 1)
        window = list(range(lo, hi))
        window.sort(key=lambda i: -scores[i])
        for i in window:
            if i not in picked:
                picked.append(i)
                break
    picked.sort()

    room_dir = Path(a.out) / room
    if room_dir.exists():
        shutil.rmtree(room_dir)
    room_dir.mkdir(parents=True)
    for k, i in enumerate(picked, start=1):
        shutil.copy2(fs.path(fs.names[i]), room_dir / f"frame_{k:02d}.jpg")
    shutil.rmtree(work, ignore_errors=True)

    meta = {"source_video": str(video), "derived_from": "video",
            "note": "These are frames taken from a clip, not photographs. Any photo-tier result "
                    "on them is a cross-tier comparison, not a photo-tier capture.",
            "n_images": len(picked), "rotation": a.rotation,
            "blur_scores": [round(float(scores[i]), 2) for i in picked]}
    (Path(a.out) / "DERIVED_FROM_VIDEO.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps({"room": room, "images": len(picked), "dir": str(room_dir)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
