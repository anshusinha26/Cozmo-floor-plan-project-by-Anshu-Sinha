"""Run MapAnything on images only and save predictions. Images, no depth, no poses, no intrinsics."""
import argparse, json, os, resource, sys, time
from pathlib import Path

import numpy as np
import torch

from mapanything.models import MapAnything
from mapanything.utils.image import load_images

ap = argparse.ArgumentParser()
ap.add_argument("--frames", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--device", default="mps")
ap.add_argument("--amp", default="1")
ap.add_argument("--checkpoint", default="facebook/map-anything-apache")
a = ap.parse_args()

device = torch.device(a.device)
paths = sorted(str(p) for p in Path(a.frames).glob("*.jpg"))
print(f"device={device} frames={len(paths)} checkpoint={a.checkpoint}", flush=True)

t_load = time.time()
model = MapAnything.from_pretrained(a.checkpoint).to(device)
model.eval()
print(f"model loaded in {time.time() - t_load:.1f}s", flush=True)

views = load_images(paths, verbose=False)
assert all(set(v.keys()) & {"depth_z", "camera_poses", "intrinsics"} == set() for v in views), \
    "views must carry image data only"

t0 = time.time()
with torch.no_grad():
    preds = model.infer(
        views,
        memory_efficient_inference=True,
        use_amp=a.amp == "1",
        amp_dtype="fp16" if device.type == "mps" else "bf16",
        apply_mask=True,
        mask_edges=True,
        apply_confidence_mask=False,
    )
if device.type == "mps":
    torch.mps.synchronize()
elapsed = time.time() - t0

rss_gb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9
mps_gb = torch.mps.driver_allocated_memory() / 1e9 if device.type == "mps" else 0.0

out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
np.savez_compressed(
    out / "preds.npz",
    depth_z=np.stack([p["depth_z"][0].float().cpu().numpy() for p in preds]),
    pts3d=np.stack([p["pts3d"][0].float().cpu().numpy() for p in preds]),
    mask=np.stack([p["mask"][0].float().cpu().numpy() for p in preds]) if "mask" in preds[0] else np.zeros(1),
    camera_poses=np.stack([p["camera_poses"][0].float().cpu().numpy() for p in preds]),
    intrinsics=np.stack([p["intrinsics"][0].float().cpu().numpy() for p in preds]),
    frame_files=np.array([Path(p).name for p in paths]),
)
meta = {"n": len(paths), "device": str(device), "seconds": elapsed, "max_rss_gb": rss_gb,
        "mps_driver_gb": mps_gb, "amp": a.amp == "1",
        "pred_shape": list(preds[0]["depth_z"].shape), "torch": torch.__version__}
(out / "meta.json").write_text(json.dumps(meta, indent=2))
print(json.dumps(meta, indent=2), flush=True)
