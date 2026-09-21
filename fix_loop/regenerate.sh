#!/usr/bin/env bash
# Regenerate one side of fix loop 1 (room segmentation) from a clean checkout.
#
#   fix_loop/regenerate.sh before    # or: after
#
# Runs the loop's pinned capture registry, copies plans, manifests, eval
# output and debug images into fix_loop/<side>/, and records the commit the
# run was made at.
#
# The registry is fix_loop/captures_loop1.yaml, not benchmarks/captures.yaml,
# because these snapshots are evidence for a comparison made when only those
# five captures existed. Reading the live registry would sweep every capture
# added since into a snapshot that never contained them.
# Everything it needs is in the repo except data/sample, which is gitignored.
set -euo pipefail

SIDE="${1:?usage: regenerate.sh before|after}"
# BEFORE is the erosion segmentation, AFTER is the wall-driven cell complex.
# Both run the same eval on the same captures, so the comparison is fair.
case "$SIDE" in
  before) SEG=erosion ;;
  after)  SEG=cells ;;
  *) echo "usage: regenerate.sh before|after" >&2; exit 2 ;;
esac
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/fix_loop/$SIDE"
RUN="$OUT/bench"
PY="${PYTHON:-$ROOT/.venv/bin/python}"

cd "$ROOT"
test -d data/sample || { echo "data/sample is missing; it is gitignored and must be restored first" >&2; exit 1; }

rm -rf "$RUN"
mkdir -p "$OUT"
REGISTRY="$ROOT/fix_loop/captures_loop1.yaml"
"$PY" -m cozmo.cli bench --set "$REGISTRY" --out "$RUN" --seed 0 \
  --segmentation "$SEG" 2>"$OUT/bench.log" | tee "$OUT/bench.stdout"

# Logs are committed, so the machine they were produced on must not be.
for f in "$OUT/bench.log" "$OUT/bench.stdout"; do
  [ -f "$f" ] || continue
  sed -i '' -e "s#$ROOT/##g" -e "s#$ROOT#.#g" "$f" 2>/dev/null ||
    sed -i -e "s#$ROOT/##g" -e "s#$ROOT#.#g" "$f"
done

{
  echo "side: $SIDE"
  echo "segmentation: $SEG"
  echo "registry: fix_loop/captures_loop1.yaml"
  echo "commit: $(git rev-parse HEAD)"
  echo "commit_subject: $(git log -1 --pretty=%s)"
  echo "dirty: $(test -n "$(git status --porcelain)" && echo true || echo false)"
  echo "generated_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "python: $($PY --version 2>&1)"
  echo "config_sha256: $($PY -c 'from cozmo.io.manifest import load_config, config_sha256; print(config_sha256(load_config("config/gates.yaml")))')"
} > "$OUT/PROVENANCE.txt"

echo "wrote $OUT"
