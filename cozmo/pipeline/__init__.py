"""Pipeline registry. Only the stub exists until reconstruction lands."""

from __future__ import annotations

from cozmo.pipeline.base import Pipeline

DEFAULT_PIPELINE = "stub"


def get_pipeline(name: str = DEFAULT_PIPELINE) -> Pipeline:
    if name == "stub":
        from cozmo.pipeline.stub import StubPipeline

        return StubPipeline()
    raise KeyError(f"unknown pipeline {name!r}; available: stub")
