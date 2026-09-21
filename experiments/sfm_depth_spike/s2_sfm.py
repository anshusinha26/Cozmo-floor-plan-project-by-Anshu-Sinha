"""Step 2: pycolmap SIFT + sequential matching + incremental mapping.

One shared SIMPLE_RADIAL camera. Reads ONLY the extracted rgb frames."""
import argparse, json, shutil, time
from pathlib import Path

import numpy as np
import pycolmap

ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
ap.add_argument("--overlap", type=int, default=10)
ap.add_argument("--max-image-size", type=int, default=1600)
ap.add_argument("--exhaustive", action="store_true")
ap.add_argument("--relax", action="store_true")
ap.add_argument("--tag", default="sfm")
a = ap.parse_args()

out = Path(a.out)
img_dir = out / "images"
sfm_dir = out / a.tag
if sfm_dir.exists():
    shutil.rmtree(sfm_dir)
sfm_dir.mkdir(parents=True)
db = sfm_dir / "database.db"
n_images = len(list(img_dir.glob("*.jpg")))

t = {}
t0 = time.time()
reader = pycolmap.ImageReaderOptions()
reader.camera_model = "SIMPLE_RADIAL"
fe = pycolmap.FeatureExtractionOptions()
fe.max_image_size = a.max_image_size
fe.sift.max_num_features = 8192
pycolmap.extract_features(
    database_path=db, image_path=img_dir,
    camera_mode=pycolmap.CameraMode.SINGLE,   # one shared camera
    reader_options=reader, extraction_options=fe,
)
t["extract_s"] = round(time.time() - t0, 1)

t0 = time.time()
if a.exhaustive:
    pycolmap.match_exhaustive(database_path=db)
else:
    pair = pycolmap.SequentialPairingOptions()
    pair.overlap = a.overlap
    pair.quadratic_overlap = True
    pair.loop_detection = False
    pycolmap.match_sequential(database_path=db, pairing_options=pair)
t["match_s"] = round(time.time() - t0, 1)

t0 = time.time()
opts = pycolmap.IncrementalPipelineOptions()
opts.ba_refine_principal_point = False
if a.relax:
    # Hand-held forward walking through a room: small triangulation angles and
    # near-forward motion make the stock init thresholds reject every pair.
    opts.min_num_matches = 10
    opts.mapper.init_min_tri_angle = 4.0
    opts.mapper.init_max_forward_motion = 1.0
    opts.mapper.init_min_num_inliers = 50
    opts.mapper.abs_pose_min_num_inliers = 15
    opts.mapper.abs_pose_min_inlier_ratio = 0.15
    opts.mapper.filter_max_reproj_error = 4.0
    opts.mapper.filter_min_tri_angle = 1.0
recs = pycolmap.incremental_mapping(
    database_path=db, image_path=img_dir, output_path=sfm_dir / "models", options=opts
)
t["mapping_s"] = round(time.time() - t0, 1)

if not recs:
    print(json.dumps({"error": "no reconstruction", "timings": t}))
    raise SystemExit(1)

best_id = max(recs, key=lambda k: recs[k].num_reg_images())
rec = recs[best_id]
cam = list(rec.cameras.values())[0]

res = {
    "n_input_images": n_images,
    "n_models": len(recs),
    "model_sizes": sorted((r.num_reg_images() for r in recs.values()), reverse=True),
    "registered": rec.num_reg_images(),
    "registered_fraction": round(rec.num_reg_images() / n_images, 4),
    "n_points3D": rec.num_points3D(),
    "mean_reproj_err_px": round(float(rec.compute_mean_reprojection_error()), 4),
    "mean_track_length": round(float(rec.compute_mean_track_length()), 3),
    "mean_obs_per_reg_image": round(float(rec.compute_mean_observations_per_reg_image()), 1),
    "camera_model": cam.model.name,
    "camera_wh": [cam.width, cam.height],
    "camera_params": [round(float(p), 4) for p in cam.params],
    "colmap_focal_px": round(float(cam.params[0]), 2),
    "matching": "exhaustive" if a.exhaustive else f"sequential overlap {a.overlap} quadratic", "relaxed_mapper": bool(a.relax),
    "timings": t,
    "total_s": round(sum(t.values()), 1),
}
rec.write(str(sfm_dir))
(out / f"{a.tag}.json").write_text(json.dumps(res, indent=2))
print(json.dumps(res, indent=2))
