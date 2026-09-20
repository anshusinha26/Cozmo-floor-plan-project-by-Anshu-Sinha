"""Stage 6: gravity, from a RANSAC floor plane seeded by the cameras.

A hand-held phone is held roughly upright, so the mean of the cameras' own up
vectors is within about 20 degrees of gravity. That seed does two jobs: it
picks which of the two plane normals points up, and it rejects planes that are
nowhere near horizontal, so a large wall or a table top cannot be mistaken for
the floor.

The floor is then the lowest large horizontal plane along the seed direction,
fitted by RANSAC over the points in the bottom part of that range.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

log = logging.getLogger(__name__)


@dataclass
class Gravity:
    normal: np.ndarray            # unit, points up, in the input frame
    offset_m: float               # floor plane height along the normal
    inlier_fraction: float
    seed_angle_deg: float
    method: str

    def rotation_to_y_up(self) -> np.ndarray:
        """Rotation taking the input frame to one where +y is up."""
        return rotation_between(self.normal, np.array([0.0, 1.0, 0.0]))


def rotation_between(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Shortest rotation matrix taking unit vector a onto unit vector b."""
    a = a / np.linalg.norm(a)
    b = b / np.linalg.norm(b)
    v = np.cross(a, b)
    c = float(a @ b)
    if np.linalg.norm(v) < 1e-9:
        if c > 0:
            return np.eye(3)
        # Antiparallel: a half turn about any axis perpendicular to a.
        axis = np.eye(3)[int(np.argmin(np.abs(a)))]
        u = np.cross(a, axis)
        u = u / np.linalg.norm(u)
        return 2 * np.outer(u, u) - np.eye(3)
    K = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + K + K @ K * (1.0 / (1.0 + c))


def seed_up(camera_up: np.ndarray) -> np.ndarray:
    """Mean camera up vector, normalised. Falls back to +y when there is none."""
    if camera_up is None or len(camera_up) == 0:
        return np.array([0.0, 1.0, 0.0])
    m = np.asarray(camera_up, dtype=np.float64).mean(axis=0)
    n = np.linalg.norm(m)
    return m / n if n > 1e-9 else np.array([0.0, 1.0, 0.0])


def fit_floor(points: np.ndarray, normals: np.ndarray, camera_up: np.ndarray,
              max_tilt_deg: float = 30.0, band_m: float = 0.08, iters: int = 200,
              low_quantile: float = 0.25, seed: int = 0) -> Gravity:
    """RANSAC the floor plane among near-horizontal points below the cameras."""
    up = seed_up(camera_up)
    if len(points) < 100:
        return Gravity(up, float(np.percentile(points @ up, 1)) if len(points) else 0.0,
                       0.0, 0.0, "camera_up_only_too_few_points")

    cos_lim = np.cos(np.deg2rad(max_tilt_deg))
    align = normals @ up
    horizontal = np.abs(align) >= cos_lim
    h = points @ up
    # The floor is the low end of the height range, not the whole cloud.
    low = horizontal & (h <= np.quantile(h, low_quantile))
    cand = np.nonzero(low)[0]
    if len(cand) < 50:
        cand = np.nonzero(h <= np.quantile(h, low_quantile))[0]
    if len(cand) < 50:
        return Gravity(up, float(np.percentile(h, 1)), 0.0, 0.0, "camera_up_only_no_floor_points")

    rng = np.random.default_rng(seed)
    P = points[cand]
    best = (0, up, float(np.percentile(h, 1)))
    for _ in range(iters):
        idx = rng.choice(len(P), 3, replace=False)
        a, b, c = P[idx]
        n = np.cross(b - a, c - a)
        ln = np.linalg.norm(n)
        if ln < 1e-9:
            continue
        n = n / ln
        if n @ up < 0:
            n = -n
        if n @ up < cos_lim:
            continue
        d = float(n @ a)
        inliers = int(np.count_nonzero(np.abs(P @ n - d) <= band_m))
        if inliers > best[0]:
            best = (inliers, n, d)

    inliers, n, d = best
    if inliers >= 50:
        # Refit on the inliers so three random points do not set the answer.
        m = np.abs(P @ n - d) <= band_m
        Q = P[m]
        cov = np.cov((Q - Q.mean(0)).T)
        w, V = np.linalg.eigh(cov)
        nn = V[:, 0]
        if nn @ up < 0:
            nn = -nn
        if nn @ up >= cos_lim:
            n = nn
            d = float(np.median(Q @ n))
    frac = inliers / len(P) if len(P) else 0.0
    angle = float(np.rad2deg(np.arccos(np.clip(n @ up, -1, 1))))
    log.info("gravity: floor plane %.1f degrees off the camera seed, %.0f%% inliers of %d candidates",
             angle, 100 * frac, len(P))
    return Gravity(n, float(d), float(frac), angle,
                   "ransac_floor_plane" if inliers >= 50 else "camera_up_only_ransac_failed")
