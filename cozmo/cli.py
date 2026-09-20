"""Cozmo command line.

    cozmo run    --input <path> --tier photo|video|lidar --out <dir> [--config] [--seed] [--drift-correction on|off] [--video-rotation auto|0|90|180|270]
    cozmo eval   --pred <plan.json|dir> --truth <ground_truth.yaml|dir> --out <dir>
    cozmo bench  --set benchmarks/captures.yaml --out <dir>
    cozmo schema --out schema/plan.schema.json
    cozmo render --plan <plan.json> --out <dir>

``run`` writes plan.json (byte-stable in input, config, seed) and
run_manifest.json (everything volatile: timings, timestamps, environment).
"""

from __future__ import annotations

import json
import logging
import platform
import sys
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

import typer

from cozmo import __version__
from cozmo.contracts.export_schema import write_schema
from cozmo.contracts.models import Plan, Renders
from cozmo.io import manifest as prov
from cozmo.io.ground_truth import GroundTruth, load_ground_truth, load_registry
from cozmo.io.inputs import InputError, validate_input
from cozmo.eval.runner import evaluate, write_eval
from cozmo.eval.self_consistency import cross_plan_repeat_pairs, same_space_verdict, self_consistency
from cozmo.eval import gates as G
from cozmo.pipeline import get_pipeline, pipeline_for
from cozmo.render.plan import render_plan_png

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Cozmo: handheld capture to dimensioned floor plan. Run, evaluate, benchmark, render, publish schema.",
)

DEFAULT_CONFIG = Path("config/gates.yaml")
DEFAULT_SCHEMA_OUT = Path("schema/plan.schema.json")


class TierOpt(str, Enum):
    photo = "photo"
    video = "video"
    lidar = "lidar"


class Switch(str, Enum):
    on = "on"
    off = "off"


class RoomModeOpt(str, Enum):
    """A per-room clip has one room in it; a property walk does not."""

    auto = "auto"
    on = "on"
    off = "off"


class RotationOpt(str, Enum):
    """ffmpeg applies a container rotation tag by itself, so `auto` is right for
    phone video. Stray Scanner's rgb.mp4 carries no tag and needs 90."""

    auto = "auto"
    r0 = "0"
    r90 = "90"
    r180 = "180"
    r270 = "270"


@app.callback()
def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(levelname)s %(name)s: %(message)s",
        force=True,
    )


def _fail(msg: str, code: int = 1) -> None:
    typer.echo(f"error: {msg}", err=True)
    raise typer.Exit(code)


def _not_implemented(command: str, section: str) -> None:
    typer.echo(f"error: `cozmo {command}` is not implemented yet ({section}).", err=True)
    raise typer.Exit(2)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def resolve_config(config_path: Path, drift_correction: bool, pipeline_name: str,
                   video_rotation: str = "auto", camera_height_m: float | None = None,
                   single_room: str = "auto", connector: str | None = None,
                   cache_root: str | None = None) -> dict[str, Any]:
    """File config plus CLI overrides. This resolved dict is what gets hashed."""
    cfg = prov.load_config(config_path)
    cfg["run"] = {"pipeline": pipeline_name, "drift_correction": drift_correction,
                  "video_rotation": video_rotation, "camera_height_m": camera_height_m,
                  "single_room": single_room, "connector": connector,
                  "cache_root": cache_root}
    return cfg


def execute_run(input_path: Path, tier: str, out: Path, config: Path, seed: int, drift_correction: bool,
                pipeline_name: str | None = None, debug: bool = True,
                video_rotation: str = "auto", camera_height_m: float | None = None,
                single_room: str = "auto", connector: str | None = None,
                cache_root: str | None = None) -> dict[str, Any]:
    """Run one capture: validate input, run the pipeline, write plan.json, plan.png, run_manifest.json.

    Raises InputError / FileNotFoundError on bad input. Returns the manifest dict.
    """
    if not input_path.exists():
        raise FileNotFoundError(f"input not found: {input_path}")
    if not config.exists():
        raise FileNotFoundError(f"config not found: {config}")
    spec = validate_input(input_path, tier)
    if spec.rooms is not None:
        logging.getLogger("cozmo.cli").info("input ok: %d room folder(s): %s", len(spec.rooms), ", ".join(r.room_id for r in spec.rooms))
    else:
        logging.getLogger("cozmo.cli").info("input ok: scan folder with %d readable file(s) for tier %s", len(spec.files), tier)

    name = pipeline_for(tier, pipeline_name)
    resolved = resolve_config(config, drift_correction, name, video_rotation, camera_height_m,
                              single_room, connector, cache_root)
    config_hash = prov.config_sha256(resolved)
    input_manifest = prov.build_input_manifest(input_path, spec.files)

    pipeline = get_pipeline(name)
    pipeline.input_manifest_sha256 = input_manifest["sha256"]
    out.mkdir(parents=True, exist_ok=True)
    if debug and hasattr(pipeline, "debug_dir"):
        pipeline.debug_dir = out / "debug"
    started = _now()
    plan = pipeline.run(input_path, tier, resolved, seed)
    finished = _now()

    if plan.capture.input_manifest_sha256 != input_manifest["sha256"]:
        raise RuntimeError("pipeline and CLI disagree on input manifest hash")
    if plan.run.config_sha256 != config_hash:
        raise RuntimeError("pipeline and CLI disagree on config hash")

    with pipeline.stage("render"):
        render_plan_png(plan, out / "plan.png")
    plan = plan.model_copy(update={"renders": Renders(plan_png="plan.png")})
    plan_bytes = plan.to_json_bytes()
    plan_path = out / "plan.json"
    plan_path.write_bytes(plan_bytes)

    manifest = {
        "capture_id": plan.capture.id,
        "tier": tier,
        "input": input_manifest,
        "config": {"path": str(config), "sha256": config_hash, "resolved": resolved},
        "git": {"commit": prov.git_commit(), "dirty": prov.git_dirty()},
        "seed": seed,
        "pipeline": {"name": pipeline.name, "version": pipeline.version, "cozmo_version": __version__},
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "duration_s": (finished - started).total_seconds(),
        "stage_timings_s": dict(pipeline.stage_timings_s),
        "library_versions": prov.library_versions(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "outputs": {"plan": plan_path.name, "plan_png": "plan.png",
                    "debug": getattr(pipeline, "debug_images", []),
                    "drift_report": "drift_report.json" if getattr(pipeline, "drift_report", None) else None},
        "plan_sha256": prov.sha256_bytes(plan_bytes),
        "n_rooms": len(plan.rooms),
        "warnings": list(plan.warnings),
    }
    if getattr(pipeline, "drift_report", None):
        pipeline.write_drift_report(out / "drift_report.json")
    (out / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest


@app.command()
def run(
    input_path: Path = typer.Option(..., "--input", help="Capture directory: one subfolder per room"),
    tier: TierOpt = typer.Option(..., "--tier", help="Input tier: photo, video or lidar"),
    out: Path = typer.Option(..., "--out", help="Output directory"),
    config: Path = typer.Option(DEFAULT_CONFIG, "--config", help="Gate and matching config"),
    seed: int = typer.Option(0, "--seed"),
    drift_correction: Switch = typer.Option(Switch.on, "--drift-correction"),
    pipeline: str = typer.Option(None, "--pipeline", help="Force a pipeline: stub, lidar or video"),
    video_rotation: RotationOpt = typer.Option(RotationOpt.auto, "--video-rotation",
                                               help="Video tier only: override the container rotation tag"),
    camera_height_m: float = typer.Option(None, "--camera-height",
                                          help="Height the phone was held at, metres. Sets the metric "
                                               "scale for the video and photo tiers (default 1.40)"),
    single_room: RoomModeOpt = typer.Option(RoomModeOpt.auto, "--single-room",
                                            help="Fit one room around the camera path instead of segmenting"),
    connector: str = typer.Option(None, "--connector",
                                  help="Room id that the other rooms attach to when stitching"),
    cache_root: str = typer.Option(None, "--cache-root",
                                   help="Share decoded frames and reconstructions between runs of "
                                        "the same capture, keyed by capture name"),
) -> None:
    """Run the pipeline on one capture and write plan.json, plan.png and run_manifest.json."""
    try:
        manifest = execute_run(input_path, tier.value, out, config, seed, drift_correction == Switch.on,
                               pipeline_name=pipeline, video_rotation=video_rotation.value,
                               camera_height_m=camera_height_m, single_room=single_room.value,
                               connector=connector, cache_root=cache_root)
    except (InputError, FileNotFoundError, RuntimeError, ValueError, KeyError) as e:
        _fail(str(e))
    typer.echo(f"wrote {out / 'plan.json'} ({manifest['n_rooms']} rooms), plan.png and run_manifest.json")
    for w in manifest["warnings"]:
        typer.echo(f"warning: {w}", err=True)


def _collect_plans(pred: Path) -> list[Path]:
    if pred.is_file():
        return [pred]
    return sorted(pred.rglob("plan.json"))


def _collect_truths(truth: Path) -> dict[str, GroundTruth]:
    files = [truth] if truth.is_file() else sorted(list(truth.glob("*.yaml")) + list(truth.glob("*.yml")))
    out: dict[str, GroundTruth] = {}
    for f in files:
        gt = load_ground_truth(f)
        if gt.capture_id in out:
            raise ValueError(f"duplicate ground truth for capture {gt.capture_id!r}: {f}")
        out[gt.capture_id] = gt
    return out


def _pair_plans_with_truth(plan_paths: list[Path], truths: dict[str, GroundTruth]) -> list[tuple[Plan, GroundTruth]]:
    pairs = []
    for p in plan_paths:
        plan = Plan.from_json_bytes(p.read_bytes())
        gt = truths.get(plan.capture.id)
        if gt is None:
            raise KeyError(f"no ground truth for capture {plan.capture.id!r} (from {p}); have {sorted(truths)}")
        pairs.append((plan, gt))
    return pairs


def run_eval(pred: Path, truth: Path, out: Path, config: Path) -> dict[str, Any]:
    cfg = prov.load_config(config)
    plan_paths = _collect_plans(pred)
    if not plan_paths:
        raise FileNotFoundError(f"no plan.json under {pred}")
    pairs = _pair_plans_with_truth(plan_paths, _collect_truths(truth))
    result = evaluate(pairs, cfg)
    result["config"] = {"path": str(config), "sha256": prov.config_sha256(cfg)}
    write_eval(result, out)
    return result


@app.command()
def eval(
    pred: Path = typer.Option(..., "--pred", help="plan.json or directory of runs"),
    truth: Path = typer.Option(..., "--truth", help="ground_truth.yaml or directory of them"),
    out: Path = typer.Option(..., "--out"),
    config: Path = typer.Option(DEFAULT_CONFIG, "--config"),
) -> None:
    """Evaluate predictions against ground truth; writes eval.json and eval.md."""
    try:
        result = run_eval(pred, truth, out, config)
    except (FileNotFoundError, KeyError, ValueError) as e:
        _fail(str(e).strip('"'))
    s = result["summary"]
    typer.echo(f"wrote {out / 'eval.json'} and {out / 'eval.md'}: {s['n_passed']}/{s['n_gates']} gates passed, "
               f"ceiling diagnosis {s['ceiling_height_diagnosis']}")


def _no_truth_report(entries, manifests, plans: dict[str, Plan], cfg: dict[str, Any]) -> dict[str, Any]:
    """Everything that can honestly be said about captures with no ground truth."""
    rows = {cid: self_consistency(p) for cid, p in plans.items()}
    repeats = []
    for e in entries:
        if e.repeat_of is None or e.repeat_of not in plans or e.capture_id not in plans:
            continue
        a, b = plans[e.repeat_of], plans[e.capture_id]
        verdict = same_space_verdict(a, b)
        pairs, match_summary = cross_plan_repeat_pairs(a, b, e.space_id, e.tier)
        # Score the gate whatever the same-space verdict says. Skipping it on a
        # weak verdict would report a vacuous pass on zero rows, which reads as
        # success and hides the failure being investigated.
        gate = G.repeatability(pairs, cfg)
        repeats.append({"capture_a": a.capture.id, "capture_b": b.capture.id, "space_id": e.space_id,
                        "tier": e.tier, "same_space": verdict, "matching": match_summary, "gate": gate})
    return {"self_consistency": rows, "repeat_pairs": repeats,
            "note": "No ground truth for these captures. Nothing here measures accuracy."}


def _no_truth_md(entries, manifests, report: dict[str, Any]) -> list[str]:
    md = ["## Captures with no ground truth", "",
          "**These captures have no tape or laser measurements, so nothing below is an accuracy result.** "
          "Reported: what the pipeline produced, how long it took, and whether the output is self-consistent.", "",
          "| capture | tier | rooms | walls | openings | footprint m2 | sum of rooms m2 | room overlap m2 | rooms connected | ceiling from prior | duration_s |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for e in entries:
        r = report["self_consistency"].get(e.capture_id)
        if r is None:
            continue
        m = manifests[e.capture_id]
        md.append(f"| {e.capture_id} | {e.tier} | {r['n_rooms']} | {r['n_walls']} | {r['n_openings']} | "
                  f"{r['footprint_area_m2']:.2f} | {r['sum_room_area_m2']:.2f} | {r['room_overlap_m2']:.3f} | "
                  f"{'yes' if r['rooms_connected'] else 'no ' + str(r['isolated_rooms'])} | "
                  f"{len(r['ceiling_from_prior'])}/{r['n_rooms']} | {m['duration_s']:.1f} |")
    for rp in report["repeat_pairs"]:
        v = rp["same_space"]
        ms = rp["matching"]
        reg = ms["registration"]
        md += ["", f"### Repeat pair: {rp['capture_a']} and {rp['capture_b']} ({rp['tier']})", "",
               f"Registration: rotation {reg['rotation_deg']} degrees, translation "
               f"({reg['tx']:.2f}, {reg['ty']:.2f}) m, footprint IoU {reg['footprint_iou']:.2f}.", "",
               f"Same space check: {v['matched_rooms']} of {min(v['rooms_a'], v['rooms_b'])} rooms pair by polygon IoU. "
               f"Verdict: **{'same space' if v['same_space'] else 'NOT confirmed as the same space'}** "
               f"({v['basis']}). The gate below is scored either way; a weak verdict is itself "
               f"evidence about the segmentation, not a reason to skip scoring.", "", v["note"], "",
               f"Room matching: {ms['rooms_a']} rooms in {rp['capture_a']}, {ms['rooms_b']} in {rp['capture_b']}, "
               f"{ms['rooms_matched']} matched at IoU >= {ms['min_iou']} (IoU values {ms['room_iou']}). "
               f"Unmatched: {ms['unmatched_rooms_a']} and {ms['unmatched_rooms_b']}.", "",
               f"Wall matching inside matched rooms: {ms['walls_matched']} paired by nearest parallel face "
               f"within {ms['max_wall_offset_m']} m, {ms['walls_unmatched']} with no counterpart.", ""]
        g = rp["gate"]
        md += [f"Repeatability gate: {'PASS' if g['passed'] else 'FAIL'} on {g['n']} wall rows, "
               f"worst ratio {g['value']:.2f} against the allowed 1.0. "
               f"Within tolerance: {g['detail'].get('n_within_tolerance', 0)} of {g['n']}."]
        if g["n"]:
            matched_rows = [r for r in g["detail"]["per_wall"] if r.get("matched", True)]
            if matched_rows:
                w = max(matched_rows, key=lambda r: r["ratio"])
                md += ["", f"Worst matched wall: {w['room_id']} {w['wall_id']} {w['a']:.3f} m vs {w['b']:.3f} m, "
                           f"difference {w['diff_m'] * 100:.1f} cm against {w['allowed_m'] * 100:.1f} cm allowed.",
                       "", f"Of the {len(matched_rows)} matched wall pairs, "
                           f"{sum(1 for r in matched_rows if r['ok'])} are within tolerance.", ""]
            md += [f"Rows failing because a wall or room has no counterpart: "
                   f"{sum(1 for r in g['detail']['per_wall'] if not r.get('matched', True))}.", ""]
    return md


def _bench_md(entries, manifests: dict[str, dict[str, Any]], result: dict[str, Any] | None,
              eval_md: str, no_truth: dict[str, Any] | None, no_truth_entries) -> str:
    md = ["# Benchmark report", "", f"Captures: {len(entries)}. cozmo {__version__}.", ""]
    if result is not None and result["summary"]["stub_output"]:
        md += ["**WARNING: some plans came from the STUB PIPELINE. Their numbers describe the harness, not a reconstruction.**", ""]
    md += ["## Captures", "",
           "| capture | space | tier | pipeline | repeat_of | multi_room | rooms | duration_s | stages (s) | plan sha256 |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for e in entries:
        m = manifests[e.capture_id]
        stages = ", ".join(f"{k} {v:.2f}" for k, v in m["stage_timings_s"].items())
        md.append(f"| {e.capture_id} | {e.space_id} | {e.tier} | {m['pipeline']['name']} | {e.repeat_of or ''} | "
                  f"{e.multi_room} | {m['n_rooms']} | {m['duration_s']:.1f} | {stages} | {m['plan_sha256'][:12]} |")
    if no_truth is not None:
        md += [""] + _no_truth_md(no_truth_entries, manifests, no_truth)
    if result is not None:
        md += ["", "## Gate summary (captures with ground truth)", "",
               "| gate | result | value | threshold | n |", "|---|---|---|---|---|"]
        for g in result["gates"]:
            md.append(f"| {g['name']} | {'PASS' if g['passed'] else 'FAIL'} | {g['value']:.4f} | {g['threshold']:.4f} | {g['n']} |")
        md += ["", "---", "", eval_md]
    return "\n".join(md)


@app.command()
def bench(
    set_path: Path = typer.Option(..., "--set", help="benchmarks/captures.yaml"),
    out: Path = typer.Option(..., "--out"),
    config: Path = typer.Option(DEFAULT_CONFIG, "--config"),
    seed: int = typer.Option(0, "--seed"),
) -> None:
    """Run and evaluate every capture in a registry; writes runs/, eval.json, eval.md, benchmark.md."""
    if not set_path.exists():
        _fail(f"registry not found: {set_path}")
    registry = load_registry(set_path)
    base = set_path.resolve().parent.parent  # registry paths are relative to the repo root
    resolve = lambda p: Path(p) if Path(p).is_absolute() else base / p  # noqa: E731

    manifests: dict[str, dict[str, Any]] = {}
    pairs: list[tuple[Plan, GroundTruth]] = []
    plans: dict[str, Plan] = {}
    for e in registry.captures:
        run_dir = out / "runs" / e.capture_id
        try:
            manifests[e.capture_id] = execute_run(
                resolve(e.input), e.tier, run_dir, config, seed, True,
                pipeline_name=getattr(e, "pipeline", None),
                video_rotation=getattr(e, "video_rotation", None) or "auto")
        except (InputError, FileNotFoundError, RuntimeError, ValueError, KeyError) as ex:
            _fail(f"{e.capture_id}: {ex}")
        plan = Plan.from_json_bytes((run_dir / "plan.json").read_bytes())
        plans[e.capture_id] = plan
        if e.ground_truth is None:
            continue
        gt = load_ground_truth(resolve(e.ground_truth))
        if gt.capture_id != e.capture_id:
            _fail(f"{e.capture_id}: ground truth file says capture_id {gt.capture_id!r}")
        pairs.append((plan, gt))

    cfg = prov.load_config(config)
    untruthed = [e for e in registry.captures if e.ground_truth is None]
    no_truth = _no_truth_report(untruthed, manifests, {e.capture_id: plans[e.capture_id] for e in untruthed}, cfg) \
        if untruthed else None
    result = None
    eval_md = ""
    if pairs:
        result = evaluate(pairs, cfg)
        result["config"] = {"path": str(config), "sha256": prov.config_sha256(cfg)}
        if no_truth is not None:
            result["no_ground_truth"] = no_truth
        _, md_path = write_eval(result, out)
        eval_md = md_path.read_text(encoding="utf-8")
    elif no_truth is not None:
        (out / "eval.json").write_text(json.dumps({"no_ground_truth": no_truth}, indent=2, default=str) + "\n",
                                       encoding="utf-8")
    (out / "benchmark.md").write_text(
        _bench_md(registry.captures, manifests, result, eval_md, no_truth, untruthed), encoding="utf-8")
    if result is not None:
        s = result["summary"]
        typer.echo(f"wrote {out / 'benchmark.md'}: {len(registry.captures)} captures, "
                   f"{s['n_passed']}/{s['n_gates']} gates passed on {len(pairs)} with ground truth, "
                   f"ceiling diagnosis {s['ceiling_height_diagnosis']}")
    else:
        typer.echo(f"wrote {out / 'benchmark.md'}: {len(registry.captures)} captures, none with ground truth")
    return

@app.command()
def schema(
    out: Path = typer.Option(DEFAULT_SCHEMA_OUT, "--out"),
) -> None:
    """Write the versioned JSON Schema for plan.json."""
    path = write_schema(out)
    typer.echo(f"wrote {path}")


@app.command()
def render(
    plan: Path = typer.Option(..., "--plan"),
    out: Path = typer.Option(..., "--out"),
) -> None:
    """Draw a plan.json to plan.png in the output directory."""
    if not plan.exists():
        _fail(f"plan not found: {plan}")
    path = render_plan_png(Plan.from_json_bytes(plan.read_bytes()), out / "plan.png")
    typer.echo(f"wrote {path}")


if __name__ == "__main__":
    app()
