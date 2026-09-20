"""Publish the Plan contract as a versioned JSON Schema artifact.

The schema is generated from the pydantic models so it can never drift from
the code; ``cozmo schema`` writes it to ``schema/plan.schema.json`` and a test
validates real output against it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cozmo.contracts.models import SCHEMA_VERSION, Plan

SCHEMA_ID = "https://cozmo.ai/schema/plan.schema.json"


def build_schema() -> dict[str, Any]:
    schema = Plan.model_json_schema()
    header = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_ID,
        "title": "Plan",
        "version": SCHEMA_VERSION,
        "description": "Cozmo floor plan output contract. Every dimension is a Measurement with a confidence interval.",
    }
    # Header first so the file reads top-down; remaining keys keep pydantic order.
    return {**header, **{k: v for k, v in schema.items() if k not in header}}


def write_schema(out_path: Path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(build_schema(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out_path
