# Cozmo

Pipeline scaffold that turns handheld phone captures of interior spaces into a
dimensioned, stitched floor plan with damage annotations. Three input tiers
(photo, video, LiDAR) share one output contract. Accuracy is graded against
tape and laser ground truth, and every reported dimension carries a calibrated
confidence interval.

This repository holds the output contract, the CLI, the input convention, the
ground-truth format, the evaluation harness (matching, gates, calibration,
repeatability), a PNG renderer and a stub pipeline. It contains no computer
vision and no ML dependencies. Everything runs CPU-only and offline.

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

## Input convention

A capture is a directory with one subfolder per room; the subfolder name is
the room id.

| tier | each room subfolder holds |
|---|---|
| photo | 2 or more images (jpg, jpeg, png, heic) |
| video | exactly one clip (mp4, mov) |
| lidar | `rgb/`, `depth/`, `poses.json`, `intrinsics.json` (fx, fy, cx, cy) |

`run` validates this layout and fails with a message naming the room and the
problem. No pixels are decoded in this version.

## Run

```bash
# Produce a plan for one capture (stub pipeline for now)
uv run cozmo run --input benchmarks/captures/EXAMPLE --tier photo --out runs/EXAMPLE \
    [--config config/gates.yaml] [--seed 0] [--drift-correction on|off]

# Evaluate one plan or a directory of runs against ground truth
uv run cozmo eval --pred runs/EXAMPLE/plan.json --truth benchmarks/ground_truth/EXAMPLE.yaml --out evals/EXAMPLE

# Run and evaluate every capture in the registry
uv run cozmo bench --set benchmarks/captures.yaml --out bench

# Draw an existing plan
uv run cozmo render --plan runs/EXAMPLE/plan.json --out runs/EXAMPLE

# Publish the JSON Schema for plan.json
uv run cozmo schema --out schema/plan.schema.json
```

`run` writes `plan.json`, `plan.png` and `run_manifest.json` into `--out`.
The plan is byte-identical for the same input, config and seed. The manifest
records SHA-256 of every input file, the resolved config and its hash, git
commit, seed, per-stage timings and library versions.

`eval` writes `eval.json` and `eval.md`: gate pass/fail table, matching
counts (matched / missed / phantom), per-room error tables, calibration
table by tier and quantity, repeatability table and the ceiling-height
diagnosis label. `bench` runs every registry capture, evaluates them together
(so repeat captures feed the spread and repeatability gates) and writes
`benchmark.md` with per-capture timing from each `run_manifest.json`.

## Ground truth

One YAML per capture in `benchmarks/ground_truth/`, listed in
`benchmarks/captures.yaml`. Walls are listed clockwise starting from the wall
with the main door. `EXAMPLE.yaml` holds obviously fake values so the
harness can run end to end; replace with tape or laser readings.

## Evaluation design

* Rooms match by id. Walls match by cyclic order: every rotation and both
  directions are tried, lowest total length error wins, openings break ties
  on symmetric rooms. Openings match by centre position within 0.5 m on the
  matched wall. Nothing is dropped: unmatched entities are counted.
* Gate denominators include missed and phantom entities, so predicting less
  cannot raise a score.
* Calibration is scored separately: coverage against the nominal 95%, mean
  interval width as % of value, and a "confident garbage" count (truth
  outside the interval and interval narrower than the median for that
  quantity).
* Thresholds live in `config/gates.yaml`. The LiDAR wall budget is marked
  PROVISIONAL.

## Output contract

See [docs/schema.md](docs/schema.md). The one rule: no dimension is ever a
bare float. Every `*_m`, `*_m2`, `*_deg` key holds a `Measurement` with
`value`, `ci_low`, `ci_high`, `unit`, `method` and `ci_level`.

## Status

See [docs/compliance_matrix.md](docs/compliance_matrix.md) for the full
requirement table.

| area | status |
|------|--------|
| Measurement type and validation | done |
| Plan output models, referential integrity, schema export | done |
| CLI `run` and `schema`, run manifest, byte-identical reruns | done |
| Input convention validation (photo, video, lidar) | done |
| Stub pipeline (hand-written two-room plan, loudly marked) | done |
| Ground-truth format and benchmark registry | done (EXAMPLE values fake) |
| Entity matching (rooms by id, walls cyclic, openings by offset) | done |
| Gates, calibration, repeatability | done |
| `cozmo eval`, `cozmo bench`, eval.json, eval.md, benchmark.md | done |
| Renderer (`plan.png`) | done |
| Compliance matrix | done |
| Any real reconstruction (photo, video, LiDAR) | not started |

The stub pipeline ignores input content. Its plan is marked with
`"STUB PIPELINE: NOT A REAL RECONSTRUCTION"` in `warnings`, a WARNING log line
on every run, red text on the rendered PNG, and a banner in eval.md and
benchmark.md. It must never be read as a result.
