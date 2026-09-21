"""Scale check A (per-frame depth ratio) and B (path length ratio) against the Stray capture."""
import argparse, csv, json
from pathlib import Path

import cv2
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
ap.add_argument("--frames", required=True)
ap.add_argument("--scan", required=True)
a = ap.parse_args()

scan = Path(a.scan)
d = np.load(Path(a.out) / "preds.npz", allow_pickle=True)
pred_depth = d["depth_z"]           # (N, H, W, 1) metres
poses = d["camera_poses"]           # (N, 4, 4) cam2world
files = [str(x) for x in d["frame_files"]]
frame_ids = [int(f.split("_f")[1].split(".")[0]) for f in files]

# ---- odometry
rows = []
with open(scan / "odometry.csv") as fh:
    r = csv.reader(fh)
    hdr = [h.strip() for h in next(r)]
    for row in r:
        if row and row[0].strip():
            rows.append(row)
col = {h: i for i, h in enumerate(hdr)}
frame_col = np.array([int(x[col["frame"]]) for x in rows])
t_world = np.array([[float(x[col[k]]) for k in ("x", "y", "z")] for x in rows])

# ---- Scale check A: median(pred / lidar) per frame over confidence-2 pixels
ratios, kept = [], []
for i, fid in enumerate(frame_ids):
    dp = cv2.imread(str(scan / "depth" / f"{fid:06d}.png"), cv2.IMREAD_UNCHANGED)
    cf = cv2.imread(str(scan / "confidence" / f"{fid:06d}.png"), cv2.IMREAD_UNCHANGED)
    if dp is None or cf is None:
        continue
    # Same rotation applied to the rgb frames before inference.
    dp = cv2.rotate(dp, cv2.ROTATE_90_CLOCKWISE).astype(np.float32) / 1000.0
    cf = cv2.rotate(cf, cv2.ROTATE_90_CLOCKWISE)
    p = pred_depth[i, ..., 0]
    ph, pw = p.shape
    dp_r = cv2.resize(dp, (pw, ph), interpolation=cv2.INTER_NEAREST)
    cf_r = cv2.resize(cf, (pw, ph), interpolation=cv2.INTER_NEAREST)
    m = (cf_r == 2) & (dp_r > 0.2) & (dp_r < 4.5) & np.isfinite(p) & (p > 0.05)
    if m.sum() < 500:
        continue
    ratios.append(float(np.median(p[m] / dp_r[m])))
    kept.append(fid)
ratios = np.array(ratios)

# ---- Scale check B: predicted path length vs ARKit path length over the same frames
pred_pos = poses[:, :3, 3]
sel = np.array([np.argmin(np.abs(frame_col - f)) for f in frame_ids])
ark_pos = t_world[sel]
pred_len = float(np.linalg.norm(np.diff(pred_pos, axis=0), axis=1).sum())
ark_len = float(np.linalg.norm(np.diff(ark_pos, axis=0), axis=1).sum())

res = {
    "n_frames": len(frame_ids),
    "n_frames_scored": int(len(ratios)),
    "ratio_A_mean": float(ratios.mean()) if len(ratios) else None,
    "ratio_A_sd": float(ratios.std(ddof=1)) if len(ratios) > 1 else None,
    "ratio_A_median": float(np.median(ratios)) if len(ratios) else None,
    "ratio_A_min": float(ratios.min()) if len(ratios) else None,
    "ratio_A_max": float(ratios.max()) if len(ratios) else None,
    "pred_path_m": pred_len,
    "arkit_path_m": ark_len,
    "ratio_B": pred_len / ark_len if ark_len else None,
}
(Path(a.out) / "scale.json").write_text(json.dumps(res, indent=2))
print(json.dumps(res, indent=2))
