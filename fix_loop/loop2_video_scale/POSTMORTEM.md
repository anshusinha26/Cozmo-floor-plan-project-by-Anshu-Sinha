# Fix loop 2: postmortem

Predicted against actual, in plain terms.

## What I said would happen, and what did

The declaration was committed before any fix code. It made eight predictions.
Two came true, six did not.

**Right.** Every clip now produces a plan, where three of six produced nothing
before. On the sample scan the share of the video reaching the output went from
30% to 70%, and accepted bridges from 2 of 6 to 4 of 6.

**Wrong.** The median wall error went from 54.8% to 35.3%, where I predicted 8
to 20%. The worst went from 75.6% to 65.8%, where I predicted under 35%. Nothing
reached the 3% gate, where I predicted one to three of six would. And the two
captures of one bedroom, which should have agreed once both were pinned to the
same prior, disagree **more** than before: 198% and 145% per wall, against 107%
and 143%.

Three of the five falsifiers I wrote down fired. By the standard I set myself
beforehand, the root cause was not the whole story.

## Why the prediction was wrong

The diagnosis said the metric scale was wrong because it came from a monocular
depth model. That was true, and fixing it was worth doing, but it was not the
binding constraint. Two things were missed.

**The prior only works when the floor plane is right.** The height prior scales
a chunk so its own camera sits 1.40 m above its own floor. When the floor is
found correctly, that is a good measurement. When a chunk covers a few seconds
of a sweep and sees almost no floor, the plane it fits is not the floor, and the
prior then scales confidently to the wrong thing. On `bedroom_2_repeat` two
bridged chunks ended up at 0.148 and 0.247 m per SfM unit, a 67% disagreement,
**with both set by the prior**. Replacing one unreliable scale cue with another
unreliable scale cue does not give a reliable scale.

That is also why repeatability got worse rather than better. Before the fix both
captures were wrong in the same direction, because Depth Pro's bias is a
property of the content and the two captures show the same room. After the fix
each capture is wrong in whatever direction its own worst chunk's floor plane
points, which is not shared between captures. The error became less biased and
more random, and random errors do not cancel between two captures.

**The rooms were never measured in the first place.** Underneath the scale
problem sat something simpler: a face counted as a wall only if it reached 1.5 m
above the floor, inherited from the LiDAR tier. A phone carried at 1.4 m and
pointed level or down never reconstructs that high. On `bedroom_2_repeat` all
eight faces topped out between 0.72 and 1.46 m, none qualified, and the room
came back as the camera path in a box. No amount of scale work is visible while
that is true, and it was true for every clip in loop 1. Fixing it took two of
four room sides from assumed to measured on that clip. It should have been found
before the fix was designed, by looking at what the room fitter was actually
using, and it was not.

## What the loop did produce

* A fix that is right in direction and insufficient in size, with the size measured.
* Four defects found only by running on real data: a free rotational degree of
  freedom that made bridges disagree about gravity by 164 degrees, a `KeyError(0)`
  that surfaced as `error: 0`, a wall-height threshold no capture at this tier
  could ever meet, and length intervals with negative lower bounds.
* Evidence that the geometry engine, not the scale cue, is now the limit. Nine
  stills of `bedroom_2` through MapAnything plus the same height prior plus the
  same room fitter give walls within about 1%. Fifty seconds of video of the same
  room through SfM gives 53% and 66%. Same scale cue, same room fitter, same
  tape. The difference is what reconstructs the geometry.

## What I would do next, and why

Not another scale fix. The photo path is better on the same rooms with the same
prior, so the next thing to try is running the video tier's frames through the
photo tier's reconstruction instead of through COLMAP. That is iteration 2, and
it is declared in `DECLARATION.md`'s addendum before it is attempted, for the
same reason the first declaration came first.

---

## Iteration 2: tried, measured, rejected

The addendum predicted that running a clip's frames through the photo tier's
reconstruction would give 3 to 12% median wall error. Measured on the room it
named:

| run | walls cm | error |
|---|---|---|
| tape | 388.6, 363.2 | - |
| frames engine, 16 frames | 658.0, 590.9 | +69.3%, +62.7% |
| frames engine, 24 frames | 248.0, 240.4 | -36.2%, -33.8% |
| sfm (iteration 1) | 181.7, 124.3 | -53.2%, -65.8% |

The falsifier fired. `sfm` stays the default, and the addendum records a
rejected idea, which is what it said it would do.

The interesting part is why the reasoning was wrong, because it was a reasonable
inference from real evidence. The photo tier reached 1% on this room with the
same scale cue and the same room fitter, so the geometry engine looked like the
only remaining difference. It was not: nine composed photographs of a room are
not the same views as sixteen frames of someone walking past its walls. The
photographs are taken from genuinely separate positions and frame whole walls;
the frames are close-ups a step apart, with narrow baselines and motion blur.

So the honest reading of the photo tier's 1% is not that MapAnything beats
COLMAP. It is that **wide, well separated views beat a walk along the walls**,
whichever engine reconstructs them. That is a finding about how these clips are
captured, not about which library to use, and the next thing worth trying is the
capture protocol: slow sweeps with pauses from the corners of a room, rather
than a walk around its perimeter.

Full detail in `after_iter2/RESULT.md`.
