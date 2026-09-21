"""Damage detection as a stage of `cozmo run`.

The damage module was reachable only through `scripts/run_damage_eval.py`, so
a plan written by the command line always carried an empty damage list and a
warning saying the feature was not implemented. It was implemented; it was
just not wired. This module is the wire.

**Why `auto` is the default.** The weights are 1.4 GB and the lidar profile is
meant to install in seconds without them, so requiring them would break the
quick path. Defaulting to on when they are present and off when they are not
keeps both honest, provided the plan says which happened: an empty
`damage_regions` list means "none found" and "never looked" equally well, and
those are not the same claim.
"""

from __future__ import annotations

import enum
import logging
from pathlib import Path
from typing import Iterable

from cozmo.contracts.models import Plan
from cozmo.damage.frames import DamageFrame

log = logging.getLogger(__name__)

DAMAGE_OFF_WARNING = "Damage detection did not run"
DAMAGE_TIER_UNSUPPORTED = (
    "the video tier has no frame source wired into the damage stage yet, so damage was not "
    "looked for on this capture even though the weights are present")


class DamageMode(enum.Enum):
    on = "on"
    off = "off"


def weights_present() -> bool:
    """True when both damage checkpoints are already in the HuggingFace cache.

    Checked by looking, not by importing: loading the models costs seconds and
    a chunk of memory, and `auto` has to decide before paying that.
    """
    try:
        from huggingface_hub import constants
    except ImportError:
        return False
    hub = Path(constants.HF_HUB_CACHE)
    needed = ("models--google--owlv2-base-patch16-ensemble", "models--google--siglip-base-patch16-224")
    return all((hub / n).is_dir() and any((hub / n / "snapshots").glob("*")) for n in needed)


def resolve_damage_mode(requested: str, weights_present: bool) -> DamageMode:
    """Turn the flag into a decision, refusing to fake the one that cannot be met."""
    if requested == "off":
        return DamageMode.off
    if requested == "on":
        if not weights_present:
            raise RuntimeError(
                "--damage on was asked for but the damage weights are not installed; "
                "run scripts/fetch_weights.sh damage, or use --damage auto")
        return DamageMode.on
    if requested != "auto":
        raise ValueError(f"unknown --damage value {requested!r}: expected auto, on or off")
    return DamageMode.on if weights_present else DamageMode.off


def run_damage_stage(plan: Plan, mode: DamageMode, frames: Iterable[DamageFrame] | None,
                     detector, cfg: dict, reason: str | None = None,
                     fallback_surface_id: str | None = None, verifier=None) -> Plan:
    """Return the plan with damage attached, or with a warning saying why not."""
    if mode is DamageMode.off or frames is None or detector is None:
        why = f"{DAMAGE_OFF_WARNING}: {reason or 'it was switched off'}. "
        why += "damage_regions, concealed_damage_flags and scope_items are empty for that reason, "
        why += "not because the capture is undamaged"
        return plan.model_copy(update={"warnings": list(plan.warnings) + [why]})

    from cozmo.damage.pipeline import analyse_damage

    surface_id = fallback_surface_id or (plan.surfaces[0].id if plan.surfaces else None)
    result = analyse_damage(frames, plan, detector, cfg, fallback_surface_id=surface_id,
                            verifier=verifier)
    log.info("damage: %d detection(s) merged into %d region(s)", result.detections, result.merged)
    extra = list(result.warnings)
    if any(r.extent_m2.method == "unbounded_no_metric_depth" for r in result.regions):
        # Merging repeats needs a world point per detection, which needs depth.
        # Without it one mark photographed nine times can survive as several
        # regions, so the count is an upper bound on the marks in the room.
        extra.append(
            "Without metric depth the same mark seen in several photos cannot be merged, so "
            "damage_regions counts detections per photo and over-counts the marks present. "
            "Read the count as an upper bound, not as a number of defects")
    return plan.model_copy(update={
        "damage_regions": list(result.regions),
        "concealed_damage_flags": list(result.flags),
        "scope_items": list(result.scope_items),
        "warnings": list(plan.warnings) + extra,
    })


def frames_for_tier(tier: str, input_path: Path, spec, cfg: dict):
    """The frame source for a tier, or None with the reason it has none.

    The lidar tier is the only one with metric depth and poses at hand, so it
    is the only tier whose damage extents are measured rather than bounded.
    The photo tier's reconstruction does hold per-view points and poses, but
    they sit in the reconstruction's own frame, and mapping them to the plan's
    world means repeating the gravity rotation and scale the pipeline applied.
    Getting that wrong attaches a mark to the wrong wall silently, which is
    worse than saying the extent is unbounded, so the photos are read as plain
    images until that transform is exposed.
    """
    from cozmo.damage.frames import frames_from_images, frames_from_stray

    if tier == "lidar":
        from cozmo.io.stray import StrayScan

        dcfg = cfg.get("damage", {})
        scan = StrayScan(input_path, "lidar")
        return frames_from_stray(scan, stride=int(dcfg.get("stray_stride", 120)),
                                 max_frames=int(dcfg.get("max_frames", 25))), None
    if tier == "photo":
        images = [f for r in (spec.rooms or []) for f in r.files]
        if not images:
            return None, "no room photos were found to look at"
        return frames_from_images(images), None
    return None, DAMAGE_TIER_UNSUPPORTED


def build_detector(cfg: dict):
    """The real detector, built only once a caller has decided damage is on."""
    from cozmo.damage.detector import Owlv2Detector

    return Owlv2Detector(threshold=float(cfg.get("damage", {}).get("threshold", 0.20)))


def build_verifier(cfg: dict):
    """The SigLIP crop verifier, which does most of the precision work.

    Without it the detector reports dozens of marks in a room with two: the
    ablation puts photos at 63 false regions unfiltered against 8 to 15 with
    the four filters on, and the verifier is the one that moves it most. It is
    optional only so the ablation can measure its effect.
    """
    from cozmo.damage.filters import CropVerifier

    return CropVerifier(margin=float(cfg.get("damage", {}).get("verifier_margin", 0.0)))
