"""Stage 5: split the floor into rooms and give each a rectilinear polygon.

Free space is where the floor was seen or the camera walked; occupied space is
where wall points are. Eroding free space by about half a metre pinches every
doorway shut, so connected components of the eroded mask are room seeds. A
watershed grows the seeds back to the full free space, which puts the room
boundary in the middle of each doorway rather than at an arbitrary place.

Polygons are made rectilinear (every edge axis aligned in the Manhattan frame)
and their edges snapped to detected wall faces, so a room's area is measured
between wall faces the way a tape measure would.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage
from shapely.geometry import Polygon as SPoly, box
from shapely.ops import unary_union
from skimage.segmentation import watershed

from cozmo.lidar.cloud import Cloud
from cozmo.lidar.levels import Levels
from cozmo.lidar.walls import ManhattanFrame, WallFace


@dataclass
class Grid:
    origin: np.ndarray  # (2,) frame coordinates of cell (0, 0) corner
    cell: float
    shape: tuple[int, int]

    def to_cell(self, xz: np.ndarray) -> np.ndarray:
        return np.floor((xz - self.origin) / self.cell).astype(np.int64)

    def to_world(self, ij: np.ndarray) -> np.ndarray:
        """Cell centres in frame coordinates."""
        return self.origin + (np.asarray(ij, dtype=np.float64) + 0.5) * self.cell

    def inside(self, ij: np.ndarray) -> np.ndarray:
        return (ij[:, 0] >= 0) & (ij[:, 0] < self.shape[0]) & (ij[:, 1] >= 0) & (ij[:, 1] < self.shape[1])

    def raster(self, xz: np.ndarray) -> np.ndarray:
        mask = np.zeros(self.shape, dtype=bool)
        if len(xz) == 0:
            return mask
        ij = self.to_cell(xz)
        ok = self.inside(ij)
        mask[ij[ok, 0], ij[ok, 1]] = True
        return mask


@dataclass
class Room:
    id: str
    label: str
    kind: str  # room or connector
    polygon_frame: list[tuple[float, float]]
    polygon_world: list[tuple[float, float]]
    area_m2: float
    mask: np.ndarray = field(repr=False, default=None)
    # Set by the cell-complex segmentation: a room whose outline is only
    # partly backed by observed wall is reported, not silently closed.
    partially_observed: bool = False
    perimeter_support: float = 1.0


@dataclass
class RoomResult:
    rooms: list[Room]
    grid: Grid
    free: np.ndarray
    occupied: np.ndarray
    labels: np.ndarray
    warnings: list[str] = field(default_factory=list)
    edges: list = field(default_factory=list)
    support: object = None
    complex: object = None


def _densify(path: np.ndarray, step: float) -> np.ndarray:
    """Sample a polyline at ``step`` so rasterising it leaves no gaps between frames."""
    if len(path) < 2:
        return path
    out = [path[:1]]
    for a, b in zip(path[:-1], path[1:]):
        d = float(np.linalg.norm(b - a))
        n = max(int(d / step), 1)
        out.append(a + (b - a) * np.linspace(0, 1, n + 1)[1:, None])
    return np.vstack(out)


def _snap(value: float, targets: np.ndarray, tol: float) -> float:
    if len(targets) == 0:
        return value
    i = int(np.argmin(np.abs(targets - value)))
    return float(targets[i]) if abs(targets[i] - value) <= tol else value


def _cell_lines(faces_pos: np.ndarray, lo: float, hi: float, snap_m: float) -> np.ndarray:
    """Candidate polygon edge positions: wall faces inside the span, plus the span ends."""
    inside = faces_pos[(faces_pos > lo - snap_m) & (faces_pos < hi + snap_m)]
    lines = np.concatenate([[lo, hi], inside])
    lines = np.sort(np.unique(np.round(lines, 6)))
    # Drop lines that sit within snap_m of the previous one; they would make
    # slivers, and a wall face that close to the mask edge is the same edge.
    keep = [lines[0]]
    for v in lines[1:]:
        if v - keep[-1] > snap_m:
            keep.append(v)
        else:
            keep[-1] = v if abs(v - lo) > snap_m and abs(v - hi) > snap_m else keep[-1]
    return np.array(keep)


def polygon_from_faces(mask: np.ndarray, grid: "Grid", snap_x: np.ndarray, snap_z: np.ndarray,
                       snap_m: float, min_fill: float = 0.5) -> list[tuple[float, float]] | None:
    """Rectilinear polygon as the union of wall-bounded cells that the mask mostly fills.

    Wall faces cut the room's bounding box into a coarse grid. A coarse cell
    joins the room when the mask fills at least ``min_fill`` of it. The result
    is axis aligned and snapped to real wall faces by construction, which is
    both what a floor plan looks like and what makes the area comparable to a
    tape measure between wall faces.
    """
    ii, jj = np.nonzero(mask)
    if len(ii) == 0:
        return None
    x0 = grid.origin[0] + ii.min() * grid.cell
    x1 = grid.origin[0] + (ii.max() + 1) * grid.cell
    z0 = grid.origin[1] + jj.min() * grid.cell
    z1 = grid.origin[1] + (jj.max() + 1) * grid.cell
    xs = _cell_lines(snap_x, x0, x1, snap_m)
    zs = _cell_lines(snap_z, z0, z1, snap_m)
    if len(xs) < 2 or len(zs) < 2:
        return None
    boxes = []
    for a, b in zip(xs[:-1], xs[1:]):
        i0 = int(np.floor((a - grid.origin[0]) / grid.cell))
        i1 = int(np.ceil((b - grid.origin[0]) / grid.cell))
        for c, d in zip(zs[:-1], zs[1:]):
            j0 = int(np.floor((c - grid.origin[1]) / grid.cell))
            j1 = int(np.ceil((d - grid.origin[1]) / grid.cell))
            sub = mask[max(i0, 0):i1, max(j0, 0):j1]
            if sub.size and sub.mean() >= min_fill:
                boxes.append(box(a, c, b, d))
    if not boxes:
        return None
    merged = unary_union(boxes)
    if merged.geom_type == "MultiPolygon":
        merged = max(merged.geoms, key=lambda g: g.area)
    if merged.is_empty or merged.area <= 0:
        return None
    ring = list(merged.exterior.simplify(1e-9).coords)[:-1]
    out: list[tuple[float, float]] = []
    for x, z in ring:
        if not out or abs(out[-1][0] - x) > 1e-9 or abs(out[-1][1] - z) > 1e-9:
            out.append((float(x), float(z)))
    if len(out) < 4:
        return None
    if not SPoly(out).exterior.is_ccw:
        out = out[::-1]
    return out


def merge_open_regions(labels: np.ndarray, dist: np.ndarray, min_constriction_m: float) -> np.ndarray:
    """Merge watershed regions whose shared border is not a doorway.

    Furniture puts wall-like points inside a room, so eroded free space can
    break one room into several seeds. Two regions are the same room when the
    passage between them is wide: the widest point on their shared border has a
    clearance above ``min_constriction_m`` (half the passage width). A real
    doorway has clearance around 0.4 to 0.6 m, an open split inside a room has
    much more. Labels are renumbered by descending area so the output is
    deterministic.
    """
    pairs: list[np.ndarray] = []
    clear: list[np.ndarray] = []
    for a, b, da, db in ((labels[:-1, :], labels[1:, :], dist[:-1, :], dist[1:, :]),
                         (labels[:, :-1], labels[:, 1:], dist[:, :-1], dist[:, 1:])):
        m = (a > 0) & (b > 0) & (a != b)
        if not m.any():
            continue
        pairs.append(np.stack([np.minimum(a[m], b[m]), np.maximum(a[m], b[m])], axis=1))
        clear.append(np.maximum(da[m], db[m]))
    n = int(labels.max())
    parent = np.arange(n + 1)

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    if pairs:
        pr = np.concatenate(pairs)
        cl = np.concatenate(clear)
        key = pr[:, 0] * (n + 1) + pr[:, 1]
        uniq, inv = np.unique(key, return_inverse=True)
        best = np.zeros(len(uniq))
        np.maximum.at(best, inv, cl)
        for k, c in zip(uniq, best):
            if c > min_constriction_m:
                ra, rb = find(int(k // (n + 1))), find(int(k % (n + 1)))
                if ra != rb:
                    parent[max(ra, rb)] = min(ra, rb)
    root = np.array([find(i) for i in range(n + 1)])
    root[0] = 0
    merged = root[labels]
    # Renumber by descending area, ties broken by first appearance.
    ids, counts = np.unique(merged[merged > 0], return_counts=True)
    order = ids[np.lexsort((ids, -counts))]
    remap = np.zeros(int(merged.max()) + 1, dtype=np.int64)
    for new, old in enumerate(order, start=1):
        remap[old] = new
    return remap[merged]


def segment_rooms(cloud: Cloud, levels: Levels, frame: ManhattanFrame, faces: list[WallFace],
                  cfg: dict) -> RoomResult:
    rcfg = cfg["room"]
    cell = rcfg["grid_m"]
    warnings: list[str] = []

    xz = frame.to_frame(cloud.points[:, [0, 2]])
    path = frame.to_frame(cloud.camera_path[:, [0, 2]]) if len(cloud.camera_path) else np.zeros((0, 2))
    lo = np.minimum(xz.min(axis=0), path.min(axis=0) if len(path) else xz.min(axis=0)) - 0.3
    hi = np.maximum(xz.max(axis=0), path.max(axis=0) if len(path) else xz.max(axis=0)) + 0.3
    shape = (int(np.ceil((hi[0] - lo[0]) / cell)), int(np.ceil((hi[1] - lo[1]) / cell)))
    grid = Grid(origin=lo, cell=cell, shape=shape)

    floor_sel = np.abs(cloud.points[:, 1] - levels.floor.height_at(cloud.points[:, [0, 2]])) <= 0.06
    floor_sel &= np.abs(cloud.normals[:, 1]) >= cfg["vertical_normal_cos"]
    free = grid.raster(xz[floor_sel])
    if len(path):
        free |= ndimage.binary_dilation(grid.raster(_densify(path, cell / 2)),
                                        structure=np.ones((3, 3), bool), iterations=int(round(0.15 / cell)))

    # Only structural faces block room segmentation: furniture makes vertical
    # planes too, and treating a sofa back as a wall splits one room in two.
    blocking = [f for f in faces if f.is_structural(rcfg["wall_min_top_m"])]
    wall_mask_points = []
    for f in blocking:
        for a, b in f.segments:
            n = max(int((b - a) / (cell / 2)), 1)
            along = np.linspace(a, b, n + 1)
            pos = np.full_like(along, f.pos)
            wall_mask_points.append(np.column_stack([pos, along] if f.axis == 0 else [along, pos]))
    occupied = grid.raster(np.vstack(wall_mask_points)) if wall_mask_points else np.zeros(shape, bool)
    occupied = ndimage.binary_dilation(occupied, np.ones((3, 3), bool))

    free = free & ~occupied
    free = ndimage.binary_closing(free, np.ones((5, 5), bool))
    # Anything enclosed by walls and observed floor is floor, even where the
    # scan never looked (under furniture). Filling the enclosed region is what
    # turns a walked path into a room; without it, room area measures the
    # capture pattern instead of the room.
    free = ndimage.binary_fill_holes(free | occupied) & ~occupied
    free = ndimage.binary_opening(free, np.ones((3, 3), bool))

    # Erode by half a metre: every doorway narrower than a metre pinches shut,
    # so the remaining components are room cores rather than one blob.
    dist = ndimage.distance_transform_edt(free) * cell
    seeds, n_seeds = ndimage.label(dist > rcfg["erode_m"])
    if n_seeds == 0:
        seeds, n_seeds = ndimage.label(free)
        warnings.append("Room seeding fell back to raw free space: no component survived erosion")
    labels = watershed(-dist, markers=seeds, mask=free)
    labels = merge_open_regions(labels, dist, rcfg["min_constriction_m"])

    snap_x = np.array(sorted(f.pos for f in blocking if f.axis == 0))
    snap_z = np.array(sorted(f.pos for f in blocking if f.axis == 1))
    cand: list[tuple[float, np.ndarray, int]] = []
    for lab in range(1, int(labels.max()) + 1):
        m = labels == lab
        area = float(m.sum()) * cell * cell
        if area <= 0:
            continue
        cand.append((area, m, lab))
    cand.sort(key=lambda t: (-t[0], t[2]))

    rooms: list[Room] = []
    for area, m, lab in cand:
        poly = polygon_from_faces(m, grid, snap_x, snap_z, rcfg["snap_m"])
        if poly is None:
            warnings.append(f"Component {lab} dropped: no valid rectilinear polygon")
            continue
        poly_area = SPoly(poly).area
        kind = "room" if poly_area >= rcfg["min_area_m2"] else "connector"
        rooms.append(Room(id="", label="", kind=kind, polygon_frame=poly,
                          polygon_world=[tuple(p) for p in frame.to_world(np.array(poly))],
                          area_m2=float(poly_area), mask=m))

    rooms = [r for r in rooms if r.area_m2 >= 0.5]
    rooms.sort(key=lambda r: -r.area_m2)
    n_conn = 0
    for i, r in enumerate(rooms, start=1):
        if r.kind == "connector":
            n_conn += 1
            r.id = f"connector_{n_conn:02d}"
            r.label = f"Connector {n_conn}"
        else:
            r.id = f"room_{i:02d}"
            r.label = f"Room {i}"
    return RoomResult(rooms, grid, free, occupied, labels, warnings)
