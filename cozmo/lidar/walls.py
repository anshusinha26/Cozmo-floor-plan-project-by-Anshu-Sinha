"""Stages 3 and 4: wall points, the Manhattan frame, and wall faces.

Wall points are those with a near-horizontal normal, at least 0.3 m above the
floor (below that is skirting and floor clutter) and below the ceiling band.

The Manhattan assumption: interior walls of one property mostly meet at right
angles, so all wall normal azimuths collapse modulo 90 degrees into one
dominant direction. Rotating the world by that angle makes walls axis
aligned, which turns wall fitting into two 1D problems. This is recorded in
the plan's assumptions, because it is wrong for a curved or a 45 degree wall,
and such a wall will show up as a missing face rather than a silent error.

A "face" is one side of a wall. Two faces about 10 to 25 cm apart are the two
sides of the same physical wall; the room polygons touch the faces, so room
areas are measured inside faces as a tape measure would.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.signal import find_peaks

from cozmo.lidar.cloud import Cloud
from cozmo.lidar.levels import Levels


def dominant_yaw(normals: np.ndarray, weights: np.ndarray) -> float:
    """Dominant wall direction in radians, in [0, pi/2).

    Azimuths are multiplied by 4 before averaging so that directions 90
    degrees apart (the two wall orientations of a rectangular room) reinforce
    instead of cancelling, then divided back.
    """
    az = np.arctan2(normals[:, 2], normals[:, 0])
    c = float(np.sum(weights * np.cos(4 * az)))
    s = float(np.sum(weights * np.sin(4 * az)))
    yaw = np.arctan2(s, c) / 4.0
    return float(yaw % (np.pi / 2))


@dataclass
class ManhattanFrame:
    """Rotation about world y that makes walls axis aligned, plus a shift to the cloud centroid."""

    yaw: float
    origin: np.ndarray  # (2,) world xz subtracted before rotation

    @classmethod
    def fit(cls, normals: np.ndarray, xz: np.ndarray, weights: np.ndarray | None = None) -> "ManhattanFrame":
        w = np.ones(len(normals)) if weights is None else weights
        return cls(dominant_yaw(normals, w), xz.mean(axis=0))

    @property
    def _R(self) -> np.ndarray:
        c, s = np.cos(-self.yaw), np.sin(-self.yaw)
        return np.array([[c, -s], [s, c]])

    def to_frame(self, xz: np.ndarray) -> np.ndarray:
        return (xz - self.origin) @ self._R.T

    def to_world(self, xz: np.ndarray) -> np.ndarray:
        return xz @ self._R + self.origin

    def rotate_normals(self, normals: np.ndarray) -> np.ndarray:
        n2 = normals[:, [0, 2]] @ self._R.T
        return np.column_stack([n2[:, 0], normals[:, 1], n2[:, 1]])


@dataclass
class WallFace:
    """One side of a wall in the Manhattan frame.

    ``axis`` 0 means the normal points along x and the face runs along z;
    ``axis`` 1 is the transpose. ``pos`` is the coordinate along the normal.
    """

    axis: int
    pos: float
    segments: list[tuple[float, float]] = field(default_factory=list)
    n_points: int = 0
    resid_std: float = 0.0
    sign: float = 0.0  # mean normal direction: which side the observer was on

    def length(self) -> float:
        return float(sum(b - a for a, b in self.segments))

    def extent(self) -> tuple[float, float]:
        return (min(a for a, _ in self.segments), max(b for _, b in self.segments)) if self.segments else (0.0, 0.0)


def wall_points(cloud: Cloud, levels: Levels, cfg: dict) -> np.ndarray:
    """Boolean mask of points that belong to walls."""
    wcfg = cfg["wall"]
    horizontal = np.abs(cloud.normals[:, 1]) < cfg["horizontal_normal_cos"]
    above_floor = cloud.points[:, 1] > levels.floor.height_at(cloud.points[:, [0, 2]]) + wcfg["min_height_above_floor_m"]
    sel = horizontal & above_floor
    if levels.ceiling is not None:
        sel &= cloud.points[:, 1] < levels.ceiling.y - wcfg["max_height_below_ceiling_m"]
    return sel


def _runs(along: np.ndarray, bin_m: float, max_gap_m: float, min_run_m: float) -> list[tuple[float, float]]:
    """Merged, filtered segments along a face, from occupancy of ``along`` positions.

    Segment ends come from the extreme points inside the end bins, not from the
    bin edges, so a 5 cm occupancy bin does not add up to 10 cm to every wall.
    """
    if len(along) == 0:
        return []
    origin = float(np.floor(along.min() / bin_m) * bin_m)
    n_bins = int(np.ceil((along.max() - origin) / bin_m)) + 1
    b = np.clip(((along - origin) / bin_m).astype(int), 0, n_bins - 1)
    occ = np.zeros(n_bins, dtype=bool)
    occ[b] = True
    idx = np.flatnonzero(occ)
    if len(idx) == 0:
        return []
    breaks = np.flatnonzero(np.diff(idx) > max(1, int(round(max_gap_m / bin_m))))
    out = []
    for g in np.split(idx, breaks + 1):
        inside = (b >= g[0]) & (b <= g[-1])
        a0, a1 = float(along[inside].min()), float(along[inside].max())
        if a1 - a0 >= min_run_m:
            out.append((a0, a1))
    return out


def extract_faces(xz: np.ndarray, normals: np.ndarray, cfg: dict) -> list[WallFace]:
    """Wall faces per axis: histogram peaks along the normal, extents from occupancy runs.

    Points are assigned to the axis their normal is closest to, so a point on
    an east wall never votes for a north wall's position.
    """
    wcfg = cfg["wall"]
    nx = np.abs(normals[:, 0])
    nz = np.abs(normals[:, 2])
    faces: list[WallFace] = []
    for axis in (0, 1):
        belongs = (nx >= nz) if axis == 0 else (nz > nx)
        if belongs.sum() < wcfg["peak_min_points"]:
            continue
        pos = xz[belongs, axis]
        along = xz[belongs, 1 - axis]
        sign = normals[belongs, 0 if axis == 0 else 2]
        bin_m = wcfg["hist_bin_m"]
        lo, hi = float(pos.min()), float(pos.max())
        edges = np.arange(lo - bin_m, hi + 2 * bin_m, bin_m)
        hist, edges = np.histogram(pos, bins=edges)
        peaks, _ = find_peaks(hist, height=wcfg["peak_min_points"],
                              distance=max(1, int(round(wcfg["peak_min_separation_m"] / bin_m))))
        for p in peaks:
            centre = float((edges[p] + edges[p + 1]) / 2)
            band = np.abs(pos - centre) <= bin_m * 1.5
            if band.sum() < wcfg["peak_min_points"]:
                continue
            refined = float(np.median(pos[band]))
            band = np.abs(pos - refined) <= bin_m * 1.5
            segments = _runs(along[band], wcfg["occupancy_bin_m"], wcfg["max_gap_m"], wcfg["min_run_m"])
            if not segments:
                continue
            faces.append(WallFace(axis=axis, pos=refined, segments=segments, n_points=int(band.sum()),
                                  resid_std=float(np.std(pos[band])), sign=float(np.mean(sign[band]))))
    faces.sort(key=lambda f: (f.axis, f.pos))
    return faces
