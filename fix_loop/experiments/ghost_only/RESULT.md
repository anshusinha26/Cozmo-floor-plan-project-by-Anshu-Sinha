# Falsifier: ghost-face rejection only

Question from the declaration: "Ghosts are the real cause if dropping ghost
faces alone, with the erosion segmentation left in place, brings room counts
to within one of each other."

**Answer: no. The falsifier is negative, so the cell complex is needed.**

| quantity | before | ghost rejection only |
|---|---|---|
| rooms, 1a8384c3f6 | 8 | 8 |
| rooms, c7d28f72c6 | 10 | 11 |
| repeatability rows within tolerance | 0 of 112 | 0 of 117 |
| median length difference, matched pairs | 0.975 m | 0.976 m |
| rooms paired at IoU 0.3 | 6 | 6 |
| registered footprint IoU | 0.68 | 0.68 |

Room counts did not converge; they moved apart by one. The gate did not move
at all.

## Why the effect was so small

The visibility test drops only 3 faces (2.0 m) in `1a8384c3f6` and 2 faces
(1.0 m) in `c7d28f72c6`, about 1% of face length, not the 16% that evidence d
reported. Those two numbers measure different things and the earlier one was
the weaker measure:

* evidence d asked whether a face lies outside the envelope of the room
  polygons. Those polygons are themselves inflated by the segmentation being
  tested, so a face can fall outside the envelope while sitting against a
  genuinely observed wall.
* the visibility test asks whether anyone stood next to the face. That is a
  property of the capture, independent of segmentation, and it says almost all
  faces are real.

So ghosts were over-counted in the declaration's evidence d. They are a real
but minor effect, and hypothesis H3 is not the cause of the repeatability
failure.

Ghost rejection is kept anyway: it is cheap, it removes returns that are
genuinely outside the property, and it costs nothing in room count.

Reproduce: `.venv/bin/python fix_loop/experiments/ghost_only/run.py`
