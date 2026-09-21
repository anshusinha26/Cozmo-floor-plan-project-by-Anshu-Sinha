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


def _fit_rigid(src, dst) -> tuple[np.ndarray, np.ndarray] | None:
    """The rotation and translation taking ``src`` points onto ``dst`` points.

    The stitch rotates a room about its own anchor and returns the placed
    polygon, while the recorded (theta, tx, ty) rotate about the origin. Using
    the second on the walls while taking the first for the polygon puts the two
    in different frames, which is how a room came out with its walls drawn
    somewhere else. Recovering the transform from the polygon the stitch
    actually produced keeps every part of the room in one frame, whatever
    convention the stitch used internally.

    Kabsch with no scaling, on corresponding vertices. Returns None when the
    two polygons do not correspond, so the caller can fall back.
    """
    src = np.asarray(src, dtype=float)
    dst = np.asarray(dst, dtype=float)
    if src.shape != dst.shape or len(src) < 2:
        return None
    sc = src.mean(axis=0)
    dc = dst.mean(axis=0)
    H = (src - sc).T @ (dst - dc)
    U, _, Vt = np.linalg.svd(H)
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    R = Vt.T @ np.diag([1.0, d]) @ U.T
    t = dc - R @ sc
    if not np.allclose((src @ R.T) + t, dst, atol=1e-6):
        return None
    return R, t


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
        polygon = [tuple(map(float, p)) for p in placed.polygon]
        # Recover the transform from the polygon the stitch produced, so the
        # walls land in the same frame as the fill they belong to. Falls back to
        # the recorded placement only if the polygons do not correspond.
        fit = _fit_rigid(src.polygon, placed.polygon)
        if fit is None:
            R = _rotation(placed.theta_deg)
            t = np.array([placed.tx, placed.ty], dtype=float)
            warnings.append(
                f"{placed.room_id}: could not recover the stitch transform from the polygon, "
                "so walls fall back to the recorded placement and may not sit on the outline")
        else:
            R, t = fit
        if not SPoly(polygon).exterior.is_ccw:
            polygon = polygon[::-1]
        walls = [Wall(id=w.id, start=_apply(R, t, w.start), end=_apply(R, t, w.end),
                      length_m=w.length_m, height_m=w.height_m) for w in src.walls]
        # Every room was reconstructed on its own, so each one calls itself
        # room_01 and names its surfaces and openings after that. Ids are unique
        # across the whole plan, so they are rebased onto the folder name here.
        openings = [o.model_copy(deep=True, update={"id": _rebase(o.id, src.id, placed.room_id)})
                    for o in src.openings]
        # "room" is what a single-room reconstruction calls itself. Once it is
        # placed in a property it has a name, and the plan should show it.
        label = src.label if src.label and src.label != "room" else \
            placed.room_id.replace("_", " ").title()
        room = Room(id=placed.room_id, label=label, polygon=polygon, walls=walls,
                    ceiling_height_m=src.ceiling_height_m, floor_area_m2=src.floor_area_m2,
                    openings=openings)
        rooms.append(room)
        for surf in plan.surfaces:
            surfaces.append(surf.model_copy(update={
                "room_id": placed.room_id, "id": _rebase(surf.id, src.id, placed.room_id)}))
        # The polygon and the walls above are already in the stitched frame:
        # the rotation and translation have been applied to them. Recording the
        # same transform again would make the placement a second application,
        # and a consumer following the contract would move every room on top of
        # the others. The placement is therefore the identity, exactly as the
        # lidar tier emits it, and the transform that was applied is kept in the
        # method string so nothing is lost. The interval on theta stays: where a
        # room sits relative to the others really is uncertain by about 15
        # degrees, and that is a property of the stitch, not of the frame.
        placements.append(Placement(
            room_id=placed.room_id, tx=0.0, ty=0.0,
            theta_deg=Measurement(value=0.0, ci_low=-15.0, ci_high=15.0, unit="deg",
                                  method=(f"star_layout_assumption_{placed.attached_by}"
                                          f"_applied_theta_{float(placed.theta_deg):.1f}"
                                          f"_tx_{float(placed.tx):.3f}_ty_{float(placed.ty):.3f}"),
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
    return clamp_plan_intervals(plan, [])
