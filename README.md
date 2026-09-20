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

| tier | input |
|---|---|
| photo | a directory with one subfolder per room (the room id), each with 2 or more images (jpg, jpeg, png, heic) |
| video | one Stray Scanner scan folder; only `rgb.mp4` may be read |
| lidar | one Stray Scanner scan folder covering the whole property; the pipeline segments rooms itself |

A Stray Scanner scan folder holds `rgb.mp4` (1920x1440, 60 fps),
`depth/NNNNNN.png` (256x192 uint16 millimetres), `confidence/NNNNNN.png`
(0, 1, 2), `odometry.csv` and `camera_matrix.csv`.

Tier isolation is enforced in code, not by convention: every file access goes
through a check that refuses files the tier may not read, and the run manifest
hashes only those files. A photo input that looks like a scan folder is
rejected, because `depth/` holds png files that would otherwise pass as room
photos.

## Run

```bash
# LiDAR tier: the real reconstruction
uv run cozmo run --input data/sample/c00a170fe1 --tier lidar --out runs/c00a170fe1 \
    [--config config/gates.yaml] [--seed 0] [--drift-correction on|off] [--pipeline stub]

# Photo and video tiers: still the stub, which says so in warnings
uv run cozmo run --input benchmarks/captures/EXAMPLE --tier photo --out runs/EXAMPLE

# Evaluate one plan or a directory of runs against ground truth
uv run cozmo eval --pred runs/EXAMPLE/plan.json --truth benchmarks/ground_truth/EXAMPLE.yaml --out evals/EXAMPLE

# Run and evaluate every capture in the registry
uv run cozmo bench --set benchmarks/captures.yaml --out bench

# Draw an existing plan
uv run cozmo render --plan runs/EXAMPLE/plan.json --out runs/EXAMPLE

# Publish the JSON Schema for plan.json
uv run cozmo schema --out schema/plan.schema.json
```

`run` writes `plan.json`, `plan.png` and `run_manifest.json` into `--out`. A
LiDAR run also writes `drift_report.json` and `debug/` (density map, wall
faces, room masks, openings).
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

## LiDAR reconstruction

Classical geometry only. No machine learning, no open3d. Stages:

1. **Fuse** every 10th depth frame, keeping confidence 2 and depth 0.2 to
   4.5 m. Normals come from the depth image itself and are oriented toward
   the camera. Voxel downsample to 2 cm.
2. **Levels.** Floor and ceiling are histogram peaks of near-vertical-normal
   points, refined by a trimmed plane fit. Ceiling height is measured per
   grid cell. Where the ceiling covers under 15% of floor cells, a 2.2 to
   3.2 m prior is emitted with method `prior_no_ceiling_observed` and a
   warning, rather than a number invented from a few points.
3. **Manhattan frame.** Wall normal azimuths collapse modulo 90 degrees into
   one dominant direction; rotating by it makes wall fitting two 1D problems.
   Recorded in the plan's assumptions.
4. **Wall faces.** Histogram peaks along each axis, extents from occupancy
   runs. A face whose points stop below 1.6 m is furniture, not wall.
5. **Rooms.** Two methods, picked with `--segmentation`:
   * `cells` (default): wall faces become grid lines, the lines cut the plan
     into cells, and two cells are separated only where the edge between them
     carries wall support in the 1.0 to 1.6 m band. Rooms under 80% supported
     are flagged partially observed with doubled intervals.
   * `erosion` (the original): free space from seen floor and the walked
     path, eroded by half a metre, watershed back.

   On the sample captures neither is repeatable across two scans of one
   property. See `fix_loop/POSTMORTEM.md`; the recommendation there is to
   default to `erosion` until the cell method's footprint inflation is fixed.
6. **Openings.** Gaps in wall occupancy between 0.3 and 1.9 m that free space
   crosses on both sides. Height from lintel points, or a prior with a
   warning. Windows are not attempted, and a warning says so.
7. **Adjacency** from openings joining two rooms.
8. **Drift correction** (`--drift-correction on|off`, default on). Per
   5 second chunk: yaw against the global Manhattan axes, floor height
   offset, then a 1D shift onto the global wall faces. Estimates beyond the
   configured limits are rejected. `drift_report.json` carries footprint area
   and mean wall thickness for both settings.

   Re-measured under the wall-driven segmentation: mean wall thickness is
   32.1 mm without correction and 35.8 mm with it on `1a8384c3f6`, and 32.5
   against 32.6 mm on `c7d28f72c6`. Correction does not reduce the smear on
   these captures, because the estimated corrections are small to begin with
   (mean yaw error 0.55 to 1.57 degrees, mean height error 3 to 8 mm). It is
   left on by default because it costs a second pass and does no harm, but
   it is not earning its keep on this data.
9. **Uncertainty.** Wall length intervals combine each bounding face's
   position error (residual spread over an effective sample size that counts
   0.25 m patches, not 2 cm points) with a 1% depth scale bias and a 1 cm
   floor. Areas propagate from the lengths.

### Known limitations of the LiDAR path

* Room segmentation is not repeatable across two captures of one property.
  Under the erosion method the two sample apartment scans produce 8 and 10
  rooms; under the wall-driven cell complex they produce 6 and 9. The
  cross-capture repeatability gate fails under both, at 0 rows within
  tolerance. One fix loop has been run and did not fix it; see
  `fix_loop/POSTMORTEM.md` for what remains.
* The cell method inflates footprint area, because a room with an unobserved
  side is closed at the edge of what was seen. 86.6 m2 and 64.7 m2 against a
  flat of roughly 75 m2.
* No scan has ground truth for room count or room size. `c00a170fe1` is not
  one closed room: the camera path crosses two or three partly scanned
  spaces with unobserved sides. Any earlier text treating its camera-path
  extent as a room size was wrong.
* Accuracy is unverified. There is no tape ground truth for the sample scans,
  so `bench` reports outputs, runtime and self-consistency only.
* Damage detection does not exist. LiDAR plans emit empty damage lists and a
  warning.

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
| Drift correction and ablation report | done, lidar tier |
| LiDAR reconstruction (Stray Scanner scans) | done, accuracy unverified |
| Photo and video reconstruction | not started, both use the stub |

The stub pipeline ignores input content. Its plan is marked with
`"STUB PIPELINE: NOT A REAL RECONSTRUCTION"` in `warnings`, a WARNING log line
on every run, red text on the rendered PNG, and a banner in eval.md and
benchmark.md. It must never be read as a result.
