"""Tier-agnostic damage detection, concealed-damage rules and scope items.

The module takes an iterator of frames and the plan's surfaces, so the same
code serves the photo, video and LiDAR tiers. What a tier can supply decides
how much can be said: with metric depth an extent is measured, without it the
region is emitted with an explicitly unbounded extent and a warning.
"""

from cozmo.damage.frames import DamageFrame, frames_from_images, frames_from_stray
from cozmo.damage.pipeline import DamageResult, analyse_damage

__all__ = ["DamageFrame", "DamageResult", "analyse_damage", "frames_from_images", "frames_from_stray"]
