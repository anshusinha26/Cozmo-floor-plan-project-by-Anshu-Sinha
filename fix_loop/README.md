# Fix loops

Each loop was declared before the fix was written, then measured after. Two of
the three are negative results, reported as they came out.

| loop | subject | outcome |
|---|---|---|
| [1](#loop-1-cross-capture-repeatability) | lidar room segmentation, cross-capture repeatability | **negative**: declared cause falsified, gate unmoved |
| [2](loop2_video_scale/) | video tier metric scale | **partial**: every clip now produces a plan, accuracy still far off |
| [photo focal](loop2_video_scale/photo_ablation.md) | photo tier scored worse on camera originals | **fixed**: cause found, 22.4% to 13.0% median wall error |
| [3](#loop-3-photo-unanchored-wall) | photo tier unanchored wall | running on the tier branch |

---

## Loop 1: cross-capture repeatability

**An honest negative result.** The gate failed at 0 rows within tolerance
before the fix and still fails after it. The declaration predicted 40%.

What the loop established:

* The eval itself was broken first. Plans are emitted in the ARKit world
  frame, so two captures sat 58 degrees apart and no quarter turn aligned
  them. Fixed before the BEFORE run was taken.
* Wall geometry is sound: matched faces from the two captures agree to
  **1.9 cm**.
* Ghost faces were over-counted in the declaration's own evidence, 16% against
  a real 1%, and the ghost-only falsifier moved nothing.
* **Coverage dominates.** Only 56% and 37% of each capture's wall-face length
  has any counterpart in the other. No segmentation rule can invent a wall one
  capture never saw. This was the third falsifier listed and it is the one
  that fired.

Decision at the end: erosion is the default segmentation again, because the
wall-driven cell complex scored no better and inflated footprints. Two of its
improvements were kept: collinear edges collapse, and rooms whose outline is
mostly unsupported are flagged partially observed with widened intervals.

| path | what |
|---|---|
| `DECLARATION.md` | the declaration, with an addendum recording what happened |
| `POSTMORTEM.md` | predicted against actual, and what remains |
| `DIFF.md` | code changes, commit range, before and after tables |
| `before/`, `after/` | full runs with `PROVENANCE.txt` naming the commit |
| `evidence/` | the five analyses behind the declaration |
| `experiments/ghost_only/` | the falsifier |
| `regenerate.sh` | `fix_loop/regenerate.sh before` or `after` |

## Loop 2: video tier metric scale

In [`loop2_video_scale/`](loop2_video_scale/). **Partial.** Eight predictions
were written before any fix code; two came true and six did not.

* **Right:** every clip now produces a plan, where three of six produced
  nothing, and the share of the sample scan reaching the output went from 30%
  to 70%.
* **Wrong:** median wall error went 54.8% to 35.3% against a predicted 8 to
  20%, nothing reached the 3% gate, and the two captures of one bedroom
  disagreed more than before. **Three of five falsifiers fired.**
* Two causes the diagnosis missed: a camera-height prior that scales
  confidently to a floor plane that is not the floor, and a 1.5 m wall-height
  threshold inherited from the lidar tier that no clip at this tier could ever
  meet.
* Iteration 2, running the clip's frames through the photo reconstruction, was
  declared, tried and rejected.

The finding that outlived the loop: nine composed stills of one room gave
walls within about 1% where fifty seconds of video of the same room gave 53%
and 66%, on the same scale cue and the same room fitter. That is a capture
difference, and the capture protocol now reflects it.

## The photo focal regression

In [`loop2_video_scale/photo_ablation.md`](loop2_video_scale/photo_ablation.md).
**Found and fixed**, and the only one of the four that ends with a number
moving the right way.

The photo tier scored better on compressed copies of the photographs than on
the camera originals, which is the wrong way round. The photographs are the
same pictures, matched at correlation 1.000. The cause was the focal length:
MapAnything estimates one when it is not given one, and on the originals it
guessed **464 px against a true 332 px**, implying a 46 degree field of view
where the camera has 76. Too long a focal pushes the scene apart sideways
while the camera-height prior pins the heights, which is the signature that
was seen: ceilings right, walls 33 to 47% long.

| quantity | before | after |
|---|---|---|
| median wall error | 22.4% | **13.0%** |
| walls inside the 8% budget | 2 of 12 | **6 of 12** |
| interval coverage | 0.69 | **0.88** |
| confident-garbage cases | 5 | **2** |

The control is the Nokia 8.1, which writes a focal in millimetres but no 35 mm
equivalent, gets no intrinsics, and is the one camera whose rooms did not
improve.

## Loop 3: photo unanchored wall

Running on the tier branch. This section is filled in after that work merges,
with the same structure as the others: what was declared, what was measured,
which falsifiers fired.
