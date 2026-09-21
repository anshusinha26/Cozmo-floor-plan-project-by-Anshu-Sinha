"""Several one-room plans into one property plan.

Each room is reconstructed on its own, so each arrives as a complete Plan with a
single room in its own frame. Merging is a rigid transform per room, taken from
the stitch, applied to the polygon and to the wall endpoints. Openings survive
untouched because their offsets are measured along their own wall.

What changes is the honesty of the stitched block: the placements are real
numbers now rather than the identity, they are marked approximate, and the
footprint interval is widened because the arrangement was assumed rather than
measured.
"""

from __future__ import annotations

import logging

import numpy as np
from shapely.geometry import Polygon as SPoly

from cozmo.contracts.models import (
    Adjacency,
    Measurement,
    Placement,
    Plan,
    Renders,
    Room,
    StitchedPlan,
    Surface,
    Wall,
)

log = logging.getLogger(__name__)

# The arrangement is a guess, so the property outline is much less certain than
# any single room in it. This multiplies the footprint's own interval.
FOOTPRINT_WIDENING = 2.5


def _rebase(ident: str, old_room: str, new_room: str) -> str:
    """Rename an id that carries its room's name, keeping the rest intact."""
    if old_room and old_room in ident:
        return ident.replace(old_room, new_room, 1)
    return f"{new_room}_{ident}"


def _rotation(theta_deg: float) -> np.ndarray:
    t = np.radians(theta_deg)
    return np.array([[np.cos(t), -np.sin(t)], [np.sin(t), np.cos(t)]])


def _apply(R: np.ndarray, t: np.ndarray, p) -> tuple[float, float]:
    v = R @ np.asarray(p, dtype=float) + t
    return (float(v[0]), float(v[1]))


def merge(per_room: dict[str, Plan], stitch_result, capture, run, ci_level: float,
          warnings: list[str], assumptions: list[str]) -> Plan:
    """One Plan for the property, from one Plan per room plus a stitch."""
    placements: list[Placement] = []
    rooms: list[Room] = []
    surfaces: list[Surface] = []

    for placed in stitch_result.placed:
        plan = per_room.get(placed.room_id)
        if plan is None or not plan.rooms:
            continue
        src = plan.rooms[0]
        R = _rotation(placed.theta_deg)
        t = np.array([placed.tx, placed.ty], dtype=float)
        # The stitch rotated about the room's own anchor, so reproduce that here
        # by using the polygon the stitch actually produced.
        polygon = [tuple(map(float, p)) for p in placed.polygon]
        if not SPoly(polygon).exterior.is_ccw:
            polygon = polygon[::-1]
        walls = [Wall(id=w.id, start=_apply(R, t, w.start), end=_apply(R, t, w.end),
                      length_m=w.length_m, height_m=w.height_m) for w in src.walls]
        # Every room was reconstructed on its own, so each one calls itself
        # room_01 and names its surfaces and openings after that. Ids are unique
        # across the whole plan, so they are rebased onto the folder name here.
        openings = [o.model_copy(deep=True, update={"id": _rebase(o.id, src.id, placed.room_id)})
                    for o in src.openings]
        room = Room(id=placed.room_id, label=src.label, polygon=polygon, walls=walls,
                    ceiling_height_m=src.ceiling_height_m, floor_area_m2=src.floor_area_m2,
                    openings=openings)
        rooms.append(room)
        for surf in plan.surfaces:
            surfaces.append(surf.model_copy(update={
                "room_id": placed.room_id, "id": _rebase(surf.id, src.id, placed.room_id)}))
        placements.append(Placement(
            room_id=placed.room_id, tx=float(placed.tx), ty=float(placed.ty),
            theta_deg=Measurement(value=float(placed.theta_deg),
                                  ci_low=float(placed.theta_deg) - 15.0,
                                  ci_high=float(placed.theta_deg) + 15.0, unit="deg",
                                  method="star_layout_assumption_" + placed.attached_by,
                                  ci_level=ci_level)))

    if not rooms:
        raise ValueError("no room survived the stitch")

    area = float(stitch_result.footprint_area_m2)
    # The interval is the quadrature sum of the rooms' own area intervals, then
    # widened because where they sit relative to each other was not measured.
    rel = np.sqrt(sum((r.floor_area_m2.width / 2 / max(r.floor_area_m2.value, 1e-6)) ** 2
                      for r in rooms)) if rooms else 0.2
    half = max(rel * area * FOOTPRINT_WIDENING, 0.5)
    stitched = StitchedPlan(
        placements=placements, footprint_polygon=stitch_result.footprint,
        footprint_area_m2=Measurement(value=area, ci_low=area - half, ci_high=area + half,
                                      unit="m2", method="star_layout_union_of_rooms",
                                      ci_level=ci_level),
        overlap_area_m2=Measurement(value=float(stitch_result.overlap_m2),
                                    ci_low=0.0, ci_high=float(stitch_result.overlap_m2) + 0.05,
                                    unit="m2", method="pairwise_polygon_intersection",
                                    ci_level=ci_level))

    known = {r.id for r in rooms}
    opening_ids = {o.id for r in rooms for o in r.openings}
    adjacency = [Adjacency(room_a=a, room_b=b,
                           via_opening_id=v if v and v in opening_ids else None)
                 for a, b, v in stitch_result.adjacency if a in known and b in known]

    merged_warnings = list(warnings) + list(stitch_result.warnings)
    for rid, plan in per_room.items():
        for w in plan.warnings:
            merged_warnings.append(f"{rid}: {w}")
    seen: set[str] = set()
    merged_warnings = [w for w in merged_warnings if not (w in seen or seen.add(w))]
    merged_assumptions = list(assumptions)
    for plan in per_room.values():
        for a in plan.assumptions:
            if a not in merged_assumptions:
                merged_assumptions.append(a)

    from cozmo.pipeline.video.intervals import clamp_plan_intervals

    log.info("merged %d rooms into one property, footprint %.2f m2", len(rooms), area)
    plan = Plan(capture=capture, run=run, rooms=rooms, adjacency=adjacency,
                stitched_plan=stitched, surfaces=surfaces, damage_regions=[],
                concealed_damage_flags=[], scope_items=[], assumptions=merged_assumptions,
                warnings=merged_warnings, renders=Renders())
