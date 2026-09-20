"""LiDAR-tier pipeline: a Stray Scanner scan to a dimensioned, stitched plan.

Classical geometry only. The stages live in :mod:`cozmo.lidar`; this module
runs them in order, turns the result into the output contract, and records
what was assumed and what could not be measured.

All rooms are reconstructed in one world frame, so stitching placements are
the identity apart from the Manhattan rotation that is already baked into the
room polygons. They are still populated, because the contract and the
evaluation harness expect one placement per room.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
from shapely.geometry import Polygon as SPoly
from shapely.ops import unary_union

from cozmo.contracts.models import (
    Adjacency,
    Measurement,
    Opening,
    Placement,
    Plan,
    Renders,
    Room,
    StitchedPlan,
    Surface,
    Tier,
    Wall,
)
from cozmo.io.stray import StrayScan
from cozmo.lidar.cloud import build_cloud
from cozmo.lidar.debug import write_debug_images
from cozmo.lidar.drift import DriftModel, estimate_drift
from cozmo.lidar.levels import detect_levels, measure_ceiling_height
from cozmo.lidar.openings import WINDOWS_NOT_ATTEMPTED, adjacency_from_openings, find_openings
from cozmo.lidar.rooms import segment_rooms
from cozmo.lidar.uncertainty import area_measurement, face_position_sigma, length_measurement
from cozmo.lidar.walls import ManhattanFrame, extract_faces, wall_points
from cozmo.pipeline.base import Pipeline

log = logging.getLogger(__name__)

MANHATTAN_ASSUMPTION = (
    "Manhattan assumption: walls meet at right angles and are axis aligned after a single "
    "global rotation. A curved or 45 degree wall appears as a missing face, not a wrong one"
)


def _geometry(scan: StrayScan, cfg: dict, pipeline: "LidarPipeline", drift: DriftModel | None,
              want_chunks: bool):
    """Cloud, levels, Manhattan frame, faces, rooms for one pose setting."""
    cloud = build_cloud(
        scan,
        stride=cfg["frame_stride"],
        voxel_m=cfg["voxel_m"],
        min_depth=cfg["min_depth_m"],
        max_depth=cfg["max_depth_m"],
        pose_fn=drift.pose_fn if drift is not None else None,
        chunk_s=cfg["drift"]["chunk_s"] if want_chunks else None,
    )
    levels = detect_levels(cloud, cfg)
    sel = wall_points(cloud, levels, cfg)
    if sel.sum() < 500:
        raise ValueError("too few wall points to reconstruct a plan")
    frame = ManhattanFrame.fit(cloud.normals[sel], cloud.points[sel][:, [0, 2]])
    height = cloud.points[sel][:, 1] - levels.floor.height_at(cloud.points[sel][:, [0, 2]])
    faces = extract_faces(frame.to_frame(cloud.points[sel][:, [0, 2]]),
                          frame.rotate_normals(cloud.normals[sel]), height, cfg)
    rooms = segment_rooms(cloud, levels, frame, faces, cfg)
    return cloud, levels, frame, faces, rooms


def _mean_wall_thickness(cloud, levels, frame, faces, cfg) -> float:
    """Mean point spread about each wall face: the direct read-out of pose drift.

    A perfectly registered scan puts every point of one wall on one plane, so
    drift shows up as a thicker face. The spread is measured over a wide 8 cm
    band, not the narrow band the face was fitted in, because a narrow band
    cannot show a smear larger than itself.
    """
    sel = wall_points(cloud, levels, cfg)
    if not sel.any():
        return 0.0
    xz = frame.to_frame(cloud.points[sel][:, [0, 2]])
    nrm = frame.rotate_normals(cloud.normals[sel])
    vals = []
    for f in faces:
        if not f.is_structural(cfg["wall"]["wall_min_top_m"]):
            continue
        a_lo, a_hi = f.extent()
        belongs = (np.abs(nrm[:, 0]) >= np.abs(nrm[:, 2])) if f.axis == 0 else (np.abs(nrm[:, 2]) > np.abs(nrm[:, 0]))
        near = belongs & (np.abs(xz[:, f.axis] - f.pos) <= 0.08) & \
               (xz[:, 1 - f.axis] >= a_lo) & (xz[:, 1 - f.axis] <= a_hi)
        if near.sum() >= 200:
            vals.append(float(np.std(xz[near, f.axis])))
    return float(np.mean(vals)) if vals else 0.0


def _closed_union(polys, bridge: float = 0.25):
    """Union of room polygons, closed across wall thickness so the property is one outline."""
    merged = unary_union(polys)
    closed = merged.buffer(bridge, join_style=2).buffer(-bridge, join_style=2)
    return closed if not closed.is_empty else merged


def _footprint(rooms) -> tuple[list[tuple[float, float]], float, float]:
    polys = [SPoly(r.polygon_world) for r in rooms if len(r.polygon_world) >= 4]
    polys = [p for p in polys if p.is_valid and p.area > 0]
    if not polys:
        return [], 0.0, 0.0
    overlap = 0.0
    for i in range(len(polys)):
        for j in range(i + 1, len(polys)):
            overlap += polys[i].intersection(polys[j]).area
    closed = _closed_union(polys)
    area = float(closed.area)
    outline = max(closed.geoms, key=lambda g: g.area) if closed.geom_type == "MultiPolygon" else closed
    ring = [(float(x), float(y)) for x, y in outline.exterior.coords[:-1]]
    if not SPoly(ring).exterior.is_ccw:
        ring = ring[::-1]
    return ring, area, float(overlap)


class LidarPipeline(Pipeline):
    name = "lidar"
    version = "0.1.0"

    def __init__(self) -> None:
        super().__init__()
        self.cfg: dict[str, Any] = {}
        self.debug_dir: Path | None = None
        self.drift_report: dict[str, Any] | None = None
        self.debug_images: list[str] = []

    def run(self, input_path: Path, tier: Tier, config: dict[str, Any], seed: int) -> Plan:
        if tier != "lidar":
            raise ValueError(f"LidarPipeline only handles the lidar tier, got {tier!r}")
        cfg = config["pipeline"]["lidar"]
        self.cfg = cfg
        drift_on = bool(config.get("run", {}).get("drift_correction", True))
        scan = StrayScan(Path(input_path), "lidar")
        warnings: list[str] = []
        assumptions: list[str] = [MANHATTAN_ASSUMPTION]

        with self.stage("fuse_raw"):
            raw = _geometry(scan, cfg, self, None, want_chunks=True)
        cloud, levels, frame, faces, rooms = raw

        with self.stage("drift_estimate"):
            model = estimate_drift(cloud, levels, frame, faces, cfg)
            model.enabled = drift_on

        if drift_on:
            with self.stage("fuse_corrected"):
                corrected = _geometry(scan, cfg, self, model, want_chunks=False)
            cloud, levels, frame, faces, rooms = corrected
        else:
            corrected = raw
            warnings.append("Drift correction was disabled with --drift-correction off; poses are used as given")

        with self.stage("openings"):
            openings = find_openings(cloud, levels, frame, faces, rooms, cfg)
            adjacency = adjacency_from_openings(openings)
        warnings.append(WINDOWS_NOT_ATTEMPTED)

        with self.stage("drift_report"):
            self.drift_report = self._build_drift_report(raw, corrected, model, drift_on)

        with self.stage("assemble"):
            plan = self._assemble(scan, tier, config, seed, cloud, levels, frame, faces, rooms,
                                  openings, adjacency, cfg, warnings, assumptions, model)

        if self.debug_dir is not None:
            with self.stage("debug_images"):
                self.debug_images = write_debug_images(self.debug_dir, cloud, levels, frame, faces,
                                                       rooms, openings, cfg)
        return plan

    def _build_drift_report(self, raw, corrected, model: DriftModel, drift_on: bool) -> dict[str, Any]:
        """Footprint area and wall thickness with and without correction, plus the model summary."""
        out = {}
        for name, geom in (("drift_off", raw), ("drift_on", corrected)):
            cloud, levels, frame, faces, rooms = geom
            ring, area, overlap = _footprint(rooms.rooms)
            out[name] = {
                "footprint_area_m2": area,
                "mean_wall_thickness_m": _mean_wall_thickness(cloud, levels, frame, faces, self.cfg),
                "n_rooms": len(rooms.rooms),
                "n_wall_faces": len(faces),
                "room_overlap_m2": overlap,
            }
        if drift_on:
            off, on = out["drift_off"], out["drift_on"]
            out["delta"] = {
                "footprint_area_m2": on["footprint_area_m2"] - off["footprint_area_m2"],
                "mean_wall_thickness_m": on["mean_wall_thickness_m"] - off["mean_wall_thickness_m"],
            }
        else:
            out["note"] = "drift correction disabled; drift_on mirrors drift_off"
        out["applied"] = drift_on
        out["model"] = model.summary()
        return out

    def _assemble(self, scan, tier, config, seed, cloud, levels, frame, faces, rooms, openings,
                  adjacency, cfg, warnings, assumptions, model) -> Plan:
        capture, run = self.provenance(Path(scan.root), tier, config, seed)
        warnings = list(warnings) + list(levels.warnings) + list(rooms.warnings)
        assumptions = list(assumptions) + list(levels.assumptions)

        face_by_axis = {a: [f for f in faces if f.axis == a] for a in (0, 1)}
        sigma_cache = {id(f): face_position_sigma(f, cfg) for f in faces}
        default_sigma = float(np.median(list(sigma_cache.values()))) if sigma_cache else 0.01

        def nearest_face(axis: int, pos: float):
            cands = face_by_axis.get(axis, [])
            if not cands:
                return None
            f = min(cands, key=lambda f: abs(f.pos - pos))
            return f if abs(f.pos - pos) <= cfg["room"]["snap_m"] else None

        out_rooms: list[Room] = []
        surfaces: list[Surface] = []
        contract_openings: dict[str, list[Opening]] = {}
        # A doorway is shared by two rooms but belongs to a different wall in
        # each, and contract opening ids are globally unique, so each side gets
        # its own entity. Adjacency points at the first side reported.
        opening_ids: dict[tuple[str, int], str] = {}

        for room in rooms.rooms:
            poly = np.array(room.polygon_frame)
            n = len(poly)
            walls: list[Wall] = []
            edge_ms: list[Measurement] = []
            for i in range(n):
                a, b = poly[i], poly[(i + 1) % n]
                length = float(np.linalg.norm(b - a))
                if length < 1e-6:
                    continue
                # A horizontal edge (constant z) has its length set by the two
                # x faces at its ends, and vice versa.
                const_axis = 1 if abs(b[1] - a[1]) < abs(b[0] - a[0]) else 0
                end_axis = 1 - const_axis
                fa = nearest_face(end_axis, float(a[end_axis]))
                fb = nearest_face(end_axis, float(b[end_axis]))
                sa = sigma_cache.get(id(fa), default_sigma) if fa else default_sigma
                sb = sigma_cache.get(id(fb), default_sigma) if fb else default_sigma
                m = length_measurement(length, sa, sb, cfg)
                edge_ms.append(m)
                wid = f"w{len(walls) + 1}"
                walls.append(Wall(id=wid, start=tuple(frame.to_world(a[None, :])[0]),
                                  end=tuple(frame.to_world(b[None, :])[0]),
                                  length_m=m, height_m=levels.height))
            if len(walls) < 3:
                warnings.append(f"{room.id}: fewer than three usable walls; room dropped")
                continue

            inside = np.zeros(len(cloud.points), dtype=bool)
            ij = rooms.grid.to_cell(frame.to_frame(cloud.points[:, [0, 2]]))
            ok = rooms.grid.inside(ij)
            inside[ok] = room.mask[ij[ok, 0], ij[ok, 1]]
            ceiling_m, coverage, _, ch_warn, ch_assume = measure_ceiling_height(
                cloud, levels.floor, levels.ceiling, cfg, inside)
            for w in ch_warn:
                warnings.append(f"{room.id}: {w}")
            for a in ch_assume:
                if a not in assumptions:
                    assumptions.append(a)
            for w in walls:
                w.height_m = ceiling_m

            area = area_measurement(room.area_m2, edge_ms, cfg)
            room_openings: list[Opening] = []
            for oi, o in enumerate(openings):
                if room.id not in o.room_ids:
                    continue
                wall = self._wall_for_opening(walls, frame, o)
                if wall is None:
                    continue
                oid = opening_ids.setdefault((room.id, id(o)), f"{room.id}_o{len(room_openings) + 1}")
                unc = cfg["uncertainty"]
                half_w = max(1.96 * np.hypot(cfg["opening"]["bin_m"] / 2, unc["depth_scale_bias"] * o.width_m),
                             unc["abs_floor_m"])
                width_m = Measurement(value=o.width_m, ci_low=o.width_m - half_w, ci_high=o.width_m + half_w,
                                      unit="m", method="wall_occupancy_gap", ci_level=unc["ci_level"])
                if o.height_m is not None:
                    hh = max(1.96 * 0.03, unc["abs_floor_m"])
                    height_m = Measurement(value=o.height_m, ci_low=o.height_m - hh, ci_high=o.height_m + hh,
                                           unit="m", method="lintel_points", ci_level=unc["ci_level"])
                else:
                    height_m = Measurement(value=2.05, ci_low=1.9, ci_high=2.3, unit="m",
                                           method="prior_no_lintel_observed", ci_level=unc["ci_level"])
                    warnings.append(f"{oid}: no lintel observed above the opening; height is a prior")
                offset = self._offset_along(wall, frame, o)
                room_openings.append(Opening(
                    id=oid, type=o.type, wall_id=wall.id,
                    offset_along_wall_m=Measurement(value=offset, ci_low=offset - half_w, ci_high=offset + half_w,
                                                    unit="m", method="wall_occupancy_gap", ci_level=unc["ci_level"]),
                    width_m=width_m, height_m=height_m, sill_height_m=None,
                    detection_confidence=0.6 if o.height_m is not None else 0.4,
                ))
            contract_openings[room.id] = room_openings

            out_rooms.append(Room(
                id=room.id, label=room.label,
                polygon=[tuple(p) for p in frame.to_world(poly)] if SPoly(frame.to_world(poly)).exterior.is_ccw
                else [tuple(p) for p in frame.to_world(poly)][::-1],
                walls=walls, ceiling_height_m=ceiling_m, floor_area_m2=area, openings=room_openings,
            ))
            for w in walls:
                wall_area = w.length_m.value * ceiling_m.value
                surfaces.append(Surface(id=f"s_{room.id}_{w.id}", room_id=room.id, type="wall", wall_id=w.id,
                                        area_m2=area_measurement(wall_area, [w.length_m, ceiling_m], cfg,
                                                                 method="wall_length_times_height")))
            surfaces.append(Surface(id=f"s_{room.id}_floor", room_id=room.id, type="floor", area_m2=area))
            surfaces.append(Surface(id=f"s_{room.id}_ceiling", room_id=room.id, type="ceiling", area_m2=area))

        if not out_rooms:
            raise ValueError("no rooms reconstructed from this scan")

        known = {r.id for r in out_rooms}
        known_openings = {o.id for r in out_rooms for o in r.openings}
        adj = []
        seen: set[tuple[str, str]] = set()
        for a, b, _ in adjacency:
            if a not in known or b not in known or a == b:
                continue
            key = tuple(sorted((a, b)))
            if key in seen:
                continue
            seen.add(key)
            via = None
            for o in openings:
                if set(o.room_ids) != set(key):
                    continue
                for side in key:
                    cand = opening_ids.get((side, id(o)))
                    if cand in known_openings:
                        via = cand
                        break
                if via:
                    break
            adj.append(Adjacency(room_a=key[0], room_b=key[1], via_opening_id=via))

        unc = cfg["uncertainty"]
        ring, fp_area, overlap = _footprint([r for r in rooms.rooms if r.id in known])
        if len(ring) < 3:
            raise ValueError("stitched footprint has no valid outline")
        fp_edges = [m for r in out_rooms for m in [w.length_m for w in r.walls]]
        placements = [Placement(room_id=r.id, tx=0.0, ty=0.0,
                                theta_deg=Measurement(value=0.0, ci_low=-1.0, ci_high=1.0, unit="deg",
                                                      method="single_world_frame", ci_level=unc["ci_level"]))
                      for r in out_rooms]
        stitched = StitchedPlan(
            placements=placements,
            footprint_polygon=ring,
            footprint_area_m2=area_measurement(fp_area, fp_edges, cfg, method="union_of_room_polygons"),
            overlap_area_m2=Measurement(value=overlap, ci_low=max(0.0, overlap - 0.05), ci_high=overlap + 0.05,
                                        unit="m2", method="pairwise_polygon_intersection", ci_level=unc["ci_level"]),
        )
        assumptions.append(
            "All rooms are reconstructed in one world frame, so stitching placements are the identity")
        if model.summary().get("rejected"):
            warnings.append(f"Drift correction rejected some chunk estimates: {model.summary()['rejected']}")

        return Plan(
            capture=capture, run=run, rooms=out_rooms, adjacency=adj, stitched_plan=stitched,
            surfaces=surfaces, damage_regions=[], concealed_damage_flags=[], scope_items=[],
            assumptions=assumptions,
            warnings=warnings + ["Damage detection is not implemented; damage_regions, concealed_damage_flags and scope_items are empty"],
            renders=Renders(),
        )

    @staticmethod
    def _wall_for_opening(walls: list[Wall], frame: ManhattanFrame, opening) -> Wall | None:
        """The room wall whose line the opening sits on."""
        best, best_d = None, 1e9
        for w in walls:
            a = frame.to_frame(np.array([w.start]))[0]
            b = frame.to_frame(np.array([w.end]))[0]
            const_axis = 0 if abs(b[0] - a[0]) < abs(b[1] - a[1]) else 1
            if const_axis != opening.face.axis:
                continue
            d = abs((a[const_axis] + b[const_axis]) / 2 - opening.face.pos)
            lo, hi = sorted((a[1 - const_axis], b[1 - const_axis]))
            if not (lo - 0.2 <= opening.centre_along <= hi + 0.2):
                continue
            if d < best_d:
                best, best_d = w, d
        return best if best_d <= 0.35 else None

    @staticmethod
    def _offset_along(wall: Wall, frame: ManhattanFrame, opening) -> float:
        a = frame.to_frame(np.array([wall.start]))[0]
        b = frame.to_frame(np.array([wall.end]))[0]
        along_axis = 1 - opening.face.axis
        start = a[along_axis]
        direction = 1.0 if b[along_axis] >= start else -1.0
        return float(max(0.0, (opening.a0 - start) * direction))

    def write_drift_report(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.drift_report or {}, indent=2) + "\n", encoding="utf-8")
        return path
