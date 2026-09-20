"""Video tier: one video file to one dimensioned plan.

The tier reads the video and nothing else. Stage order and why each stage is
where it is:

1. ``frames``        decode at about 10 fps, long side 1280, drop the blurriest fifth.
2. ``sfm``           COLMAP in a subprocess; every sub-model of 15 images or more is kept.
3. ``scale``         Depth Pro on the COLMAP focal, kept as a weak second opinion.
4. ``dense_prefit``  Depth Anything V2 fitted to the SfM sparse depths, cached per frame.
5. ``level``         each chunk alone: its own floor plane, then the scale that puts its
                     own camera at the height the capture protocol says it was held.
6. ``bridge``        MapAnything over a short overlap, reduced to a yaw and a slide,
                     because every chunk now stands upright on a common floor at its
                     own metric scale.
7. ``scale_solve``   one consistent set of scales from the prior, Depth Pro and the bridges.
8. ``drift``         Manhattan yaw snap per chunk, then a re-fuse from the cache.
9. ``assemble``      the same backend the LiDAR tier runs, through one adapter.

Fix loop 2 moved scale off the depth model. Loop 1 put the camera anywhere from
0.43 m to 2.61 m above its own floor, so the metric scale was wrong by a
different factor in every clip. The camera height is the one quantity here whose
answer is known before the capture starts, so it sets the scale, and the gap
between it and the depth model sets the intervals.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import numpy as np

from cozmo.contracts.models import Plan, Tier
from cozmo.io.inputs import validate_input
from cozmo.pipeline.base import Pipeline
from cozmo.pipeline.video import bridge as bridge_mod
from cozmo.pipeline.video import dense as dense_mod
from cozmo.pipeline.video import drift as drift_mod
from cozmo.pipeline.video import frames as frames_mod
from cozmo.pipeline.video import height_prior as height_mod
from cozmo.pipeline.video import scale as scale_mod
from cozmo.pipeline.video import scale_solve
from cozmo.pipeline.video import sfm as sfm_mod
from cozmo.pipeline.video import up as up_mod
from cozmo.pipeline.video.adapter import plan_from_cloud
from cozmo.pipeline.video.devices import pick_device
from cozmo.pipeline.video.intervals import build_budget
from cozmo.pipeline.video.probe import find_video

log = logging.getLogger(__name__)


class VideoPipeline(Pipeline):
    name = "video"
    version = "0.1.0"

    def __init__(self) -> None:
        super().__init__()
        self.debug_dir: Path | None = None
        self.debug_images: list[str] = []
        self.drift_report: dict[str, Any] | None = None
        self.report: dict[str, Any] = {}

    # ------------------------------------------------------------------
    def run(self, input_path: Path, tier: Tier, config: dict[str, Any], seed: int) -> Plan:
        if tier != "video":
            raise ValueError(f"VideoPipeline only handles the video tier, got {tier!r}")
        cfg = config["pipeline"]["video"]
        run_cfg = config.get("run", {})
        drift_on = bool(run_cfg.get("drift_correction", True))
        rotation = str(run_cfg.get("video_rotation", cfg["frames"].get("rotation", "auto")))
        device = pick_device(cfg.get("device"))
        # Frames and reconstructions are keyed by the capture, not by the output
        # directory, so two runs of one clip share them. That is what lets a
        # before-and-after comparison use the same chunks: the mapper is not
        # reproducible, so the cached reconstruction is the reproducible thing.
        cache_root = run_cfg.get("cache_root")
        if cache_root:
            work = Path(cache_root) / Path(input_path).name
        else:
            work = Path(self.debug_dir) if self.debug_dir else Path(input_path).parent / ".cozmo_video_work"
        work.mkdir(parents=True, exist_ok=True)
        spec = validate_input(Path(input_path), "video")
        if spec.rooms is not None:
            from cozmo.pipeline.video.multiroom import run_multi_room

            return run_multi_room(self, spec, Path(input_path), tier, config, seed)
        video = find_video(Path(input_path))
        single_room = _single_room_mode(run_cfg.get("single_room", "auto"), Path(input_path))
        warnings: list[str] = []
        assumptions: list[str] = [
            "Metric scale comes from a monocular depth model given the focal length COLMAP "
            "estimated from the same frames; nothing in this tier measured a distance directly",
        ]
        log.info("video tier on %s, device %s, rotation %s", video.name, device, rotation)

        with self.stage("frames"):
            fcfg = cfg["frames"]
            fs = frames_mod.extract(video, work / "frames", target_fps=fcfg["target_fps"],
                                    long_side=fcfg["long_side"], max_frames=fcfg["max_frames"],
                                    rotation=rotation, drop_blur_frac=fcfg["drop_blur_fraction"])

        with self.stage("sfm"):
            scfg = cfg["sfm"]
            result = sfm_mod.run_sfm(fs.dir, work / "sfm",
                                     times_s={n: float(t) for n, t in zip(fs.names, fs.times_s)},
                                     overlap=scfg["overlap"], max_image_size=scfg["max_image_size"],
                                     min_images=scfg["min_chunk_images"], seed=seed,
                                     deterministic=scfg.get("deterministic", True),
                                     reuse=scfg.get("reuse_reconstruction", True))
        if result.registered < 0.25 * len(fs):
            warnings.append(f"COLMAP registered only {result.registered} of {len(fs)} frames "
                            f"({result.registered / max(len(fs), 1):.0%}); the plan rests on a minority "
                            f"of the video")

        with self.stage("scale"):
            scale_rows = scale_mod.estimate_scales(result.chunks, fs, device,
                                                   max_frames=cfg["scale"]["max_frames"])

        with self.stage("dense_prefit"):
            dcfg = cfg["dense"]
            all_chunks = list(range(len(result.chunks)))
            build = dense_mod.build(result.chunks, all_chunks, fs, device,
                                    max_keyframes=dcfg["max_keyframes"],
                                    pixel_stride=dcfg["pixel_stride"],
                                    min_depth_m=dcfg["min_depth_m"], max_depth_m=dcfg["max_depth_m"],
                                    scale_tolerance=dcfg["scale_tolerance"])
        if not build.keyframes:
            raise ValueError("no keyframe could be fitted to the SfM sparse depths")

        with self.stage("level"):
            hcfg = cfg["height_prior"]
            target_h = float(run_cfg.get("camera_height_m") or hcfg["camera_height_m"])
            levels, scale_rows2 = height_mod.level_chunks(
                build, result.chunks, all_chunks, target_height_m=target_h,
                max_tilt_deg=cfg["gravity"]["max_tilt_deg"], seed=seed,
                voxel_m=cfg["gravity"]["voxel_m"])
            level_tf = {lv.chunk: lv.transform for lv in levels}
            for lv in levels:
                result.chunks[lv.chunk].scale_m_per_unit = lv.scale
            n_prior = sum(1 for lv in levels if lv.method == "camera_height_prior")
        assumptions.append(
            f"Camera-height prior: the phone was held at {target_h:.2f} m plus or minus "
            f"{hcfg['camera_height_sigma_m']:.2f} m, and each chunk is scaled so its own median "
            f"camera sits that far above its own floor plane. This is the capture protocol, not "
            f"a measurement, and its uncertainty is carried into every interval")
        if n_prior < len(levels):
            warnings.append(f"{len(levels) - n_prior} of {len(levels)} chunks had no usable floor "
                            f"plane and kept the monocular depth scale instead of the height prior")

        with self.stage("bridge"):
            bcfg = cfg["bridge"]
            br = bridge_mod.bridge_chunks(
                result.chunks, fs, device, overlap_frames=bcfg["overlap_frames"],
                max_rms_m=bcfg["max_rms_m"], max_rms_frac=bcfg["max_rms_frac"],
                max_scale_disagreement=bcfg["max_scale_disagreement"],
                overlap_window_s=bcfg["overlap_window_s"], min_span_m=bcfg["min_span_m"],
                scale_sem_sigmas=bcfg["scale_sem_sigmas"], levelled=True, transforms=level_tf,
                max_tilt_deg=bcfg["max_tilt_deg"], max_vertical_m=bcfg["max_vertical_m"],
                time_box_s=bcfg["time_box_s"])
        if br.timed_out:
            warnings.append("Chunk bridging hit its time box; the plan uses only what was bridged "
                            "before the stop")
        for d in br.dropped:
            warnings.append(f"Chunk {d['chunk']} ({d['n_images']} frames, "
                            f"{d['share_of_video']:.0%} of the video) could not be bridged to the "
                            f"main group and was dropped")

        build.group = list(br.group)
        transforms = dict(br.transforms)

        with self.stage("scale_solve"):
            bridge_ratios = []
            for a in br.attempts:
                if not a.accepted or a.scale_ratio is None or a.scale_ratio <= 0:
                    continue
                sa = result.chunks[a.a].scale_m_per_unit
                sb = result.chunks[a.b].scale_m_per_unit
                bridge_ratios.append((a.a, a.b, float(np.log(sa / sb) - np.log(a.scale_ratio))))
            by_chunk = {r.chunk: r for r in scale_rows2}
            solution = scale_solve.solve(
                br.group,
                {c: by_chunk[c].height_prior for c in br.group if c in by_chunk},
                {c: by_chunk[c].depth_pro for c in br.group if c in by_chunk},
                bridge_ratios)
            for c, v in solution.scales.items():
                result.chunks[c].scale_m_per_unit = v

        with self.stage("drift"):
            if drift_on:
                transforms, yaw_report = drift_mod.yaw_snap(
                    build, transforms, cfg, voxel_m=cfg["drift"]["voxel_m"],
                    max_yaw_deg=cfg["drift"]["max_yaw_deg"])
            else:
                yaw_report = drift_mod.disabled_report(br.group)
                warnings.append("Drift correction was disabled with --drift-correction off; "
                                "chunk placements are used as the bridge left them")
            model = drift_mod.YawSnapModel(yaw_report)

        with self.stage("fuse"):
            cloud = build.fuse(transforms, voxel_m=cfg["voxel_m"],
                               min_depth_m=cfg["dense"]["min_depth_m"],
                               max_depth_m=cfg["dense"]["max_depth_m"])

        if self.debug_dir is not None:
            # Dumped before assembly, so a run that fails to find a room can be
            # diagnosed from the cloud it failed on instead of being re-run.
            Path(self.debug_dir).mkdir(parents=True, exist_ok=True)
            np.savez_compressed(Path(self.debug_dir) / "fused_cloud.npz",
                                points=cloud.points.astype(np.float32),
                                normals=cloud.normals.astype(np.float32),
                                camera_path=cloud.camera_path.astype(np.float32),
                                camera_times=cloud.camera_times.astype(np.float32))

        group_frames = sum(len(result.chunks[i]) for i in br.group)
        cam_h = [lv.measured_height_m for lv in levels if np.isfinite(lv.measured_height_m)]
        # Two denominators, for two questions. The blur filter drops a fifth of
        # the frames by design, so the share of decoded frames can never pass
        # 80% and is the wrong thing to gate on; the share of the frames the
        # tier actually kept measures how much of the capture registered and
        # bridged, which is what the interval widening is about.
        share_kept = group_frames / max(len(fs), 1)
        share_decoded = group_frames / max(fs.n_decoded, 1)
        hp_rel = float(hcfg["camera_height_sigma_m"]) / max(target_h, 1e-6)
        disagreement = height_mod.scale_disagreement(scale_rows2)
        budget = build_budget(scale_rows, br.group, share_kept, cfg,
                              height_prior_rel=hp_rel, method_disagreement=disagreement)
        warnings.extend(budget.warnings())

        self.report = {
            "video": fs.summary(), "sfm": result.summary(), "scale": scale_rows,
            "height_prior": {"target_m": target_h, "rows": [r.summary() for r in scale_rows2],
                             "measured_heights_m": [round(h, 3) for h in cam_h],
                             "median_disagreement": round(height_mod.scale_disagreement(scale_rows2), 4)},
            "scale_solve": solution.summary(),
            "bridge": br.summary(), "dense": build.stats,
            "coverage": {"group_chunks": br.group, "frames_in_group": group_frames,
                         "frames_decoded": fs.n_decoded, "frames_kept": len(fs),
                         "share_of_kept_frames": round(share_kept, 4),
                         "share_of_video": round(share_decoded, 4)},
            "device": device, "interval_budget": budget.summary(), "single_room": single_room,
        }
        if self.debug_dir is not None:
            self._write_report()

        with self.stage("assemble"):
            built = plan_from_cloud(cloud.points, cloud.normals, cloud.camera_path,
                                    cloud.camera_times, build.stats["keyframes"], Path(input_path),
                                    tier, config, seed, self, budget, model, warnings, assumptions,
                                    single_room=single_room)
        plan = built.plan

        self.drift_report = {"tier": "video", "yaw_snap": yaw_report, "applied": drift_on,
                             "model": model.summary(),
                             "gravity": {"method": "per_chunk_floor_plane_before_bridging",
                                         "chunks": [{"chunk": lv.chunk, "method": lv.method,
                                                     "floor_inliers": round(lv.floor_inlier_fraction, 3),
                                                     "camera_height_m": None if not np.isfinite(lv.measured_height_m)
                                                     else round(lv.measured_height_m, 3)}
                                                    for lv in levels]}}
        self.report["geometry"] = built.detail
        self.report["stage_timings_s"] = dict(self.stage_timings_s)
        if self.debug_dir is not None:
            with self.stage("debug"):
                self._write_debug(built.geometry)
            self._write_report()
        log.info("video tier done: %d room(s), %.0f%% of the decoded video covered "
                 "(%.0f%% of the frames kept), %.1f s", len(plan.rooms), 100 * share_decoded,
                 100 * share_kept, sum(self.stage_timings_s.values()))
        return plan

    # ------------------------------------------------------------------
    def _write_report(self) -> None:
        Path(self.debug_dir).mkdir(parents=True, exist_ok=True)
        (Path(self.debug_dir) / "video_report.json").write_text(
            json.dumps(self.report, indent=2, default=_jsonable) + "\n", encoding="utf-8")

    def _write_debug(self, geometry) -> None:
        from cozmo.lidar.debug import write_debug_images

        cloud, levels, frame, faces, rooms, openings, cfg = geometry
        try:
            self.debug_images = write_debug_images(Path(self.debug_dir), cloud, levels, frame,
                                                   faces, rooms, openings, cfg)
        except Exception as e:  # debug images must never fail a run
            log.warning("debug images skipped: %s: %s", type(e).__name__, e)
            self.debug_images = []

    def write_drift_report(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.drift_report or {}, indent=2, default=_jsonable) + "\n",
                        encoding="utf-8")
        return path


def _single_room_mode(setting: str, input_path: Path) -> bool:
    """One clip of one room, or a walk through a property.

    A per-room capture folder holds one video and nothing else. A Stray Scanner
    export holds odometry and depth beside it and covers several spaces, so it
    keeps the segmenter.
    """
    from cozmo.io.inputs import looks_like_scan

    if setting in ("on", "true", True):
        return True
    if setting in ("off", "false", False):
        return False
    return not looks_like_scan(Path(input_path))


def _jsonable(o):
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, Path):
        return str(o)
    return str(o)
