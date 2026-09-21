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

---

# Addendum: iteration 2, the geometry engine rather than the scale cue

Appended after the first iteration was measured. Everything above is the
original text, unchanged.

## What the first iteration showed

The fix was right in direction and far too small. Median wall error went from
54.8% to 35.3% against a prediction of 8 to 20%, nothing reached the 3% gate,
and the two captures of one bedroom ended up disagreeing more than before, which
fired a falsifier declared in advance.

The reason is in `POSTMORTEM.md`: a height prior only fixes scale when the
fragment's floor plane is right, and a chunk covering a few seconds of a sweep
often gets it wrong. Two bridged chunks of one room ended at 0.148 and 0.247 m
per SfM unit with **both** set by the prior.

## The evidence that redirects this

The photo tier reconstructs the same rooms from nine stills using the same
camera-height prior and the same single-room fitter, and differs only in what
builds the geometry: MapAnything instead of COLMAP SfM.

| room | photo tier, 9 stills | video tier, 50 s of clip | tape |
|---|---|---|---|
| bedroom_2 walls | 393.0, 366.8 cm (+1.1%, +1.0%) | 181.7, 124.3 cm (-53%, -66%) | 388.6, 363.2 |
| bedroom_2_repeat walls | 400.4, 373.4 cm (+3.0%, +2.8%) | 303.9, 540.6 cm (-22%, +49%) | 388.6, 363.2 |
| cross-capture agreement | 1.9%, 1.8% | 198%, 145% | - |

Same scale cue, same room fitter, same tape, two orders of magnitude apart. The
scale cue is no longer what limits the video tier. The geometry engine is.

## The change

A `--video-engine frames|sfm` switch, defaulting to `frames`. The frames engine
decodes the clip, picks a spread of sharp frames across it, and runs the photo
tier's room reconstruction on them. Only the video file is read, so tier
isolation is unchanged. The SfM path stays selectable and is what a
whole-property walk still needs.

## Prediction

| quantity | iteration 1 | predicted for iteration 2 |
|---|---|---|
| median absolute wall error | 35.3% | 3% to 12% |
| worst absolute wall error | 65.8% | under 25% |
| walls within the 3% gate | 0 of 8 | 1 to 4 of 8 |
| bedroom_2 against its repeat | 198%, 145% | under 10% |
| clips producing a plan | 6 of 6 | 6 of 6 |

The per-room clips should land near the photo tier's numbers, because they
become the photo tier with frames pulled from video instead of stills. The
sample scan should not: it is a walk through several spaces, and a single
reconstruction of it is one space by definition.

## What would falsify it

* **Per-room clips do not approach the photo tier's error.** Then the difference
  is not the engine, and something about frames from video, motion blur, rolling
  shutter, narrower baselines, is the real limit.
* **The repeat pair still disagrees by more than 15%.** Then the instability is
  in the capture rather than in the reconstruction, and no engine fixes it.
* **The frames engine is worse than SfM on any per-room clip.** Then `sfm` stays
  the default and this addendum records a rejected idea.
