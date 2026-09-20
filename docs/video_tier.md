# Video tier

One video file in, one dimensioned plan out. The tier reads the video and
nothing else: no depth sensor, no device poses, no intrinsics from the capture.
It is registered for `--tier video` and can be forced anywhere with
`--pipeline video`.

```
cozmo run --input data/own/bedroom_1 --tier video --out runs/video/bedroom_1
cozmo run --input data/sample/c00a170fe1 --tier video --out runs/video/c00a170fe1 --video-rotation 90
```

Weights are fetched once with `scripts/fetch_weights.sh`. Device order is cuda,
then mps, then cpu.

## Stages

| stage | what it does | why it is there |
|---|---|---|
| `frames` | ffmpeg decodes at about 10 fps, long side 1280, then the blurriest 20% are deleted | 4K frames never reach Python; OpenCV seeks wrongly on phone HEVC |
| `sfm` | COLMAP SIFT, sequential matching overlap 10, one shared SIMPLE_RADIAL camera | poses, sparse points, and the focal length the scale stage needs |
| `scale` | Depth Pro on the COLMAP focal, median of per-frame medians of metric over SfM depth | metres per SfM unit, per chunk, with no depth sensor |
| `bridge` | MapAnything over 4 + 4 frames joins neighbouring chunks rigidly | COLMAP splits a room into chunks that share no points |
| `dense` | Depth Anything V2 fitted to each frame's SfM sparse depths, cached | dense metric geometry; the fitted maps are reused by the drift step |
| `gravity` | RANSAC floor plane seeded by the mean camera up vector | stands the cloud upright so the backend's height logic applies |
| `drift` | Manhattan yaw snap per SfM chunk, then a re-fuse | bridges fix a chunk's yaw to a few degrees, not a fraction of one |
| `assemble` | the LiDAR tier's backend, unchanged, through one adapter | levels, walls, rooms, openings, contract assembly |

`sfm` runs in a subprocess. pycolmap and torch each link their own libomp and
importing both into one interpreter aborts with `OMP: Error #15`. The process
boundary is the fix; `KMP_DUPLICATE_LIB_OK` is not used because it can silently
corrupt results.

## Frame decoding and rotation

ffmpeg applies a container rotation tag by itself, so phone video comes out
upright with no help and `--video-rotation auto` (the default) is correct for
it. Stray Scanner's `rgb.mp4` carries no tag and needs `--video-rotation 90`;
`benchmarks/captures.yaml` carries a `video_rotation` field per capture so
`cozmo bench` does not need the flag.

Of the five own-capture clips, four carry a `-90` tag and one, `bedroom_1`,
carries none and is genuinely landscape. Both come out upright under `auto`.

Frame budget: at most 600 decoded frames per clip, with the frame rate lowered
until the clip fits, then the blurriest 20% dropped. An 86 s clip decodes at
7.0 fps rather than 10.

## Chunks, and why they are all kept

COLMAP does not produce one model for a room scan. On `c00a170fe1` it split
into six sub-models where the largest held 48 of 229 frames; on the own
captures it splits into five to eight. Keeping only the largest throws away most
of the capture, so every sub-model with at least 15 registered images is kept as
a **chunk**, each with its own metric scale.

Chunks are consecutive in time, so the last frames of one and the first frames
of the next see overlapping geometry even though no feature track survived the
gap. **Bridging** runs MapAnything on those 4 + 4 frames, images only, and uses
it purely as a relative-pose oracle. Its own scale is discarded: spike 1
measured its trajectory running 2.5 to 3.9 times long and its depth 30% short.
Each side is Sim3-aligned to its own chunk's metric cameras, and the two
alignments compose into a rigid transform.

A bridge is accepted only when

* both alignment residuals are under `max(0.12 m, 25% of the overlap's camera span)`, and
* the two implied scales agree within 15%.

Disagreeing scales mean MapAnything did not see one consistent scene across the
overlap. A rejected bridge leaves the chunks separate; the tier never guesses.
The largest bridged group is what reaches the output, and every dropped chunk is
named in the plan's warnings with the share of the video it covered.

## Tier parameters

Wall tolerances are wider than the LiDAR tier's, and the number comes from
measurement, not taste. Spike 2 fitted a line to one clean wall in the top-down
band and got 4.35 cm RMS against 0.96 cm for the same wall from LiDAR. A face
histogram binned for a 1 cm wall cannot find a 4 cm one.

| parameter | lidar | video |
|---|---|---|
| `wall.hist_bin_m` | 0.02 | 0.04 |
| `wall.peak_min_separation_m` | 0.06 | 0.10 |
| `wall.max_gap_m` | 0.35 | 0.45 |
| `room.grid_m` | 0.02 | 0.03 |
| `room.snap_m` | 0.15 | 0.22 |
| `uncertainty.abs_floor_m` | 0.01 | 0.03 |

## Drift correction

The LiDAR tier corrects drift inside one continuous trajectory. This tier's
error is different: each chunk is internally rigid and the error is in how the
chunks sit relative to each other, carried in from the bridge. So the drift step
is a **Manhattan yaw snap per SfM chunk**: each chunk's own wall normals have a
dominant direction modulo 90 degrees, the difference from the direction the
whole group agrees on is that chunk's yaw error, and the chunk is rotated about
its own camera centroid to remove it. A correction over 6 degrees is rejected,
because a chunk that looks 15 degrees off usually has too little wall to measure.

`--drift-correction off` skips the snap and adds a warning. Re-fusing after the
snap is cheap because the fitted depth maps are cached, so no network pass is
repeated.

## Intervals

Three terms combine in quadrature into the `depth_scale_bias` the backend reads,
and one multiplier sits on top.

* **Systematic, 3%** (`uncertainty.systematic_scale_bias`). Spike 2 measured the
  LiDAR-free scale to 1.1% on `c00a170fe1` and 1.3% on `c7d28f72c6`. The tier
  claims 3%, wider than either, and stays there **until it is calibrated against
  tape data**. Two scans of one device do not earn a tight claim. This is marked
  `status: PROVISIONAL` in `config/gates.yaml`.
* **Measured scale spread.** The scale stage takes the median of per-frame
  ratios in each chunk; the standard error of that median (about 1.25 sigma over
  the square root of the frame count) enters the budget, weighted by chunk size.
  This is not a formality. On close-range handheld room loops the per-frame
  ratios disagree by a factor of five, and a cross-check against Depth Anything
  V2 on the same frames put the correlation of the two models' log ratios at
  0.18: two independent models drifting in uncorrelated directions, which means
  the SfM chunk is self-consistent and each depth model is independently
  unreliable on near, glossy, textureless surfaces.
* **Chunk disagreement.** When several chunks reach the output, their scales
  spread about the group median, and no single number removes that.

**Coverage.** If less than 60% of the decoded video reached the output, every
interval is multiplied by 1.6 and the plan warns that it should be read as a
fragment. A plan built from a third of a room is not entitled to the same
interval as one built from all of it.

Nothing here makes a fragment accurate. It makes the number honest about what
it is.

## Known limits

* **Monocular metric scale is the weak link on close-range captures.** The
  method is sound (1.1% and 1.3% on the sample scans) but its accuracy depends
  on the content, and a room loop shot half a metre from a glossy wall gives a
  depth model almost nothing. The measured spread goes into the interval, so
  the failure is visible rather than silent, but a tape calibration is the real
  fix and it is not done yet.
* **Registration is not solved**, only worked around. Bridging recovers a large
  connected group on the slow 4K loops; it does not turn a scan into one model.
* **Mirrors.** A wardrobe mirror puts a confident wall where the room continues.
  The face-support check that drops such faces lives in `cozmo.lidar.ghosts`
  and is used when it is present in the build; the plan warns when it is not.
* **Windows are not attempted**, same as the LiDAR tier.
* **Damage detection is not implemented.** Two paper sheets taped to a wall in
  `bedroom_2_repeat` are staged damage and this tier does not look for them.

## Evidence

`experiments/mapanything_spike/` and `experiments/sfm_depth_spike/` hold the two
spikes that decided this design, with the scripts and the numbers.
