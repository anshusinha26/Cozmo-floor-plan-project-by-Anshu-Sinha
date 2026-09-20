"""SCAFFOLD PLACEHOLDER. This is not a reconstruction.

``StubPipeline`` returns a hand-written two-room plan with plausible values and
deliberately wide intervals so the CLI, schema, renderer and evaluation harness
can be exercised end to end before any computer vision exists. It ignores the
content of the input entirely (files are hashed for provenance only).

It marks itself three ways so it can never be mistaken for a result: this
docstring, a fixed entry in ``Plan.warnings``, and a WARNING log line on
every run.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

from cozmo.contracts.models import (
    Adjacency,
    ConcealedDamageFlag,
    DamageClass,
    DamageRegion,
    Measurement,
    Opening,
    Placement,
    Plan,
    Point,
    Renders,
    Room,
    ScopeItem,
    StitchedPlan,
    Surface,
    Tier,
    Wall,
)
from cozmo.pipeline.base import Pipeline

log = logging.getLogger(__name__)

STUB_WARNING = "STUB PIPELINE: NOT A REAL RECONSTRUCTION"
STUB_ASSUMPTION = (
    "STUB: geometry is hand-written and independent of input content; "
    "input files were hashed for provenance only"
)
METHOD = "stub_hand_written"

# Interval half-widths. Deliberately wide: the stub should read as uncertain.
HALF_LENGTH_M = 0.15
HALF_HEIGHT_M = 0.10
HALF_OPENING_M = 0.08
HALF_ANGLE_DEG = 3.0
REL_AREA = 0.10


def _m(value: float, unit: str, half: float) -> Measurement:
    return Measurement(value=value, ci_low=value - half, ci_high=value + half, unit=unit, method=METHOD)


def _area(value: float) -> Measurement:
    return _m(value, "m2", abs(value) * REL_AREA)


def _rect(w: float, d: float) -> list[Point]:
    """Axis-aligned CCW rectangle with its corner at the origin."""
    return [(0.0, 0.0), (w, 0.0), (w, d), (0.0, d)]


def _walls(prefix: str, polygon: list[Point], height: float) -> list[Wall]:
    walls = []
    n = len(polygon)
    for i in range(n):
        s, e = polygon[i], polygon[(i + 1) % n]
        length = math.hypot(e[0] - s[0], e[1] - s[1])
        walls.append(
            Wall(
                id=f"{prefix}{i + 1}",
                start=s,
                end=e,
                length_m=_m(round(length, 3), "m", HALF_LENGTH_M),
                height_m=_m(height, "m", HALF_HEIGHT_M),
            )
        )
    return walls


def _surfaces(room: Room) -> list[Surface]:
    out = []
    for w in room.walls:
        out.append(
            Surface(
                id=f"s_{room.id}_{w.id}",
                room_id=room.id,
                type="wall",
                wall_id=w.id,
                area_m2=_area(round(w.length_m.value * w.height_m.value, 3)),
            )
        )
    out.append(Surface(id=f"s_{room.id}_floor", room_id=room.id, type="floor", area_m2=room.floor_area_m2))
    out.append(Surface(id=f"s_{room.id}_ceiling", room_id=room.id, type="ceiling", area_m2=room.floor_area_m2))
    return out


class StubPipeline(Pipeline):
    name = "stub"
    version = "0.1.0"

    def run(self, input_path: Path, tier: Tier, config: dict[str, Any], seed: int) -> Plan:
        log.warning("%s (input=%s, tier=%s, seed=%d)", STUB_WARNING, input_path, tier, seed)

        with self.stage("provenance"):
            capture, run = self.provenance(input_path, tier, config, seed)

        with self.stage("hand_written_geometry"):
            height = 2.70
            living_poly = _rect(4.2, 4.4)
            living = Room(
                id="living",
                label="Living room",
                polygon=living_poly,
                walls=_walls("w", living_poly, height),
                ceiling_height_m=_m(height, "m", HALF_HEIGHT_M),
                floor_area_m2=_area(round(4.2 * 4.4, 3)),
                openings=[
                    Opening(
                        id="o1",
                        type="door",
                        wall_id="w2",
                        offset_along_wall_m=_m(0.70, "m", HALF_LENGTH_M),
                        width_m=_m(0.82, "m", HALF_OPENING_M),
                        height_m=_m(2.03, "m", HALF_OPENING_M),
                        sill_height_m=None,
                        detection_confidence=0.5,
                    ),
                    Opening(
                        id="o2",
                        type="window",
                        wall_id="w3",
                        offset_along_wall_m=_m(1.50, "m", HALF_LENGTH_M),
                        width_m=_m(1.20, "m", HALF_OPENING_M),
                        height_m=_m(1.10, "m", HALF_OPENING_M),
                        sill_height_m=_m(0.90, "m", HALF_OPENING_M),
                        detection_confidence=0.5,
                    ),
                ],
            )
            hall_poly = _rect(1.2, 3.0)
            hall = Room(
                id="hall",
                label="Hall",
                polygon=hall_poly,
                walls=_walls("h", hall_poly, height),
                ceiling_height_m=_m(height, "m", HALF_HEIGHT_M),
                floor_area_m2=_area(round(1.2 * 3.0, 3)),
                openings=[],
            )

        with self.stage("hand_written_stitch"):
            # Hall sits against the living room's east wall (w2), door at y=0.7.
            footprint = [
                (0.0, 0.0), (4.2, 0.0), (4.2, 0.7), (5.4, 0.7),
                (5.4, 3.7), (4.2, 3.7), (4.2, 4.4), (0.0, 4.4),
            ]
            stitched = StitchedPlan(
                placements=[
                    Placement(room_id="living", tx=0.0, ty=0.0, theta_deg=_m(0.0, "deg", HALF_ANGLE_DEG)),
                    Placement(room_id="hall", tx=4.2, ty=0.7, theta_deg=_m(0.0, "deg", HALF_ANGLE_DEG)),
                ],
                footprint_polygon=footprint,
                footprint_area_m2=_area(round(4.2 * 4.4 + 1.2 * 3.0, 3)),
                overlap_area_m2=Measurement(value=0.0, ci_low=0.0, ci_high=0.05, unit="m2", method=METHOD),
            )

        with self.stage("hand_written_damage"):
            surfaces = _surfaces(living) + _surfaces(hall)
            damage = [
                DamageRegion(
                    id="d1",
                    surface_id="s_living_w1",
                    damage_class=DamageClass.water_stain,
                    extent_m2=_m(0.35, "m2", 0.20),
                    polygon=[(1.0, 0.1), (1.7, 0.1), (1.7, 0.6), (1.0, 0.6)],
                    confidence=0.5,
                )
            ]
            concealed = [
                ConcealedDamageFlag(
                    id="c1",
                    surface_id="s_living_floor",
                    rule_id="CD-01",
                    rule_text="Water stain within 0.3 m of the floor on a wall implies possible moisture under adjacent flooring",
                    evidence=["d1"],
                    confidence=0.3,
                )
            ]
            scope = [
                ScopeItem(
                    id="sc1",
                    surface_id="s_living_w1",
                    damage_region_ids=["d1"],
                    description="Stain-block and repaint water-stained wall area",
                    quantity=_m(0.35, "m2", 0.20),
                    basis="damage region extent_m2",
                )
            ]

        return Plan(
            capture=capture,
            run=run,
            rooms=[living, hall],
            adjacency=[Adjacency(room_a="living", room_b="hall", via_opening_id="o1")],
            stitched_plan=stitched,
            surfaces=surfaces,
            damage_regions=damage,
            concealed_damage_flags=concealed,
            scope_items=scope,
            assumptions=[STUB_ASSUMPTION],
            warnings=[STUB_WARNING],
            renders=Renders(),
        )
