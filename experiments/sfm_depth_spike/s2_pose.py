"""Step 3: Sim3 (Umeyama) alignment of SfM camera centres to ARKit odometry.

ARKit is EVALUATION ONLY. The SfM model itself saw nothing but rgb frames."""
import argparse, csv, json
from pathlib import Path

import numpy as np
import pycolmap

ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
ap.add_argument("--scan", required=True)
ap.add_argument("--tag", default="sfm")
a = ap.parse_args()

out, scan = Path(a.out), Path(a.scan)
rec = pycolmap.Reconstruction(str(out / a.tag))

names, C = [], []
for im in rec.images.values():
    if im.has_pose:
        names.append(im.name)
        C.append(im.projection_center())
order = np.argsort(names)
names = [names[i] for i in order]
C = np.array(C)[order]                       # SfM camera centres, arbitrary units
fids = np.array([int(n[1:7]) for n in names])

rows = list(csv.DictReader(open(scan / "odometry.csv"), skipinitialspace=True))
ofid = np.array([int(r["frame"]) for r in rows])
opos = np.array([[float(r["x"]), float(r["y"]), float(r["z"])] for r in rows])
sel = np.array([int(np.argmin(np.abs(ofid - f))) for f in fids])
G = opos[sel]                                # ARKit centres, metres


def umeyama(X, Y):
    """Return s, R, t minimising ||s R X + t - Y||. X, Y are (N,3)."""
    mx, my = X.mean(0), Y.mean(0)
    Xc, Yc = X - mx, Y - my
    S = Yc.T @ Xc / len(X)
    U, D, Vt = np.linalg.svd(S)
    W = np.eye(3)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        W[2, 2] = -1
    R = U @ W @ Vt
    s = float(np.trace(np.diag(D) @ W) / (Xc ** 2).sum() * len(X))
    t = my - s * R @ mx
    return s, R, t


s, R, t = umeyama(C, G)
aligned = (s * (R @ C.T)).T + t
err = np.linalg.norm(aligned - G, axis=1)

sfm_len = float(np.linalg.norm(np.diff(C, axis=0), axis=1).sum())
ark_len = float(np.linalg.norm(np.diff(G, axis=0), axis=1).sum())

res = {
    "tag": a.tag,
    "n_aligned": len(C),
    "s_true_m_per_sfm_unit": round(s, 6),
    "ate_rmse_cm": round(float(np.sqrt((err ** 2).mean())) * 100, 2),
    "ate_median_cm": round(float(np.median(err)) * 100, 2),
    "ate_max_cm": round(float(err.max()) * 100, 2),
    "sfm_path_units": round(sfm_len, 4),
    "arkit_path_m_same_frames": round(ark_len, 4),
    "arkit_span_m": round(float(np.linalg.norm(G.max(0) - G.min(0))), 3),
    "frame_id_min": int(fids.min()), "frame_id_max": int(fids.max()),
}
(out / f"pose_{a.tag}.json").write_text(json.dumps(res, indent=2))
np.savez(out / f"align_{a.tag}.npz", s=s, R=R, t=t, names=np.array(names), fids=fids)
print(json.dumps(res, indent=2))
