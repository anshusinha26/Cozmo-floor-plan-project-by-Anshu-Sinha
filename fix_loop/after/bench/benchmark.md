# Benchmark report

Captures: 5. cozmo 0.1.0.

**WARNING: some plans came from the STUB PIPELINE. Their numbers describe the harness, not a reconstruction.**

## Captures

| capture | space | tier | pipeline | repeat_of | multi_room | rooms | duration_s | stages (s) | plan sha256 |
|---|---|---|---|---|---|---|---|---|---|
| EXAMPLE | example_flat | photo | stub |  | True | 2 | 0.0 | provenance 0.02, hand_written_geometry 0.00, hand_written_stitch 0.00, hand_written_damage 0.00, render 0.10 | f817dfc5d6fe |
| EXAMPLE_REPEAT | example_flat | photo | stub | EXAMPLE | True | 2 | 0.0 | provenance 0.01, hand_written_geometry 0.00, hand_written_stitch 0.00, hand_written_damage 0.00, render 0.06 | 6dd349e6785e |
| c00a170fe1 | sample_partial_spaces | lidar | lidar |  | False | 4 | 4.6 | fuse_raw 2.15, drift_estimate 0.07, fuse_corrected 2.00, openings 0.01, drift_report 0.03, assemble 0.11, debug_images 0.25, render 0.07 | be6036b86c9c |
| 1a8384c3f6 | sample_apartment | lidar | lidar |  | True | 6 | 15.5 | fuse_raw 7.06, drift_estimate 0.25, fuse_corrected 6.57, openings 0.35, drift_report 0.49, assemble 0.34, debug_images 0.45, render 0.22 | 2ee1a33d9239 |
| c7d28f72c6 | sample_apartment | lidar | lidar | 1a8384c3f6 | True | 9 | 34.5 | fuse_raw 15.09, drift_estimate 0.53, fuse_corrected 14.71, openings 0.97, drift_report 1.79, assemble 0.81, debug_images 0.49, render 0.37 | 6a4cab8853ca |

## Captures with no ground truth

**These captures have no tape or laser measurements, so nothing below is an accuracy result.** Reported: what the pipeline produced, how long it took, and whether the output is self-consistent.

| capture | tier | rooms | walls | openings | footprint m2 | sum of rooms m2 | room overlap m2 | rooms connected | ceiling from prior | duration_s |
|---|---|---|---|---|---|---|---|---|---|---|
| c00a170fe1 | lidar | 4 | 16 | 0 | 35.85 | 35.85 | 0.000 | no ['room_02', 'room_03', 'room_04'] | 4/4 | 4.6 |
| 1a8384c3f6 | lidar | 6 | 110 | 6 | 86.59 | 84.04 | 0.000 | no ['connector_01', 'room_02', 'room_04', 'room_05'] | 6/6 | 15.5 |
| c7d28f72c6 | lidar | 9 | 224 | 9 | 64.71 | 61.30 | 0.000 | no ['connector_01', 'connector_02', 'connector_03', 'connector_04', 'connector_05', 'room_02', 'room_03', 'room_04'] | 8/9 | 34.5 |

### Repeat pair: 1a8384c3f6 and c7d28f72c6 (lidar)

Registration: rotation 328.5119525266558 degrees, translation (-6.04, 0.47) m, footprint IoU 0.61.

Same space check: 3 of 6 rooms pair by polygon IoU. Verdict: **same space** (registered footprint IoU at least 0.5 and at least half the rooms pairing by polygon IoU). The gate below is scored either way; a weak verdict is itself evidence about the segmentation, not a reason to skip scoring.

Agreement between two captures is repeatability, not accuracy. Both can be wrong together.

Room matching: 6 rooms in 1a8384c3f6, 9 in c7d28f72c6, 3 matched at IoU >= 0.3 (IoU values [0.465, 0.403, 0.536]). Unmatched: ['room_02', 'room_03', 'connector_01'] and ['room_03', 'connector_01', 'connector_02', 'connector_03', 'connector_04', 'connector_05'].

Wall matching inside matched rooms: 32 paired by nearest parallel face within 0.3 m, 164 with no counterpart.

Repeatability gate: FAIL on 302 wall rows, worst ratio inf against the allowed 1.0. Within tolerance: 1 of 302.

Worst matched wall: room_01~room_01 w23~w89 2.321 m vs 0.512 m, difference 180.9 cm against 1.0 cm allowed.

Of the 32 matched wall pairs, 1 are within tolerance.

Rows failing because a wall or room has no counterpart: 270.


## Gate summary (captures with ground truth)

| gate | result | value | threshold | n |
|---|---|---|---|---|
| opening_width | FAIL | 0.0000 | 0.8500 | 10 |
| ceiling_height | FAIL | 0.2000 | 0.0150 | 4 |
| ceiling_height_diagnosis | FAIL | 0.2000 | 0.0150 | 4 |
| repeatability | PASS | 0.0000 | 1.0000 | 8 |
| wall_length_tier | FAIL | 2.5000 | 1.0000 | 16 |
| footprint | PASS | 0.0400 | 0.0800 | 2 |
| stitch_adjacency | PASS | 0.0000 | 0.0000 | 2 |
| stitch_overlap | PASS | 0.0000 | 0.0500 | 2 |

---

# Evaluation report

Captures: 2. Gates passed: 4/8. Overall: FAIL. Ceiling diagnosis: **repeatable_but_biased**.

**WARNING: at least one evaluated plan came from the STUB PIPELINE. These numbers say nothing about reconstruction quality.**

## Gates

| gate | result | value | threshold | n | note |
|---|---|---|---|---|---|
| opening_width | FAIL | 0.0000 | 0.8500 | 10 |  |
| ceiling_height | FAIL | 0.2000 | 0.0150 | 4 |  |
| ceiling_height_diagnosis | FAIL | 0.2000 | 0.0150 | 4 | label: repeatable_but_biased |
| repeatability | PASS | 0.0000 | 1.0000 | 8 |  |
| wall_length_tier | FAIL | 2.5000 | 1.0000 | 16 |  |
| footprint | PASS | 0.0400 | 0.0800 | 2 |  |
| stitch_adjacency | PASS | 0.0000 | 0.0000 | 2 |  |
| stitch_overlap | PASS | 0.0000 | 0.0500 | 2 |  |

## Matching counts

| capture | tier | rooms matched/missing/phantom | walls matched/unmatched truth/unmatched pred | openings matched/missed/phantom |
|---|---|---|---|---|
| EXAMPLE | photo | 2/0/0 | 8/0/0 | 0/3/2 |
| EXAMPLE_REPEAT | photo | 2/0/0 | 8/0/0 | 0/3/2 |

## Per-room errors

### EXAMPLE (photo, stub-0.1.0)

| room | ceiling pred | ceiling truth | abs err | floor area pred | floor area truth | abs err | wall order reversed |
|---|---|---|---|---|---|---|---|
| living | 2.700 | 2.500 | 0.200 | 18.480 | 20.000 | 1.520 | yes |
| hall | 2.700 | 2.500 | 0.200 | 3.600 | 3.000 | 0.600 | yes |

Walls:

| room | truth wall | pred wall | truth m | pred m | ci low | ci high | abs err |
|---|---|---|---|---|---|---|---|
| living | south | w4 | 5.000 | 4.400 | 4.250 | 4.550 | 0.600 |
| living | west | w3 | 4.000 | 4.200 | 4.050 | 4.350 | 0.200 |
| living | north | w2 | 5.000 | 4.400 | 4.250 | 4.550 | 0.600 |
| living | east | w1 | 4.000 | 4.200 | 4.050 | 4.350 | 0.200 |
| hall | west | h4 | 3.000 | 3.000 | 2.850 | 3.150 | 0.000 |
| hall | north | h3 | 1.000 | 1.200 | 1.050 | 1.350 | 0.200 |
| hall | east | h2 | 3.000 | 3.000 | 2.850 | 3.150 | 0.000 |
| hall | south | h1 | 1.000 | 1.200 | 1.050 | 1.350 | 0.200 |

Missing rooms: none. Phantom rooms: none. Missed openings: ['door_main', 'window_north', 'door_main']. Phantom openings: ['o1', 'o2'].

Footprint: pred 22.080 m2, truth 23.000 m2 (sum of room floor areas). Room overlap (geometric): 0.000 m2.

Warnings: STUB PIPELINE: NOT A REAL RECONSTRUCTION

### EXAMPLE_REPEAT (photo, stub-0.1.0)

| room | ceiling pred | ceiling truth | abs err | floor area pred | floor area truth | abs err | wall order reversed |
|---|---|---|---|---|---|---|---|
| living | 2.700 | 2.500 | 0.200 | 18.480 | 20.000 | 1.520 | yes |
| hall | 2.700 | 2.500 | 0.200 | 3.600 | 3.000 | 0.600 | yes |

Walls:

| room | truth wall | pred wall | truth m | pred m | ci low | ci high | abs err |
|---|---|---|---|---|---|---|---|
| living | south | w4 | 5.000 | 4.400 | 4.250 | 4.550 | 0.600 |
| living | west | w3 | 4.000 | 4.200 | 4.050 | 4.350 | 0.200 |
| living | north | w2 | 5.000 | 4.400 | 4.250 | 4.550 | 0.600 |
| living | east | w1 | 4.000 | 4.200 | 4.050 | 4.350 | 0.200 |
| hall | west | h4 | 3.000 | 3.000 | 2.850 | 3.150 | 0.000 |
| hall | north | h3 | 1.000 | 1.200 | 1.050 | 1.350 | 0.200 |
| hall | east | h2 | 3.000 | 3.000 | 2.850 | 3.150 | 0.000 |
| hall | south | h1 | 1.000 | 1.200 | 1.050 | 1.350 | 0.200 |

Missing rooms: none. Phantom rooms: none. Missed openings: ['door_main', 'window_north', 'door_main']. Phantom openings: ['o1', 'o2'].

Footprint: pred 22.080 m2, truth 23.000 m2 (sum of room floor areas). Room overlap (geometric): 0.000 m2.

Warnings: STUB PIPELINE: NOT A REAL RECONSTRUCTION

## Calibration

Coverage target is the nominal ci_level (0.95). Confident garbage = truth outside the interval and interval narrower than the per-quantity median width.

Overall:

| group | n | coverage | mean width % of value | outside | confident garbage |
|---|---|---|---|---|---|
| all | 26 | 0.308 | 13.3 | 18 | 6 |

By tier:

| group | n | coverage | mean width % of value | outside | confident garbage |
|---|---|---|---|---|---|
| photo | 26 | 0.308 | 13.3 | 18 | 6 |

By quantity:

| group | n | coverage | mean width % of value | outside | confident garbage |
|---|---|---|---|---|---|
| ceiling_height | 4 | 0.000 | 7.4 | 4 | 0 |
| floor_area | 4 | 0.500 | 20.0 | 2 | 2 |
| footprint_area | 2 | 1.000 | 20.0 | 0 | 0 |
| wall_length | 16 | 0.250 | 12.2 | 12 | 4 |

By tier and quantity:

| group | n | coverage | mean width % of value | outside | confident garbage |
|---|---|---|---|---|---|
| photo/ceiling_height | 4 | 0.000 | 7.4 | 4 | 0 |
| photo/floor_area | 4 | 0.500 | 20.0 | 2 | 2 |
| photo/footprint_area | 2 | 1.000 | 20.0 | 0 | 0 |
| photo/wall_length | 16 | 0.250 | 12.2 | 12 | 4 |

## Repeatability

| space | tier | capture a | capture b | room | wall | a | b | diff | allowed | ok |
|---|---|---|---|---|---|---|---|---|---|---|
| example_flat | photo | EXAMPLE | EXAMPLE_REPEAT | hall | east | 3.000 | 3.000 | 0.000 | 0.015 | yes |
| example_flat | photo | EXAMPLE | EXAMPLE_REPEAT | hall | north | 1.200 | 1.200 | 0.000 | 0.010 | yes |
| example_flat | photo | EXAMPLE | EXAMPLE_REPEAT | hall | south | 1.200 | 1.200 | 0.000 | 0.010 | yes |
| example_flat | photo | EXAMPLE | EXAMPLE_REPEAT | hall | west | 3.000 | 3.000 | 0.000 | 0.015 | yes |
| example_flat | photo | EXAMPLE | EXAMPLE_REPEAT | living | east | 4.200 | 4.200 | 0.000 | 0.021 | yes |
| example_flat | photo | EXAMPLE | EXAMPLE_REPEAT | living | north | 4.400 | 4.400 | 0.000 | 0.022 | yes |
| example_flat | photo | EXAMPLE | EXAMPLE_REPEAT | living | south | 4.400 | 4.400 | 0.000 | 0.022 | yes |
| example_flat | photo | EXAMPLE | EXAMPLE_REPEAT | living | west | 4.200 | 4.200 | 0.000 | 0.021 | yes |

Worst case: EXAMPLE vs EXAMPLE_REPEAT hall/east diff 0.000 m against allowed 0.015 m.

## Ceiling height diagnosis

| space | room | captures | spread m | mean error m | label |
|---|---|---|---|---|---|
| example_flat | hall | 2 | 0.000 | 0.200 | repeatable_but_biased |
| example_flat | living | 2 | 0.000 | 0.200 | repeatable_but_biased |
