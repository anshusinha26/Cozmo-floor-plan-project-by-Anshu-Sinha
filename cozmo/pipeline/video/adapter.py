"""The seam between the video tier and the plan-building backend.

Everything above this file is video specific: decoding, SfM, monocular depth,
chunk bridging. Everything below it is the same code the LiDAR tier runs, and
it is called here unchanged. One function crosses the seam,
:func:`plan_from_cloud`, and it takes points, normals and a camera path.

What differs is the configuration, not the code. Two things are widened for
this tier and both are measured, not guessed:

* **Wall-face tolerance.** Spike 2 fitted a line to one clean wall in the
  top-down band and got 4.35 cm RMS against 0.96 cm for the same wall from
  LiDAR. A face histogram binned for a 1 cm wall cannot find a 4 cm one, so the
  bin, the peak separation and the polygon snap distance all widen.
* **The systematic scale term.** The LiDAR tier claims 1%. Spike 2 measured 1.1%
  and 1.3% scale error on two scans, and this tier carries 3% until it is
  calibrated against tape. The measured per-chunk scale spread and a coverage
  penalty are folded into the same term, so a plan built from a fragment can
  never report a tight number.
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from cozmo.contracts.models import Plan, Tier
from cozmo.lidar.cloud import Cloud
from cozmo.lidar.levels import detect_levels
from cozmo.lidar.openings import WINDOWS_NOT_ATTEMPTED, adjacency_from_openings, find_openings
from cozmo.lidar.rooms import segment_rooms
from cozmo.lidar.walls import ManhattanFrame, extract_faces, wall_points
from cozmo.pipeline.lidar import MANHATTAN_ASSUMPTION, LidarPipeline
from cozmo.pipeline.video.intervals import IntervalBudget, clamp_plan_intervals
from cozmo.pipeline.video.singleroom import as_room_result, fit_single_room

log = logging.getLogger(__name__)


def _adaptive_wall_top(height_above_floor: np.ndarray, cfg: dict, warnings: list[str]) -> float:
    """How high a face must reach before it counts as a wall rather than furniture.

    The LiDAR tier asks for 1.5 m, which works when the scan sees a whole wall.
    This tier does not see one: the phone is carried at about 1.4 m and pointed
    level or down, so a reconstructed wall stops around 1.5 m and often lower.
    On bedroom_2_repeat every face topped out between 0.72 and 1.46 m, so nothing
    passed and the room came back as the camera path in a box.

    So the bar is relative to what was actually reconstructed: a wall is a face
    that reaches most of the way up whatever this capture saw. It is never
    stricter than the configured value, and never low enough for a table.
    """
    rcfg = cfg["room"]
    configured = float(rcfg["wall_min_top_m"])
    if not len(height_above_floor):
        return configured
    observed = float(np.percentile(height_above_floor, 95))
    floor_m = float(rcfg.get("wall_min_top_floor_m", 0.9))
    fraction = float(rcfg.get("wall_min_top_fraction", 0.75))
    adaptive = min(configured, max(floor_m, fraction * observed))
    if adaptive < configured:
        warnings.append(
            f"Walls were only reconstructed to about {observed:.2f} m above the floor, so a face "
            f"counts as a wall at {adaptive:.2f} m rather than the usual {configured:.2f} m. "
            f"Wall heights and the ceiling are not measured from this capture")
    cfg["room"]["wall_min_top_m"] = adaptive
    cfg["wall"]["wall_min_top_m"] = adaptive
    return adaptive


def _reject_ghosts(cloud, levels, frame, faces, cfg):
    """Drop wall faces with no observed floor on either side, when that stage exists.

    A wardrobe mirror puts a confident wall where the room actually continues,
    and it is a named hazard in these captures. The check lives in the LiDAR
    tier and is still landing there, so it is used when present and reported as
    missing when not, rather than duplicated here.
    """
    try:
        from cozmo.lidar.ghosts import reject_ghost_faces
    except ImportError:
        return list(faces), [], {"available": False,
                                 "note": "cozmo.lidar.ghosts is not in this build"}
    kept, ghosts, report = reject_ghost_faces(cloud, levels, frame, faces, cfg)
    report["available"] = True
    return kept, ghosts, report


class _Assembler(LidarPipeline):
    """Only for :meth:`LidarPipeline._assemble` and the opening helpers it uses.

    Subclassing is how the backend gets reused without editing it. ``run`` is
    never called on this object; the video pipeline owns the run.
    """

    name = "video-assembler"

    def __init__(self, provenance_source) -> None:
        super().__init__()
        self._provenance_source = provenance_source

    def provenance(self, input_path, tier, config, seed):
        return self._provenance_source.provenance(input_path, tier, config, seed)

    def run(self, input_path, tier, config, seed):  # pragma: no cover - never used
        raise NotImplementedError("the assembler only assembles; VideoPipeline owns the run")


@dataclass
class PlanBuild:
    """What crossed the seam: the plan, what to report, and the geometry for debug images."""

    plan: Plan
    detail: dict
    geometry: tuple


class _ScanShim:
    """``_assemble`` reads ``scan.root`` for provenance and nothing else."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)


CAMERA_HEIGHT_RANGE_M = (1.1, 1.8)


def camera_height_check(camera_path: np.ndarray, levels, points: np.ndarray) -> tuple[float, str | None]:
    """How far the phone sat above the reconstructed floor, and whether that is possible.

    Nothing in this tier measures a distance directly, so a scale error is
    invisible in the plan itself: a room scaled by 1.9 looks like a bigger room.
    The camera height is the one quantity with a known answer. A person carries a
    phone somewhere between knee and eye level, and every capture here was taken
    walking, so a reconstruction that puts the camera 0.43 m or 2.61 m above its
    own floor has a scale error of roughly that ratio, whatever its walls say.
    """
    if not len(camera_path):
        return float("nan"), None
    floor_y = float(np.median(levels.floor.height_at(camera_path[:, [0, 2]])))
    height = float(np.median(camera_path[:, 1]) - floor_y)
    lo, hi = CAMERA_HEIGHT_RANGE_M
    if lo <= height <= hi:
        return height, None
    factor = height / (0.5 * (lo + hi))
    return height, (
        f"The reconstruction puts the camera {height:.2f} m above its own floor, outside the "
        f"{lo:.1f} to {hi:.1f} m a hand-held phone can be. Every length in this plan is likely "
        f"off by about {factor:.1f}x, because the metric scale comes from a monocular depth "
        f"model and nothing here measured a distance directly")


def plan_from_cloud(points: np.ndarray, normals: np.ndarray, camera_path: np.ndarray,
                    camera_times: np.ndarray, n_frames_used: int, input_path: Path, tier: Tier,
                    config: dict[str, Any], seed: int, pipeline, budget: IntervalBudget,
                    drift_model, warnings: list[str], assumptions: list[str],
                    single_room: bool = False, tier_cfg: dict | None = None) -> PlanBuild:
    """Points, normals and a camera path to a Plan, through the LiDAR backend.

    ``budget`` carries this tier's interval widening; it is applied by editing
    the uncertainty block of the config the backend reads, so every interval in
    the plan, lengths, areas and openings alike, comes out of one place.
    """
    # ``config`` is what gets hashed into provenance, so it is never edited.
    # ``tier_cfg`` lets a caller reconstruct with another tier's parameters, which
    # is how the frames engine runs the photo tier's settings over a clip.
    cfg = copy.deepcopy(tier_cfg if tier_cfg is not None else config["pipeline"]["video"])
    cfg["uncertainty"] = budget.apply(cfg["uncertainty"])

    cloud = Cloud(points=points, normals=normals,
                  counts=np.ones(len(points), dtype=np.int64),
                  camera_path=camera_path, camera_times=camera_times,
                  frame_index=np.arange(len(camera_path), dtype=np.int64),
                  n_frames_used=n_frames_used, chunks=[])

    levels = detect_levels(cloud, cfg)
    sel = wall_points(cloud, levels, cfg)
    if sel.sum() < cfg["wall"]["peak_min_points"]:
        raise ValueError(f"too few wall points to reconstruct a plan: {int(sel.sum())}")
    frame = ManhattanFrame.fit(cloud.normals[sel], cloud.points[sel][:, [0, 2]])
    height = cloud.points[sel][:, 1] - levels.floor.height_at(cloud.points[sel][:, [0, 2]])
    top = _adaptive_wall_top(height, cfg, warnings)
    wall_xz = frame.to_frame(cloud.points[sel][:, [0, 2]])
    faces = extract_faces(wall_xz, frame.rotate_normals(cloud.normals[sel]), height, cfg)
    faces, ghosts, ghost_report = _reject_ghosts(cloud, levels, frame, faces, cfg)
    if ghosts:
        warnings.append(f"Dropped {len(ghosts)} wall face(s) with no observed floor on either side; "
                        f"a mirror or a window reflection reads as a wall from one side only")
    elif not ghost_report.get("available", True):
        warnings.append("Mirror and glass rejection is not available in this build, so a wardrobe "
                        "mirror can still read as a wall")
    cam_height, cam_warning = camera_height_check(camera_path, levels, points)
    if cam_warning:
        warnings.append(cam_warning)

    room_fit = None
    if single_room:
        # One clip, one room, and the person walked around inside it. Segmenting
        # free space out of a partly reconstructed floor either finds nothing or
        # finds a fragment and calls it the room; fitting around the whole camera
        # path cannot do either.
        path_frame = frame.to_frame(camera_path[:, [0, 2]])
        room_fit = fit_single_room(faces, path_frame, cfg,
                                   margin_m=cfg["room"].get("unsupported_margin_m", 0.35),
                                   allow_l=cfg["room"].get("allow_l_shape", True),
                                   wall_xz=wall_xz)
        rooms = as_room_result(room_fit, frame, cell_m=cfg["room"]["grid_m"])
        warnings.extend(room_fit.warnings)
        assumptions.extend(room_fit.assumptions)
        budget = budget.with_unsupported_sides(room_fit.unsupported_weight)
        cfg["uncertainty"] = budget.apply(cfg["uncertainty"])
    else:
        rooms = segment_rooms(cloud, levels, frame, faces, cfg)
        if not rooms.rooms:
            raise ValueError(
                f"no room segmented from {len(points)} points: {len(faces)} wall faces from "
                f"{int(sel.sum())} wall points, {len(camera_path)} camera poses. Either too little "
                f"of the room registered or the floor was never seen from enough of it")
    openings = find_openings(cloud, levels, frame, faces, rooms, cfg)
    adjacency = adjacency_from_openings(openings)

    assembler = _Assembler(pipeline)
    plan = assembler._assemble(_ScanShim(input_path), tier, config, seed, cloud, levels, frame,
                               faces, rooms, openings, adjacency, cfg,
                               list(warnings) + [WINDOWS_NOT_ATTEMPTED],
                               list(assumptions) + [MANHATTAN_ASSUMPTION], drift_model)
    plan = clamp_plan_intervals(plan, [])
    detail = {"n_cloud_points": int(len(points)), "n_wall_points": int(sel.sum()),
              "n_faces": len(faces), "n_ghost_faces": len(ghosts), "ghost_report": ghost_report,
              "wall_min_top_m": round(top, 3),
              "manhattan_yaw_deg": round(float(np.degrees(frame.yaw)), 3),
              "floor_height_m": round(float(np.median(levels.floor.height_at(cloud.points[:, [0, 2]]))), 4),
              "camera_height_above_floor_m": None if np.isnan(cam_height) else round(cam_height, 3),
              "camera_height_plausible": bool(cam_warning is None),
              "n_rooms": len(plan.rooms), "n_openings": sum(len(r.openings) for r in plan.rooms),
              "interval_budget": budget.summary(),
              "single_room": None if room_fit is None else room_fit.summary()}
    return PlanBuild(plan=plan, detail=detail,
                     geometry=(cloud, levels, frame, faces, rooms, openings, cfg))
