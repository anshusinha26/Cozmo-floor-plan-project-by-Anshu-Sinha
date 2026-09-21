# Evaluation report

Captures: 6. Gates passed: 2 of 7 evaluated (8 defined). Overall: FAIL. Ceiling diagnosis: **repeatable_but_biased**.

## Gates, per tier

### photo

Captures: own.

| gate | result | value | threshold | n | note |
|---|---|---|---|---|---|
| opening_width | FAIL | 0.0000 | 0.8500 | 7 |  |
| ceiling_height | FAIL | 0.1065 | 0.0150 | 4 |  |
| ceiling_height_diagnosis | FAIL | 0.1065 | 0.0150 | 4 | label: repeatable_but_biased; spaces seen once have spread 0 by construction and cannot be labelled unrepeatable |
| repeatability | NOT EVALUATED | 0.0000 | 1.0000 | 0 | no repeat captures of the same space at this tier |
| wall_length_tier | FAIL | 3.9911 | 1.0000 | 12 |  |
| footprint | NOT EVALUATED | 0.0000 | 0.0800 | 0 | no capture has a tape-measured footprint: the hall was not measured wall by wall, so the only multi-room property has no truth footprint to compare against |
| stitch_adjacency | PASS | 0.0000 | 0.0000 | 1 |  |
| stitch_overlap | PASS | 0.0000 | 0.0500 | 1 |  |

2 of 6 evaluated gates pass, 2 not evaluated.

### video

Captures: hall, bedroom_1, bedroom_2, bedroom_2_repeat, kitchen.

| gate | result | value | threshold | n | note |
|---|---|---|---|---|---|
| opening_width | FAIL | 0.0000 | 0.8500 | 7 |  |
| ceiling_height | FAIL | 0.6329 | 0.0150 | 5 |  |
| ceiling_height_diagnosis | FAIL | 0.6329 | 0.0150 | 5 | label: repeatable_but_biased; spaces seen once have spread 0 by construction and cannot be labelled unrepeatable |
| repeatability | FAIL | 250.4362 | 1.0000 | 4 |  |
| wall_length_tier | FAIL | 45.8165 | 1.0000 | 16 |  |
| footprint | NOT EVALUATED | 0.0000 | 0.0800 | 0 | no capture has a tape-measured footprint: the hall was not measured wall by wall, so the only multi-room property has no truth footprint to compare against |
| stitch_adjacency | PASS | 0.0000 | 0.0000 | 5 |  |
| stitch_overlap | PASS | 0.0000 | 0.0500 | 5 |  |

2 of 7 evaluated gates pass, 1 not evaluated.

## Gates, every capture together

| gate | result | value | threshold | n | note |
|---|---|---|---|---|---|
| opening_width | FAIL | 0.0000 | 0.8500 | 14 |  |
| ceiling_height | FAIL | 0.6329 | 0.0150 | 9 |  |
| ceiling_height_diagnosis | FAIL | 0.6329 | 0.0150 | 9 | label: repeatable_but_biased; spaces seen once have spread 0 by construction and cannot be labelled unrepeatable |
| repeatability | FAIL | 250.4362 | 1.0000 | 4 |  |
| wall_length_tier | FAIL | 45.8165 | 1.0000 | 28 |  |
| footprint | NOT EVALUATED | 0.0000 | 0.0800 | 0 | no capture has a tape-measured footprint: the hall was not measured wall by wall, so the only multi-room property has no truth footprint to compare against |
| stitch_adjacency | PASS | 0.0000 | 0.0000 | 6 |  |
| stitch_overlap | PASS | 0.0000 | 0.0500 | 6 |  |

## Matching counts

| capture | tier | rooms matched/missing/phantom | walls matched/unmatched truth/unmatched pred | openings matched/missed/phantom |
|---|---|---|---|---|
| own | photo | 4/0/0 | 12/0/0 | 0/6/1 |
| hall | video | 1/0/0 | 0/0/0 | 0/3/0 |
| bedroom_1 | video | 1/0/0 | 4/0/2 | 0/1/0 |
| bedroom_2 | video | 1/0/0 | 4/0/0 | 0/1/0 |
| bedroom_2_repeat | video | 1/0/0 | 4/0/0 | 0/1/0 |
| kitchen | video | 1/0/0 | 4/0/0 | 0/1/0 |

## Per-room errors

### own (photo, photo-0.1.0)

| room | ceiling pred | ceiling truth | abs err | floor area pred | floor area truth | abs err | wall order reversed |
|---|---|---|---|---|---|---|---|
| hall | 2.865 | 2.972 | 0.107 | 36.042 | n/a | n/a | no |
| bedroom_1 | 3.050 | 2.972 | 0.078 | 12.176 | n/a | n/a | yes |
| bedroom_2 | 3.058 | 2.972 | 0.086 | 14.685 | n/a | n/a | yes |
| kitchen | 2.992 | 2.972 | 0.021 | 12.633 | n/a | n/a | yes |

Walls:

| room | truth wall | pred wall | truth m | pred m | ci low | ci high | abs err |
|---|---|---|---|---|---|---|---|
| bedroom_1 | A | w4 | 3.658 | 3.637 | 2.840 | 4.433 | 0.021 |
| bedroom_1 | B | w3 | 3.912 | 3.348 | 2.615 | 4.081 | 0.563 |
| bedroom_1 | C | w2 | 3.658 | 3.637 | 2.840 | 4.433 | 0.021 |
| bedroom_1 | D | w1 | 3.912 | 3.348 | 2.615 | 4.081 | 0.563 |
| bedroom_2 | B | w4 | 3.632 | 3.744 | 2.925 | 4.564 | 0.112 |
| bedroom_2 | C | w3 | 3.886 | 3.922 | 3.063 | 4.781 | 0.036 |
| bedroom_2 | D | w2 | 3.632 | 3.744 | 2.925 | 4.564 | 0.112 |
| bedroom_2 | A | w1 | 3.886 | 3.922 | 3.063 | 4.781 | 0.036 |
| kitchen | B | w4 | 3.603 | 4.753 | 3.828 | 5.679 | 1.150 |
| kitchen | C | w3 | 2.692 | 2.658 | 2.140 | 3.175 | 0.035 |
| kitchen | D | w2 | 3.603 | 4.753 | 3.828 | 5.679 | 1.150 |
| kitchen | A | w1 | 2.692 | 2.658 | 2.140 | 3.175 | 0.035 |

Missing rooms: none. Phantom rooms: none. Missed openings: ['door_staircase', 'door_portico', 'door_bedroom_2', 'door_hall', 'door_hall', 'door_hall']. Phantom openings: ['kitchen_d1'].

Footprint: pred 75.536 m2, truth n/a m2 (sum of room floor areas). Room overlap (geometric): 0.000 m2.

Warnings: Skipped all (0 image(s), needs at least 2); Skipped home (0 image(s), needs at least 2); app_comparision was excluded by --exclude and is not treated as a room; bedroom_2_repeat is a repeat capture: it is measured and reported, but it is not placed in the property, because it is the same room as another; kitchen is attached wall to wall: no free door pair was available between it and hall; bedroom_1: 1 of 4 room sides (x+) are set by a dense band of points rather than by a wall face that passed the strict test, which is what a wall behind a curtain or a wardrobe looks like. Their intervals are widened; bedroom_1: Windows are not detected in this version; openings are doors and pass-throughs only; bedroom_2: 1 of 4 room sides (z-) are set by a dense band of points rather than by a wall face that passed the strict test, which is what a wall behind a curtain or a wardrobe looks like. Their intervals are widened; bedroom_2: Windows are not detected in this version; openings are doors and pass-throughs only; hall: 1 of 4 room sides (z+) are set by a dense band of points rather than by a wall face that passed the strict test, which is what a wall behind a curtain or a wardrobe looks like. Their intervals are widened; hall: Windows are not detected in this version; openings are doors and pass-throughs only; kitchen: Windows are not detected in this version; openings are doors and pass-throughs only; footprint area is reported with an interval wider than the value itself (75.54 m2, plus or minus 94.69). It is an unreliable measurement: the reconstruction constrains it barely or not at all; Damage regions were detected without metric depth, so their extent is unbounded: extent_m2 carries a nominal value with an interval spanning the plausible range and method unbounded_no_metric_depth. Do not read these as measured areas; Damage regions in this plan are attached to a wall of the room each photo came from by fallback, not by measurement: without depth the mark cannot be placed on a specific wall, so it is recorded against that room's first wall surface; Without metric depth the same mark seen in several photos cannot be merged, so damage_regions counts detections per photo and over-counts the marks present. Read the count as an upper bound, not as a number of defects

### hall (video, video-0.1.0)

| room | ceiling pred | ceiling truth | abs err | floor area pred | floor area truth | abs err | wall order reversed |
|---|---|---|---|---|---|---|---|
| hall | 2.700 | 2.972 | 0.272 | 5.150 | n/a | n/a | no |

Missing rooms: none. Phantom rooms: none. Missed openings: ['door_staircase', 'door_portico', 'door_bedroom_2']. Phantom openings: none.

Footprint: pred 5.150 m2, truth n/a m2 (sum of room floor areas). Room overlap (geometric): 0.000 m2.

Warnings: 6 of 9 chunks had no usable floor plane and kept the monocular depth scale instead of the height prior; Chunk 0 (45 frames, 8% of the video) could not be bridged to the main group and was dropped; Chunk 1 (23 frames, 4% of the video) could not be bridged to the main group and was dropped; Chunk 2 (46 frames, 8% of the video) could not be bridged to the main group and was dropped; Chunk 3 (16 frames, 3% of the video) could not be bridged to the main group and was dropped; Chunk 4 (19 frames, 3% of the video) could not be bridged to the main group and was dropped; Chunk 7 (52 frames, 9% of the video) could not be bridged to the main group and was dropped; Chunk 8 (32 frames, 5% of the video) could not be bridged to the main group and was dropped; The camera-height prior and the monocular depth scale disagree by 6% on this capture; the wider of that and the prior's own uncertainty sets the scale term in every interval; Only 11% of the video reached the output, under the 60% this tier expects; every interval is widened by 1.6x and the plan should be read as a fragment; Mirror and glass rejection is not available in this build, so a wardrobe mirror can still read as a wall; The reconstruction puts the camera 2.02 m above its own floor, outside the 1.1 to 1.8 m a hand-held phone can be. Every length in this plan is likely off by about 1.4x, because the metric scale comes from a monocular depth model and nothing here measured a distance directly; 4 of 4 room sides had no supported wall face (x-, x+, z-, z+); they are closed at the camera path plus 0.35 m by the rectangle assumption and the room is only partially observed; Windows are not detected in this version; openings are doors and pass-throughs only; Ceiling not observed over enough of the floor (coverage 0% < 12%); ceiling height is a prior interval, not a measurement; 4 of 4 room sides had no supported wall face (x-, x+, z-, z+); they are closed at the camera path plus 0.35 m by the rectangle assumption and the room is only partially observed; room_01: Ceiling not observed over enough of the floor (coverage 0% < 12%); ceiling height is a prior interval, not a measurement; Drift correction rejected some chunk estimates: ['yaw beyond the limit']; Damage detection is not implemented; damage_regions, concealed_damage_flags and scope_items are empty

### bedroom_1 (video, video-0.1.0)

| room | ceiling pred | ceiling truth | abs err | floor area pred | floor area truth | abs err | wall order reversed |
|---|---|---|---|---|---|---|---|
| bedroom_1 | 2.700 | 2.972 | 0.272 | 95.244 | n/a | n/a | yes |

Walls:

| room | truth wall | pred wall | truth m | pred m | ci low | ci high | abs err |
|---|---|---|---|---|---|---|---|
| bedroom_1 | A | w5 | 3.658 | 8.685 | -18.681 | 36.051 | 5.027 |
| bedroom_1 | B | w4 | 3.912 | 4.220 | -9.077 | 17.517 | 0.308 |
| bedroom_1 | C | w3 | 3.658 | 3.186 | -6.853 | 13.225 | 0.472 |
| bedroom_1 | D | w2 | 3.912 | 4.936 | -10.617 | 20.489 | 1.024 |

Missing rooms: none. Phantom rooms: none. Missed openings: ['door_hall']. Phantom openings: none.

Footprint: pred 95.244 m2, truth n/a m2 (sum of room floor areas). Room overlap (geometric): 0.000 m2.

Warnings: Chunk 0 (17 frames, 4% of the video) could not be bridged to the main group and was dropped; Chunk 1 (17 frames, 4% of the video) could not be bridged to the main group and was dropped; Chunk 2 (16 frames, 4% of the video) could not be bridged to the main group and was dropped; Chunk 6 (15 frames, 3% of the video) could not be bridged to the main group and was dropped; Chunk 7 (74 frames, 17% of the video) could not be bridged to the main group and was dropped; Monocular depth disagreed with itself across frames on this capture: the weighted standard error of the per-chunk scale is 21.2%, which is carried into every interval; The camera-height prior and the monocular depth scale disagree by 66% on this capture; the wider of that and the prior's own uncertainty sets the scale term in every interval; Only 47% of the video reached the output, under the 60% this tier expects; every interval is widened by 1.6x and the plan should be read as a fragment; Mirror and glass rejection is not available in this build, so a wardrobe mirror can still read as a wall; The reconstruction puts the camera 2.26 m above its own floor, outside the 1.1 to 1.8 m a hand-held phone can be. Every length in this plan is likely off by about 1.6x, because the metric scale comes from a monocular depth model and nothing here measured a distance directly; 2 of 4 room sides had no supported wall face (x-, z+); they are closed at the camera path plus 0.35 m by the rectangle assumption and the room is only partially observed; Windows are not detected in this version; openings are doors and pass-throughs only; Ceiling not observed over enough of the floor (coverage 2% < 12%); ceiling height is a prior interval, not a measurement; 2 of 4 room sides had no supported wall face (x-, z+); they are closed at the camera path plus 0.35 m by the rectangle assumption and the room is only partially observed; room_01: Ceiling not observed over enough of the floor (coverage 2% < 12%); ceiling height is a prior interval, not a measurement; Drift correction rejected some chunk estimates: ['yaw beyond the limit']; Damage detection is not implemented; damage_regions, concealed_damage_flags and scope_items are empty

### bedroom_2 (video, video-0.1.0)

| room | ceiling pred | ceiling truth | abs err | floor area pred | floor area truth | abs err | wall order reversed |
|---|---|---|---|---|---|---|---|
| bedroom_2 | 2.700 | 2.972 | 0.272 | 2.259 | n/a | n/a | yes |

Walls:

| room | truth wall | pred wall | truth m | pred m | ci low | ci high | abs err |
|---|---|---|---|---|---|---|---|
| bedroom_2 | A | w4 | 3.886 | 1.243 | -2.778 | 5.264 | 2.643 |
| bedroom_2 | B | w3 | 3.632 | 1.817 | -4.062 | 7.697 | 1.815 |
| bedroom_2 | C | w2 | 3.886 | 1.243 | -2.778 | 5.264 | 2.643 |
| bedroom_2 | D | w1 | 3.632 | 1.817 | -4.062 | 7.697 | 1.815 |

Missing rooms: none. Phantom rooms: none. Missed openings: ['door_hall']. Phantom openings: none.

Footprint: pred 2.259 m2, truth n/a m2 (sum of room floor areas). Room overlap (geometric): 0.000 m2.

Warnings: 1 of 5 chunks had no usable floor plane and kept the monocular depth scale instead of the height prior; Chunk 1 (15 frames, 3% of the video) could not be bridged to the main group and was dropped; Chunk 2 (99 frames, 19% of the video) could not be bridged to the main group and was dropped; Chunk 3 (48 frames, 9% of the video) could not be bridged to the main group and was dropped; Chunk 4 (17 frames, 3% of the video) could not be bridged to the main group and was dropped; The camera-height prior and the monocular depth scale disagree by 69% on this capture; the wider of that and the prior's own uncertainty sets the scale term in every interval; Only 40% of the video reached the output, under the 60% this tier expects; every interval is widened by 1.6x and the plan should be read as a fragment; Mirror and glass rejection is not available in this build, so a wardrobe mirror can still read as a wall; 2 of 4 room sides had no supported wall face (x-, z-); they are closed at the camera path plus 0.35 m by the rectangle assumption and the room is only partially observed; Windows are not detected in this version; openings are doors and pass-throughs only; Ceiling not observed over enough of the floor (coverage 0% < 12%); ceiling height is a prior interval, not a measurement; 2 of 4 room sides had no supported wall face (x-, z-); they are closed at the camera path plus 0.35 m by the rectangle assumption and the room is only partially observed; room_01: Ceiling not observed over enough of the floor (coverage 0% < 12%); ceiling height is a prior interval, not a measurement; Damage detection is not implemented; damage_regions, concealed_damage_flags and scope_items are empty

### bedroom_2_repeat (video, video-0.1.0)

| room | ceiling pred | ceiling truth | abs err | floor area pred | floor area truth | abs err | wall order reversed |
|---|---|---|---|---|---|---|---|
| bedroom_2 | 2.700 | 2.972 | 0.272 | 16.428 | n/a | n/a | yes |

Walls:

| room | truth wall | pred wall | truth m | pred m | ci low | ci high | abs err |
|---|---|---|---|---|---|---|---|
| bedroom_2 | A | w4 | 3.886 | 5.406 | -12.486 | 23.298 | 1.519 |
| bedroom_2 | B | w3 | 3.632 | 3.039 | -7.020 | 13.097 | 0.593 |
| bedroom_2 | C | w2 | 3.886 | 5.406 | -12.486 | 23.298 | 1.519 |
| bedroom_2 | D | w1 | 3.632 | 3.039 | -7.020 | 13.097 | 0.593 |

Missing rooms: none. Phantom rooms: none. Missed openings: ['door_hall']. Phantom openings: none.

Footprint: pred 16.428 m2, truth n/a m2 (sum of room floor areas). Room overlap (geometric): 0.000 m2.

Warnings: Chunk 0 (76 frames, 16% of the video) could not be bridged to the main group and was dropped; Chunk 1 (58 frames, 12% of the video) could not be bridged to the main group and was dropped; Chunk 2 (108 frames, 23% of the video) could not be bridged to the main group and was dropped; Monocular depth disagreed with itself across frames on this capture: the weighted standard error of the per-chunk scale is 10.5%, which is carried into every interval; The camera-height prior and the monocular depth scale disagree by 70% on this capture; the wider of that and the prior's own uncertainty sets the scale term in every interval; Only 31% of the video reached the output, under the 60% this tier expects; every interval is widened by 1.6x and the plan should be read as a fragment; Walls were only reconstructed to about 1.55 m above the floor, so a face counts as a wall at 1.16 m rather than the usual 1.50 m. Wall heights and the ceiling are not measured from this capture; Mirror and glass rejection is not available in this build, so a wardrobe mirror can still read as a wall; 2 of 4 room sides had no supported wall face (x+, z+); they are closed at the camera path plus 0.35 m by the rectangle assumption and the room is only partially observed; Windows are not detected in this version; openings are doors and pass-throughs only; Ceiling not observed over enough of the floor (coverage 0% < 12%); ceiling height is a prior interval, not a measurement; 2 of 4 room sides had no supported wall face (x+, z+); they are closed at the camera path plus 0.35 m by the rectangle assumption and the room is only partially observed; room_01: Ceiling not observed over enough of the floor (coverage 0% < 12%); ceiling height is a prior interval, not a measurement; Drift correction rejected some chunk estimates: ['yaw beyond the limit']; Damage detection is not implemented; damage_regions, concealed_damage_flags and scope_items are empty

### kitchen (video, video-0.1.0)

| room | ceiling pred | ceiling truth | abs err | floor area pred | floor area truth | abs err | wall order reversed |
|---|---|---|---|---|---|---|---|
| kitchen | 2.339 | 2.972 | 0.633 | 5.710 | n/a | n/a | yes |

Walls:

| room | truth wall | pred wall | truth m | pred m | ci low | ci high | abs err |
|---|---|---|---|---|---|---|---|
| kitchen | A | w4 | 2.692 | 1.806 | 0.567 | 3.044 | 0.887 |
| kitchen | B | w3 | 3.603 | 3.162 | 0.994 | 5.331 | 0.441 |
| kitchen | C | w2 | 2.692 | 1.806 | 0.567 | 3.044 | 0.887 |
| kitchen | D | w1 | 3.603 | 3.162 | 0.994 | 5.331 | 0.441 |

Missing rooms: none. Phantom rooms: none. Missed openings: ['door_hall']. Phantom openings: none.

Footprint: pred 5.710 m2, truth n/a m2 (sum of room floor areas). Room overlap (geometric): 0.000 m2.

Warnings: 1 of 4 chunks had no usable floor plane and kept the monocular depth scale instead of the height prior; Chunk 1 (36 frames, 9% of the video) could not be bridged to the main group and was dropped; Chunk 2 (20 frames, 5% of the video) could not be bridged to the main group and was dropped; Chunk 3 (75 frames, 20% of the video) could not be bridged to the main group and was dropped; The camera-height prior and the monocular depth scale disagree by 14% on this capture; the wider of that and the prior's own uncertainty sets the scale term in every interval; Only 33% of the video reached the output, under the 60% this tier expects; every interval is widened by 1.6x and the plan should be read as a fragment; Mirror and glass rejection is not available in this build, so a wardrobe mirror can still read as a wall; 2 of 4 room sides had no supported wall face (x+, z+); they are closed at the camera path plus 0.35 m by the rectangle assumption and the room is only partially observed; Windows are not detected in this version; openings are doors and pass-throughs only; 2 of 4 room sides had no supported wall face (x+, z+); they are closed at the camera path plus 0.35 m by the rectangle assumption and the room is only partially observed; Damage detection is not implemented; damage_regions, concealed_damage_flags and scope_items are empty

## Calibration

Coverage target is the nominal ci_level (0.95). Confident garbage = truth outside the interval and interval narrower than the per-quantity median width.

Overall:

| group | n | coverage | mean width % of value | outside | confident garbage |
|---|---|---|---|---|---|
| all | 37 | 0.946 | 250.5 | 2 | 2 |

By tier:

| group | n | coverage | mean width % of value | outside | confident garbage |
|---|---|---|---|---|---|
| photo | 16 | 0.875 | 42.4 | 2 | 2 |
| video | 21 | 1.000 | 409.1 | 0 | 0 |

By quantity:

| group | n | coverage | mean width % of value | outside | confident garbage |
|---|---|---|---|---|---|
| ceiling_height | 9 | 1.000 | 50.8 | 0 | 0 |
| wall_length | 28 | 0.929 | 314.7 | 2 | 2 |

By tier and quantity:

| group | n | coverage | mean width % of value | outside | confident garbage |
|---|---|---|---|---|---|
| photo/ceiling_height | 4 | 1.000 | 43.0 | 0 | 0 |
| photo/wall_length | 12 | 0.833 | 42.2 | 2 | 2 |
| video/ceiling_height | 5 | 1.000 | 57.1 | 0 | 0 |
| video/wall_length | 16 | 1.000 | 519.1 | 0 | 0 |

## Repeatability

| space | tier | capture a | capture b | room | wall | a | b | diff | allowed | ok |
|---|---|---|---|---|---|---|---|---|---|---|
| own_bedroom_2 | video | bedroom_2 | bedroom_2_repeat | bedroom_2 | A | 1.243 | 5.406 | 4.163 | 0.017 | no |
| own_bedroom_2 | video | bedroom_2 | bedroom_2_repeat | bedroom_2 | B | 1.817 | 3.039 | 1.222 | 0.012 | no |
| own_bedroom_2 | video | bedroom_2 | bedroom_2_repeat | bedroom_2 | C | 1.243 | 5.406 | 4.163 | 0.017 | no |
| own_bedroom_2 | video | bedroom_2 | bedroom_2_repeat | bedroom_2 | D | 1.817 | 3.039 | 1.222 | 0.012 | no |

Worst case: bedroom_2 vs bedroom_2_repeat bedroom_2/A diff 4.163 m against allowed 0.017 m.

## Ceiling height diagnosis

| space | room | captures | spread m | mean error m | label |
|---|---|---|---|---|---|
| own_bedroom_1 | bedroom_1 | 1 | 0.000 | -0.272 | repeatable_but_biased |
| own_bedroom_2 | bedroom_2 | 2 | 0.000 | -0.272 | repeatable_but_biased |
| own_hall | hall | 1 | 0.000 | -0.272 | repeatable_but_biased |
| own_home | bedroom_1 | 1 | 0.000 | 0.078 | repeatable_but_biased |
| own_home | bedroom_2 | 1 | 0.000 | 0.086 | repeatable_but_biased |
| own_home | hall | 1 | 0.000 | -0.107 | repeatable_but_biased |
| own_home | kitchen | 1 | 0.000 | 0.021 | repeatable_but_biased |
| own_kitchen | kitchen | 1 | 0.000 | -0.633 | repeatable_but_biased |

spaces seen once have spread 0 by construction and cannot be labelled unrepeatable
