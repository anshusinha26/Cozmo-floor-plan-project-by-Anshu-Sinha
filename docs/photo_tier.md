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

## Two photo sets, and the intrinsics bug they exposed

The rooms were shot once and stored twice. `data/own/` holds the **originals**
straight off the phones: 4096x3072 on a Moto Edge 50 Neo for hall, bedroom_1,
bedroom_2 and kitchen, 4032x3024 on a Nokia 8.1 for bedroom_2_repeat, all with
EXIF make, model and a 35 mm equivalent focal length. `data/own_compressed/`
holds what a messaging app did to three of them: 1200x1600, EXIF stripped.

They are the **same photographs**. Matching them by a normalised 32x32
correlation gives 1.000 for 9 of 9 shots in every room, so nothing here is about
which pictures were taken.

The originals scored worse, 3 of 12 within the gate against 8 of 12, and the
reason was a real bug.

**MapAnything was guessing the focal length, and guessing badly.** It works at a
392x518 tensor whatever it is handed, and on the originals it estimated 464 px
there. EXIF says 2617 px across the 4096 px side, which is 332 px in that
tensor: the estimate was **39% too long**. A focal too long means the model
believes it is seeing a narrower angle than it is, so it pushes the scene apart
sideways by the same factor. That is the whole error: ceilings were right
because the camera-height prior pins them, and walls were 33 to 47% long.

On the compressed copies it guessed 283 px, much nearer the truth, which is the
only reason they scored better. The tier was being graded on how lucky the
model's guess was.

So the focal is now handed to the model rather than guessed, scaled to the
working tensor by the same factor the image was. On bedroom_2 that took the
walls from 532.3 and 432.4 cm to 458.6 and 392.2, against a tape of 388.6 and
363.2.

Two supporting details, both checked and both wrong-able:

* **The long side.** EXIF gives the focal across the sensor's long side, and
  after the orientation rotation that side is the image height, not the width.
  The scale is averaged over both axes, which is right because the resize very
  nearly preserves the aspect ratio.
* **Only the 35 mm equivalent is usable.** A bare focal in millimetres needs a
  sensor width to become pixels. EXIF rarely carries it, and assuming a full
  frame sensor for a phone is wrong by about six times. The Nokia has no 35 mm
  equivalent, so it gets no intrinsics and the model estimates as before. That
  is deliberate: a wrong focal is worse than an estimated one.

**EXIF orientation was also never applied.** Every original is Orientation 6, a
quarter turn, and nothing applied it, so rooms were reconstructed lying on their
side with gravity pointing sideways. The compressed copies hid it by baking the
rotation in. Fixed, though on its own it moved bedroom_2 by about 1%, so it was
not what separated the two sets.

## Intervals and the gate

The gate at this tier is 8%. The camera-height prior alone is 0.12 on 1.40,
which is 8.6% before anything else is counted, so **this tier cannot pass its own
gate on the strength of the prior**. That is stated here rather than discovered
later. Passing needs the prior replaced by a measurement: a reference object of
known size in one photo, or a tape reading fed in as a constraint.
