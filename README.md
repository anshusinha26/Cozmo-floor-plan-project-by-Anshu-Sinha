# Cozmo

**Reviewing this? Start with [SUBMISSION.md](SUBMISSION.md)**: the eight
deliverables with their paths, and a ten-line honest status of what works,
what does not, and what was never evaluated.

Turns a handheld phone capture of an interior into a dimensioned, stitched
floor plan. Three input tiers (photo, video, LiDAR) share one output contract.
Every reported dimension carries a confidence interval, and the evaluation
harness scores those intervals as well as the numbers.

Damage detection runs as part of `cozmo run` at the lidar and photo tiers.
`--damage auto` is the default: on when the damage weights are installed, off
with a warning when they are not. The plan always says which happened, because
an empty damage list otherwise means "none found" and "never looked" equally
well.

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
    [--segmentation erosion|cells] [--damage auto|on|off] [--pipeline stub]
```

The photo tier with damage on has been observed taking far longer than the
same run without it on this machine, 26 minutes against under 4; the cause is
not established. `--damage off` gives the plan alone, quickly.

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
an iPhone Pro. **Otherwise photographs, not video**: nine deliberate stills
from the corners of each room at chest height on the 1x lens, and send the
camera originals. Measured on the same rooms, photographs give a median wall
error of 2.2% where a video loop gives 32.9%, and the pipeline reads the lens
details the camera writes into each file, which a messaging app strips.

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
| Damage detection, concealed-damage rules, scope items | in `cozmo run` at the lidar and photo tiers; precision is poor on photos |
| Head-to-head against AR Plan 3D, both sides against tape | done; the rival is closer on 4 of 6 shared dimensions |

## What works, and how well

All three tiers reconstruct. None of them measures well enough to trust.
Numbers from [docs/benchmark/benchmark.md](docs/benchmark/benchmark.md),
rebuilt by `scripts/benchmark_all.py`.

| tier | median wall error | budget | gates passed | interval coverage |
|---|---|---|---|---|
| photo | **2.2%**, 8 of 12 walls inside the budget, worst 31.9% | 8% | 2 of 6 evaluated | 0.88, mean width 42% of value |
| video | **32.9%** | 3% | 2 of 7 evaluated | 1.00, mean width 409% of value |
| lidar | no number exists | 2 cm or 1%, provisional | 0 of 8, all NOT EVALUATED | not evaluated |

## What is not implemented, or does not work

* **Accuracy at the lidar tier is unknown.** Every lidar gate reads NOT
  EVALUATED: the three supplied scans are of a property nobody measured, and
  no iPhone was available to scan the five rooms that were. Its only evidence
  is cross-capture agreement, where two scans of one apartment place the same
  wall face within 1.9 cm while the room polygons built from those faces
  disagree by 97.5 cm. The geometry is sound; the partition into rooms is not.
* **Openings are not found.** Zero of seven matched at either image tier, so
  the opening gate is failing on absence, not on width.
* **Cross-capture repeatability.** The gate fails wherever it can be measured,
  including a same-device video pair. Fix loop 1 was run and did not move it;
  see [fix_loop/POSTMORTEM.md](fix_loop/POSTMORTEM.md).
* **The photo tier's worst wall is still 31.9% long.** Fix loop 3 anchored
  every room side to evidence and took the median to 2.2%, but the kitchen did
  not move: the rule takes the outermost qualifying wall face, and the one it
  takes there has the fewest points of any it found.
* **Video-tier intervals are vacuous.** 1.00 coverage at 409% mean width is an
  interval wide enough to contain anything.
* **Damage detection at usable precision.** Clean on a LiDAR capture, 24
  regions in a photographed room containing 2 marks. Both marks are found, but
  without depth the same mark in several photos cannot be merged, so the count
  is an upper bound and the plan says so. See
  [docs/damage_eval/README.md](docs/damage_eval/README.md).
* **Damage at the video tier.** The stage has no frame source there yet, so it
  is skipped with an explicit warning rather than guessed at.

## Where the numbers are

| document | what it holds |
|---|---|
| [SUBMISSION.md](SUBMISSION.md) | the honest status in ten lines, and every deliverable's path |
| [docs/benchmark/benchmark.md](docs/benchmark/benchmark.md) | gates per tier, interval coverage, repeatability, timing, head to head |
| [docs/photo_tier.md](docs/photo_tier.md) | how the photo tier works and what it measures |
| [docs/video_tier.md](docs/video_tier.md) | how the video tier works and what it measures |
| [docs/STATUS_main.md](docs/STATUS_main.md) | running status, newest stage last |
| [docs/device_matrix.md](docs/device_matrix.md) | what ran on what, and what each tier delivers |
| [docs/damage_eval/README.md](docs/damage_eval/README.md) | damage precision, filter by filter |
| [docs/compliance_matrix.md](docs/compliance_matrix.md) | every requirement against a real file |
| [fix_loop/](fix_loop/) | three fix loops and a focal regression, each scored against its predictions |
| [docs/schema.md](docs/schema.md) | the output contract |
| [docs/technical_report.md](docs/technical_report.md) | the bound report, six pages |
| [docs/capture_protocol.md](docs/capture_protocol.md) | how to capture a property |
| [docs/hazards.md](docs/hazards.md) | mirrors, glass, glossy floors, low light and the rest |
| [docs/rehearsal.md](docs/rehearsal.md) | clone to first plan, timed on a fresh machine |

## Third-party models and licences

| model | used for | licence |
|---|---|---|
| [Depth Pro](https://huggingface.co/apple/DepthPro) | monocular metric depth, video and photo | weights `apple-amlr`; code Apple Sample Code licence |
| [Depth Anything V2 Metric Indoor Large](https://huggingface.co/depth-anything/Depth-Anything-V2-Metric-Indoor-Large-hf) | second metric depth cue, video and photo | **CC BY-NC 4.0**, non-commercial |
| [MapAnything](https://huggingface.co/facebook/map-anything-apache) | chunk-boundary poses and the photo tier's reconstruction | Apache 2.0 checkpoint, chosen for that reason |
| [COLMAP](https://colmap.github.io/), through `pycolmap` | structure from motion, video and photo | BSD 3-Clause |
| [OWLv2](https://huggingface.co/google/owlv2-base-patch16-ensemble) | open-vocabulary damage detection | Apache 2.0 |
| [SigLIP](https://huggingface.co/google/siglip-base-patch16-224) | crop verifier that rejects false detections | Apache 2.0 |

**The lidar tier uses none of them.** Its reconstruction is classical
geometry (numpy, scipy, OpenCV, shapely, scikit-image), so nothing in a lidar
dimension came from a trained model. That claim holds for the lidar tier only:
every dimension the video and photo tiers report passed through the models
above. Depth Anything V2 Large is non-commercial, which makes it the one
component that would have to be swapped in a commercial build.

The full list, with versions, sizes and what each is used for, is in
[THIRD_PARTY.md](THIRD_PARTY.md).

Python dependencies and their licences are resolved by `uv sync` from
`pyproject.toml`.

## Data

Capture data lives in `data/` and is gitignored: it is large, and the supplied
LiDAR scans are not ours to redistribute. Everything else, including every
test, runs without it.

**Raw benchmark data** (own captures: original photos, 4K room videos, the tape
measurements PDF, rival-app screenshots, and the messaging-app photo copies):
https://drive.google.com/drive/folders/1MkwFUkSrNJ4x_tVjm0pCOvGsyGjdGNaR

Access is restricted to the assessors. To reproduce, download `own` and
`own_compressed` into `data/`. The supplied LiDAR scans come from
`scripts/fetch_sample_data.sh`.

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
