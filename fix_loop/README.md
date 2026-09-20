# Fix loop 1: cross-capture repeatability of LiDAR room segmentation

**Outcome: an honest negative result. The declared root cause was falsified and
the fix did not work.**

The repeatability gate on the two LiDAR captures of one apartment failed at 0
rows within tolerance before the fix, and still fails at 0 after it. The
declaration predicted 40%.

What the loop established:

* The eval itself was broken first. Plans are emitted in the ARKit world
  frame, so the two captures sat 58 degrees apart and no quarter turn aligned
  them. Fixed before the BEFORE run was taken, so the numbers compared here
  are real failures rather than comparison artefacts.
* Wall geometry is sound. Matched wall faces from the two captures agree to
  1.9 cm.
* Ghost faces were over-counted in the declaration's evidence. The real figure
  is about 1% of face length, not 16%, and the ghost-only falsifier moved
  nothing.
* **Coverage dominates.** Only 56% and 37% of each capture's wall-face length
  has any counterpart in the other. No segmentation rule can invent a wall one
  capture never saw, so room-level repeatability is not achievable until the
  two captures cover the same rooms. This was the third falsifier listed in
  the declaration and it is the one that fired.

Decision taken at the end of the loop: the erosion segmentation is the
default again, because the wall-driven cell complex scored no better on the
gate and inflated footprint areas. The cell complex stays selectable with
`--segmentation cells`. Two improvements from the loop were carried back into
the erosion path: collinear polygon edges are collapsed, and rooms whose
outline is mostly unsupported are flagged partially observed with widened
intervals.

## Contents

| path | what |
|---|---|
| `DECLARATION.md` | the declaration, with an addendum recording what happened |
| `POSTMORTEM.md` | predicted against actual, and what remains |
| `DIFF.md` | code changes, commit range, before and after tables |
| `before/`, `after/` | full runs with `PROVENANCE.txt` naming the commit |
| `evidence/` | the five analyses behind the declaration |
| `experiments/ghost_only/` | the falsifier |
| `regenerate.sh` | `fix_loop/regenerate.sh before` or `after` |

## Loop 2

A second fix loop, on video-tier scale rather than segmentation, is being run
on the video-tier branch under `fix_loop/loop2_video_scale/`. It is not part
of this branch and nothing here depends on it.
