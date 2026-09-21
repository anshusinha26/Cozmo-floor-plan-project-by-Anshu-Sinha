# Status, main branch

Updated at the end of every stage. Newest stage last.

## Stage A: close fix loop 1

Done.

* Default segmentation is `erosion` again. `--segmentation cells` still
  selects the wall-driven cell complex. The default is recorded in the
  resolved config, so it is part of the run manifest hash.
* Two improvements from the loop carried back into the erosion path:
  collinear polygon edges are collapsed, and rooms whose outline is under 80%
  backed by observed wall are flagged partially observed with doubled
  intervals.
* `fix_loop/README.md` states the loop as an honest negative result and points
  at loop 2 on the video-tier branch.

Numbers on `c7d28f72c6` under the restored default: 11 rooms, 86 walls, 10 of
11 flagged partially observed, largest room 9.6 m2. Room count is unchanged
from the original erosion output; the wall count fell from 107 under cells,
and the partially observed flag is new information that the pipeline could not
report before.

Failures and open items: the cross-capture repeatability gate still fails at
0 rows within tolerance under both segmentations. Loop 1 did not fix it, and
the postmortem argues it needs a capture-protocol or gate-denominator change
rather than another algorithm.

Tests: 143 passing.

## Stage B: ground truth for the hand-measured captures

Done.

* `truth_uncertainty_m` added to the ground-truth model, set to 0.013 for
  every hand-measured file. The coverage check widens the truth by it before
  asking whether a predicted interval covers it, so a pipeline is not
  penalised for being more precise than a tape read to the nearest inch.
* `present_unmeasured` marks an opening known to exist with no reading. Such
  an opening can be neither missed nor phantom, and contributes no
  calibration item. Used for the four unmeasured windows.
* `score_walls: false` on the hall, an open-plan connector taking in the
  corridor and laundry. It is scored on ceiling height, openings and
  adjacency only; its walls are not scored at all rather than scored against
  nothing.
* Staged damage recorded as `extent_m2_upper_bound`, not as an extent: an A4
  sheet bounds the mark it stands for.
* Input conventions extended so the captures load as they are. A folder of
  photos is one room named after the folder; a folder with exactly one clip
  is one room for the video tier; a folder of such folders is several rooms.
  Tier isolation still holds: the photo tier does not see the clip sitting
  beside the images, and a Stray scan folder still exposes only rgb.mp4 to
  the video tier.

Twelve ground-truth files written and loading: five rooms plus `home`, each
at photo and video tier. Seventeen captures in the registry.

Tape readings recorded, in metres:

| room | A | B | C | D | ceiling | door |
|---|---|---|---|---|---|---|
| bedroom_1 | 3.6576 | 3.9116 | 3.6576 | 3.9116 | 2.9718 | 0.9144 x 1.9812 on A |
| bedroom_2 | 3.8862 | 3.6322 | 3.8862 | 3.6322 | 2.9718 | 0.9144 x 1.9812 on A |
| kitchen | 2.6924 | 3.6028 | 2.6924 | 3.6028 | 2.9718 | 0.8128 x 1.9812 on A |
| hall | not scored | | | | 2.9718 | three doors, 0.9144 and 1.1684 wide |

Failures and open items: none in this stage. No predictions exist for these
captures yet, because the photo and video tiers are being built on another
branch, so nothing is scored against this ground truth so far.

Tests: 155 passing. The bench test now uses a two-capture fixture registry
rather than the real one, which had grown to seventeen captures including
LiDAR scans and made the unit suite depend on gitignored data.

## Stage C: damage, concealed-damage rules, scope items

Done, and the honest result is that it is not ready for use.

Module `cozmo/damage/`, tier-agnostic: it takes an iterator of frames (image,
and optionally depth, intrinsics and pose) plus the plan's surfaces, so the
same code serves all three tiers. Detector is OWLv2
(`google/owlv2-base-patch16-ensemble`, Apache 2.0) behind an interface, with
two or three text prompts per damage class. Weights come from
`scripts/fetch_damage_weights.py`; nothing downloads during a run. Device
order cuda, mps, cpu. About 0.2 s per image on mps after a 25 s load.

* With depth, extent is an interval from a colour-contrast estimate inside the
  box to the box projected on the surface. The box bounds the mark, it is not
  the mark, so it is the upper end.
* Without depth, the region carries method `unbounded_no_metric_depth`, an
  interval from 0 to 4 m2 and a warning on the result.
* Detections of one mark across frames merge when they land within 0.35 m in
  world coordinates.
* Eight concealed-damage rules, each with id, text, evidence and a confidence
  no higher than 0.6. Nine-row scope table keyed on class and surface, with
  quantities as Measurements carrying propagated intervals and a minimum area.

Measured results, full numbers in `docs/damage_eval/README.md`:

| case | frames | detections | regions | outcome |
|---|---|---|---|---|
| own/bedroom_2_repeat, two staged A4 marks | 9 | 133 | 52 at threshold 0.20 | both classes found, 38 of 52 regions are classes not present |
| data/sample/c7d28f72c6, no known damage | 25 | 146 | 121 | 97 with measured extent, largest 2.58 m2, which is a wall not a mark |

* Hits: water_stain and crack, both staged classes.
* Misses: none at threshold 0.20 or below. The crack disappears at 0.25.
* False positives: heavy at every threshold that keeps recall. There is no
  setting that finds both planted marks without inventing dozens.

The default threshold is 0.20 because it is the only measured setting that
keeps both planted classes. The reflective and transparent surfaces in the
LiDAR scan behave as predicted: confident boxes of nothing.

Failures and open items: precision. The next steps that would help, in order,
are a depth-based planarity test to reject furniture and reflections,
requiring agreement across frames before emitting a region, and calibrating
confidence against the staged captures rather than trusting the raw score.

Tests: 11 damage tests, all running without model weights through a dummy
detector.

## Stage D: head-to-head scaffold

Done.

`benchmarks/head_to_head/arplan3d.yaml` records AR Plan 3D (Grymala) on
Android: one casual attempt per room, corners hidden by furniture estimated by
the operator, screenshots in `data/own/app_comparision`. It also records that
magicplan offers no camera scan on Android, so there is nothing to compare on
the same device, with the screenshot kept.

`cozmo/eval/head_to_head.py` plus `scripts/head_to_head.py` render the table:
tape, theirs, ours, and who is closer per dimension, with a 1.5 cm tie
threshold and a beat-or-tie percentage. Our column reads "not yet" until a
tier produces plans for these rooms; it never prints a placeholder number.

The rival's own errors against tape, which stand without our column:

| room | dimension | tape m | theirs m | their error |
|---|---|---|---|---|
| bedroom_1 | short pair | 3.658 | 3.410 | 24.8 cm |
| bedroom_1 | long pair | 3.912 | 3.730 | 18.2 cm |
| kitchen | short wall 1 | 2.692 | 2.750 | 5.8 cm |
| kitchen | short wall 2 | 2.692 | 2.700 | 0.8 cm |
| kitchen | long wall 1 | 3.603 | 3.510 | 9.3 cm |
| kitchen | long wall 2 | 3.603 | 3.790 | 18.7 cm |

Median 18.2 cm, worst 24.8 cm over six dimensions. Note the kitchen, where the
app reported the two opposite long walls as 3.51 and 3.79 m, a 28 cm
difference between walls that are the same wall run.

Failures and open items: our column cannot be filled on this branch. The photo
and video tiers are being built elsewhere; `scripts/head_to_head.py --plans
<dir>` fills it as soon as plans for these rooms exist.

Tests: 161 passing.

## Stage A (task 6): damage precision

Done. Two of three targets met, and the miss is structural rather than a
tuning failure.

Four filters added, each switchable so its effect is measured rather than
asserted: distractor prompts, a geometry test against the plan's surfaces, a
multi-view requirement, and a SigLIP crop verifier.

| case | raw false regions | after all four | staged marks kept |
|---|---|---|---|
| own/bedroom_2_repeat photos, threshold 0.15 | 63 | **9** | both |
| clean LiDAR scan, threshold 0.15 | 106 | **0** | n/a, no damage present |

| target | result |
|---|---|
| both staged marks still found | met at threshold 0.15 |
| under 5 false regions in bedroom_2_repeat | not met, 9 |
| under 5 false regions on the clean LiDAR scan | met, 0 |

What each filter is worth: distractor prompts almost nothing (93 to 91 on
photos, 106 to 104 on LiDAR); geometry a third of LiDAR boxes and nothing on
photos; multi-view 72 to 26 on LiDAR and nothing on photos; the crop verifier
26 to 0 on LiDAR and 91 to 27 on photos. The verifier does the work.

Failures and open items: two of the four filters need depth and poses, so the
photo case gets no benefit from them, which is why it is the one that misses.
The multi-view rule cannot be applied to photo folders as specified, because
without poses there is no way to know whether a mark was visible in another
photo. The crop verifier costs recall: at threshold 0.20 it removes the crack
along with the false positives, so cracks are the class most at risk. Full
tables and failure modes in `docs/damage_eval/README.md`.

Default threshold is 0.15, the setting that keeps both planted classes.

## Stage B (task 6): repeatability reporting

Done. No denominator changed.

* The official repeat pair is `bedroom_2` against `bedroom_2_repeat`,
  registered at both photo and video tier. The video pair is same-device
  (Nokia 8.1) and is the primary repeatability evidence. The photo pair is
  cross-device (Moto Edge 50 Neo against Nokia 8.1) and is labelled as such,
  because its disagreement mixes pipeline repeatability with camera
  differences.
* The two sample LiDAR scans are now labelled `coverage_mismatched`: not a
  valid repeat pair. The strict result stays visible and unchanged at 0 of 153
  rows within tolerance.
* Beneath it, a secondary statistic over the walls both captures saw, clearly
  marked as not the gate: 14 shared walls of 153 rows, median polygon-edge
  difference 76.1 cm, registered footprint IoU 0.61. And at the wall-face
  level, below the polygon, the two captures place the same wall within a
  median of 1.9 cm, with 56% and 37% of each capture's face length having any
  counterpart.

That contrast is the whole finding: the faces agree to two centimetres and
the polygon edges disagree by most of a metre, because the two captures cut
the same wall into different edges.

Devices are recorded per capture in `benchmarks/captures.yaml` and in each
ground-truth file. EXIF make and model were stripped from the supplied photos,
so device attribution is the operator's record and says so in the files.
Measured from the files themselves: photos are 1200 x 1600, videos are
3840 x 2160 H.264 at about 30 fps.

## Stage C (task 6): input robustness for the walk-in test

Done.

* HEIC and HEIF stills are accepted and decoded through pillow-heif, which is
  now a dependency. A real HEIC file is written and read back in the tests
  rather than a stub.
* `.mov`, `.m4v` and `.hevc` clips join `.mp4`.
* Extensions are matched lower-cased, so `IMG_0001.HEIC` and `clip.MOV` work.
* Sidecar files are ignored: iOS `.AAE` edit files and Finder's `.DS_Store`
  no longer count as room contents.
* A Stray Scanner export is recognised by its layout, not its folder name, so
  a renamed scan folder still loads.
* Error messages now name what was found and what is accepted, for example
  "photo tier needs at least 2 images, found 1. Accepted: .heic, .heif, .jpeg,
  .jpg, .png, any case. Folder holds: only.HEIC".

Failures and open items: none. The tests use tiny generated fixtures, so they
run without the gitignored data.

## Stage D (task 6): documents and the reproduction bundle

Done.

* `docs/capture_protocol.md`: one page, three routes, each ending in the exact
  command. Written for someone with no technical knowledge: which phone, which
  lens, what height, how far from the wall, how long, and a "what to avoid"
  list. The LiDAR route names Stray Scanner and says plainly that without
  tilting up to catch the ceiling, ceiling height falls back to a 2.2 to 3.2 m
  prior.
* `docs/device_matrix.md`: capture hardware by processing hardware by tier.
  Both Android phones are listed with what each captured and the file facts
  read from the captures themselves. Video and photo accuracy cells read
  "pending loop 2 results" and carry no invented numbers. The LiDAR row states
  that no tape ground truth exists for the supplied scans and gives the
  cross-capture agreement instead: 1.9 cm face placement, 56% and 37% face
  coverage, 0 of 153 on the strict gate.
* **No iPhone was available for capture**, stated in the device matrix. Every
  LiDAR result comes from the three supplied scans, so the LiDAR capture route
  in the protocol has been written from the format and the data and not walked
  through on our own device.
* `README.md`: clone to first plan in under 15 minutes, one command per
  capture, weights and data by script, what is and is not implemented, the two
  third-party models with their Apache 2.0 licences, and AI coding assistance
  disclosed in one line.
* Reproduction bundle: `scripts/fetch_weights.sh`, `scripts/fetch_sample_data.sh`
  and `scripts/regenerate_all.sh`, which rebuilds every reported number and has
  a `--quick` mode that skips the parts needing model weights.
* `docs/compliance_matrix.md` refreshed. Every file path in it was checked to
  exist; none are missing.

Failures and open items: the technical report is still spread across
`STATUS_main.md`, `fix_loop/POSTMORTEM.md` and `docs/damage_eval/README.md`
rather than bound into one document, and the compliance matrix says so.
`scripts/fetch_sample_data.sh` needs `COZMO_DATA_URL` set to the shared Drive
folder; it refuses with instructions rather than failing silently.

Tests: 168 passing.

## Task 7: data URL and the bound technical report

Done.

* `scripts/fetch_sample_data.sh` now defaults `COZMO_DATA_URL` to the
  assessor-supplied Drive folder and is still overridable. It downloads with
  gdown, unpacks any archives, installs each scan as
  `data/sample/<scan_id>/`, and then verifies the Stray Scanner layout: it
  checks `rgb.mp4`, `odometry.csv`, `depth/` and `confidence/` exist and that
  the depth and confidence frame counts match, naming what is missing if not.
  On the present data it reports 1a8384c3f6 5251 frames, c00a170fe1 1715,
  c7d28f72c6 9745.
* `docs/technical_report.md`: one bound document, **6 rendered pages against a
  hard limit of 6**. Sections in the required order: architecture; tiers and
  devices; drift; error budget; calibration; the fix loop; known failure
  modes.
* Every number in it was checked against the file it comes from by a script
  written for the purpose. Two did not trace and were corrected rather than
  kept: an example wall interval that came from a run made with the
  non-default segmentation, and a polygon-edge disagreement quoted as 76.1 cm
  while its cited file says 97.5 cm. The report now reads 2.4% median interval
  width and a longest wall of 4.186 m plus or minus 8.3 cm, both from the
  default-segmentation run, and 97.5 cm against 1.9 cm for the edge-versus-face
  contrast.
* Items written as PENDING with what they wait on: video and photo tier
  accuracy (loop 2 after-run and the photo tier), empirical interval coverage
  for every tier (predictions for the hand-measured rooms), and the
  head-to-head "ours" column. No placeholder numbers anywhere.
* MapAnything's rejection is now evidenced inside the repository at
  `docs/experiments/mapanything/result.json`, so the report cites a file
  rather than a memory: depth ratio 0.712, 0.704 and 0.709 across three runs,
  with the smeared top-down density image beside it.
* `scripts/build_report.sh` renders to PDF, preferring pandoc with a LaTeX
  engine, then pandoc with wkhtmltopdf, then a reportlab fallback that needs
  no system tools (`scripts/md_to_pdf.py`). It prints the page count and
  **fails if the render exceeds 6 pages**, so the limit cannot drift.

Failures and open items: pandoc is not installed on this machine, so the
shipped PDF was produced by the reportlab fallback. It is plain but complete,
and a reader with pandoc will get a better-looking document from the same
source. The technical report row in the compliance matrix is now `done`.

Tests: 168 passing.

## Task 8: walk-in rehearsal, hazards, publish hygiene

Done.

### Stage A: clean-machine rehearsal

`docs/rehearsal.md`. Fresh clone into a temporary directory, README followed
literally, every step timed.

**Clone to first plan: 2 minutes 51 seconds**, including the optional test
run, against a 15-minute target. Breakdown: clone 0.5 s, `uv sync` on a cold
cache 11.2 s, tests 43.5 s, the real Drive download of all three scans 96.4 s,
first plan 19.0 s. The largest scan takes 33.5 s.

A run with the network off, proxy pointed at a dead port and `HF_HUB_OFFLINE`
set, completed in 5.6 s and produced a **byte-identical** plan. Nothing calls
out at run time.

**Four real failures were found by rehearsing, and all four are fixed:**

1. A test asserted the hand-measured capture folders exist, but `data/` is
   gitignored, so it failed on any fresh clone.
2. `scripts/fetch_sample_data.sh` needed `gdown`, which `uv sync` did not
   install, so a stranger hit a dead end two steps into the README.
3. That script passed `--remaining-ok`, a flag gdown 6 removed, so the
   download failed with a usage error.
4. **torch and transformers were never declared in `pyproject.toml`.** They
   had been installed by hand during development, so `uv sync` on a clean
   clone produced a venv where `scripts/fetch_weights.sh` failed on
   `No module named 'transformers'`. Fixed with a `damage` extra; the README
   now says `uv sync --extra damage`.

Only the fourth needed a design decision: the damage dependencies are now an
optional extra, because reconstruction genuinely does not need them.

### Stage B: hazards

`docs/hazards.md`, one section each with evidence or an explicit gap.

* **Glass**: 16% of wall-face length outside the room envelope on two scans,
  but that measure over-counts because the envelope comes from the polygons
  under test. The visibility test puts it near 1%. For damage, the filters
  take the shower-screen scan from 106 regions to 0.
* **Mirrors**: no number. The bedroom_2 captures could not be re-read (see
  below). The pipeline does nothing specific about mirrors; stated as a gap.
* **Glossy floors**: floor plane residual 10 to 13 mm, still a single sharp
  peak; the trimmed plane fit discards the reflection population.
* **Low light**: LiDAR is active sensing and does not depend on room light,
  and the reconstruction never reads the RGB stream at all. For the image
  detector, measured on gamma-darkened frames: detection volume is flat from
  150.6 to 65.5 mean brightness.
* **A moving dog, textureless white walls, a ceiling never observed**: each
  with what breaks and what the pipeline does.

**Blocked measurement, stated rather than worked around.** `data/own` became
unreadable partway through this session: the files carry
`com.apple.quarantine` and every read returns `Operation not permitted`, while
`data/sample` is unaffected. So whether the staged stain and crack survive
darkening is marked PENDING with the one command that answers it. Results
already derived from those photos stand and are unaffected. Nothing was
substituted silently.

### Stage C: publish hygiene

| check | result |
|---|---|
| absolute `/Users/` paths in tracked files | 0, four run logs scrubbed and `fix_loop/regenerate.sh` now scrubs as it writes |
| tracked files over 5 MB | 0 |
| secrets or tokens | none found |
| `data/` tracked | 0 files; fully ignored |
| `.DS_Store` tracked | removed, and now ignored along with other editor noise |
| LICENSE | added, MIT |
| THIRD_PARTY.md | added |

`THIRD_PARTY.md` lists every model, library, tool and dataset with its licence
and use, including the one copyleft dependency (pillow-heif, LGPL, used
unmodified through its public API) and the models evaluated and rejected.

`docs/MERGE_PLAN.md` names the eight files both branches touched, what each
side did to them, and how each should resolve. The one needing care is
`cozmo/io/inputs.py`, where both branches independently extended the same two
functions; the resolution is a union, and video-tier's more forgiving `_photo`
should win with main's error text inside it. `cozmo/pipeline/__init__.py`
takes video-tier whole, since it is a strict superset.

**Nothing was merged.**

Failures and open items: the cold-cache timing for the model weights was
attempted twice and neither attempt produced a clean number, so
`docs/rehearsal.md` quotes the measured download sizes (OWLv2 1.2 GB, SigLIP
1.5 GB) and no time. The `data/own` permission problem above blocks one hazard
measurement.

Tests: 168 passing.

## Task 9: merge, full benchmark, report filled

Done. Two merges, the second taking the photo re-run on camera originals.

### Stage A: merge

Resolved per `docs/MERGE_PLAN.md`. Four conflicts, all unions, and the plan
was right about which side should win each one. `inputs.py` took video-tier's
forgiving photo scan with main's error text; `pipeline/__init__.py` took
video-tier whole; `cli.py` and `fetch_weights.sh` took both sides.

Extras declared: `damage`, `video`, `photo` and `all`. The README now has two
install profiles, lidar-only (under three minutes to first plan) and
everything. `scripts/fetch_weights.sh` covers all five checkpoints with
measured sizes and can fetch either half.

### Stage B: benchmark

`scripts/benchmark_all.py`, output in `docs/benchmark/`. Video and photo plans
are reused from the tier branch rather than recomputed; every plan records its
source and whether its input still hashes the same. All six reused plans
verify.

| gate | result | value | threshold | n |
|---|---|---|---|---|
| opening_width | FAIL | 0 | 0.85 | 14 |
| ceiling_height | FAIL | 0.9097 | 0.015 | 9 |
| ceiling_height_diagnosis | FAIL | 0.9097 | 0.015 | 9 |
| repeatability | FAIL | 250.4 | 1 | 4 |
| wall_length_tier | FAIL | 45.82 | 1 | 28 |
| footprint | PASS | 0 | 0.08 | 0 |
| stitch_adjacency | PASS | 0 | 0 | 6 |
| stitch_overlap | FAIL | 28.01 | 0.05 | 6 |

| tier | walls | within tier budget | median error | worst |
|---|---|---|---|---|
| photo | 12 | 2 | 25.9% | 39.0% |
| video | 16 | 0 | 32.9% | 137.4% |

Interval coverage: photo 0.56 at 47% mean width with seven confident-garbage
cases; video 1.00 at 409% mean width with none. Both are badly calibrated in
opposite directions, and the video tier looks better only because its
intervals are too wide to be wrong.

Repeatability, same-device video pair (`bedroom_2` against
`bedroom_2_repeat`): 0 of 8 wall rows within tolerance.

Head to head against AR Plan 3D, 1.5 cm tie threshold:

| tier | room | dimension | tape m | theirs m | their error cm | ours m | our error cm | closer |
|---|---|---|---|---|---|---|---|---|
| photo | bedroom_1 | short_pair | 3.658 | 3.410 | 24.8 | 4.026 | 36.9 | theirs |
| photo | bedroom_1 | long_pair | 3.912 | 3.730 | 18.2 | 5.193 | 128.2 | theirs |
| photo | kitchen | short_wall_1 | 2.692 | 2.750 | 5.8 | 2.636 | 5.7 | tie |
| photo | kitchen | short_wall_2 | 2.692 | 2.700 | 0.8 | 2.636 | 5.7 | theirs |
| photo | kitchen | long_wall_1 | 3.603 | 3.510 | 9.3 | 5.007 | 140.4 | theirs |
| photo | kitchen | long_wall_2 | 3.603 | 3.790 | 18.7 | 5.007 | 140.4 | theirs |
| video | bedroom_1 | short_pair | 3.658 | 3.410 | 24.8 | 5.935 | 227.8 | theirs |
| video | bedroom_1 | long_pair | 3.912 | 3.730 | 18.2 | 4.578 | 66.6 | theirs |
| video | kitchen | short_wall_1 | 2.692 | 2.750 | 5.8 | 1.806 | 88.7 | theirs |
| video | kitchen | short_wall_2 | 2.692 | 2.700 | 0.8 | 1.806 | 88.7 | theirs |
| video | kitchen | long_wall_1 | 3.603 | 3.510 | 9.3 | 3.162 | 44.1 | theirs |
| video | kitchen | long_wall_2 | 3.603 | 3.790 | 18.7 | 3.162 | 44.1 | theirs |

**Photo beats or ties on 17% of dimensions, video on 0%.** The rival app is
better than both of our image tiers on these rooms.

The brief asks for this comparison at the lidar tier, which was impossible: no
iPhone was available, so there is no lidar scan of the rooms the rival
measured, and the supplied lidar scans are of a different property with no
tape at all.

### Stage C: report

Every PENDING replaced. Six rendered pages, enforced by
`scripts/build_report.sh`, which fails over the limit. Three rounds of cutting
were needed to fit the new material.

**The finding that changed most between the two merges:** the photo tier
scored 1.4% median wall error on compressed copies of the photographs and
25.9% on the camera originals. The originals carry EXIF the copies had
stripped, and reading the real focal length made the answer worse. Both runs
are kept and the report says it is unexplained.

### Failures and open items

* Neither image tier is accurate enough to ship. Photo misses its 8% budget on
  10 of 12 walls, video misses its 3% budget on all 16.
* The photo tier's intervals are over-confident: 0.56 coverage against 0.95.
* Repeatability fails at every tier.
* Ceiling height fails at every tier, 2.4 to 91.0 cm against a 1.5 cm gate.
* Two of eight gates pass.

Tests: 213 passing.

## Task 10: per-tier gates, full-profile rehearsal, second merge

Done. Two merges landed, both photo fixes measured.

### Gates, per tier

Pooled tables are gone from the top of the report. A gate with nothing to
score reads NOT EVALUATED with its reason and can never count as a pass.

**lidar**

**NOT EVALUATED**: no lidar capture has tape ground truth. The supplied scans are of a property nobody measured, and no iPhone was available to scan the rooms that were.

**photo**

| gate | result | value | threshold | n |
|---|---|---|---|---|
| opening_width | FAIL | 0 | 0.85 | 7 |
| ceiling_height | FAIL | 0.1065 | 0.015 | 4 |
| ceiling_height_diagnosis | FAIL | 0.1065 | 0.015 | 4 |
| repeatability | NOT EVALUATED | 0 | 1 | 0 |
| wall_length_tier | FAIL | 3.991 | 1 | 12 |
| footprint | NOT EVALUATED | 0 | 0.08 | 0 |
| stitch_adjacency | PASS | 0 | 0 | 1 |
| stitch_overlap | PASS | 0 | 0.05 | 1 |

2 of 6 evaluated gates pass, 2 not evaluated.

**video**

| gate | result | value | threshold | n |
|---|---|---|---|---|
| opening_width | FAIL | 0 | 0.85 | 7 |
| ceiling_height | FAIL | 0.6329 | 0.015 | 5 |
| ceiling_height_diagnosis | FAIL | 0.6329 | 0.015 | 5 |
| repeatability | FAIL | 250.4 | 1 | 4 |
| wall_length_tier | FAIL | 45.82 | 1 | 16 |
| footprint | NOT EVALUATED | 0 | 0.08 | 0 |
| stitch_adjacency | PASS | 0 | 0 | 5 |
| stitch_overlap | PASS | 0 | 0.05 | 5 |

2 of 7 evaluated gates pass, 1 not evaluated.

### Head to head against AR Plan 3D, 1.5 cm tie threshold

| tier | room | dimension | tape m | theirs m | their error cm | ours m | our error cm | closer |
|---|---|---|---|---|---|---|---|---|
| photo | bedroom_1 | short_pair | 3.658 | 3.410 | 24.8 | 3.637 | 2.1 | ours |
| photo | bedroom_1 | long_pair | 3.912 | 3.730 | 18.2 | 4.729 | 81.8 | theirs |
| photo | kitchen | short_wall_1 | 2.692 | 2.750 | 5.8 | 2.658 | 3.5 | ours |
| photo | kitchen | short_wall_2 | 2.692 | 2.700 | 0.8 | 2.658 | 3.5 | theirs |
| photo | kitchen | long_wall_1 | 3.603 | 3.510 | 9.3 | 4.753 | 115.0 | theirs |
| photo | kitchen | long_wall_2 | 3.603 | 3.790 | 18.7 | 4.753 | 115.0 | theirs |
| video | bedroom_1 | short_pair | 3.658 | 3.410 | 24.8 | 5.935 | 227.8 | theirs |
| video | bedroom_1 | long_pair | 3.912 | 3.730 | 18.2 | 4.578 | 66.6 | theirs |
| video | kitchen | short_wall_1 | 2.692 | 2.750 | 5.8 | 1.806 | 88.7 | theirs |
| video | kitchen | short_wall_2 | 2.692 | 2.700 | 0.8 | 1.806 | 88.7 | theirs |
| video | kitchen | long_wall_1 | 3.603 | 3.510 | 9.3 | 3.162 | 44.1 | theirs |
| video | kitchen | long_wall_2 | 3.603 | 3.790 | 18.7 | 3.162 | 44.1 | theirs |

**Photo beats or ties on 33% of dimensions, video on 0%.** The photo tier now
wins two dimensions outright, both short walls, and loses the long walls.

### The stitch_overlap finding

28.01 m2 was real and came from the photo tier, not a stale plan. The stitcher
applied its rotation and translation to every polygon and wall, then recorded
the same transform as the placement, so a consumer following the contract
applied it twice and put all four rooms on top of each other. The tier's own
report said 0.0000 because it never re-applied the placement. Fixed by
recording the identity, keeping the transform in the method string and the
15 degree interval on theta. Overlap is now 0.0000 and the gate passes at both
tiers.

### The photo regression, found and fixed

The branch found the cause: MapAnything estimates a focal length when it is
not given one, and on the camera originals it guessed 464 px against a true
332 px, implying a 46 degree field of view where the camera has 76. Too long a
focal pushes the scene apart sideways while the camera-height prior pins the
heights, which is exactly what was seen. Giving it the EXIF focal:

| quantity | before | after |
|---|---|---|
| median wall error | 22.4% | **13.0%** |
| walls inside the 8% budget | 2 of 12 | **6 of 12** |
| interval coverage | 0.69 | **0.88** |
| confident-garbage cases | 5 | **2** |

The capture protocol gains the instruction that follows: send the camera
originals, because a messaging app strips the lens details the pipeline reads.

### Full-profile rehearsal

| step | time | size |
|---|---|---|
| clone | 1.1 s | |
| `uv sync --extra all`, cold cache | 44.0 s | 1.6 GB venv |
| `scripts/fetch_weights.sh`, cold cache | 929 s | 9.60 GB |
| photo tier, one room | 78 s | |
| video tier, one clip | 1017 s | |

**Two defects found by installing what the README tells a stranger to
install.** The `all` extra was unsatisfiable: depth-pro pins numpy<2 while
mapanything needs numpy>=2. depth-pro runs correctly on numpy 2 and the whole
image path was measured on 2.4.6, so the pin is overridden with the reason
written beside it. The git-sourced packages also needed
`allow-direct-references`. Neither is visible from a venv built up by hand.

The weights are **9.60 GB, not the 7.3 GB estimated**, and MapAnything is half
of that alone. Corrected in the README, the fetch script and the rehearsal.

### Failures and open items

* Neither image tier is accurate enough to ship. Photo is within reach at
  13.0% median error against an 8% budget; video is not, at 32.9% against 3%.
* Repeatability still fails: 0 of 4 rows on the same-device video pair, and
  the photo repeat pair has no plan of its own to compare.
* Ceiling height fails at both image tiers.
* Every lidar gate is NOT EVALUATED, and will stay that way until someone
  measures a property that was scanned with a LiDAR phone.

Tests: 266 passing.

## Stage: rendered plans, evidence hygiene and a stale-claims sweep

Done.

**The photo stitcher put walls and polygons in different frames.** It rotated
a room's polygon about that room's own anchor and its walls about the origin,
so a placed room drew its outline in one place and its walls in another. Three
rooms stacked, fills sat off their outlines, and every room was labelled
"room". Placements are now fitted from the polygon correspondence and applied
once to everything; labels fall back to the room id. `tests/test_plan_geometry.py`
fails if any wall endpoint lies off its room polygon after placement, or if
two rooms overlap.

**The renderer was rewritten for legibility.** Drawings rotate into the plan's
Manhattan frame, walls under 0.6 m get no label, labels sit outside their wall,
the font scales with room size, doors and pass-throughs are drawn distinctly,
partially observed sides are dashed, and the title carries capture, tier,
pipeline version and an UNRELIABLE marker. `plan.json` is untouched by any of
it.

**Fix loop 1's snapshots had been swept.** `fix_loop/regenerate.sh` read the
live `benchmarks/captures.yaml`, so every capture added after the loop landed
in its after snapshot: twelve stub-pipeline `own_*` runs the loop never
measured. It now reads `fix_loop/captures_loop1.yaml`, frozen at the five
captures that existed then, and `tests/test_evidence_hygiene.py` fails if
either snapshot grows, if the script reaches for the live registry again, or
if a stub plan appears under `docs/benchmark`.

**The head-to-head column never could have filled.** `--plans` built a map of
room id to plan and handed it to a function expecting (room id, truth wall) to
length, so every lookup missed whatever was passed. The flag is now `--eval`,
and `docs/head_to_head.md` carries real numbers: the rival is closer on 4 of 6
shared dimensions, our photo tier on 2.

**The image tiers never marked a guessed side.** The single-room fit closes an
unsupported side at the camera path plus a margin and recorded that only in a
warning string, so the guessed side got the same narrow interval as a measured
one. The fit now sets `partially_observed` and `perimeter_support`, as the
lidar tier already did.

**Stale documentation.** The README said both image tiers run the stub, that
no tier produced plans for the measured rooms, and that the head-to-head
column was pending. The third-party section claimed no trained model sits in
the measurement path, which is true of the lidar tier alone. The compliance
matrix scored accuracy rows "on the stub only". All corrected against
`docs/benchmark`.

**A gap found while correcting them:** damage detection is fully built and
measured but is **not wired into `cozmo run`**. It is reached through
`scripts/run_damage_eval.py`, and a plan from the command line carries an
empty damage list and a warning saying so. Now stated in the README and the
compliance matrix rather than implied away.

Tests: 280 passing.
