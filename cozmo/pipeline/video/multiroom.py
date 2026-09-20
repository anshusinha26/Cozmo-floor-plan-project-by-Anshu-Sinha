"""A property captured as one clip per room.

Each clip is reconstructed by the ordinary single-clip path, which after fix
loop 2 always produces exactly one room. Nothing relates one clip to another, so
the rooms are stitched with the same star assumption the photo tier uses, and
the placements are marked approximate for the same reason.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from cozmo.contracts.models import Plan, Renders, Tier
from cozmo.pipeline.photo import merge as merge_mod
from cozmo.pipeline.photo import stitch as stitch_mod
from cozmo.pipeline.photo.pipeline import _opening_centre

log = logging.getLogger(__name__)


def run_multi_room(pipeline, spec, input_path: Path, tier: Tier, config: dict[str, Any],
                   seed: int) -> Plan:
    """One plan per room folder, then one property plan."""
    from cozmo.pipeline.video.pipeline import VideoPipeline

    run_cfg = config.get("run", {})
    per_room: dict[str, Plan] = {}
    polygons: dict[str, list[tuple[float, float]]] = {}
    doors: dict[str, list[dict]] = {}
    areas: dict[str, float] = {}
    rows: list[dict] = []
    warnings: list[str] = [f"{len(spec.rooms)} room clips were reconstructed separately and "
                           f"stitched; nothing in the capture relates one room to another"]
    for note in spec.skipped:
        warnings.append(f"Skipped {note}")
    assumptions: list[str] = []

    for room_input in spec.rooms:
        rid = room_input.room_id
        folder = Path(room_input.files[0]).parent
        sub = VideoPipeline()
        sub.input_manifest_sha256 = pipeline.input_manifest_sha256
        if getattr(pipeline, "debug_dir", None):
            sub.debug_dir = Path(pipeline.debug_dir) / rid
        with pipeline.stage(f"room:{rid}"):
            try:
                plan = sub.run(folder, tier, config, seed)
            except (ValueError, RuntimeError, KeyError) as e:
                warnings.append(f"{rid}: no plan could be built ({e})")
                rows.append({"room_id": rid, "error": str(e)})
                continue
        if not plan.rooms:
            warnings.append(f"{rid}: the clip produced no room")
            continue
        per_room[rid] = plan
        if sub.debug_dir is not None:
            # Each room's own plan is written beside its debug output, so a
            # multi-room run doubles as the per-room runs and a before-and-after
            # comparison does not have to reconstruct everything twice.
            Path(sub.debug_dir).mkdir(parents=True, exist_ok=True)
            (Path(sub.debug_dir) / "plan.json").write_bytes(plan.to_json_bytes())
        polygons[rid] = [tuple(p) for p in plan.rooms[0].polygon]
        areas[rid] = plan.rooms[0].floor_area_m2.value
        doors[rid] = [{"id": o.id, "width_m": o.width_m.value,
                       "centre": _opening_centre(plan.rooms[0], o)}
                      for o in plan.rooms[0].openings if o.type == "door"]
        rows.append({"room_id": rid, "report": sub.report})
        for a in plan.assumptions:
            if a not in assumptions:
                assumptions.append(a)

    if not per_room:
        raise ValueError("no room clip produced a plan")

    connector = stitch_mod.choose_connector(list(per_room), areas, run_cfg.get("connector"))
    result = stitch_mod.stitch(polygons, doors, connector)
    assumptions.append(stitch_mod.STAR_ASSUMPTION)
    capture, run = pipeline.provenance(Path(input_path), tier, config, seed)
    plan = merge_mod.merge(per_room, result, capture, run,
                           config["pipeline"]["video"]["uncertainty"]["ci_level"],
                           warnings, assumptions)
    pipeline.report = {"multi_room": True, "connector": connector, "rooms": rows,
                       "stitch": result.summary()}
    pipeline.drift_report = {"tier": "video", "multi_room": True,
                             "note": "drift is corrected inside each room clip"}
    log.info("multi-room video: %d of %d room clips produced a plan, connector %s",
             len(per_room), len(spec.rooms), connector)
    return plan.model_copy(update={"renders": Renders()})
