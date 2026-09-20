"""Pipeline registry.

The lidar and video tiers run real reconstructions. The photo tier has none yet
and falls back to the stub, which marks itself in warnings. ``--pipeline stub``
forces the stub for any tier.
"""

from __future__ import annotations

from cozmo.pipeline.base import Pipeline

REAL_BY_TIER = {"lidar": "lidar", "video": "video"}


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
    if name == "video":
        from cozmo.pipeline.video.pipeline import VideoPipeline

        return VideoPipeline()
    raise KeyError(f"unknown pipeline {name!r}; available: stub, lidar, video")
