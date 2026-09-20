"""Pipeline registry.

The lidar tier runs the real reconstruction. The photo and video tiers have no
reconstruction yet and fall back to the stub, which marks itself in warnings.
``--pipeline stub`` forces the stub for any tier.
"""

from __future__ import annotations

from cozmo.pipeline.base import Pipeline

REAL_BY_TIER = {"lidar": "lidar"}


def pipeline_for(tier: str, override: str | None = None) -> str:
    if override:
        return override
    return REAL_BY_TIER.get(tier, "stub")


def get_pipeline(name: str) -> Pipeline:
    if name == "stub":
        from cozmo.pipeline.stub import StubPipeline

        return StubPipeline()
    if name == "lidar":
        from cozmo.pipeline.lidar import LidarPipeline

        return LidarPipeline()
    raise KeyError(f"unknown pipeline {name!r}; available: stub, lidar")
