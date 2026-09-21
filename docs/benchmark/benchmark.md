# Benchmark: every capture with ground truth

Rebuild with `scripts/benchmark_all.py`. Tape readings are centimetres to the nearest inch, so `truth_uncertainty_m` is 0.013 and the coverage check widens the truth by it.

## Provenance

Video and photo plans cost about eight minutes a capture and were produced on the tier branch. They are reused, not recomputed. The lidar tier is run here because it takes seconds.

| capture | tier | plan | input hash matches | duration s | note |
|---|---|---|---|---|---|
| EXAMPLE | photo | no plan available | None | n/a |  |
| EXAMPLE_REPEAT | photo | no plan available | None | n/a |  |
| own_hall_photo | photo | no plan available | None | n/a |  |
| own_bedroom_1_photo | photo | no plan available | None | n/a |  |
| own_bedroom_2_photo | photo | no plan available | None | n/a |  |
| own_bedroom_2_repeat_photo | photo | no plan available | None | n/a |  |
| own_kitchen_photo | photo | no plan available | None | n/a |  |
| own_home_photo | photo | reused from the tier branch | False | 77 | input on disk differs from the one the plan was made from |
| own_hall_video | video | reused from the tier branch | True | 570 | room id renamed room_01 -> hall, geometry untouched |
| own_bedroom_1_video | video | reused from the tier branch | True | 507 | room id renamed room_01 -> bedroom_1, geometry untouched |
| own_bedroom_2_video | video | reused from the tier branch | True | 375 | room id renamed room_01 -> bedroom_2, geometry untouched |
| own_bedroom_2_repeat_video | video | reused from the tier branch | True | 318 | room id renamed room_01 -> bedroom_2, geometry untouched |
| own_kitchen_video | video | reused from the tier branch | True | 326 | room id renamed room_01 -> kitchen, geometry untouched |
| own_home_video | video | no plan available | None | n/a |  |

## Gates

One set of gates over every capture with ground truth. A gate covering more than one tier fails if any tier fails it.

| gate | result | value | threshold | n |
|---|---|---|---|---|
| opening_width | FAIL | 0 | 0.85 | 14 |
| ceiling_height | FAIL | 0.8584 | 0.015 | 9 |
| ceiling_height_diagnosis | FAIL | 0.8584 | 0.015 | 9 |
| repeatability | FAIL | 250.4 | 1 | 4 |
| wall_length_tier | FAIL | 45.82 | 1 | 28 |
| footprint | PASS | 0 | 0.08 | 0 |
| stitch_adjacency | PASS | 0 | 0 | 6 |
| stitch_overlap | FAIL | 10.02 | 0.05 | 6 |

### Wall length by tier

| tier | walls | within the tier budget | worst error |
|---|---|---|---|
| photo | 12 | 8 | 77.5 cm on kitchen B |
| video | 16 | 0 | 502.7 cm on bedroom_1 A |

## Interval coverage

Coverage is the share of tape readings inside the stated 95% interval. Confident garbage counts readings that fall outside an interval narrower than the median for that quantity: wrong and sure of itself.

| group | n | coverage | mean width, % of value | outside | confident garbage |
|---|---|---|---|---|---|
| all | 37 | 0.97 | 251 | 1 | 1 |
| photo | 16 | 0.94 | 43 | 1 | 1 |
| video | 21 | 1.00 | 409 | 0 | 0 |
| photo/ceiling_height | 4 | 0.75 | 44 | 1 | 1 |
| photo/wall_length | 12 | 1.00 | 42 | 0 | 0 |
| video/ceiling_height | 5 | 1.00 | 57 | 0 | 0 |
| video/wall_length | 16 | 1.00 | 519 | 0 | 0 |

## Repeatability

### own_bedroom_2_video against own_bedroom_2_repeat_video (video)

**Same device, the primary repeatability evidence.**

Devices: Nokia 8.1, Android and Nokia 8.1, Android.

Gate: FAIL, 0 of 8 wall rows within tolerance.

Walls seen in both: 0, median difference 0.0 cm. Registered footprint IoU 0.14.

## Timing

| capture | tier | seconds |
|---|---|---|
| own_home_photo | photo | 77 |
| own_hall_video | video | 570 |
| own_bedroom_1_video | video | 507 |
| own_bedroom_2_video | video | 375 |
| own_bedroom_2_repeat_video | video | 318 |
| own_kitchen_video | video | 326 |

## Head to head against AR Plan 3D

Both sides against tape, per shared dimension. A tie means the two errors differ by less than 1.5 cm.

### Our photo tier

| room | dimension | tape m | theirs m | their error cm | ours m | our error cm | closer |
|---|---|---|---|---|---|---|---|
| bedroom_1 | short_pair | 3.658 | 3.410 | 24.8 | 3.679 | 2.1 | ours |
| bedroom_1 | long_pair | 3.912 | 3.730 | 18.2 | 4.377 | 46.5 | theirs |
| kitchen | short_wall_1 | 2.692 | 2.750 | 5.8 | 2.649 | 4.4 | tie |
| kitchen | short_wall_2 | 2.692 | 2.700 | 0.8 | 2.649 | 4.4 | theirs |
| kitchen | long_wall_1 | 3.603 | 3.510 | 9.3 | 4.378 | 77.5 | theirs |
| kitchen | long_wall_2 | 3.603 | 3.790 | 18.7 | 4.378 | 77.5 | theirs |

**Beat or tie: 33% of 6 dimensions** (ours 1, tie 1, theirs 4).

### Our video tier

| room | dimension | tape m | theirs m | their error cm | ours m | our error cm | closer |
|---|---|---|---|---|---|---|---|
| bedroom_1 | short_pair | 3.658 | 3.410 | 24.8 | 5.935 | 227.8 | theirs |
| bedroom_1 | long_pair | 3.912 | 3.730 | 18.2 | 4.578 | 66.6 | theirs |
| kitchen | short_wall_1 | 2.692 | 2.750 | 5.8 | 1.806 | 88.7 | theirs |
| kitchen | short_wall_2 | 2.692 | 2.700 | 0.8 | 1.806 | 88.7 | theirs |
| kitchen | long_wall_1 | 3.603 | 3.510 | 9.3 | 3.162 | 44.1 | theirs |
| kitchen | long_wall_2 | 3.603 | 3.790 | 18.7 | 3.162 | 44.1 | theirs |

**Beat or tie: 0% of 6 dimensions** (ours 0, tie 0, theirs 6).

## What the brief asked for, and what was possible

The brief asks for the head to head at the lidar tier. That was impossible here: **no iPhone was available for capture**, so there is no lidar scan of the rooms the rival app measured, and the three supplied lidar scans are of a different property with no tape ground truth at all. The comparison is therefore run at the photo and video tiers, which do have captures of the same rooms the rival measured.

