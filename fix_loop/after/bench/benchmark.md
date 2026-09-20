# Benchmark report

Captures: 17. cozmo 0.1.0.

**WARNING: some plans came from the STUB PIPELINE. Their numbers describe the harness, not a reconstruction.**

## Captures

| capture | space | tier | pipeline | repeat_of | multi_room | rooms | duration_s | stages (s) | plan sha256 |
|---|---|---|---|---|---|---|---|---|---|
| EXAMPLE | example_flat | photo | stub |  | True | 2 | 0.0 | provenance 0.01, hand_written_geometry 0.00, hand_written_stitch 0.00, hand_written_damage 0.00, render 0.10 | 48f77eba660f |
| EXAMPLE_REPEAT | example_flat | photo | stub | EXAMPLE | True | 2 | 0.0 | provenance 0.01, hand_written_geometry 0.00, hand_written_stitch 0.00, hand_written_damage 0.00, render 0.06 | 67ac7f349e11 |
| c00a170fe1 | sample_partial_spaces | lidar | lidar |  | False | 4 | 4.4 | fuse_raw 2.01, drift_estimate 0.06, fuse_corrected 1.95, openings 0.01, drift_report 0.03, assemble 0.08, debug_images 0.24, render 0.07 | 77d0a5e28c9e |
| 1a8384c3f6 | sample_apartment | lidar | lidar |  | True | 6 | 14.0 | fuse_raw 6.35, drift_estimate 0.16, fuse_corrected 6.09, openings 0.28, drift_report 0.47, assemble 0.31, debug_images 0.38, render 0.15 | 5b2179073305 |
| c7d28f72c6 | sample_apartment | lidar | lidar | 1a8384c3f6 | True | 9 | 29.0 | fuse_raw 12.39, drift_estimate 0.34, fuse_corrected 12.13, openings 0.99, drift_report 1.76, assemble 0.83, debug_images 0.51, render 0.25 | 1f2cbea573bf |
| own_hall_photo | own_hall | photo | stub |  | False | 2 | 0.0 | provenance 0.02, hand_written_geometry 0.00, hand_written_stitch 0.00, hand_written_damage 0.00, render 0.05 | e0b7739d06c3 |
| own_bedroom_1_photo | own_bedroom_1 | photo | stub |  | False | 2 | 0.0 | provenance 0.02, hand_written_geometry 0.00, hand_written_stitch 0.00, hand_written_damage 0.00, render 0.05 | e066eb4120f3 |
| own_bedroom_2_photo | own_bedroom_2 | photo | stub |  | False | 2 | 0.0 | provenance 0.02, hand_written_geometry 0.00, hand_written_stitch 0.00, hand_written_damage 0.00, render 0.05 | 7ad3577bc2a5 |
| own_bedroom_2_repeat_photo | own_bedroom_2 | photo | stub | own_bedroom_2_photo | False | 2 | 0.0 | provenance 0.02, hand_written_geometry 0.00, hand_written_stitch 0.00, hand_written_damage 0.00, render 0.05 | 0b835325bb86 |
| own_kitchen_photo | own_kitchen | photo | stub |  | False | 2 | 0.0 | provenance 0.02, hand_written_geometry 0.00, hand_written_stitch 0.00, hand_written_damage 0.00, render 0.05 | b57c0769033a |
| own_home_photo | own_home | photo | stub |  | True | 2 | 0.0 | provenance 0.02, hand_written_geometry 0.00, hand_written_stitch 0.00, hand_written_damage 0.00, render 0.05 | 66901facbc91 |
| own_hall_video | own_hall | video | stub |  | False | 2 | 0.0 | provenance 0.02, hand_written_geometry 0.00, hand_written_stitch 0.00, hand_written_damage 0.00, render 0.05 | 6094300b46d2 |
| own_bedroom_1_video | own_bedroom_1 | video | stub |  | False | 2 | 0.0 | provenance 0.02, hand_written_geometry 0.00, hand_written_stitch 0.00, hand_written_damage 0.00, render 0.06 | dd06b5345fea |
| own_bedroom_2_video | own_bedroom_2 | video | stub |  | False | 2 | 0.0 | provenance 0.02, hand_written_geometry 0.00, hand_written_stitch 0.00, hand_written_damage 0.00, render 0.05 | 085d6ae4d523 |
| own_bedroom_2_repeat_video | own_bedroom_2 | video | stub | own_bedroom_2_video | False | 2 | 0.0 | provenance 0.02, hand_written_geometry 0.00, hand_written_stitch 0.00, hand_written_damage 0.00, render 0.05 | 51c4082382f4 |
| own_kitchen_video | own_kitchen | video | stub |  | False | 2 | 0.0 | provenance 0.02, hand_written_geometry 0.00, hand_written_stitch 0.00, hand_written_damage 0.00, render 0.05 | 81f061a0e86c |
| own_home_video | own_home | video | stub |  | True | 2 | 0.0 | provenance 0.02, hand_written_geometry 0.00, hand_written_stitch 0.00, hand_written_damage 0.00, render 0.10 | 96d35721341f |

## Captures with no ground truth

**These captures have no tape or laser measurements, so nothing below is an accuracy result.** Reported: what the pipeline produced, how long it took, and whether the output is self-consistent.

| capture | tier | rooms | walls | openings | footprint m2 | sum of rooms m2 | room overlap m2 | rooms connected | ceiling from prior | duration_s |
|---|---|---|---|---|---|---|---|---|---|---|
| c00a170fe1 | lidar | 4 | 16 | 0 | 35.85 | 35.85 | 0.000 | no ['room_02', 'room_03', 'room_04'] | 4/4 | 4.4 |
| 1a8384c3f6 | lidar | 6 | 60 | 6 | 86.59 | 84.04 | 0.000 | no ['connector_01', 'room_02', 'room_04', 'room_05'] | 6/6 | 14.0 |
| c7d28f72c6 | lidar | 9 | 107 | 9 | 64.71 | 61.30 | 0.000 | no ['connector_01', 'connector_02', 'connector_03', 'connector_04', 'connector_05', 'room_02', 'room_03', 'room_04'] | 8/9 | 29.0 |

### Repeat pair: 1a8384c3f6 and c7d28f72c6 (lidar)

**NOT a valid repeat pair. The two captures cover different subsets of the building, so the strict gate number below measures coverage as much as repeatability. It is kept visible, and a secondary statistic over the walls both captures saw is reported beneath it.**

Devices: iPhone with LiDAR, supplied scan; no EXIF available and iPhone with LiDAR, supplied scan; no EXIF available.

Registration: rotation 328.5119525266558 degrees, translation (-6.04, 0.47) m, footprint IoU 0.61.

Same space check: 3 of 6 rooms pair by polygon IoU. Verdict: **same space** (registered footprint IoU at least 0.5 and at least half the rooms pairing by polygon IoU). The gate below is scored either way; a weak verdict is itself evidence about the segmentation, not a reason to skip scoring.

Agreement between two captures is repeatability, not accuracy. Both can be wrong together.

Room matching: 6 rooms in 1a8384c3f6, 9 in c7d28f72c6, 3 matched at IoU >= 0.3 (IoU values [0.465, 0.403, 0.536]). Unmatched: ['room_02', 'room_03', 'connector_01'] and ['room_03', 'connector_01', 'connector_02', 'connector_03', 'connector_04', 'connector_05'].

Wall matching inside matched rooms: 14 paired by nearest parallel face within 0.3 m, 77 with no counterpart.

Repeatability gate: FAIL on 153 wall rows, worst ratio inf against the allowed 1.0. Within tolerance: 0 of 153.

Worst matched wall: room_01~room_01 w17~w45 4.364 m vs 0.571 m, difference 379.3 cm against 1.2 cm allowed.

Of the 14 matched wall pairs, 0 are within tolerance.

Rows failing because a wall or room has no counterpart: 139.

Secondary statistic, walls observed in both captures. **This is not the gate**: the gate scores every wall, including those only one capture saw, so that reporting fewer things cannot raise a score.

| walls seen in both | median difference | within 5 cm | registered footprint IoU |
|---|---|---|---|
| 14 of 153 rows | 76.1 cm | 1 (7%) | 0.61 |

Walls seen by only one capture are excluded here and included in the gate. Agreement on shared walls does not show the plans agree.

At the wall-face level, below the polygon, the two captures place the same wall within a median of 1.9 cm. Face length with any counterpart: 1a8384c3f6 56%, c7d28f72c6 37%. The polygon edges disagree far more than the faces do, because the two captures cut the same wall into different edges. Source: fix_loop/evidence/evidence.json, regenerated by fix_loop/evidence_run.py.


## Gate summary (captures with ground truth)

| gate | result | value | threshold | n |
|---|---|---|---|---|
| opening_width | FAIL | 0.0000 | 0.8500 | 60 |
| ceiling_height | FAIL | 0.2718 | 0.0150 | 8 |
| ceiling_height_diagnosis | FAIL | 0.2718 | 0.0150 | 8 |
| repeatability | PASS | 0.0000 | 1.0000 | 8 |
| wall_length_tier | FAIL | 2.5000 | 1.0000 | 72 |
| footprint | PASS | 0.0400 | 0.0800 | 2 |
| stitch_adjacency | FAIL | 18.0000 | 0.0000 | 14 |
| stitch_overlap | PASS | 0.0000 | 0.0500 | 14 |

---

# Evaluation report

Captures: 14. Gates passed: 3/8. Overall: FAIL. Ceiling diagnosis: **repeatable_but_biased**.

**WARNING: at least one evaluated plan came from the STUB PIPELINE. These numbers say nothing about reconstruction quality.**

## Gates

| gate | result | value | threshold | n | note |
|---|---|---|---|---|---|
| opening_width | FAIL | 0.0000 | 0.8500 | 60 |  |
| ceiling_height | FAIL | 0.2718 | 0.0150 | 8 |  |
| ceiling_height_diagnosis | FAIL | 0.2718 | 0.0150 | 8 | label: repeatable_but_biased |
| repeatability | PASS | 0.0000 | 1.0000 | 8 |  |
| wall_length_tier | FAIL | 2.5000 | 1.0000 | 72 |  |
| footprint | PASS | 0.0400 | 0.0800 | 2 |  |
| stitch_adjacency | FAIL | 18.0000 | 0.0000 | 14 |  |
| stitch_overlap | PASS | 0.0000 | 0.0500 | 14 |  |

## Matching counts

| capture | tier | rooms matched/missing/phantom | walls matched/unmatched truth/unmatched pred | openings matched/missed/phantom |
|---|---|---|---|---|
| EXAMPLE | photo | 2/0/0 | 8/0/0 | 0/3/2 |
| EXAMPLE_REPEAT | photo | 2/0/0 | 8/0/0 | 0/3/2 |
| hall | photo | 1/0/1 | 0/0/4 | 0/3/2 |
| bedroom_1 | photo | 0/1/2 | 0/4/8 | 0/1/2 |
| bedroom_2 | photo | 0/1/2 | 0/4/8 | 0/1/2 |
| bedroom_2_repeat | photo | 0/1/2 | 0/4/8 | 0/1/2 |
| kitchen | photo | 0/1/2 | 0/4/8 | 0/1/2 |
| home | photo | 1/3/1 | 0/12/4 | 0/6/2 |
| hall | video | 1/0/1 | 0/0/4 | 0/3/2 |
| bedroom_1 | video | 0/1/2 | 0/4/8 | 0/1/2 |
| bedroom_2 | video | 0/1/2 | 0/4/8 | 0/1/2 |
| bedroom_2_repeat | video | 0/1/2 | 0/4/8 | 0/1/2 |
| kitchen | video | 0/1/2 | 0/4/8 | 0/1/2 |
| home | video | 1/3/1 | 0/12/4 | 0/6/2 |

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

### hall (photo, stub-0.1.0)

| room | ceiling pred | ceiling truth | abs err | floor area pred | floor area truth | abs err | wall order reversed |
|---|---|---|---|---|---|---|---|
| hall | 2.700 | 2.972 | 0.272 | 3.600 | n/a | n/a | no |

Missing rooms: none. Phantom rooms: ['living']. Missed openings: ['door_staircase', 'door_portico', 'door_bedroom_2']. Phantom openings: none.

Footprint: pred 22.080 m2, truth n/a m2 (sum of room floor areas). Room overlap (geometric): 0.000 m2.

Warnings: STUB PIPELINE: NOT A REAL RECONSTRUCTION

### bedroom_1 (photo, stub-0.1.0)

| room | ceiling pred | ceiling truth | abs err | floor area pred | floor area truth | abs err | wall order reversed |
|---|---|---|---|---|---|---|---|

Missing rooms: ['bedroom_1']. Phantom rooms: ['living', 'hall']. Missed openings: none. Phantom openings: none.

Footprint: pred 22.080 m2, truth n/a m2 (sum of room floor areas). Room overlap (geometric): 0.000 m2.

Warnings: STUB PIPELINE: NOT A REAL RECONSTRUCTION

### bedroom_2 (photo, stub-0.1.0)

| room | ceiling pred | ceiling truth | abs err | floor area pred | floor area truth | abs err | wall order reversed |
|---|---|---|---|---|---|---|---|

Missing rooms: ['bedroom_2']. Phantom rooms: ['living', 'hall']. Missed openings: none. Phantom openings: none.

Footprint: pred 22.080 m2, truth n/a m2 (sum of room floor areas). Room overlap (geometric): 0.000 m2.

Warnings: STUB PIPELINE: NOT A REAL RECONSTRUCTION

### bedroom_2_repeat (photo, stub-0.1.0)

| room | ceiling pred | ceiling truth | abs err | floor area pred | floor area truth | abs err | wall order reversed |
|---|---|---|---|---|---|---|---|

Missing rooms: ['bedroom_2']. Phantom rooms: ['living', 'hall']. Missed openings: none. Phantom openings: none.

Footprint: pred 22.080 m2, truth n/a m2 (sum of room floor areas). Room overlap (geometric): 0.000 m2.

Warnings: STUB PIPELINE: NOT A REAL RECONSTRUCTION

### kitchen (photo, stub-0.1.0)

| room | ceiling pred | ceiling truth | abs err | floor area pred | floor area truth | abs err | wall order reversed |
|---|---|---|---|---|---|---|---|

Missing rooms: ['kitchen']. Phantom rooms: ['living', 'hall']. Missed openings: none. Phantom openings: none.

Footprint: pred 22.080 m2, truth n/a m2 (sum of room floor areas). Room overlap (geometric): 0.000 m2.

Warnings: STUB PIPELINE: NOT A REAL RECONSTRUCTION

### home (photo, stub-0.1.0)

| room | ceiling pred | ceiling truth | abs err | floor area pred | floor area truth | abs err | wall order reversed |
|---|---|---|---|---|---|---|---|
| hall | 2.700 | 2.972 | 0.272 | 3.600 | n/a | n/a | no |

Missing rooms: ['bedroom_1', 'bedroom_2', 'kitchen']. Phantom rooms: ['living']. Missed openings: ['door_staircase', 'door_portico', 'door_bedroom_2']. Phantom openings: none.

Footprint: pred 22.080 m2, truth n/a m2 (sum of room floor areas). Room overlap (geometric): 0.000 m2.

Warnings: STUB PIPELINE: NOT A REAL RECONSTRUCTION

### hall (video, stub-0.1.0)

| room | ceiling pred | ceiling truth | abs err | floor area pred | floor area truth | abs err | wall order reversed |
|---|---|---|---|---|---|---|---|
| hall | 2.700 | 2.972 | 0.272 | 3.600 | n/a | n/a | no |

Missing rooms: none. Phantom rooms: ['living']. Missed openings: ['door_staircase', 'door_portico', 'door_bedroom_2']. Phantom openings: none.

Footprint: pred 22.080 m2, truth n/a m2 (sum of room floor areas). Room overlap (geometric): 0.000 m2.

Warnings: STUB PIPELINE: NOT A REAL RECONSTRUCTION

### bedroom_1 (video, stub-0.1.0)

| room | ceiling pred | ceiling truth | abs err | floor area pred | floor area truth | abs err | wall order reversed |
|---|---|---|---|---|---|---|---|

Missing rooms: ['bedroom_1']. Phantom rooms: ['living', 'hall']. Missed openings: none. Phantom openings: none.

Footprint: pred 22.080 m2, truth n/a m2 (sum of room floor areas). Room overlap (geometric): 0.000 m2.

Warnings: STUB PIPELINE: NOT A REAL RECONSTRUCTION

### bedroom_2 (video, stub-0.1.0)

| room | ceiling pred | ceiling truth | abs err | floor area pred | floor area truth | abs err | wall order reversed |
|---|---|---|---|---|---|---|---|

Missing rooms: ['bedroom_2']. Phantom rooms: ['living', 'hall']. Missed openings: none. Phantom openings: none.

Footprint: pred 22.080 m2, truth n/a m2 (sum of room floor areas). Room overlap (geometric): 0.000 m2.

Warnings: STUB PIPELINE: NOT A REAL RECONSTRUCTION

### bedroom_2_repeat (video, stub-0.1.0)

| room | ceiling pred | ceiling truth | abs err | floor area pred | floor area truth | abs err | wall order reversed |
|---|---|---|---|---|---|---|---|

Missing rooms: ['bedroom_2']. Phantom rooms: ['living', 'hall']. Missed openings: none. Phantom openings: none.

Footprint: pred 22.080 m2, truth n/a m2 (sum of room floor areas). Room overlap (geometric): 0.000 m2.

Warnings: STUB PIPELINE: NOT A REAL RECONSTRUCTION

### kitchen (video, stub-0.1.0)

| room | ceiling pred | ceiling truth | abs err | floor area pred | floor area truth | abs err | wall order reversed |
|---|---|---|---|---|---|---|---|

Missing rooms: ['kitchen']. Phantom rooms: ['living', 'hall']. Missed openings: none. Phantom openings: none.

Footprint: pred 22.080 m2, truth n/a m2 (sum of room floor areas). Room overlap (geometric): 0.000 m2.

Warnings: STUB PIPELINE: NOT A REAL RECONSTRUCTION

### home (video, stub-0.1.0)

| room | ceiling pred | ceiling truth | abs err | floor area pred | floor area truth | abs err | wall order reversed |
|---|---|---|---|---|---|---|---|
| hall | 2.700 | 2.972 | 0.272 | 3.600 | n/a | n/a | no |

Missing rooms: ['bedroom_1', 'bedroom_2', 'kitchen']. Phantom rooms: ['living']. Missed openings: ['door_staircase', 'door_portico', 'door_bedroom_2']. Phantom openings: none.

Footprint: pred 22.080 m2, truth n/a m2 (sum of room floor areas). Room overlap (geometric): 0.000 m2.

Warnings: STUB PIPELINE: NOT A REAL RECONSTRUCTION

## Calibration

Coverage target is the nominal ci_level (0.95). Confident garbage = truth outside the interval and interval narrower than the per-quantity median width.

Overall:

| group | n | coverage | mean width % of value | outside | confident garbage |
|---|---|---|---|---|---|
| all | 30 | 0.267 | 12.5 | 22 | 6 |

By tier:

| group | n | coverage | mean width % of value | outside | confident garbage |
|---|---|---|---|---|---|
| photo | 28 | 0.286 | 12.9 | 20 | 6 |
| video | 2 | 0.000 | 7.4 | 2 | 0 |

By quantity:

| group | n | coverage | mean width % of value | outside | confident garbage |
|---|---|---|---|---|---|
| ceiling_height | 8 | 0.000 | 7.4 | 8 | 0 |
| floor_area | 4 | 0.500 | 20.0 | 2 | 2 |
| footprint_area | 2 | 1.000 | 20.0 | 0 | 0 |
| wall_length | 16 | 0.250 | 12.2 | 12 | 4 |

By tier and quantity:

| group | n | coverage | mean width % of value | outside | confident garbage |
|---|---|---|---|---|---|
| photo/ceiling_height | 6 | 0.000 | 7.4 | 6 | 0 |
| photo/floor_area | 4 | 0.500 | 20.0 | 2 | 2 |
| photo/footprint_area | 2 | 1.000 | 20.0 | 0 | 0 |
| photo/wall_length | 16 | 0.250 | 12.2 | 12 | 4 |
| video/ceiling_height | 2 | 0.000 | 7.4 | 2 | 0 |

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
| own_hall | hall | 2 | 0.000 | -0.272 | repeatable_but_biased |
| own_home | hall | 2 | 0.000 | -0.272 | repeatable_but_biased |
