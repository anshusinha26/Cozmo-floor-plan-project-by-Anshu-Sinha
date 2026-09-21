# Cozmo technical report

Handheld phone capture to a dimensioned floor plan. Every number below comes
from a file in this repository and names the script that rebuilds it. Nothing
reads PENDING: a quantity never measured says so, and why.
`scripts/regenerate_all.sh` rebuilds all of it.

---

## 1. Architecture

One contract, one backend, three front ends.

**The contract first.** `cozmo/contracts/models.py` defines the plan. No
dimension is ever a bare number: every `*_m`, `*_m2` and `*_deg` field is a
`Measurement` with `value`, `ci_low`, `ci_high`, `unit`, `method` and
`ci_level`, and a test fails on any bare number in emitted JSON. Referential
integrity is checked at load, so the evaluator never repairs input before
scoring. The schema is generated from the models.

**The shared backend.** Tiers differ only in how they make geometry. Once a
tier has a point cloud with poses, the rest is shared: `cozmo/lidar/levels.py`
(floor and ceiling), `walls.py` (Manhattan frame, wall faces), `rooms.py` and
`cells.py` (rooms), `openings.py` (doors, adjacency), `uncertainty.py`
(intervals), `render/plan.py`. Damage is separate and tier-agnostic.

**Provenance.** `run` writes `plan.json`, `plan.png`, `run_manifest.json`,
`drift_report.json` and `debug/`. The manifest holds a SHA-256 of every input
file the tier may read, the resolved config and its hash, the git commit, the
seed, stage timings and library versions. No wall-clock field reaches the
plan, so the same input, config and seed give a byte-identical `plan.json`,
which is how the benchmark checks a reused plan.

**Tier isolation is enforced in code**, not convention: every access goes
through `StrayScan.open`, which raises on a file the tier may not read. The
video tier sees only `rgb.mp4`, and the photo tier is refused a scan folder
because `depth/` holds png files that would pass as room photos
(`tests/test_stray.py`).

## 2. Tiers and devices

| tier | input | reconstruction | median wall error against tape |
|---|---|---|---|
| lidar | one Stray Scanner scan for the whole property | classical geometry, no trained model | no tape ground truth exists |
| photo | 2 to 8 stills per room | MapAnything poses, camera-height scale, same backend | **2.2%**, worst 31.9% |
| video | one clip per room | COLMAP SfM in chunks, camera-height scale, same backend | **32.9%**, worst 137.4% |

Wall errors from `docs/benchmark/eval.json`, rebuilt by
`scripts/benchmark_all.py`, over 12 photo and 16 video walls with tape.
**Neither image tier is accurate enough to ship**, though photo is within
reach: 8 of 12 photo walls fall inside the 8% budget against none of 16 video
walls inside 3%. Gates are scored **per tier**
(`docs/benchmark/benchmark.md`): pooling lets a tier with large errors and many
walls swamp one with few small ones, and a gate with nothing to score reads NOT
EVALUATED, never PASS. Photo and video each pass the structural gates
(adjacency, overlap) and no dimensional one. **Every lidar
gate reads NOT EVALUATED**: the supplied scans are of a property nobody
measured and no iPhone was available to scan the rooms that were, so the
tier's only evidence is cross-capture agreement, **1.9 cm** between wall faces
two scans both saw.

### A regression found by measuring, and its cause

The photo tier first scored better on **compressed copies** of the photographs
than on the **camera originals**, the wrong way round. They are the same
pictures, matched at correlation 1.000, 9 of 9 in every room. The cause was
the focal length: MapAnything estimates one when not given one, and on the
originals guessed **464 px against a true 332 px**, a 46 degree field of view
where the camera has 76. Too long a focal pushes the scene apart sideways
while the camera-height prior pins the heights, which is the signature seen:
ceilings right, walls 33 to 47% long. The compressed copies scored better only
because the guess landed nearer the truth on soft images.

Ablation on `bedroom_2` (`fix_loop/loop2_video_scale/photo_ablation.md`),
against a tape of 388.6 and 363.2 cm: with the model estimating the focal the
walls came out 532.3 and 432.4 cm, **+46.6% and +11.3%**; downscaling to
1600 px left the estimate unchanged at 464 px; **giving it the EXIF focal**
gave 458.6 and 392.2 cm, **+26.3% and +0.9%**. Across twelve walls the fix
took the tier from 22.4% to **13.0%** median error and coverage from 0.69 to
0.88. Downscaling changes nothing; giving the model the focal is the fix. The
control is the Nokia 8.1, which writes a focal in millimetres but no 35 mm
equivalent, so it gets no intrinsics and the model still guesses. It is the
one camera whose rooms did not improve.

**Stray Scanner format.** `rgb.mp4` 1920x1440 HEVC 60 fps stored rotated;
`depth/` 256x192 uint16 mm; `confidence/` 0, 1, 2 with only 2 used;
`odometry.csv` camera-to-world poses, quaternions x, y, z, w, intrinsics
scaled by 256/1920 for depth; unprojection in OpenCV convention. Getting it
wrong is silent, so a test pins the floor of `c00a170fe1` at world
y = -1.48 m within 2 cm (`tests/test_stray.py`).

**Devices.** Nokia 8.1 shot every video loop and the `bedroom_2_repeat`
stills, Moto Edge 50 Neo the rest. **No iPhone was available for capture**, so
every lidar result comes from the three supplied scans and the lidar capture
route was never walked on our own device (`docs/device_matrix.md`).

**Runtime** on an M1 Max: lidar 4.0, 13.2 and 27.8 s for 1715, 5251 and 9745
frames against a 3 minute budget; video about 8 minutes a clip, photo 226 s
for four rooms (`docs/benchmark/provenance.json`).

### Video tier: what was rejected and why

**MapAnything was tested and rejected as a metric source**
(`docs/experiments/mapanything/result.json`): the median ratio of predicted to
lidar depth is 0.712, 0.704 and 0.709 over three runs, standard deviation 0.09
to 0.13, so a fixed correction leaves about 13% spread. Feeding it ARKit poses
would likely have fixed the scale and was refused: a video result from
lidar-derived poses measures the lidar tier. It is kept for relative poses
across a chunk seam.

### What the video tier actually does

COLMAP structure from motion in **chunks**, not over the whole walk: a
50-second sweep rarely registers as one reconstruction, and a failed chunk
costs seconds of video rather than the room. Chunks join by **floor-plane
bridging**, MapAnything giving only the relative pose across the seam.
**Scale comes from the camera-height prior**, each chunk scaled so its camera
sits 1.40 m above its own floor, with Depth Pro a **weak second opinion**
checking the scale rather than setting it. The room is fitted as a **single
room around the camera path**, because segmenting free space from a partly
reconstructed floor finds nothing or a fragment. Section 6 says why the result
is 32.9%.

## 3. Drift handling

ARKit odometry drifts slowly: yaw creeps and floor height wanders over minutes
of walking, smearing wall faces and breaking the floor into a wedge.
`cozmo/lidar/drift.py` anchors to the building, not the trajectory. Per
5-second chunk: the dominant wall azimuth modulo 90 degrees gives a yaw error
against the global Manhattan direction, removed by rotating about the chunk's
centroid; the median height of its floor points gives a vertical offset; then
its wall points shift onto the nearest global faces. Corrections beyond
configured limits are rejected, because a chunk that looks 20 degrees off
usually has too little wall to estimate from.

**The ablation says it barely matters here**
(`fix_loop/after/bench/runs/*/drift_report.json`):

| scan | wall thickness off | on | footprint off | on |
|---|---|---|---|---|
| c00a170fe1 | 24.2 mm | 23.6 mm | 55.4 m2 | 35.8 m2 |
| 1a8384c3f6 | 32.1 mm | 35.8 mm | 80.0 m2 | 86.6 m2 |
| c7d28f72c6 | 32.5 mm | 32.6 mm | 65.8 m2 | 64.7 m2 |

Thickness improves on one scan, worsens on another and is unchanged on the
third, because the corrections are tiny: mean yaw error 0.55 to 1.57 degrees,
mean height error 3 to 8 mm. **ARKit's poses were already good enough that
there was little to correct.** Room overlap does fall consistently, and it
stays on because it costs one pass and does no harm. The video tier's drift
problem is different, its chunks disagreeing about scale rather than
orientation; section 6 covers it.

## 4. Error budget

Every interval is built from named terms in `cozmo/lidar/uncertainty.py`.

**Wall length.** Statistical: each bounding face's position error is its
residual spread over an effective sample size counting 0.25 m patches, never
raw points, because points 2 cm apart on one wall are not independent
measurements. Systematic: a 1% depth scale bias scaling with length, plus a
1 cm floor. Half width `1.96 * sqrt(sa^2 + sb^2 + (bias * L)^2)`. On the lidar
scans the median interval is 2.4% of length.

**Ceiling height.** Per 25 cm cell, ceiling mean minus the floor plane
beneath, reported as the median. **The spread is deliberately not divided by
the square root of the cell count**: cells are not independent samples, and
sub-millimetre precision from a handheld scan is the confident garbage the
grading penalises. Under 15% coverage no number is invented: a 2.2 to 3.2 m
prior with method `prior_no_ceiling_observed` and a warning. It is the weakest
quantity at both image tiers, 2.1 to 10.7 cm error at photo and 27.2 to
63.3 cm at video against a 1.5 cm gate.

**Areas** propagate from edge lengths in quadrature. **Partially observed
rooms** have intervals doubled and say so in the method string. **Damage
extent** with depth is the box projected on the surface; without depth it is
`unbounded_no_metric_depth`, 0 to 4 m2.

### Ground truth, and its limits

The error budget is only as good as what checks it:

* **The supplied lidar scans have no ground truth.** Nobody measured that
  property, so no lidar accuracy number exists or is given.
* **Own rooms: tape, centimetres to the nearest inch.**
  `truth_uncertainty_m` is 0.013 and the coverage check widens the truth by it,
  so a pipeline is not marked wrong for beating the reference.
* **The hall is scored on ceiling, openings and adjacency only**
  (`score_walls: false`): an open-plan connector with no measurable wall run.
* **Four windows are `present_unmeasured`**: neither hit nor phantom, no
  calibration item. **Staged damage is two A4 sheets**, recorded as
  `extent_m2_upper_bound: 0.0624`, a bound on the mark rather than the mark.

## 5. Calibration analysis

Calibration is scored separately from accuracy, in `cozmo/eval/calibration.py`:
empirical coverage against the nominal 95%, mean interval width as a
percentage of value, and a "confident garbage" count, meaning the truth falls
outside an interval narrower than the median for its quantity type. The
median is per quantity because widths in metres and in square metres are not
comparable.

Measured over every capture with tape, from `docs/benchmark/eval.json`:

| group | n | coverage | mean width, % of value | confident garbage |
|---|---|---|---|---|
| all | 37 | **0.95** | 250 | 2 |
| photo | 16 | 0.88 | 42 | 2 |
| video | 21 | 1.00 | **409** | 0 |

**The photo tier is roughly calibrated; the video tier is not, and looks
better only because it says less.** Photo covers 0.88 with intervals wide in
proportion to what a handheld photo reconstruction knows, and two
confident-garbage cases, both wall lengths wrong with an interval too narrow
to admit it. Video covers 1.00 with intervals averaging **409% of value**: a
wall reported as 6.6 m plus or minus 5 m contains the tape reading and tells
nobody anything. That is not knowing its error, it is refusing to commit.

The lidar tier contributes no coverage, the supplied scans having no tape.
What it contributes is refusal: two of three scans report ceiling height as a
2.2 to 3.2 m prior rather than a number, and every room in the largest is
flagged partially observed with doubled intervals.


## 6. The fix loops

Three loops were run. None reached what it predicted, and all three are
reported as they came out.

### Loop 1: cross-capture repeatability (`fix_loop/`)

**Declared:** 0 of 112 wall rows within tolerance on two lidar captures of one
apartment, the worst gate. Hypothesis: the room partition grows from observed
floor and the walked path, so it follows the operator, not the building.
Predicted after: 40% of rows within tolerance.

**The eval was broken first.** Plans are emitted in the ARKit world frame, so
the captures sat 58 degrees apart, no quarter turn aligned them and every wall
pair failed the parallel test. Fixed by canonicalising each plan to its own
Manhattan frame, before the BEFORE run.

**The falsifier fired.** Dropping ghost faces alone, the cheap test the
declaration named, moved nothing: about 1% of face length is rejected and the
gate stayed at 0. The declaration's own evidence had over-counted ghosts at
16%, measuring faces against an envelope built from the polygons under test.

**The fix shipped and did not work.** Wall-driven cell complex segmentation
supported from the 1.0 to 1.6 m band: still 0 rows, rooms paired across the
captures fell from 6 to 3, footprints inflated. Three of four predictions
wrong. `erosion` is the default again.

**The cause was coverage**, the third falsifier: only **56% and 37%** of each
capture's wall-face length has any counterpart in the other. From
`fix_loop/evidence/evidence.json`, the two captures disagree by **1.9 cm**
median on wall face position and **97.5 cm** median on polygon edge length.
The geometry agrees to two centimetres; the partition into rooms does not, and
no rule can invent a wall one capture never saw.

### Loop 2: video-tier metric scale (`fix_loop/loop2_video_scale/`)

**Declared:** the metric scale came from a monocular depth model and was wrong.
Eight predictions, **two met**: every clip now produces a plan where three of
six produced nothing, and the share of the sample scan reaching the output went
30% to 70%. **Six missed.** Median wall error went **54.8% to 35.3%** against a
predicted 8 to 20%, nothing reached the 3% gate, and two captures of one bedroom
disagreed **more** than before, 198% and 145% against 107% and 143%. **Three of
five falsifiers fired.** Two causes the diagnosis missed:

* **The prior only works when the floor plane is right.** A chunk seeing almost
  no floor fits a plane that is not the floor and scales confidently to it: two
  bridged chunks landed at 0.148 and 0.247 m per SfM unit, 67% apart, both set
  by the prior. The error stopped being a shared bias and became random.
* **The rooms were never measured at all.** A face counted as a wall only above
  1.5 m, **inherited from the lidar tier**. A phone at 1.4 m pointed level never
  reconstructs that high: on one clip all eight faces topped out between 0.72
  and 1.46 m, none qualified, and the room came back as the path in a box.

**Iteration 2 was declared, tried and rejected**: frames through the photo
reconstruction were predicted to give 3 to 12% error and gave +69% then -36%.
**The finding that matters most is not about scale.** Nine composed stills of
`bedroom_2` gave walls within about 1% where fifty seconds of video of the same
room gave 53% and 66%, on the same prior and fitter. **The difference is the
capture**, and the protocol now recommends photographs over video.

### Loop 3: the photo tier's unanchored wall (`fix_loop/loop3_photo_unanchored_wall/`)

**Declared:** three room sides found a supported wall face; the fourth was
closed at the camera path plus a margin, which overshoots whenever the
photographer did not stand against that wall. Five predictions, **four met**.

| prediction | actual | met |
|---|---|---|
| walls within the 8% gate: 7 to 9 of 12 | 8 of 12 | yes |
| sides anchored to evidence: 19 or 20 of 20 | 20 of 20 | yes |
| bedroom_2 long axis inside the band | +3.1% | yes |
| kitchen unchanged | unchanged | yes |
| bedroom_1 long axis 380 to 430 cm | 334.8 cm, **-14.4%** | no |

**bedroom_1 flipped sign**, 20.9% long to 14.4% short: the outermost density
peak there is inside the true wall, a wardrobe front or a curtain proud of it,
which the fitter cannot tell from the wall. **Kitchen was the control and it
held**, all four sides already anchored and the loop not touching anchored
sides; it is still 31.9% long because the rule takes the outermost qualifying
face and the one it takes has 1584 points, the fewest found. The first attempt
searched only beyond the camera path and anchored nothing: on bedroom_2 the
path runs 0.61 m **past** the room's own wall, a stretched reconstruction
carrying the cameras out with it.

## 7. Known failure modes

**Measured.**

* **The video tier is not accurate enough to ship**, 32.9% median wall error
  against a 3% budget. Photo reaches 2.2% against 8%, but its worst wall is
  31.9%, so the median flatters it. Photo intervals are close to calibrated at
  0.88 coverage; two confident-garbage cases remain.
* **The photo stitcher recorded its transform twice**, in the geometry and
  again as a placement, so applying the contract stacked every room: 28.01 m2
  overlap against a 0.05 m2 gate while the tier's own report said 0.0000.
  Found by the two disagreeing; fixed, now passing.
* **Openings are not found.** 0 of 7 within 2 cm at both image tiers, by
  absence rather than inaccuracy: **nothing matched**, 0 against 6 missed and
  1 phantom at photo, 0 against 7 missed at video.
* **Cross-capture repeatability fails at every tier**: 0 of 153 rows on the
  lidar pair, 0 of 8 on the same-device video pair. **Ceiling height** fails
  everywhere, and is unavailable on two of three lidar scans.
* **Damage precision on photos**: 8 to 15 false regions in a room with 2
  marks, from 63 before filtering; on lidar the same filters reach 0 from 106,
  because two of four need depth and poses. Cracks are most at risk.
  Segmentation over-segments: 11 rooms on a flat with 6 or 7.

**Hazards in the real captures**, with evidence in `docs/hazards.md`. Glass
and a wardrobe mirror return confident depth for a room that is not there: the
damage filters handle them, reconstruction does not. Also measured there: a dog
crossing a capture, glossy tiles thickening the floor peak, textureless walls
returning sparsely, and an unobserved ceiling, the commonest cause of a wide
interval and purely a protocol problem.

**Assumptions that will break.** Manhattan turns a curved wall into a missing
face, the safer failure but a failure. Image-tier scale assumes the phone near
1.4 m, so a waist-height capture is undetectably wrong by the height ratio.
