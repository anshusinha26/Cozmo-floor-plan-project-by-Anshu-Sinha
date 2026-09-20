"""One consistent set of chunk scales from three disagreeing sources.

Fix loop 2. After the camera-height prior there are two independent estimates of
every chunk's metres per SfM unit, and the accepted bridges say how pairs of
them must relate. Rather than picking one, solve for the set that fits all three
with weights that say how much each is trusted.

Working in logs makes it linear: a ratio constraint between two chunks becomes a
difference, and a least squares over log scale is a least squares over relative
error, which is the quantity that actually matters here.

Weights, and why:

* **height prior, strong.** Its error is the spread of where people hold a
  phone, about 0.12 m on 1.40, so 8 to 9%.
* **Depth Pro, weak.** Loop 1 measured its chunk-to-chunk disagreement at 18 to
  142%. It is kept in the solve rather than dropped because it is the only term
  that carries any information when a chunk has no usable floor plane.
* **bridge ratios, medium.** A bridge that passed its residual gate says
  something real about how two chunks relate, but it is built on eight frames.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

log = logging.getLogger(__name__)

W_HEIGHT = 1.0 / 0.09       # 9% relative uncertainty
W_DEPTH_PRO = 1.0 / 0.60    # 60%: loop 1's measured chunk-to-chunk disagreement
W_BRIDGE = 1.0 / 0.15


@dataclass
class ScaleSolution:
    chunks: list[int]
    scales: dict[int, float]
    residuals: dict[str, float]
    n_constraints: int
    note: str = ""

    def summary(self) -> dict:
        return {"chunks": self.chunks,
                "scales": {k: round(v, 6) for k, v in self.scales.items()},
                "n_constraints": self.n_constraints,
                "residuals_relative": {k: round(v, 4) for k, v in self.residuals.items()},
                "note": self.note}


def solve(group: list[int], height: dict[int, float | None], depth_pro: dict[int, float | None],
          bridges: list[tuple[int, int, float]], w_height: float = W_HEIGHT,
          w_depth_pro: float = W_DEPTH_PRO, w_bridge: float = W_BRIDGE) -> ScaleSolution:
    """Least squares over log scale.

    ``bridges`` are ``(a, b, log_ratio)`` where ``log_ratio`` is the value that
    ``log s_a - log s_b`` should take for the two chunks to agree through the
    bridge.
    """
    idx = {c: i for i, c in enumerate(group)}
    rows, rhs, weights, kinds = [], [], [], []

    def add(row, value, weight, kind):
        rows.append(row)
        rhs.append(value)
        weights.append(weight)
        kinds.append(kind)

    for c in group:
        r = np.zeros(len(group))
        r[idx[c]] = 1.0
        if height.get(c):
            add(r.copy(), np.log(height[c]), w_height, "height_prior")
        if depth_pro.get(c):
            add(r.copy(), np.log(depth_pro[c]), w_depth_pro, "depth_pro")
    for a, b, log_ratio in bridges:
        if a not in idx or b not in idx:
            continue
        r = np.zeros(len(group))
        r[idx[a]] = 1.0
        r[idx[b]] = -1.0
        add(r, float(log_ratio), w_bridge, "bridge")

    if not rows:
        raise ValueError("no scale evidence for any chunk in the group")
    A = np.array(rows)
    b = np.array(rhs)
    w = np.array(weights)
    sol, *_ = np.linalg.lstsq(A * w[:, None], b * w, rcond=None)
    resid = A @ sol - b

    by_kind: dict[str, list[float]] = {}
    for k, r in zip(kinds, resid):
        by_kind.setdefault(k, []).append(abs(float(np.expm1(r))))  # log residual to relative error
    residuals = {k: float(np.median(v)) for k, v in by_kind.items()}
    scales = {c: float(np.exp(sol[idx[c]])) for c in group}
    log.info("scale solve: %d constraints over %d chunks, median relative residual %s",
             len(rows), len(group), ", ".join(f"{k} {v:.1%}" for k, v in residuals.items()))
    return ScaleSolution(chunks=list(group), scales=scales, residuals=residuals,
                         n_constraints=len(rows))
