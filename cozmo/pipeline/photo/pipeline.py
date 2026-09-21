"""Photo tier: one folder per room, two or more stills each, images only.

Per room: MapAnything for geometry, the camera-height prior for metric scale,
the single-room fitter from fix loop 2 for the shape. Then every room is
attached to a connector to make one property.

Scale never comes from MapAnything. Spike 1 measured its depth at 0.70x while
its trajectory ran 2.5 to 3.9 times long, so its own scale is not even
self-consistent. Depth Pro is asked for a second opinion when EXIF carries a
focal length, and its only job is to widen intervals when it disagrees.
"""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from cozmo.contracts.models import Plan, Renders, Tier
from cozmo.io.inputs import validate_input
from cozmo.pipeline.base import Pipeline
from cozmo.pipeline.photo import merge as merge_mod
from cozmo.pipeline.photo import openings as openings_mod
from cozmo.pipeline.photo import room as room_mod
from cozmo.pipeline.photo import stitch as stitch_mod
from cozmo.pipeline.video.adapter import plan_from_cloud
from cozmo.pipeline.video.devices import pick_device
from cozmo.pipeline.video.drift import YawSnapModel
from cozmo.pipeline.video.intervals import IntervalBudget
from cozmo.pipeline.video.up import fit_floor, rotation_between

log = logging.getLogger(__name__)


class PhotoPipeline(Pipeline):
    name = "photo"
    version = "0.1.0"

    def __init__(self) -> None:
        super().__init__()
        self.debug_dir: Path | None = None
        self.debug_images: list[str] = []
        self.drift_report: dict[str, Any] | None = None
        self.report: dict[str, Any] = {}

    def run(self, input_path: Path, tier: Tier, config: dict[str, Any], seed: int) -> Plan:
        if tier != "photo":
            raise ValueError(f"PhotoPipeline only handles the photo tier, got {tier!r}")
        cfg = config["pipeline"]["photo"]
        run_cfg = config.get("run", {})
        device = pick_device(cfg.get("device"))
        target_h = float(run_cfg.get("camera_height_m") or cfg["height_prior"]["camera_height_m"])
        sigma = float(cfg["height_prior"]["camera_height_sigma_m"])
        spec = validate_input(Path(input_path), "photo")
        if not spec.rooms:
            raise ValueError("the photo tier needs one subfolder per room")
        excluded = set(run_cfg.get("exclude") or [])
        repeats = set(run_cfg.get("repeat_rooms") or [])
        room_inputs = [r for r in spec.rooms if r.room_id not in excluded]
        if not room_inputs:
            raise ValueError(f"every room folder was excluded: {sorted(excluded)}")

        warnings: list[str] = []
        assumptions: list[str] = [
            f"Camera-height prior: the photos were taken from about {target_h:.2f} m plus or minus "
            f"{sigma:.2f} m, and each room is scaled so its own median camera sits that far above "
            f"its own floor plane. Nothing in this tier measured a distance directly",
            "MapAnything supplies the geometry and the camera poses; its own metric scale is "
            "discarded, because spike 1 measured its depth at 0.70x while its trajectory ran 2.5 "
            "to 3.9 times long, so the two are not consistent with each other",
        ]

        reconstructor = room_mod.MapAnythingReconstructor(device)
        ocfg = cfg["openings"]
        detector = (openings_mod.DoorDetector(device) if ocfg.get("enabled", True) else None)
        openings_note: list[str] = []
        per_room: dict[str, Plan] = {}
        rows: list[dict] = []
        polygons: dict[str, list[tuple[float, float]]] = {}
        doors: dict[str, list[dict]] = {}
        areas: dict[str, float] = {}

        for room_input in room_inputs:
            rid = room_input.room_id
            with self.stage(f"room:{rid}"):
                try:
                    plan, row = self._one_room(rid, room_input.files, reconstructor, cfg, config,
                                               seed, target_h, sigma, device, input_path,
                                               detector, ocfg, openings_note)
                except (ValueError, RuntimeError) as e:
                    warnings.append(f"{rid}: no plan could be built ({e})")
                    rows.append({"room_id": rid, "error": str(e)})
                    continue
            per_room[rid] = plan
            rows.append(row)
            polygons[rid] = [tuple(p) for p in plan.rooms[0].polygon]
            areas[rid] = plan.rooms[0].floor_area_m2.value
            doors[rid] = [{"id": o.id, "width_m": o.width_m.value,
                           "centre": _opening_centre(plan.rooms[0], o)}
                          for o in plan.rooms[0].openings if o.type == "door"]

        if not per_room:
            raise ValueError("no room could be reconstructed from this capture")

        with self.stage("stitch"):
            # A repeat capture is a second look at a room that is already in the
            # property. Including it would put the same room in the plan twice,
            # so it is reconstructed and reported but not placed.
            stitch_ids = [r for r in per_room if r not in repeats]
            if not stitch_ids:
                raise ValueError("every reconstructed room was marked as a repeat")
            connector = stitch_mod.choose_connector(
                stitch_ids, {k: areas[k] for k in stitch_ids}, run_cfg.get("connector"))
            result = stitch_mod.stitch({k: polygons[k] for k in stitch_ids},
                                       {k: doors.get(k, []) for k in stitch_ids}, connector)
            assumptions.append(stitch_mod.STAR_ASSUMPTION)
        for note in spec.skipped:
            warnings.append(f"Skipped {note}")
        for rid in sorted(excluded):
            warnings.append(f"{rid} was excluded by --exclude and is not treated as a room")
        for rid in sorted(repeats & set(per_room)):
            warnings.append(f"{rid} is a repeat capture: it is measured and reported, but it is "
                            f"not placed in the property, because it is the same room as another")

        capture, run = self.provenance(Path(input_path), tier, config, seed)
        with self.stage("assemble"):
            plan = merge_mod.merge({k: v for k, v in per_room.items() if k in stitch_ids},
                                   result, capture, run, cfg["uncertainty"]["ci_level"],
                                   warnings, assumptions)

        if openings_note:
            warnings.append(f"Openings were not attempted at this tier: {openings_note[0]}. "
                            f"Doors and pass-throughs are absent from this plan, not confirmed absent")
        self.report = {"device": device, "rooms": rows, "stitch": result.summary(),
                       "excluded": sorted(excluded), "repeat_rooms": sorted(repeats),
                       "repeat_measurements": {k: _room_summary(per_room[k])
                                               for k in sorted(repeats & set(per_room))},
                       "openings_note": openings_note[0] if openings_note else None,
                       "camera_height_m": target_h, "n_rooms": len(per_room)}
        self.drift_report = {"tier": "photo", "applied": False,
                             "note": "the photo tier has no trajectory to drift"}
        if self.debug_dir is not None:
            Path(self.debug_dir).mkdir(parents=True, exist_ok=True)
            (Path(self.debug_dir) / "photo_report.json").write_text(
                json.dumps(self.report, indent=2, default=str) + "\n", encoding="utf-8")
        return plan.model_copy(update={"renders": Renders()})

    # ------------------------------------------------------------------
    def _one_room(self, rid: str, files: list[Path], reconstructor, cfg, config, seed: int,
                  target_h: float, sigma: float, device: str, input_path: Path,
                  detector=None, ocfg: dict | None = None, openings_note: list | None = None,
                  tier: str = "photo", extra_warnings: list[str] | None = None):
        work = Path(self.debug_dir) / "upright" if self.debug_dir else Path(tempfile.mkdtemp())
        rec = room_mod.reconstruct_room(rid, list(files), reconstructor,
                                        voxel_m=cfg["voxel_m"],
                                        pixel_stride=cfg["pixel_stride"], work_dir=work)
        cloud = rec.cloud
        g = fit_floor(cloud.points, cloud.normals, rec.camera_up,
                      max_tilt_deg=cfg["gravity"]["max_tilt_deg"], seed=seed)
        R = rotation_between(g.normal, np.array([0.0, 1.0, 0.0]))
        height = float(np.median(rec.camera_path @ g.normal) - g.offset_m)
        warnings: list[str] = []
        if g.method.startswith("ransac") and np.isfinite(height) and height > 0.05:
            s = target_h / height
            method = "camera_height_prior"
        else:
            s = 1.0
            method = "unscaled_no_floor_plane"
            warnings.append(f"{rid}: no floor plane was found, so this room carries "
                            f"MapAnything's own scale, which spike 1 measured at 0.70x")
        points = (cloud.points @ R.T) * s
        normals = cloud.normals @ R.T
        path = (rec.camera_path @ R.T) * s
        drop = np.array([0.0, float(np.percentile(points[:, 1], 1.0)), 0.0])
        points = points - drop
        path = path - drop

        rec.scale_applied = s
        rec.measured_height_m = height
        rec.method = method
        if extra_warnings:
            warnings.extend(extra_warnings)
        budget = IntervalBudget(systematic=cfg["uncertainty"]["systematic_scale_bias"],
                                height_prior=sigma / max(target_h, 1e-6),
                                coverage=1.0,
                                min_coverage=cfg["uncertainty"]["min_coverage"],
                                low_coverage_factor=cfg["uncertainty"]["low_coverage_factor"],
                                abs_floor_m=cfg["uncertainty"]["abs_floor_m"])
        built = plan_from_cloud(points, normals, path,
                                np.arange(len(path), dtype=np.float64), len(files),
                                Path(input_path), tier, config, seed, self, budget,
                                YawSnapModel({"applied": False, "per_chunk": [],
                                              "note": "the photo tier has no trajectory to drift"}),
                                warnings=warnings, assumptions=[], single_room=True,
                                tier_cfg=cfg)
        plan = built.plan
        row = rec.summary()
        row["fitted"] = built.detail.get("single_room")
        row["interval_budget"] = built.detail.get("interval_budget")

        if detector is not None and plan.rooms:
            def to_frame(pts: np.ndarray) -> np.ndarray:
                return (pts @ R.T) * s - drop

            try:
                dets = openings_mod.detect_doors(rid, rec, to_frame, detector,
                                                 ocfg["min_score"], ocfg["max_photos"])
                doors, dropped = openings_mod.attach_doors(
                    plan.rooms[0], dets, cfg["uncertainty"]["ci_level"])
                if doors:
                    room = plan.rooms[0].model_copy(update={"openings": doors})
                    plan = plan.model_copy(update={"rooms": [room]})
                row["doors"] = [d.summary() for d in dets]
                row["doors_dropped_off_wall"] = dropped
            except openings_mod.OpeningsUnavailable as e:
                if openings_note is not None and not openings_note:
                    openings_note.append(str(e))
                row["doors"] = None
        return plan, row


def _room_summary(plan) -> dict:
    """A repeat room's measurements, kept out of the plan but not out of the report.

    Intervals travel with the values: a repeat room is scored against tape like
    any other, so reporting it without its interval would make it look either
    better or worse than it is.
    """
    r = plan.rooms[0]
    seen: dict[float, dict] = {}
    for w in r.walls:
        key = round(w.length_m.value, 3)
        seen.setdefault(key, {"value": key, "ci_low": round(w.length_m.ci_low, 3),
                              "ci_high": round(w.length_m.ci_high, 3)})
    return {"walls_m": sorted(seen.values(), key=lambda d: -d["value"]),
            "ceiling_m": {"value": round(r.ceiling_height_m.value, 3),
                          "ci_low": round(r.ceiling_height_m.ci_low, 3),
                          "ci_high": round(r.ceiling_height_m.ci_high, 3)},
            "area_m2": round(r.floor_area_m2.value, 3)}


def _write_drift_report(self, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(self.drift_report or {}, indent=2, default=str) + "\n",
                    encoding="utf-8")
    return path


PhotoPipeline.write_drift_report = _write_drift_report


def _opening_centre(room, opening) -> tuple[float, float]:
    """World position of an opening's centre, from its wall and offset."""
    wall = next((w for w in room.walls if w.id == opening.wall_id), None)
    if wall is None:
        return (0.0, 0.0)
    a = np.array(wall.start, dtype=float)
    b = np.array(wall.end, dtype=float)
    d = b - a
    ln = float(np.linalg.norm(d))
    if ln < 1e-9:
        return (float(a[0]), float(a[1]))
    t = (opening.offset_along_wall_m.value + opening.width_m.value / 2) / ln
    p = a + np.clip(t, 0.0, 1.0) * d
    return (float(p[0]), float(p[1]))
