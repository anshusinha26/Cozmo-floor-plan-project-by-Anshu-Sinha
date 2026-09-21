"""Device selection: cuda, then mps, then cpu."""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

ORDER = ("cuda", "mps", "cpu")


def pick_device(prefer: str | None = None) -> str:
    """First available of cuda, mps, cpu. ``prefer`` short-circuits if available."""
    import torch

    def ok(name: str) -> bool:
        if name == "cuda":
            return torch.cuda.is_available()
        if name == "mps":
            return torch.backends.mps.is_available()
        return True

    if prefer and ok(prefer):
        return prefer
    if prefer:
        log.warning("requested device %s is not available; falling back", prefer)
    for name in ORDER:
        if ok(name):
            return name
    return "cpu"


def autocast_dtype(device: str):
    """Half precision on cuda, float32 elsewhere. MPS half precision produced
    NaNs in Depth Pro during the spike, so it is not used here."""
    import torch

    return torch.float16 if device == "cuda" else torch.float32
