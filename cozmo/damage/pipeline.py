"""Run the detector over frames, merge repeats, attach surfaces, emit contract objects.

Surface attachment is the step that turns a box in an image into a claim about
the building. With a pose and depth the detection's centre is unprojected and
assigned to the nearest surface; without them the caller supplies a room and
the region is attached to that room's largest wall, and the plan says so.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Iterable, Iterator

import numpy as np
from shapely.geometry import Polygon as SPoly

from cozmo.contracts.models import (
    ConcealedDamageFlag,
    DamageClass,
    DamageRegion,
    Measurement,
    Plan,
    ScopeItem,
    Surface,
)
from cozmo.damage.detector import Detection, Detector
from cozmo.damage.extent import UNBOUNDED_METHOD, estimate_extent
from cozmo.damage.frames import DamageFrame
from cozmo.damage.rules import RULES, scope_for

log = logging.getLogger(__name__)

UNBOUNDED_WARNING = (
    "Damage regions were detected without metric depth, so their extent is unbounded: "
    "extent_m2 carries a nominal value with an interval spanning the plausible range and "
    "method {method}. Do not read these as measured areas"
)


@dataclass
class MergedRegion:
    damage_class: str
    detections: list[Detection] = field(default_factory=list)
    world_points: list[np.ndarray] = field(default_factory=list)
    extents: list[float] = field(default_factory=list)
    upper_bounds: list[float] = field(default_factory=list)
    surface_id: str | None = None
    height_above_floor_m: float | None = None
    bounded: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def confidence(self) -> float:
        """Best single detection, nudged up when several frames agree.

        Seeing the same mark from three angles is stronger evidence than one
        lucky box, but agreement between frames of one model is not
        independent evidence, so the bonus is small and capped.
        """
        best = max(d.confidence for d in self.detections)
        bonus = min(0.10, 0.03 * (len({d.frame_id for d in self.detections}) - 1))
        return float(min(best + bonus, 0.99))

    @property
    def world_centre(self) -> np.ndarray | None:
        return np.mean(self.world_points, axis=0) if self.world_points else None


def _merge(regions: list[MergedRegion], det: Detection, world: np.ndarray | None,
           merge_radius_m: float) -> MergedRegion:
    """Attach a detection to an existing region when it is the same mark seen again."""
    for r in regions:
        if r.damage_class != det.damage_class:
            continue
        if world is not None and r.world_points:
            if float(np.linalg.norm(r.world_centre - world)) <= merge_radius_m:
                return r
        elif world is None and not r.world_points:
            # Without geometry, the same class in the same frame is one region;
            # across frames nothing can be said, so they stay separate.
            if any(d.frame_id == det.frame_id for d in r.detections):
                iou = _box_iou(r.detections[-1].box, det.box)
                if iou > 0.3:
                    return r
    r = MergedRegion(damage_class=det.damage_class)
    regions.append(r)
    return r


def _box_iou(a, b) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    union = (ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - inter
    return inter / union if union > 0 else 0.0


def _surface_for_point(plan: Plan, point: np.ndarray, floor_y: float | None) -> tuple[str | None, float | None]:
    """Nearest wall surface to a world point, and the point's height above the floor."""
    best_id, best_d = None, 1e9
    for room in plan.rooms:
        poly = np.asarray(room.polygon)
        n = len(poly)
        for i in range(n):
            a, b = poly[i], poly[(i + 1) % n]
            seg = b - a
            L = float(np.linalg.norm(seg))
            if L < 1e-6:
                continue
            t = float(np.clip(np.dot(point[[0, 2]] - a, seg) / (L * L), 0.0, 1.0))
            closest = a + t * seg
            d = float(np.linalg.norm(point[[0, 2]] - closest))
            if d < best_d:
                best_d = d
                wall = room.walls[i] if i < len(room.walls) else None
                best_id = f"s_{room.id}_{wall.id}" if wall else None
    known = {s.id for s in plan.surfaces}
    if best_id not in known:
        best_id = None
    height = float(point[1] - floor_y) if floor_y is not None else None
    return best_id, height


@dataclass
class DamageResult:
    regions: list[DamageRegion] = field(default_factory=list)
    flags: list[ConcealedDamageFlag] = field(default_factory=list)
    scope_items: list[ScopeItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    detections: int = 0
    merged: int = 0
    per_class: dict[str, int] = field(default_factory=dict)


def analyse_damage(frames: Iterable[DamageFrame], plan: Plan, detector: Detector, cfg: dict,
                   floor_y: float | None = None, merge_radius_m: float = 0.35,
                   min_confidence: float = 0.15, fallback_surface_id: str | None = None) -> DamageResult:
    regions: list[MergedRegion] = []
    n_det = 0
    any_depth = False
    for frame in frames:
        dets = [d for d in detector.detect(frame.image, frame.frame_id) if d.confidence >= min_confidence]
        n_det += len(dets)
        any_depth = any_depth or frame.has_metric_depth
        for det in dets:
            world = frame.unproject(*det.centre) if frame.has_metric_depth and frame.pose is not None else None
            region = _merge(regions, det, world, merge_radius_m)
            region.detections.append(det)
            if world is not None:
                region.world_points.append(world)
            ext = estimate_extent(frame, det, cfg)
            if ext.bounded:
                region.bounded = True
                region.upper_bounds.append(ext.upper_bound_m2)
                region.extents.append(ext.estimate_m2)
                if ext.note:
                    region.notes.append(ext.note)
            elif ext.note:
                region.notes.append(ext.note)

    result = DamageResult(detections=n_det, merged=len(regions))
    surface_types = {s.id: s.type for s in plan.surfaces}
    unc = cfg.get("uncertainty", {})
    ci_level = unc.get("ci_level", 0.95)

    for i, region in enumerate(regions, start=1):
        centre = region.world_centre
        surface_id, height = (None, None)
        if centre is not None:
            surface_id, height = _surface_for_point(plan, centre, floor_y)
        if surface_id is None:
            surface_id = fallback_surface_id or (plan.surfaces[0].id if plan.surfaces else None)
        if surface_id is None:
            result.warnings.append("No surfaces in the plan, so damage regions cannot be attached")
            break
        region.surface_id = surface_id
        region.height_above_floor_m = height

        if region.bounded and region.upper_bounds:
            lo = float(np.median(region.extents))
            hi = float(np.median(region.upper_bounds))
            value = (lo + hi) / 2
            extent = Measurement(value=value, ci_low=min(lo, value), ci_high=max(hi, value), unit="m2",
                                 method="box_on_surface_upper_bound_with_contrast_mask", ci_level=ci_level)
        else:
            # No scale at all. A nominal value with a deliberately enormous
            # interval, and a method name that says so.
            extent = Measurement(value=0.25, ci_low=0.0, ci_high=4.0, unit="m2",
                                 method=UNBOUNDED_METHOD, ci_level=ci_level)

        rid = f"d{i}"
        box = region.detections[0].box
        result.regions.append(DamageRegion(
            id=rid, surface_id=surface_id, damage_class=DamageClass(region.damage_class),
            extent_m2=extent,
            polygon=[(float(box[0]), float(box[1])), (float(box[2]), float(box[1])),
                     (float(box[2]), float(box[3])), (float(box[0]), float(box[3]))],
            confidence=region.confidence))
        result.per_class[region.damage_class] = result.per_class.get(region.damage_class, 0) + 1

        fact = {"damage_class": region.damage_class,
                "surface_type": surface_types.get(surface_id, "wall"),
                "height_above_floor_m": region.height_above_floor_m}
        for rule in RULES:
            try:
                fires = rule.applies(fact)
            except Exception:
                fires = False
            if not fires:
                continue
            result.flags.append(ConcealedDamageFlag(
                id=f"c{len(result.flags) + 1}", surface_id=surface_id, rule_id=rule.id,
                rule_text=rule.text, evidence=[rid], confidence=rule.confidence))

        srule = scope_for(region.damage_class, surface_types.get(surface_id, "wall"))
        if srule is not None:
            q_low = max(extent.ci_low * srule.quantity_factor, srule.minimum_m2)
            q_high = max(extent.ci_high * srule.quantity_factor, srule.minimum_m2)
            q_val = min(max(extent.value * srule.quantity_factor, srule.minimum_m2), q_high)
            result.scope_items.append(ScopeItem(
                id=f"sc{len(result.scope_items) + 1}", surface_id=surface_id, damage_region_ids=[rid],
                description=srule.description,
                quantity=Measurement(value=q_val, ci_low=min(q_low, q_val), ci_high=max(q_high, q_val),
                                     unit="m2", method=f"scope_table_x{srule.quantity_factor}", ci_level=ci_level),
                basis=srule.basis))

    if regions and not any_depth:
        result.warnings.append(UNBOUNDED_WARNING.format(method=UNBOUNDED_METHOD))
    return result
