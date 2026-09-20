# Compliance matrix

Status is one of: done, partial, not started, waived.
"Done" here means the harness side exists and is tested. No reconstruction
exists yet, so every accuracy row is scored on the stub only.

| requirement | file path | artifact | status |
|---|---|---|---|
| Photo tier (2 or more stills per room, no depth, no poses) | cozmo/io/inputs.py, cozmo/pipeline/stub.py | input validation, stub plan | partial: input convention validated, no reconstruction |
| Video tier (handheld walkthrough clip per room) | cozmo/io/inputs.py, cozmo/pipeline/stub.py | input validation, stub plan | partial: input convention validated, no reconstruction |
| LiDAR tier (rgb, depth, poses, intrinsics per room) | cozmo/io/inputs.py, config/gates.yaml | input validation, PROVISIONAL gate | waived: no iPhone available, approved by email; validation on public ARKitScenes data is a stretch goal |
| Per-room plan (polygon, walls, openings) | cozmo/contracts/models.py | plan.json rooms[] | done (contract); stub values only |
| Ceiling height per room with interval | cozmo/contracts/models.py, cozmo/eval/gates.py | rooms[].ceiling_height_m, ceiling_height gate | done (contract and gate); stub values only |
| Floor area per room with interval | cozmo/contracts/models.py, cozmo/eval/calibration.py | rooms[].floor_area_m2, calibration row floor_area | done (contract and calibration); stub values only |
| Openings (door, window, pass-through) with width, height, offset | cozmo/contracts/models.py, cozmo/eval/matching.py | rooms[].openings[], opening matching | done (contract and matching); stub values only |
| Stitched plan with adjacency graph | cozmo/contracts/models.py, cozmo/eval/gates.py | stitched_plan, adjacency[], stitch_adjacency and stitch_overlap gates | done (contract and gates); stub values only |
| Damage regions with class enum and extent | cozmo/contracts/models.py | damage_regions[], DamageClass | done (contract); no detector |
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
| Drift ablation (--drift-correction on vs off) | cozmo/cli.py | flag recorded in run_manifest.json | partial: flag plumbed and hashed, no effect until a pipeline uses it |
| Head-to-head (tiers or pipelines on the same space) | benchmarks/captures.yaml, cozmo/eval/runner.py | same space_id across captures in one bench | partial: harness groups by space_id; no second pipeline to compare |
| Fix loop bundle (eval.md pasted back for iteration) | cozmo/eval/runner.py | eval.md | done |
| Capture protocol (how to film each tier) | docs/ | protocol document | not started |
| Device matrix (phones tested per tier) | docs/, benchmarks/ground_truth/*.yaml device field | matrix document | not started; device recorded per ground-truth file |
| Reproduction bundle (inputs, config, seed, manifest, outputs) | cozmo/cli.py, cozmo/io/manifest.py | run_manifest.json with hashes, versions, commit | done for a single run; no packaging script |
| Technical report | docs/ | report | not started |
| Raw data (captures and tape measurements) | benchmarks/captures/, benchmarks/ground_truth/ | real captures | not started; EXAMPLE placeholders only |
| Mirrors, glass, wet-look and low-light coverage | benchmarks/captures.yaml | flagged captures in registry | not started; registry has no scene-condition flags yet |
