# Spike 1: MapAnything as the whole video tier

Throwaway spike, 2026-09-20. Question: can MapAnything (facebook/map-anything-apache)
turn rgb frames alone into a metric, registered reconstruction good enough to fit a
floor plan? Scripts here are copied verbatim from the spike folder; they are evidence,
not library code, and nothing in `cozmo/` imports them.

## What was tested

Scan `data/sample/c00a170fe1` (Stray Scanner, iPhone LiDAR). The pipeline under test read
only `rgb.mp4`; the LiDAR depth, confidence and ARKit odometry were used to score it.

- `extract_frames.py` decodes N evenly spaced frames upright (rotate 90 clockwise).
- `run_infer.py` runs MapAnything on images only: no depth, no poses, no intrinsics. It
  asserts that the view dicts carry image data alone, so nothing metric leaks in.
- `scale_check.py` scores two independent scale checks against the capture:
  check A is the per-frame median of predicted depth over LiDAR depth on confidence-2
  pixels; check B is predicted trajectory length over ARKit trajectory length.
- `export_cloud.py` fuses the predicted points to PLY and draws a top-down density.

Run at 20, 40 and 80 frames on MPS with autocast.

## The numbers

| frames | depth ratio A, mean | A sd | A median | A min | A max | path ratio B | bbox diag ratio | seconds | peak RSS |
|---|---|---|---|---|---|---|---|---|---|
| 20 | 0.712 | 0.093 | 0.689 | 0.533 | 0.937 | 2.49 | 0.89 | - | - |
| 40 | 0.704 | 0.129 | 0.683 | 0.568 | 1.271 | 2.64 | 0.81 | - | - |
| 80 | 0.709 | 0.094 | 0.696 | 0.512 | 1.147 | 3.95 | 1.30 | 141 | 10.3 GB |

A correct reconstruction puts both ratios at 1.0.

## Decision: rejected as the video tier

Two failures, either one disqualifying.

1. **Scale is wrong and not correctable by a constant.** Depth comes out about 30% short
   (ratio A around 0.70) while the trajectory comes out 2.5 to 3.9 times too long (ratio
   B). Those two disagree, so no single scale factor fixes the model: the depth and the
   motion are inconsistent with each other. The per-frame spread is also wide, min 0.51
   against max 1.27 at 40 frames.

2. **Registration degrades with more frames.** Path ratio grows 2.49, 2.64, 3.95 as
   frames go 20, 40, 80, and the predicted cloud bounding box grows from 9 x 5 x 8 m to
   20 x 8 x 11 m for a space whose ARKit bounding box diagonal is about 6 m. The model is
   inventing trajectory, and it invents more of it the more frames it sees.

Memory is also a practical problem: 10.3 GB peak RSS and 16.3 GB of MPS driver memory at
80 frames, on a capture that needs hundreds.

Spike 2 (`../sfm_depth_spike/`) tested the replacement: classical SfM for poses plus a
learned metric depth model for dense geometry and scale.
