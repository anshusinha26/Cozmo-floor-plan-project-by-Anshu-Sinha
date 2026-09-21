#!/usr/bin/env python
"""Benchmark every capture that has ground truth, across all three tiers.

Video and photo plans are expensive (8 minutes a clip) and were produced on
the tier branch. They are reused rather than recomputed, and the report says
which plan came from where and whether its input hash still matches the data
on disk. Only the lidar tier is run here, because it takes seconds.

    .venv/bin/python scripts/benchmark_all.py --out docs/benchmark
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from pathlib import Path

from cozmo.contracts.models import Plan
from cozmo.eval import gates as G
from cozmo.eval.head_to_head import build_rows, load_spec, render_markdown, summarize
from cozmo.eval.runner import evaluate, write_eval
from cozmo.eval.self_consistency import cross_plan_repeat_pairs, observed_in_both, same_space_verdict
from cozmo.io.ground_truth import load_ground_truth, load_registry
from cozmo.io.inputs import validate_input
from cozmo.io.manifest import build_input_manifest, load_config

ROOT = Path(__file__).resolve().parent.parent
BRANCH = Path("/Users/anshusinha/Downloads/Cozmo-AI/cozmo-video-tier")

# Where a reusable plan lives, per capture. Paths are relative to the branch
# worktree; the benchmark records the source of every plan it uses.
# A local directory can stand in for a branch plan when something here had to
# be re-run, for example after a fix to the stitcher. Set COZMO_REUSE_OVERRIDE
# to a JSON object of capture id to directory.
def _overrides() -> dict:
    import os

    raw = os.environ.get("COZMO_REUSE_OVERRIDE")
    return json.loads(raw) if raw else {}


REUSE = {
    "video": {
        "own_bedroom_1_video": "fix_loop/loop2_video_scale/after/runs/bedroom_1",
        "own_bedroom_2_video": "fix_loop/loop2_video_scale/after/runs/bedroom_2",
        "own_bedroom_2_repeat_video": "fix_loop/loop2_video_scale/after/runs/bedroom_2_repeat",
        "own_kitchen_video": "fix_loop/loop2_video_scale/after/runs/kitchen",
        "own_hall_video": "fix_loop/loop2_video_scale/after/runs/hall",
    },
    "photo": {
        # The re-run on the camera originals, not the earlier run on the
        # compressed copies. The originals are what is on disk now, so this is
        # the plan whose input hash can be verified.
        "own_home_photo": "fix_loop/loop2_video_scale/photo_originals",
    },
}


def rename_single_room(plan: Plan, room_id: str) -> tuple[Plan, str | None]:
    """Give a one-room plan the ground truth's name for that room.

    A room id is a label, not a measurement: the video tier numbered its single
    room `room_01` until that was fixed, and the plans reused here predate the
    fix. Renaming is cheaper and more honest than recomputing eight minutes of
    reconstruction to change a string, and every rename is recorded in
    provenance. Only applied when the plan has exactly one room.
    """
    if len(plan.rooms) != 1 or plan.rooms[0].id == room_id:
        return plan, None
    old = plan.rooms[0].id
    data = json.loads(plan.to_json_bytes())
    data["rooms"][0]["id"] = room_id
    for surface in data.get("surfaces", []):
        if surface["room_id"] == old:
            surface["room_id"] = room_id
            surface["id"] = surface["id"].replace(f"s_{old}_", f"s_{room_id}_", 1)
    for placement in data["stitched_plan"]["placements"]:
        if placement["room_id"] == old:
            placement["room_id"] = room_id
    known = {s["id"] for s in data.get("surfaces", [])}
    for group in ("damage_regions", "concealed_damage_flags", "scope_items"):
        for item in data.get(group, []):
            if item["surface_id"] not in known:
                item["surface_id"] = item["surface_id"].replace(f"s_{old}_", f"s_{room_id}_", 1)
    return Plan.model_validate(data), f"{old} -> {room_id}"


def input_state(capture, spec_tier: str) -> dict:
    """Does the capture's input still exist, and does it hash as it did?"""
    src = ROOT / capture.input
    if not src.exists():
        return {"present": False, "sha256": None, "note": "input folder no longer on disk"}
    try:
        spec = validate_input(src, spec_tier)
        return {"present": True, "sha256": build_input_manifest(src, spec.files)["sha256"]}
    except Exception as e:
        return {"present": True, "sha256": None, "note": f"{type(e).__name__}: {e}"}


def _f(v, nd=2, suffix=""):
    return "n/a" if v is None else f"{v:.{nd}f}{suffix}"


def _portable(path) -> str:
    """A source path safe to commit.

    An override plan is usually re-run into a scratch directory outside the
    repository, and writing that absolute path into provenance.json leaks one
    machine's layout into a file everyone reads. Inside the repo the path is
    made relative; outside it, only the leaf survives, which is enough to
    match against a rerun and carries nothing about the machine.
    """
    p = Path(path)
    try:
        return str(p.resolve().relative_to(ROOT))
    except ValueError:
        return f"<outside the repository>/{p.name}"


def render_report(result: dict, registry) -> str:
    md = ["# Benchmark: every capture with ground truth", "",
          "Rebuild with `scripts/benchmark_all.py`. Tape readings are centimetres to the "
          "nearest inch, so `truth_uncertainty_m` is 0.013 and the coverage check widens "
          "the truth by it.", ""]

    md += ["## Provenance", "",
           "Video and photo plans cost about eight minutes a capture and were produced on "
           "the tier branch. They are reused, not recomputed. The lidar tier is run here "
           "because it takes seconds.", "",
           "The EXAMPLE fixtures in `benchmarks/captures.yaml` are left out: they are "
           "placeholder files run through the stub pipeline, and nothing the stub "
           "produces belongs in a table of measured results.", "",
           "A reused plan is the plan as it was made. The video plans below predate both "
           "the fix that records a guessed room side in the wall's method string and fix "
           "loop 3's shared room fitter, so **no video number here reflects either "
           "change**: their intervals are not widened for a guessed side and `plan.png` "
           "draws those sides solid, while the plan's own warnings say all four sides "
           "were closed by assumption. The photo plan was re-run after both and carries "
           "them.", "",
           "| capture | tier | plan | input hash matches | duration s | note |",
           "|---|---|---|---|---|---|"]
    for r in result["provenance"]:
        note = r.get("room_renamed", "")
        if note:
            note = f"room id renamed {note}, geometry untouched"
        if r.get("input_hash_matches") is False:
            note = (note + "; " if note else "") + "input on disk differs from the one the plan was made from"
        md.append(f"| {r['capture_id']} | {r['tier']} | {r.get('source', '')} | "
                  f"{r.get('input_hash_matches')} | {_f(r.get('duration_s'), 0)} | {note} |")

    md += ["", "## Gates, per tier", "",
           "One table per tier. The brief asks for gates at all three tiers, and pooling "
           "them hides both: a tier with large errors and many walls swamps a tier with "
           "small ones, and the single number that comes out describes neither. A gate "
           "with nothing to score reads NOT EVALUATED with the reason, never PASS.", ""]

    tiers = result.get("tiers", [])
    for tier in ["lidar", "video", "photo"]:
        md += [f"### {tier} tier", ""]
        gates = result.get("gates_by_tier", {}).get(tier)
        if not gates:
            reason = {"lidar": ("no lidar capture has tape ground truth. The three supplied "
                                "scans are of a property nobody measured, and no iPhone was "
                                "available to scan the rooms that were measured."),
                      }.get(tier, "no capture at this tier has ground truth.")
            md += [f"**NOT EVALUATED**: {reason}", ""]
            continue
        caps = [c["capture_id"] for c in result["captures"] if c["tier"] == tier]
        md += [f"Captures: {', '.join(caps)}.", "",
               "| gate | result | value | threshold | n | note |", "|---|---|---|---|---|---|"]
        for g in gates:
            note = g["detail"].get("note", "")
            if g["name"] == "ceiling_height_diagnosis":
                note = f"label: {g['detail']['label']}" + (f"; {note}" if note else "")
            md.append(f"| {g['name']} | {g['status']} | {g['value']:.4g} | {g['threshold']:.4g} | "
                      f"{g['n']} | {note} |")
        n_pass = sum(1 for g in gates if g["passed"])
        n_eval = sum(1 for g in gates if g["evaluated"])
        md += ["", f"**{n_pass} of {n_eval} evaluated gates pass** "
                   f"({len(gates) - n_eval} not evaluated).", ""]

    md += ["### Every capture together", "",
           "Kept for completeness. Read the per-tier tables above instead.", "",
           "| gate | result | value | threshold | n |", "|---|---|---|---|---|"]
    for g in result["gates"]:
        md.append(f"| {g['name']} | {g['status']} | {g['value']:.4g} | {g['threshold']:.4g} | {g['n']} |")

    md += ["", "### Two gaps worth stating plainly", "",
           "**Openings are not found at all.** The opening_width gate reads 0 of 7 within "
           "2 cm at both image tiers, and the reason is not that the widths are wrong: it "
           "is that **no opening was matched**. Photo has 0 matched, 6 missed and 1 "
           "phantom; video has 0 matched and 7 missed. The gate is failing on absence.", "",
           "**The lidar tier is NOT EVALUATED on every gate**, for lack of tape ground "
           "truth: the supplied scans are of a property nobody measured, and no iPhone was "
           "available to scan the rooms that were. Its only evidence is cross-capture "
           "agreement, where two scans of one apartment place the same wall face within "
           "**1.9 cm** of each other while the room polygons built from those faces "
           "disagree by 97.5 cm (`fix_loop/evidence/evidence.json`). The geometry is "
           "sound; the partition into rooms is not.", ""]

    md += ["", "## Interval coverage", "",
           "Coverage is the share of tape readings inside the stated 95% interval. "
           "Confident garbage counts readings that fall outside an interval narrower than "
           "the median for that quantity: wrong and sure of itself.", "",
           "| group | n | coverage | mean width, % of value | outside | confident garbage |",
           "|---|---|---|---|---|---|"]
    cal = result["calibration"]
    for label, row in [("all", cal["overall"])] + sorted(cal["by_tier"].items()) + \
            sorted(cal["by_tier_quantity"].items()):
        md.append(f"| {label} | {row['n']} | {_f(row['coverage'])} | "
                  f"{_f(row['mean_width_pct'], 0)} | {row['outside']} | {row['confident_garbage']} |")

    md += ["", "## Repeatability", ""]
    if not result.get("repeat_pairs"):
        md.append("No repeat pair had plans on both sides.")
    for rp in result["repeat_pairs"]:
        kind = {"same_device_repeat": "**Same device, the primary repeatability evidence.**",
                "cross_device_repeat": "**Cross device: disagreement mixes pipeline repeatability "
                                       "with camera differences.**",
                "coverage_mismatched": "**Not a valid repeat: the two captures cover different "
                                       "parts of the building.**"}.get(rp["repeat_kind"], "")
        g = rp["gate"]
        ob = rp["observed_in_both"]
        md += [f"### {rp['capture_a']} against {rp['capture_b']} ({rp['tier']})", "", kind, "",
               f"Devices: {rp['device_a']} and {rp['device_b']}.", "",
               f"Gate: {'PASS' if g['passed'] else 'FAIL'}, {g['n_within_tolerance']} of {g['n']} "
               f"wall rows within tolerance.", "",
               f"Walls seen in both: {ob['walls_observed_in_both']}, median difference "
               f"{_f((ob['median_abs_difference_m'] or 0) * 100, 1)} cm. Registered footprint IoU "
               f"{_f(ob['registration_footprint_iou'])}.", ""]

    md += ["## Timing", "", "| capture | tier | seconds |", "|---|---|---|"]
    for r in result["provenance"]:
        if r.get("duration_s") is not None:
            md.append(f"| {r['capture_id']} | {r['tier']} | {r['duration_s']:.0f} |")

    md += ["", "## Head to head against AR Plan 3D", "",
           "Both sides against tape, per shared dimension. A tie means the two errors "
           "differ by less than 1.5 cm.", ""]
    for tier, h in sorted(result.get("head_to_head", {}).items()):
        s_ = h["summary"]
        md += [f"### Our {tier} tier", "",
               "| room | dimension | tape m | theirs m | their error cm | ours m | our error cm | closer |",
               "|---|---|---|---|---|---|---|---|"]
        for r in h["rows"]:
            md.append(f"| {r['room']} | {r['dimension']} | {_f(r['tape_m'], 3)} | "
                      f"{_f(r['rival_m'], 3)} | {_f((r['rival_error_m'] or 0) * 100, 1)} | "
                      f"{_f(r['ours_m'], 3)} | "
                      f"{_f(None if r['our_error_m'] is None else r['our_error_m'] * 100, 1)} | "
                      f"{r['verdict']} |")
        if s_["n_scored"]:
            md += ["", f"**Beat or tie: {s_['beat_or_tie_pct']:.0f}% of {s_['n_scored']} dimensions** "
                       f"(ours {s_['ours']}, tie {s_['tie']}, theirs {s_['theirs']}).", ""]
        else:
            md += ["", "No plans for these rooms at this tier.", ""]

    md += ["## What the brief asked for, and what was possible", "",
           "The brief asks for the head to head at the lidar tier. That was impossible here: "
           "**no iPhone was available for capture**, so there is no lidar scan of the rooms the "
           "rival app measured, and the three supplied lidar scans are of a different property "
           "with no tape ground truth at all. The comparison is therefore run at the photo and "
           "video tiers, which do have captures of the same rooms the rival measured.", ""]
    return "\n".join(md) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "docs" / "benchmark"))
    ap.add_argument("--branch", default=str(BRANCH))
    ap.add_argument("--skip-lidar", action="store_true")
    a = ap.parse_args()
    out = Path(a.out)
    (out / "runs").mkdir(parents=True, exist_ok=True)
    branch = Path(a.branch)
    cfg = load_config(ROOT / "config" / "gates.yaml")
    registry = load_registry(ROOT / "benchmarks" / "captures.yaml")

    provenance: list[dict] = []
    pairs: list[tuple[Plan, object]] = []

    for cap in registry.captures:
        if cap.ground_truth is None:
            continue
        # The stub emits a fixed shape with no reconstruction behind it, and
        # the EXAMPLE fixtures are placeholder files. A row naming a capture
        # reads as a result even when its plan cell is empty, so the published
        # benchmark leaves them out entirely rather than listing them as gaps.
        if getattr(cap, "pipeline", None) == "stub":
            continue
        gt_path = ROOT / cap.ground_truth
        if not gt_path.is_file():
            continue
        dest = out / "runs" / cap.capture_id
        record = {"capture_id": cap.capture_id, "tier": cap.tier, "device": cap.device,
                  "space_id": cap.space_id, "repeat_of": cap.repeat_of,
                  "repeat_kind": cap.repeat_kind}

        override = _overrides().get(cap.capture_id)
        reuse_rel = REUSE.get(cap.tier, {}).get(cap.capture_id)
        if override and (Path(override) / "plan.json").is_file():
            src_dir = Path(override)
            reuse_rel = override
        elif reuse_rel and (branch / reuse_rel / "plan.json").is_file():
            src_dir = branch / reuse_rel
        else:
            src_dir = None
        if src_dir is not None:
            dest.mkdir(parents=True, exist_ok=True)
            for name in ("plan.json", "run_manifest.json", "plan.png", "drift_report.json"):
                if (src_dir / name).is_file():
                    shutil.copy2(src_dir / name, dest / name)
            plan = Plan.from_json_bytes((dest / "plan.json").read_bytes())
            truth = load_ground_truth(gt_path)
            if len(truth.rooms) == 1:
                plan, renamed = rename_single_room(plan, truth.rooms[0].id)
                if renamed:
                    (dest / "plan.json").write_bytes(plan.to_json_bytes())
                    record["room_renamed"] = renamed
            state = input_state(cap, cap.tier)
            record.update({
                "source": ("re-run here after a fix, see the note"
                           if override else "reused from the tier branch"),
                "source_path": _portable(reuse_rel),
                "recomputed": False,
                "plan_input_sha256": plan.capture.input_manifest_sha256,
                "input_now": state,
                "input_hash_matches": (state.get("sha256") == plan.capture.input_manifest_sha256)
                if state.get("sha256") else None,
            })
            if (dest / "run_manifest.json").is_file():
                m = json.loads((dest / "run_manifest.json").read_text())
                record["duration_s"] = m.get("duration_s")
                record["pipeline"] = (m.get("pipeline") or {}).get("name")
        elif cap.tier == "lidar" and not a.skip_lidar:
            t0 = time.time()
            r = subprocess.run(
                [str(ROOT / ".venv" / "bin" / "python"), "-m", "cozmo.cli", "run",
                 "--input", str(ROOT / cap.input), "--tier", "lidar", "--out", str(dest),
                 "--seed", "0"], cwd=ROOT, capture_output=True, text=True)
            if r.returncode != 0:
                record.update({"source": "run failed", "error": r.stderr.strip()[-300:]})
                provenance.append(record)
                continue
            plan = Plan.from_json_bytes((dest / "plan.json").read_bytes())
            record.update({"source": "run here", "recomputed": True,
                           "duration_s": round(time.time() - t0, 1),
                           "plan_input_sha256": plan.capture.input_manifest_sha256,
                           "input_hash_matches": True})
        else:
            record.update({"source": "no plan available", "recomputed": False})
            provenance.append(record)
            continue

        record["plan_path"] = str(dest / "plan.json")
        record["rooms"] = [r.id for r in plan.rooms]
        provenance.append(record)
        pairs.append((plan, load_ground_truth(gt_path)))

    if not pairs:
        print("no plans with ground truth")
        return 1

    result = evaluate(pairs, cfg)
    result["provenance"] = provenance

    # Repeatability, per registered repeat pair. The gate itself is unchanged;
    # what differs per pair is whether the two captures used the same phone.
    plans_by_id = {r["capture_id"]: r for r in provenance if r.get("plan_path")}
    repeats = []
    for cap in registry.captures:
        if not cap.repeat_of or cap.capture_id not in plans_by_id or cap.repeat_of not in plans_by_id:
            continue
        a = Plan.from_json_bytes(Path(plans_by_id[cap.repeat_of]["plan_path"]).read_bytes())
        b = Plan.from_json_bytes(Path(plans_by_id[cap.capture_id]["plan_path"]).read_bytes())
        rows, summary = cross_plan_repeat_pairs(a, b, cap.space_id, cap.tier)
        gate = G.repeatability(rows, cfg)
        repeats.append({
            "capture_a": cap.repeat_of, "capture_b": cap.capture_id, "tier": cap.tier,
            "repeat_kind": cap.repeat_kind or "same_device_repeat",
            "device_a": next((c.device for c in registry.captures if c.capture_id == cap.repeat_of), None),
            "device_b": cap.device,
            "same_space": same_space_verdict(a, b),
            "matching": summary,
            "observed_in_both": observed_in_both(a, b),
            "gate": {"passed": gate["passed"], "n": gate["n"], "value": gate["value"],
                     "n_within_tolerance": gate["detail"]["n_within_tolerance"],
                     "share_within_tolerance": gate["detail"]["share_within_tolerance"]},
        })
    result["repeat_pairs"] = repeats

    # Head to head, with our column filled from whatever plans we just gathered.
    spec_path = ROOT / "benchmarks" / "head_to_head" / "arplan3d.yaml"
    h2h = {}
    if spec_path.is_file():
        spec = load_spec(spec_path)
        from cozmo.eval.head_to_head import matched_lengths

        for tier in ("photo", "video"):
            lengths = matched_lengths(result, tier)
            rows = build_rows(spec, ROOT / "benchmarks" / "ground_truth", lengths, tier)
            summary = summarize(rows, spec["comparison"]["tie_threshold_m"])
            h2h[tier] = {"summary": summary,
                         "rows": [{"room": r.room_id, "dimension": r.dimension, "walls": r.walls,
                                   "tape_m": r.truth_m, "rival_m": r.rival_m, "ours_m": r.ours_m,
                                   "rival_error_m": r.rival_error, "our_error_m": r.our_error,
                                   "verdict": r.verdict(spec["comparison"]["tie_threshold_m"])}
                                  for r in rows]}
            (out / f"head_to_head_{tier}.md").write_text(render_markdown(spec, rows, summary))
    result["head_to_head"] = h2h
    result["config"] = {"path": "config/gates.yaml"}
    write_eval(result, out)
    (out / "provenance.json").write_text(json.dumps(provenance, indent=2, default=str) + "\n")

    (out / "benchmark.md").write_text(render_report(result, registry))

    print(f"{len(pairs)} plans evaluated")
    for r in provenance:
        mark = "run" if r.get("recomputed") else ("reused" if "reused" in str(r.get("source")) else "none")
        print(f"  {r['capture_id']:30s} {r['tier']:6s} {mark:6s} "
              f"hash_ok={r.get('input_hash_matches')}")
    s = result["summary"]
    print(f"gates: {s['n_passed']}/{s['n_gates']} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
