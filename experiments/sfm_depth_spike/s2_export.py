"""Export the SfM model to npz so the depth scripts never import pycolmap
alongside torch (both ship their own libomp and the process aborts)."""
import argparse, json
from pathlib import Path

import numpy as np
import pycolmap

ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
ap.add_argument("--tag", default="sfm")
a = ap.parse_args()
out = Path(a.out)
rec = pycolmap.Reconstruction(str(out / a.tag))
cam = list(rec.cameras.values())[0]

names, cfw, obs_uv, obs_z, obs_off = [], [], [], [], [0]
for im in sorted((i for i in rec.images.values() if i.has_pose), key=lambda i: i.name):
    names.append(im.name)
    M = np.eye(4); M[:3, :4] = im.cam_from_world().matrix()
    cfw.append(M)
    for p2 in im.points2D:
        if not p2.has_point3D():
            continue
        z = float((im.cam_from_world() * rec.points3D[p2.point3D_id].xyz)[2])
        if z <= 0.05:
            continue
        obs_uv.append(p2.xy); obs_z.append(z)
    obs_off.append(len(obs_z))

np.savez(out / f"export_{a.tag}.npz",
         names=np.array(names), cam_from_world=np.array(cfw),
         obs_uv=np.array(obs_uv, np.float32), obs_z=np.array(obs_z, np.float32),
         obs_off=np.array(obs_off, np.int64),
         cam_params=np.array(cam.params, np.float64),
         cam_wh=np.array([cam.width, cam.height], np.int64),
         cam_model=np.array(cam.model.name),
         xyz=np.array([p.xyz for p in rec.points3D.values()], np.float64))
print(json.dumps({"images": len(names), "observations": len(obs_z), "points3D": rec.num_points3D(),
                  "cam_model": cam.model.name, "params": [round(float(x), 4) for x in cam.params]}))
