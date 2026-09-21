"""Put independently reconstructed rooms into one property.

Nothing in a per-room capture relates one room to another: each is reconstructed
in its own frame, and no photo sees two rooms at once. So the layout cannot be
measured, only assumed, and the assumption here is a star: one connector, every
other room attached to its perimeter.

That is declared in the plan, the placements are marked approximate, and the
footprint interval is widened to cover the fact that the arrangement is a guess.
Room shapes and sizes are measurements; where the rooms sit relative to each
other is not.

Doors are used when both sides have them, because a door is the one feature two
rooms genuinely share. Otherwise a room is pushed up against the connector's
longest free wall. Either way shapely enforces that no two rooms overlap.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

import numpy as np
from shapely.affinity import rotate as shapely_rotate
from shapely.affinity import translate as shapely_translate
from shapely.geometry import Polygon as SPoly
from shapely.ops import unary_union

log = logging.getLogger(__name__)

CONNECTOR_NAMES = ("hall", "corridor", "living", "landing", "lobby")
PUSH_STEP_M = 0.05
MAX_PUSH_M = 6.0

STAR_ASSUMPTION = (
    "Star layout assumption: no photograph or clip sees two rooms at once, so nothing measures "
    "where one room sits relative to another. Each room is attached to the connector's perimeter, "
    "door to door where both sides have a door and wall to wall otherwise. Room shapes and sizes "
    "are measured; the arrangement is assumed, and the placements are approximate"
)


@dataclass
class Placed:
    room_id: str
    theta_deg: float
    tx: float
    ty: float
    polygon: list[tuple[float, float]]
    attached_by: str
    pushed_m: float = 0.0

    def summary(self) -> dict:
        return {"room_id": self.room_id, "theta_deg": round(self.theta_deg, 1),
                "tx": round(self.tx, 3), "ty": round(self.ty, 3),
                "attached_by": self.attached_by, "pushed_m": round(self.pushed_m, 3)}


@dataclass
class StitchResult:
    connector: str
    placed: list[Placed]
    adjacency: list[tuple[str, str, str | None]]
    footprint: list[tuple[float, float]]
    footprint_area_m2: float
    overlap_m2: float
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        return {"connector": self.connector, "n_rooms": len(self.placed),
                "placements": [p.summary() for p in self.placed],
                "adjacency": [[a, b] for a, b, _ in self.adjacency],
                "footprint_area_m2": round(self.footprint_area_m2, 3),
                "overlap_m2": round(self.overlap_m2, 4), "warnings": self.warnings}


def choose_connector(room_ids: list[str], areas: dict[str, float], requested: str | None) -> str:
    """The room everything else hangs off: asked for, named like a hall, or biggest."""
    if requested:
        if requested not in room_ids:
            raise ValueError(f"--connector {requested!r} is not one of {sorted(room_ids)}")
        return requested
    for rid in room_ids:
        if any(n in rid.lower() for n in CONNECTOR_NAMES):
            return rid
    return max(room_ids, key=lambda r: areas.get(r, 0.0))


def _edges(poly: SPoly) -> list[tuple[np.ndarray, np.ndarray]]:
    ring = list(poly.exterior.coords)[:-1]
    return [(np.array(ring[i]), np.array(ring[(i + 1) % len(ring)])) for i in range(len(ring))]


def _outward_normal(poly: SPoly, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    mid = (a + b) / 2
    d = b - a
    n = np.array([d[1], -d[0]], dtype=float)
    ln = np.linalg.norm(n)
    if ln < 1e-9:
        return np.array([1.0, 0.0])
    n = n / ln
    return n if not poly.contains(SPoly(poly.exterior).centroid.__class__(*(mid + 0.01 * n))) else -n


def _normal_of(poly: SPoly, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Unit normal of edge a-b pointing away from the polygon."""
    from shapely.geometry import Point

    d = b - a
    n = np.array([d[1], -d[0]], dtype=float)
    ln = np.linalg.norm(n)
    if ln < 1e-9:
        return np.array([1.0, 0.0])
    n /= ln
    mid = (a + b) / 2
    return -n if poly.contains(Point(*(mid + 0.02 * n))) else n


def _longest_edge(poly: SPoly) -> tuple[np.ndarray, np.ndarray]:
    return max(_edges(poly), key=lambda e: float(np.linalg.norm(e[1] - e[0])))


SQUARE_ASSUMPTION = (
    "Rooms are assumed square to each other: each room is rotated into its own Manhattan frame "
    "before placement, so every room sits at a quarter turn to the connector. Each room was "
    "reconstructed separately and carries a few degrees of its own yaw, which nothing in this "
    "pipeline measures against the building. Lengths and areas are unchanged by the rotation"
)


def _own_yaw_deg(poly: SPoly) -> float:
    """The polygon's own Manhattan yaw: how far its walls sit off the axes.

    Length-weighted circular mean of the edge directions taken modulo 90
    degrees, so the two orientations of a rectangular room reinforce rather
    than cancel. Rotating a room by minus this angle squares it to the page
    and changes no length or area, because it is a rigid rotation.
    """
    num = complex(0.0, 0.0)
    total = 0.0
    for a, b in _edges(poly):
        v = b - a
        length = float(np.hypot(v[0], v[1]))
        if length < 1e-9:
            continue
        ang = math.atan2(v[1], v[0])
        num += length * complex(math.cos(4 * ang), math.sin(4 * ang))
        total += length
    if total == 0.0 or abs(num) < 1e-12:
        return 0.0
    return float(math.degrees(math.atan2(num.imag, num.real)) / 4.0)


def _square_up(poly: SPoly, doors: list[dict]) -> tuple[SPoly, list[dict]]:
    """Rotate a room and its door centres into the room's own Manhattan frame."""
    yaw = _own_yaw_deg(poly)
    if abs(yaw) < 1e-9:
        return poly, doors
    origin = tuple(np.asarray(poly.centroid.coords[0]))
    squared = shapely_rotate(poly, -yaw, origin=origin, use_radians=False)
    c, s = math.cos(math.radians(-yaw)), math.sin(math.radians(-yaw))
    ox, oy = origin
    out = []
    for d in doors:
        x, y = float(d["centre"][0]) - ox, float(d["centre"][1]) - oy
        moved = dict(d)
        moved["centre"] = (c * x - s * y + ox, s * x + c * y + oy)
        out.append(moved)
    return squared, out


def _snap_quarter(theta_deg: float) -> float:
    """Rooms in one property share a Manhattan frame, so turns are quarter turns."""
    return float(round(theta_deg / 90.0) * 90.0)


def _place_one(room_poly: SPoly, room_edge, connector_poly: SPoly, connector_edge,
               room_anchor: np.ndarray, connector_anchor: np.ndarray, occupied: SPoly
               ) -> tuple[SPoly, float, np.ndarray, float]:
    """Rotate the room to face the connector edge, align the anchors, then clear it.

    Pushing straight out only separates a room from the connector. Two rooms
    hung on the same wall still sit on top of each other, which is how six rooms
    on one hall came out with 32 m2 of overlap against a gate of zero. So the
    search slides along the wall as well as away from it, and takes the first
    placement that touches nothing, nearest first.
    """
    ra, rb = room_edge
    ca, cb = connector_edge
    n_room = _normal_of(room_poly, ra, rb)
    n_conn = _normal_of(connector_poly, ca, cb)
    # The room's attaching wall must face back at the connector's wall.
    target = -n_conn
    theta = _snap_quarter(np.degrees(np.arctan2(target[1], target[0]) -
                                     np.arctan2(n_room[1], n_room[0])))
    origin = tuple(room_anchor)
    rotated = shapely_rotate(room_poly, theta, origin=origin, use_radians=False)
    shift = connector_anchor - room_anchor
    placed = shapely_translate(rotated, xoff=shift[0], yoff=shift[1])

    tangent = np.array([-n_conn[1], n_conn[0]])
    steps = int(MAX_PUSH_M / PUSH_STEP_M)
    best = None
    for out_k in range(steps + 1):
        for lat_k in range(steps + 1):
            for sign in ((1,) if lat_k == 0 else (1, -1)):
                offset = n_conn * (out_k * PUSH_STEP_M) + tangent * (sign * lat_k * PUSH_STEP_M)
                cand = shapely_translate(placed, xoff=offset[0], yoff=offset[1])
                if cand.intersection(occupied).area <= 1e-9:
                    best = (cand, offset, float(np.linalg.norm(offset)))
                    break
            if best:
                break
        if best:
            break
    if best is None:
        return placed, theta, shift, MAX_PUSH_M
    cand, offset, moved = best
    return cand, theta, shift + offset, moved


def stitch(rooms: dict[str, list[tuple[float, float]]], doors: dict[str, list[dict]],
           connector: str) -> StitchResult:
    """Attach every room to the connector, with no two rooms overlapping.

    ``doors`` maps room id to door centres. Zero overlap is asserted before the
    result is returned, because the gate is zero and a plan that quietly
    overlaps its own rooms is worse than one that refuses to be built.
    """
    polys = {rid: SPoly(p) for rid, p in rooms.items()}
    for rid, p in polys.items():
        if not p.is_valid or p.area <= 0:
            raise ValueError(f"{rid}: room polygon is not a usable shape")
    # Square every room to its own walls first. The placement search already
    # snaps the turn between a room and the connector to a quarter turn, but
    # that only holds the two square to each other if each is square in
    # itself: otherwise every room keeps the few degrees of yaw its own
    # reconstruction happened to end on, and the plan reads as a pile of
    # tilted boxes. Rotation changes no length and no area.
    doors = dict(doors)
    for rid in list(polys):
        polys[rid], squared_doors = _square_up(polys[rid], list(doors.get(rid, [])))
        if squared_doors:
            doors[rid] = squared_doors
    conn = polys[connector]
    occupied = conn
    placed: list[Placed] = [Placed(connector, 0.0, 0.0, 0.0,
                                   [tuple(c) for c in conn.exterior.coords[:-1]], "connector")]
    adjacency: list[tuple[str, str, str | None]] = []
    warnings: list[str] = []
    conn_doors = list(doors.get(connector, []))
    used_conn_doors: set[int] = set()

    for rid in sorted(r for r in rooms if r != connector):
        poly = polys[rid]
        room_doors = doors.get(rid, [])
        attached_by = "wall"
        via = None
        # Door to door when both sides have one that is still free.
        free = [i for i in range(len(conn_doors)) if i not in used_conn_doors]
        if room_doors and free:
            di = free[0]
            used_conn_doors.add(di)
            c_door = np.array(conn_doors[di]["centre"])
            r_door = np.array(max(room_doors, key=lambda d: d.get("width_m", 0.0))["centre"])
            c_edge = _nearest_edge(conn, c_door)
            r_edge = _nearest_edge(poly, r_door)
            attached_by = "door"
            via = conn_doors[di].get("id")
            anchors = (r_door, c_door)
        else:
            c_edge = _longest_free_edge(conn, occupied)
            r_edge = _longest_edge(poly)
            anchors = ((r_edge[0] + r_edge[1]) / 2, (c_edge[0] + c_edge[1]) / 2)
            if room_doors or conn_doors:
                warnings.append(f"{rid} is attached wall to wall: no free door pair was available "
                                f"between it and {connector}")
        moved, theta, total, pushed = _place_one(poly, r_edge, conn, c_edge, anchors[0],
                                                 anchors[1], occupied)
        if pushed >= MAX_PUSH_M:
            warnings.append(f"{rid} could not be placed clear of the other rooms within "
                            f"{MAX_PUSH_M:.0f} m; its position is unreliable")
        placed.append(Placed(rid, theta, float(total[0]), float(total[1]),
                             [tuple(c) for c in moved.exterior.coords[:-1]], attached_by, pushed))
        adjacency.append((connector, rid, via))
        occupied = unary_union([occupied, moved])
        polys[rid] = moved

    overlap = 0.0
    ids = list(polys)
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            overlap += polys[ids[i]].intersection(polys[ids[j]]).area
    if overlap > 1e-6:
        raise ValueError(f"stitching left {overlap:.3f} m2 of overlap between rooms; the gate "
                         f"requires zero and the placement search could not find room")
    merged = unary_union(list(polys.values()))
    outline = max(merged.geoms, key=lambda g: g.area) if merged.geom_type == "MultiPolygon" else merged
    ring = [(float(x), float(y)) for x, y in outline.exterior.coords[:-1]]
    if not SPoly(ring).exterior.is_ccw:
        ring = ring[::-1]
    log.info("stitched %d rooms onto %s, %.3f m2 overlap, %.2f m2 footprint",
             len(placed), connector, overlap, merged.area)
    return StitchResult(connector=connector, placed=placed, adjacency=adjacency, footprint=ring,
                        footprint_area_m2=float(merged.area), overlap_m2=float(overlap),
                        warnings=warnings)


def _nearest_edge(poly: SPoly, point: np.ndarray):
    def dist(e):
        a, b = e
        d = b - a
        t = np.clip(np.dot(point - a, d) / max(float(d @ d), 1e-9), 0, 1)
        return float(np.linalg.norm(a + t * d - point))

    return min(_edges(poly), key=dist)


def _longest_free_edge(poly: SPoly, occupied: SPoly):
    """The longest edge of the connector that nothing is already attached to."""
    from shapely.geometry import LineString

    best, best_len = None, -1.0
    for a, b in _edges(poly):
        seg = LineString([a, b])
        if seg.buffer(0.05).intersection(occupied.difference(poly)).area > 0.02:
            continue
        ln = float(np.linalg.norm(b - a))
        if ln > best_len:
            best, best_len = (a, b), ln
    return best if best is not None else _longest_edge(poly)
