#!/usr/bin/env bash
# Regenerate the BEFORE run of fix loop 3.
#
#   fix_loop/loop3_photo_unanchored_wall/before/regenerate.sh [out_dir]
#
# Checks out the commit in provenance.json and runs the five-room photo capture
# through it. MapAnything is deterministic for a fixed input set, so unlike the
# video tier this reproduces without a cached reconstruction.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
OUT="${1:-$REPO/runs/photo/loop3_before}"
COMMIT="$(python3 -c "import json;print(json.load(open('$HERE/provenance.json'))['commit'])")"
SNAP="$(mktemp -d)"
git -C "$REPO" archive "$COMMIT" | tar -x -C "$SNAP"
ln -s "$REPO/.venv" "$SNAP/.venv"; ln -s "$REPO/data" "$SNAP/data"
cd "$SNAP"
export PYTORCH_ENABLE_MPS_FALLBACK=1 TOKENIZERS_PARALLELISM=false
.venv/bin/python -m cozmo.cli run --input data/own --tier photo --out "$OUT" \
    --exclude app_comparision --repeat bedroom_2_repeat --connector hall
echo "regenerated into $OUT"
