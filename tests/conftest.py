"""Shared fixtures: a small hand-built plan used to exercise the contract."""

from __future__ import annotations

from typing import Any

import pytest


def m(value: float, unit: str = "m", half: float = 0.05, method: str = "test") -> dict[str, Any]:
    """Measurement dict with a symmetric interval, for building fixtures tersely."""
    return {
        "value": value,
        "ci_low": value - half,
        "ci_high": value + half,
        "unit": unit,
        "method": method,
    }


def two_room_plan_dict() -> dict[str, Any]:
    """Minimal valid two-room plan as plain dicts (so tests can mutate it)."""
    living = {
        "id": "living",
        "label": "Living room",
        "polygon": [[0.0, 0.0], [4.0, 0.0], [4.0, 3.0], [0.0, 3.0]],
        "walls": [
            {"id": "w1", "start": [0.0, 0.0], "end": [4.0, 0.0], "length_m": m(4.0), "height_m": m(2.7)},
            {"id": "w2", "start": [4.0, 0.0], "end": [4.0, 3.0], "length_m": m(3.0), "height_m": m(2.7)},
            {"id": "w3", "start": [4.0, 3.0], "end": [0.0, 3.0], "length_m": m(4.0), "height_m": m(2.7)},
            {"id": "w4", "start": [0.0, 3.0], "end": [0.0, 0.0], "length_m": m(3.0), "height_m": m(2.7)},
        ],
        "ceiling_height_m": m(2.7),
        "floor_area_m2": m(12.0, "m2", 0.5),
        "openings": [
            {
                "id": "o1",
                "type": "door",
                "wall_id": "w2",
                "offset_along_wall_m": m(1.0),
                "width_m": m(0.8),
                "height_m": m(2.0),
                "sill_height_m": None,
                "detection_confidence": 0.9,
            }
        ],
    }
    hall = {
        "id": "hall",
        "label": "Hall",
        "polygon": [[0.0, 0.0], [1.2, 0.0], [1.2, 3.0], [0.0, 3.0]],
        "walls": [
            {"id": "h1", "start": [0.0, 0.0], "end": [1.2, 0.0], "length_m": m(1.2), "height_m": m(2.7)},
            {"id": "h2", "start": [1.2, 0.0], "end": [1.2, 3.0], "length_m": m(3.0), "height_m": m(2.7)},
            {"id": "h3", "start": [1.2, 3.0], "end": [0.0, 3.0], "length_m": m(1.2), "height_m": m(2.7)},
            {"id": "h4", "start": [0.0, 3.0], "end": [0.0, 0.0], "length_m": m(3.0), "height_m": m(2.7)},
        ],
        "ceiling_height_m": m(2.7),
        "floor_area_m2": m(3.6, "m2", 0.3),
        "openings": [],
    }
    return {
        "schema_version": "1.0.0",
        "capture": {
            "id": "apt_living_01",
            "tier": "video",
            "device": None,
            "captured_at": None,
            "input_manifest_sha256": "0" * 64,
        },
        "run": {
            "pipeline_version": "test-0",
            "git_commit": None,
            "config_sha256": "0" * 64,
            "seed": 0,
        },
        "rooms": [living, hall],
        "adjacency": [{"room_a": "living", "room_b": "hall", "via_opening_id": "o1"}],
        "stitched_plan": {
            "placements": [
                {"room_id": "living", "tx": 0.0, "ty": 0.0, "theta_deg": m(0.0, "deg", 1.0)},
                {"room_id": "hall", "tx": 4.0, "ty": 0.0, "theta_deg": m(0.0, "deg", 1.0)},
            ],
            "footprint_polygon": [[0.0, 0.0], [5.2, 0.0], [5.2, 3.0], [0.0, 3.0]],
            "footprint_area_m2": m(15.6, "m2", 0.8),
            "overlap_area_m2": m(0.0, "m2", 0.0),
        },
        "surfaces": [
            {"id": "s_living_w1", "room_id": "living", "type": "wall", "wall_id": "w1", "area_m2": m(10.8, "m2", 0.4)},
            {"id": "s_living_floor", "room_id": "living", "type": "floor", "wall_id": None, "area_m2": m(12.0, "m2", 0.5)},
        ],
        "damage_regions": [
            {
                "id": "d1",
                "surface_id": "s_living_w1",
                "damage_class": "water_stain",
                "extent_m2": m(0.3, "m2", 0.1),
                "polygon": [[1.0, 1.0], [1.5, 1.0], [1.5, 1.6], [1.0, 1.6]],
                "confidence": 0.7,
            }
        ],
        "concealed_damage_flags": [
            {
                "id": "c1",
                "surface_id": "s_living_floor",
                "rule_id": "R1",
                "rule_text": "water stain on wall base implies possible subfloor moisture",
                "evidence": ["d1"],
                "confidence": 0.4,
            }
        ],
        "scope_items": [
            {
                "id": "sc1",
                "surface_id": "s_living_w1",
                "damage_region_ids": ["d1"],
                "description": "Treat and repaint stained wall area",
                "quantity": m(0.3, "m2", 0.1),
                "basis": "damage region extent",
            }
        ],
        "assumptions": ["fixture"],
        "warnings": [],
        "renders": {"plan_png": None, "plan_svg": None},
    }


@pytest.fixture
def plan_dict() -> dict[str, Any]:
    return two_room_plan_dict()
