# Plan output contract (schema 1.0.0)

The output of every `cozmo run` is one `plan.json` conforming to
`schema/plan.schema.json`. The schema is generated from the pydantic models in
`cozmo/contracts/models.py` by `cozmo schema`, so code and schema cannot drift.
Bump `SCHEMA_VERSION` when the shape changes; a plan whose `schema_version`
does not match the running code is rejected on load.

## The one rule: no bare dimensions

Any key ending in `_m`, `_m2` or `_deg` holds a `Measurement`, never a number:

```json
{"value": 4.212, "ci_low": 4.10, "ci_high": 4.32, "unit": "m",
 "method": "scale_from_door_prior", "ci_level": 0.95}
```

* `ci_low <= value <= ci_high` is enforced. NaN and inf are rejected.
* `ci_level` is the nominal coverage. The evaluator compares it with the
  empirical coverage against ground truth, so an honest wide interval scores
  better than a confident wrong one.
* `method` is free text naming how the value was obtained.

A test walks every emitted plan and fails on any bare-number dimension.

## Top level

| key | content |
|-----|---------|
| `schema_version` | `"1.0.0"` |
| `capture` | `id`, `tier` (photo, video, lidar), `device`, `captured_at`, `input_manifest_sha256` |
| `run` | `pipeline_version`, `git_commit`, `config_sha256`, `seed` |
| `rooms` | list of rooms, each with polygon, walls, openings, ceiling height, floor area |
| `adjacency` | undirected edges `room_a`, `room_b`, optional `via_opening_id` |
| `stitched_plan` | per-room rigid `placements`, `footprint_polygon`, `footprint_area_m2`, `overlap_area_m2` |
| `surfaces` | wall, floor and ceiling surfaces with `area_m2` |
| `damage_regions` | polygons on a surface with a `damage_class` and `extent_m2` |
| `concealed_damage_flags` | rule-based inferences with evidence and confidence |
| `scope_items` | remediation quantities tied to surfaces and damage regions |
| `assumptions`, `warnings` | free text; the stub pipeline always emits a warning |
| `renders` | relative paths to `plan_png` and `plan_svg`, or null |

### Why `run` holds no timestamps

`plan.json` must be byte-identical for the same input, config and seed. Wall
clock fields (`started_at`, `duration_s`, `stage_timings_s`) therefore live in
`run_manifest.json`, which sits next to the plan and also records every input
file's SHA-256, the resolved config and its hash, git commit and dirty flag,
library versions and the plan's own SHA-256.

## Geometry conventions

* Room `polygon` is in metres, in a room-local frame, counter-clockwise, not
  closed (first point is not repeated). Clockwise polygons are rejected.
* `walls[].start` and `end` are in the same room-local frame.
* `openings[].offset_along_wall_m` is measured from the wall's `start`.
* `stitched_plan.placements` map each room-local frame into the plan frame:
  rotate by `theta_deg` about the room origin, then translate by `(tx, ty)`.
  `theta_deg` is a `Measurement` because rotation error propagates into the
  footprint; `tx`, `ty` are coordinates like polygon vertices.
* `footprint_polygon` is CCW in the plan frame.

## Referential integrity enforced on load

* Room, wall, opening, surface, damage region, flag and scope item ids are
  unique within their scope.
* Every opening's `wall_id` names a wall in the same room.
* Every adjacency edge names two distinct known rooms, and its
  `via_opening_id` (if any) names a known opening.
* Every room has exactly one placement.
* Wall surfaces carry a `wall_id` that exists in their room; floor and ceiling
  surfaces carry none.
* Damage regions, concealed flags and scope items reference existing surfaces;
  scope items reference existing damage regions.

This is enforced at load time so the evaluator counts matched, missed and
phantom entities on a consistent graph and never has to repair input first.

## Damage classes

Defined once as `DamageClass` in `cozmo/contracts/models.py`:
`water_stain`, `mould`, `crack`, `hole_puncture`, `burn_char`,
`missing_material`, `peeling_paint`.
