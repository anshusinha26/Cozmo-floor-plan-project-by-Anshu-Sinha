# What changed

Commit range: `4c564f3..e930feb` (declaration to the last fix commit).

| commit | what |
|---|---|
| `7e7d5b1` | falsifier: ghost-face rejection alone, erosion segmentation kept |
| `b062c02` | wall-driven cell complex segmentation, selectable with `--segmentation` |
| `e930feb` | collapse collinear edges in cell-complex room polygons |

## Code

**New `cozmo/lidar/ghosts.py`.** A wall face is kept when observed floor lies
within 25 cm of at least 25% of its length, on either side. The observed mask
is built from floor points and the camera path only, so the test does not
depend on the faces it is testing. Used by both segmentations.

**New `cozmo/lidar/cells.py`.** Wall-driven segmentation:

* `build_support` bins wall points in the 1.0 to 1.6 m band per axis, so
  support is measured from points rather than from face extents.
* `build_complex` turns structural face positions into grid lines, cuts the
  plan into cells, and marks a cell interior when at least 25% of it is
  observed. The dilation that builds the observed mask stops at wall cells;
  without that, floor bleeds through walls and the space outside the building
  is marked interior.
* `edge_verdict` cuts between two cells when at least 55% of the shared edge
  carries wall support and every unsupported run is at most 1.6 m. A longer
  run is a wide opening, so the cells are one space.
* `segment_rooms_cells` unions the cells of each component, collapses
  collinear edges, and computes perimeter support. A room under 80% supported
  is flagged `partially_observed`.

**Changed `cozmo/lidar/rooms.py`.** `Room` gained `partially_observed` and
`perimeter_support`; `RoomResult` gained `edges`, `support` and `complex` for
debugging. The erosion method itself is unchanged.

**Changed `cozmo/pipeline/lidar.py`.** Ghost rejection runs before
segmentation. `segmentation` in config picks the method. A partially observed
room has its wall length and floor area intervals doubled and gets a warning
naming its support share.

**Changed `cozmo/cli.py`.** `--segmentation cells|erosion` on `run` and
`bench`, recorded in the resolved config and therefore in the run manifest
hash.

**Changed `config/gates.yaml`.** New `ghost` and `cells` blocks, and
`segmentation: cells`. `min_line_gap_m` was set to 0.16 by sweeping both
apartment captures.

**Tests.** `tests/test_ghosts.py` and `tests/test_cells.py`, 12 tests: a door
does not merge two rooms, a 2.4 m opening does, a room with a missing wall is
flagged, polygons stay rectilinear and counter-clockwise, and the whole thing
is deterministic.

## Gates, before and after

Both sides run the same eval on the same five captures. BEFORE uses
`--segmentation erosion`, AFTER uses `cells`.

| gate | before | after |
|---|---|---|
| opening_width | FAIL (0, n=10) | FAIL (0, n=10) |
| ceiling_height | FAIL (0.2, n=4) | FAIL (0.2, n=4) |
| ceiling_height_diagnosis | FAIL (0.2, n=4) | FAIL (0.2, n=4) |
| repeatability | PASS (0, n=8) | PASS (0, n=8) |
| wall_length_tier | FAIL (2.5, n=16) | FAIL (2.5, n=16) |
| footprint | PASS (0.04, n=2) | PASS (0.04, n=2) |
| stitch_adjacency | PASS (0, n=2) | PASS (0, n=2) |
| stitch_overlap | PASS (0, n=2) | PASS (0, n=2) |
| repeatability (apartment pair) | FAIL (0 of 112 rows within tolerance) | FAIL (0 of 153 rows within tolerance) |

## Rooms per scan

| scan | rooms before | rooms after | walls before | walls after | partially observed after |
|---|---|---|---|---|---|
| c00a170fe1 | 2 | 4 | 8 | 16 | 3 |
| 1a8384c3f6 | 8 | 6 | 56 | 60 | 5 |
| c7d28f72c6 | 10 | 9 | 76 | 107 | 9 |

Pair-level matching:

| quantity | before | after |
|---|---|---|
| rooms matched across the pair | 6 | 3 |
| walls matched across the pair | 20 | 14 |
| walls with no counterpart | 50 | 77 |
| registered footprint IoU | 0.68 | 0.61 |

## Drift ablation, both segmentations

| scan | side | footprint off/on m2 | wall thickness off/on mm | rooms off/on | overlap off/on m2 |
|---|---|---|---|---|---|
| c00a170fe1 | before | 24.6 / 19.5 | 24.2 / 23.6 | 2 / 2 | 0.000 / 0.042 |
| c00a170fe1 | after | 55.4 / 35.8 | 24.2 / 23.6 | 2 / 4 | 0.000 / 0.000 |
| 1a8384c3f6 | before | 47.9 / 50.3 | 31.6 / 35.3 | 9 / 8 | 0.130 / 0.013 |
| 1a8384c3f6 | after | 80.0 / 86.6 | 32.1 / 35.8 | 7 / 6 | 0.000 / 0.000 |
| c7d28f72c6 | before | 49.8 / 46.9 | 32.5 / 32.7 | 11 / 10 | 0.392 / 0.272 |
| c7d28f72c6 | after | 65.8 / 64.7 | 32.5 / 32.6 | 8 / 9 | 0.000 / 0.000 |

Room overlap falls to zero under the cell complex, because cells cannot
overlap by construction. Wall thickness is unchanged, as expected: it
measures the point cloud, which segmentation does not touch.
