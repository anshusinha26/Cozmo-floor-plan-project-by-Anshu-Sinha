#!/usr/bin/env python
"""Score a photo-tier property run against tape.

    scripts/photo_tier_report.py runs/photo/own

Tape is measured to the nearest inch, so it is good to about plus or minus
1.3 cm. The gate at this tier is 8%. Repeat rooms are measured and reported but
are not in the property, so they are scored from the run report rather than the
plan. The two bedroom_2 captures are on different phones, so their agreement is
a cross-device check, not a repeatability check on one device.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

TAPE_CM = {
    "bedroom_1": {"walls": [365.76, 391.16], "door_wall": 365.76, "ceiling": 297.18,
                  "door_width": 91.44},
    "bedroom_2": {"walls": [388.62, 363.22], "door_wall": 388.62, "ceiling": 297.18,
                  "door_width": 91.44},
    "bedroom_2_repeat": {"walls": [388.62, 363.22], "door_wall": 388.62, "ceiling": 297.18,
                         "door_width": 91.44},
    "kitchen": {"walls": [269.24, 360.28], "door_wall": 269.24, "ceiling": 297.18,
                "door_width": 81.28},
    "hall": {"walls": None, "ceiling": 297.18},
}
TRUTH_ADJACENCY = {("hall", "bedroom_1"), ("hall", "bedroom_2"), ("hall", "kitchen")}
TAPE_PRECISION_CM = 1.3
GATE = 0.08


def _pair(tape: list[float], pred: list[float]) -> list[tuple[float, float | None]]:
    free = list(range(len(pred)))
    out = []
    for t in tape:
        if not free:
            out.append((t, None))
            continue
        k = min(free, key=lambda i: abs(pred[i] - t))
        free.remove(k)
        out.append((t, pred[k]))
    return out


def _row(room, what, tape, value, lo, hi):
    err = value - tape
    pct = 100 * err / tape
    inside = lo - TAPE_PRECISION_CM <= tape <= hi + TAPE_PRECISION_CM
    return (f"| {room} | {what} | {tape:.1f} | {value:.1f} [{lo:.1f}, {hi:.1f}] | {err:+.1f} "
            f"| {pct:+.1f}% | {'yes' if inside else 'NO'} | "
            f"{'PASS' if abs(pct) <= GATE * 100 else 'FAIL'} |"), abs(pct) <= GATE * 100, inside


def main(argv: list[str]) -> int:
    run = Path(argv[1]) if len(argv) > 1 else Path("runs/photo/own")
    plan = json.loads((run / "plan.json").read_text())
    report_path = run / "debug" / "photo_report.json"
    report = json.loads(report_path.read_text()) if report_path.is_file() else {}

    walls_cm: dict[str, list[float]] = {}
    ci: dict[str, list[tuple[float, float]]] = {}
    ceilings: dict[str, tuple[float, float, float]] = {}
    for r in plan["rooms"]:
        lengths = sorted({round(w["length_m"]["value"] * 100, 1) for w in r["walls"]}, reverse=True)
        walls_cm[r["id"]] = lengths
        ci[r["id"]] = [(w["length_m"]["ci_low"] * 100, w["length_m"]["ci_high"] * 100)
                       for w in r["walls"]]
        c = r["ceiling_height_m"]
        ceilings[r["id"]] = (c["value"] * 100, c["ci_low"] * 100, c["ci_high"] * 100)
    for rid, meas in (report.get("repeat_measurements") or {}).items():
        walls = meas["walls_m"]
        walls_cm[rid] = [round(w["value"] * 100, 1) for w in walls]
        ci[rid] = [(w["ci_low"] * 100, w["ci_high"] * 100) for w in walls]
        c = meas["ceiling_m"]
        ceilings[rid] = (c["value"] * 100, c["ci_low"] * 100, c["ci_high"] * 100)

    print("## Photo tier against tape\n")
    print(f"Gate {GATE:.0%}. Tape good to about plus or minus {TAPE_PRECISION_CM} cm.\n")
    print("| room | quantity | tape cm | predicted cm | error cm | error % | in interval | within 8% |")
    print("|---|---|---|---|---|---|---|---|")
    passed = total = inside_n = 0
    for rid in ("bedroom_1", "bedroom_2", "bedroom_2_repeat", "kitchen"):
        tape = TAPE_CM[rid]
        if rid not in walls_cm:
            print(f"| {rid} | all | - | not reconstructed | - | - | - | FAIL |")
            continue
        cv, clo, chi = ceilings[rid]
        line, ok, ins = _row(rid, "ceiling", tape["ceiling"], cv, clo, chi)
        print(line)
        passed += ok; total += 1; inside_n += ins
        for t, pv in _pair(tape["walls"], walls_cm[rid]):
            if pv is None:
                print(f"| {rid} | wall {t:.1f} | {t:.1f} | no matching wall | - | - | no | FAIL |")
                total += 1
                continue
            k = min(range(len(ci[rid])), key=lambda i: abs(
                (ci[rid][i][0] + ci[rid][i][1]) / 2 - pv)) if ci[rid] else 0
            lo, hi = ci[rid][k] if ci[rid] else (pv, pv)
            label = "wall (door)" if t == tape.get("door_wall") else "wall"
            line, ok, ins = _row(rid, label, t, pv, lo, hi)
            print(line)
            passed += ok; total += 1; inside_n += ins
    print(f"\n**{passed} of {total} within the {GATE:.0%} gate. "
          f"{inside_n} of {total} tape values inside the stated interval.**\n")

    a, b = walls_cm.get("bedroom_2"), walls_cm.get("bedroom_2_repeat")
    print("## bedroom_2 against bedroom_2_repeat (cross-device: Moto against Nokia)\n")
    if a and b:
        print("| wall | bedroom_2 cm | repeat cm | difference cm | difference % |")
        print("|---|---|---|---|---|")
        for i in range(min(len(a), len(b))):
            d = b[i] - a[i]
            print(f"| {i + 1} (longest first) | {a[i]:.1f} | {b[i]:.1f} | {d:+.1f} | "
                  f"{100 * d / a[i]:+.1f}% |")
    else:
        print("One of the two captures produced no room.\n")

    print("\n## Adjacency against truth\n")
    pred = {tuple(sorted((x["room_a"], x["room_b"]))) for x in plan.get("adjacency", [])}
    truth = {tuple(sorted(t)) for t in TRUTH_ADJACENCY}
    print(f"predicted: {sorted(pred)}")
    print(f"truth:     {sorted(truth)}")
    print(f"matched {len(pred & truth)} of {len(truth)}; "
          f"{len(pred - truth)} predicted edge(s) not in truth")

    st = plan["stitched_plan"]
    print(f"\n## Overlap and footprint\n")
    print(f"overlap {st['overlap_area_m2']['value']:.4f} m2 (gate: zero)")
    fp = st["footprint_area_m2"]
    print(f"footprint {fp['value']:.2f} m2 [{fp['ci_low']:.2f}, {fp['ci_high']:.2f}]")
    print(f"rooms placed: {len(st['placements'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
