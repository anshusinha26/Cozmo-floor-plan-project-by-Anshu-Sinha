"""Wall straightness: fit a 2D line to the top-down band inside a hand-picked box
and report the RMS perpendicular residual, mono cloud vs LiDAR."""
import json, sys
from pathlib import Path
import numpy as np

out = Path(sys.argv[1]); model = sys.argv[2]
P = {}
for tagname, f in (("mono", f"band_mono_{model}.npy"), ("lidar", "band_lidar.npy")):
    P[tagname] = np.load(out / f)
BOXES = {"wall_NW": (-0.2, 1.3, 1.7, 3.0), "wall_E": (1.9, 2.8, -0.8, 2.4)}
res = {}
for wname, (x0, x1, z0, z1) in BOXES.items():
    for src, Q in P.items():
        m = (Q[:, 0] > x0) & (Q[:, 0] < x1) & (Q[:, 1] > z0) & (Q[:, 1] < z1)
        q = Q[m]
        if len(q) < 200:
            res[f"{wname}_{src}"] = None; continue
        c = q.mean(0)
        u, s, vt = np.linalg.svd(q - c, full_matrices=False)
        r = (q - c) @ vt[1]                      # perpendicular residual, metres
        res[f"{wname}_{src}"] = {"n": int(len(q)),
                                 "rms_cm": round(float(np.sqrt((r ** 2).mean())) * 100, 2),
                                 "p95_abs_cm": round(float(np.percentile(np.abs(r), 95)) * 100, 2),
                                 "length_m": round(float(s[0] / np.sqrt(len(q)) * 2 * np.sqrt(3)), 2)}
print(json.dumps(res, indent=2))
(out / f"wall_{model}.json").write_text(json.dumps(res, indent=2))
