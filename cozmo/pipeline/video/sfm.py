"""Stage 2: COLMAP structure from motion over the extracted frames.

SIFT, sequential matching with overlap 10, incremental mapping, one shared
SIMPLE_RADIAL camera for the whole clip. Every sub-model with at least
``min_images`` registered frames is kept, not just the largest one: on the
sample scans COLMAP reliably splits a room into several chunks, and throwing
away all but the biggest one discards most of the capture (spike 2 measured 197
of 229 frames registered into some model but only 48 into the largest).

This module runs in a **subprocess**. pycolmap and torch each link their own
copy of libomp, and importing both into one interpreter aborts with
``OMP: Error #15``. The parent calls :func:`run_sfm`, which spawns
``python -m cozmo.pipeline.video.sfm``; the child writes one npz per chunk and
never imports torch.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)


class SfmError(RuntimeError):
    pass


def frames_digest(names: list[str]) -> str:
    """Identifies the exact frame set a reconstruction was built from."""
    return hashlib.sha256("\n".join(sorted(names)).encode()).hexdigest()[:16]


@dataclass
class SfmChunk:
    """One connected COLMAP sub-model, in SfM units and the sub-model's own frame."""

    index: int
    names: list[str]
    times_s: np.ndarray            # (n,) seconds into the clip
    cam_from_world: np.ndarray     # (n, 4, 4) world to camera, OpenCV axes
    obs_uv: np.ndarray             # (m, 2) pixel positions of sparse observations
    obs_z: np.ndarray              # (m,) camera-frame depth in SfM units
    obs_off: np.ndarray            # (n+1,) row offsets into obs_uv / obs_z
    xyz: np.ndarray                # (p, 3) sparse points, SfM units
    focal_px: float
    cam_params: np.ndarray
    cam_wh: tuple[int, int]
    mean_reproj_err_px: float
    scale_m_per_unit: float | None = None
    scale_frame_ratios: np.ndarray | None = None

    def __len__(self) -> int:
        return len(self.names)

    def centres(self) -> np.ndarray:
        """Camera centres in the chunk's own SfM frame."""
        R = self.cam_from_world[:, :3, :3]
        t = self.cam_from_world[:, :3, 3]
        return -np.einsum("nji,nj->ni", R, t)

    def observations(self, i: int) -> tuple[np.ndarray, np.ndarray]:
        s, e = int(self.obs_off[i]), int(self.obs_off[i + 1])
        return self.obs_uv[s:e], self.obs_z[s:e]


@dataclass
class SfmResult:
    chunks: list[SfmChunk]
    n_images: int
    n_models_found: int
    model_sizes: list[int]
    timings_s: dict[str, float]

    @property
    def registered(self) -> int:
        return sum(len(c) for c in self.chunks)

    def summary(self) -> dict:
        return {"n_images": self.n_images, "n_models_found": self.n_models_found,
                "model_sizes": self.model_sizes, "chunks_kept": len(self.chunks),
                "registered_images": self.registered,
                "registered_fraction": round(self.registered / self.n_images, 4) if self.n_images else 0.0,
                "chunk_sizes": [len(c) for c in self.chunks],
                "focal_px": [round(c.focal_px, 2) for c in self.chunks],
                "mean_reproj_err_px": [round(c.mean_reproj_err_px, 4) for c in self.chunks],
                "timings_s": self.timings_s}


# --------------------------------------------------------------------------
# child process
# --------------------------------------------------------------------------

def _reconstruct(image_dir: Path, out_dir: Path, overlap: int, max_image_size: int,
                 min_images: int, times_json: Path | None, seed: int, deterministic: bool) -> dict:
    import pycolmap

    # The mapper is randomised (initial pair trials, RANSAC) and threaded, so
    # both have to be pinned or the same clip splits differently on two runs.
    pycolmap.set_random_seed(seed)

    out_dir = Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    db = out_dir / "database.db"
    names_all = sorted(p.name for p in Path(image_dir).glob("*.jpg"))
    timings: dict[str, float] = {}

    t0 = time.perf_counter()
    reader = pycolmap.ImageReaderOptions()
    reader.camera_model = "SIMPLE_RADIAL"
    fe = pycolmap.FeatureExtractionOptions()
    fe.max_image_size = max_image_size
    fe.sift.max_num_features = 8192
    pycolmap.extract_features(database_path=db, image_path=image_dir,
                              camera_mode=pycolmap.CameraMode.SINGLE,
                              reader_options=reader, extraction_options=fe)
    timings["extract"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    pair = pycolmap.SequentialPairingOptions()
    pair.overlap = overlap
    pair.quadratic_overlap = True
    pair.loop_detection = False
    fm = pycolmap.FeatureMatchingOptions()
    if deterministic:
        # Geometric verification is RANSAC per pair and COLMAP gives each worker
        # its own generator, so a global seed is not enough on its own.
        fm.num_threads = 1
        pair.num_threads = 1
    pycolmap.match_sequential(database_path=db, matching_options=fm, pairing_options=pair)
    timings["match"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    opts = pycolmap.IncrementalPipelineOptions()
    opts.ba_refine_principal_point = False
    opts.random_seed = seed
    opts.mapper.random_seed = seed
    if deterministic:
        opts.num_threads = 1
        opts.mapper.num_threads = 1
    recs = pycolmap.incremental_mapping(database_path=db, image_path=image_dir,
                                        output_path=out_dir / "models", options=opts)
    timings["mapping"] = time.perf_counter() - t0
    if not recs:
        raise SfmError("COLMAP registered no images at all")

    times = json.loads(Path(times_json).read_text()) if times_json else {}
    sizes = sorted((r.num_reg_images() for r in recs.values()), reverse=True)
    kept = []
    for rec in recs.values():
        if rec.num_reg_images() < min_images:
            continue
        imgs = sorted((i for i in rec.images.values() if i.has_pose), key=lambda i: i.name)
        names = [im.name for im in imgs]
        cfw, uv, z, off = [], [], [], [0]
        for im in imgs:
            M = np.eye(4)
            M[:3, :4] = im.cam_from_world().matrix()
            cfw.append(M)
            for p2 in im.points2D:
                if not p2.has_point3D():
                    continue
                d = float((im.cam_from_world() * rec.points3D[p2.point3D_id].xyz)[2])
                if d <= 0.05:
                    continue
                uv.append(p2.xy)
                z.append(d)
            off.append(len(z))
        cam = list(rec.cameras.values())[0]
        kept.append({
            "names": names, "cfw": np.array(cfw),
            "times": np.array([times.get(n, float("nan")) for n in names]),
            "uv": np.array(uv, np.float32).reshape(-1, 2), "z": np.array(z, np.float32),
            "off": np.array(off, np.int64),
            "xyz": np.array([p.xyz for p in rec.points3D.values()], np.float64),
            "params": np.array(cam.params, np.float64),
            "wh": np.array([cam.width, cam.height], np.int64),
            "err": float(rec.compute_mean_reprojection_error()),
        })

    # Chunks are consecutive in time, so order them by when they happen.
    kept.sort(key=lambda c: float(np.nanmedian(c["times"])) if np.isfinite(c["times"]).any() else 0.0)
    for i, c in enumerate(kept):
        np.savez(out_dir / f"chunk_{i:02d}.npz", names=np.array(c["names"]), cam_from_world=c["cfw"],
                 times_s=c["times"], obs_uv=c["uv"], obs_z=c["z"], obs_off=c["off"], xyz=c["xyz"],
                 cam_params=c["params"], cam_wh=c["wh"], mean_reproj_err_px=np.array(c["err"]))
    index = {"n_images": len(names_all), "n_models_found": len(recs), "model_sizes": sizes,
             "n_chunks": len(kept), "min_images": min_images, "seed": seed,
             "deterministic": deterministic, "frames_digest": frames_digest(names_all),
             "timings_s": {k: round(v, 2) for k, v in timings.items()}}
    (out_dir / "sfm.json").write_text(json.dumps(index, indent=2) + "\n")
    return index


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--images", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--overlap", type=int, default=10)
    ap.add_argument("--max-image-size", type=int, default=1600)
    ap.add_argument("--min-images", type=int, default=15)
    ap.add_argument("--times-json", default=None)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--nondeterministic", action="store_true",
                    help="let the mapper use every core; faster, and not regenerable")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    index = _reconstruct(Path(a.images), Path(a.out), a.overlap, a.max_image_size,
                         a.min_images, Path(a.times_json) if a.times_json else None,
                         a.seed, not a.nondeterministic)
    print(json.dumps(index))
    return 0


# --------------------------------------------------------------------------
# parent process
# --------------------------------------------------------------------------

def load_chunks(out_dir: Path) -> list[SfmChunk]:
    out = []
    for i, p in enumerate(sorted(Path(out_dir).glob("chunk_*.npz"))):
        d = np.load(p, allow_pickle=True)
        params = d["cam_params"]
        out.append(SfmChunk(
            index=i, names=[str(x) for x in d["names"]], times_s=d["times_s"],
            cam_from_world=d["cam_from_world"], obs_uv=d["obs_uv"], obs_z=d["obs_z"],
            obs_off=d["obs_off"], xyz=d["xyz"], focal_px=float(params[0]), cam_params=params,
            cam_wh=(int(d["cam_wh"][0]), int(d["cam_wh"][1])),
            mean_reproj_err_px=float(d["mean_reproj_err_px"]),
        ))
    return out


def run_sfm(image_dir: Path, out_dir: Path, times_s: dict[str, float] | None = None,
            overlap: int = 10, max_image_size: int = 1600, min_images: int = 15,
            seed: int = 0, deterministic: bool = True, reuse: bool = True,
            timeout_s: float = 3600.0) -> SfmResult:
    """Run COLMAP in a child interpreter and load the chunks it wrote.

    The subprocess exists because pycolmap and torch cannot share a process.

    ``deterministic`` pins every seed and thread count the library exposes. On
    pycolmap 4.2 that is still not enough: two runs of one clip come back with
    the same chunk sizes but camera centres up to 6% of the chunk extent apart,
    which is a structurally different reconstruction rather than solver noise.
    So the reconstruction is cached as well. ``reuse`` loads an existing one
    whose frame digest matches, which is what makes a run regenerable and what
    lets a before-and-after comparison be about the change rather than about two
    draws from the mapper.
    """
    out_dir = Path(out_dir)
    if reuse:
        cached = _load_cached(out_dir, image_dir)
        if cached is not None:
            log.info("reusing the cached reconstruction in %s (%d chunks)", out_dir,
                     len(cached.chunks))
            return cached
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    args = [sys.executable, "-m", "cozmo.pipeline.video.sfm", "--images", str(image_dir),
            "--out", str(out_dir), "--overlap", str(overlap),
            "--max-image-size", str(max_image_size), "--min-images", str(min_images),
            "--seed", str(seed)]
    if not deterministic:
        args.append("--nondeterministic")
    if times_s:
        tj = out_dir.parent / "frame_times.json"
        tj.write_text(json.dumps(times_s))
        args += ["--times-json", str(tj)]
    t0 = time.perf_counter()
    r = subprocess.run(args, capture_output=True, text=True, timeout=timeout_s)
    wall = time.perf_counter() - t0
    if r.returncode != 0:
        tail = (r.stderr or "").strip().splitlines()[-6:]
        raise SfmError("COLMAP subprocess failed: " + " | ".join(tail))
    index = json.loads((out_dir / "sfm.json").read_text())
    index["timings_s"]["subprocess_wall"] = round(wall, 2)
    chunks = load_chunks(out_dir)
    if not chunks:
        raise SfmError(f"no COLMAP sub-model reached {min_images} images "
                       f"(sizes found: {index['model_sizes']})")
    return SfmResult(chunks=chunks, n_images=index["n_images"],
                     n_models_found=index["n_models_found"], model_sizes=index["model_sizes"],
                     timings_s=index["timings_s"])


def _load_cached(out_dir: Path, image_dir: Path) -> SfmResult | None:
    """An earlier reconstruction of exactly this frame set, or None."""
    index_path = out_dir / "sfm.json"
    if not index_path.is_file():
        return None
    try:
        index = json.loads(index_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    names = sorted(p.name for p in Path(image_dir).glob("*.jpg"))
    if index.get("frames_digest") != frames_digest(names):
        return None
    chunks = load_chunks(out_dir)
    if not chunks:
        return None
    index.setdefault("timings_s", {})["subprocess_wall"] = 0.0
    index["timings_s"]["reused"] = True
    return SfmResult(chunks=chunks, n_images=index["n_images"],
                     n_models_found=index["n_models_found"], model_sizes=index["model_sizes"],
                     timings_s=index["timings_s"])


if __name__ == "__main__":
    raise SystemExit(_main())
