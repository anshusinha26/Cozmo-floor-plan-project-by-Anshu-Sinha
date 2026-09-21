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
    """One of the four sides of the fitted room, in the Manhattan frame.

    ``support`` is how the position was arrived at: a wall face that passed the
    strict test, a dense band of points that did not, or nothing at all.
    """

    axis: int          # 0: the face's normal is along x, so the side runs along z
    direction: int     # -1 for the low side, +1 for the high side
    pos: float
    supported: bool
    face_length_m: float = 0.0
    n_points: int = 0
    margin_used_m: float = 0.0
    support: str = "face"          # face | density | camera_path

    @property
    def weak(self) -> bool:
        return self.support == "density"

    def summary(self) -> dict:
        return {"axis": self.axis, "direction": self.direction, "pos": round(self.pos, 3),
                "supported": self.supported, "support": self.support,
                "face_length_m": round(self.face_length_m, 3), "n_points": self.n_points}


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
    def n_weak(self) -> int:
        return sum(1 for s in self.sides if s.weak)

    @property
    def unsupported_weight(self) -> float:
        """How much of the room is assumed rather than measured.

        A side found by density is real evidence but weaker than a wall face, so
        it counts half. A side closed at the camera path counts whole.
        """
        return sum(0.0 if s.support == "face" else 0.5 if s.weak else 1.0 for s in self.sides)

    @property
    def area_m2(self) -> float:
        p = np.array(self.polygon_frame)
        x, y = p[:, 0], p[:, 1]
        return float(abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2)

    def summary(self) -> dict:
        return {"shape": self.shape, "n_supported_sides": self.n_supported,
                "n_weakly_supported": self.n_weak,
                "unsupported_weight": round(self.unsupported_weight, 2),
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


def density_side(wall_xz: np.ndarray, axis: int, direction: int, path: np.ndarray,
                 cfg: dict) -> tuple[float, int] | None:
    """The outermost dense band of points beyond the camera path on this side.

    Fix loop 3. The strict face test wants a plane that is long enough, tall
    enough and flat enough. A wall behind a curtain, a run of window, or a
    wardrobe front fails all three while still leaving a dense sheet of points
    exactly where the wall is. This looks for that sheet.

    Outermost among the *significant* peaks, not outermost overall: a handful of
    points leaking through a doorway or a reflection must not become a wall,
    which is the mistake the strict path already makes from the other direction.

    The search starts a little **inside** the camera path, not at it. The path is
    not a reliable inner bound: on bedroom_2 it runs 0.61 m past the room's own
    wall, because a reconstruction that is imperfect along one axis carries the
    cameras out with it. Requiring the wall to lie beyond the path found nothing
    at all on the first attempt, for exactly that reason.
    """
    if wall_xz is None or len(wall_xz) == 0:
        return None
    rcfg = cfg["room"]
    bin_m = float(rcfg.get("density_bin_m", 0.06))
    min_points = int(rcfg.get("density_min_points", 120))
    min_share = float(rcfg.get("density_min_share", 0.35))
    max_reach = float(rcfg.get("density_max_reach_m", 2.5))
    inward = float(rcfg.get("density_inward_m", 1.0))

    lo, hi = _span(path, axis)
    other_lo, other_hi = _span(path, 1 - axis)
    span = max(other_hi - other_lo, 1e-6)
    along = wall_xz[:, 1 - axis]
    pos = wall_xz[:, axis]
    # Same room: the points have to run along the stretch the camera path covers.
    near = (along >= other_lo - 0.5 * span) & (along <= other_hi + 0.5 * span)
    if direction < 0:
        sel = near & (pos <= lo + inward) & (pos >= lo - max_reach)
    else:
        sel = near & (pos >= hi - inward) & (pos <= hi + max_reach)
    vals = pos[sel]
    if len(vals) < min_points:
        return None
    edges = np.arange(vals.min() - bin_m, vals.max() + 2 * bin_m, bin_m)
    counts, edges = np.histogram(vals, bins=edges)
    if not counts.size or counts.max() < min_points:
        return None
    strong = np.nonzero(counts >= max(min_points, min_share * counts.max()))[0]
    if not strong.size:
        return None
    k = int(strong[0] if direction < 0 else strong[-1])
    centre = float((edges[k] + edges[k + 1]) / 2)
    band = np.abs(vals - centre) <= 1.5 * bin_m
    if band.sum() < min_points:
        return None
    return float(np.median(vals[band])), int(band.sum())


def _pick_side(faces: list[WallFace], axis: int, direction: int, path: np.ndarray,
               cfg: dict, margin_m: float, wall_xz: np.ndarray | None = None) -> Side:
    lo, hi = _span(path, axis)
    other_lo, other_hi = _span(path, 1 - axis)
    cands = _candidates(faces, axis, direction, lo, hi, other_lo, other_hi, cfg)
    if cands:
        # Outermost: the wall is the furthest supported face, not the nearest,
        # because furniture and half-height returns sit between the path and it.
        f = min(cands, key=lambda f: f.pos) if direction < 0 else max(cands, key=lambda f: f.pos)
        return Side(axis, direction, float(f.pos), True, f.length(), f.n_points, support="face")

    found = density_side(wall_xz, axis, direction, path, cfg)
    if found is not None:
        pos, n = found
        fallback = (lo - margin_m) if direction < 0 else (hi + margin_m)
        # A peak further out than the fallback would be worse than not looking,
        # which is one of the declared falsifiers for this change.
        outside = pos < fallback if direction < 0 else pos > fallback
        if not outside:
            return Side(axis, direction, pos, True, 0.0, n, support="density")

    # Nothing to anchor to. The room is closed a short step beyond where the
    # photographer stood, because a person backs away from the wall they are
    # photographing and the path is therefore always inside the room.
    pos = (lo - margin_m) if direction < 0 else (hi + margin_m)
    return Side(axis, direction, float(pos), False, margin_used_m=margin_m, support="camera_path")


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
                    margin_m: float = 0.35, allow_l: bool = True,
                    wall_xz: np.ndarray | None = None) -> SingleRoomFit:
    """The room around this camera path, as a rectangle or a clearly supported L."""
    if len(path_frame) == 0:
        raise ValueError("single-room fitting needs a camera path")
    sides = [_pick_side(faces, axis, d, path_frame, cfg, margin_m, wall_xz)
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

    weak = [s for s in sides if s.weak]
    if weak:
        names = ", ".join(_side_name(s) for s in weak)
        warnings.append(
            f"{len(weak)} of 4 room sides ({names}) are set by a dense band of points rather "
            f"than by a wall face that passed the strict test, which is what a wall behind a "
            f"curtain or a wardrobe looks like. Their intervals are widened")
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
    log.info("single room: %s, %.2f by %.2f m, %d of 4 sides on a face, %d on point density, "
             "%d closed at the camera path", shape, x1 - x0, z1 - z0,
             sum(1 for s in sides if s.support == "face"), len(weak), len(unsupported))
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
    room = Room(id=room_id, label=label, kind="room", polygon_frame=[tuple(p) for p in poly],
                polygon_world=world, area_m2=fit.area_m2, mask=mask)
    return RoomResult(rooms=[room], grid=grid, free=mask, occupied=~mask,
                      labels=mask.astype(np.int32), warnings=list(fit.warnings))
