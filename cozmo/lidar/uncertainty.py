"""Stage 9: where every interval in the LiDAR plan comes from.

Each wall length is the distance between two wall faces. Its uncertainty has
two independent parts:

* statistical: how well each face's position is known. A face is a cloud of
  points with a residual spread; the position error is that spread divided by
  the square root of an effective sample size. Points 2 cm apart on the same
  wall are not independent measurements, so the effective count is the face
  length divided by a correlation length (0.25 m), never the raw point count.
* systematic: a depth scale bias (default 1%, config
  ``uncertainty.depth_scale_bias``) that scales with the measured length, and
  an absolute floor (default 1 cm, ``uncertainty.abs_floor_m``) below which no
  measurement is ever claimed.

Areas propagate from the lengths: for a rectilinear room the relative area
error is the quadrature sum of the two axes' relative length errors.
"""

from __future__ import annotations

import numpy as np

from cozmo.contracts.models import Measurement
from cozmo.lidar.walls import WallFace

CORRELATION_LENGTH_M = 0.25


def face_position_sigma(face: WallFace, cfg: dict) -> float:
    """Standard error of a wall face's position along its normal."""
    length = max(face.length(), CORRELATION_LENGTH_M)
    n_eff = max(length / CORRELATION_LENGTH_M, 1.0)
    spread = max(face.resid_std, 0.002)  # 2 mm: the sensor's own depth quantisation
    return float(spread / np.sqrt(n_eff))


def length_measurement(value: float, sigma_a: float, sigma_b: float, cfg: dict,
                       method: str = "wall_face_separation") -> Measurement:
    unc = cfg["uncertainty"]
    systematic = unc["depth_scale_bias"] * abs(value)
    sigma = float(np.sqrt(sigma_a ** 2 + sigma_b ** 2 + systematic ** 2))
    half = max(1.96 * sigma, unc["abs_floor_m"])
    return Measurement(value=float(value), ci_low=float(value - half), ci_high=float(value + half),
                       unit="m", method=method, ci_level=unc["ci_level"])


def relative_half_width(m: Measurement) -> float:
    return (m.width / 2) / abs(m.value) if m.value else 0.0


def area_measurement(area: float, edge_measurements: list[Measurement], cfg: dict,
                     method: str = "polygon_from_wall_faces") -> Measurement:
    """Area interval propagated from the edge length intervals.

    Relative errors are combined in quadrature over the two axes, which is the
    exact rule for a rectangle and a good approximation for the rectilinear
    polygons this pipeline produces.
    """
    unc = cfg["uncertainty"]
    rels = [relative_half_width(m) for m in edge_measurements if m.value]
    rel = float(np.sqrt(sum(r ** 2 for r in sorted(rels, reverse=True)[:2]))) if rels else unc["depth_scale_bias"]
    half = max(rel * abs(area), unc["abs_floor_m"])
    return Measurement(value=float(area), ci_low=float(area - half), ci_high=float(area + half),
                       unit="m2", method=method, ci_level=unc["ci_level"])
