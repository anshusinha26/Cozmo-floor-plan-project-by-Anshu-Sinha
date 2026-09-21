# Submission

## Status in ten lines

1. **The lidar tier works and is fast**: a Stray Scanner scan becomes a
   dimensioned plan in 4 to 34 seconds, CPU only, no network, no trained model.
2. **No lidar accuracy number exists.** Every lidar gate reads NOT EVALUATED,
   because the supplied scans are of a property nobody measured and no iPhone
   was available to scan the rooms that were.
3. **The photo tier runs on every room** and reaches 13.0% median wall error,
   against an 8% budget. Six of twelve walls are inside it.
4. **The video tier runs on every clip** and reaches 32.9% median wall error
   against a 3% budget. It is not close.
5. **Openings are not found.** Zero of seven matched at either image tier: the
   gate fails on absence, not on width.
6. **Repeatability fails everywhere** it can be measured, including a
   same-device video pair.
7. **Intervals are honest at the photo tier** (0.88 coverage, 70% mean width)
   and vacuous at the video tier (1.00 coverage, 409% mean width).
8. **A rival consumer app beats both image tiers** on 4 of 6 shared
   dimensions; our photo tier wins 2.
9. **Damage detection finds what is there** and too much else: both staged
   marks found, 8 to 15 false regions in a room containing two.
10. **Three fix loops were run and written up**, two of them negative results
    reported as they came out rather than as they were predicted.

## The eight deliverables

| # | deliverable | path |
|---|---|---|
| 1 | **Working pipeline**, one command per capture, three tiers | [`cozmo/`](cozmo/), [`README.md`](README.md) |
| 2 | **Output contract and schema**, every dimension an interval | [`cozmo/contracts/models.py`](cozmo/contracts/models.py), [`schema/plan.schema.json`](schema/plan.schema.json), [`docs/schema.md`](docs/schema.md) |
| 3 | **Technical report**, six pages | [`docs/technical_report.md`](docs/technical_report.md), [`docs/technical_report.pdf`](docs/technical_report.pdf) |
| 4 | **Benchmark report**, gates per tier, coverage, repeatability, timing, head to head | [`docs/benchmark/benchmark.md`](docs/benchmark/benchmark.md) |
| 5 | **Capture protocol**, one page a non-engineer can follow | [`docs/capture_protocol.md`](docs/capture_protocol.md) |
| 6 | **Device matrix**, capture hardware by processing hardware by tier | [`docs/device_matrix.md`](docs/device_matrix.md) |
| 7 | **Reproduction bundle**, one command rebuilds every reported number | [`scripts/regenerate_all.sh`](scripts/regenerate_all.sh), [`scripts/fetch_weights.sh`](scripts/fetch_weights.sh), [`scripts/fetch_sample_data.sh`](scripts/fetch_sample_data.sh) |
| 8 | **Fix loops**, declared before the fix, measured after | [`fix_loop/`](fix_loop/), [`fix_loop/README.md`](fix_loop/README.md) |

## Supporting evidence

| what | path |
|---|---|
| Ground truth, tape to the nearest inch | [`benchmarks/ground_truth/`](benchmarks/ground_truth/) |
| Capture registry, devices and repeat pairs | [`benchmarks/captures.yaml`](benchmarks/captures.yaml) |
| Compliance matrix, every requirement against a real file | [`docs/compliance_matrix.md`](docs/compliance_matrix.md) |
| Hazards: glass, mirrors, glossy floors, low light, a moving dog | [`docs/hazards.md`](docs/hazards.md) |
| Damage precision, filter by filter | [`docs/damage_eval/README.md`](docs/damage_eval/README.md) |
| Clean-machine rehearsal, both install profiles timed | [`docs/rehearsal.md`](docs/rehearsal.md) |
| Running status, newest last | [`docs/STATUS_main.md`](docs/STATUS_main.md) |
| Licences of every model, library and dataset | [`THIRD_PARTY.md`](THIRD_PARTY.md) |
| Models evaluated and rejected | [`docs/experiments/`](docs/experiments/) |

## Raw data

**Raw benchmark data** (own captures: original photos, 4K room videos, the tape
measurements PDF, rival-app screenshots, and the messaging-app photo copies):
https://drive.google.com/drive/folders/1MkwFUkSrNJ4x_tVjm0pCOvGsyGjdGNaR

Access is restricted to the assessors. To reproduce, download `own` and
`own_compressed` into `data/`. The supplied LiDAR scans come from
`scripts/fetch_sample_data.sh`.

## What was never evaluated, and why

**Every lidar gate.** The three supplied Stray Scanner scans are of a property
nobody measured with a tape, and no iPhone was available to scan the five
rooms that were measured. There is no way to put a lidar prediction next to a
tape reading in this repository. The only evidence the tier has is
cross-capture agreement: two scans of one apartment place the same wall face
within **1.9 cm** of each other, while the room polygons built from those
faces disagree by 97.5 cm. That says the geometry is sound and the partition
into rooms is not.

**The footprint gate, at every tier.** The hall is an open-plan connector
taking in the corridor and laundry, and it was never measured wall by wall, so
the only multi-room property has no truth footprint to compare against.

**The photo repeat pair.** `bedroom_2_repeat` is a repeat capture and is left
out of the stitch, so it has no plan of its own to compare against
`bedroom_2`. The video repeat pair does have both and fails.

## How to check any number here

```bash
scripts/regenerate_all.sh          # rebuilds every reported number
scripts/regenerate_all.sh --quick  # skips the parts needing model weights
```

Every figure in the technical report names the file it comes from and the
script that rebuilds it. Where a plan was reused rather than recomputed,
`docs/benchmark/provenance.json` says so and records whether its input still
hashes the same.
