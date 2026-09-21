"""One room from a handful of stills.

MapAnything is run on the room's photos and asked for everything it has: world
points, per-view depth, camera poses and intrinsics. Its geometry is used and
its scale is not. Spike 1 measured that scale at 0.70x on depth while the
trajectory ran 2.5 to 3.9 times long, so the two are not even consistent with
each other. Scale comes from the same camera-height prior the video tier uses
after fix loop 2.

Depth Pro is run as a second opinion when EXIF gives a focal length, because
that is the one case where it can be told the focal it needs. It never sets the
scale; it only says how far the two methods are apart, which widens intervals.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from cozmo.lidar.cloud import Cloud, VoxelGrid
from cozmo.pipeline.video.depth_models import sync

log = logging.getLogger(__name__)

MAPANYTHING_CHECKPOINT = "facebook/map-anything-apache"
MAX_PHOTOS = 12
MIN_POINTS = 500


@dataclass
class RoomReconstruction:
    room_id: str
    cloud: Cloud
    camera_path: np.ndarray
    camera_up: np.ndarray
    focal_px: list[float]
    n_photos: int
    scale_applied: float
    measured_height_m: float
    exif_focal_px: float | None
    depth_pro_scale: float | None
    method: str
    views: list[dict] = field(default_factory=list, repr=False)
    paths: list = field(default_factory=list, repr=False)
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        return {"room_id": self.room_id, "n_photos": self.n_photos,
                "points": int(len(self.cloud.points)),
                "scale_applied": round(self.scale_applied, 4),
                "measured_camera_height_m": None if not np.isfinite(self.measured_height_m)
                else round(self.measured_height_m, 3),
                "exif_focal_px": None if self.exif_focal_px is None else round(self.exif_focal_px, 1),
                "mapanything_focal_px": [round(f, 1) for f in self.focal_px],
                "depth_pro_scale": None if self.depth_pro_scale is None else round(self.depth_pro_scale, 4),
                "method": self.method, "warnings": self.warnings}


def exif_focal_px(path: Path) -> float | None:
    """Focal length in pixels from EXIF, or None.

    The number lives in the Exif sub-IFD, not the top level, which is why an
    earlier version of this read nothing and the second opinion never ran.

    Only the 35 mm equivalent is usable. A bare focal length in millimetres
    needs the sensor width to become pixels, EXIF rarely carries it, and
    assuming a full frame sensor for a phone is wrong by a factor of about six.
    A wrong focal is worse than none here, because it would be fed to Depth Pro
    as if it were known.
    """
    try:
        from PIL import ExifTags, Image
    except ImportError:  # pragma: no cover
        return None
    try:
        with Image.open(path) as im:
            width = im.width
            exif = im.getexif()
            if not exif:
                return None
            tags = {ExifTags.TAGS.get(k, k): v for k, v in exif.items()}
            try:
                ifd = exif.get_ifd(0x8769)
                tags.update({ExifTags.TAGS.get(k, k): v for k, v in ifd.items()})
            except Exception:
                pass
            f35 = tags.get("FocalLengthIn35mmFilm")
            if f35:
                # 35 mm film is 36 mm wide, so focal in pixels is f35 / 36 * width.
                return float(f35) / 36.0 * width
    except Exception:
        return None
    return None


def upright_copies(paths: list[Path], work_dir: Path) -> tuple[list[Path], int]:
    """Photographs rotated as EXIF says they should be, written to ``work_dir``.

    A phone writes the sensor's own orientation and an Orientation tag saying
    how to turn it. Every one of these captures is tag 6, a quarter turn, and
    nothing downstream applies it: MapAnything reads the file as it sits on
    disk, so it was reconstructing rooms lying on their side, and the camera up
    vectors that set gravity pointed sideways with them.

    The messaging-app copies hid this by baking the rotation in, which is why
    they scored better than the originals until this was found.
    """
    from PIL import Image, ImageOps

    work_dir.mkdir(parents=True, exist_ok=True)
    out, rotated = [], 0
    for i, src in enumerate(paths):
        try:
            with Image.open(src) as im:
                tag = im.getexif().get(0x0112)
                if not tag or tag == 1:
                    out.append(src)
                    continue
                upright = ImageOps.exif_transpose(im)
                dst = work_dir / f"{i:03d}_{src.stem}.jpg"
                upright.convert("RGB").save(dst, quality=95)
                out.append(dst)
                rotated += 1
        except Exception as e:
            log.warning("could not read the orientation of %s: %s", src.name, e)
            out.append(src)
    if rotated:
        log.info("applied the EXIF orientation to %d of %d photos", rotated, len(paths))
    return out, rotated


def normals_from_world_pointmap(P: np.ndarray, valid: np.ndarray, centre: np.ndarray,
                                jump_frac: float = 0.08) -> tuple[np.ndarray, np.ndarray]:
    """Normals from a structured world point map, oriented toward the camera."""
    h, w = valid.shape
    du = np.zeros_like(P)
    dv = np.zeros_like(P)
    du[:, 1:-1] = P[:, 2:] - P[:, :-2]
    dv[1:-1, :] = P[2:, :] - P[:-2, :]
    ok = np.zeros((h, w), dtype=bool)
    ok[1:-1, 1:-1] = True
    ok &= valid
    ok[:, 1:-1] &= valid[:, 2:] & valid[:, :-2]
    ok[1:-1, :] &= valid[2:, :] & valid[:-2, :]
    rng = np.linalg.norm(P - centre, axis=-1)
    with np.errstate(invalid="ignore"):
        jump = np.zeros((h, w), dtype=bool)
        jump[:, 1:-1] |= np.abs(rng[:, 2:] - rng[:, :-2]) > jump_frac * np.maximum(rng[:, 1:-1], 1e-6)
        jump[1:-1, :] |= np.abs(rng[2:, :] - rng[:-2, :]) > jump_frac * np.maximum(rng[1:-1, :], 1e-6)
    ok &= ~jump
    n = np.cross(du, dv)
    norm = np.linalg.norm(n, axis=-1)
    ok &= norm > 1e-12
    with np.errstate(invalid="ignore", divide="ignore"):
        n = n / norm[..., None]
    n = np.nan_to_num(n)
    flip = np.einsum("ijk,ijk->ij", n, P - centre) > 0
    n[flip] *= -1.0
    return n, ok


class MapAnythingReconstructor:
    """Loaded once and reused across rooms; the checkpoint is several gigabytes."""

    def __init__(self, device: str, checkpoint: str = MAPANYTHING_CHECKPOINT) -> None:
        self.device_name = device
        self.checkpoint = checkpoint
        self._model = None

    def _load(self):
        if self._model is None:
            import torch
            from mapanything.models import MapAnything

            log.info("loading MapAnything (%s) on %s", self.checkpoint, self.device_name)
            self._model = MapAnything.from_pretrained(self.checkpoint).to(torch.device(self.device_name))
            self._model.eval()
        return self._model

    def infer(self, paths: list[Path]) -> list[dict]:
        import torch
        from mapanything.utils.image import load_images

        model = self._load()
        views = load_images([str(p) for p in paths], verbose=False)
        with torch.no_grad():
            preds = model.infer(views, memory_efficient_inference=True, use_amp=True,
                                amp_dtype="fp16" if self.device_name == "mps" else "bf16",
                                apply_mask=True, mask_edges=True, apply_confidence_mask=False)
        sync(self.device_name)
        out = []
        for p in preds:
            d = {"pts3d": p["pts3d"][0].float().cpu().numpy(),
                 "pose": p["camera_poses"][0].float().cpu().numpy(),
                 "intrinsics": p["intrinsics"][0].float().cpu().numpy()}
            if "mask" in p:
                m = p["mask"][0].float().cpu().numpy()
                d["mask"] = m[..., 0] > 0.5 if m.ndim == 3 else m > 0.5
            else:
                d["mask"] = np.ones(d["pts3d"].shape[:2], dtype=bool)
            out.append(d)
        return out


def reconstruct_room(room_id: str, paths: list[Path], reconstructor: MapAnythingReconstructor,
                     voxel_m: float = 0.03, pixel_stride: int = 1,
                     work_dir: Path | None = None) -> RoomReconstruction:
    """Photos in, a metric-in-MapAnything-units cloud out. Scaling happens after."""
    if len(paths) < 2:
        raise ValueError(f"{room_id}: the photo tier needs at least 2 images, got {len(paths)}")
    use = paths[:MAX_PHOTOS]
    focal = exif_focal_px(use[0])
    if work_dir is not None:
        use, n_rotated = upright_copies(use, Path(work_dir) / room_id)
    else:
        n_rotated = 0
    preds = reconstructor.infer(use)

    grid = VoxelGrid(voxel_m)
    centres, ups, focals = [], [], []
    buf_p, buf_n = [], []
    for pred in preds:
        P = pred["pts3d"]
        valid = pred["mask"] & np.isfinite(P).all(axis=-1)
        pose = pred["pose"]
        centre = pose[:3, 3]
        n, ok = normals_from_world_pointmap(P, valid, centre)
        keep = valid & ok
        if keep.any():
            buf_p.append(P[keep][::pixel_stride])
            buf_n.append(n[keep][::pixel_stride])
        centres.append(centre)
        ups.append(-pose[:3, 1])       # camera y is down in OpenCV axes
        focals.append(float(pred["intrinsics"][0, 0]))
    if not buf_p:
        raise ValueError(f"{room_id}: MapAnything returned no usable points")
    grid.add(np.concatenate(buf_p), np.concatenate(buf_n))
    pts, nrm, cnt = grid.result()
    if len(pts) < MIN_POINTS:
        raise ValueError(f"{room_id}: only {len(pts)} points survived, too few to fit a room")

    path = np.array(centres)
    cloud = Cloud(points=pts, normals=nrm, counts=cnt, camera_path=path,
                  camera_times=np.arange(len(path), dtype=np.float64),
                  frame_index=np.arange(len(path), dtype=np.int64), n_frames_used=len(use),
                  chunks=[])
    log.info("%s: %d photos, %d points, MapAnything focal %.0f px",
             room_id, len(use), len(pts), float(np.median(focals)))
    log.info("%s: %d of %d photos needed the EXIF orientation applied", room_id, n_rotated, len(use))
    return RoomReconstruction(room_id=room_id, cloud=cloud, camera_path=path,
                              camera_up=np.array(ups), focal_px=focals, n_photos=len(use),
                              scale_applied=1.0, measured_height_m=float("nan"),
                              exif_focal_px=focal, depth_pro_scale=None,
                              method="mapanything_unscaled",
                              views=[{"pts3d": p["pts3d"], "mask": p["mask"],
                                      "pose": p["pose"]} for p in preds], paths=list(use))
