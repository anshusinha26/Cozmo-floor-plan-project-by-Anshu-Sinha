"""Cozmo command line.

    cozmo run    --input <path> --tier photo|video|lidar --out <dir> [--config] [--seed] [--drift-correction on|off]
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
from cozmo.io import manifest as prov
from cozmo.pipeline import DEFAULT_PIPELINE, get_pipeline

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


def resolve_config(config_path: Path, drift_correction: bool, pipeline_name: str) -> dict[str, Any]:
    """File config plus CLI overrides. This resolved dict is what gets hashed."""
    cfg = prov.load_config(config_path)
    cfg["run"] = {"pipeline": pipeline_name, "drift_correction": drift_correction}
    return cfg


@app.command()
def run(
    input_path: Path = typer.Option(..., "--input", help="Capture file or directory"),
    tier: TierOpt = typer.Option(..., "--tier", help="Input tier: photo, video or lidar"),
    out: Path = typer.Option(..., "--out", help="Output directory"),
    config: Path = typer.Option(DEFAULT_CONFIG, "--config", help="Gate and matching config"),
    seed: int = typer.Option(0, "--seed"),
    drift_correction: Switch = typer.Option(Switch.on, "--drift-correction"),
) -> None:
    """Run the pipeline on one capture and write plan.json plus run_manifest.json."""
    if not input_path.exists():
        _fail(f"input not found: {input_path}")
    if not config.exists():
        _fail(f"config not found: {config}")

    resolved = resolve_config(config, drift_correction == Switch.on, DEFAULT_PIPELINE)
    config_hash = prov.config_sha256(resolved)
    input_manifest = prov.build_input_manifest(input_path)

    pipeline = get_pipeline(DEFAULT_PIPELINE)
    started = _now()
    plan = pipeline.run(input_path, tier.value, resolved, seed)
    finished = _now()

    if plan.capture.input_manifest_sha256 != input_manifest["sha256"]:
        _fail("pipeline and CLI disagree on input manifest hash")
    if plan.run.config_sha256 != config_hash:
        _fail("pipeline and CLI disagree on config hash")

    out.mkdir(parents=True, exist_ok=True)
    plan_bytes = plan.to_json_bytes()
    plan_path = out / "plan.json"
    plan_path.write_bytes(plan_bytes)

    manifest = {
        "capture_id": plan.capture.id,
        "tier": tier.value,
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
        "outputs": {"plan": plan_path.name},
        "plan_sha256": prov.sha256_bytes(plan_bytes),
        "warnings": list(plan.warnings),
    }
    (out / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    typer.echo(f"wrote {plan_path} ({len(plan.rooms)} rooms) and {out / 'run_manifest.json'}")
    for w in plan.warnings:
        typer.echo(f"warning: {w}", err=True)


@app.command()
def eval(
    pred: Path = typer.Option(..., "--pred", help="plan.json or directory of runs"),
    truth: Path = typer.Option(..., "--truth", help="ground_truth.yaml or directory"),
    out: Path = typer.Option(..., "--out"),
) -> None:
    """Evaluate predictions against ground truth; writes eval.json and eval.md."""
    _not_implemented("eval", "sections 5-7, 10")


@app.command()
def bench(
    set_path: Path = typer.Option(..., "--set", help="benchmarks/captures.yaml"),
    out: Path = typer.Option(..., "--out"),
) -> None:
    """Run and evaluate every capture in a benchmark registry."""
    _not_implemented("bench", "section 4 and 10")


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
    """Draw a plan.json to PNG and SVG."""
    _not_implemented("render", "section 9")


if __name__ == "__main__":
    app()
