# Status: branch `video-tier`

Final for this session. Worktree `../cozmo-video-tier`, **not merged**.

## What exists

| tier | state |
|---|---|
| lidar | untouched, still the reference |
| **video** | built, two fix-loop iterations, does not pass its 3% gate |
| **photo** | built, passes 8 of 12 quantities at its 8% gate |

## Results against tape

**Photo tier**, camera originals, gate 8%, after fix loops 2 and 3:

| run | within 8% | inside interval | Moto vs Nokia | footprint |
|---|---|---|---|---|
| **current: EXIF focal + density anchoring** | **8 of 12** | 11 of 12 | +10.0%, +9.9% | 75.54 m2 |
| EXIF focal only (loop 3 before) | 6 of 12 | 10 of 12 | +10.9%, +10.0% | 89.93 m2 |
| model guessing the focal | 3 of 12 | 7 of 12 | -4.5%, -0.2% | 111.10 m2 |
| messaging-app copies, model guessing | 8 of 12 | 11 of 12 | +1.9%, +1.8% | 79.85 m2 |

All give adjacency 3 of 3 and zero overlap.

Two loops, two causes, both measured:

* **Loop 2**: MapAnything was guessing the focal 39% long, which stretches a
  room sideways by 39% while the camera-height prior holds the ceiling right.
  Handing it the EXIF focal fixed it; the Nokia, which publishes no 35 mm
  equivalent, is the control that did not improve.
* **Loop 3**: a room side with no qualifying wall face was closed at the camera
  path plus a margin, which assumed the path lies inside the room. It does not:
  on bedroom_2 the path runs 0.61 m past the room's own wall. Anchoring to the
  outermost significant peak in point density instead took bedroom_2's long wall
  from +26.3% to +3.1% and every side from 16 of 20 anchored to 20 of 20.

Known remaining, both named with evidence in
`fix_loop/loop3_photo_unanchored_wall/POSTMORTEM.md`:

* **kitchen, +31.9%**, untouched by loop 3 as predicted. All four sides are on
  faces, but the rule takes the *outermost* qualifying face and the one it picked
  has 1584 points against thousands for its neighbours. The outermost-wins rule
  has the same defect the old fallback had.
* **bedroom_1, -14.4%**, now short where it was long: the density peak found a
  plane inside the true wall, probably a wardrobe front. The fix trades a
  consistent overshoot for a smaller two-sided error, which is an improvement and
  is not the same as being right.
* **bedroom_2_repeat, the Nokia**, +18.8%, still guessing its intrinsics.

**The video tier shares `fit_single_room` and inherits loop 3.** It was not
re-run, so every video number recorded below predates the change.

**Video tier**: 6 of 6 clips produce a plan, median wall error 35.3%, nothing
within 3%. It does not pass. Full before and after in
`fix_loop/loop2_video_scale/`.

## Fix loop 2, in order and provable from git

1. `89a09e9` determinism and the reconstruction cache
2. `2506691` BEFORE snapshot
3. `3609d25` DECLARATION, alone, before any fix code
4. `5e3b86a` the fix
5. `85e59b1` AFTER, DIFF, POSTMORTEM
6. `9bf7b4f` iteration 2 addendum, alone, before its code
7. iteration 2 measured and **rejected**; `sfm` stays the default

Two of eight predictions came true. Three declared falsifiers fired. That is
written up plainly in `POSTMORTEM.md` rather than dressed up.

## What this session learned that the code does not show

* **The scale cue was not the binding constraint.** A wall face had to reach
  1.5 m to count, inherited from the LiDAR tier, and a phone carried at 1.4 m
  never reconstructs that high. Every video room was the camera path in a box
  until that was found.
* **Wide separated views beat a walk along the walls.** Nine composed stills
  give 1%; fifty seconds of walking video of the same room gives 53%. Iteration
  2 wrongly read that as an engine difference; it is a capture difference. The
  next thing worth changing is the capture protocol, not the library.
* **pycolmap 4.2 is not bit-reproducible** through its public options here, so
  the cached reconstruction is what makes a run regenerable.

## Known limits

* Video tier: one clip per room. A whole-property walk is reconstructed as one
  space, with a warning.
* Openings: OWLv2 doors at the photo tier; none at the video tier. Windows are
  not attempted anywhere.
* The star stitch assumes a layout it cannot measure, and says so in every plan.
* Mirror and glass rejection still waits on `cozmo.lidar.ghosts` from main.
* No video or photo capture is in `benchmarks/captures.yaml`, because `bench`
  runs every entry and the tests run `bench`.

## What I would do next

1. Change the capture protocol to slow wide sweeps with pauses, and re-measure.
   This is the cheapest thing with the most evidence behind it.
2. Replace the camera-height prior with something measured: a reference object
   of known size in one frame.
3. Only then revisit the video geometry engine.
