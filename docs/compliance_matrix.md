# Compliance matrix

Status is one of: done, partial, not started, waived.
"Done" here means the harness side exists and is tested. No reconstruction
exists yet, so every accuracy row is scored on the stub only.

| requirement | file path | artifact | status |
|---|---|---|---|
| Photo tier (2 or more stills per room, no depth, no poses) | cozmo/io/inputs.py, cozmo/pipeline/stub.py | input validation, stub plan | partial: input convention validated, still the stub, which says so in warnings |
| Video tier (one scan folder, rgb.mp4 only) | cozmo/io/inputs.py, cozmo/pipeline/stub.py | input validation, tier isolation, stub plan | partial: the tier may open only rgb.mp4, enforced in code; still the stub, which says so in warnings |
| LiDAR tier (Stray Scanner scan folder) | cozmo/io/stray.py, cozmo/lidar/, cozmo/pipeline/lidar.py | reconstruction to plan.json, plan.png, drift_report.json, debug images | done: no longer waived. Sample iPhone LiDAR scans supplied; classical reconstruction runs on all three. Accuracy unverified: no tape ground truth yet |
| Per-room plan (polygon, walls, openings) | cozmo/contracts/models.py | plan.json rooms[] | done (contract); stub values only |
| Ceiling height per room with interval | cozmo/contracts/models.py, cozmo/eval/gates.py | rooms[].ceiling_height_m, ceiling_height gate | done (contract and gate); stub values only |
| Floor area per room with interval | cozmo/contracts/models.py, cozmo/eval/calibration.py | rooms[].floor_area_m2, calibration row floor_area | done (contract and calibration); stub values only |
| Openings (door, window, pass-through) with width, height, offset | cozmo/contracts/models.py, cozmo/eval/matching.py | rooms[].openings[], opening matching | done (contract and matching); stub values only |
| Stitched plan with adjacency graph | cozmo/contracts/models.py, cozmo/eval/gates.py | stitched_plan, adjacency[], stitch_adjacency and stitch_overlap gates | done (contract and gates); stub values only |
| Damage regions with class enum and extent | cozmo/contracts/models.py | damage_regions[], DamageClass | partial: contract done, no detector; lidar plans emit an empty list and a warning saying so |
| Concealed-damage flags with rule id and evidence | cozmo/contracts/models.py | concealed_damage_flags[] | done (contract); no rules engine |
| Scope items with quantity and basis | cozmo/contracts/models.py | scope_items[] | done (contract); no generator |
| Interval on every measurement (no bare floats) | cozmo/contracts/models.py, tests/test_contract.py, tests/test_cli.py | Measurement type, bare-dimension walker test on emitted output | done |
| One command per capture | cozmo/cli.py | cozmo run | done |
| JSON schema published and versioned | cozmo/contracts/export_schema.py, schema/plan.schema.json | cozmo schema | done |
| Rendered plan | cozmo/render/plan.py | plan.png next to plan.json | done (PNG only; SVG dropped per revised scope) |
| Run manifest and byte-identical reruns | cozmo/cli.py, cozmo/io/manifest.py, tests/test_cli.py | run_manifest.json, determinism test | done |
| Ground-truth format and benchmark registry | cozmo/io/ground_truth.py, benchmarks/ | EXAMPLE.yaml, captures.yaml | done (EXAMPLE values are fake) |
| Gate: opening_width (2 cm on 85%, denominator matched+missed+phantom) | cozmo/eval/gates.py, config/gates.yaml | eval.json gates[] | done |
| Gate: ceiling_height (1.5 cm per room, 1 cm spread across captures) | cozmo/eval/gates.py | eval.json gates[] | done |
| Gate: ceiling_height_diagnosis (ok, repeatable_but_biased, unrepeatable) | cozmo/eval/gates.py | label in eval.json and eval.md | done |
| Gate: repeatability (1 cm or 0.5% per wall, worst case) | cozmo/eval/gates.py, cozmo/eval/repeatability.py | per-wall table in eval.md | done |
| Gate: wall_length_tier (photo 8%, video 3%, lidar 2 cm or 1% PROVISIONAL) | cozmo/eval/gates.py, config/gates.yaml | eval.json gates[] | done; lidar budget provisional |
| Gate: footprint (8%) | cozmo/eval/gates.py | eval.json gates[] | done |
| Gate: stitch_adjacency (graph equality, missing and spurious edges) | cozmo/eval/gates.py | eval.json gates[] | done |
| Gate: stitch_overlap (pairwise intersection about 0) | cozmo/eval/gates.py | eval.json gates[] | done |
| Calibration (coverage, width %, confident garbage by tier and quantity) | cozmo/eval/calibration.py | calibration table in eval.json and eval.md | done (Winkler score dropped per revised scope) |
| Evaluation report | cozmo/eval/runner.py | eval.json, eval.md | done |
| Benchmark report with per-capture timing | cozmo/cli.py (bench) | benchmark.md | done |
| Drift ablation (--drift-correction on vs off) | cozmo/lidar/drift.py, cozmo/pipeline/lidar.py | drift_report.json: footprint area and mean wall thickness for both settings | done for the lidar tier |
| Head-to-head (tiers or pipelines on the same space) | benchmarks/captures.yaml, cozmo/eval/runner.py | same space_id across captures in one bench | partial: harness groups by space_id; no second pipeline to compare |
| Fix loop bundle (eval.md pasted back for iteration) | cozmo/eval/runner.py | eval.md | done |
| Capture protocol (how to film each tier) | docs/ | protocol document | not started |
| Device matrix (phones tested per tier) | docs/, benchmarks/ground_truth/*.yaml device field | matrix document | not started; device recorded per ground-truth file |
| Reproduction bundle (inputs, config, seed, manifest, outputs) | cozmo/cli.py, cozmo/io/manifest.py | run_manifest.json with hashes, versions, commit | done for a single run; no packaging script |
| Technical report | docs/ | report | not started |
| Raw data (captures and tape measurements) | data/sample/ (gitignored), benchmarks/captures.yaml | three iPhone LiDAR scans registered with truth null | partial: captures exist, tape measurements do not |
| Mirrors, glass, wet-look and low-light coverage | benchmarks/captures.yaml | flagged captures in registry | not started; registry has no scene-condition flags yet |

## Added in the LiDAR reconstruction task

| requirement | file path | artifact | status |
|---|---|---|---|
| Stray Scanner format reader (rgb.mp4, depth, confidence, odometry.csv) | cozmo/io/stray.py | StrayScan, Frame.unproject | done |
| Unprojection convention pinned by a regression test | tests/test_stray.py | floor of c00a170fe1 at world y = -1.48 m | done |
| Tier isolation enforced in code | cozmo/io/stray.py, cozmo/io/inputs.py | TierViolation; video sees only rgb.mp4; photo rejects scan folders | done |
| Point cloud with normals, voxel downsample | cozmo/lidar/cloud.py | Cloud | done |
| Floor and ceiling detection, ceiling prior when unobserved | cozmo/lidar/levels.py | prior_no_ceiling_observed method and warning | done |
| Manhattan alignment and wall faces | cozmo/lidar/walls.py | WallFace list, recorded in assumptions | done |
| Room segmentation and rectilinear polygons | cozmo/lidar/rooms.py, cozmo/lidar/cells.py | erosion and wall-driven cell complex, selectable with --segmentation | partial: neither is repeatable across two captures of one property. One fix loop run, see fix_loop/POSTMORTEM.md |
| Openings from wall occupancy gaps | cozmo/lidar/openings.py | doors and pass-throughs; windows not attempted, with a warning | partial |
| Adjacency from openings | cozmo/lidar/openings.py | adjacency[] | done |
| Drift correction, plane anchored | cozmo/lidar/drift.py | per-chunk yaw, height and 1D shift; drift_report.json | done; re-measured under wall-driven segmentation and it does not reduce wall smear on this data |
| Uncertainty model with named terms | cozmo/lidar/uncertainty.py | every Measurement in a lidar plan | done |
| Debug images | cozmo/lidar/debug.py | density, wall faces, room masks, openings | done |
| Bench without ground truth | cozmo/cli.py, cozmo/eval/self_consistency.py | benchmark.md no-ground-truth section | done |
| Cross-capture repeatability of the apartment pair | cozmo/eval/self_consistency.py | same-space check then the repeatability gate | done; the gate currently fails, reported as such |
| Runtime under 3 minutes for the largest scan | cozmo/pipeline/lidar.py | 9745 frames in 28 s on an M1 Max | done |

## Added in the repeatability fix loop

| requirement | file path | artifact | status |
|---|---|---|---|
| Cross-capture plan registration | cozmo/eval/registration.py | four quarter turns after per-plan Manhattan canonicalisation, translation by mask correlation | done |
| Room matching by polygon IoU | cozmo/eval/registration.py | Hungarian assignment, floor of 0.3 | done |
| Wall matching by nearest parallel face | cozmo/eval/registration.py | replaces cyclic order, which pairs walls that are not the same wall | done |
| Ghost-face rejection | cozmo/lidar/ghosts.py | visibility test, about 1% of face length rejected | done |
| Wall-driven cell complex segmentation | cozmo/lidar/cells.py | 1.0 to 1.6 m support band, doorway gap rule | done, but not better on the gate |
| Partially observed rooms flagged | cozmo/lidar/cells.py, cozmo/pipeline/lidar.py | perimeter support under 80%, intervals doubled | done |
| Fix loop artifacts | fix_loop/ | DECLARATION.md with addendum, before/, after/, evidence/, experiments/, DIFF.md, POSTMORTEM.md, regenerate.sh | done |
| Cross-capture repeatability gate passing | cozmo/eval/gates.py | 0 of 153 rows within tolerance | NOT DONE, see fix_loop/POSTMORTEM.md |
