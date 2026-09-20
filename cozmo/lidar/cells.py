"""Wall-driven room segmentation: an axis-aligned cell complex cut by wall support.

The erosion method grew rooms from observed floor and then split them with a
fixed radius, which made the room partition a function of where the operator
walked. Two captures of one flat walk differently, so they partitioned
differently: that was the repeatability failure.

Here the partition comes from the building instead. Wall faces extend into
grid lines, the lines cut the plan into cells, and two neighbouring cells are
separated only where the edge between them carries real wall support. Support
is measured directly from wall points in a height band, not from the face
extents, so a wall that a face missed still separates rooms.

A gap in an otherwise supported edge is a doorway, not a reason to merge, up
to ``max_opening_m``. A wider gap means the two cells are one space.

Rooms whose boundary is partly unsupported and partly unobserved are flagged
``partially_observed`` rather than closed by guesswork; the pipeline widens
their intervals.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage
from shapely.geometry import Polygon as SPoly, box
from shapely.ops import unary_union

from cozmo.lidar.cloud import Cloud
from cozmo.lidar.ghosts import observed_mask
from cozmo.lidar.levels import Levels
from cozmo.lidar.rooms import Grid, Room, RoomResult
from cozmo.lidar.walls import ManhattanFrame, WallFace


@dataclass
class WallSupport:
    """Occupancy of wall points in the support band, per axis, on a coarse grid."""

    cell: float
    band: tuple[float, float]
    grids: dict[int, np.ndarray]
    origins: dict[int, np.ndarray]

    def support_profile(self, axis: int, pos: float, a0: float, a1: float,
                        tol_m: float = 0.12) -> np.ndarray:
        """Boolean occupancy along the edge, one entry per ``cell`` step."""
        grid = self.grids[axis]
        origin = self.origins[axis]
        n = max(int(np.ceil((a1 - a0) / self.cell)), 1)
        along = a0 + (np.arange(n) + 0.5) * self.cell
        j = np.floor((along - origin[1]) / self.cell).astype(np.int64)
        k = int(np.ceil(tol_m / self.cell))
        out = np.zeros(n, dtype=bool)
        centre = int(np.floor((pos - origin[0]) / self.cell))
        for di in range(-k, k + 1):
            i = centre + di
            if i < 0 or i >= grid.shape[0]:
                continue
            ok = (j >= 0) & (j < grid.shape[1])
            out[ok] |= grid[i, j[ok]]
        return out


def build_support(cloud: Cloud, levels: Levels, frame: ManhattanFrame, cfg: dict) -> WallSupport:
    """Wall-point occupancy in the support band, binned per axis.

    The band is the highest one that real captures actually cover. Handheld
    scans look down far more than up, so a band chosen from the best scan is
    empty in the others.
    """
    ccfg = cfg["cells"]
    lo, hi = ccfg["support_band_m"]
    cell = ccfg["support_cell_m"]
    h = cloud.points[:, 1] - levels.floor.height_at(cloud.points[:, [0, 2]])
    horizontal = np.abs(cloud.normals[:, 1]) < cfg["horizontal_normal_cos"]
    sel = horizontal & (h >= lo) & (h <= hi)
    xz = frame.to_frame(cloud.points[sel][:, [0, 2]])
    nrm = frame.rotate_normals(cloud.normals[sel])
    grids: dict[int, np.ndarray] = {}
    origins: dict[int, np.ndarray] = {}
    for axis in (0, 1):
        belongs = (np.abs(nrm[:, 0]) >= np.abs(nrm[:, 2])) if axis == 0 else (np.abs(nrm[:, 2]) > np.abs(nrm[:, 0]))
        pts = xz[belongs]
        if len(pts) == 0:
            grids[axis] = np.zeros((1, 1), dtype=bool)
            origins[axis] = np.zeros(2)
            continue
        key = np.stack([pts[:, axis], pts[:, 1 - axis]], axis=1)
        origin = key.min(axis=0) - cell
        shape = (int(np.ceil((key[:, 0].max() - origin[0]) / cell)) + 2,
                 int(np.ceil((key[:, 1].max() - origin[1]) / cell)) + 2)
        g = np.zeros(shape, dtype=bool)
        ij = np.floor((key - origin) / cell).astype(np.int64)
        g[ij[:, 0], ij[:, 1]] = True
        grids[axis] = g
        origins[axis] = origin
    return WallSupport(cell, (lo, hi), grids, origins)


def _merge_lines(values: list[float], min_gap: float) -> list[float]:
    """Collapse grid lines closer than ``min_gap`` so cells are not slivers."""
    if not values:
        return []
    vals = sorted(values)
    out = [vals[0]]
    for v in vals[1:]:
        if v - out[-1] < min_gap:
            out[-1] = (out[-1] + v) / 2.0
        else:
            out.append(v)
    return out


def _gaps_from_profile(prof: np.ndarray, cell: float) -> tuple[float, float]:
    """Supported share and the longest unsupported run, in metres."""
    if len(prof) == 0:
        return 0.0, 0.0
    share = float(prof.mean())
    longest = run = 0
    for v in prof:
        run = 0 if v else run + 1
        longest = max(longest, run)
    return share, longest * cell


@dataclass
class Cell:
    i: int
    j: int
    x0: float
    x1: float
    z0: float
    z1: float
    interior: bool = False
    observed_share: float = 0.0
    label: int = 0

    @property
    def area(self) -> float:
        return (self.x1 - self.x0) * (self.z1 - self.z0)

    def polygon(self) -> SPoly:
        return box(self.x0, self.z0, self.x1, self.z1)


@dataclass
class CellComplex:
    xs: list[float]
    zs: list[float]
    cells: dict[tuple[int, int], Cell] = field(default_factory=dict)


def build_complex(cloud: Cloud, levels: Levels, frame: ManhattanFrame, faces: list[WallFace],
                  cfg: dict) -> tuple[CellComplex, np.ndarray, np.ndarray]:
    """Grid lines from wall faces plus the observed bounds, cells marked interior."""
    ccfg = cfg["cells"]
    structural = [f for f in faces if f.is_structural(cfg["wall"]["wall_min_top_m"])]
    # Walls block the dilation, otherwise observed floor bleeds through them
    # and the space outside the building is marked interior.
    c = ccfg["observed_cell_m"]
    probe, probe_origin = observed_mask(cloud, levels, frame, c, reach_m=0.0)
    barrier = np.zeros_like(probe)
    for f in structural:
        for a, b in f.segments:
            n = max(int((b - a) / (c / 2)), 1)
            along = np.linspace(a, b, n + 1)
            p = np.empty((len(along), 2))
            p[:, f.axis] = f.pos
            p[:, 1 - f.axis] = along
            ij = np.floor((p - probe_origin) / c).astype(np.int64)
            ok = (ij[:, 0] >= 0) & (ij[:, 0] < barrier.shape[0]) & (ij[:, 1] >= 0) & (ij[:, 1] < barrier.shape[1])
            barrier[ij[ok, 0], ij[ok, 1]] = True
    barrier = ndimage.binary_dilation(barrier, np.ones((3, 3), bool))
    obs, obs_origin = observed_mask(cloud, levels, frame, c,
                                    reach_m=ccfg["observed_reach_m"], barriers=barrier)
    ii, jj = np.nonzero(obs)
    if len(ii) == 0:
        raise ValueError("no observed free space to segment")
    bounds = (obs_origin[0] + ii.min() * c, obs_origin[0] + (ii.max() + 1) * c,
              obs_origin[1] + jj.min() * c, obs_origin[1] + (jj.max() + 1) * c)

    xs = [f.pos for f in structural if f.axis == 0 and bounds[0] - 1.0 < f.pos < bounds[1] + 1.0]
    zs = [f.pos for f in structural if f.axis == 1 and bounds[2] - 1.0 < f.pos < bounds[3] + 1.0]
    xs = _merge_lines(xs + [bounds[0], bounds[1]], ccfg["min_line_gap_m"])
    zs = _merge_lines(zs + [bounds[2], bounds[3]], ccfg["min_line_gap_m"])

    complex_ = CellComplex(xs, zs)
    for i in range(len(xs) - 1):
        for j in range(len(zs) - 1):
            cell = Cell(i, j, xs[i], xs[i + 1], zs[j], zs[j + 1])
            if cell.area < ccfg["min_cell_area_m2"]:
                continue
            i0 = max(int((cell.x0 - obs_origin[0]) / c), 0)
            i1 = min(int(np.ceil((cell.x1 - obs_origin[0]) / c)), obs.shape[0])
            j0 = max(int((cell.z0 - obs_origin[1]) / c), 0)
            j1 = min(int(np.ceil((cell.z1 - obs_origin[1]) / c)), obs.shape[1])
            sub = obs[i0:i1, j0:j1]
            cell.observed_share = float(sub.mean()) if sub.size else 0.0
            cell.interior = cell.observed_share >= ccfg["min_observed_share"]
            complex_.cells[(i, j)] = cell
    return complex_, obs, obs_origin


@dataclass
class EdgeVerdict:
    supported_share: float
    max_gap_m: float
    cut: bool


def edge_verdict(support: WallSupport, axis: int, pos: float, a0: float, a1: float,
                 cfg: dict) -> EdgeVerdict:
    """Is the edge between two cells a wall (cut) or open space (merge)?

    An edge is a wall when most of it carries wall points in the support band
    and every unsupported run is no longer than a doorway. A longer run means
    the two cells are one space with a wide opening, not two rooms.
    """
    ccfg = cfg["cells"]
    prof = support.support_profile(axis, pos, a0, a1, ccfg["support_tol_m"])
    share, gap = _gaps_from_profile(prof, support.cell)
    cut = share >= ccfg["min_support_share"] and gap <= ccfg["max_opening_m"]
    return EdgeVerdict(share, gap, cut)


def segment_rooms_cells(cloud: Cloud, levels: Levels, frame: ManhattanFrame, faces: list[WallFace],
                        cfg: dict) -> RoomResult:
    ccfg = cfg["cells"]
    rcfg = cfg["room"]
    support = build_support(cloud, levels, frame, cfg)
    complex_, obs, obs_origin = build_complex(cloud, levels, frame, faces, cfg)
    warnings: list[str] = []

    interior = {k: c for k, c in complex_.cells.items() if c.interior}
    if not interior:
        raise ValueError("no interior cells; the capture observed no enclosed space")

    # Union-find over interior cells: merge across every edge that is not a wall.
    parent = {k: k for k in interior}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    edges: list[dict] = []
    for (i, j), cell in interior.items():
        for di, dj in ((1, 0), (0, 1)):
            nb = interior.get((i + di, j + dj))
            if nb is None:
                continue
            if di:  # shared edge is the x line between them, running along z
                axis, pos = 0, cell.x1
                a0, a1 = max(cell.z0, nb.z0), min(cell.z1, nb.z1)
            else:
                axis, pos = 1, cell.z1
                a0, a1 = max(cell.x0, nb.x0), min(cell.x1, nb.x1)
            if a1 - a0 <= 0:
                continue
            v = edge_verdict(support, axis, pos, a0, a1, cfg)
            edges.append({"axis": axis, "pos": pos, "a0": a0, "a1": a1,
                          "share": v.supported_share, "gap": v.max_gap_m, "cut": v.cut,
                          "cells": ((i, j), (i + di, j + dj))})
            if not v.cut:
                union((i, j), (i + di, j + dj))

    groups: dict[tuple[int, int], list[Cell]] = {}
    for k, cell in interior.items():
        groups.setdefault(find(k), []).append(cell)

    # Outer boundary support per group decides the partially observed flag.
    rooms: list[Room] = []
    cell_grid = rcfg["grid_m"]
    xz_all = np.array([[c.x0, c.z0] for c in complex_.cells.values()] +
                      [[c.x1, c.z1] for c in complex_.cells.values()])
    lo = xz_all.min(axis=0) - 0.3
    hi = xz_all.max(axis=0) + 0.3
    shape = (int(np.ceil((hi[0] - lo[0]) / cell_grid)), int(np.ceil((hi[1] - lo[1]) / cell_grid)))
    grid = Grid(origin=lo, cell=cell_grid, shape=shape)

    candidates = []
    for key, cells in groups.items():
        merged = unary_union([c.polygon() for c in cells])
        if merged.geom_type == "MultiPolygon":
            merged = max(merged.geoms, key=lambda g: g.area)
        if merged.is_empty or merged.area <= 0:
            continue
        ring = [(float(x), float(z)) for x, z in merged.exterior.coords[:-1]]
        if len(ring) < 4:
            continue
        if not SPoly(ring).exterior.is_ccw:
            ring = ring[::-1]
        member = {(c.i, c.j) for c in cells}
        # Perimeter support: how much of the room outline is backed by wall.
        supported = total = 0.0
        for c in cells:
            for axis, pos, a0, a1, nb in ((0, c.x0, c.z0, c.z1, (c.i - 1, c.j)),
                                          (0, c.x1, c.z0, c.z1, (c.i + 1, c.j)),
                                          (1, c.z0, c.x0, c.x1, (c.i, c.j - 1)),
                                          (1, c.z1, c.x0, c.x1, (c.i, c.j + 1))):
                if nb in member:
                    continue
                prof = support.support_profile(axis, pos, a0, a1, ccfg["support_tol_m"])
                share, _ = _gaps_from_profile(prof, support.cell)
                total += a1 - a0
                supported += (a1 - a0) * share
        perimeter_support = supported / total if total else 0.0
        candidates.append((merged.area, ring, cells, perimeter_support, key))

    candidates.sort(key=lambda t: (-t[0], t[4]))
    n_room = n_conn = 0
    for area, ring, cells, perim, _ in candidates:
        if area < ccfg["min_keep_area_m2"]:
            continue
        mask = np.zeros(shape, dtype=bool)
        for c in cells:
            i0 = max(int((c.x0 - lo[0]) / cell_grid), 0)
            i1 = min(int(np.ceil((c.x1 - lo[0]) / cell_grid)), shape[0])
            j0 = max(int((c.z0 - lo[1]) / cell_grid), 0)
            j1 = min(int(np.ceil((c.z1 - lo[1]) / cell_grid)), shape[1])
            mask[i0:i1, j0:j1] = True
        kind = "room" if area >= rcfg["min_area_m2"] else "connector"
        if kind == "room":
            n_room += 1
            rid, label = f"room_{n_room:02d}", f"Room {n_room}"
        else:
            n_conn += 1
            rid, label = f"connector_{n_conn:02d}", f"Connector {n_conn}"
        room = Room(id=rid, label=label, kind=kind, polygon_frame=ring,
                    polygon_world=[tuple(p) for p in frame.to_world(np.array(ring))],
                    area_m2=float(area), mask=mask)
        room.partially_observed = perim < ccfg["min_perimeter_support"]
        room.perimeter_support = float(perim)
        rooms.append(room)

    if not rooms:
        raise ValueError("cell segmentation produced no rooms")
    n_partial = sum(1 for r in rooms if getattr(r, "partially_observed", False))
    if n_partial:
        warnings.append(
            f"{n_partial} of {len(rooms)} rooms have less than "
            f"{ccfg['min_perimeter_support']:.0%} of their outline backed by observed wall; "
            "they are flagged partially observed and their intervals are widened")

    free = np.zeros(shape, dtype=bool)
    for r in rooms:
        free |= r.mask
    occupied = ndimage.binary_dilation(np.zeros(shape, dtype=bool))
    labels = np.zeros(shape, dtype=np.int32)
    for n, r in enumerate(rooms, start=1):
        labels[r.mask] = n
    result = RoomResult(rooms, grid, free, occupied, labels, warnings)
    result.edges = edges
    result.support = support
    result.complex = complex_
    return result
