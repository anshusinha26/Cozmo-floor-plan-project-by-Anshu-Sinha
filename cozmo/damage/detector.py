"""Open-vocabulary damage detection with OWLv2 (Apache 2.0).

OWLv2 takes text prompts, so damage classes are described in words rather
than trained for. Several prompts per class, because "a damp patch" and "a
water stain" find different things and a surveyor would call both a stain.

The model is not the point of this module: `Detector` is an interface, and
`DummyDetector` lets everything downstream be tested without weights.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Iterable, Protocol

import numpy as np

from cozmo.contracts.models import DamageClass

log = logging.getLogger(__name__)

MODEL_ID = "google/owlv2-base-patch16-ensemble"

# Prompt sets per class. Each entry maps a phrase to the class it evidences.
PROMPTS: dict[str, list[str]] = {
    DamageClass.water_stain.value: [
        "a water stain on the wall",
        "a brown damp patch on the wall",
        "a water stain on the ceiling",
    ],
    DamageClass.mould.value: [
        "black mould on the wall",
        "mildew growing in the corner of a wall",
    ],
    DamageClass.crack.value: [
        "a crack in the wall",
        "a crack in the plaster",
    ],
    DamageClass.hole_puncture.value: [
        "a hole in the wall",
        "a puncture in the plasterboard",
    ],
    DamageClass.burn_char.value: [
        "a burn mark on the wall",
        "charred scorched wall surface",
    ],
    DamageClass.missing_material.value: [
        "missing plaster exposing the wall behind",
        "a missing tile on the wall",
    ],
    DamageClass.peeling_paint.value: [
        "peeling paint on the wall",
        "flaking paint on the wall",
    ],
}


@dataclass
class Detection:
    damage_class: str
    prompt: str
    confidence: float
    box: tuple[float, float, float, float]  # x0, y0, x1, y1 in image pixels
    frame_id: str
    extras: dict = field(default_factory=dict)

    @property
    def centre(self) -> tuple[float, float]:
        x0, y0, x1, y1 = self.box
        return ((x0 + x1) / 2, (y0 + y1) / 2)


class Detector(Protocol):
    def detect(self, image: np.ndarray, frame_id: str) -> list[Detection]:
        ...


class DummyDetector:
    """Returns fixed boxes. Lets the rest of the module be tested without weights."""

    def __init__(self, boxes: dict[str, list[Detection]] | None = None) -> None:
        self.boxes = boxes or {}

    def detect(self, image: np.ndarray, frame_id: str) -> list[Detection]:
        return list(self.boxes.get(frame_id, []))


def pick_device(preferred: Iterable[str] = ("cuda", "mps", "cpu")) -> str:
    import torch

    for name in preferred:
        if name == "cuda" and torch.cuda.is_available():
            return "cuda"
        if name == "mps" and torch.backends.mps.is_available():
            return "mps"
        if name == "cpu":
            return "cpu"
    return "cpu"


class Owlv2Detector:
    """OWLv2 behind the `Detector` interface.

    Weights are fetched by ``scripts/fetch_damage_weights.py``; nothing here
    downloads during a run without saying so.
    """

    # 0.20 is the only setting measured on the staged captures that keeps both
    # planted classes. Precision there is poor; see docs/damage_eval/README.md.
    DEFAULT_THRESHOLD = 0.20

    def __init__(self, threshold: float = DEFAULT_THRESHOLD, device: str | None = None,
                 model_id: str = MODEL_ID) -> None:
        import torch
        from transformers import Owlv2ForObjectDetection, Owlv2Processor

        self.torch = torch
        self.device = device or pick_device()
        self.threshold = threshold
        log.info("loading %s on %s", model_id, self.device)
        self.processor = Owlv2Processor.from_pretrained(model_id)
        self.model = Owlv2ForObjectDetection.from_pretrained(model_id).to(self.device).eval()
        self.prompts: list[str] = []
        self.prompt_class: list[str] = []
        for cls, phrases in PROMPTS.items():
            for p in phrases:
                self.prompts.append(p)
                self.prompt_class.append(cls)

    def detect(self, image: np.ndarray, frame_id: str) -> list[Detection]:
        from PIL import Image

        pil = Image.fromarray(image)
        inputs = self.processor(text=[self.prompts], images=pil, return_tensors="pt").to(self.device)
        with self.torch.no_grad():
            out = self.model(**inputs)
        sizes = self.torch.tensor([[pil.height, pil.width]]).to(self.device)
        res = self.processor.post_process_grounded_object_detection(
            out, threshold=self.threshold, target_sizes=sizes)[0]
        dets = []
        for score, label, box in zip(res["scores"], res["labels"], res["boxes"]):
            i = int(label)
            dets.append(Detection(damage_class=self.prompt_class[i], prompt=self.prompts[i],
                                  confidence=float(score),
                                  box=tuple(float(v) for v in box), frame_id=frame_id))
        dets.sort(key=lambda d: (-d.confidence, d.damage_class))
        return dets
