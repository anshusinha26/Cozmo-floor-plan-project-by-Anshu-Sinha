# Cozmo

Turns a handheld phone capture of an interior into a dimensioned, stitched
floor plan with damage annotations. Three input tiers (photo, video, LiDAR)
share one output contract. Every reported dimension carries a confidence
interval, and the evaluation harness scores those intervals as well as the
numbers.

## Install: two profiles

Requires Python 3.11 and [uv](https://docs.astral.sh/uv/).

### Profile 1: lidar only, the quick path

Everything needed to turn a LiDAR scan into a plan. No machine learning, no
model weights, no network at run time. **Clone to first plan is under three
minutes**, timed on a fresh machine in `docs/rehearsal.md`.

```bash
git clone <this repo> && cd Cozmo-floor-plan-project-by-Anshu-Sinha
uv sync                          # about 15 seconds on a cold cache
uv run pytest -q                 # about 45 seconds, no data or weights needed
scripts/fetch_sample_data.sh     # the three sample scans, about 95 seconds
uv run cozmo run --input data/sample/c00a170fe1 --tier lidar --out runs/first
```

That last command writes `plan.json`, `plan.png`, `run_manifest.json`,
`drift_report.json` and a `debug/` folder, in 4 to 34 seconds depending on the
scan.

### Profile 2: everything

Adds the video tier, the photo tier and damage detection. These pull torch,
COLMAP and several model checkpoints, so it is a much bigger install.

```bash
uv sync --extra all              # about 45 seconds on a cold cache, 1.6 GB venv
scripts/fetch_weights.sh         # 9.6 GB of weights, about 15 minutes
```

**The 15-minute target applies to the lidar path only.** Measured on a fresh
clone with a cold cache and a fast connection: 44 seconds to install (1.6 GB
of packages) and **15 minutes 30 seconds to fetch 9.6 GB of weights**. Your
connection decides that second number, not this repository. If you only want
a plan from a LiDAR scan, Profile 1 is the whole story and needs none of it.
Timings in `docs/rehearsal.md`.

Narrower extras exist if you only want one part: `--extra video` (also covers
photo), `--extra photo`, `--extra damage`. `scripts/fetch_weights.sh video`
and `scripts/fetch_weights.sh damage` fetch only that half.

| model | used by | size on disk |
|---|---|---|
| Depth Pro | video, photo | 1.90 GB |
| Depth Anything V2 Metric Indoor Large | video, photo | 1.34 GB |
| MapAnything, Apache checkpoint | video, photo, chunk-boundary poses only | 4.91 GB |
| OWLv2 | damage | 0.62 GB |
| SigLIP | damage | 0.82 GB |
| **total** | | **9.60 GB** |

Nothing downloads during a run. If a weight is missing the run fails and says
to run the fetch script.

**The lidar tier needs no weights, no network and no torch.** It is classical
geometry, so nothing in a lidar dimension came from a trained model. A lidar
run works with the network off; that is checked in `docs/rehearsal.md`. The
video and photo tiers do use trained models, and say which in
[THIRD_PARTY.md](THIRD_PARTY.md).

## One command per capture

```bash
uv run cozmo run --input <path> --tier photo|video|lidar --out <dir> \
    [--config config/gates.yaml] [--seed 0] [--drift-correction on|off] \
    [--segmentation erosion|cells] [--pipeline stub]
```

The rest of the commands:

```bash
uv run cozmo eval   --pred <plan.json|dir> --truth <ground_truth.yaml|dir> --out <dir>
uv run cozmo bench  --set benchmarks/captures.yaml --out <dir>
uv run cozmo render --plan <plan.json> --out <dir>
uv run cozmo schema --out schema/plan.schema.json
```

`scripts/regenerate_all.sh` rebuilds every number in this repository.

## Capturing your own property

Follow [docs/capture_protocol.md](docs/capture_protocol.md). It is one page
and assumes no technical knowledge. The short version: LiDAR route if you have
an iPhone Pro, otherwise one video loop per room at chest height on the 1x
lens.

## What is implemented

| area | state |
|---|---|
| Output contract, JSON schema, no bare dimensions anywhere | done |
| CLI, run manifest, byte-identical reruns | done |
| Input handling for photo, video and LiDAR, including HEIC and .mov | done |
| **LiDAR reconstruction**: floor, ceiling, walls, rooms, openings, adjacency, drift correction, uncertainty | done, accuracy unverified |
| Renderer, debug images | done |
| Ground truth format, hand-measured captures, benchmark registry | done |
| Evaluation: matching, eight gates, calibration, repeatability, cross-capture registration | done |
| Damage detection, concealed-damage rules, scope items | done, precision is poor on photos |
| Head-to-head comparison scaffold | done, our column pending |

## What is not implemented

* **Photo and video reconstruction.** Both tiers validate their input and then
  run the stub, which says so loudly in `warnings`. They are being built
  separately.
* **Accuracy against tape for any tier.** The LiDAR scans have no tape ground
  truth. Tape readings exist for five hand-measured rooms, but no tier
  produces plans for them yet.
* **Cross-capture repeatability.** The gate fails. One fix loop was run and
  did not fix it; see [fix_loop/POSTMORTEM.md](fix_loop/POSTMORTEM.md).
* **Damage detection at usable precision.** Clean on a LiDAR capture, 9 false
  regions in a photographed room with 2 marks. See
  [docs/damage_eval/README.md](docs/damage_eval/README.md).

## Where the numbers are

| document | what it holds |
|---|---|
| [docs/STATUS_main.md](docs/STATUS_main.md) | running status, newest stage last |
| [docs/device_matrix.md](docs/device_matrix.md) | what ran on what, and what each tier delivers |
| [docs/damage_eval/README.md](docs/damage_eval/README.md) | damage precision, filter by filter |
| [docs/compliance_matrix.md](docs/compliance_matrix.md) | every requirement against a real file |
| [fix_loop/](fix_loop/) | the repeatability fix loop, including its negative result |
| [docs/schema.md](docs/schema.md) | the output contract |
| [docs/technical_report.md](docs/technical_report.md) | the bound report, six pages |
| [docs/capture_protocol.md](docs/capture_protocol.md) | how to capture a property |
| [docs/hazards.md](docs/hazards.md) | mirrors, glass, glossy floors, low light and the rest |
| [docs/rehearsal.md](docs/rehearsal.md) | clone to first plan, timed on a fresh machine |

## Third-party models and licences

| model | used for | licence |
|---|---|---|
| [OWLv2](https://huggingface.co/google/owlv2-base-patch16-ensemble) `google/owlv2-base-patch16-ensemble` | open-vocabulary damage detection | Apache 2.0 |
| [SigLIP](https://huggingface.co/google/siglip-base-patch16-224) `google/siglip-base-patch16-224` | crop verifier that rejects false detections | Apache 2.0 |

No other model weights are used. Reconstruction is classical geometry: numpy,
scipy, OpenCV, shapely, scikit-image. There is no trained model anywhere in
the measurement path, so nothing in a reported dimension came from a network.

Python dependencies and their licences are resolved by `uv sync` from
`pyproject.toml`.

## Data

Capture data lives in `data/` and is gitignored: it is large, and the supplied
LiDAR scans are not ours to redistribute. `scripts/fetch_sample_data.sh`
retrieves it. Everything else, including every test, runs without it.

## Licence

MIT, see [LICENSE](LICENSE). Every third-party model, library and dataset,
with its licence and what it is used for, is listed in
[THIRD_PARTY.md](THIRD_PARTY.md).

## AI coding assistance

This repository was written with AI coding assistance (Claude). Every design
decision, threshold and reported number was reviewed and, where it mattered,
re-measured by the author; the negative results in `fix_loop/` and
`docs/damage_eval/` are reported as they came out rather than as they were
predicted.
