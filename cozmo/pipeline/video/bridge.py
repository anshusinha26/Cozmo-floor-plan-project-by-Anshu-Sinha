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
    scale_tolerance: float | None = None


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
                              "scale_tolerance": None if a.scale_tolerance is None else round(a.scale_tolerance, 4),
                              "seconds": None if a.seconds is None else round(a.seconds, 1)}
                             for a in self.attempts],
                "dropped": self.dropped}


def umeyama_2d(X: np.ndarray, Y: np.ndarray) -> tuple[float, float, np.ndarray, float]:
    """Similarity in the floor plane: returns (scale, yaw, translation, rms).

    Once both sides are gravity aligned the only freedom left is a turn about
    gravity and a slide, and solving for exactly that is the point. A full 3D
    similarity fitted to four cameras walking in a line leaves the rotation about
    the line of travel unconstrained, which is how two chunks standing on the
    same floor came out 164 degrees apart about which way was down.
    """
    if len(X) < 2:
        raise ValueError("a planar similarity fit needs at least 2 correspondences")
    mx, my = X.mean(0), Y.mean(0)
    Xc, Yc = X - mx, Y - my
    var = float((Xc ** 2).sum())
    if var <= 1e-12:
        raise ValueError("degenerate correspondences: source points coincide")
    # Complex form: the least squares similarity is one complex division.
    a = float((Xc[:, 0] * Yc[:, 0] + Xc[:, 1] * Yc[:, 1]).sum())
    b = float((Xc[:, 0] * Yc[:, 1] - Xc[:, 1] * Yc[:, 0]).sum())
    scale = float(np.hypot(a, b) / var)
    yaw = float(np.arctan2(b, a))
    c, sn = np.cos(yaw), np.sin(yaw)
    Rot = np.array([[c, -sn], [sn, c]])
    t = my - scale * (Rot @ mx)
    resid = (scale * (Rot @ X.T)).T + t - Y
    return scale, yaw, t, float(np.sqrt((resid ** 2).sum(1).mean()))


def gravity_align(poses: np.ndarray) -> np.ndarray:
    """Rotation taking MapAnything's own frame to y-up, from its camera up vectors.

    MapAnything does not know which way is down, so its output has to be stood up
    before it can be compared with two chunks that already have been.
    """
    from cozmo.pipeline.video.up import rotation_between

    up = -poses[:, :3, 1].mean(axis=0)
    n = float(np.linalg.norm(up))
    if n < 1e-9:
        return np.eye(3)
    return rotation_between(up / n, np.array([0.0, 1.0, 0.0]))


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


def scale_standard_error(chunk: SfmChunk) -> float:
    """Relative standard error of this chunk's metric scale, from its own frames.

    The scale is the median of per-frame ratios, so its standard error is about
    1.25 sigma over the square root of the frame count, with sigma taken
    robustly. This is what makes the scale-agreement gate honest: a chunk whose
    scale is known only to 12% cannot be asked to agree with its neighbour to 15%.
    """
    r = chunk.scale_frame_ratios
    if r is None or len(r) < 2:
        return 0.0
    med = float(np.median(r))
    if med <= 0:
        return 0.0
    spread = float(1.4826 * np.median(np.abs(r - med)) / med)
    return float(1.2533 * spread / np.sqrt(len(r)))


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


def _overlap_side(times: np.ndarray, k: int, window_s: float, tail: bool) -> np.ndarray:
    """``k`` frames from one end of a chunk, spread over ``window_s`` seconds.

    Taking the last k frames outright would span 0.3 s at 10 fps, about 15 cm of
    walking, and a similarity fit to four cameras 15 cm apart has almost no
    leverage on scale: that is what made the first bridging attempt reject
    nearly every pair with implied scales off by factors of ten. Spreading the
    same four frames over a couple of seconds gives the fit a real baseline
    without asking MapAnything to look at more images.
    """
    order = np.argsort(np.where(np.isfinite(times), times, np.inf), kind="stable")
    t = times[order]
    good = np.isfinite(t)
    order, t = order[good], t[good]
    if len(order) == 0:
        return np.zeros(0, dtype=int)
    if len(order) <= k:
        return order
    within = order[t >= t[-1] - window_s] if tail else order[t <= t[0] + window_s]
    if len(within) < k:
        within = order[-k:] if tail else order[:k]
    pick = np.unique(np.linspace(0, len(within) - 1, k).round().astype(int))
    return within[pick]


def _overlap_indices(chunk_a: SfmChunk, chunk_b: SfmChunk, k: int,
                     window_s: float = 2.0) -> tuple[np.ndarray, np.ndarray]:
    """Frames from the end of a and the start of b, spread over a time window."""
    return (_overlap_side(chunk_a.times_s, k, window_s, tail=True),
            _overlap_side(chunk_b.times_s, k, window_s, tail=False))


def try_bridge(chunk_a: SfmChunk, chunk_b: SfmChunk, frames: FrameSet, oracle: MapAnythingOracle,
               overlap_frames: int = 4, max_rms_m: float = 0.12, max_rms_frac: float = 0.25,
               max_scale_disagreement: float = 0.15, overlap_window_s: float = 2.0,
               min_span_m: float = 0.20, scale_sem_sigmas: float = 2.0,
               levelled: bool = False, transforms: dict | None = None,
               max_tilt_deg: float = 12.0, max_vertical_m: float = 0.35
               ) -> tuple[BridgeAttempt, tuple[np.ndarray, np.ndarray] | None]:
    """One neighbouring pair. Returns the attempt record and, if accepted, (R, t) taking b into a."""
    t0 = time.perf_counter()
    ia, ib = _overlap_indices(chunk_a, chunk_b, overlap_frames, overlap_window_s)
    if len(ia) < 3 or len(ib) < 3:
        return BridgeAttempt(chunk_a.index, chunk_b.index, False,
                             "fewer than 3 frames available on one side"), None
    def centres(chunk, idx):
        """Overlap camera centres in whatever frame the caller is working in."""
        c = metric_centres(chunk, idx)
        if transforms is not None and chunk.index in transforms:
            R, t = transforms[chunk.index]
            c = c @ R.T + t
        return c

    paths = [frames.path(chunk_a.names[i]) for i in ia] + [frames.path(chunk_b.names[i]) for i in ib]
    try:
        poses = oracle.poses(paths)
    except Exception as e:  # a bridge failing must not take the run down
        return BridgeAttempt(chunk_a.index, chunk_b.index, False,
                             f"MapAnything failed: {type(e).__name__}: {e}"[:160],
                             seconds=time.perf_counter() - t0), None
    ma = poses[:, :3, 3]
    ma_a, ma_b = ma[:len(ia)], ma[len(ia):]

    if levelled:
        return _planar_bridge(chunk_a, chunk_b, ia, ib, poses, centres, max_rms_m, max_rms_frac,
                              max_vertical_m, min_span_m, time.perf_counter() - t0)

    try:
        fit_a = umeyama(ma_a, centres(chunk_a, ia))
        fit_b = umeyama(ma_b, centres(chunk_b, ib))
    except ValueError as e:
        return BridgeAttempt(chunk_a.index, chunk_b.index, False, f"alignment degenerate: {e}",
                             seconds=time.perf_counter() - t0), None

    span_a = float(np.linalg.norm(np.ptp(centres(chunk_a, ia), axis=0)))
    span_b = float(np.linalg.norm(np.ptp(centres(chunk_b, ib), axis=0)))
    tol_a = max(max_rms_m, max_rms_frac * span_a)
    tol_b = max(max_rms_m, max_rms_frac * span_b)
    ratio = fit_a.s / fit_b.s if fit_b.s else float("inf")
    secs = time.perf_counter() - t0

    if min(span_a, span_b) < min_span_m:
        return BridgeAttempt(chunk_a.index, chunk_b.index, False,
                             f"overlap cameras span only {min(span_a, span_b):.2f} m, under the "
                             f"{min_span_m:.2f} m a similarity fit needs to pin a scale",
                             fit_a.rms_m, fit_b.rms_m, ratio, secs), None
    if fit_a.rms_m > tol_a or fit_b.rms_m > tol_b:
        return BridgeAttempt(chunk_a.index, chunk_b.index, False,
                             f"alignment residual {fit_a.rms_m:.3f} m and {fit_b.rms_m:.3f} m "
                             f"against {tol_a:.3f} and {tol_b:.3f} allowed",
                             fit_a.rms_m, fit_b.rms_m, ratio, secs), None
    # The gate is the configured floor, or two sigma of the two chunks' own
    # measured scale errors, whichever is looser. Holding a pair to 15% when
    # each side's scale is only known to 12% rejects bridges for being inside
    # their own noise.
    R = fit_a.R @ fit_b.R.T
    t = fit_a.t - R @ fit_b.t

    sem = float(np.hypot(scale_standard_error(chunk_a), scale_standard_error(chunk_b)))
    tol_scale = max(max_scale_disagreement, scale_sem_sigmas * sem)
    if not np.isfinite(ratio) or abs(ratio - 1.0) > tol_scale:
        return BridgeAttempt(chunk_a.index, chunk_b.index, False,
                             f"implied scales disagree by {abs(ratio - 1.0):.1%}, over the "
                             f"{tol_scale:.0%} allowed ({max_scale_disagreement:.0%} floor, "
                             f"{scale_sem_sigmas:.0f} sigma of the chunks' own {sem:.1%})",
                             fit_a.rms_m, fit_b.rms_m, ratio, secs, tol_scale), None

    # Compose, dropping the residual scale: both sides are already in metres
    # through their own chunk, so the chunk-to-chunk transform must be rigid.
    return BridgeAttempt(chunk_a.index, chunk_b.index, True, "accepted",
                         fit_a.rms_m, fit_b.rms_m, ratio, secs, tol_scale), (R, t)


def yaw_of(R: np.ndarray) -> float:
    """The rotation about y that best matches R, in radians.

    After levelling, two chunks differ only by a turn about gravity and a slide
    along the floor. Anything else in the bridge's rotation is error, so it is
    projected out rather than applied.
    """
    return float(np.arctan2(R[0, 2] - R[2, 0], R[0, 0] + R[2, 2]))


def yaw_matrix(theta: float) -> np.ndarray:
    c, s_ = np.cos(theta), np.sin(theta)
    return np.array([[c, 0.0, s_], [0.0, 1.0, 0.0], [-s_, 0.0, c]])


def planar(R: np.ndarray, t: np.ndarray) -> tuple[np.ndarray, np.ndarray, float, float]:
    """Reduce a rigid transform to a yaw and a slide on the floor.

    Returns the planar rotation and translation plus what was discarded: the
    tilt away from a pure yaw, and the vertical shift. Both are reported,
    because a large one means the two chunks did not agree about which way is
    down and the bridge should be distrusted.
    """
    theta = yaw_of(R)
    Rp = yaw_matrix(theta)
    tilt_deg = float(np.rad2deg(np.arccos(np.clip((np.trace(Rp.T @ R) - 1) / 2, -1, 1))))
    tp = np.array([t[0], 0.0, t[2]])
    return Rp, tp, tilt_deg, float(abs(t[1]))


def _planar_bridge(chunk_a, chunk_b, ia, ib, poses, centres, max_rms_m, max_rms_frac,
                   max_vertical_m, min_span_m, secs):
    """Bridge two chunks that already stand upright on a common floor.

    Everything is stood up first, MapAnything included, and then the fit is a
    turn about gravity and a slide. There is no rotation left over to get wrong.
    """
    R_ma = gravity_align(poses)
    ma = poses[:, :3, 3] @ R_ma.T
    ma_a, ma_b = ma[:len(ia)], ma[len(ia):]
    ca, cb = centres(chunk_a, ia), centres(chunk_b, ib)

    span_a = float(np.linalg.norm(np.ptp(ca[:, [0, 2]], axis=0)))
    span_b = float(np.linalg.norm(np.ptp(cb[:, [0, 2]], axis=0)))
    if min(span_a, span_b) < min_span_m:
        return BridgeAttempt(chunk_a.index, chunk_b.index, False,
                             f"overlap cameras span only {min(span_a, span_b):.2f} m on the floor, "
                             f"under the {min_span_m:.2f} m a fit needs to pin a turn",
                             seconds=secs), None
    try:
        s_a, yaw_a, t_a, rms_a = umeyama_2d(ma_a[:, [0, 2]], ca[:, [0, 2]])
        s_b, yaw_b, t_b, rms_b = umeyama_2d(ma_b[:, [0, 2]], cb[:, [0, 2]])
    except ValueError as e:
        return BridgeAttempt(chunk_a.index, chunk_b.index, False, f"alignment degenerate: {e}",
                             seconds=secs), None

    tol_a = max(max_rms_m, max_rms_frac * span_a)
    tol_b = max(max_rms_m, max_rms_frac * span_b)
    ratio = s_a / s_b if s_b else float("inf")
    if rms_a > tol_a or rms_b > tol_b:
        return BridgeAttempt(chunk_a.index, chunk_b.index, False,
                             f"floor-plane alignment residual {rms_a:.3f} m and {rms_b:.3f} m "
                             f"against {tol_a:.3f} and {tol_b:.3f} allowed",
                             rms_a, rms_b, ratio, secs), None
    vertical = float(abs(np.median(ca[:, 1]) - np.median(cb[:, 1])))
    if vertical > max_vertical_m:
        return BridgeAttempt(chunk_a.index, chunk_b.index, False,
                             f"the two chunks put their cameras {vertical:.2f} m apart in height, "
                             f"over the {max_vertical_m:.2f} m allowed, so they are not on one floor",
                             rms_a, rms_b, ratio, secs), None

    yaw = yaw_a - yaw_b
    Rp = yaw_matrix(yaw)
    c, sn = np.cos(yaw), np.sin(yaw)
    Rot2 = np.array([[c, -sn], [sn, c]])
    t2 = t_a - Rot2 @ t_b
    tp = np.array([t2[0], 0.0, t2[1]])
    return BridgeAttempt(chunk_a.index, chunk_b.index, True,
                         f"accepted on yaw {np.degrees(yaw):+.1f} degrees, residuals "
                         f"{rms_a:.3f} and {rms_b:.3f} m, implied scales differ by "
                         f"{abs(ratio - 1):.0%}", rms_a, rms_b, ratio, secs), (Rp, tp)


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
                  max_scale_disagreement: float = 0.15, overlap_window_s: float = 2.0,
                  min_span_m: float = 0.20, scale_sem_sigmas: float = 2.0,
                  levelled: bool = False, transforms: dict | None = None,
                  max_tilt_deg: float = 12.0, max_vertical_m: float = 0.35,
                  time_box_s: float = 5400.0) -> BridgeResult:
    """Bridge every neighbouring pair, then keep the largest connected group.

    ``time_box_s`` is a hard stop. If it expires the result is whatever has been
    bridged so far, flagged, and the caller ships the largest chunk on its own
    rather than a half-built group.
    """
    n = len(chunks)
    if n == 1:
        base = transforms[0] if transforms else (np.eye(3), np.zeros(3))
        return BridgeResult(group=[0], transforms={0: base},
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
                                 max_rms_m, max_rms_frac, max_scale_disagreement,
                                 overlap_window_s, min_span_m, scale_sem_sigmas,
                                 levelled, transforms, max_tilt_deg, max_vertical_m)
        attempts.append(attempt)
        log.info("bridge %d-%d: %s", attempt.a, attempt.b,
                 "accepted" if attempt.accepted else f"rejected, {attempt.reason}")
        if tf is not None:
            edges.append((i, i + 1))
            pair_tf[(i, i + 1)] = tf

    weights = [len(c) for c in chunks]
    group = sorted(_largest_group(n, edges, weights))

    # Compose along the chain to the first chunk of the group.
    out_tf: dict[int, tuple[np.ndarray, np.ndarray]] = {group[0]: (np.eye(3), np.zeros(3))}
    for k in range(len(group) - 1):
        i, j = group[k], group[k + 1]
        if (i, j) not in pair_tf:
            break
        R_ij, t_ij = pair_tf[(i, j)]
        R_prev, t_prev = out_tf[i]
        out_tf[j] = (R_prev @ R_ij, R_prev @ t_ij + t_prev)
    group = [g for g in group if g in out_tf]
    if transforms is not None:
        # Compose onto the levelling transform each chunk already carries.
        out_tf = {g: (out_tf[g][0] @ transforms[g][0],
                      out_tf[g][0] @ transforms[g][1] + out_tf[g][1]) for g in group}
    transforms = out_tf

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
