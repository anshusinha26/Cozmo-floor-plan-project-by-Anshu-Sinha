"""Stage 6 and 7: openings in wall faces, and the adjacency they create.

An opening is a gap in wall occupancy between 0.3 m and 1.9 m above the floor
that free space crosses: if the wall is missing there and you can walk or see
through, it is a door or a pass-through. Requiring free space on both sides is
what separates a doorway from a stretch of wall the scanner simply missed.

Height comes from the lintel: the lowest wall points directly above the gap.
Where nothing was seen above the gap, no height is claimed.

Windows are not attempted in this version. A warning says so rather than
letting a reader assume none were present.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage

from cozmo.lidar.cloud import Cloud
from cozmo.lidar.levels import Levels
from cozmo.lidar.rooms import RoomResult
from cozmo.lidar.walls import ManhattanFrame, WallFace

WINDOWS_NOT_ATTEMPTED = (
    "Windows are not detected in this version; openings are doors and pass-throughs only"
)


@dataclass
class Opening:
    face: WallFace
    a0: float
    a1: float
    centre_along: float
    width_m: float
    height_m: float | None
    type: str
    room_ids: list[str] = field(default_factory=list)
    n_lintel_points: int = 0

    @property
    def offset_along_wall_m(self) -> float:
        return self.a0 - self.face.extent()[0]


def _gaps(occupied: np.ndarray, bin_m: float, origin: float, min_w: float, max_w: float) -> list[tuple[float, float]]:
    """Runs of unoccupied bins between occupied ones, within the width band."""
    out = []
    n = len(occupied)
    i = 0
    while i < n:
        if occupied[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and not occupied[j + 1]:
            j += 1
        # A gap at either end of the face is the end of the wall, not an opening.
        if i > 0 and j < n - 1:
            w = (j - i + 1) * bin_m
            if min_w <= w <= max_w:
                out.append((origin + i * bin_m, origin + (j + 1) * bin_m))
        i = j + 1
    return out


def find_openings(cloud: Cloud, levels: Levels, frame: ManhattanFrame, faces: list[WallFace],
                  rooms: RoomResult, cfg: dict) -> list[Opening]:
    ocfg = cfg["opening"]
    bin_m = ocfg["bin_m"]
    grid = rooms.grid
    label_of = {r.id: i for i, r in enumerate(rooms.rooms)}
    room_label_img = np.zeros(grid.shape, dtype=np.int32)
    for i, r in enumerate(rooms.rooms, start=1):
        room_label_img[r.mask] = i
    # Dilate so a lookup just beside a wall still lands in the room.
    room_label_img = ndimage.grey_dilation(room_label_img, size=(9, 9))

    xz = frame.to_frame(cloud.points[:, [0, 2]])
    h = cloud.points[:, 1] - levels.floor.height_at(cloud.points[:, [0, 2]])
    band = (h >= ocfg["band_low_m"]) & (h <= ocfg["band_high_m"])

    out: list[Opening] = []
    for face in faces:
        if not face.is_structural(cfg["wall"]["wall_min_top_m"]):
            continue
        a_lo, a_hi = face.extent()
        if a_hi - a_lo < ocfg["min_width_m"] * 2:
            continue
        near = band & (np.abs(xz[:, face.axis] - face.pos) <= 0.10)
        along = xz[near, 1 - face.axis]
        n_bins = max(int(np.ceil((a_hi - a_lo) / bin_m)), 1)
        occ = np.zeros(n_bins, dtype=bool)
        idx = ((along - a_lo) / bin_m).astype(int)
        ok = (idx >= 0) & (idx < n_bins)
        occ[idx[ok]] = True
        for g0, g1 in _gaps(occ, bin_m, a_lo, ocfg["min_width_m"], ocfg["max_width_m"]):
            centre = (g0 + g1) / 2
            # Free space must exist on both sides, otherwise this is just a
            # stretch of wall the scanner never saw.
            probes = []
            for s in (-1.0, 1.0):
                pt = np.zeros(2)
                pt[face.axis] = face.pos + s * 0.35
                pt[1 - face.axis] = centre
                probes.append(pt)
            ij = grid.to_cell(np.array(probes))
            if not grid.inside(ij).all():
                continue
            labels = [int(room_label_img[i, j]) for i, j in ij]
            if any(l == 0 for l in labels):
                continue
            # Lintel: wall points directly above the gap give the opening height.
            above = (np.abs(xz[:, face.axis] - face.pos) <= 0.12) & (xz[:, 1 - face.axis] >= g0) & \
                    (xz[:, 1 - face.axis] <= g1) & (h > ocfg["band_high_m"])
            height = None
            n_lintel = int(above.sum())
            if n_lintel >= 20:
                height = float(np.percentile(h[above], 5))
            width = g1 - g0
            room_ids = []
            for l in labels:
                rid = rooms.rooms[l - 1].id
                if rid not in room_ids:
                    room_ids.append(rid)
            kind = "door" if (height is not None and height <= 2.3 and width <= 1.3) else "pass_through"
            out.append(Opening(face, g0, g1, centre, float(width), height, kind, room_ids, n_lintel))
    out.sort(key=lambda o: (o.face.axis, round(o.face.pos, 6), o.a0))
    return out


def adjacency_from_openings(openings: list[Opening]) -> list[tuple[str, str, str]]:
    """Undirected room pairs joined by an opening, one edge per pair (widest opening wins)."""
    best: dict[tuple[str, str], tuple[float, str]] = {}
    for i, o in enumerate(openings):
        if len(o.room_ids) != 2:
            continue
        key = tuple(sorted(o.room_ids))
        oid = f"opening_{i + 1:02d}"
        if key not in best or o.width_m > best[key][0]:
            best[key] = (o.width_m, oid)
    return [(a, b, oid) for (a, b), (_, oid) in sorted(best.items())]
