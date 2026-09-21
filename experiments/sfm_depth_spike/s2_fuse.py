"""Step 6: fit each mono depth map to that frame's SfM sparse depths (robust
scale + shift), unproject with SfM poses scaled by s_est, fuse, and plot the
1.0-2.2 m band top-down next to the same plot built from LiDAR.

The mono cloud uses only rgb + SfM + s_est. ARKit R,t are used to put the two
clouds in the same frame for the picture; s_est, not s_true, carries the scale,
so the video tier's scale error stays visible."""
import argparse, csv, json
from pathlib import Path

import cv2
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
ap.add_argument("--scan", required=True)
ap.add_argument("--tag", default="sfm")
ap.add_argument("--model", required=True)
ap.add_argument("--stride-px", type=int, default=3)
a = ap.parse_args()
out, scan = Path(a.out), Path(a.scan)

E = np.load(out / f"export_{a.tag}.npz", allow_pickle=True)
names = [str(x) for x in E["names"]]
cfw = E["cam_from_world"]
obs_uv, obs_z, obs_off = E["obs_uv"], E["obs_z"], E["obs_off"]
f, cx, cy, k = [float(x) for x in E["cam_params"]]

AL = np.load(out / f"align_{a.tag}.npz", allow_pickle=True)
R_al, t_al = AL["R"], AL["t"]
D = json.loads((out / f"depth_{a.model}_{a.tag}.json").read_text())
s_est, s_true = D["s_est_m_per_sfm_unit"], D["s_true_m_per_sfm_unit"]
DM = np.load(out / f"depthmaps_{a.model}_{a.tag}.npz")


def robust_fit(d, z, iters=8):
    """Least squares a*d + b ~ z, reweighted Huber. Returns (a, b)."""
    A = np.stack([d, np.ones_like(d)], 1)
    w = np.ones_like(d)
    ab = np.array([1.0, 0.0])
    for _ in range(iters):
        W = w[:, None]
        ab = np.linalg.lstsq(A * W, z * w, rcond=None)[0]
        r = A @ ab - z
        s = 1.4826 * np.median(np.abs(r - np.median(r))) + 1e-6
        w = 1.0 / np.sqrt(1.0 + (r / (1.345 * s)) ** 2)
    return float(ab[0]), float(ab[1])


# ---------- mono cloud (rgb + SfM only, scaled by s_est) ----------
mono, mono_rgb, fits = [], [], []
for i, name in enumerate(names):
    if name not in DM.files:
        continue
    dep = DM[name].astype(np.float32)
    H, W = dep.shape
    uv = obs_uv[obs_off[i]:obs_off[i + 1]]
    zs = obs_z[obs_off[i]:obs_off[i + 1]]
    uu = np.round(uv[:, 0]).astype(int); vv = np.round(uv[:, 1]).astype(int)
    ok = (uu >= 0) & (uu < W) & (vv >= 0) & (vv < H)
    dk, zk = dep[vv[ok], uu[ok]], zs[ok]
    g = np.isfinite(dk) & (dk > 0.05)
    if g.sum() < 30:
        continue
    # SfM depth is in SfM units; mono depth is metres. Fit metres -> SfM units.
    A_, B_ = robust_fit(dk[g], zk[g])
    fits.append((A_, B_, int(g.sum())))

    ys, xs = np.mgrid[0:H:a.stride_px, 0:W:a.stride_px]
    z_sfm = A_ * dep[ys, xs] + B_
    m = np.isfinite(z_sfm) & (z_sfm > 0.05) & (z_sfm < 30.0)
    xs, ys, z_sfm = xs[m], ys[m], z_sfm[m]
    X = (xs - cx) / f * z_sfm
    Y = (ys - cy) / f * z_sfm
    P_cam = np.stack([X, Y, z_sfm], 1)
    Rw = cfw[i][:3, :3]; tw = cfw[i][:3, 3]
    P_sfm = (P_cam - tw) @ Rw                      # SfM world, SfM units
    mono.append((s_est * (R_al @ P_sfm.T)).T + t_al)   # ARKit frame, metres via s_est
    img = cv2.imread(str(out / "images" / name))
    mono_rgb.append(img[ys, xs][:, ::-1])
mono = np.concatenate(mono); mono_rgb = np.concatenate(mono_rgb)

# ---------- LiDAR cloud (EVAL ONLY) ----------
rows = list(csv.DictReader(open(scan / "odometry.csv"), skipinitialspace=True))
ofid = np.array([int(r["frame"]) for r in rows])
fids = [int(n[1:7]) for n in names]
K = np.loadtxt(scan / "camera_matrix.csv", delimiter=",")
lid = []
for fid in fids:
    dp = cv2.imread(str(scan / "depth" / f"{fid:06d}.png"), cv2.IMREAD_UNCHANGED)
    cf = cv2.imread(str(scan / "confidence" / f"{fid:06d}.png"), cv2.IMREAD_UNCHANGED)
    if dp is None:
        continue
    dh, dw = dp.shape
    sx, sy = dw / 1920.0, dh / 1440.0
    fx, fy = K[0, 0] * sx, K[1, 1] * sy
    ux, uy = K[0, 2] * sx, K[1, 2] * sy
    z = dp.astype(np.float32) / 1000.0
    m = (cf == 2) & (z > 0.15) & (z < 6.0)
    vv, uu = np.nonzero(m); zz = z[m]
    # Stray Scanner's odometry quaternion is already an OpenCV-style cam->world
    # (checked empirically: the floor lands 1.44 m below the camera; flipping y
    # and z instead puts every point above the camera).
    P = np.stack([(uu - ux) / fx * zz, (vv - uy) / fy * zz, zz], 1)
    r = rows[int(np.argmin(np.abs(ofid - fid)))]
    q = np.array([float(r["qx"]), float(r["qy"]), float(r["qz"]), float(r["qw"])])
    x, w = q[:3], float(q[3])
    Rq = (np.eye(3) * (w * w - x @ x) + 2 * np.outer(x, x) +
          2 * w * np.array([[0, -x[2], x[1]], [x[2], 0, -x[0]], [-x[1], x[0], 0]]))
    lid.append(P @ Rq.T + np.array([float(r["x"]), float(r["y"]), float(r["z"])]))
lid = np.concatenate(lid)

# ---------- top-down band ----------
floor = float(np.percentile(lid[:, 1], 1.0))
lo, hi = floor + 1.0, floor + 2.2


def band(P):
    return P[(P[:, 1] > lo) & (P[:, 1] < hi)]


bm, bl = band(mono), band(lid)
np.save(out / f"band_mono_{a.model}.npy", bm[:, [0, 2]])
np.save(out / "band_lidar.npy", bl[:, [0, 2]])
allp = np.concatenate([bm, bl])
pad = 0.4
ext = [allp[:, 0].min() - pad, allp[:, 0].max() + pad, allp[:, 2].min() - pad, allp[:, 2].max() + pad]
bins = [int((ext[1] - ext[0]) / 0.02), int((ext[3] - ext[2]) / 0.02)]

fig, ax = plt.subplots(1, 2, figsize=(13, 6.2))
for k_, (P, ttl) in enumerate([(bm, f"video tier: SfM + {a.model} (s_est)"), (bl, "LiDAR + ARKit (reference)")]):
    Hh, _, _ = np.histogram2d(P[:, 0], P[:, 2], bins=bins, range=[ext[:2], ext[2:]])
    ax[k_].imshow(np.log1p(Hh).T, origin="lower", extent=ext, cmap="magma", aspect="equal")
    ax[k_].set_title(f"{ttl}\n{len(P):,} pts in {lo - floor:.1f}-{hi - floor:.1f} m band")
    ax[k_].set_xlabel("x (m)"); ax[k_].set_ylabel("z (m)")
fig.suptitle(f"top-down density, scan {scan.name}   s_est={s_est:.4f}  s_true={s_true:.4f}  "
             f"ratio={s_est / s_true:.3f}")
fig.tight_layout()
png = out / f"topdown_{a.model}_{a.tag}.png"
fig.savefig(png, dpi=130)

ply = out / f"fused_{a.model}_{a.tag}.ply"
with open(ply, "w") as fh:
    fh.write(f"ply\nformat ascii 1.0\nelement vertex {len(mono)}\n"
             "property float x\nproperty float y\nproperty float z\n"
             "property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n")
    for p, c in zip(mono.astype(np.float32), mono_rgb.astype(np.uint8)):
        fh.write(f"{p[0]:.4f} {p[1]:.4f} {p[2]:.4f} {c[0]} {c[1]} {c[2]}\n")

res = {"model": a.model, "keyframes_fused": len(fits), "mono_points": int(len(mono)),
       "lidar_points": int(len(lid)), "floor_y_m": round(floor, 3),
       "band_mono_pts": int(len(bm)), "band_lidar_pts": int(len(bl)),
       "s_est": s_est, "s_true": s_true, "s_est_over_s_true": round(s_est / s_true, 4),
       "png": str(png), "ply": str(ply)}
(out / f"fuse_{a.model}_{a.tag}.json").write_text(json.dumps(res, indent=2))
print(json.dumps(res, indent=2))
