"""Stage 4: join neighbouring SfM chunks into one metric frame.

COLMAP splits a room scan into several sub-models that share no points, so
nothing inside COLMAP relates them. The chunks are still consecutive in time,
which means the last frames of one chunk and the first frames of the next see
overlapping geometry even though no feature track survived across the gap.

MapAnything is used there, and only there, as a relative-pose oracle over a
short overlap: images in, camera poses out. Its own scale is discarded. Spike 1
measured its trajectory running 2.5 to 3.9 times long and its depth 30% short,
so its metric output is not trustworthy, but a Sim3 fit absorbs exactly that
error. Each side is aligned to its own chunk's metric cameras and the two
alignments are composed into a rigid chunk-to-chunk transform.

A bridge is accepted only if both alignments fit well and the two implied
scales agree. Disagreeing scales mean MapAnything did not see one consistent
scene across the overlap, and a bridge built on that would fold the plan.
A rejected bridge leaves the chunks separate; it never guesses.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import numpy as np

from cozmo.pipeline.video.frames import FrameSet
from cozmo.pipeline.video.sfm import SfmChunk

log = logging.getLogger(__name__)

MAPANYTHING_CHECKPOINT = "facebook/map-anything-apache"


@dataclass
class Sim3:
    s: float
    R: np.ndarray
    t: np.ndarray
    rms_m: float
    n: int

    def apply(self, P: np.ndarray) -> np.ndarray:
        return (self.s * (self.R @ P.T)).T + self.t


@dataclass
class BridgeAttempt:
    a: int
    b: int
    accepted: bool
    reason: str
    rms_a_m: float | None = None
    rms_b_m: float | None = None
    scale_ratio: float | None = None
    seconds: float | None = None


@dataclass
class BridgeResult:
    group: list[int]                               # chunk indices in the largest bridged group
    transforms: dict[int, tuple[np.ndarray, np.ndarray]] = field(default_factory=dict)
    attempts: list[BridgeAttempt] = field(default_factory=list)
    dropped: list[dict] = field(default_factory=list)
    timed_out: bool = False
    note: str = ""

    @property
    def accepted(self) -> list[BridgeAttempt]:
        return [a for a in self.attempts if a.accepted]

    @property
    def rejected(self) -> list[BridgeAttempt]:
        return [a for a in self.attempts if not a.accepted]

    def summary(self) -> dict:
        return {"group": self.group, "n_bridges_tried": len(self.attempts),
                "n_accepted": len(self.accepted), "n_rejected": len(self.rejected),
                "timed_out": self.timed_out, "note": self.note,
                "attempts": [{"a": a.a, "b": a.b, "accepted": a.accepted, "reason": a.reason,
                              "rms_a_m": None if a.rms_a_m is None else round(a.rms_a_m, 4),
                              "rms_b_m": None if a.rms_b_m is None else round(a.rms_b_m, 4),
                              "scale_ratio": None if a.scale_ratio is None else round(a.scale_ratio, 4),
                              "seconds": None if a.seconds is None else round(a.seconds, 1)}
                             for a in self.attempts],
                "dropped": self.dropped}


def umeyama(X: np.ndarray, Y: np.ndarray) -> Sim3:
    """Least squares similarity mapping X onto Y, both (N, 3)."""
    if len(X) < 3:
        raise ValueError("a similarity fit needs at least 3 correspondences")
    mx, my = X.mean(0), Y.mean(0)
    Xc, Yc = X - mx, Y - my
    var = (Xc ** 2).sum()
    if var <= 1e-12:
        raise ValueError("degenerate correspondences: source points coincide")
    U, D, Vt = np.linalg.svd(Yc.T @ Xc / len(X))
    W = np.eye(3)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        W[2, 2] = -1
    R = U @ W @ Vt
    s = float(np.trace(np.diag(D) @ W) * len(X) / var)
    t = my - s * R @ mx
    resid = (s * (R @ X.T)).T + t - Y
    return Sim3(s=s, R=R, t=t, rms_m=float(np.sqrt((resid ** 2).sum(1).mean())), n=len(X))


def metric_centres(chunk: SfmChunk, idx: np.ndarray) -> np.ndarray:
    """Camera centres of selected frames, in metres, using the chunk's own scale."""
    if chunk.scale_m_per_unit is None:
        raise ValueError(f"chunk {chunk.index} has no metric scale yet")
    return chunk.centres()[idx] * chunk.scale_m_per_unit


class MapAnythingOracle:
    """Poses for a short image list. Loaded lazily so a single-chunk clip never pays for it."""

    def __init__(self, device: str, checkpoint: str = MAPANYTHING_CHECKPOINT) -> None:
        self.device_name = device
        self.checkpoint = checkpoint
        self._model = None

    def _load(self):
        if self._model is None:
            import torch
            from mapanything.models import MapAnything

            log.info("loading MapAnything (%s) on %s for chunk bridging", self.checkpoint, self.device_name)
            self._model = MapAnything.from_pretrained(self.checkpoint).to(torch.device(self.device_name))
            self._model.eval()
        return self._model

    def poses(self, paths: list) -> np.ndarray:
        """(n, 4, 4) camera to world in MapAnything's own arbitrary frame."""
        import torch
        from mapanything.utils.image import load_images

        model = self._load()
        views = load_images([str(p) for p in paths], verbose=False)
        with torch.no_grad():
            preds = model.infer(views, memory_efficient_inference=True,
                                use_amp=True, amp_dtype="fp16" if self.device_name == "mps" else "bf16",
                                apply_mask=True, mask_edges=True, apply_confidence_mask=False)
        return np.stack([p["camera_poses"][0].float().cpu().numpy() for p in preds])


def _overlap_indices(chunk_a: SfmChunk, chunk_b: SfmChunk, k: int) -> tuple[np.ndarray, np.ndarray]:
    """Last k frames of a and first k of b, in time order."""
    oa = np.argsort(chunk_a.times_s) if np.isfinite(chunk_a.times_s).all() else np.arange(len(chunk_a))
    ob = np.argsort(chunk_b.times_s) if np.isfinite(chunk_b.times_s).all() else np.arange(len(chunk_b))
    return oa[-k:], ob[:k]


def try_bridge(chunk_a: SfmChunk, chunk_b: SfmChunk, frames: FrameSet, oracle: MapAnythingOracle,
               overlap_frames: int = 4, max_rms_m: float = 0.12, max_rms_frac: float = 0.25,
               max_scale_disagreement: float = 0.15) -> tuple[BridgeAttempt, tuple[np.ndarray, np.ndarray] | None]:
    """One neighbouring pair. Returns the attempt record and, if accepted, (R, t) taking b into a."""
    t0 = time.perf_counter()
    ia, ib = _overlap_indices(chunk_a, chunk_b, overlap_frames)
    if len(ia) < 3 or len(ib) < 3:
        return BridgeAttempt(chunk_a.index, chunk_b.index, False,
                             "fewer than 3 frames available on one side"), None
    paths = [frames.path(chunk_a.names[i]) for i in ia] + [frames.path(chunk_b.names[i]) for i in ib]
    try:
        poses = oracle.poses(paths)
    except Exception as e:  # a bridge failing must not take the run down
        return BridgeAttempt(chunk_a.index, chunk_b.index, False,
                             f"MapAnything failed: {type(e).__name__}: {e}"[:160],
                             seconds=time.perf_counter() - t0), None
    ma = poses[:, :3, 3]
    ma_a, ma_b = ma[:len(ia)], ma[len(ia):]

    try:
        fit_a = umeyama(ma_a, metric_centres(chunk_a, ia))
        fit_b = umeyama(ma_b, metric_centres(chunk_b, ib))
    except ValueError as e:
        return BridgeAttempt(chunk_a.index, chunk_b.index, False, f"alignment degenerate: {e}",
                             seconds=time.perf_counter() - t0), None

    span_a = float(np.linalg.norm(metric_centres(chunk_a, ia).ptp(axis=0)))
    span_b = float(np.linalg.norm(metric_centres(chunk_b, ib).ptp(axis=0)))
    tol_a = max(max_rms_m, max_rms_frac * span_a)
    tol_b = max(max_rms_m, max_rms_frac * span_b)
    ratio = fit_a.s / fit_b.s if fit_b.s else float("inf")
    secs = time.perf_counter() - t0

    if fit_a.rms_m > tol_a or fit_b.rms_m > tol_b:
        return BridgeAttempt(chunk_a.index, chunk_b.index, False,
                             f"alignment residual {fit_a.rms_m:.3f} m and {fit_b.rms_m:.3f} m "
                             f"against {tol_a:.3f} and {tol_b:.3f} allowed",
                             fit_a.rms_m, fit_b.rms_m, ratio, secs), None
    if not np.isfinite(ratio) or abs(ratio - 1.0) > max_scale_disagreement:
        return BridgeAttempt(chunk_a.index, chunk_b.index, False,
                             f"implied scales disagree by {abs(ratio - 1.0):.1%}, "
                             f"over the {max_scale_disagreement:.0%} allowed",
                             fit_a.rms_m, fit_b.rms_m, ratio, secs), None

    # Compose, dropping the residual scale: both sides are already in metres
    # through their own chunk, so the chunk-to-chunk transform must be rigid.
    R = fit_a.R @ fit_b.R.T
    t = fit_a.t - R @ fit_b.t
    return BridgeAttempt(chunk_a.index, chunk_b.index, True, "accepted",
                         fit_a.rms_m, fit_b.rms_m, ratio, secs), (R, t)


def _largest_group(n: int, edges: list[tuple[int, int]], weights: list[int]) -> list[int]:
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in edges:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return max(groups.values(), key=lambda g: (sum(weights[i] for i in g), -min(g)))


def bridge_chunks(chunks: list[SfmChunk], frames: FrameSet, device: str, overlap_frames: int = 4,
                  max_rms_m: float = 0.12, max_rms_frac: float = 0.25,
                  max_scale_disagreement: float = 0.15,
                  time_box_s: float = 5400.0) -> BridgeResult:
    """Bridge every neighbouring pair, then keep the largest connected group.

    ``time_box_s`` is a hard stop. If it expires the result is whatever has been
    bridged so far, flagged, and the caller ships the largest chunk on its own
    rather than a half-built group.
    """
    n = len(chunks)
    if n == 1:
        return BridgeResult(group=[0], transforms={0: (np.eye(3), np.zeros(3))},
                            note="single chunk: the clip registered as one model, nothing to bridge")

    oracle = MapAnythingOracle(device)
    edges: list[tuple[int, int]] = []
    pair_tf: dict[tuple[int, int], tuple[np.ndarray, np.ndarray]] = {}
    attempts: list[BridgeAttempt] = []
    started = time.perf_counter()
    timed_out = False
    for i in range(n - 1):
        if time.perf_counter() - started > time_box_s:
            timed_out = True
            log.warning("bridge time box of %.0f s expired after %d of %d pairs",
                        time_box_s, i, n - 1)
            break
        attempt, tf = try_bridge(chunks[i], chunks[i + 1], frames, oracle, overlap_frames,
                                 max_rms_m, max_rms_frac, max_scale_disagreement)
        attempts.append(attempt)
        log.info("bridge %d-%d: %s", attempt.a, attempt.b,
                 "accepted" if attempt.accepted else f"rejected, {attempt.reason}")
        if tf is not None:
            edges.append((i, i + 1))
            pair_tf[(i, i + 1)] = tf

    weights = [len(c) for c in chunks]
    group = sorted(_largest_group(n, edges, weights))

    # Compose along the chain to the first chunk of the group.
    transforms: dict[int, tuple[np.ndarray, np.ndarray]] = {group[0]: (np.eye(3), np.zeros(3))}
    for k in range(len(group) - 1):
        i, j = group[k], group[k + 1]
        if (i, j) not in pair_tf:
            break
        R_ij, t_ij = pair_tf[(i, j)]
        R_prev, t_prev = transforms[i]
        transforms[j] = (R_prev @ R_ij, R_prev @ t_ij + t_prev)
    group = [g for g in group if g in transforms]

    total_frames = sum(weights)
    dropped = []
    for i, c in enumerate(chunks):
        if i in group:
            continue
        times = c.times_s[np.isfinite(c.times_s)]
        dropped.append({"chunk": i, "n_images": len(c),
                        "share_of_registered_frames": round(len(c) / total_frames, 4)
                        if total_frames else 0.0,
                        "share_of_video": round(len(c) / max(frames.n_decoded, 1), 4),
                        "time_span_s": [round(float(times.min()), 1), round(float(times.max()), 1)]
                        if len(times) else None})
    note = "bridge time box expired; groups are whatever was bridged before the stop" if timed_out else ""
    return BridgeResult(group=group, transforms=transforms, attempts=attempts, dropped=dropped,
                        timed_out=timed_out, note=note)
