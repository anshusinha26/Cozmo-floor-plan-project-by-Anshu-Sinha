"""A plan's parts must all live in one frame once placements are applied.

The stitched plan is the product surface: if the walls sit somewhere other
than the fill they bound, the picture is wrong even when every number in it is
right. These tests fail on that, rather than leaving it to be noticed by eye.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from shapely.geometry import Point
from shapely.geometry import Polygon as SPoly

from cozmo.contracts.models import Plan
from cozmo.eval.gates import place_polygon, placed_rooms


def wall_endpoints_off_polygon(plan: Plan, tol_m: float = 0.15) -> list[str]:
    """Wall endpoints that do not lie on their own room's placed outline."""
    by_room = {p.room_id: p for p in plan.stitched_plan.placements}
    off: list[str] = []
    for room in plan.rooms:
        placement = by_room[room.id]
        poly = SPoly(place_polygon(room.polygon, placement)).buffer(tol_m)
        for wall in room.walls:
            for name, point in (("start", wall.start), ("end", wall.end)):
                moved = place_polygon([point], placement)[0]
                if not poly.contains(Point(moved)):
                    off.append(f"{room.id}.{wall.id}.{name}")
    return off


def rooms_overlapping(plan: Plan, tol_m2: float = 0.05) -> list[tuple[str, str, float]]:
    placed = placed_rooms(plan)
    ids = list(placed)
    out = []
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            area = SPoly(placed[ids[i]]).intersection(SPoly(placed[ids[j]])).area
            if area > tol_m2:
                out.append((ids[i], ids[j], area))
    return out


def test_walls_lie_on_their_room_outline(plan_dict):
    assert wall_endpoints_off_polygon(Plan.model_validate(plan_dict)) == []


def test_a_wall_moved_off_the_outline_is_caught(plan_dict):
    plan_dict["rooms"][0]["walls"][0]["start"] = [99.0, 99.0]
    off = wall_endpoints_off_polygon(Plan.model_validate(plan_dict))
    assert off and off[0].endswith(".start")


def test_a_placement_applied_to_walls_but_not_the_polygon_is_caught(plan_dict):
    """The exact defect that stacked three rooms in the photo plan.

    Walls in one frame and the polygon in another looks fine in any single
    number and wrong in every picture.
    """
    room = plan_dict["rooms"][0]
    for wall in room["walls"]:
        wall["start"] = [wall["start"][0] + 3.0, wall["start"][1]]
        wall["end"] = [wall["end"][0] + 3.0, wall["end"][1]]
    assert wall_endpoints_off_polygon(Plan.model_validate(plan_dict))


def test_rooms_do_not_overlap_after_placement(plan_dict):
    from tests.test_registration import world_two_room_plan

    assert rooms_overlapping(Plan.model_validate(world_two_room_plan())) == []


def test_stacked_rooms_are_caught():
    """The defect that put three rooms on top of each other.

    The hall's placement is zeroed while its polygon is left where the
    placement would have put it, which is what a double-applied transform
    amounts to: two rooms ending up in the same place.
    """
    from tests.test_registration import world_two_room_plan

    d = world_two_room_plan()
    d["rooms"][1]["polygon"] = [[x - 4.2, y] for x, y in d["rooms"][1]["polygon"]]
    d["rooms"][1]["walls"] = [dict(w, start=[w["start"][0] - 4.2, w["start"][1]],
                                   end=[w["end"][0] - 4.2, w["end"][1]])
                              for w in d["rooms"][1]["walls"]]
    for placement in d["stitched_plan"]["placements"]:
        placement["tx"] = 0.0
    overlaps = rooms_overlapping(Plan.model_validate(d))
    assert overlaps and overlaps[0][2] > 1.0


def test_rigid_fit_recovers_the_stitch_transform():
    """The stitcher recovers its transform from the polygon it produced."""
    from cozmo.pipeline.photo.merge import _fit_rigid

    src = [(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)]
    theta = math.radians(37.0)
    c, s = math.cos(theta), math.sin(theta)
    R = np.array([[c, -s], [s, c]])
    t = np.array([2.5, -1.25])
    dst = [tuple((R @ np.array(p)) + t) for p in src]
    fit = _fit_rigid(src, dst)
    assert fit is not None
    R2, t2 = fit
    assert np.allclose(R2, R, atol=1e-9) and np.allclose(t2, t, atol=1e-9)
    assert _fit_rigid(src, dst[:3]) is None
    assert _fit_rigid(src, [(0.0, 0.0), (8.0, 0.0), (8.0, 6.0), (0.0, 6.0)]) is None
