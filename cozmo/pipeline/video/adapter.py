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
from cozmo.pipeline.video.intervals import IntervalBudget

log = logging.getLogger(__name__)


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


def plan_from_cloud(points: np.ndarray, normals: np.ndarray, camera_path: np.ndarray,
                    camera_times: np.ndarray, n_frames_used: int, input_path: Path, tier: Tier,
                    config: dict[str, Any], seed: int, pipeline, budget: IntervalBudget,
                    drift_model, warnings: list[str], assumptions: list[str]) -> PlanBuild:
    """Points, normals and a camera path to a Plan, through the LiDAR backend.

    ``budget`` carries this tier's interval widening; it is applied by editing
    the uncertainty block of the config the backend reads, so every interval in
    the plan, lengths, areas and openings alike, comes out of one place.
    """
    cfg = copy.deepcopy(config["pipeline"]["video"])
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
    faces = extract_faces(frame.to_frame(cloud.points[sel][:, [0, 2]]),
                          frame.rotate_normals(cloud.normals[sel]), height, cfg)
    faces, ghosts, ghost_report = _reject_ghosts(cloud, levels, frame, faces, cfg)
    if ghosts:
        warnings.append(f"Dropped {len(ghosts)} wall face(s) with no observed floor on either side; "
                        f"a mirror or a window reflection reads as a wall from one side only")
    elif not ghost_report.get("available", True):
        warnings.append("Mirror and glass rejection is not available in this build, so a wardrobe "
                        "mirror can still read as a wall")
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
    detail = {"n_cloud_points": int(len(points)), "n_wall_points": int(sel.sum()),
              "n_faces": len(faces), "n_ghost_faces": len(ghosts), "ghost_report": ghost_report,
              "manhattan_yaw_deg": round(float(np.degrees(frame.yaw)), 3),
              "floor_height_m": round(float(np.median(levels.floor.height_at(cloud.points[:, [0, 2]]))), 4),
              "n_rooms": len(plan.rooms), "n_openings": sum(len(r.openings) for r in plan.rooms),
              "interval_budget": budget.summary()}
    return PlanBuild(plan=plan, detail=detail,
                     geometry=(cloud, levels, frame, faces, rooms, openings, cfg))
