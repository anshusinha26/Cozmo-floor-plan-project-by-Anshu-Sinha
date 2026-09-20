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
