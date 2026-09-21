# Cozmo technical report

Handheld phone capture to a dimensioned floor plan with damage annotations.

Every number below comes from a file in this repository and names the script
that rebuilds it. Anything not yet measured is marked PENDING with what it
waits on. `scripts/regenerate_all.sh` rebuilds all of it.

---

## 1. Architecture

One contract, one backend, three front ends.

**The contract first.** `cozmo/contracts/models.py` defines the plan. No
dimension is ever a bare number: every `*_m`, `*_m2` and `*_deg` field is a
`Measurement` with `value`, `ci_low`, `ci_high`, `unit`, `method` and
`ci_level`. A test walks emitted JSON and fails on any bare number.
Referential integrity is checked at load, so a plan that parses has a
consistent graph and the evaluator never repairs input before scoring it. The
schema is generated from the models, so the two cannot drift.

**The shared backend.** Tiers differ only in how they make geometry. Once a
tier has a point cloud with poses, the rest is shared: `cozmo/lidar/levels.py`
(floor and ceiling), `walls.py` (Manhattan frame, wall faces), `rooms.py` and
`cells.py` (rooms), `openings.py` (doors, adjacency), `uncertainty.py`
(intervals), `render/plan.py`. Damage is separate and tier-agnostic.

**Provenance.** `run` writes `plan.json`, `plan.png`, `run_manifest.json`,
`drift_report.json` and `debug/`. The manifest holds a SHA-256 of every input
file the tier may read, the resolved config and its hash, the git commit, the
seed, stage timings and library versions. The plan holds no wall-clock field,
so the same input, config and seed give a byte-identical `plan.json`.

**Tier isolation is enforced in code, not by convention.** Every file access
goes through `StrayScan.open`, which raises on a file the tier may not read:
the video tier sees only `rgb.mp4`, the photo tier is refused a scan folder
outright because `depth/` holds png files that would otherwise pass as room
photos. The run manifest hashes only the permitted files, so provenance never
touches data the tier could not have used (`tests/test_stray.py`).

---

## 2. Tiers and devices

| tier | input | reconstruction | median wall error against tape |
|---|---|---|---|
| lidar | one Stray Scanner scan for the whole property | classical geometry, no trained model | no tape ground truth exists |
| photo | 2 to 8 stills per room | MapAnything poses, camera-height scale, same backend | **1.4%**, worst 21.5% |
| video | one clip per room | COLMAP SfM in chunks, camera-height scale, same backend | **32.9%**, worst 137.4% |

Wall errors from `docs/benchmark/eval.json`, rebuilt by
`scripts/benchmark_all.py`, over 12 photo walls and 16 video walls with tape
readings. The photo tier is an order of magnitude better than the video tier
on the same rooms with the same scale cue and the same room fitter; section 6
explains why.

**Stray Scanner format.** `rgb.mp4` 1920x1440 HEVC 60 fps stored rotated;
`depth/` 256x192 uint16 millimetres; `confidence/` 0, 1, 2 with only 2 used;
`odometry.csv` camera-to-world poses, quaternions x, y, z, w, per-frame
intrinsics scaled by 256/1920 for depth. Unprojection is OpenCV convention.
Getting it wrong is silent, so a regression test pins the floor of
`c00a170fe1` at world y = -1.48 m within 2 cm (`tests/test_stray.py`).

**Devices.** Nokia 8.1 shot every video loop and the `bedroom_2_repeat`
stills; Moto Edge 50 Neo shot the other stills. EXIF make and model were
stripped, so attribution is the operator's record and the files say so.
**No iPhone was available for capture**: every lidar result comes from the
three supplied scans, so the lidar capture route is written from the format
and has not been walked through on our own device (`docs/device_matrix.md`).

**Runtime** on an M1 Max: lidar 4.0, 13.2 and 27.8 s for 1715, 5251 and 9745
frames, against a 3 minute budget. Video is about 8 minutes a clip and photo
77 s for four rooms (`docs/benchmark/provenance.json`).

### Video tier: what was rejected and why

**MapAnything was tested and rejected as a metric source**
(`docs/experiments/mapanything/result.json`). Image-only inference on
`c00a170fe1` at 20, 40 and 80 frames: the median ratio of predicted depth to
lidar depth is 0.712, 0.704 and 0.709, standard deviation 0.09 to 0.13. A
fixed correction would leave about 13% residual spread, so it is a systematic
error with per-frame noise on top, not a calibration.

Feeding it ARKit poses would likely have fixed the scale, and was refused: a
video result obtained from lidar-derived poses measures the lidar tier. It is
kept for one job it is good at, relative poses across a chunk seam.

### What the video tier actually does

COLMAP structure from motion over frames sampled from the clip, run in
**chunks** rather than over the whole walk: a 50-second sweep rarely
registers as one reconstruction, and a chunk that fails then costs a few
seconds of video instead of the room. Chunks are joined by **floor-plane
bridging**, which aligns consecutive chunks on the floor they share and uses
MapAnything only for the relative pose across the seam.

**Scale comes from the camera-height prior**, not from a depth model: each
chunk is scaled so its own camera sits 1.40 m above its own floor. Depth Pro
runs as a **weak second opinion** and is used to sanity-check that scale, not
to set it. The room is then fitted as a **single room around the camera
path**, because segmenting free space out of a partly reconstructed floor
either finds nothing or finds a fragment and calls it the room.

Measured: median wall error 32.9% over 16 walls. Section 6 says why that is
still far off, and what it is not caused by.

---

## 3. Drift handling

ARKit odometry drifts slowly: yaw creeps and floor height wanders over a few
minutes of walking, which smears wall faces and breaks the floor into a wedge.

`cozmo/lidar/drift.py` anchors to the building, not the trajectory. The walk
is cut into 5-second chunks. Per chunk: the dominant wall azimuth modulo 90
degrees gives a yaw error against the global Manhattan direction, removed by
rotating about the chunk's own centroid; the median height of its floor points
gives a vertical offset; then its wall points shift along each axis by the
median offset to the nearest global face. Corrections beyond configured limits
are rejected, because a chunk that looks 20 degrees off usually has too little
wall to estimate from.

**The ablation says it barely matters here**
(`fix_loop/after/bench/runs/*/drift_report.json`):

| scan | wall thickness off | on | footprint off | on |
|---|---|---|---|---|
| c00a170fe1 | 24.2 mm | 23.6 mm | 55.4 m2 | 35.8 m2 |
| 1a8384c3f6 | 32.1 mm | 35.8 mm | 80.0 m2 | 86.6 m2 |
| c7d28f72c6 | 32.5 mm | 32.6 mm | 65.8 m2 | 64.7 m2 |

Thickness improves on one scan, worsens on another, unchanged on the third.
The model summary says why: mean yaw error 0.55 to 1.57 degrees, mean height
error 3 to 8 mm, mean shift 1.4 to 2.2 cm. **ARKit's poses were already good
enough that there was little to correct.** Room overlap does fall
consistently. It stays on because it costs one pass and does no harm; that is
the whole case for it.

The video tier has its own drift problem and it is not this one: chunks
disagree about scale, not orientation, which section 6 covers.

---

## 4. Error budget

Every interval is built from named terms, defined in
`cozmo/lidar/uncertainty.py`.

**Wall length.** Statistical: each bounding face's position error is its
residual spread over an effective sample size counting 0.25 m patches, never
raw points, because points 2 cm apart on one wall are not independent
measurements. Systematic: a 1% depth scale bias scaling with length, plus a
1 cm floor. Half width `1.96 * sqrt(sa^2 + sb^2 + (bias * L)^2)`, floored at
1 cm. On the lidar scans the median interval is 2.4% of length.

**Ceiling height.** Per 25 cm cell, ceiling mean minus the floor plane
beneath, reported as the median. Half width combines cell spread with the
depth scale term. **The spread is deliberately not divided by the square root
of the cell count**: cells are not independent samples, and sub-millimetre
precision from a handheld scan is exactly the confident garbage the grading
penalises. Under 15% ceiling coverage no number is invented: a 2.2 to 3.2 m
prior with method `prior_no_ceiling_observed` and a warning. Two of three
lidar scans take that path; the third measured 3.06 to 3.08 m across rooms.

Ceiling height is the weakest measured quantity at every tier: errors run
11.9 to 85.8 cm at the photo tier and 27.2 to 63.3 cm at the video tier,
against a 1.5 cm gate (`docs/benchmark/eval.json`).

**Areas** propagate from edge lengths in quadrature over the two axes.
**Partially observed rooms** have length and area intervals doubled and say so
in the method string. **Damage extent** with depth runs from a contrast
estimate to the box projected on the surface; without depth it is
`unbounded_no_metric_depth`, 0 to 4 m2, with a warning.

### Ground truth, and its limits

The error budget is only as good as what checks it:

* **The supplied lidar scans have no ground truth at all.** Nobody measured
  that property, so no lidar accuracy number exists or is given.
* **Own rooms: tape, centimetres to the nearest inch.**
  `truth_uncertainty_m` is 0.013 and the coverage check widens the truth by
  it, so a pipeline is not marked wrong for beating the reference.
* **The hall is scored on ceiling, openings and adjacency only**
  (`score_walls: false`): an open-plan connector with no measurable wall run.
* **Four windows are `present_unmeasured`**: neither hit nor phantom, and no
  calibration item.
* **Staged damage is two A4 sheets**, recorded as
  `extent_m2_upper_bound: 0.0624`, a bound on the mark rather than the mark.

---

## 5. Calibration analysis

Calibration is scored separately from accuracy, in `cozmo/eval/calibration.py`:
empirical coverage against the nominal 95%, mean interval width as a
percentage of value, and a "confident garbage" count, meaning the truth falls
outside the interval and that interval is narrower than the median for its
quantity type. The median is per quantity because widths in metres and in
square metres are not comparable. Broken down by tier and by quantity.

Measured over every capture with tape, from `docs/benchmark/eval.json`:

| group | n | coverage | mean width, % of value | confident garbage |
|---|---|---|---|---|
| all | 37 | 0.97 | 251 | 1 |
| photo | 16 | 0.94 | 43 | 1 |
| video | 21 | 1.00 | 409 | 0 |
| photo, wall length | 12 | 1.00 | 42 | 0 |
| photo, ceiling height | 4 | 0.75 | 44 | 1 |
| video, wall length | 16 | 1.00 | 519 | 0 |
| video, ceiling height | 5 | 1.00 | 57 | 0 |

**Both tiers over-cover**, and they do it for opposite reasons. The photo
tier reaches 0.94 with intervals about 43% of the value: wide, but in
proportion to how much a handheld photo reconstruction actually knows. The
video tier reaches 1.00 with intervals averaging **409% of the value**, which
is not calibration but an interval so wide it cannot be wrong. A wall
reported as 6.6 m plus or minus 5 m contains the tape reading and tells
nobody anything.

That is the honest reading of the calibration score: the video tier is not
being rewarded for knowing its own error, it is being rewarded for saying
almost nothing. The one confident-garbage case is a photo-tier ceiling.

The lidar tier contributes no coverage, because the supplied scans have no
tape. What it does contribute is refusal: two of three scans report ceiling
height as a 2.2 to 3.2 m prior rather than a number, and every room in the
largest is flagged partially observed with doubled intervals.

---

## 6. The fix loops

Two loops were run. Both are negative results and both are reported as such.

### Loop 1: cross-capture repeatability (`fix_loop/`)

**Declared:** worst gate repeatability, 0 of 112 wall rows within tolerance on
two lidar captures of one apartment. Root cause hypothesis: room partition is
unstable because it grows from observed floor and the walked path, so it
follows the operator rather than the building. Predicted after: 40% of rows
within tolerance.

**The eval was broken first.** Plans are emitted in the ARKit world frame, so
the two captures sat 58 degrees apart and no quarter turn aligned them. Every
wall pair failed the parallel test. Fixed by canonicalising each plan to its
own Manhattan frame before the search, in commits before the BEFORE run.

**The falsifier fired.** Dropping ghost faces alone, the cheap test named in
the declaration, moved nothing: about 1% of face length is rejected and the
gate stayed at 0. That also showed the declaration's own evidence had
over-counted ghosts at 16%, because it measured faces against an envelope
built from the polygons under test.

**The fix shipped and did not work.** Wall-driven cell complex segmentation
with support from the 1.0 to 1.6 m band. Still 0 rows within tolerance, rooms
paired across the captures fell from 6 to 3, footprints inflated. Three of
four predictions wrong. `erosion` is the default again.

**The cause was coverage**, the third falsifier: only **56% and 37%** of each
capture's wall-face length has any counterpart in the other. The contrast
that carries it, from `fix_loop/evidence/evidence.json`:

| measured at | disagreement between the two captures |
|---|---|
| wall face position | **1.9 cm** median |
| polygon edge length | **97.5 cm** median |

The geometry agrees to two centimetres. The partition into rooms and edges
does not, and no rule can invent a wall one capture never saw.

### Loop 2: video-tier metric scale (`fix_loop/loop2_video_scale/`)

**Declared:** the video tier's metric scale came from a monocular depth model
and was wrong. Eight predictions were written down before any fix code.

**Two came true.** Every clip now produces a plan, where three of six produced
nothing. The share of the sample scan reaching the output went from 30% to
70%, accepted bridges from 2 of 6 to 4 of 6.

**Six did not.** Median wall error went from **54.8% to 35.3%**, against a
predicted 8 to 20%. Nothing reached the 3% gate. The two captures of one
bedroom, which should have agreed once both were pinned to the same prior,
disagreed **more** than before: 198% and 145% per wall against 107% and 143%.
**Three of five falsifiers fired.**

Two things the diagnosis missed:

* **The prior only works when the floor plane is right.** A chunk covering a
  few seconds of sweep that sees almost no floor fits a plane that is not the
  floor, and the prior then scales confidently to the wrong thing. On one clip
  two bridged chunks landed at 0.148 and 0.247 metres per SfM unit, a 67%
  disagreement, both set by the prior. Repeatability got worse because the
  error stopped being a shared bias and became random, and random errors do
  not cancel between two captures.
* **The rooms were never measured at all.** A face counted as a wall only if
  it reached 1.5 m above the floor, a threshold **inherited from the lidar
  tier**. A phone carried at 1.4 m and pointed level or down never
  reconstructs that high. On one clip all eight faces topped out between 0.72
  and 1.46 m, none qualified, and the room came back as the camera path in a
  box. That was true for every clip in loop 1, and it should have been found
  by looking at what the room fitter was using before the fix was designed.

**Iteration 2 was declared, tried and rejected.** Running the clip's frames
through the photo tier's reconstruction was predicted to give 3 to 12% median
error; at 16 frames it gave +69% and +63%, at 24 frames it gave -36% and -34%.
SfM remains the default.

**The finding that matters most is not about scale.** Nine composed stills of
`bedroom_2` through the photo path, with the same height prior and the same
room fitter, give walls within about 1%. Fifty seconds of video of the same
room through SfM gives 53% and 66%. Same scale cue, same fitter, same tape.
**The difference is the capture, not the algorithm**: nine deliberate stills
from the corners beat a continuous walk, because the walk never holds a
viewpoint long enough to triangulate a wall well. That is a capture-protocol
finding, and it is reflected in `docs/capture_protocol.md`.

## 7. Known failure modes

**Measured.**

* **The video tier is not accurate enough to ship.** 32.9% median wall error,
  worst 137.4%, and intervals averaging 409% of the value.
* **Cross-capture repeatability fails at every tier.** 0 of 153 rows on the
  lidar pair, 0 of 8 on the same-device video pair.
* **Ceiling height fails at every tier**, 11.9 to 85.8 cm against a 1.5 cm
  gate, and is unavailable entirely on two of three lidar scans.
* **Damage precision on photos.** 8 to 15 false regions in a room with 2
  marks, from 63 before filtering; on a lidar capture the same filters reach
  0 from 106. Two of the four filters need depth and poses.
* **Cracks are the class most at risk**: the verifier that removes false
  positives removes the crack at threshold 0.20, so 0.15 ships.
* **Room segmentation over-segments**: 11 rooms on a flat with perhaps 6 or 7.

**Hazards in the real captures** (`docs/hazards.md`, each with evidence).
Glass and a wardrobe mirror return confident depth for a room that is not
there; the damage filters handle them, reconstruction does not. A dog walked
through one capture. Glossy tiles thicken the floor peak. Textureless white
walls give sparse returns, part of why coverage differs so much between two
walks of one flat. An unobserved ceiling is the commonest cause of a wide
interval and is purely a protocol problem.

**Assumptions that will break.** Manhattan: a curved or 45 degree wall appears
as a missing face rather than a wrong one, the safer failure but still a
failure. Video and photo scale depends on the phone being held near 1.4 m; a
clip shot at waist height is wrong by the ratio of heights and nothing in the
pipeline can detect it.
