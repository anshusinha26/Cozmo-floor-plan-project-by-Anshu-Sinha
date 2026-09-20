"""Register two plans of the same space, then match their rooms and walls.

Matching two captures by room id is meaningless: ids are per-capture inventions
numbered by size. Matching by floor area is worse than it looks, because two
rooms of similar size in different corners of a flat pair happily, which turns
an eval artefact into a reconstruction failure.

This module puts both plans in one frame first:

* each plan is first rotated into its own Manhattan frame, estimated from its
  own wall segments. Plans are emitted in the ARKit world frame, whose
  orientation depends on where the capture started, so two captures of one
  flat can sit at any relative angle; only after this step is the residual
  rotation one of 0, 90, 180, 270 degrees. All four are tried.
* the translation comes from cross-correlating rasterised footprint masks on a
  5 cm grid, which is a plain brute-force best overlap rather than a fit that
  could converge to a local optimum.
* the transform with the best footprint intersection over union wins, and that
  IoU is reported so a weak registration cannot pass unnoticed.

Rooms then match by polygon IoU under a global assignment (Hungarian), and
walls inside matched rooms by nearest parallel face. Cyclic order is not used:
the two captures produce different vertex counts for the same room, so a
cyclic assignment pairs walls that are not the same wall.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.signal import fftconvolve
from shapely.geometry import Polygon as SPoly

from cozmo.contracts.models import Plan, Room

DEFAULT_CELL_M = 0.05
DEFAULT_MIN_IOU = 0.3
DEFAULT_WALL_OFFSET_M = 0.3
DEFAULT_WALL_ANGLE_DEG = 2.0


@dataclass
class Registration:
    """Rigid transform taking plan B into plan A's frame: rotate, then translate.

    ``rotation_deg`` is the total rotation in world terms, which is the
    difference of the two plans' Manhattan yaws plus the chosen quarter turn.
    ``quarter_turns`` records which of the four was picked.
    """

    rotation_deg: float
    tx: float
    ty: float
    iou: float
    cell_m: float = DEFAULT_CELL_M
    quarter_turns: int = 0
    yaw_a_deg: float = 0.0
    yaw_b_deg: float = 0.0

    @property
    def matrix(self) -> np.ndarray:
        th = np.radians(self.rotation_deg)
        c, s = np.cos(th), np.sin(th)
        return np.array([[c, -s], [s, c]])


def manhattan_yaw(plan: Plan) -> float:
    """Dominant wall direction of one plan, in degrees in [0, 90).

    Wall directions repeat every 90 degrees, so angles are quadrupled before
    the length-weighted circular mean and divided back, which stops the two
    orientations of a rectangular room from cancelling.
    """
    ang = []
    wts = []
    for room in plan.rooms:
        for w in room.walls:
            d = np.asarray(w.end, dtype=float) - np.asarray(w.start, dtype=float)
            n = float(np.linalg.norm(d))
            if n < 1e-9:
                continue
            ang.append(np.arctan2(d[1], d[0]))
            wts.append(n)
    if not ang:
        return 0.0
    ang = np.asarray(ang)
    wts = np.asarray(wts)
    c = float(np.sum(wts * np.cos(4 * ang)))
    s = float(np.sum(wts * np.sin(4 * ang)))
    return float(np.degrees((np.arctan2(s, c) / 4.0) % (np.pi / 2)))


def transform_xy(xy: np.ndarray, reg: Registration) -> np.ndarray:
    return np.asarray(xy, dtype=float) @ reg.matrix.T + np.array([reg.tx, reg.ty])


def _rasterise(polys: list[SPoly], cell: float, origin: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    """Fill polygons onto a grid by point-in-polygon on cell centres."""
    mask = np.zeros(shape, dtype=bool)
    if not polys:
        return mask
    for poly in polys:
        minx, miny, maxx, maxy = poly.bounds
        i0 = max(int((minx - origin[0]) / cell), 0)
        i1 = min(int((maxx - origin[0]) / cell) + 2, shape[0])
        j0 = max(int((miny - origin[1]) / cell), 0)
        j1 = min(int((maxy - origin[1]) / cell) + 2, shape[1])
        if i1 <= i0 or j1 <= j0:
            continue
        ii, jj = np.meshgrid(np.arange(i0, i1), np.arange(j0, j1), indexing="ij")
        px = origin[0] + (ii + 0.5) * cell
        py = origin[1] + (jj + 0.5) * cell
        # Even-odd ray casting, vectorised: cheaper than shapely per point.
        ring = np.asarray(poly.exterior.coords[:-1])
        inside = np.zeros(px.shape, dtype=bool)
        n = len(ring)
        for k in range(n):
            x1, y1 = ring[k]
            x2, y2 = ring[(k + 1) % n]
            cond = ((y1 > py) != (y2 > py))
            with np.errstate(divide="ignore", invalid="ignore"):
                xint = (x2 - x1) * (py - y1) / (y2 - y1 + 1e-300) + x1
            inside ^= cond & (px < xint)
        mask[i0:i1, j0:j1] |= inside
    return mask


def _rot(deg: float) -> np.ndarray:
    th = np.radians(deg)
    c, s = np.cos(th), np.sin(th)
    return np.array([[c, -s], [s, c]])


def _room_polys(plan: Plan, rotate_deg: float = 0.0) -> list[SPoly]:
    out = []
    R = _rot(rotate_deg)
    for r in plan.rooms:
        pts = np.asarray(r.polygon, dtype=float) @ R.T
        p = SPoly(pts)
        if p.is_valid and p.area > 0:
            out.append(p)
    return out


def footprint_mask(plan: Plan, cell: float = DEFAULT_CELL_M, origin: np.ndarray | None = None,
                   shape: tuple[int, int] | None = None) -> tuple[np.ndarray, np.ndarray]:
    polys = _room_polys(plan)
    if origin is None or shape is None:
        allpts = np.vstack([np.asarray(p.exterior.coords) for p in polys])
        origin = allpts.min(axis=0) - cell
        span = allpts.max(axis=0) + cell - origin
        shape = (int(np.ceil(span[0] / cell)) + 1, int(np.ceil(span[1] / cell)) + 1)
    return _rasterise(polys, cell, origin, shape), origin


def _rotate_polys(polys: list[SPoly], deg: int) -> list[SPoly]:
    th = np.radians(deg)
    c, s = np.cos(th), np.sin(th)
    R = np.array([[c, -s], [s, c]])
    return [SPoly(np.asarray(p.exterior.coords[:-1]) @ R.T) for p in polys]


def register_plans(plan_a: Plan, plan_b: Plan, cell: float = DEFAULT_CELL_M) -> Registration:
    """Best of the four Manhattan rotations, translation by mask cross-correlation."""
    yaw_a = manhattan_yaw(plan_a)
    yaw_b = manhattan_yaw(plan_b)
    polys_a = _room_polys(plan_a, -yaw_a)
    polys_b = _room_polys(plan_b, -yaw_b)
    if not polys_a or not polys_b:
        return Registration(0.0, 0.0, 0.0, 0.0, cell, 0, yaw_a, yaw_b)

    pts_a = np.vstack([np.asarray(p.exterior.coords) for p in polys_a])
    origin_a = pts_a.min(axis=0) - 1.0
    span_a = pts_a.max(axis=0) + 1.0 - origin_a
    shape_a = (int(np.ceil(span_a[0] / cell)) + 1, int(np.ceil(span_a[1] / cell)) + 1)
    mask_a = _rasterise(polys_a, cell, origin_a, shape_a)
    area_a = mask_a.sum()

    best = Registration(0.0, 0.0, 0.0, 0.0, cell, 0, yaw_a, yaw_b)
    for deg in (0, 90, 180, 270):
        rot = _rotate_polys(polys_b, deg)
        pts_b = np.vstack([np.asarray(p.exterior.coords) for p in rot])
        origin_b = pts_b.min(axis=0) - 1.0
        span_b = pts_b.max(axis=0) + 1.0 - origin_b
        shape_b = (int(np.ceil(span_b[0] / cell)) + 1, int(np.ceil(span_b[1] / cell)) + 1)
        mask_b = _rasterise(rot, cell, origin_b, shape_b)
        area_b = mask_b.sum()
        if area_a == 0 or area_b == 0:
            continue
        # Correlation of the two masks: peak is the shift with the most overlap.
        corr = fftconvolve(mask_a.astype(np.float32), mask_b[::-1, ::-1].astype(np.float32), mode="full")
        k = int(np.argmax(corr))
        di, dj = np.unravel_index(k, corr.shape)
        inter = float(corr[di, dj])
        iou = inter / (area_a + area_b - inter) if (area_a + area_b - inter) > 0 else 0.0
        shift_i = di - (mask_b.shape[0] - 1)
        shift_j = dj - (mask_b.shape[1] - 1)
        tx = origin_a[0] - origin_b[0] + shift_i * cell
        ty = origin_a[1] - origin_b[1] + shift_j * cell
        if iou > best.iou:
            # Compose: canonicalise B, quarter turn, then back into A's world
            # frame. Rotation adds up; the translation rotates with yaw_a.
            total = (yaw_a - yaw_b + deg) % 360.0
            t_world = _rot(yaw_a) @ np.array([tx, ty])
            best = Registration(float(total), float(t_world[0]), float(t_world[1]),
                                float(iou), cell, deg, yaw_a, yaw_b)
    return best


@dataclass
class RoomPair:
    room_a: str
    room_b: str
    iou: float
    area_a: float
    area_b: float


def match_rooms_by_iou(plan_a: Plan, plan_b: Plan, reg: Registration,
                       min_iou: float = DEFAULT_MIN_IOU) -> list[RoomPair]:
    """Global assignment of rooms maximising total IoU, pairs below min_iou dropped."""
    ra, rb = plan_a.rooms, plan_b.rooms
    if not ra or not rb:
        return []
    pa = [SPoly(r.polygon) for r in ra]
    pb = [SPoly(transform_xy(np.asarray(r.polygon), reg)) for r in rb]
    iou = np.zeros((len(pa), len(pb)))
    for i, x in enumerate(pa):
        for j, y in enumerate(pb):
            if not x.is_valid or not y.is_valid:
                continue
            inter = x.intersection(y).area
            union = x.union(y).area
            iou[i, j] = inter / union if union > 0 else 0.0
    rows, cols = linear_sum_assignment(-iou)
    out = []
    for i, j in zip(rows, cols):
        if iou[i, j] >= min_iou:
            out.append(RoomPair(ra[i].id, rb[j].id, float(iou[i, j]),
                                float(pa[i].area), float(pb[j].area)))
    return out


@dataclass
class WallPair:
    wall_a: str
    wall_b: str
    length_a: float
    length_b: float
    offset_m: float
    angle_deg: float
    overlap_m: float


def _wall_line(start, end):
    a = np.asarray(start, dtype=float)
    b = np.asarray(end, dtype=float)
    d = b - a
    n = np.linalg.norm(d)
    if n < 1e-9:
        return None
    u = d / n
    normal = np.array([-u[1], u[0]])
    return a, b, u, normal, n


def match_walls_by_face(room_a: Room, room_b: Room, reg: Registration,
                        max_offset_m: float = DEFAULT_WALL_OFFSET_M,
                        max_angle_deg: float = DEFAULT_WALL_ANGLE_DEG,
                        ) -> tuple[list[WallPair], list[str], list[str]]:
    """Pair walls by nearest parallel face.

    Two walls match when their directions are parallel within ``max_angle_deg``
    (direction sign ignored, a wall has no orientation), their supporting lines
    are within ``max_offset_m``, and their extents overlap along the line. Greedy
    on smallest offset, so the closest faces pair first. Vertex counts differ
    between captures, so cyclic order cannot be used.
    """
    lines_a = [(w, _wall_line(w.start, w.end)) for w in room_a.walls]
    lines_b = []
    for w in room_b.walls:
        s = transform_xy(np.asarray([w.start]), reg)[0]
        e = transform_xy(np.asarray([w.end]), reg)[0]
        lines_b.append((w, _wall_line(s, e)))

    cands = []
    for ia, (wa, la) in enumerate(lines_a):
        if la is None:
            continue
        a0, a1, ua, na, len_a = la
        for ib, (wb, lb) in enumerate(lines_b):
            if lb is None:
                continue
            b0, b1, ub, nb, len_b = lb
            cos = abs(float(np.dot(ua, ub)))
            angle = float(np.degrees(np.arccos(np.clip(cos, -1.0, 1.0))))
            if angle > max_angle_deg:
                continue
            offset = abs(float(np.dot(b0 - a0, na)))
            if offset > max_offset_m:
                continue
            # Overlap of the two extents projected on wall A's direction.
            ta = sorted([0.0, len_a])
            tb = sorted([float(np.dot(b0 - a0, ua)), float(np.dot(b1 - a0, ua))])
            overlap = min(ta[1], tb[1]) - max(ta[0], tb[0])
            if overlap <= 0:
                continue
            cands.append((offset, -overlap, ia, ib, angle, overlap, len_a, len_b))
    cands.sort()
    used_a: set[int] = set()
    used_b: set[int] = set()
    pairs: list[WallPair] = []
    for offset, _, ia, ib, angle, overlap, len_a, len_b in cands:
        if ia in used_a or ib in used_b:
            continue
        used_a.add(ia)
        used_b.add(ib)
        pairs.append(WallPair(room_a.walls[ia].id, room_b.walls[ib].id,
                              room_a.walls[ia].length_m.value, room_b.walls[ib].length_m.value,
                              float(offset), float(angle), float(overlap)))
    un_a = [w.id for i, w in enumerate(room_a.walls) if i not in used_a]
    un_b = [w.id for i, w in enumerate(room_b.walls) if i not in used_b]
    return pairs, un_a, un_b
