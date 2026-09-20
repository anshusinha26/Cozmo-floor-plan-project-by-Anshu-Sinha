# Cozmo

Pipeline scaffold that turns handheld phone captures of interior spaces into a
dimensioned, stitched floor plan with damage annotations. Three input tiers
(photo, video, LiDAR) share one output contract. Accuracy is graded against
tape and laser ground truth, and every reported dimension carries a calibrated
confidence interval.

This repository currently holds the output contract, the CLI, the provenance
manifest and a stub pipeline. It contains no computer vision and no ML
dependencies. Everything runs CPU-only and offline.

## Install

Requires Python 3.11 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync            # creates .venv and installs locked dependencies
uv run pytest      # run the test suite
```

Without uv:

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e . pytest
```

## Run

```bash
# Produce a plan for one capture (stub pipeline for now)
uv run cozmo run --input path/to/capture_dir --tier video --out runs/apt_living_01 \
    [--config config/gates.yaml] [--seed 0] [--drift-correction on|off]

# Publish the JSON Schema for plan.json
uv run cozmo schema --out schema/plan.schema.json
```

`run` writes `plan.json` and `run_manifest.json` into `--out`. The plan is
byte-identical for the same input, config and seed. The manifest records
SHA-256 of every input file, the resolved config and its hash, git commit,
seed, per-stage timings and library versions.

Not implemented yet, and each says so with exit code 2:

```bash
uv run cozmo eval   --pred <plan.json|dir> --truth <ground_truth.yaml|dir> --out <dir>
uv run cozmo bench  --set benchmarks/captures.yaml --out <dir>
uv run cozmo render --plan <plan.json> --out <dir>
```

## Output contract

See [docs/schema.md](docs/schema.md). The one rule: no dimension is ever a
bare float. Every `*_m`, `*_m2`, `*_deg` key holds a `Measurement` with
`value`, `ci_low`, `ci_high`, `unit`, `method` and `ci_level`.

## Status

| area | status |
|------|--------|
| Measurement type and validation | done |
| Plan output models, referential integrity, schema export | done |
| CLI `run` and `schema`, run manifest, byte-identical reruns | done |
| Stub pipeline (hand-written two-room plan, loudly marked) | done |
| Ground-truth format and benchmark registry | not started |
| Entity matching (walls, openings) | not started |
| Gates, calibration, repeatability | not started |
| `cozmo eval`, `cozmo bench`, eval.json and eval.md | not started |
| Renderer (`cozmo render`) | not started |
| Compliance matrix | not started |
| Any real reconstruction (photo, video, LiDAR) | not started |

The stub pipeline ignores input content. Its plan is marked with
`"STUB PIPELINE: NOT A REAL RECONSTRUCTION"` in `warnings`, a WARNING log line
on every run, and a module docstring. It must never be read as a result.
