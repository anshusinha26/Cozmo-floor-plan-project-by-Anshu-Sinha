# Fix loop 2: video-tier metric scale

Declared before any fix code. The BEFORE run in `before/` was produced by the
commit named in `before/provenance.json` and can be regenerated with
`before/regenerate.sh`.

## Worst gate

**Video-tier wall length against tape.** Zero of six scored quantities fall
within the 3% gate. Wall errors run from 36% to 76%, and **three of six clips
produce no plan at all** (`bedroom_1`, `kitchen`, `hall`).

Measured on the BEFORE run in `before/`, not on an earlier one:

| room | quantity | tape cm | predicted cm | error % | inside its own interval |
|---|---|---|---|---|---|
| bedroom_2 | wall (door) | 388.6 | 120.0 | -69.1% | no |
| bedroom_2 | wall | 363.2 | 88.7 | -75.6% | no |
| bedroom_2 | ceiling | 297.2 | 270.0 | -9.1% | yes |
| bedroom_2_repeat | wall (door) | 388.6 | 249.0 | -35.9% | no |
| bedroom_2_repeat | wall | 363.2 | 216.0 | -40.5% | no |
| bedroom_2_repeat | ceiling | 297.2 | 270.0 | -9.1% | yes |
| bedroom_1, kitchen, hall | all | - | no plan | - | - |

Two of six land inside their stated interval, and both are ceilings, which come
from a prior rather than from the reconstruction. Every wall misses, and some
miss with intervals that reach below zero.

The same two captures of one room, `bedroom_2` and `bedroom_2_repeat`, disagree
with **each other** by 107% and 143% per wall. Nothing about the room changed
between them.

## Root cause: the monocular metric scale is wrong, by a different factor per chunk

The tier's only source of absolute scale is Depth Pro's depth at the SfM sparse
points. Four independent lines of evidence say that source is unreliable on
these captures, and that its error is a per-chunk bias rather than noise.

1. **Camera height above the reconstructed floor.** A walking person holds a
   phone between about 1.1 and 1.8 m up. Where the BEFORE run got far enough to
   measure it, the reconstructions put the camera at 0.46 m, 0.92 m and 1.47 m
   above their own floors; loop 1's draw of the same clips gave 0.43, 1.00,
   1.15, 1.60 and 2.61 m. That is a 0.3x to 1.8x spread on a quantity whose
   answer is known, and it is the most direct measurement of the scale error
   available without tape.
2. **The error is one-directional inside a sweep.** A chunk covers a few seconds
   of one sweep across one part of one room, so every frame sees similar
   surfaces at similar distances and the model is wrong the same way on all of
   them. Averaging twelve frames tightens the spread without touching the bias.
3. **The per-frame spread understates the error tenfold.** Within a chunk the
   per-frame scale ratios disagree by 2.7% to 11%. Between neighbouring chunks,
   measured through the bridge, the same quantity disagrees by 18% to 142%. The
   interval budget currently uses the first number.
4. **Two independent depth models disagree with each other.** Depth Pro and
   Depth Anything V2 on the same frames gave a correlation of 0.18 between their
   log scale ratios, which means the SfM chunk is self-consistent and each model
   is independently wrong.

Spike 2 measured 1.1% and 1.3% scale error on the LiDAR sample scans and that
result did not generalise. Those scans had ordinary room content; these loops
are shot close to glossy, textureless walls, where a monocular model has almost
nothing to work from.

## Secondary cause: only 11% to 40% of frames reach the plan

Chunk bridging depends on the two chunks' metric scales agreeing, so a scale
error of 18% to 142% rejects most bridges, which leaves the plan built from one
or two chunks. The resulting fragment is then fitted as if it were a room: a
1.19 m strip stands in for a 3.91 m wall, which is where the largest errors come
from. This is a consequence of the root cause, not a separate defect, but it has
to be fixed separately because rescaling alone does not lengthen a wall the
reconstruction never saw.

## The fix

1. **Camera-height prior.** Solve one scale per chunk so the median camera
   height above that chunk's own floor plane equals H, default 1.40 m, plus or
   minus 0.12 m. This replaces a monocular guess with a measurement whose answer
   is known from the capture protocol. It is an assumption and it is declared in
   `plan.assumptions`.
2. **Bridging on yaw and translation only.** Every chunk becomes a metric,
   gravity-aligned fragment on a common floor, so a bridge needs a quarter-turn
   choice and a 2D translation, not a scale. Acceptance relaxes accordingly.
3. **Global least squares over chunk scales.** Height prior weighted strong,
   Depth Pro weak, accepted bridge ratios as constraints. Residuals reported.
4. **Intervals.** The per-frame standard error is replaced by the larger of the
   height-prior uncertainty and the disagreement between the height-prior and
   Depth Pro scales, so an interval can never be tighter than the evidence that
   the two methods disagree.
5. **Single-room mode.** For per-room clips, fit one rectilinear room from the
   outermost supported wall faces around the camera path instead of segmenting.
   Unsupported sides are closed by the rectangle assumption and flagged. It never
   returns "no room".
6. **Ceiling measured** where ceiling points survive rescaling, prior otherwise.

## Predicted after-numbers

| quantity | before | predicted after |
|---|---|---|
| clips producing a plan | 3 of 6 | 6 of 6 |
| camera height above own floor | 0.46 to 1.47 m | 1.40 m by construction, so not evidence |
| **measured ceiling height** (independent of the prior's direction) | 2.70 m, from a prior, on both | 2.6 to 3.3 m measured, against 2.97 tape |
| median absolute wall error | 54.8% | 8% to 20% |
| worst absolute wall error | 75.6% | under 35% |
| walls within the 3% gate | 0 of 6 | 1 to 3 of 6 |
| tape inside the stated interval | 2 of 6, both ceilings | 4 to 6 of 6 |
| bedroom_2 against bedroom_2_repeat, per wall | 107% and 143% | under 20% |
| share of frames reaching the plan | 11% to 40% | 40% to 80% |

The gate is not predicted to pass. A 0.12 m uncertainty on a 1.40 m prior is
plus or minus 8.6% before anything else, so 3% is out of reach at this tier
until the prior is replaced by a measurement. What is predicted is that the
errors stop being dominated by scale and the intervals start covering the truth.

## What would falsify this

* **Measured ceiling heights do not converge near 2.97 m** after rescaling. The
  prior fixes camera height by construction, so it cannot be its own evidence;
  the ceiling is the independent vertical check. If ceilings stay spread from
  2.7 to 3.9 m, the vertical scale was not the problem.
* **Median wall error stays above 25%.** Then the dominant error is not scale
  and the diagnosis is wrong.
* **Height-prior scale and Depth Pro scale agree within 20%** on most chunks.
  That would mean Depth Pro was not the culprit and something else moved the
  camera height, most likely the floor plane fit.
* **bedroom_2 and bedroom_2_repeat still disagree by more than 25%** per wall.
  A systematic per-capture scale bias should largely cancel between two captures
  of one room once both are pinned to the same prior; if it does not, the error
  is random rather than systematic and a prior cannot fix it.
* **Coverage does not improve** once bridging stops depending on scale. That
  would mean bridges were failing for a reason other than scale disagreement.
