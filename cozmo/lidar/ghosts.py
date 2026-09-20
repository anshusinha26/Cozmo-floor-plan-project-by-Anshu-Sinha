"""Reject wall faces that are not part of the building.

Glass, mirrors and views through a doorway put depth returns outside the
property. Those become wall faces that no room can be bounded by, and they
drag room polygons outwards.

The test is visibility, not geometry: a real wall has observed floor on at
least one side of it, because somebody stood there. The observed-floor mask
used here is built from floor points and the camera path only, so it does not
depend on the faces being tested and cannot argue in a circle.
"""

from __future__ import annotations

import numpy as np
from scipy import ndimage

from cozmo.lidar.cloud import Cloud
from cozmo.lidar.levels import Levels
from cozmo.lidar.walls import ManhattanFrame, WallFace

PROBE_OFFSET_M = 0.25
MIN_SUPPORTED_SHARE = 0.25


def observed_mask(cloud: Cloud, levels: Levels, frame: ManhattanFrame, cell: float,
                  reach_m: float = 0.35, barriers: np.ndarray | None = None
                  ) -> tuple[np.ndarray, np.ndarray]:
    """Cells where the floor was seen or the camera walked, dilated by ``reach_m``.

    With ``barriers`` the dilation is geodesic: it stops at wall cells instead
    of bleeding through them. The ghost test passes no barriers, because asking
    whether a face has floor beside it must not depend on that same face.

    Returns the mask and the frame-space origin of cell (0, 0).
    """
    xz = frame.to_frame(cloud.points[:, [0, 2]])
    path = frame.to_frame(cloud.camera_path[:, [0, 2]]) if len(cloud.camera_path) else np.zeros((0, 2))
    pts = np.vstack([xz, path]) if len(path) else xz
    lo = pts.min(axis=0) - 1.0
    hi = pts.max(axis=0) + 1.0
    shape = (int(np.ceil((hi[0] - lo[0]) / cell)) + 1, int(np.ceil((hi[1] - lo[1]) / cell)) + 1)

    floor = np.abs(cloud.points[:, 1] - levels.floor.height_at(cloud.points[:, [0, 2]])) <= 0.06
    floor &= np.abs(cloud.normals[:, 1]) >= 0.9
    mask = np.zeros(shape, dtype=bool)

    def put(points: np.ndarray) -> None:
        if len(points) == 0:
            return
        ij = np.floor((points - lo) / cell).astype(np.int64)
        ok = (ij[:, 0] >= 0) & (ij[:, 0] < shape[0]) & (ij[:, 1] >= 0) & (ij[:, 1] < shape[1])
        mask[ij[ok, 0], ij[ok, 1]] = True

    put(xz[floor])
    if len(path) > 1:
        # Densify the path so consecutive frames leave no gap.
        seg = []
        for a, b in zip(path[:-1], path[1:]):
            d = float(np.linalg.norm(b - a))
            n = max(int(d / (cell / 2)), 1)
            seg.append(a + (b - a) * np.linspace(0, 1, n + 1)[1:, None])
        put(np.vstack(seg))
    elif len(path):
        put(path)

    it = max(int(round(reach_m / cell)), 1)
    if barriers is None:
        return ndimage.binary_dilation(mask, np.ones((3, 3), bool), iterations=it), lo
    blocked = barriers if barriers.shape == mask.shape else np.zeros_like(mask)
    mask &= ~blocked
    for _ in range(it):
        mask = ndimage.binary_dilation(mask, np.ones((3, 3), bool)) & ~blocked
    return mask, lo


def face_support(face: WallFace, mask: np.ndarray, origin: np.ndarray, cell: float,
                 probe_m: float = PROBE_OFFSET_M, step_m: float = 0.10) -> float:
    """Share of the face's length that has observed floor on at least one side."""
    total = supported = 0.0
    for a, b in face.segments:
        n = max(int((b - a) / step_m), 1)
        along = np.linspace(a, b, n + 1)
        hits = np.zeros(len(along), dtype=bool)
        for sign in (-1.0, 1.0):
            p = np.empty((len(along), 2))
            p[:, face.axis] = face.pos + sign * probe_m
            p[:, 1 - face.axis] = along
            ij = np.floor((p - origin) / cell).astype(np.int64)
            ok = (ij[:, 0] >= 0) & (ij[:, 0] < mask.shape[0]) & (ij[:, 1] >= 0) & (ij[:, 1] < mask.shape[1])
            hit = np.zeros(len(along), dtype=bool)
            hit[ok] = mask[ij[ok, 0], ij[ok, 1]]
            hits |= hit
        total += b - a
        supported += (b - a) * float(hits.mean())
    return supported / total if total else 0.0


def reject_ghost_faces(cloud: Cloud, levels: Levels, frame: ManhattanFrame, faces: list[WallFace],
                       cfg: dict) -> tuple[list[WallFace], list[WallFace], dict]:
    """Split faces into kept and rejected. Returns (kept, ghosts, report)."""
    gcfg = cfg.get("ghost", {})
    if not gcfg.get("enabled", True):
        return list(faces), [], {"enabled": False}
    cell = gcfg.get("cell_m", 0.05)
    probe = gcfg.get("probe_offset_m", PROBE_OFFSET_M)
    min_share = gcfg.get("min_supported_share", MIN_SUPPORTED_SHARE)
    mask, origin = observed_mask(cloud, levels, frame, cell, gcfg.get("reach_m", 0.35))
    kept, ghosts = [], []
    for f in faces:
        if face_support(f, mask, origin, cell, probe) >= min_share:
            kept.append(f)
        else:
            ghosts.append(f)
    report = {
        "enabled": True,
        "n_faces": len(faces),
        "n_kept": len(kept),
        "n_rejected": len(ghosts),
        "rejected_length_m": float(sum(f.length() for f in ghosts)),
        "kept_length_m": float(sum(f.length() for f in kept)),
        "min_supported_share": min_share,
        "probe_offset_m": probe,
    }
    return kept, ghosts, report
