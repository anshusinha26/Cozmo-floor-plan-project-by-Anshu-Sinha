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
