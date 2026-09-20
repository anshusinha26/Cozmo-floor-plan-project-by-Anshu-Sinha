#!/usr/bin/env bash
# Regenerate one side of the fix loop from a clean checkout.
#
#   fix_loop/regenerate.sh before    # or: after
#
# Runs the full benchmark, copies plans, manifests, eval output and debug
# images into fix_loop/<side>/, and records the commit the run was made at.
# Everything it needs is in the repo except data/sample, which is gitignored.
set -euo pipefail

SIDE="${1:?usage: regenerate.sh before|after}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/fix_loop/$SIDE"
RUN="$OUT/bench"
PY="${PYTHON:-$ROOT/.venv/bin/python}"

cd "$ROOT"
test -d data/sample || { echo "data/sample is missing; it is gitignored and must be restored first" >&2; exit 1; }

rm -rf "$RUN"
mkdir -p "$OUT"
"$PY" -m cozmo.cli bench --set benchmarks/captures.yaml --out "$RUN" --seed 0 2>"$OUT/bench.log" | tee "$OUT/bench.stdout"

{
  echo "side: $SIDE"
  echo "commit: $(git rev-parse HEAD)"
  echo "commit_subject: $(git log -1 --pretty=%s)"
  echo "dirty: $(test -n "$(git status --porcelain)" && echo true || echo false)"
  echo "generated_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "python: $($PY --version 2>&1)"
  echo "config_sha256: $($PY -c 'from cozmo.io.manifest import load_config, config_sha256; print(config_sha256(load_config("config/gates.yaml")))')"
} > "$OUT/PROVENANCE.txt"

echo "wrote $OUT"
