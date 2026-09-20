"""Photo tier: a handful of stills per room to a dimensioned plan.

Two or more photos of a room, images only, no EXIF required. MapAnything gives
depth, poses and intrinsics; the camera-height prior gives metric scale, because
MapAnything's own scale came out 0.70x in spike 1 and is not trusted; the
single-room fitter from fix loop 2 turns the result into a room. Rooms are then
stitched into one property around a connector.
"""

from __future__ import annotations

__all__ = ["PhotoPipeline"]


def __getattr__(name: str):
    if name == "PhotoPipeline":
        from cozmo.pipeline.photo.pipeline import PhotoPipeline

        return PhotoPipeline
    raise AttributeError(name)
