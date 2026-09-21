"""Video tier: one video file in, one dimensioned plan out.

The tier reads the video and nothing else. No depth sensor, no device poses,
no intrinsics from the capture. Stage order:

``frames`` decode and blur filter, ``sfm`` COLMAP poses and sparse points,
``scale`` metres per SfM unit per chunk, ``bridge`` chunk to chunk rigid
transforms, ``dense`` fused metric cloud, ``up`` gravity, then the same
plan-building backend the LiDAR tier uses through
:func:`cozmo.pipeline.video.adapter.plan_from_cloud`.

``sfm`` runs in a subprocess on purpose: pycolmap and torch each link their own
libomp and importing both into one process aborts the interpreter.
"""

from __future__ import annotations

__all__ = ["VideoPipeline"]


def __getattr__(name: str):
    if name == "VideoPipeline":
        from cozmo.pipeline.video.pipeline import VideoPipeline

        return VideoPipeline
    raise AttributeError(name)
