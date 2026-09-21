"""Stage 7 drift: a Manhattan yaw snap per SfM chunk.

The LiDAR tier corrects drift inside one continuous trajectory. This tier has a
different failure: each COLMAP chunk is internally rigid, and the error is in
how the chunks sit relative to each other, carried in from the MapAnything
bridge. A bridge fixes a chunk's yaw to within a few degrees, not to within a
fraction of one, and a couple of degrees over a 4 m room is several centimetres
of wall offset.

So the correction is a yaw snap. Each chunk's own wall normals have a dominant
direction modulo 90 degrees; the difference from the direction the whole group
agrees on is the chunk's yaw error, and the chunk is rotated about its own
camera centroid to remove it. Rotating about the chunk's own centroid keeps it
where it is instead of swinging it across the room.

A correction larger than the configured limit is rejected rather than applied:
a chunk that looks 15 degrees off is usually a chunk with too little wall to
measure, not a chunk that is really turned.
"""

from __future__ import annotations

import logging

import numpy as np

from cozmo.lidar.walls import dominant_yaw
from cozmo.pipeline.video.dense import DenseBuild, Transforms

log = logging.getLogger(__name__)

MIN_WALL_POINTS = 400


def apply_rotation(transforms: Transforms, R: np.ndarray) -> Transforms:
    """Left-multiply every chunk placement, for example to stand the cloud upright."""
    return {k: (R @ Rg, R @ tg) for k, (Rg, tg) in transforms.items()}


def wrap_to_quarter(delta: float) -> float:
    """Map a yaw difference into (-45, 45] degrees: walls repeat every 90 degrees."""
    q = np.pi / 2
    return float((delta + q / 2) % q - q / 2)


def _wall_mask(points: np.ndarray, normals: np.ndarray, floor_y: float,
               horizontal_cos: float, low_m: float, high_m: float) -> np.ndarray:
    h = points[:, 1] - floor_y
    return (np.abs(normals[:, 1]) < horizontal_cos) & (h > low_m) & (h < high_m)


def yaw_snap(build: DenseBuild, transforms: Transforms, cfg: dict, voxel_m: float = 0.06,
             max_yaw_deg: float = 6.0, coarse: int = 2) -> tuple[Transforms, dict]:
    """Rotate each chunk so its walls line up with the group's Manhattan direction.

    ``transforms`` must already be gravity aligned (y up). Returns new
    transforms and a report; a single-chunk group is returned unchanged.
    """
    horiz = float(cfg.get("horizontal_normal_cos", 0.25))
    low = float(cfg["wall"]["min_height_above_floor_m"])
    high = low + 2.5
    report = {"applied": True, "max_yaw_deg": max_yaw_deg, "per_chunk": []}
    if len(build.group) < 2:
        report["note"] = "single chunk: nothing to snap against"
        return transforms, report

    whole = build.fuse(transforms, voxel_m=voxel_m, coarse=coarse)
    if len(whole.points) < MIN_WALL_POINTS:
        report["note"] = "too few fused points to measure a Manhattan direction"
        return transforms, report
    floor_y = float(np.percentile(whole.points[:, 1], 1.0))
    sel = _wall_mask(whole.points, whole.normals, floor_y, horiz, low, high)
    if sel.sum() < MIN_WALL_POINTS:
        report["note"] = "too few wall points to measure a Manhattan direction"
        return transforms, report
    global_yaw = dominant_yaw(whole.normals[sel], np.ones(int(sel.sum())))
    report["global_yaw_deg"] = round(float(np.degrees(global_yaw)), 3)

    out = dict(transforms)
    for ci in build.group:
        one = build.fuse(transforms, voxel_m=voxel_m, only={ci}, coarse=coarse)
        row = {"chunk": ci, "n_wall_points": 0, "yaw_delta_deg": 0.0, "rejected": None}
        if len(one.points):
            m = _wall_mask(one.points, one.normals, floor_y, horiz, low, high)
            row["n_wall_points"] = int(m.sum())
            if m.sum() >= MIN_WALL_POINTS:
                delta = wrap_to_quarter(dominant_yaw(one.normals[m], np.ones(int(m.sum()))) - global_yaw)
                row["yaw_delta_deg"] = round(float(np.degrees(delta)), 3)
                if abs(np.degrees(delta)) <= max_yaw_deg:
                    c = one.camera_path.mean(axis=0) if len(one.camera_path) else one.points.mean(axis=0)
                    ca, sa = np.cos(-delta), np.sin(-delta)
                    Ry = np.array([[ca, 0.0, sa], [0.0, 1.0, 0.0], [-sa, 0.0, ca]])
                    Rg, tg = transforms[ci]
                    out[ci] = (Ry @ Rg, Ry @ (tg - c) + c)
                else:
                    row["rejected"] = "yaw beyond the limit"
            else:
                row["rejected"] = "too few wall points"
        else:
            row["rejected"] = "no fused points"
        report["per_chunk"].append(row)
    applied = [r for r in report["per_chunk"] if r["rejected"] is None]
    log.info("yaw snap: %d of %d chunks corrected, worst applied %.2f degrees",
             len(applied), len(build.group),
             max((abs(r["yaw_delta_deg"]) for r in applied), default=0.0))
    return out, report


def disabled_report(group: list[int]) -> dict:
    return {"applied": False, "per_chunk": [], "note": "drift correction disabled with --drift-correction off",
            "n_chunks": len(group)}


class YawSnapModel:
    """Stands in for the LiDAR tier's DriftModel where the contract wants a summary."""

    def __init__(self, report: dict) -> None:
        self.report = report

    def summary(self) -> dict:
        rows = self.report.get("per_chunk", [])
        applied = [r for r in rows if r.get("rejected") is None]
        return {"method": "manhattan_yaw_snap_per_sfm_chunk",
                "applied": bool(self.report.get("applied")),
                "n_chunks": len(rows),
                "n_corrected": len(applied),
                "yaw_deg": {"mean": round(float(np.mean([abs(r["yaw_delta_deg"]) for r in applied])), 3),
                            "max": round(float(np.max([abs(r["yaw_delta_deg"]) for r in applied])), 3)}
                if applied else {"mean": 0.0, "max": 0.0},
                "rejected": sorted({r["rejected"] for r in rows if r.get("rejected")}),
                "note": self.report.get("note", "")}
