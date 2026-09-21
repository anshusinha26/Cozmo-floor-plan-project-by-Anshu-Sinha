# Compliance matrix

Status is one of: done, partial, not started, waived.
"Done" here means the artefact exists and is tested. All three tiers now
reconstruct for real; accuracy rows are scored on those outputs, and the
numbers behind them are in `docs/benchmark/benchmark.md`. The stub pipeline
survives only as a test fixture reachable through `--pipeline stub`, and
nothing it produces appears in any reported result.

| requirement | file path | artifact | status |
|---|---|---|---|
| Photo tier (2 or more stills per room, no depth, no poses) | cozmo/pipeline/photo/ | real reconstruction; 2.2% median wall error over 12 walls, worst 31.9% | partial: runs on every room, 8 of 12 walls inside the 8% budget after fix loop 3. See fix_loop/loop3_photo_unanchored_wall/ |
| Video tier (one clip per room) | cozmo/pipeline/video/ | real reconstruction; 32.9% median wall error over 16 walls | partial: runs on every clip, not accurate enough to ship. Two fix loops, see fix_loop/loop2_video_scale/POSTMORTEM.md |
| LiDAR tier (Stray Scanner scan folder) | cozmo/io/stray.py, cozmo/lidar/, cozmo/pipeline/lidar.py | reconstruction to plan.json, plan.png, drift_report.json, debug images | done: no longer waived. Sample iPhone LiDAR scans supplied; classical reconstruction runs on all three. Accuracy unverified: no tape ground truth yet |
| Per-room plan (polygon, walls, openings) | cozmo/contracts/models.py, cozmo/lidar/, cozmo/pipeline/ | plan.json rooms[] | done; reconstructed values at all three tiers |
| Ceiling height per room with interval | cozmo/contracts/models.py, cozmo/eval/gates.py | rooms[].ceiling_height_m, ceiling_height gate | done and scored against tape; the gate fails at both image tiers, see docs/benchmark/benchmark.md |
| Floor area per room with interval | cozmo/contracts/models.py, cozmo/eval/calibration.py | rooms[].floor_area_m2 | done and emitted at every tier; never scored, because no room has a tape-measured floor area to score it against |
| Openings (door, window, pass-through) with width, height, offset | cozmo/contracts/models.py, cozmo/eval/matching.py | rooms[].openings[], opening matching | partial: contract, detection and matching done, but 0 of 7 openings match at either image tier, so the gate fails on absence |
| Stitched plan with adjacency graph | cozmo/contracts/models.py, cozmo/pipeline/photo/merge.py, cozmo/eval/gates.py | stitched_plan, adjacency[], stitch_adjacency and stitch_overlap gates | done and scored; adjacency matches truth, overlap is in docs/benchmark/benchmark.md |
| Damage regions with class enum and extent | cozmo/contracts/models.py, cozmo/damage/detector.py, cozmo/damage/extent.py | damage_regions[], DamageClass | partial: detector, four precision filters and metric extent all work and are measured, but the module is **not wired into `cozmo run`**. It is reached through scripts/run_damage_eval.py, so plan.json still emits an empty list and a warning saying so. Precision is poor on photos: docs/damage_eval/README.md |
| Concealed-damage flags with rule id and evidence | cozmo/contracts/models.py, cozmo/damage/rules.py | concealed_damage_flags[] | partial: the rules engine emits a rule id and its evidence, but reaches plan.json only through the damage scripts, not through `cozmo run` |
| Scope items with quantity and basis | cozmo/contracts/models.py, cozmo/damage/pipeline.py | scope_items[] | partial: generated from the surviving damage regions, on the same script-only path as the flags above |
| Interval on every measurement (no bare floats) | cozmo/contracts/models.py, tests/test_contract.py | Measurement type, bare-dimension walker on emitted output; coverage 0.94 photo and 1.00 video, measured | done |
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
| Head-to-head against a rival app | benchmarks/head_to_head/arplan3d.yaml, docs/benchmark/head_to_head_photo.md | AR Plan 3D against our photo and video tiers, both against tape | done: photo beats or ties on 33% of dimensions, video on 0% |
| Fix loop bundle (eval.md pasted back for iteration) | cozmo/eval/runner.py | eval.md | done |
| Capture protocol (how to film each tier) | docs/capture_protocol.md | one-page protocol, three routes, each ending in the exact command | done |
| Device matrix (phones tested per tier) | docs/device_matrix.md, benchmarks/captures.yaml device field | matrix document, device recorded per capture | done |
| Reproduction bundle (inputs, config, seed, manifest, outputs) | scripts/regenerate_all.sh, scripts/fetch_weights.sh, scripts/fetch_sample_data.sh, cozmo/io/manifest.py | one command rebuilds every reported number; run_manifest.json carries hashes, versions and commit | done |
| Technical report | docs/technical_report.md, scripts/build_report.sh | one bound document, 6 rendered pages, every number traced to a file and a regenerating script, no PENDING cells left | done |
| Raw data (captures and tape measurements) | data/ (gitignored), benchmarks/captures.yaml, benchmarks/ground_truth/ | three supplied iPhone LiDAR scans with truth null, plus five hand-measured rooms captured as photos and 4K video. Raw data, access restricted to the assessors: https://drive.google.com/drive/folders/1MkwFUkSrNJ4x_tVjm0pCOvGsyGjdGNaR . Download `own` and `own_compressed` into data/; the LiDAR scans come from scripts/fetch_sample_data.sh | done |
| Mirrors, glass, wet-look and low-light coverage | docs/hazards.md, scripts/hazard_lowlight.py | one section each with evidence: shower screen, wardrobe mirror, glossy tiles, darkened photos at two levels, moving dog, textureless walls, unobserved ceiling | done |

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
| Cross-capture repeatability, official pair | cozmo/eval/self_consistency.py, benchmarks/captures.yaml | bedroom_2 against bedroom_2_repeat, same-device at video tier and cross-device at photo tier | registered; awaiting predictions from the photo and video tiers |
| Cross-capture repeatability, sample LiDAR pair | cozmo/cli.py, fix_loop/evidence/ | reported as coverage-mismatched, not a valid repeat: strict 0 of 153 kept visible, plus 14 shared walls and 1.9 cm face agreement as a labelled secondary statistic | done |
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

## Added in the precision, robustness and documents pass

| requirement | file path | artifact | status |
|---|---|---|---|
| Damage precision filters, measured individually | cozmo/damage/filters.py, scripts/damage_ablation.py | ablation table per filter and per threshold | done: 63 to 9 false regions on photos, 106 to 0 on LiDAR |
| Distractor prompts | cozmo/damage/detector.py | 14 everyday lookalikes competing with the damage prompts | done; measured effect is small |
| Crop verifier | cozmo/damage/filters.py | SigLIP zero-shot check on each surviving crop | done; the filter that does most of the work |
| iPhone input robustness | cozmo/io/inputs.py, tests/test_iphone_inputs.py | HEIC, .mov, .hevc, mixed case, sidecar files, any scan folder name | done |
| Clear input error messages | cozmo/io/inputs.py | every rejection names what was found and what is accepted | done |
| Capture protocol | docs/capture_protocol.md | one page, three routes, what to avoid | done |
| Device matrix | docs/device_matrix.md | capture hardware by processing hardware by tier | done; every accuracy cell now carries a measured number, none invented |
| README, install to first run under 15 minutes | README.md | quickstart, licences, AI disclosure | done |
| Reproduction bundle | scripts/regenerate_all.sh and the two fetch scripts | rebuilds every reported number | done |
| Sample data fetch | scripts/fetch_sample_data.sh | defaults to the assessor-supplied Drive folder, unpacks into data/sample/<scan_id>/ and verifies the Stray Scanner layout | done |
| MapAnything rejection evidence | docs/experiments/mapanything/result.json | 0.70x depth scale over three runs, smeared top-down density | done |
| Report renderer | scripts/build_report.sh, scripts/md_to_pdf.py | PDF via pandoc when present, reportlab fallback otherwise, fails if over 6 pages | done |

## Added in the merge and full benchmark

| requirement | file path | artifact | status |
|---|---|---|---|
| Benchmark across every tier with ground truth | scripts/benchmark_all.py, docs/benchmark/benchmark.md | gates, coverage, repeatability, timing, head to head, with per-plan provenance | done |
| Reuse of expensive plans, declared | docs/benchmark/provenance.json | every plan records its source and whether its input still hashes the same | done |
| Interval coverage per tier and quantity | docs/benchmark/eval.json | photo 0.94 at 43% width, video 1.00 at 409% width, one confident-garbage case | done |
| Repeatability, same-device video pair | docs/benchmark/benchmark.md | bedroom_2 against bedroom_2_repeat, 0 of 8 rows within tolerance | done; the gate fails |
| Fix loop 2, video scale | fix_loop/loop2_video_scale/ | declaration, before and after runs, postmortem, iteration 2 rejected | done; negative result |
| Install profiles and extras | pyproject.toml, README.md | lidar-only quick path and everything; damage, video, photo and all extras | done |
| Model weights, all tiers | scripts/fetch_weights.sh | five checkpoints with measured sizes, fetched in halves or all at once | done |

| Gates reported per tier | cozmo/eval/runner.py, docs/benchmark/benchmark.md | one table per tier, plus a pooled table kept for completeness | done |
| Empty gates read NOT EVALUATED | cozmo/eval/gates.py, tests/test_gates.py | status with the reason; an unevaluated gate can never count as a pass | done |
| Full-profile install rehearsal | docs/rehearsal.md | clean clone, all extras, every weight, timed with measured sizes | done |
| Photo focal regression, found and fixed | fix_loop/loop2_video_scale/photo_ablation.md | root cause: the model guessed a 464 px focal against a true 332 px; ablation table as evidence | done |
| Photo stitcher placement fix | cozmo/pipeline/photo/merge.py, docs/benchmark/benchmark.md | identity placements, stitch_overlap 28.01 m2 to 0.0000 | done |
