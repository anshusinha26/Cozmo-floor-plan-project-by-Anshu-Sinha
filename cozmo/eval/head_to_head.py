"""Compare our measurements against a rival app, both against tape.

The table answers one question per dimension: who is closer to the tape, and
by how much. A dimension is a tie when the two errors differ by less than the
tie threshold, because below that the difference is smaller than the tape's
own resolution and claiming a win would be noise.

Our column stays empty until a tier produces plans for these captures. An
empty column prints as "not yet", never as a zero.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from cozmo.contracts.models import Plan
from cozmo.io.ground_truth import load_ground_truth


@dataclass
class Row:
    room_id: str
    dimension: str
    walls: list[str]
    truth_m: float | None
    rival_m: float | None
    ours_m: float | None

    @property
    def rival_error(self) -> float | None:
        return abs(self.rival_m - self.truth_m) if self.rival_m is not None and self.truth_m is not None else None

    @property
    def our_error(self) -> float | None:
        return abs(self.ours_m - self.truth_m) if self.ours_m is not None and self.truth_m is not None else None

    def verdict(self, tie_threshold_m: float) -> str:
        if self.our_error is None or self.rival_error is None:
            return "not yet"
        diff = self.rival_error - self.our_error
        if abs(diff) < tie_threshold_m:
            return "tie"
        return "ours" if diff > 0 else "theirs"


def load_spec(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def truth_for(room_id: str, walls: list[str], gt_dir: Path, tier: str = "photo") -> float | None:
    """Mean tape length of the walls a rival dimension stands for.

    A rival that reports one number for two opposite walls is compared against
    the mean of those walls, which is the fairest reading of a single number.
    """
    path = gt_dir / f"own_{room_id}_{tier}.yaml"
    if not path.is_file():
        return None
    gt = load_ground_truth(path)
    try:
        room = gt.room(room_id)
    except KeyError:
        return None
    lengths = [w.length_m for w in room.walls if w.id in walls]
    return float(sum(lengths) / len(lengths)) if lengths else None


def ours_for(room_id: str, walls: list[str], plans: dict[str, Plan]) -> float | None:
    """Our mean wall length for the same walls, once a plan exists for the room."""
    plan = plans.get(room_id)
    if plan is None:
        return None
    for room in plan.rooms:
        if room.id != room_id:
            continue
        lengths = [w.length_m.value for w in room.walls if w.id in walls]
        if lengths:
            return float(sum(lengths) / len(lengths))
    return None


def build_rows(spec: dict[str, Any], gt_dir: Path, plans: dict[str, Plan] | None = None,
               tier: str = "photo") -> list[Row]:
    plans = plans or {}
    rows: list[Row] = []
    for room in spec.get("rooms", []):
        rid = room["room_id"]
        for dim in room.get("dimensions", []):
            walls = list(dim.get("maps_to_walls", []))
            rows.append(Row(
                room_id=rid, dimension=dim["name"], walls=walls,
                truth_m=truth_for(rid, walls, gt_dir, tier),
                rival_m=float(dim["value_m"]),
                ours_m=ours_for(rid, walls, plans),
            ))
    return rows


def summarize(rows: list[Row], tie_threshold_m: float) -> dict[str, Any]:
    verdicts = [r.verdict(tie_threshold_m) for r in rows]
    scored = [v for v in verdicts if v != "not yet"]
    beat_or_tie = sum(1 for v in scored if v in ("ours", "tie"))
    return {
        "n_dimensions": len(rows),
        "n_scored": len(scored),
        "ours": verdicts.count("ours"),
        "tie": verdicts.count("tie"),
        "theirs": verdicts.count("theirs"),
        "not_yet": verdicts.count("not yet"),
        "beat_or_tie_pct": (100.0 * beat_or_tie / len(scored)) if scored else None,
        "tie_threshold_m": tie_threshold_m,
    }


def _f(v: float | None, nd: int = 3) -> str:
    return "not yet" if v is None else f"{v:.{nd}f}"


def render_markdown(spec: dict[str, Any], rows: list[Row], summary: dict[str, Any]) -> str:
    rival = spec.get("rival", {})
    out = [f"# Head to head against {rival.get('name', 'the rival app')}", "",
           f"{rival.get('name')} by {rival.get('vendor')} on {rival.get('platform')}. "
           f"Protocol: {rival.get('protocol')}.", "",
           "Every dimension is compared against the tape reading, which is the "
           "only thing either side can be right or wrong about. A tie means the "
           f"two errors differ by less than {summary['tie_threshold_m'] * 100:.1f} cm.", ""]
    for entry in spec.get("not_compared", []):
        out += [f"Not compared: {entry['name']}. {entry['reason'].strip()}", ""]
    out += ["| room | dimension | walls | tape m | theirs m | their error m | ours m | our error m | closer |",
            "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        out.append(f"| {r.room_id} | {r.dimension} | {', '.join(r.walls)} | {_f(r.truth_m)} | "
                   f"{_f(r.rival_m)} | {_f(r.rival_error)} | {_f(r.ours_m)} | {_f(r.our_error)} | "
                   f"{r.verdict(summary['tie_threshold_m'])} |")
    out += [""]
    if summary["n_scored"]:
        out += [f"Beat or tie: {summary['beat_or_tie_pct']:.0f}% of {summary['n_scored']} scored dimensions "
                f"(ours {summary['ours']}, tie {summary['tie']}, theirs {summary['theirs']})."]
    else:
        out += ["Our column is empty: no tier has produced plans for these rooms yet. "
                "The rival's own errors against tape are in the table and stand on their own."]
        errs = [r.rival_error for r in rows if r.rival_error is not None]
        if errs:
            out += ["", f"Their error against tape: median {sorted(errs)[len(errs) // 2] * 100:.1f} cm, "
                        f"worst {max(errs) * 100:.1f} cm over {len(errs)} dimensions."]
    return "\n".join(out) + "\n"
