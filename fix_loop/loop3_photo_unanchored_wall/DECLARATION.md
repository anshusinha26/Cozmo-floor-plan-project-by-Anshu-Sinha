# Fix loop 3: the wall the room fitter never anchors

Declared before any fix code. The BEFORE run is in `before/`, regenerable with
`before/regenerate.sh` from the commit in `before/provenance.json`.

## Worst gate

**Photo-tier wall length against tape.** 6 of 12 quantities within the 8% gate.
The failures are not spread evenly: they are one axis per room.

| room | door-wall axis | error | other axis | error |
|---|---|---|---|---|
| bedroom_1 | 363.7 vs 365.8 | **-0.6%** | 472.9 vs 391.2 | **+20.9%** |
| bedroom_2 | 392.2 vs 388.6 | **+0.9%** | 458.6 vs 363.2 | **+26.3%** |
| kitchen | 265.8 vs 269.2 | **-1.3%** | 475.3 vs 360.3 | **+31.9%** |
| bedroom_2_repeat (Nokia, no EXIF focal) | 431.4 vs 388.6 | +11.0% | 508.5 vs 363.2 | +40.0% |

One axis per room is essentially exact and the other is 82 to 115 cm long. Every
error has the same sign.

## Root cause, and a correction to the obvious explanation

The expected explanation was that the long axis is the one whose sides the
fitter could not anchor to a wall face, so it closes them at the camera path
plus a 0.35 m margin. The BEFORE run's own side-by-side record says that is
**part** of the story and not all of it:

| room | supported sides | unanchored side | long axis |
|---|---|---|---|
| bedroom_1 | 3 of 4 | `x+` | x |
| bedroom_2 | 3 of 4 | `z-` | z |
| bedroom_2_repeat | 3 of 4 | `z+` | z |
| hall | 3 of 4 | `z+` | not scored |
| **kitchen** | **4 of 4** | none | **z, +31.9%** |

So:

* **Three rooms have exactly one unanchored side**, not two, on the long axis.
  Half the excess is therefore a margin problem at most, not twice the margin.
* **Kitchen has every side anchored and is still 31.9% long.** Its `z+` face sits
  at 2.83 m with 1584 points, the fewest of any face it found. A face was found;
  it was the wrong one, further out than the wall.

Both failures come from the same decision. `_pick_side` takes the **outermost**
qualifying face, on the reasoning that furniture sits between the camera and the
wall. That is right for a near face and wrong for a far one: a window, a curtain,
a mirror or a doorway lets points land beyond the wall, and the outermost face is
then outside the room. When the strict face test rejects those points instead,
the side is left unanchored and the camera-path fallback also overshoots,
because a photographer stands back from the wall they are photographing.

The unifying statement is that **the fitter has no evidence about where a wall
is other than where points are, and it currently takes the extreme rather than
the strongest**.

## The fix

For a side with no qualifying face, search again with a relaxed test before
falling back: the outermost **significant peak in the point-density histogram**
along that axis, beyond the camera path, inside the wall height band, with
looser length and height requirements than the strict face test. Curtains,
windows and wardrobes break the strict test but still leave a dense plane of
points. A side anchored this way is flagged **weakly supported** and its
interval widened. Only if that finds nothing does the camera-path fallback
apply, with a documented margin and a partially-observed flag.

## Predicted numbers

| quantity | before | predicted after |
|---|---|---|
| bedroom_1 long axis | 472.9 cm, +20.9% | 380 to 430 cm, within 10% |
| bedroom_2 long axis | 458.6 cm, +26.3% | 355 to 405 cm, within 10% |
| kitchen long axis | 475.3 cm, +31.9% | **unchanged, it is already anchored** |
| walls within the 8% gate | 6 of 12 | 7 to 9 of 12 |
| sides anchored to a face across the five rooms | 16 of 20 | 19 or 20 of 20 |

Kitchen is predicted **not** to improve, because its side is already anchored and
this fix only touches unanchored sides. If kitchen improves, something other
than what is described here changed.

## What would falsify it

* **No density peak exists near the true wall** on the unanchored sides. Then the
  points simply are not there, the relaxed search finds nothing, and the fallback
  is the only option: the fix cannot work and the problem is reconstruction
  coverage, not the fitter.
* **The relaxed search anchors further out than the camera-path fallback.** Then
  the outermost-peak rule has the same defect as the outermost-face rule and the
  fix makes matters worse.
* **bedroom_1 and bedroom_2 do not both improve.** One improving could be noise.
* **kitchen changes.** It has no unanchored side, so this fix must not touch it.
  A change means the edit reached further than intended.
