"""The two monocular metric depth models, loaded once and reused.

Depth Pro is used for scale because it is the only one of the two that lands
within a couple of percent of truth, and only when it is told the focal length.
Left to its own focal estimate it overshoots by about 26% and drags depth with
it (spike 2: it guessed 1365 px where the truth was 1071). COLMAP already
estimates the focal from the same frames, so the tier hands that over.

Depth Anything V2 Metric Indoor is used for the dense pass. It carries a fixed
bias of roughly +35%, which does not matter there because every depth map is
fitted to that frame's SfM sparse depths before it is unprojected, and it is
eight times faster than Depth Pro per frame.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

DEPTH_PRO_REPO = "apple/DepthPro"
DEPTH_PRO_FILE = "depth_pro.pt"
DAV2_MODEL = "depth-anything/Depth-Anything-V2-Metric-Indoor-Large-hf"


class DepthProRunner:
    """Apple Depth Pro. ``infer`` returns metres at the input resolution."""

    name = "depth_pro"

    def __init__(self, device: str) -> None:
        import depth_pro
        import torch
        from huggingface_hub import hf_hub_download

        self.torch = torch
        self.device = torch.device(device)
        cfg = depth_pro.depth_pro.DEFAULT_MONODEPTH_CONFIG_DICT
        # The packaged config points at ./checkpoints/depth_pro.pt, which only
        # exists in a clone of the upstream repo. DepthProConfig is a dataclass,
        # not a namedtuple, so _replace does not exist; assign the field.
        cfg.checkpoint_uri = hf_hub_download(DEPTH_PRO_REPO, DEPTH_PRO_FILE)
        self.model, self.transform = depth_pro.create_model_and_transforms(
            config=cfg, device=self.device, precision=torch.float32)
        self.model.eval()
        self._load_rgb = depth_pro.load_rgb

    def infer(self, path: Path, focal_px: float | None = None) -> tuple[np.ndarray, float]:
        """Metric depth in metres and the focal length actually used."""
        img, _, _ = self._load_rgb(str(path))
        f_in = None if focal_px is None else self.torch.tensor(float(focal_px))
        with self.torch.no_grad():
            p = self.model.infer(self.transform(img), f_px=f_in)
        return p["depth"].detach().float().cpu().numpy(), float(p["focallength_px"])


class DepthAnythingRunner:
    """Depth Anything V2 Metric Indoor Large through transformers."""

    name = "depth_anything_v2_metric_indoor"

    def __init__(self, device: str) -> None:
        import torch
        from transformers import AutoImageProcessor, AutoModelForDepthEstimation

        self.torch = torch
        self.device = torch.device(device)
        self.processor = AutoImageProcessor.from_pretrained(DAV2_MODEL)
        self.model = AutoModelForDepthEstimation.from_pretrained(DAV2_MODEL).to(self.device).eval()

    def infer(self, path: Path, focal_px: float | None = None) -> tuple[np.ndarray, float]:
        from PIL import Image

        pil = Image.open(path).convert("RGB")
        inputs = self.processor(images=pil, return_tensors="pt").to(self.device)
        with self.torch.no_grad():
            out = self.model(**inputs)
        post = self.processor.post_process_depth_estimation(out, target_sizes=[(pil.height, pil.width)])
        return post[0]["predicted_depth"].float().cpu().numpy(), float("nan")


def sync(device: str) -> None:
    """Make device timings honest before stopping a clock."""
    import torch

    if device == "cuda":
        torch.cuda.synchronize()
    elif device == "mps":
        torch.mps.synchronize()
