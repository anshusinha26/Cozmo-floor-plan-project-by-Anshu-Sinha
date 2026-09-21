# Fix loops

Each loop was declared before the fix was written, then measured after. Two of
the four are negative results, reported as they came out.

| loop | subject | outcome |
|---|---|---|
| [1](#loop-1-cross-capture-repeatability) | lidar room segmentation, cross-capture repeatability | **negative**: declared cause falsified, gate unmoved |
| [2](loop2_video_scale/) | video tier metric scale | **partial**: every clip now produces a plan, accuracy still far off |
| [photo focal](loop2_video_scale/photo_ablation.md) | photo tier scored worse on camera originals | **fixed**: cause found, 22.4% to 13.0% median wall error |
| [3](loop3_photo_unanchored_wall/) | photo tier unanchored wall | **partial**: 4 of 5 predictions met, 6 of 12 walls within gate became 8 of 12, one room flipped sign |

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

## Loop 3: the photo tier's unanchored wall

In [`loop3_photo_unanchored_wall/`](loop3_photo_unanchored_wall/). **Partial.**
Five predictions were written before any fix code; four came true.

Three of four room sides found a supported wall face. The fourth was closed at
the camera path plus a margin, which overshoots whenever the photographer did
not stand against that wall. Every room had exactly one such side, and every
one of them was long.

| prediction | actual | met |
|---|---|---|
| walls within the 8% gate: 7 to 9 of 12 | **8 of 12** | yes |
| room sides anchored to evidence: 19 or 20 of 20 | **20 of 20** | yes |
| bedroom_2 long axis inside the predicted band | **+3.1%** | yes |
| kitchen unchanged | **unchanged** | yes |
| bedroom_1 long axis between 380 and 430 cm | **334.8 cm, -14.4%** | no |

**bedroom_1 flipped sign.** It had been 20.9% long and came back 14.4% short.
The outermost significant density peak on that side sits inside the true wall,
most likely a wardrobe front or a curtain hanging proud of it, and the fitter
cannot tell that from the wall itself. The magnitude improved and the error
became two-sided. That is an improvement and it is not the same as being right.

**Kitchen was the control, and it held.** It was predicted not to move, because
all four of its sides were already anchored and this loop deliberately did not
touch anchored sides. It did not move. That is what says the edit reached no
further than intended. It is still 31.9% long for a different reason: the rule
takes the **outermost** qualifying face, and the face it takes there has 1584
points, the fewest of any it found. That is the next loop's subject.

**The first attempt found nothing at all.** It searched only beyond the camera
path, on the reasoning that a wall must be outside where the photographer
stood, and anchored 0 sides. On bedroom_2 the path runs 0.61 m **past** the
room's own wall: a reconstruction stretched along one axis carries the cameras
out with it, so the path is not an inner bound. That also explains the old
fallback, which was adding a margin to an overshoot rather than covering an
undershoot, and is why every error had the same sign.
