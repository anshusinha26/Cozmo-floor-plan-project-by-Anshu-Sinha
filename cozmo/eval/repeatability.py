"""Pair repeat captures of the same space and tier for the repeatability gate.

Walls are joined through the truth wall id each prediction was matched to, so
two captures are compared wall for wall even if the pipelines numbered them
differently. Every pair of captures of one space at one tier is compared.
"""

from __future__ import annotations

from itertools import combinations
from typing import Any


def repeat_pairs(captures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """``captures``: {capture_id, space_id, tier, walls: {(room_id, truth_wall_id): pred_length}}."""
    rows = []
    ordered = sorted(captures, key=lambda c: c["capture_id"])
    for a, b in combinations(ordered, 2):
        if a["space_id"] != b["space_id"] or a["tier"] != b["tier"]:
            continue
        for key in sorted(set(a["walls"]) & set(b["walls"])):
            room_id, wall_id = key
            rows.append({
                "space_id": a["space_id"], "tier": a["tier"],
                "capture_a": a["capture_id"], "capture_b": b["capture_id"],
                "room_id": room_id, "wall_id": wall_id,
                "a": a["walls"][key], "b": b["walls"][key],
            })
    return rows
