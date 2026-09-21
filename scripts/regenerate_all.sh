#!/usr/bin/env bash
# Rebuild every number this repository reports.
#
#   scripts/regenerate_all.sh          everything
#   scripts/regenerate_all.sh --quick  skip the parts that need model weights
#
# Needs data/ (scripts/fetch_sample_data.sh) and, unless --quick, the model
# weights (scripts/fetch_weights.sh). Each step prints where it wrote.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-$ROOT/.venv/bin/python}"
QUICK="${1:-}"
cd "$ROOT"

step() { echo; echo "=== $* ==="; }

step "Tests"
"$PY" -m pytest -q

step "JSON schema"
"$PY" -m cozmo.cli schema --out schema/plan.schema.json

if [ ! -d data/sample ]; then
  echo "data/sample is missing; run scripts/fetch_sample_data.sh first" >&2
  exit 1
fi

step "Fix loop 1: BEFORE run (erosion segmentation)"
fix_loop/regenerate.sh before

step "Fix loop 1: AFTER run (cell complex segmentation)"
fix_loop/regenerate.sh after

step "Fix loop 1: evidence figures"
"$PY" fix_loop/evidence_run.py >/dev/null
echo "wrote fix_loop/evidence/"

step "Fix loop 1: ghost-only falsifier"
rm -rf fix_loop/experiments/ghost_only/runs
"$PY" fix_loop/experiments/ghost_only/run.py >/dev/null
echo "wrote fix_loop/experiments/ghost_only/result.json"

step "Technical report PDF"
scripts/build_report.sh

step "Benchmark: every capture with ground truth, all tiers"
# Video and photo plans are reused from the tier branch rather than recomputed;
# the report records the source of every plan and whether its input still
# hashes the same. Pass --skip-lidar to reuse those too.
"$PY" scripts/benchmark_all.py >/dev/null
echo "wrote docs/benchmark/"

step "Head to head against AR Plan 3D"
"$PY" scripts/head_to_head.py --out docs/head_to_head.md >/dev/null
echo "wrote docs/head_to_head.md"

if [ "$QUICK" = "--quick" ]; then
  echo
  echo "Skipped the damage runs (--quick). Everything else is rebuilt."
  exit 0
fi

step "Damage: filter ablation"
"$PY" scripts/damage_ablation.py >/dev/null
echo "wrote docs/damage_eval/ablation.json"

step "Damage: end-to-end run"
"$PY" scripts/run_damage_eval.py >/dev/null
echo "wrote docs/damage_eval/damage_eval.json"

step "Hazards: low light on the staged damage photos"
"$PY" scripts/hazard_lowlight.py --source own >/dev/null
echo "wrote docs/damage_eval/lowlight_own.json"

echo
echo "All reported numbers rebuilt."
