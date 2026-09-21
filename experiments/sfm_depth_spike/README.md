# Spike 2: classical SfM poses plus monocular metric depth

Throwaway spike, 2026-09-20, after spike 1 rejected MapAnything. Question: does COLMAP
SfM for poses plus a learned metric depth model for dense geometry and scale give a video
tier good enough to fit a floor plan? Scripts here are copied verbatim from the spike
folder; they are evidence, not library code, and nothing in `cozmo/` imports them.

The pipeline under test read only `rgb.mp4`. LiDAR depth, confidence and ARKit odometry
were used to score it.

## Scripts

| script | step |
|---|---|
| `s2_frames.py` | sequential decode, every Nth frame, upright, 1280 long side, drop blurriest 20% |
| `s2_sfm.py` | pycolmap SIFT, sequential matching, incremental mapping, one shared SIMPLE_RADIAL camera |
| `s2_pose.py` | Sim3 (Umeyama) alignment of camera centres to ARKit: ATE and the true metres per SfM unit |
| `s2_export.py` | dump poses, intrinsics and sparse observations to npz so torch code never imports pycolmap |
| `s2_depth.py` | Depth Pro and Depth Anything V2 Metric Indoor on MPS; LiDAR ratio and LiDAR-free scale recovery |
| `s2_fuse.py` | per-frame robust scale and shift fit to SfM sparse depths, unproject, fuse, top-down plot, PLY |
| `s2_wall.py` | RMS perpendicular residual of a line fit to one wall, video tier against LiDAR |

## Geometry results

Scan A is `data/sample/c00a170fe1` at frame stride 6, scan B is `data/sample/c7d28f72c6`
at stride 20.

| | A stride 12 | A stride 6 | B stride 20 |
|---|---|---|---|
| decoded / candidates / kept frames | 1714 / 143 / 114 | 1714 / 286 / 229 | 9744 / 488 / 390 |
| largest SfM model | 24 images | 48 images | 19 images |
| registered fraction (largest model) | 21.1% | 21.0% | 4.9% |
| frames in any sub-model | 86 of 114 | 197 of 229 | 83 of 390 |
| sparse points | 2219 | 3689 | 745 |
| mean reprojection error | 0.58 px | 0.66 px | 0.78 px |
| COLMAP focal (ARKit truth) | 1066.0 (1066.5) | 1071.3 (1066.5) | 1039.8 (1042.4) |
| ATE RMSE after Sim3 | 3.38 cm | 2.66 cm | 1.74 cm |
| true metres per SfM unit | 0.201995 | 0.201528 | 0.274016 |

## Metric depth and LiDAR-free scale

30 frames on scan A, 19 on scan B, MPS. `s_est` is the LiDAR-free scale: per frame, the
median of metric depth over SfM depth at the sparse points, then the median across frames.

| model | s/frame A | median(pred/lidar), mean ± sd A | s_est/s_true A | s/frame B | ratio B | s_est/s_true B |
|---|---|---|---|---|---|---|
| Depth Pro, own focal estimate | 3.72 | 1.249 ± 0.104 | 1.2455 | 3.27 | 1.285 ± 0.214 | 1.2840 |
| Depth Pro, COLMAP focal | 3.60 | 0.982 ± 0.093 | **0.9893** | 3.35 | 1.023 ± 0.173 | **0.9874** |
| Depth Anything V2 Metric Indoor L | 0.46 | 1.352 ± 0.076 | 1.3981 | 0.33 | 1.338 ± 0.178 | 1.3018 |

Depth Pro's own focal estimate is the entire error: it guessed 1365 px on scan A where
the truth is 1071, and 1307 px on scan B where the truth is 1040, roughly +26% in both
cases, and metric depth scales with focal. Handing it the COLMAP focal drops the scale
error to 1.1% and 1.3%.

Depth Anything V2 is eight times faster with a tighter per-frame spread but carries a
fixed bias of about +35%. That bias does not matter once each depth map is fitted to the
frame's SfM sparse depths, which is why the dense stage uses it and the scale stage does
not.

## Wall straightness

Top-down density of points 1.0 to 2.2 m above the floor, one clean 1.3 m wall, RMS
perpendicular residual to a fitted line:

| | video tier | LiDAR |
|---|---|---|
| RMS | 4.35 cm | 0.96 cm |
| 95th percentile absolute | 9.99 cm | 1.93 cm |

## Decision: accepted, with registration as the open problem

- **Scale is solved.** Depth Pro with the COLMAP focal recovers metric scale to 1.1% and
  1.3% on two scans with no depth sensor. The COLMAP focal itself lands within 0.5% of
  ARKit on both. This is the number that killed spike 1 and it is now in hand.
- **Poses are solved locally.** 2.66 cm and 1.74 cm ATE RMSE, 0.6 to 0.8 px reprojection.
- **Walls are straight enough to fit.** 4.35 cm RMS against 0.96 for LiDAR: a thicker
  smear, but straight, and the top-down corners land within a few cm of the LiDAR corners.
  This is where the video tier's wider wall-face tolerance comes from.
- **Registration is the blocker.** COLMAP never builds one model: scan A splits into six
  chunks of 22 to 48 frames, scan B into eight with the largest at 19 of 390. Overlap 20,
  quadratic overlap, exhaustive matching and relaxed mapper init thresholds
  (`init_min_tri_angle` 4, `init_max_forward_motion` 1.0, `abs_pose_min_num_inliers` 15)
  were all tried and none moved the registered fraction. That knob is exhausted.

What the tier in `cozmo/pipeline/video/` does about it: keep every sub-model with 15 or
more images instead of only the largest, recover a metric scale per chunk, and bridge
neighbouring chunks with MapAnything used purely as a relative-pose oracle over an 8 frame
overlap, with its own scale discarded.

## Install problems worth remembering

1. `pycolmap` and `torch` each link their own `libomp`; importing both in one process
   aborts with `OMP: Error #15`. `KMP_DUPLICATE_LIB_OK` was not used because it can
   silently corrupt results. The fix is a process boundary: `s2_export.py` dumps the model
   to npz, and the torch scripts never import pycolmap. `cozmo/pipeline/video/sfm.py`
   carries the same boundary as a subprocess.
2. `pip install depth-pro` pins numpy back to 1.26.4, which breaks scipy 1.18
   (`module 'numpy' has no attribute 'long'`) and therefore transformers. Install
   depth-pro, then force `numpy>=2.1` afterwards. Depth Pro runs fine on numpy 2.
3. Depth Pro's default config hardcodes `./checkpoints/depth_pro.pt`, and `DepthProConfig`
   is a dataclass, not a namedtuple, so `cfg._replace(...)` fails. Assign
   `cfg.checkpoint_uri` directly.
4. pycolmap 4.2 turned `Image.cam_from_world` from a property into a method.
