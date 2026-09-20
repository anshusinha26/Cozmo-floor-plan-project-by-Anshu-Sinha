"""Precision filters. Recall was never the problem; these attack the rest.

Each filter is separate and switchable, so its effect can be measured on its
own rather than asserted. They run in the order below, cheapest first:

1. ``keep_best_damage_label``: a box survives only when its best label is a
   damage class rather than an everyday lookalike. The distractor prompts do
   the work; this is the rule that uses them.
2. ``geometry_ok``: with depth, a detection must be a plausible size and must
   lie on a surface of the plan. A box covering a quarter of a wall is not a
   mark on it.
3. ``multiview_ok``: a region must be seen more than once. One confident box
   from one angle is usually a reflection or a shadow.
4. ``CropVerifier``: a second model scores the crop against damage wording and
   against plain surfaces. Two models agreeing is weak evidence, but two
   models disagreeing is strong evidence against.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

log = logging.getLogger(__name__)

CLEAN_PROMPTS = [
    "a clean painted wall",
    "a shadow on a wall",
    "furniture",
    "glass",
]
DAMAGE_WORDING = {
    "water_stain": "a wall with a water stain",
    "mould": "a wall with black mould",
    "crack": "a wall with a crack",
    "hole_puncture": "a wall with a hole in it",
    "burn_char": "a wall with a burn mark",
    "missing_material": "a wall with missing plaster",
    "peeling_paint": "a wall with peeling paint",
}


def keep_best_damage_label(detections, iou_threshold: float = 0.55) -> list:
    """Drop a detection when an overlapping distractor label scores higher.

    OWLv2 scores every prompt independently, so the same box can come back as
    both "a crack" and "a cable". Whichever scores higher is the model's
    actual opinion about that box.
    """
    from cozmo.damage.pipeline import _box_iou

    damage = [d for d in detections if not d.extras.get("is_distractor")]
    distractors = [d for d in detections if d.extras.get("is_distractor")]
    kept = []
    for d in damage:
        beaten_by = None
        for x in distractors:
            if x.confidence <= d.confidence:
                continue
            if _box_iou(d.box, x.box) >= iou_threshold:
                beaten_by = x
                break
        if beaten_by is None:
            kept.append(d)
        else:
            d.extras["rejected_by"] = f"distractor:{beaten_by.prompt}"
    return kept


@dataclass
class GeometryLimits:
    max_surface_fraction: float = 0.25
    min_area_m2: float = 0.0025  # 5 cm square
    max_plane_distance_m: float = 0.35


def geometry_ok(frame, detection, area_m2: float | None, surface_area_m2: float | None,
                world_point: np.ndarray | None, plane_distance_m: float | None,
                limits: GeometryLimits) -> tuple[bool, str]:
    """Is this box a plausible mark on a real surface? Only decidable with depth."""
    if area_m2 is None:
        return True, "no depth, geometry not checked"
    if area_m2 < limits.min_area_m2:
        return False, f"area {area_m2 * 1e4:.0f} cm2 below the {limits.min_area_m2 * 1e4:.0f} cm2 floor"
    if surface_area_m2 and area_m2 > limits.max_surface_fraction * surface_area_m2:
        return False, (f"area {area_m2:.2f} m2 is over {limits.max_surface_fraction:.0%} of the "
                       f"{surface_area_m2:.2f} m2 surface")
    if plane_distance_m is not None and plane_distance_m > limits.max_plane_distance_m:
        return False, f"{plane_distance_m:.2f} m off any wall, ceiling or floor plane"
    return True, "ok"


def multiview_ok(region, min_frames: int = 2, require_geometry: bool = True) -> tuple[bool, str]:
    """A region must be seen in at least ``min_frames`` distinct frames."""
    frames = {d.frame_id for d in region.detections}
    if len(frames) >= min_frames:
        return True, f"seen in {len(frames)} frames"
    if require_geometry and not region.world_points:
        # Without geometry there is no way to know whether the mark was even
        # visible in another frame, so a single sighting is not held against it.
        return True, "no geometry, single sighting allowed"
    return False, f"seen in only {len(frames)} frame"


class CropVerifier:
    """Zero-shot check on the crop with a second model (SigLIP by default).

    The damage wording competes with plain-surface wording. A crop that scores
    higher as "a clean painted wall" than as the damage class is dropped.
    """

    DEFAULT_MODEL = "google/siglip-base-patch16-224"

    def __init__(self, model_id: str = DEFAULT_MODEL, device: str | None = None,
                 margin: float = 0.0) -> None:
        import torch
        from transformers import AutoModel, AutoProcessor

        from cozmo.damage.detector import pick_device

        self.torch = torch
        self.device = device or pick_device()
        self.margin = margin
        log.info("loading crop verifier %s on %s", model_id, self.device)
        self.processor = AutoProcessor.from_pretrained(model_id)
        self.model = AutoModel.from_pretrained(model_id).to(self.device).eval()

    def score(self, image: np.ndarray, box, damage_class: str) -> tuple[bool, float, str]:
        from PIL import Image

        x0, y0, x1, y1 = (int(round(v)) for v in box)
        h, w = image.shape[:2]
        pad = 8
        x0, y0 = max(x0 - pad, 0), max(y0 - pad, 0)
        x1, y1 = min(x1 + pad, w), min(y1 + pad, h)
        if x1 - x0 < 8 or y1 - y0 < 8:
            return True, 0.0, "crop too small to verify"
        crop = Image.fromarray(image[y0:y1, x0:x1])
        texts = [DAMAGE_WORDING.get(damage_class, f"a wall with {damage_class}")] + CLEAN_PROMPTS
        inputs = self.processor(text=texts, images=crop, return_tensors="pt",
                                padding="max_length", truncation=True).to(self.device)
        with self.torch.no_grad():
            out = self.model(**inputs)
        probs = out.logits_per_image.softmax(dim=-1)[0].float().cpu().numpy()
        best = int(np.argmax(probs))
        keep = best == 0 and (probs[0] - max(probs[1:])) >= self.margin
        why = "verified" if keep else f"crop reads as {texts[best]!r}"
        return keep, float(probs[0]), why


class NullVerifier:
    """Keeps everything. Lets the filter chain be tested without a second model."""

    def score(self, image, box, damage_class: str) -> tuple[bool, float, str]:
        return True, 1.0, "verifier disabled"
