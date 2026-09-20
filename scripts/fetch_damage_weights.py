#!/usr/bin/env python
"""Fetch the OWLv2 weights the damage detector uses.

Run once before using the detector, so a run never downloads silently:

    .venv/bin/python scripts/fetch_damage_weights.py

Model: google/owlv2-base-patch16-ensemble, Apache 2.0, about 1.5 GB into the
HuggingFace cache. Nothing else in the repository downloads at runtime.
"""

from __future__ import annotations

import sys

from cozmo.damage.detector import MODEL_ID


def main() -> int:
    from transformers import Owlv2ForObjectDetection, Owlv2Processor

    print(f"fetching {MODEL_ID}")
    Owlv2Processor.from_pretrained(MODEL_ID)
    Owlv2ForObjectDetection.from_pretrained(MODEL_ID)
    print("done; weights are in the HuggingFace cache")
    return 0


if __name__ == "__main__":
    sys.exit(main())
