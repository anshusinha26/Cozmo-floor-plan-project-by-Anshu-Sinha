"""Fit one rectilinear room around the camera path, without segmenting.

Fix loop 2. Room segmentation assumes the floor was observed widely enough to
carve free space out of it. The video tier does not earn that: it reconstructs
part of a floor from part of a capture, so segmentation either returns nothing
(two of six clips in loop 1) or returns a fragment of the room and presents it
as the whole (a 1.19 m strip standing in for a 3.91 m wall).

A per-room clip has one room in it by construction, and the person walked around
inside it. So the room is the smallest rectilinear shape that contains the whole
camera path and reaches out to the wall faces on each side. A side with a
supported wall face takes its position from that face. A side with none is
closed by the rectangle assumption, flagged, and its interval widened.

This never returns nothing. The worst case is a rectangle around the camera path
with every side flagged as assumed, which is still an honest statement: this is
where the person walked, and the walls are at least this far out.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

from cozmo.lidar.rooms import Grid, Room, RoomResult
from cozmo.lidar.walls import WallFace

log = logging.getLogger(__name__)

MAX_HALF_EXTENT_M = 8.0     # a face further than this from the path is not this room's wall
MIN_SPAN_OVERLAP = 0.25     # a face must run along this share of the path's span to count
MIN_STEP_M = 0.6            # an L step smaller than this is wall thickness, not a step


@dataclass
class Side:
    """One of the four sides of the fitted room, in the Manhattan frame."""

    axis: int          # 0: the face's normal is along x, so the side runs along z
    direction: int     # -1 for the low side, +1 for the high side
    pos: float
    supported: bool
    face_length_m: float = 0.0
    n_points: int = 0
    margin_used_m: float = 0.0

    def summary(self) -> dict:
        return {"axis": self.axis, "direction": self.direction, "pos": round(self.pos, 3),
                "supported": self.supported, "face_length_m": round(self.face_length_m, 3),
                "n_points": self.n_points}


@dataclass
class SingleRoomFit:
    polygon_frame: list[tuple[float, float]]
    sides: list[Side]
    shape: str
    warnings: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)

    @property
    def n_supported(self) -> int:
        return sum(1 for s in self.sides if s.supported)

    @property
    def area_m2(self) -> float:
        p = np.array(self.polygon_frame)
        x, y = p[:, 0], p[:, 1]
        return float(abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2)

    def summary(self) -> dict:
        return {"shape": self.shape, "n_supported_sides": self.n_supported,
                "area_m2": round(self.area_m2, 3),
                "sides": [s.summary() for s in self.sides]}


def _span(path: np.ndarray, axis: int) -> tuple[float, float]:
    return float(path[:, axis].min()), float(path[:, axis].max())


def _candidates(faces: list[WallFace], axis: int, direction: int, lo: float, hi: float,
                other_lo: float, other_hi: float, cfg: dict) -> list[WallFace]:
    """Structural faces on one side of the path that run along enough of it."""
    min_top = cfg["room"]["wall_min_top_m"]
    other_span = max(other_hi - other_lo, 1e-6)
    out = []
    for f in faces:
        if f.axis != axis or not f.is_structural(min_top):
            continue
        if direction < 0 and f.pos > lo:
            continue
        if direction > 0 and f.pos < hi:
            continue
        if abs(f.pos - (lo if direction < 0 else hi)) > MAX_HALF_EXTENT_M:
            continue
        a, b = f.extent()
        overlap = max(0.0, min(b, other_hi) - max(a, other_lo))
        if overlap / other_span < MIN_SPAN_OVERLAP:
            continue
        out.append(f)
    return out


def _pick_side(faces: list[WallFace], axis: int, direction: int, path: np.ndarray,
               cfg: dict, margin_m: float) -> Side:
    lo, hi = _span(path, axis)
    other_lo, other_hi = _span(path, 1 - axis)
    cands = _candidates(faces, axis, direction, lo, hi, other_lo, other_hi, cfg)
    if cands:
        # Outermost: the wall is the furthest supported face, not the nearest,
        # because furniture and half-height returns sit between the path and it.
        f = min(cands, key=lambda f: f.pos) if direction < 0 else max(cands, key=lambda f: f.pos)
        return Side(axis, direction, float(f.pos), True, f.length(), f.n_points)
    pos = (lo - margin_m) if direction < 0 else (hi + margin_m)
    return Side(axis, direction, float(pos), False, margin_used_m=margin_m)


def _l_step(faces: list[WallFace], axis: int, direction: int, path: np.ndarray,
            cfg: dict) -> tuple[WallFace, WallFace] | None:
    """Two supported faces on one side, at different depths, covering different stretches.

    That is what an L-shaped room looks like from inside: the wall steps. It has
    to be unambiguous, because a wrongly detected step invents a corner.
    """
    lo, hi = _span(path, axis)
    other_lo, other_hi = _span(path, 1 - axis)
    cands = _candidates(faces, axis, direction, lo, hi, other_lo, other_hi, cfg)
    if len(cands) < 2:
        return None
    cands = sorted(cands, key=lambda f: f.pos, reverse=direction < 0)
    outer = cands[0]
    span = max(other_hi - other_lo, 1e-6)
    for inner in cands[1:]:
        if abs(inner.pos - outer.pos) < MIN_STEP_M:
            continue
        oa, ob = outer.extent()
        ia, ib = inner.extent()
        if max(0.0, min(ob, ib) - max(oa, ia)) / span > 0.2:
            continue                      # they overlap along the wall: not a step
        if outer.length() / span < 0.3 or inner.length() / span < 0.3:
            continue
        return outer, inner
    return None


def fit_single_room(faces: list[WallFace], path_frame: np.ndarray, cfg: dict,
                    margin_m: float = 0.35, allow_l: bool = True) -> SingleRoomFit:
    """The room around this camera path, as a rectangle or a clearly supported L."""
    if len(path_frame) == 0:
        raise ValueError("single-room fitting needs a camera path")
    sides = [_pick_side(faces, axis, d, path_frame, cfg, margin_m)
             for axis in (0, 1) for d in (-1, 1)]
    by = {(s.axis, s.direction): s for s in sides}
    x0, x1 = by[(0, -1)].pos, by[(0, 1)].pos
    z0, z1 = by[(1, -1)].pos, by[(1, 1)].pos
    if x1 - x0 < 0.5 or z1 - z0 < 0.5:
        raise ValueError(f"fitted room is degenerate: {x1 - x0:.2f} by {z1 - z0:.2f} m")

    warnings: list[str] = []
    assumptions: list[str] = []
    shape = "rectangle"
    polygon = [(x0, z0), (x1, z0), (x1, z1), (x0, z1)]

    if allow_l:
        for axis in (0, 1):
            for d in (-1, 1):
                step = _l_step(faces, axis, d, path_frame, cfg)
                if step is None:
                    continue
                polygon = _l_polygon(x0, x1, z0, z1, axis, d, step, path_frame)
                if polygon is not None:
                    shape = "l_shape"
                    assumptions.append(
                        "One side of this room steps: two supported wall faces at different "
                        "depths cover different stretches of it, so it is fitted as an L rather "
                        "than a rectangle")
                    break
            if shape == "l_shape":
                break
        if shape != "l_shape":
            polygon = [(x0, z0), (x1, z0), (x1, z1), (x0, z1)]

    unsupported = [s for s in sides if not s.supported]
    if unsupported:
        names = ", ".join(_side_name(s) for s in unsupported)
        warnings.append(
            f"{len(unsupported)} of 4 room sides had no supported wall face ({names}); they are "
            f"closed at the camera path plus {margin_m:.2f} m by the rectangle assumption and the "
            f"room is only partially observed")
        assumptions.append(
            "Single-room fitting: the clip covers one room, so the room is the smallest "
            "rectilinear shape containing the whole camera path out to the wall faces found on "
            "each side. Sides with no face are closed by that assumption, not measured")
    log.info("single room: %s, %.2f by %.2f m, %d of 4 sides supported",
             shape, x1 - x0, z1 - z0, 4 - len(unsupported))
    return SingleRoomFit(polygon, sides, shape, warnings, assumptions)


def _side_name(s: Side) -> str:
    return f"{'x' if s.axis == 0 else 'z'}{'-' if s.direction < 0 else '+'}"


def _l_polygon(x0: float, x1: float, z0: float, z1: float, axis: int, direction: int,
               step, path: np.ndarray) -> list[tuple[float, float]] | None:
    """Rectangle with one corner cut back to the inner face of a stepped side."""
    outer, inner = step
    oa, ob = outer.extent()
    ia, ib = inner.extent()
    if axis == 0:
        x_out = outer.pos
        x_in = inner.pos
        cut_lo, cut_hi = (max(z0, ia), min(z1, ib))
        if cut_hi - cut_lo < MIN_STEP_M:
            return None
        lo_end = abs(cut_lo - z0) < abs(z1 - cut_hi)
        if direction < 0:
            return ([(x_in, z0), (x1, z0), (x1, z1), (x_out, z1), (x_out, cut_lo), (x_in, cut_lo)]
                    if not lo_end else
                    [(x_out, z0), (x1, z0), (x1, z1), (x_in, z1), (x_in, cut_hi), (x_out, cut_hi)])
        return ([(x0, z0), (x_in, z0), (x_in, cut_lo), (x_out, cut_lo), (x_out, z1), (x0, z1)]
                if not lo_end else
                [(x0, z0), (x_out, z0), (x_out, cut_hi), (x_in, cut_hi), (x_in, z1), (x0, z1)])
    # Mirror image for a step on a z-normal side.
    flipped = _l_polygon(z0, z1, x0, x1, 0, direction, step, path[:, ::-1])
    return None if flipped is None else [(b, a) for a, b in flipped]


def _perimeter_support(fit: SingleRoomFit) -> float:
    """Share of the outline's length that lies on an observed wall face.

    A side with no face is closed at the camera path plus a margin, which is a
    guess, not a measurement. Reporting the share that is not a guess is what
    lets the plan builder widen those intervals and lets the renderer draw the
    guessed sides differently. The fit's warning text reaches none of them.
    """
    poly = np.asarray(fit.polygon_frame, dtype=float)
    backed_positions = [(s.axis, s.pos) for s in fit.sides if s.supported]
    total = backed = 0.0
    for a, b in zip(poly, np.roll(poly, -1, axis=0)):
        length = float(np.hypot(b[0] - a[0], b[1] - a[1]))
        if length < 1e-9:
            continue
        total += length
        # An edge running along z holds x constant, so its face normal is x: axis 0.
        axis = 0 if abs(b[0] - a[0]) < abs(b[1] - a[1]) else 1
        if any(ax == axis and abs(pos - float(a[axis])) < 1e-6 for ax, pos in backed_positions):
            backed += length
    return float(backed / total) if total else 1.0


def as_room_result(fit: SingleRoomFit, frame, cell_m: float = 0.03, room_id: str = "room_01",
                   label: str = "room") -> RoomResult:
    """Wrap the fit in the structure the plan backend expects."""
    from matplotlib.path import Path as MplPath

    poly = np.array(fit.polygon_frame, dtype=np.float64)
    lo = poly.min(axis=0) - 0.3
    hi = poly.max(axis=0) + 0.3
    shape = (max(1, int(np.ceil((hi[0] - lo[0]) / cell_m))),
             max(1, int(np.ceil((hi[1] - lo[1]) / cell_m))))
    grid = Grid(origin=lo, cell=cell_m, shape=shape)
    ii, jj = np.meshgrid(np.arange(shape[0]), np.arange(shape[1]), indexing="ij")
    centres = grid.to_world(np.stack([ii.ravel(), jj.ravel()], axis=1))
    mask = MplPath(poly).contains_points(centres).reshape(shape)

    world = [tuple(p) for p in frame.to_world(poly)]
    support = _perimeter_support(fit)
    room = Room(id=room_id, label=label, kind="room", polygon_frame=[tuple(p) for p in poly],
                polygon_world=world, area_m2=fit.area_m2, mask=mask,
                partially_observed=fit.n_supported < len(fit.sides),
                perimeter_support=support)
    return RoomResult(rooms=[room], grid=grid, free=mask, occupied=~mask,
                      labels=mask.astype(np.int32), warnings=list(fit.warnings))
