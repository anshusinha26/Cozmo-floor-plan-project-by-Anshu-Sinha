# Iteration 2: frames engine, rejected

Declared in `../DECLARATION.md`'s addendum before it was built. Predicted 3 to
12% median wall error and under 10% repeat disagreement. Measured on the room
the addendum named, `bedroom_2`, plus its repeat.

| run | walls cm | error against tape |
|---|---|---|
| tape | 388.6, 363.2 | - |
| photo tier, 9 stills | 393.0, 366.8 | +1.1%, +1.0% |
| frames engine, 16 frames | 658.0, 590.9 | +69.3%, +62.7% |
| frames engine, 24 frames | 248.0, 240.4 | -36.2%, -33.8% |
| sfm engine (iteration 1) | 181.7, 124.3 | -53.2%, -65.8% |
| frames engine on the repeat, 16 frames | 498.2, 279.5 | +28.2%, -23.0% |

## Verdict: rejected, sfm stays the default

The prediction was wrong and a falsifier fired: the frames engine is not better
than SfM on a per-room clip. Worse, changing only the frame count from 16 to 24
swings the same room from 69% long to 36% short. An engine whose answer depends
that strongly on how many frames it is given is not measuring the room.

## Why the reasoning was wrong

The addendum inferred that the geometry engine was the limit because the photo
tier reached 1% on the same room where SfM reached 53%. Both tiers used the same
scale cue and the same room fitter, so the engine looked like the only
difference. It was not the only difference: **the photographs are not the same
views as the frames.**

Nine stills of a room are deliberately composed. Someone stood back, framed the
whole space, and moved to a genuinely different position for each shot. Sixteen
frames pulled from a walk are close-ups taken a step apart, with narrow
baselines and motion blur, and no guarantee any of them sees a whole wall.
MapAnything is given far less to work with, and it shows.

So the correct reading of the photo tier's 1% is not "MapAnything beats COLMAP".
It is "wide, well separated views of a room beat a walk past its walls,
whichever engine you use". That is a statement about capture, not about
software, and it points at the capture protocol rather than at the pipeline.

## What was kept

`--video-engine frames|sfm` stays, defaulting to `sfm`. The frames path is a
forty second reconstruction against five minutes for SfM, so it remains useful
as a fast preview and as the thing to retry if the capture protocol changes to
ask for slow, wide sweeps with pauses. It is not the accurate path today.
