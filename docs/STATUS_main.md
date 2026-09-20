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
