"""Fused predicted point cloud to PLY, plus a top-down density image and a robust path metric."""
import argparse, csv, json
from pathlib import Path

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
ap.add_argument("--frames", required=True)
ap.add_argument("--scan", required=True)
a = ap.parse_args()
out = Path(a.out)
d = np.load(out / "preds.npz", allow_pickle=True)
pts = d["pts3d"]            # (N, H, W, 3) world
mask = d["mask"]            # (N, H, W, 1) or zeros
poses = d["camera_poses"]
files = [str(x) for x in d["frame_files"]]

cols = []
for f in files:
    img = cv2.imread(str(Path(a.frames) / f))
    cols.append(cv2.resize(img, (pts.shape[2], pts.shape[1]), interpolation=cv2.INTER_AREA)[..., ::-1])
cols = np.stack(cols)

m = mask[..., 0] > 0.5 if mask.ndim == 4 else np.ones(pts.shape[:3], bool)
P = pts[m].reshape(-1, 3)
C = cols[m].reshape(-1, 3).astype(np.uint8)
step = max(1, len(P) // 1_500_000)
P, C = P[::step], C[::step]
print("points", len(P))

ply = out / "fused_pred.ply"
with open(ply, "wb") as fh:
    fh.write(b"ply\nformat binary_little_endian 1.0\n")
    fh.write(f"element vertex {len(P)}\n".encode())
    fh.write(b"property float x\nproperty float y\nproperty float z\n")
    fh.write(b"property uchar red\nproperty uchar green\nproperty uchar blue\n")
    fh.write(b"end_header\n")
    arr = np.empty(len(P), dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
                                  ("r", "u1"), ("g", "u1"), ("b", "u1")])
    arr["x"], arr["y"], arr["z"] = P[:, 0], P[:, 1], P[:, 2]
    arr["r"], arr["g"], arr["b"] = C[:, 0], C[:, 1], C[:, 2]
    fh.write(arr.tobytes())
print("wrote", ply, ply.stat().st_size / 1e6, "MB")

# Gravity axis: the MapAnything world frame is the first camera's frame, so the
# floor is not axis aligned. A PCA of the points does not find gravity in a
# single room. The phone was held roughly upright, so the mean of the cameras'
# +Y axes (down, in OpenCV convention) is a far better estimate.
down = poses[:, :3, 1].mean(0)
down /= np.linalg.norm(down)
up = -down
tmp = np.array([1.0, 0.0, 0.0])
if abs(tmp @ up) > 0.9:
    tmp = np.array([0.0, 0.0, 1.0])
e1 = np.cross(up, tmp); e1 /= np.linalg.norm(e1)
e2 = np.cross(up, e1)
basis = np.stack([e1, e2])
origin = P.mean(0)
xy = (P - origin) @ basis.T
h, xe, ye = np.histogram2d(xy[:, 0], xy[:, 1], bins=600)
fig, ax = plt.subplots(1, 2, figsize=(15, 7))
ax[0].imshow(np.log1p(h.T), origin="lower", extent=[xe[0], xe[-1], ye[0], ye[-1]], cmap="magma")
ax[0].set_title("predicted points, top-down (gravity from camera poses), log density")
ax[0].set_aspect("equal")
pp = (poses[:, :3, 3] - origin) @ basis.T
ax[0].plot(pp[:, 0], pp[:, 1], color="cyan", lw=1.0, label="predicted camera path")
ax[0].legend(fontsize=7)
ax[1].hist((P - origin) @ up, bins=300)
ax[1].set_title("point distribution along the up axis (floor and ceiling peaks)")
fig.savefig(out / "topdown_density.png", dpi=110, bbox_inches="tight")
plt.close(fig)

# Robust path scale: bounding box diagonal, which a jittery path does not inflate.
scan = Path(a.scan)
rows = []
with open(scan / "odometry.csv") as fh:
    r = csv.reader(fh)
    hdr = [x.strip() for x in next(r)]
    for row in r:
        if row and row[0].strip():
            rows.append(row)
col = {h: i for i, h in enumerate(hdr)}
fcol = np.array([int(x[col["frame"]]) for x in rows])
tw = np.array([[float(x[col[k]]) for k in ("x", "y", "z")] for x in rows])
fid = [int(f.split("_f")[1].split(".")[0]) for f in files]
ark = tw[[int(np.argmin(np.abs(fcol - f))) for f in fid]]
def diag(p):
    return float(np.linalg.norm(p.max(0) - p.min(0)))
res = {"pred_bbox_diag_m": diag(poses[:, :3, 3]), "arkit_bbox_diag_m": diag(ark),
       "ratio_B_bbox": diag(poses[:, :3, 3]) / diag(ark),
       "pred_cloud_bbox_m": [float(v) for v in (P.max(0) - P.min(0))]}
prev = json.loads((out / "scale.json").read_text())
prev.update(res)
(out / "scale.json").write_text(json.dumps(prev, indent=2))
print(json.dumps(res, indent=2))
