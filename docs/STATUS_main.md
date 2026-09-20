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
