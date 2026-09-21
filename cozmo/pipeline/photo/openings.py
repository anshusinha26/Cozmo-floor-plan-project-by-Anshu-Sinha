"""Doors from OWLv2 detections placed on the wall they belong to.

The photo tier has something the geometric opening finder needs and does not
have: a picture. A doorway is a gap in a wall, and a gap is only visible to the
occupancy method when the wall around it was reconstructed on both sides, which
two or three photos rarely manage. An open-vocabulary detector sees the door
itself.

The detection is a box in one image. MapAnything already gives a 3D point per
pixel, so the box does not have to be projected onto anything: the points inside
it are the door. Their spread along the wall is the width, their vertical spread
is the height, and their position along the wall is the offset.

Time-boxed. If the detector cannot be loaded or finds nothing, the tier says so
and reports no openings rather than guessing at them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

OWLV2_MODEL = "google/owlv2-base-patch16-ensemble"
QUERIES = [["a door", "a doorway", "an open door"]]
MIN_POINTS = 60
MIN_WIDTH_M = 0.5
MAX_WIDTH_M = 2.4
MIN_HEIGHT_M = 1.4
MAX_HEIGHT_M = 2.6


class OpeningsUnavailable(RuntimeError):
    """The detector could not run. The tier warns and reports no openings."""


@dataclass
class DoorDetection:
    room_id: str
    photo: str
    score: float
    centre_world: tuple[float, float, float]
    width_m: float
    height_m: float
    axis: int
    along: tuple[float, float]
    n_points: int

    def summary(self) -> dict:
        return {"photo": self.photo, "score": round(self.score, 3),
                "width_m": round(self.width_m, 3), "height_m": round(self.height_m, 3),
                "n_points": self.n_points}


class DoorDetector:
    """OWLv2, loaded once."""

    def __init__(self, device: str, model_id: str = OWLV2_MODEL) -> None:
        self.device_name = device
        self.model_id = model_id
        self._proc = None
        self._model = None

    def _load(self):
        if self._model is None:
            try:
                import torch
                from transformers import Owlv2ForObjectDetection, Owlv2Processor
            except ImportError as e:  # pragma: no cover
                raise OpeningsUnavailable(f"transformers has no OWLv2 in this build: {e}") from e
            try:
                self._proc = Owlv2Processor.from_pretrained(self.model_id)
                self._model = Owlv2ForObjectDetection.from_pretrained(self.model_id).to(
                    torch.device(self.device_name)).eval()
            except Exception as e:
                raise OpeningsUnavailable(f"could not load {self.model_id}: {e}") from e
            log.info("loaded %s on %s for door detection", self.model_id, self.device_name)
        return self._proc, self._model

    def boxes(self, path: Path, min_score: float) -> list[tuple[float, tuple[int, int, int, int]]]:
        import torch
        from PIL import Image

        proc, model = self._load()
        image = Image.open(path).convert("RGB")
        inputs = proc(text=QUERIES, images=image, return_tensors="pt").to(model.device)
        with torch.no_grad():
            outputs = model(**inputs)
        target = torch.tensor([[image.height, image.width]], device=model.device)
        results = proc.post_process_grounded_object_detection(
            outputs=outputs, target_sizes=target, threshold=min_score)[0]
        out = []
        for score, box in zip(results["scores"].tolist(), results["boxes"].tolist()):
            x0, y0, x1, y1 = (int(round(v)) for v in box)
            out.append((float(score), (x0, y0, x1, y1)))
        return sorted(out, key=lambda r: -r[0])


def _door_from_box(pts: np.ndarray) -> tuple[int, float, float, tuple[float, float]] | None:
    """Which wall the points lie on, and how wide and tall they are on it."""
    spread = np.ptp(pts, axis=0)
    axis = 0 if spread[0] < spread[2] else 2      # the door's wall is the thin direction
    along = 2 if axis == 0 else 0
    width = float(np.percentile(pts[:, along], 97) - np.percentile(pts[:, along], 3))
    height = float(np.percentile(pts[:, 1], 97) - np.percentile(pts[:, 1], 3))
    if not (MIN_WIDTH_M <= width <= MAX_WIDTH_M) or not (MIN_HEIGHT_M <= height <= MAX_HEIGHT_M):
        return None
    lo = float(np.percentile(pts[:, along], 3))
    hi = float(np.percentile(pts[:, along], 97))
    return (0 if axis == 0 else 1), width, height, (lo, hi)


def detect_doors(room_id: str, rec, transform, detector: DoorDetector, min_score: float,
                 max_photos: int) -> list[DoorDetection]:
    """Doors in this room, in the room's final metric, gravity-aligned frame.

    ``transform`` maps a raw MapAnything world point into that frame.
    """
    out: list[DoorDetection] = []
    for view, path in list(zip(rec.views, rec.paths))[:max_photos]:
        try:
            boxes = detector.boxes(Path(path), min_score)
        except OpeningsUnavailable:
            raise
        except Exception as e:
            log.warning("%s: door detection failed on %s: %s", room_id, Path(path).name, e)
            continue
        P, mask = view["pts3d"], view["mask"]
        h, w = mask.shape
        for score, (x0, y0, x1, y1) in boxes:
            x0, y0 = max(0, x0), max(0, y0)
            x1, y1 = min(w, x1), min(h, y1)
            if x1 - x0 < 4 or y1 - y0 < 4:
                continue
            sub = P[y0:y1, x0:x1]
            sub_mask = mask[y0:y1, x0:x1] & np.isfinite(sub).all(axis=-1)
            if sub_mask.sum() < MIN_POINTS:
                continue
            pts = transform(sub[sub_mask])
            fitted = _door_from_box(pts)
            if fitted is None:
                continue
            axis, width, height, along = fitted
            centre = pts.mean(axis=0)
            out.append(DoorDetection(room_id, Path(path).name, score,
                                     (float(centre[0]), float(centre[1]), float(centre[2])),
                                     width, height, axis, along, int(sub_mask.sum())))
    merged = _merge(out)
    log.info("%s: %d door detection(s) from %d photo(s), %d after merging",
             room_id, len(out), min(len(rec.views), max_photos), len(merged))
    return merged


def _merge(dets: list[DoorDetection], tol_m: float = 0.6) -> list[DoorDetection]:
    """One door seen in three photos is one door."""
    out: list[DoorDetection] = []
    for d in sorted(dets, key=lambda d: -d.score):
        c = np.array(d.centre_world)
        if any(np.linalg.norm(c - np.array(k.centre_world)) < tol_m for k in out):
            continue
        out.append(d)
    return out


def attach_doors(room, detections: list[DoorDetection], ci_level: float,
                 width_sigma_m: float = 0.08, max_offset_m: float = 0.6):
    """Turn detections into contract openings on the room's own walls.

    A detection knows where it is in the room but not which wall it belongs to,
    so it is matched to the nearest wall whose direction agrees with the spread
    of the door's own points. A detection that lands on no wall is dropped, not
    forced onto the nearest one.
    """
    from cozmo.contracts.models import Measurement, Opening

    out = []
    dropped = 0
    for i, d in enumerate(detections, start=1):
        c = np.array([d.centre_world[0], d.centre_world[2]])
        best, best_dist, best_t = None, 1e9, 0.0
        for wall in room.walls:
            a = np.array(wall.start, dtype=float)
            b = np.array(wall.end, dtype=float)
            v = b - a
            ln = float(np.linalg.norm(v))
            if ln < 1e-6:
                continue
            t = float(np.clip(np.dot(c - a, v) / (ln * ln), 0.0, 1.0))
            dist = float(np.linalg.norm(a + t * v - c))
            if dist < best_dist:
                best, best_dist, best_t = wall, dist, t * ln
        if best is None or best_dist > max_offset_m:
            dropped += 1
            continue
        offset = max(0.0, best_t - d.width_m / 2)
        half_w = max(1.96 * width_sigma_m, 0.05)
        half_h = max(1.96 * 0.10, 0.05)
        out.append(Opening(
            id=f"{room.id}_d{i}", type="door", wall_id=best.id,
            offset_along_wall_m=Measurement(value=offset, ci_low=max(0.0, offset - half_w),
                                            ci_high=offset + half_w, unit="m",
                                            method="owlv2_door_detection", ci_level=ci_level),
            width_m=Measurement(value=d.width_m, ci_low=d.width_m - half_w,
                                ci_high=d.width_m + half_w, unit="m",
                                method="owlv2_door_detection", ci_level=ci_level),
            height_m=Measurement(value=d.height_m, ci_low=d.height_m - half_h,
                                 ci_high=d.height_m + half_h, unit="m",
                                 method="owlv2_door_detection", ci_level=ci_level),
            sill_height_m=None, detection_confidence=float(min(d.score, 0.95))))
    return out, dropped
