# Postmortem: predicted against actual

## The short version

**The fix did not work. The repeatability gate still fails, and on the
measured numbers the new segmentation is worse than the one it replaced.**

| quantity | before | predicted after | actual after |
|---|---|---|---|
| repeatability rows within tolerance | 0 of 112 (0%) | 40%, range 30% to 55% | **0 of 153 (0%)** |
| median length difference, matched pairs | 0.975 m | under 0.15 m | **0.761 m** |
| rooms, the two apartment captures | 8 and 10 | 6 to 7 each, differing by at most 1 | **6 and 9, differing by 3** |
| structural face length outside the envelope | 16.1% and 16.4% | under 8% | **about 1%, but the 16% was a bad measure** |
| rooms paired across the captures | 6 | not predicted | **3** |
| registered footprint IoU | 0.68 | not predicted | **0.61** |

Three of four predictions were wrong, and two of them were wrong in the
direction that matters.

## What the falsifier said

The declaration named a cheap falsifier: if dropping ghost faces alone fixed
the room counts, the cell complex was unnecessary. It did not. Ghost
rejection removes 3 faces (2.0 m) and 2 faces (1.0 m), about 1% of face
length, and the gate did not move. Full result in
`experiments/ghost_only/RESULT.md`.

That also showed evidence d in the declaration was a bad measure. It counted
faces lying outside the envelope of the room polygons, and those polygons
were inflated by the very segmentation under test, so a face could sit
against a real wall and still be counted a ghost. The visibility test, which
asks whether anyone stood beside the face, says almost every face is real.
The 16% figure should not have been trusted.

## Why the main prediction was wrong

The declaration's reasoning was: matched wall faces agree to 1.9 cm, so if
rooms were partitioned by wall support instead of by walked floor, the wall
lengths would agree too. The first half is true. The second half does not
follow, and here is why.

**Wall support is sparse in the band the captures share.** Only 48 of 84
structural faces in `c7d28f72c6` carry support over at least 55% of their own
extent in the 1.0 to 1.6 m band. Furniture blocks the lower part of many
walls and the captures rarely look above 1.6 m. So a large share of cell
edges have no support and merge, which is why the method produces a few very
large rooms (37 m2 and 39 m2) rather than the six or seven spaces expected.

**The two captures do not see the same walls.** Only 56% and 37% of each
capture's wall-face length has any counterpart in the other. Where a wall is
missing from one capture, the cell complex merges across it in that capture
and cuts in the other. The partition therefore still depends on coverage,
just through a different route than before. Changing the segmentation rule
did not remove the dependence on what the operator happened to scan.

**Fewer rooms did not mean better-matched rooms.** Room count moved from 8
and 10 towards 6 and 9, which is closer to the expected six or seven, but
rooms paired across the captures fell from 6 to 3 and the registered
footprint IoU fell from 0.68 to 0.61. Larger rooms are individually less
likely to line up: one merge that happens in one capture and not the other
now moves tens of square metres instead of a few.

## What got better

* Room polygons are wall-driven and collinear edges are collapsed, so a room
  reports walls that correspond to walls. `c7d28f72c6` went from a room with
  89 edges to polygons that follow the grid lines.
* Room overlap is zero by construction, from 0.13 and 0.39 m2.
* Rooms with unobserved sides are flagged: 5 of 6 and 9 of 9 rooms in the
  apartment captures are partially observed, with intervals doubled. That is
  an honest statement about these captures that the pipeline could not make
  before.
* Ghost faces are rejected by a test that does not depend on the segmentation.

## What got worse

* Footprint area inflated badly: 50.3 to 86.6 m2 for `1a8384c3f6` and 46.9 to
  64.7 m2 for `c7d28f72c6`, against a flat of roughly 75 m2. Cells extend to
  the observed bounds wherever a wall is missing, so a partially observed room
  is closed at the edge of what was seen rather than left open. The flag says
  the number is unreliable, but the number is still wrong and the footprint
  gate would fail against real ground truth.
* `c00a170fe1` went from 2 rooms to 4 and its footprint from 19.5 to 35.8 m2,
  for a capture that crosses two or three partly scanned spaces.
* Rooms paired across the apartment captures fell from 6 to 3.

## What remains

The gate still fails completely. 139 of 153 rows fail because a wall or a
room has no counterpart at all, and of the 14 rows where both captures
produced a wall, none agree within the tolerance.

The honest conclusion is that the declared root cause was incomplete. Room
partition is unstable, and that is true, but the deeper cause is that the two
captures observe different subsets of the building. No segmentation rule can
invent a wall that one capture never saw. Until coverage is comparable, room
level repeatability is not achievable, and the gate is partly measuring
capture overlap rather than reconstruction quality. That was listed in the
declaration as the third falsifier and it is the one that fired.

## Recommendation

1. **Reconsider the default.** `--segmentation cells` is the default as
   specified, but on the only measurable gate it is not better, and its
   footprint areas are worse. Flipping `segmentation` to `erosion` in
   `config/gates.yaml` reverts it in one line. My recommendation is to ship
   with `erosion` as the default and keep `cells` available, until the
   footprint inflation is fixed.
2. **Stop closing partially observed rooms at the observed bound.** Leave the
   unsupported side open and report the room as an area range rather than a
   polygon. That is the direct cause of the footprint inflation.
3. **Change the gate's denominator, or the capture protocol.** Scoring
   repeatability over walls that only one capture saw measures coverage. Either
   score only the overlapping region and report coverage separately, or fix
   the protocol so two captures of one property cover the same rooms.
4. **Do not spend more time here before the deadline.** Two tiers are
   unbuilt; this gate needs a protocol change more than another algorithm.
