"""Match predicted entities to ground truth before any error is computed.

Rooms match by id (the input convention makes the subfolder name the room id,
so a pipeline has no excuse to invent ids). Walls match by cyclic order: every
rotation of both lists and both directions are tried and the assignment with
the lowest total length error wins. Ground truth is listed clockwise from the
main-door wall and predictions are CCW, so the reversed direction is the
normal case. Openings match within a matched wall by nearest centre position
along the wall, inside a gate.

Nothing is dropped: every truth entity without a partner is "missed" (or
"unmatched"), every predicted entity without a partner is "phantom". Those
counts feed the gates directly, so a pipeline cannot improve its score by
predicting fewer things.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cozmo.contracts.models import Measurement, Opening, Plan, Room
from cozmo.io.ground_truth import GTOpening, GTRoom, GroundTruth

DEFAULT_OPENING_GATE_M = 0.5


@dataclass
class Assignment:
    pairs: list[tuple[int, int]]  # (pred index, truth index)
    reversed: bool
    rot_pred: int
    rot_truth: int
    total_error: float


def _candidate_assignments(pred_lengths: list[float], truth_lengths: list[float]):
    n_p, n_t = len(pred_lengths), len(truth_lengths)
    k = min(n_p, n_t)
    if k == 0:
        yield Assignment([], False, 0, 0, 0.0)
        return
    # Reversed first: the contract makes truth clockwise and predictions CCW,
    # so on a pure tie the reversed direction is the expected one.
    for rev in (True, False):
        seq = list(reversed(pred_lengths)) if rev else list(pred_lengths)
        idx = list(reversed(range(n_p))) if rev else list(range(n_p))
        for rp in range(n_p):
            for rt in range(n_t):
                pairs = []
                err = 0.0
                for i in range(k):
                    pi = (rp + i) % n_p
                    ti = (rt + i) % n_t
                    pairs.append((idx[pi], ti))
                    err += abs(seq[pi] - truth_lengths[ti])
                yield Assignment(pairs, rev, rp, rt, err)


def cyclic_wall_assignment(
    pred_lengths: list[float],
    truth_lengths: list[float],
    tie_break=None,
    tol: float = 1e-9,
) -> Assignment:
    """Best cyclic alignment of two wall lists by total absolute length error.

    When counts differ, a run of min(n_pred, n_truth) consecutive walls is
    aligned in each list and the rest are left unmatched. That handles an
    extra or missing wall at one place in the loop, which is the common case
    (a merged or split wall); scattered mismatches are reported as unmatched
    rather than guessed at.

    Symmetric rooms (a rectangle has two zero-error directions and two
    zero-error rotations) cannot be resolved by lengths alone. Among
    assignments within ``tol`` of the minimum error, ``tie_break(assignment)``
    picks the winner (lower is better); ``match_room`` uses opening positions
    for this. Without a tie breaker the first candidate wins, and candidates
    are generated reversed-first, so the result is deterministic.
    """
    cands = list(_candidate_assignments(pred_lengths, truth_lengths))
    best_err = min(c.total_error for c in cands)
    near = [c for c in cands if c.total_error <= best_err + tol]
    if tie_break is None or len(near) == 1:
        return near[0]
    return min(near, key=tie_break)


@dataclass
class WallPair:
    truth_id: str
    pred_id: str
    truth_length_m: float
    pred_length: Measurement


@dataclass
class OpeningPair:
    truth_id: str
    pred_id: str
    truth_wall_id: str
    truth: GTOpening
    pred: Opening
    centre_distance_m: float


@dataclass
class RoomMatch:
    room_id: str
    wall_pairs: list[WallPair] = field(default_factory=list)
    unmatched_truth_walls: list[str] = field(default_factory=list)
    unmatched_pred_walls: list[str] = field(default_factory=list)
    reversed: bool = False
    scored_walls: bool = True
    total_length_error_m: float = 0.0
    opening_pairs: list[OpeningPair] = field(default_factory=list)
    missed_openings: list[str] = field(default_factory=list)
    phantom_openings: list[str] = field(default_factory=list)


def _centre(offset: float, width: float) -> float:
    return offset + width / 2.0


def _match_openings(pred: Room, truth: GTRoom, a: Assignment, gate: float):
    """Greedy nearest-centre matching of openings on walls paired by ``a``.

    Centres are compared in the truth wall's direction. If the matched
    direction is reversed, a predicted centre c on a wall of length L sits at
    L - c in the truth frame. Returns (pairs, missed truth ids, phantom pred ids).
    """
    pred_to_truth = {pred.walls[pi].id: truth.walls[ti].id for pi, ti in a.pairs}
    pred_len = {w.id: w.length_m.value for w in pred.walls}
    truth_openings = {o.id: o for o in truth.openings}
    pred_openings = {o.id: o for o in pred.openings}
    candidates: list[tuple[float, str, str]] = []
    for po in pred.openings:
        tw_id = pred_to_truth.get(po.wall_id)
        if tw_id is None:
            continue
        c = _centre(po.offset_along_wall_m.value, po.width_m.value)
        if a.reversed:
            c = pred_len[po.wall_id] - c
        for to in truth.openings:
            if to.wall_id != tw_id:
                continue
            d = abs(c - _centre(to.offset_along_wall_m, to.width_m))
            if d <= gate:
                candidates.append((d, po.id, to.id))
    candidates.sort()
    used_p: set[str] = set()
    used_t: set[str] = set()
    pairs: list[OpeningPair] = []
    for d, pid, tid in candidates:
        if pid in used_p or tid in used_t:
            continue
        used_p.add(pid)
        used_t.add(tid)
        to = truth_openings[tid]
        pairs.append(OpeningPair(tid, pid, to.wall_id, to, pred_openings[pid], d))
    missed = [o.id for o in truth.openings if o.id not in used_t]
    phantom = [o.id for o in pred.openings if o.id not in used_p]
    return pairs, missed, phantom


def match_room(pred: Room, truth: GTRoom, opening_gate_m: float = DEFAULT_OPENING_GATE_M) -> RoomMatch:
    rm = RoomMatch(room_id=truth.id)
    if not truth.score_walls:
        # An open-plan room has no tape-measurable wall run. Its walls are not
        # scored at all, rather than scored against nothing, so openings still
        # count but wall lengths do not.
        rm.scored_walls = False
        rm.opening_pairs, rm.missed_openings, rm.phantom_openings = _match_openings(
            pred, truth, Assignment([], False, 0, 0, 0.0), opening_gate_m)
        rm.missed_openings = [o for o in rm.missed_openings
                              if not next(x.present_unmeasured for x in truth.openings if x.id == o)]
        return rm

    def tie_break(a: Assignment):
        pairs, _, _ = _match_openings(pred, truth, a, opening_gate_m)
        return (-len(pairs), sum(p.centre_distance_m for p in pairs), not a.reversed, a.rot_pred, a.rot_truth)

    a = cyclic_wall_assignment(
        [w.length_m.value for w in pred.walls], [w.length_m for w in truth.walls], tie_break=tie_break
    )
    rm.reversed = a.reversed
    rm.total_length_error_m = a.total_error
    for pi, ti in a.pairs:
        pw, tw = pred.walls[pi], truth.walls[ti]
        rm.wall_pairs.append(WallPair(tw.id, pw.id, tw.length_m, pw.length_m))
    matched_truth = {p.truth_id for p in rm.wall_pairs}
    matched_pred = {p.pred_id for p in rm.wall_pairs}
    rm.unmatched_truth_walls = [w.id for w in truth.walls if w.id not in matched_truth]
    rm.unmatched_pred_walls = [w.id for w in pred.walls if w.id not in matched_pred]
    rm.opening_pairs, rm.missed_openings, rm.phantom_openings = _match_openings(pred, truth, a, opening_gate_m)
    # A truth opening marked present_unmeasured cannot be missed: nobody
    # measured it, so its absence from the prediction proves nothing.
    unmeasured = {o.id for o in truth.openings if o.present_unmeasured}
    rm.missed_openings = [o for o in rm.missed_openings if o not in unmeasured]
    return rm


@dataclass
class MatchResult:
    rooms: list[RoomMatch] = field(default_factory=list)
    missing_rooms: list[str] = field(default_factory=list)
    phantom_rooms: list[str] = field(default_factory=list)
    # Openings and walls that live in unmatched rooms still count.
    missed_openings_in_missing_rooms: list[str] = field(default_factory=list)
    phantom_openings_in_phantom_rooms: list[str] = field(default_factory=list)
    unmatched_truth_walls_in_missing_rooms: int = 0
    unmatched_pred_walls_in_phantom_rooms: int = 0

    def all_opening_pairs(self) -> list[OpeningPair]:
        return [p for r in self.rooms for p in r.opening_pairs]

    def all_wall_pairs(self) -> list[tuple[str, WallPair]]:
        return [(r.room_id, p) for r in self.rooms for p in r.wall_pairs]

    def counts(self) -> dict[str, dict[str, int]]:
        matched_o = sum(len(r.opening_pairs) for r in self.rooms)
        missed_o = sum(len(r.missed_openings) for r in self.rooms) + len(self.missed_openings_in_missing_rooms)
        phantom_o = sum(len(r.phantom_openings) for r in self.rooms) + len(self.phantom_openings_in_phantom_rooms)
        matched_w = sum(len(r.wall_pairs) for r in self.rooms)
        un_t = sum(len(r.unmatched_truth_walls) for r in self.rooms) + self.unmatched_truth_walls_in_missing_rooms
        un_p = sum(len(r.unmatched_pred_walls) for r in self.rooms) + self.unmatched_pred_walls_in_phantom_rooms
        return {
            "rooms": {"matched": len(self.rooms), "missing": len(self.missing_rooms), "phantom": len(self.phantom_rooms)},
            "walls": {"matched": matched_w, "unmatched_truth": un_t, "unmatched_pred": un_p},
            "openings": {"matched": matched_o, "missed": missed_o, "phantom": phantom_o},
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "counts": self.counts(),
            "missing_rooms": self.missing_rooms,
            "phantom_rooms": self.phantom_rooms,
            "rooms": [
                {
                    "room_id": r.room_id,
                    "reversed": r.reversed,
                    "total_length_error_m": r.total_length_error_m,
                    "walls": [
                        {"truth_id": p.truth_id, "pred_id": p.pred_id, "truth_m": p.truth_length_m,
                         "pred": p.pred_length.model_dump(), "abs_error": abs(p.pred_length.value - p.truth_length_m)}
                        for p in r.wall_pairs
                    ],
                    "unmatched_truth_walls": r.unmatched_truth_walls,
                    "unmatched_pred_walls": r.unmatched_pred_walls,
                    "openings": [
                        {"truth_id": p.truth_id, "pred_id": p.pred_id, "wall_id": p.truth_wall_id,
                         "centre_distance_m": p.centre_distance_m,
                         "width_truth": p.truth.width_m, "width_pred": p.pred.width_m.model_dump(),
                         "width_abs_error": abs(p.pred.width_m.value - p.truth.width_m)}
                        for p in r.opening_pairs
                    ],
                    "missed_openings": r.missed_openings,
                    "phantom_openings": r.phantom_openings,
                }
                for r in self.rooms
            ],
        }


def match_plan(plan: Plan, truth: GroundTruth, cfg: dict[str, Any] | None = None) -> MatchResult:
    gate = float(((cfg or {}).get("matching") or {}).get("opening_offset_gate_m", DEFAULT_OPENING_GATE_M))
    res = MatchResult()
    pred_rooms = {r.id: r for r in plan.rooms}
    truth_ids = {r.id for r in truth.rooms}
    for tr in truth.rooms:
        pr = pred_rooms.get(tr.id)
        if pr is None:
            res.missing_rooms.append(tr.id)
            res.missed_openings_in_missing_rooms += [o.id for o in tr.openings if not o.present_unmeasured]
            res.unmatched_truth_walls_in_missing_rooms += len(tr.walls)
            continue
        res.rooms.append(match_room(pr, tr, gate))
    for pr in plan.rooms:
        if pr.id not in truth_ids:
            res.phantom_rooms.append(pr.id)
            res.phantom_openings_in_phantom_rooms += [o.id for o in pr.openings]
            res.unmatched_pred_walls_in_phantom_rooms += len(pr.walls)
    return res
