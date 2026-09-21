# Status: branch `video-tier`

Final for this session. Worktree `../cozmo-video-tier`, **not merged**.

## What exists

| tier | state |
|---|---|
| lidar | untouched, still the reference |
| **video** | built, two fix-loop iterations, does not pass its 3% gate |
| **photo** | built, passes 8 of 12 quantities at its 8% gate |

## Results against tape

**Photo tier**, one folder of stills per room, gate 8%:

| room | quantity | tape cm | predicted cm | error |
|---|---|---|---|---|
| bedroom_1 | wall (door) | 365.8 | 367.9 | +0.6% |
| bedroom_1 | wall | 391.2 | 437.7 | +11.9% |
| bedroom_2 | wall (door) | 388.6 | 393.0 | +1.1% |
| bedroom_2 | wall | 363.2 | 366.8 | +1.0% |
| bedroom_2_repeat | wall (door) | 388.6 | 400.4 | +3.0% |
| bedroom_2_repeat | wall | 363.2 | 373.4 | +2.8% |
| kitchen | wall (door) | 269.2 | 264.9 | -1.6% |
| kitchen | wall | 360.3 | 437.8 | +21.5% |

8 of 12 within the gate, 11 of 12 tape values inside their stated interval,
adjacency 3 of 3 against truth, zero room overlap, and the two bedroom_2
captures agree to 1.9% **across two different phones**.

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
