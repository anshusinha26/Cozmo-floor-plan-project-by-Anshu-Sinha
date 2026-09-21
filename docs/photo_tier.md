# Photo tier

One folder per room, two or more stills in each, images only. No EXIF required.

```
cozmo run --input data/own --tier photo --out runs/photo/own
cozmo run --input data/own --tier photo --out runs/photo/own --connector hall --camera-height 1.45
```

## Stages

| stage | what it does |
|---|---|
| per room | MapAnything on that room's photos: world points, poses, intrinsics |
| gravity | RANSAC floor plane seeded by the cameras' own up vectors |
| scale | the camera-height prior, the same one fix loop 2 gave the video tier |
| shape | the single-room fitter: one rectilinear room around the camera positions |
| openings | OWLv2 "door" detections, placed on the wall their 3D points lie on |
| stitch | every room attached to a connector, star topology |

## Scale does not come from MapAnything

Spike 1 measured MapAnything's depth at 0.70x truth while its trajectory ran 2.5
to 3.9 times long. Those two do not agree with each other, so there is no single
factor that fixes its output and no reason to trust its absolute scale. Its
geometry and its relative poses are used; its scale is discarded.

What replaces it is the same thing fix loop 2 gave the video tier: the capture
protocol says roughly where the phone was held, so each room is scaled to put
its own median camera that far above its own floor plane. Default 1.40 m plus or
minus 0.12 m, overridden with `--camera-height`.

Depth Pro is a second opinion, and only when EXIF carries a focal length, which
is the one case where it can be told the number it needs. It never sets the
scale. Its job is to disagree, and the size of the disagreement widens intervals.

## The star layout, and what it does not claim

No photograph sees two rooms at once, so nothing in a per-room capture measures
where one room sits relative to another. Rather than pretend otherwise, the tier
picks a connector (`--connector`, else a folder named hall, corridor, living,
landing or lobby, else the largest room) and attaches every other room to its
perimeter, door to door where both sides have a free door and wall to wall
otherwise. shapely enforces that no two rooms overlap; a room that cannot be
placed clear within 6 m is flagged.

Room shapes and sizes are measurements. The arrangement is an assumption, it is
declared in `plan.assumptions`, the placements carry plus or minus 15 degrees,
and the footprint interval is widened by 2.5x over the quadrature sum of the
rooms' own area intervals.

## Openings

A doorway is a gap in a wall, and the geometric finder can only see a gap when
the wall around it was reconstructed on both sides, which three photos rarely
manage. So the photo tier looks for the door itself with OWLv2, then uses
MapAnything's per-pixel 3D points to turn a box into a width, a height and an
offset along the wall those points lie on. A detection that lands on no wall is
dropped rather than forced onto the nearest one, and one door seen in three
photos is merged into one.

If OWLv2 cannot be loaded, the plan says openings were not attempted at this
tier and reports none. Absent is not the same as confirmed absent, and the
warning says so.

## Per-room video

The same stitcher takes per-room **video** folders, so `--tier video` on a
folder of room clips reconstructs each clip on its own and stitches the results.
Each room's own plan is written beside its debug output.

## Two photo sets, and which is the benchmark

The rooms were shot twice over. `data/own/` holds the **originals** straight off
the phones: 4096x3072 on a Moto Edge 50 Neo for hall, bedroom_1, bedroom_2 and
kitchen, 4032x3024 on a Nokia 8.1 for bedroom_2_repeat, all with EXIF make,
model and a 35 mm equivalent focal length. `data/own_compressed/` holds what a
messaging app did to three of those rooms: 1200x1600, EXIF stripped.

The originals are the primary benchmark, because they are what a real capture
looks like. The compressed set is kept and labelled as a robustness result: the
same rooms after a messaging app has been through them.

Two things came out of comparing them, and only one was expected.

**EXIF focal length was never being read.** It sits in the Exif sub-IFD, not the
top level, and the reader only looked at the top level, so the Depth Pro second
opinion has never run on any capture. Fixed. Only the 35 mm equivalent is used:
a bare focal length in millimetres needs a sensor width to become pixels, and
assuming a full frame sensor for a phone is wrong by about six times, which is
worse than having no second opinion at all.

**The compressed copies score better than the originals, and that is the
result.** 8 of 12 quantities within the 8% gate on the messaging-app copies
against 3 of 12 on the originals, with the same code, the same rooms and the
same tape. It is the opposite of what was expected and it is not explained by
either bug above: applying the orientation moved bedroom_2 by about 1%. The two
sets are not the same photographs, only the same rooms, so the likely cause is
which shots each set contains rather than the compression itself. Until that is
pinned down, the honest statement is that this tier has reached 8 of 12 on one
photo set and 3 of 12 on another, and nobody should quote the better number
without the worse one.

**EXIF orientation was never being applied.** Every original is Orientation 6, a
quarter turn, and nothing applied it, so MapAnything reconstructed rooms lying on
their side and the camera up vectors that set gravity pointed sideways with them.
The compressed copies hid this, because the messaging app baked the rotation in.
Fixed, and the plan reports how many photos needed turning. On its own it moved
bedroom_2's walls by about 1%, so it was not what separated the two sets.

## Intervals and the gate

The gate at this tier is 8%. The camera-height prior alone is 0.12 on 1.40,
which is 8.6% before anything else is counted, so **this tier cannot pass its own
gate on the strength of the prior**. That is stated here rather than discovered
later. Passing needs the prior replaced by a measurement: a reference object of
known size in one photo, or a tape reading fed in as a constraint.
