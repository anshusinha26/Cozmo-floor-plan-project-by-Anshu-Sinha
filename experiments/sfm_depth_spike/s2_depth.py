"""Steps 4 and 5: metric monocular depth on MPS, LiDAR ratio, and LiDAR-free
scale recovery from the SfM sparse points.

The pipeline under test uses only rgb frames + the SfM model. LiDAR is read only
to score the result."""
import argparse, json, time
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image

ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
ap.add_argument("--scan", required=True)
ap.add_argument("--tag", default="sfm")
ap.add_argument("--model", required=True, choices=["depthpro_own", "depthpro_colmap", "dav2"])
ap.add_argument("--n", type=int, default=30)
ap.add_argument("--save-depth", action="store_true")
a = ap.parse_args()

out, scan = Path(a.out), Path(a.scan)
dev = torch.device("mps")
E = np.load(out / f"export_{a.tag}.npz", allow_pickle=True)
names = [str(x) for x in E["names"]]
f_colmap = float(E["cam_params"][0])
obs_uv, obs_z, obs_off = E["obs_uv"], E["obs_z"], E["obs_off"]

pick = np.linspace(0, len(names) - 1, min(a.n, len(names))).round().astype(int)
sel = sorted(set(int(i) for i in pick))

# ---------- model ----------
if a.model.startswith("depthpro"):
    import depth_pro
    from huggingface_hub import hf_hub_download
    cfg = depth_pro.depth_pro.DEFAULT_MONODEPTH_CONFIG_DICT
    cfg.checkpoint_uri = hf_hub_download("apple/DepthPro", "depth_pro.pt")
    model, tf = depth_pro.create_model_and_transforms(config=cfg, device=dev, precision=torch.float32)
    model.eval()

    def predict(path):
        img, _, f_px_exif = depth_pro.load_rgb(str(path))
        x = tf(img)
        f_in = None if a.model == "depthpro_own" else torch.tensor(f_colmap)
        p = model.infer(x, f_px=f_in)
        return p["depth"].detach().float().cpu().numpy(), float(p["focallength_px"])
else:
    from transformers import AutoImageProcessor, AutoModelForDepthEstimation
    MID = "depth-anything/Depth-Anything-V2-Metric-Indoor-Large-hf"
    proc = AutoImageProcessor.from_pretrained(MID)
    model = AutoModelForDepthEstimation.from_pretrained(MID).to(dev).eval()

    def predict(path):
        pil = Image.open(path).convert("RGB")
        inp = proc(images=pil, return_tensors="pt").to(dev)
        with torch.no_grad():
            o = model(**inp)
        d = proc.post_process_depth_estimation(o, target_sizes=[(pil.height, pil.width)])
        return d[0]["predicted_depth"].float().cpu().numpy(), float("nan")

# ---------- per-frame ----------
lidar_ratios, scale_ratios, secs, focals, npts = [], [], [], [], []
store = {}
for k in sel:
    name = names[k]
    p = out / "images" / name
    fid = int(name[1:7])
    t0 = time.time()
    dep, f_pred = predict(p)
    torch.mps.synchronize()
    secs.append(time.time() - t0)
    focals.append(f_pred)
    H, W = dep.shape
    if a.save_depth:
        store[name] = dep.astype(np.float16)

    # --- step 4: ratio vs LiDAR over confidence-2 pixels (EVAL ONLY) ---
    dl = cv2.imread(str(scan / "depth" / f"{fid:06d}.png"), cv2.IMREAD_UNCHANGED)
    cf = cv2.imread(str(scan / "confidence" / f"{fid:06d}.png"), cv2.IMREAD_UNCHANGED)
    if dl is not None and cf is not None:
        dl = cv2.rotate(dl, cv2.ROTATE_90_CLOCKWISE).astype(np.float32) / 1000.0
        cf = cv2.rotate(cf, cv2.ROTATE_90_CLOCKWISE)
        dlr = cv2.resize(dl, (W, H), interpolation=cv2.INTER_NEAREST)
        cfr = cv2.resize(cf, (W, H), interpolation=cv2.INTER_NEAREST)
        m = (cfr == 2) & (dlr > 0.2) & (dlr < 5.0) & np.isfinite(dep) & (dep > 0.05)
        if m.sum() > 500:
            lidar_ratios.append(float(np.median(dep[m] / dlr[m])))

    # --- step 5: LiDAR-free scale from SfM sparse depths ---
    uv = obs_uv[obs_off[k]:obs_off[k + 1]]
    zs = obs_z[obs_off[k]:obs_off[k + 1]]
    uu = np.round(uv[:, 0]).astype(int); vv = np.round(uv[:, 1]).astype(int)
    ok = (uu >= 0) & (uu < W) & (vv >= 0) & (vv < H)
    if ok.sum() >= 30:
        dm = dep[vv[ok], uu[ok]]; zk = zs[ok]
        good = np.isfinite(dm) & (dm > 0.05)
        if good.sum() >= 30:
            scale_ratios.append(float(np.median(dm[good] / zk[good])))
            npts.append(int(good.sum()))

lr, sr = np.array(lidar_ratios), np.array(scale_ratios)
res = {
    "model": a.model, "tag": a.tag, "n_frames": len(sel),
    "sec_per_frame": round(float(np.mean(secs)), 3),
    "sec_per_frame_median": round(float(np.median(secs)), 3),
    "pred_focal_px_mean": None if not np.isfinite(focals).any() else round(float(np.nanmean(focals)), 1),
    "colmap_focal_px": round(f_colmap, 2),
    "n_lidar_scored": int(lr.size),
    "lidar_ratio_mean": round(float(lr.mean()), 4) if lr.size else None,
    "lidar_ratio_sd": round(float(lr.std(ddof=1)), 4) if lr.size > 1 else None,
    "lidar_ratio_median": round(float(np.median(lr)), 4) if lr.size else None,
    "n_scale_frames": int(sr.size),
    "sfm_pts_per_frame_median": int(np.median(npts)) if npts else 0,
    "s_est_m_per_sfm_unit": round(float(np.median(sr)), 6) if sr.size else None,
    "s_est_sd": round(float(sr.std(ddof=1)), 6) if sr.size > 1 else None,
}
pose = json.loads((out / f"pose_{a.tag}.json").read_text())
res["s_true_m_per_sfm_unit"] = pose["s_true_m_per_sfm_unit"]
if res["s_est_m_per_sfm_unit"]:
    res["s_est_over_s_true"] = round(res["s_est_m_per_sfm_unit"] / pose["s_true_m_per_sfm_unit"], 4)
(out / f"depth_{a.model}_{a.tag}.json").write_text(json.dumps(res, indent=2))
if a.save_depth:
    np.savez_compressed(out / f"depthmaps_{a.model}_{a.tag}.npz", **store)
print(json.dumps(res, indent=2))
