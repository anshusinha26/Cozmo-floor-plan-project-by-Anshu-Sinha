"""Stage 8: plane-anchored drift correction.

ARKit odometry drifts slowly: over a few minutes of walking, yaw creeps and
the floor height wanders by a few centimetres. Both show up as blurred wall
faces and a floor that is no longer one plane.

The correction anchors to the geometry the building itself provides. The
trajectory is cut into chunks of a few seconds. For each chunk:

1. yaw: the chunk's own wall normals have a dominant direction modulo 90
   degrees; the difference from the global Manhattan direction is the chunk's
   yaw error, removed by rotating the chunk about its own centroid so the
   chunk does not swing across the map.
2. height: the median height of the chunk's floor points against the global
   floor plane gives a vertical offset.
3. position: after yaw and height, the chunk's wall points are shifted along
   each horizontal axis by the median offset to the nearest global wall face.

Corrections larger than the configured limits are rejected rather than
applied, because a chunk that looks 20 degrees off is usually a chunk with
too little wall to estimate from, not a camera that really turned.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from cozmo.lidar.cloud import Chunk, Cloud
from cozmo.lidar.levels import Levels
from cozmo.lidar.walls import ManhattanFrame, WallFace, dominant_yaw


@dataclass
class ChunkCorrection:
    frames: list[int]
    centroid: np.ndarray
    yaw_delta: float = 0.0
    dy: float = 0.0
    shift: np.ndarray = field(default_factory=lambda: np.zeros(2))
    n_wall_points: int = 0
    rejected: list[str] = field(default_factory=list)


@dataclass
class DriftModel:
    corrections: dict[int, ChunkCorrection]
    enabled: bool = True

    def pose_fn(self, frame):
        c = self.corrections.get(frame.index)
        if c is None or not self.enabled:
            return frame.R, frame.t
        ca, sa = np.cos(-c.yaw_delta), np.sin(-c.yaw_delta)
        Ry = np.array([[ca, 0.0, sa], [0.0, 1.0, 0.0], [-sa, 0.0, ca]])
        t = Ry @ (frame.t - c.centroid) + c.centroid
        t = t - np.array([c.shift[0], c.dy, c.shift[1]])
        return Ry @ frame.R, t

    def summary(self) -> dict:
        cs = list(self.corrections.values())
        uniq = {id(c): c for c in cs}.values()
        if not uniq:
            return {"n_chunks": 0}
        yaw = np.array([abs(np.degrees(c.yaw_delta)) for c in uniq])
        dy = np.array([abs(c.dy) for c in uniq])
        sh = np.array([float(np.linalg.norm(c.shift)) for c in uniq])
        return {
            "n_chunks": len(uniq),
            "yaw_deg": {"mean": float(yaw.mean()), "max": float(yaw.max())},
            "height_m": {"mean": float(dy.mean()), "max": float(dy.max())},
            "shift_m": {"mean": float(sh.mean()), "max": float(sh.max())},
            "rejected": sorted({r for c in uniq for r in c.rejected}),
        }


def _wrap_to_quarter(delta: float) -> float:
    """Map a yaw difference into (-45, 45] degrees: walls repeat every 90 degrees."""
    q = np.pi / 2
    return float((delta + q / 2) % q - q / 2)


def estimate_drift(cloud: Cloud, levels: Levels, frame: ManhattanFrame, faces: list[WallFace],
                   cfg: dict) -> DriftModel:
    dcfg = cfg["drift"]
    max_yaw = np.radians(dcfg["max_yaw_deg"])
    face_pos = {axis: np.array(sorted(f.pos for f in faces if f.axis == axis)) for axis in (0, 1)}
    corrections: dict[int, ChunkCorrection] = {}
    for ch in cloud.chunks:
        c = ChunkCorrection(frames=list(ch.frames), centroid=ch.centroid)
        if len(ch.points):
            horizontal = np.abs(ch.normals[:, 1]) < cfg["horizontal_normal_cos"]
            above = ch.points[:, 1] > levels.floor.height_at(ch.points[:, [0, 2]]) + cfg["wall"]["min_height_above_floor_m"]
            wall = horizontal & above
            c.n_wall_points = int(wall.sum())
            if c.n_wall_points >= 500:
                yaw = dominant_yaw(ch.normals[wall], np.ones(int(wall.sum())))
                delta = _wrap_to_quarter(yaw - frame.yaw)
                if abs(delta) <= max_yaw:
                    c.yaw_delta = delta
                else:
                    c.rejected.append("yaw")
            else:
                c.rejected.append("too_few_wall_points")

            flat = np.abs(ch.normals[:, 1]) >= cfg["vertical_normal_cos"]
            near_floor = flat & (np.abs(ch.points[:, 1] - levels.floor.height_at(ch.points[:, [0, 2]])) < 0.15)
            if near_floor.sum() >= 200:
                dy = float(np.median(ch.points[near_floor, 1] - levels.floor.height_at(ch.points[near_floor][:, [0, 2]])))
                if abs(dy) <= dcfg["max_shift_m"]:
                    c.dy = dy
                else:
                    c.rejected.append("height")

            if c.n_wall_points >= 500:
                # 1D alignment per axis against the global faces, after yaw.
                ca, sa = np.cos(-c.yaw_delta), np.sin(-c.yaw_delta)
                Ry = np.array([[ca, 0.0, sa], [0.0, 1.0, 0.0], [-sa, 0.0, ca]])
                pts = (ch.points[wall] - ch.centroid) @ Ry.T + ch.centroid
                nrm = ch.normals[wall] @ Ry.T
                xz = frame.to_frame(pts[:, [0, 2]])
                nn = frame.rotate_normals(nrm)
                for axis in (0, 1):
                    belongs = (np.abs(nn[:, 0]) >= np.abs(nn[:, 2])) if axis == 0 else (np.abs(nn[:, 2]) > np.abs(nn[:, 0]))
                    if belongs.sum() < 200 or len(face_pos[axis]) == 0:
                        continue
                    v = xz[belongs, axis]
                    nearest = face_pos[axis][np.argmin(np.abs(v[:, None] - face_pos[axis][None, :]), axis=1)]
                    off = float(np.median(v - nearest))
                    if abs(off) <= dcfg["max_shift_m"]:
                        c.shift[axis] = off
                    else:
                        c.rejected.append(f"shift_axis_{axis}")
                # Shift is measured in the Manhattan frame; rotate it back to world.
                world = frame.to_world(np.array([c.shift])) - frame.to_world(np.zeros((1, 2)))
                c.shift = world[0]
        for f in ch.frames:
            corrections[f] = c
    return DriftModel(corrections)
