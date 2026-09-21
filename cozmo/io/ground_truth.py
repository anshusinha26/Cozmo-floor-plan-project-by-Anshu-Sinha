"""Ground-truth YAML and the benchmark capture registry.

Ground truth carries bare floats on purpose: it is the tape or laser reading,
not a pipeline estimate, so it has no interval. Wall lists are clockwise
starting from the wall holding the main door; the matcher tries both
directions so a CCW prediction still lines up.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from cozmo.contracts.models import DamageClass, OpeningType, Tier


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class GTWall(_Strict):
    id: str
    length_m: float = Field(gt=0)


class GTOpening(_Strict):
    """A measured opening, or a marker that one exists but was not measured.

    ``present_unmeasured`` marks an opening known to be there with no tape
    reading. A prediction matching it is neither a hit nor a phantom: scoring
    it either way would be inventing a result. Such an entry carries no
    dimensions.
    """

    id: str
    type: OpeningType
    wall_id: str
    present_unmeasured: bool = False
    offset_along_wall_m: float | None = Field(default=None, ge=0,
                                              description="From the wall start to the opening's leading edge")
    width_m: float | None = Field(default=None, gt=0)
    height_m: float | None = Field(default=None, gt=0)
    sill_height_m: float | None = None

    @model_validator(mode="after")
    def _measured_or_marked(self) -> "GTOpening":
        measured = self.width_m is not None and self.height_m is not None and self.offset_along_wall_m is not None
        if self.present_unmeasured and measured:
            raise ValueError(f"opening {self.id}: present_unmeasured entries carry no dimensions")
        if not self.present_unmeasured and not measured:
            raise ValueError(
                f"opening {self.id}: needs offset, width and height, or present_unmeasured: true")
        return self


class GTRoom(_Strict):
    id: str
    ceiling_height_m: float = Field(gt=0)
    floor_area_m2: float | None = Field(default=None, gt=0)
    walls: list[GTWall] = Field(default_factory=list,
                                description="Clockwise, starting from the wall with the main door")
    openings: list[GTOpening] = Field(default_factory=list)
    score_walls: bool = Field(default=True,
                              description="False for irregular open-plan spaces with no tape-measurable wall run")
    label: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _refs(self) -> "GTRoom":
        wall_ids = [w.id for w in self.walls]
        if len(set(wall_ids)) != len(wall_ids):
            raise ValueError(f"room {self.id}: duplicate wall ids")
        for o in self.openings:
            if o.wall_id in wall_ids:
                continue
            if not self.score_walls:
                # An open-plan room has no measured wall run, but its doors are
                # still on a named side. The label locates the door for a human;
                # nothing scores against it.
                continue
            raise ValueError(f"room {self.id}: opening {o.id} has wall_id {o.wall_id!r} not in walls")
        return self

    def opening_ids(self) -> list[str]:
        return [o.id for o in self.openings]

    def measured_openings(self) -> list[GTOpening]:
        return [o for o in self.openings if not o.present_unmeasured]

    def unmeasured_openings(self) -> list[GTOpening]:
        return [o for o in self.openings if o.present_unmeasured]


class GTDamage(_Strict):
    """A known damage instance, for scoring the detector.

    ``extent_m2_upper_bound`` is what it says: a staged A4 sheet bounds the
    mark it stands for, it is not the mark's area. A predicted extent at or
    below the bound is consistent; a larger one is not.
    """

    id: str
    wall_id: str | None = None
    room_id: str | None = None
    damage_class: DamageClass
    extent_m2_upper_bound: float | None = Field(default=None, gt=0)
    staged: bool = False
    notes: str | None = None


class GTAdjacency(_Strict):
    room_a: str
    room_b: str
    via_opening_id: str | None = None


class GroundTruth(_Strict):
    capture_id: str
    space_id: str
    tier: Tier
    device: str
    measured_with: str
    measured_on: date
    truth_uncertainty_m: float = Field(
        default=0.0, ge=0.0,
        description="Half width of the tape reading's own uncertainty. Added to a predicted "
                    "interval before the coverage check, because a truth known only to the "
                    "nearest inch cannot decide whether a tight interval covers it.")
    rooms: list[GTRoom]
    adjacency: list[GTAdjacency] = Field(default_factory=list)
    damage: list[GTDamage] = Field(default_factory=list)
    footprint_area_m2: float | None = Field(
        default=None, gt=0, description="If absent, the sum of room floor areas is used"
    )

    @model_validator(mode="after")
    def _refs(self) -> "GroundTruth":
        ids = [r.id for r in self.rooms]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate room ids")
        openings = {o.id for r in self.rooms for o in r.openings}
        for a in self.adjacency:
            for rid in (a.room_a, a.room_b):
                if rid not in ids:
                    raise ValueError(f"adjacency references unknown room {rid!r}")
            if a.via_opening_id is not None and a.via_opening_id not in openings:
                raise ValueError(f"adjacency references unknown opening {a.via_opening_id!r}")
        return self

    def room(self, room_id: str) -> GTRoom:
        for r in self.rooms:
            if r.id == room_id:
                return r
        raise KeyError(room_id)

    def main_door_wall_id(self, room_id: str) -> str:
        """By convention the first listed wall holds the main door."""
        return self.room(room_id).walls[0].id

    def footprint_area(self) -> float | None:
        if self.footprint_area_m2 is not None:
            return self.footprint_area_m2
        areas = [r.floor_area_m2 for r in self.rooms]
        if any(a is None for a in areas):
            return None
        return float(sum(areas))


def load_ground_truth(path: Path) -> GroundTruth:
    with open(path, "r", encoding="utf-8") as fh:
        return GroundTruth.model_validate(yaml.safe_load(fh))


class CaptureEntry(_Strict):
    capture_id: str
    space_id: str
    tier: Tier
    input: str
    ground_truth: str | None = None  # null where no tape measurements exist yet
    device: str | None = None
    repeat_of: str | None = None
    repeat_kind: Literal["same_device_repeat", "cross_device_repeat", "coverage_mismatched"] | None = None
    multi_room: bool = False
    # Video tier only. ffmpeg applies a container rotation tag by itself, so
    # "auto" is right for phone video; Stray Scanner's rgb.mp4 carries no tag.
    video_rotation: Literal["auto", "0", "90", "180", "270"] = "auto"
    # Synthetic harness fixtures pin the stub; real captures leave this null and
    # take the tier's own pipeline.
    pipeline: str | None = None

    @model_validator(mode="after")
    def _repeat_kind_needs_a_repeat(self) -> "CaptureEntry":
        if self.repeat_kind and not self.repeat_of:
            raise ValueError(f"{self.capture_id}: repeat_kind without repeat_of")
        return self


class Registry(_Strict):
    captures: list[CaptureEntry]

    @model_validator(mode="after")
    def _refs(self) -> "Registry":
        ids = [c.capture_id for c in self.captures]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate capture ids in registry")
        for c in self.captures:
            if c.repeat_of is not None and c.repeat_of not in ids:
                raise ValueError(f"{c.capture_id}: repeat_of {c.repeat_of!r} is not in the registry")
        return self

    def by_id(self, capture_id: str) -> CaptureEntry:
        for c in self.captures:
            if c.capture_id == capture_id:
                return c
        raise KeyError(capture_id)


def load_registry(path: Path) -> Registry:
    with open(path, "r", encoding="utf-8") as fh:
        return Registry.model_validate(yaml.safe_load(fh))
