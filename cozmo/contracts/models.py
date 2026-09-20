"""Output contract for a Cozmo plan.

Every model here is a pydantic v2 model with ``extra="forbid"`` so an unknown
key is a hard error rather than silently ignored. The contract is versioned via
``SCHEMA_VERSION`` and published as JSON Schema by ``cozmo schema``.

Design rule for the whole codebase: no dimension is ever a bare float. Anything
with a physical unit is a :class:`Measurement` carrying a confidence interval,
because the harness scores calibration and a bare number has no interval to
score.

Referential integrity (openings point at real walls, adjacency at real rooms,
scope items at real damage regions) is validated here rather than downstream,
so a plan that loads is a plan whose graph is consistent. The evaluator can then
count matched / missed / phantom entities without first repairing the input.
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "1.0.0"

Unit = Literal["m", "m2", "deg"]
Tier = Literal["photo", "video", "lidar"]
OpeningType = Literal["door", "window", "pass_through"]
SurfaceType = Literal["wall", "floor", "ceiling"]

Point = tuple[float, float]
Polygon = list[Point]


class DamageClass(str, Enum):
    """The single place damage classes are defined. Extend here only."""

    water_stain = "water_stain"
    mould = "mould"
    crack = "crack"
    hole_puncture = "hole_puncture"
    burn_char = "burn_char"
    missing_material = "missing_material"
    peeling_paint = "peeling_paint"


class _Strict(BaseModel):
    """Shared config: forbid unknown keys, reject NaN and inf everywhere."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Measurement(_Strict):
    """A value with a calibrated confidence interval.

    ``ci_low <= value <= ci_high`` is enforced so an interval can never exclude
    its own point estimate. ``ci_level`` is the nominal coverage of the
    interval; the evaluation harness compares it to empirical coverage.
    """

    value: float
    ci_low: float
    ci_high: float
    unit: Unit
    method: str = Field(description="How the value was obtained, e.g. scale_from_door_prior")
    ci_level: float = Field(default=0.95, gt=0.0, lt=1.0)

    @model_validator(mode="after")
    def _interval_brackets_value(self) -> "Measurement":
        if not (self.ci_low <= self.value <= self.ci_high):
            raise ValueError(
                f"interval [{self.ci_low}, {self.ci_high}] must bracket value {self.value}"
            )
        return self

    @property
    def width(self) -> float:
        return self.ci_high - self.ci_low

    def contains(self, truth: float) -> bool:
        """True when a ground-truth value lies inside the stated interval (inclusive)."""
        return self.ci_low <= truth <= self.ci_high


def signed_area(polygon: Polygon) -> float:
    """Shoelace signed area. Positive means counter-clockwise."""
    n = len(polygon)
    total = 0.0
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return total / 2.0


def _require_ccw(polygon: Polygon, what: str) -> Polygon:
    """Room polygons are CCW by contract so wall order and normals are unambiguous."""
    if len(polygon) < 3:
        raise ValueError(f"{what} needs at least 3 vertices, got {len(polygon)}")
    if signed_area(polygon) <= 0.0:
        raise ValueError(f"{what} must be CCW with non-zero area (signed area was <= 0)")
    return polygon


def _unique(ids: list[str], what: str) -> None:
    seen: set[str] = set()
    for i in ids:
        if i in seen:
            raise ValueError(f"duplicate {what} id: {i}")
        seen.add(i)


class Capture(_Strict):
    id: str
    tier: Tier
    device: str | None = None
    captured_at: datetime | None = None
    input_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class RunInfo(_Strict):
    """Deterministic provenance only.

    Wall-clock fields (started_at, duration_s, stage_timings_s) live in
    run_manifest.json, not here, so that plan.json is byte-identical across
    runs with the same input, config and seed. Provenance that is stable
    across such runs stays in the plan.
    """

    pipeline_version: str
    git_commit: str | None = Field(default=None, pattern=r"^[0-9a-f]{7,40}$")
    config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    seed: int


class Wall(_Strict):
    id: str
    start: Point
    end: Point
    length_m: Measurement
    height_m: Measurement


class Opening(_Strict):
    id: str
    type: OpeningType
    wall_id: str
    offset_along_wall_m: Measurement
    width_m: Measurement
    height_m: Measurement
    sill_height_m: Measurement | None = None
    detection_confidence: float = Field(ge=0.0, le=1.0)


class Room(_Strict):
    id: str
    label: str
    polygon: Polygon = Field(description="Metres, room-local frame, counter-clockwise")
    walls: list[Wall]
    ceiling_height_m: Measurement
    floor_area_m2: Measurement
    openings: list[Opening] = Field(default_factory=list)

    @field_validator("polygon")
    @classmethod
    def _polygon_ccw(cls, v: Polygon) -> Polygon:
        return _require_ccw(v, "room polygon")

    @model_validator(mode="after")
    def _references(self) -> "Room":
        _unique([w.id for w in self.walls], "wall")
        _unique([o.id for o in self.openings], "opening")
        wall_ids = {w.id for w in self.walls}
        for o in self.openings:
            if o.wall_id not in wall_ids:
                raise ValueError(
                    f"opening {o.id} has wall_id {o.wall_id!r} not in room {self.id}"
                )
        return self

    def polygon_area(self) -> float:
        return signed_area(self.polygon)


class Adjacency(_Strict):
    room_a: str
    room_b: str
    via_opening_id: str | None = None

    @model_validator(mode="after")
    def _distinct(self) -> "Adjacency":
        if self.room_a == self.room_b:
            raise ValueError(f"room {self.room_a} cannot be adjacent to itself")
        return self


class Placement(_Strict):
    """Rigid transform placing a room-local polygon into the stitched frame.

    ``theta_deg`` is a Measurement, not a float, because it is a dimension and
    stitching rotation error propagates into footprint error.
    """

    room_id: str
    tx: float
    ty: float
    theta_deg: Measurement


class StitchedPlan(_Strict):
    placements: list[Placement]
    footprint_polygon: Polygon
    footprint_area_m2: Measurement
    overlap_area_m2: Measurement

    @field_validator("footprint_polygon")
    @classmethod
    def _footprint_ccw(cls, v: Polygon) -> Polygon:
        return _require_ccw(v, "footprint polygon")


class Surface(_Strict):
    id: str
    room_id: str
    type: SurfaceType
    wall_id: str | None = None
    area_m2: Measurement

    @model_validator(mode="after")
    def _wall_id_matches_type(self) -> "Surface":
        if self.type == "wall" and self.wall_id is None:
            raise ValueError(f"wall surface {self.id} requires wall_id")
        if self.type != "wall" and self.wall_id is not None:
            raise ValueError(f"{self.type} surface {self.id} must not carry wall_id")
        return self


class DamageRegion(_Strict):
    id: str
    surface_id: str
    damage_class: DamageClass
    extent_m2: Measurement
    polygon: Polygon = Field(description="Surface-local metres")
    confidence: float = Field(ge=0.0, le=1.0)


class ConcealedDamageFlag(_Strict):
    id: str
    surface_id: str
    rule_id: str
    rule_text: str
    evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class ScopeItem(_Strict):
    id: str
    surface_id: str
    damage_region_ids: list[str] = Field(default_factory=list)
    description: str
    quantity: Measurement
    basis: str


class Renders(_Strict):
    plan_png: str | None = None
    plan_svg: str | None = None


class Plan(_Strict):
    schema_version: str = SCHEMA_VERSION
    capture: Capture
    run: RunInfo
    rooms: list[Room]
    adjacency: list[Adjacency] = Field(default_factory=list)
    stitched_plan: StitchedPlan
    surfaces: list[Surface] = Field(default_factory=list)
    damage_regions: list[DamageRegion] = Field(default_factory=list)
    concealed_damage_flags: list[ConcealedDamageFlag] = Field(default_factory=list)
    scope_items: list[ScopeItem] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    renders: Renders = Field(default_factory=Renders)

    @field_validator("schema_version")
    @classmethod
    def _version_matches(cls, v: str) -> str:
        # Loud failure beats silently reading a plan written under another contract.
        if v != SCHEMA_VERSION:
            raise ValueError(f"schema_version {v!r} != supported {SCHEMA_VERSION!r}")
        return v

    @model_validator(mode="after")
    def _cross_references(self) -> "Plan":
        _unique([r.id for r in self.rooms], "room")
        room_ids = {r.id for r in self.rooms}
        _unique([o.id for r in self.rooms for o in r.openings], "opening")
        opening_ids = {o.id for r in self.rooms for o in r.openings}
        walls_by_room = {r.id: {w.id for w in r.walls} for r in self.rooms}

        for a in self.adjacency:
            for rid in (a.room_a, a.room_b):
                if rid not in room_ids:
                    raise ValueError(f"adjacency references unknown room {rid!r}")
            if a.via_opening_id is not None and a.via_opening_id not in opening_ids:
                raise ValueError(f"adjacency references unknown opening {a.via_opening_id!r}")

        placed = [p.room_id for p in self.stitched_plan.placements]
        _unique(placed, "placement room")
        missing = room_ids - set(placed)
        extra = set(placed) - room_ids
        if missing or extra:
            raise ValueError(
                f"every room needs exactly one placement; missing={sorted(missing)} unknown={sorted(extra)}"
            )

        _unique([s.id for s in self.surfaces], "surface")
        surface_ids = {s.id for s in self.surfaces}
        for s in self.surfaces:
            if s.room_id not in room_ids:
                raise ValueError(f"surface {s.id} references unknown room {s.room_id!r}")
            if s.wall_id is not None and s.wall_id not in walls_by_room[s.room_id]:
                raise ValueError(f"surface {s.id} references unknown wall {s.wall_id!r}")

        _unique([d.id for d in self.damage_regions], "damage region")
        damage_ids = {d.id for d in self.damage_regions}
        for d in self.damage_regions:
            if d.surface_id not in surface_ids:
                raise ValueError(f"damage region {d.id} references unknown surface {d.surface_id!r}")

        _unique([c.id for c in self.concealed_damage_flags], "concealed damage flag")
        for c in self.concealed_damage_flags:
            if c.surface_id not in surface_ids:
                raise ValueError(f"concealed flag {c.id} references unknown surface {c.surface_id!r}")

        _unique([s.id for s in self.scope_items], "scope item")
        for s in self.scope_items:
            if s.surface_id not in surface_ids:
                raise ValueError(f"scope item {s.id} references unknown surface {s.surface_id!r}")
            for did in s.damage_region_ids:
                if did not in damage_ids:
                    raise ValueError(f"scope item {s.id} references unknown damage region {did!r}")
        return self

    def to_json_bytes(self) -> bytes:
        """Canonical serialisation: fixed indent, field order, UTF-8, trailing newline.

        Byte-identical output for identical content is a stated requirement, so
        there is exactly one way to write a plan.
        """
        payload = self.model_dump(mode="json")
        return (json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")

    @classmethod
    def from_json_bytes(cls, data: bytes) -> "Plan":
        return cls.model_validate_json(data)
