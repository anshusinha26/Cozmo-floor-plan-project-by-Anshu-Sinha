"""Extract N evenly spaced frames from a Stray Scanner rgb.mp4, upright."""
import sys
from pathlib import Path

import cv2
import numpy as np

SCAN = Path(sys.argv[1])
N = int(sys.argv[2])
ROT = sys.argv[3] if len(sys.argv) > 3 else "none"
out = Path(sys.argv[4]) if len(sys.argv) > 4 else Path(f"frames_{N}")
out.mkdir(parents=True, exist_ok=True)

cap = cv2.VideoCapture(str(SCAN / "rgb.mp4"))
total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
idx = np.linspace(0, total - 2, N).round().astype(int)
print("video frames", total, "size", int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), "x", int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
rot = {"none": None, "cw": cv2.ROTATE_90_CLOCKWISE, "ccw": cv2.ROTATE_90_COUNTERCLOCKWISE, "180": cv2.ROTATE_180}[ROT]
# Random seek fails on this HEVC file (cap.set returns frames from the wrong
# place or None), so decode sequentially and keep the wanted indices.
wanted = set(int(i) for i in idx)
saved = []
pos = 0
img = None
while True:
    ok, frame = cap.read()
    if not ok:
        break
    if pos in wanted:
        img = cv2.rotate(frame, rot) if rot is not None else frame
        p = out / f"{len(saved):03d}_f{pos:06d}.jpg"
        cv2.imwrite(str(p), img, [cv2.IMWRITE_JPEG_QUALITY, 95])
        saved.append(pos)
    pos += 1
cap.release()
np.save(out / "frame_indices.npy", np.array(saved))
print("wrote", len(saved), "frames to", out, "rotation", ROT, "shape", img.shape)
