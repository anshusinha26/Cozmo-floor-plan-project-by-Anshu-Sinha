#!/usr/bin/env python
"""Summarise video-tier runs, and score the own-capture rooms against tape.

    scripts/video_tier_report.py runs/video/*

Two tables. The first is what the tier did per clip: coverage, chunks, bridges,
scale, runtime, plan summary. The second compares predicted wall lengths with
tape measurements taken to the nearest inch, so the tape itself is good to about
plus or minus 1.3 cm.

The tape numbers below are a QUICK SANITY CHECK held in this script on purpose.
The real ground-truth files, in the schema `cozmo eval` reads, come from
elsewhere; when they land, this script should be deleted in favour of
`cozmo eval`. The hall is open plan and irregular, so only its ceiling is scored.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

TAPE_CM = {
    "bedroom_1": {"walls": [365.76, 391.16], "door_wall": 365.76, "ceiling": 297.18,
                  "door_width": 91.44, "door_height": 198.12},
    "bedroom_2": {"walls": [388.62, 363.22], "door_wall": 388.62, "ceiling": 297.18,
                  "door_width": 91.44, "door_height": 198.12},
    "bedroom_2_repeat": {"walls": [388.62, 363.22], "door_wall": 388.62, "ceiling": 297.18,
                         "door_width": 91.44, "door_height": 198.12},
    "kitchen": {"walls": [269.24, 360.28], "door_wall": 269.24, "ceiling": 297.18,
                "door_width": 81.28, "door_height": 198.12},
    "hall": {"walls": None, "ceiling": 297.18},   # irregular open plan: walls not scored
}
TAPE_PRECISION_CM = 1.3
WALL_GATE = 0.03          # the video tier's wall length budget, config/gates.yaml


def load(run: Path) -> dict | None:
    plan_p, man_p = run / "plan.json", run / "run_manifest.json"
    if not plan_p.exists():
        return None
    out = {"name": run.name, "dir": run, "plan": json.loads(plan_p.read_text())}
    out["manifest"] = json.loads(man_p.read_text()) if man_p.exists() else {}
    vr = run / "debug" / "video_report.json"
    out["video"] = json.loads(vr.read_text()) if vr.exists() else {}
    return out


def room_axis_lengths(room: dict) -> list[dict]:
    """The two distinct wall lengths of a rectilinear room, longest first.

    Walls come in opposite pairs, so the two lengths are what a tape measures.
    Each carries the widest interval of the walls that formed it.
    """
    walls = room["walls"]
    if not walls:
        return []
    out = []
    for w in walls:
        m = w["length_m"]
        out.append({"id": w["id"], "value": m["value"] * 100,
                    "lo": m["ci_low"] * 100, "hi": m["ci_high"] * 100})
    groups: list[list[dict]] = []
    for w in sorted(out, key=lambda x: -x["value"]):
        for g in groups:
            if abs(g[0]["value"] - w["value"]) <= max(0.12 * g[0]["value"], 10.0):
                g.append(w)
                break
        else:
            groups.append([w])
    merged = []
    for g in groups:
        merged.append({"ids": "+".join(x["id"] for x in g),
                       "value": sum(x["value"] for x in g) / len(g),
                       "lo": min(x["lo"] for x in g), "hi": max(x["hi"] for x in g)})
    return sorted(merged, key=lambda x: -x["value"])


def biggest_room(plan: dict) -> dict | None:
    rooms = plan.get("rooms") or []
    return max(rooms, key=lambda r: r["floor_area_m2"]["value"]) if rooms else None


def per_clip_table(runs: list[dict]) -> str:
    cols = ["clip", "share of video", "chunks kept", "group", "bridges ok/rejected",
            "scale m per SfM unit", "runtime s", "rooms", "walls", "openings",
            "footprint m2", "plan.png"]
    rows = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in runs:
        v = r.get("video", {})
        cov, br, sfm = v.get("coverage", {}), v.get("bridge", {}), v.get("sfm", {})
        group = br.get("group") or []
        scales = ", ".join(f"{s['scale_m_per_unit']:.4f}" for s in v.get("scale", [])
                           if s["chunk"] in group) or "-"
        plan = r["plan"]
        dur = r.get("manifest", {}).get("duration_s")
        fp = (plan.get("stitched_plan") or {}).get("footprint_area_m2", {}).get("value")
        cells = [
            r["name"],
            f"{cov.get('share_of_video', 0):.0%}" if cov else "?",
            str(sfm.get("chunks_kept", "?")),
            str(len(group)),
            f"{br.get('n_accepted', '?')}/{br.get('n_rejected', '?')}",
            scales,
            f"{dur:.0f}" if dur is not None else "?",
            str(len(plan["rooms"])),
            str(sum(len(x["walls"]) for x in plan["rooms"])),
            str(sum(len(x["openings"]) for x in plan["rooms"])),
            f"{fp:.2f}" if fp is not None else "-",
            str(r["dir"] / "plan.png"),
        ]
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join(rows)


def tape_table(runs: list[dict]) -> str:
    head = ("| room | quantity | tape cm | predicted cm | error cm | error % | in interval | within 3% |")
    rows = [head, "|---" * 8 + "|"]
    for r in runs:
        tape = TAPE_CM.get(r["name"])
        if tape is None:
            continue
        room = biggest_room(r["plan"])
        if room is None:
            rows.append(f"| {r['name']} | - | - | no room reconstructed | - | - | - | - |")
            continue
        ch = room["ceiling_height_m"]
        rows.append(_row(r["name"], "ceiling", tape["ceiling"], ch["value"] * 100,
                         ch["ci_low"] * 100, ch["ci_high"] * 100))
        if not tape.get("walls"):
            rows.append(f"| {r['name']} | walls | not scored | irregular open plan | - | - | - | - |")
            continue
        pred = room_axis_lengths(room)
        # Pair each tape length with its closest unused prediction.
        free = list(range(len(pred)))
        for t in tape["walls"]:
            if not free:
                rows.append(f"| {r['name']} | wall {t:.1f} | {t:.1f} | no matching wall | - | - | no | no |")
                continue
            k = min(free, key=lambda i: abs(pred[i]["value"] - t))
            free.remove(k)
            label = "wall (door)" if t == tape.get("door_wall") else "wall"
            rows.append(_row(r["name"], f"{label} {pred[k]['ids']}", t, pred[k]["value"],
                             pred[k]["lo"], pred[k]["hi"]))
        for o in room["openings"]:
            if o["type"] != "door":
                continue
            w = o["width_m"]
            rows.append(_row(r["name"], f"door {o['id']} width", tape["door_width"],
                             w["value"] * 100, w["ci_low"] * 100, w["ci_high"] * 100))
    return "\n".join(rows)


def _row(room: str, what: str, tape: float, value: float, lo: float, hi: float) -> str:
    err = value - tape
    pct = 100 * err / tape
    inside = lo - TAPE_PRECISION_CM <= tape <= hi + TAPE_PRECISION_CM
    gate = abs(pct) <= WALL_GATE * 100
    return (f"| {room} | {what} | {tape:.1f} | {value:.1f} [{lo:.1f}, {hi:.1f}] | {err:+.1f} "
            f"| {pct:+.1f}% | {'yes' if inside else 'NO'} | {'PASS' if gate else 'FAIL'} |")


def repeat_table(runs: list[dict]) -> str:
    by = {r["name"]: r for r in runs}
    a, b = by.get("bedroom_2"), by.get("bedroom_2_repeat")
    if not a or not b:
        return "bedroom_2 and bedroom_2_repeat were not both run, so there is no agreement to report."
    ra, rb = biggest_room(a["plan"]), biggest_room(b["plan"])
    if ra is None or rb is None:
        return "One of the bedroom_2 runs produced no room, so there is no agreement to report."
    pa, pb = room_axis_lengths(ra), room_axis_lengths(rb)
    rows = ["| wall | bedroom_2 cm | bedroom_2_repeat cm | difference cm | difference % |",
            "|---|---|---|---|---|"]
    for i in range(min(len(pa), len(pb))):
        d = pb[i]["value"] - pa[i]["value"]
        rows.append(f"| {i + 1} (longest first) | {pa[i]['value']:.1f} | {pb[i]['value']:.1f} "
                    f"| {d:+.1f} | {100 * d / pa[i]['value']:+.1f}% |")
    return "\n".join(rows)


def main(argv: list[str]) -> int:
    dirs = [Path(a) for a in argv[1:]] or sorted(Path("runs/video").glob("*"))
    runs = [r for r in (load(d) for d in dirs if d.is_dir()) if r]
    if not runs:
        print("no runs with a plan.json found", file=sys.stderr)
        return 1
    print("## Per clip\n")
    print(per_clip_table(runs))
    print("\n## Predicted against tape\n")
    print(f"Tape is measured to the nearest inch, so it is good to about "
          f"plus or minus {TAPE_PRECISION_CM} cm. The video tier's wall gate is "
          f"{WALL_GATE:.0%}.\n")
    print(tape_table(runs))
    print("\n## bedroom_2 against bedroom_2_repeat\n")
    print(repeat_table(runs))
    print("\n## Warnings\n")
    for r in runs:
        ws = r["plan"].get("warnings") or []
        print(f"### {r['name']} ({len(ws)})")
        for w in ws:
            print(f"- {w}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
