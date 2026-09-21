"""Step 1: sequential decode of rgb.mp4, keep every Nth frame, upright, 1280 long
side, then drop the blurriest 20% by variance of Laplacian.

Reads ONLY rgb.mp4 from the scan."""
import argparse, json, time
from pathlib import Path

import cv2
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("--scan", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--stride", type=int, default=12)
ap.add_argument("--long-side", type=int, default=1280)
ap.add_argument("--drop-frac", type=float, default=0.20)
a = ap.parse_args()

scan, out = Path(a.scan), Path(a.out)
img_dir = out / "images"
img_dir.mkdir(parents=True, exist_ok=True)
for p in img_dir.glob("*.jpg"):
    p.unlink()

t0 = time.time()
cap = cv2.VideoCapture(str(scan / "rgb.mp4"))
reported = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

# OpenCV seeking is broken on this HEVC file, so decode straight through.
cand = []  # (frame_id, upright resized bgr, blur score)
pos = 0
while True:
    ok, frame = cap.read()
    if not ok:
        break
    if pos % a.stride == 0:
        up = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        h, w = up.shape[:2]
        s = a.long_side / max(h, w)
        small = cv2.resize(up, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
        g = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        cand.append((pos, small, float(cv2.Laplacian(g, cv2.CV_64F).var())))
    pos += 1
cap.release()
decoded = pos

blur = np.array([c[2] for c in cand])
thr = np.quantile(blur, a.drop_frac)
keep = [c for c in cand if c[2] >= thr]
for fid, img, _ in keep:
    cv2.imwrite(str(img_dir / f"f{fid:06d}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 95])

meta = {
    "scan": str(scan),
    "reported_frames": reported,
    "decoded_frames": decoded,
    "src_wh": [src_w, src_h],
    "upright_resized_wh": [keep[0][1].shape[1], keep[0][1].shape[0]],
    "stride": a.stride,
    "candidates": len(cand),
    "kept": len(keep),
    "blur_threshold": float(thr),
    "blur_min_kept": float(min(c[2] for c in keep)),
    "blur_median_kept": float(np.median([c[2] for c in keep])),
    "frame_ids": [int(c[0]) for c in keep],
    "seconds": round(time.time() - t0, 1),
}
(out / "frames.json").write_text(json.dumps(meta, indent=2))
print(json.dumps({k: v for k, v in meta.items() if k != "frame_ids"}, indent=2))
