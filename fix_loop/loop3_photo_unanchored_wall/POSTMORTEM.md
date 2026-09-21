# Fix loop 3: postmortem

## Predicted against actual

Five predictions, committed before the code. Four came true.

**Right.** Walls within gate went 6 of 12 to 8 of 12, inside the predicted 7 to
9. Every side is now anchored to evidence, 20 of 20 against a predicted 19 or
20. bedroom_2's long axis landed at +3.1%, inside the predicted band. And
kitchen did not move at all, which was predicted explicitly and matters more
than it looks: it was the control on whether the edit reached further than
intended. It did not.

**Wrong.** bedroom_1's long axis was predicted to land between 380 and 430 cm
and came in at 334.8, which is 14.4% **short** where it had been 20.9% long. The
magnitude improved and the sign flipped. Anchoring to the outermost significant
density peak found a plane that is inside the true wall on that side, most
likely a wardrobe front or a curtain hanging proud of it, and the fitter has no
way to tell that from the wall itself.

So the fix trades a consistent overshoot for a smaller two-sided error. That is
an improvement and it is not the same thing as being right.

## What the first attempt got wrong, and what it taught

The first implementation searched only **beyond** the camera path, on the
reasoning that a wall must be outside where the photographer stood. It found
nothing at all: 0 sides anchored, the result bit-identical to before.

The reason is worth keeping. On bedroom_2 the camera path runs to z = -2.43
while the wall is at about -1.82, so **the path extends 0.61 m past the room's
own wall**. A reconstruction that is stretched along one axis carries the
cameras out with it, so the camera path is not a reliable inner bound for the
room it was captured in. Letting the search start a metre inside the path is
what made it work.

That also explains the old fallback's behaviour. Closing an unanchored side at
"camera path plus a margin" assumed the path was inside the room. When the path
is already outside, the margin adds to an overshoot instead of covering an
undershoot, which is why the errors were all the same sign and all large.

## What is still wrong

**kitchen, +31.9%, untouched.** It has four sides on wall faces and is still a
metre long. The face it picked on that side has 1584 points, the fewest of any
it found, and sits at 2.83 m. This loop deliberately did not touch anchored
sides. The next loop should: the rule that takes the **outermost** qualifying
face has the same defect that the fallback had, and a face with a tenth of the
support of its neighbours should not outrank them just for being further out.

**bedroom_2_repeat, the Nokia,** improved from +40% to +18.8% but still fails.
It publishes no 35 mm equivalent, so it gets no EXIF focal and MapAnything is
still guessing its intrinsics. That is fix loop 2's residue, not this one's.
