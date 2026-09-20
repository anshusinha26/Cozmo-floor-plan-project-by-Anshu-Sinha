#!/usr/bin/env bash
# Regenerate the BEFORE run of fix loop 2.
#
#   fix_loop/loop2_video_scale/before/regenerate.sh [output_dir]
#
# Checks out the commit named in provenance.json into a temporary tree and runs
# the six clips through it. The reconstructions in runs/video/*/debug/sfm are
# reused when their frame digest matches, which is what makes this reproduce the
# same numbers: pycolmap 4.2 is not bit-reproducible even with every seed and
# thread count pinned (same chunk sizes, camera centres up to 6% of the chunk
# extent apart), so the cached reconstruction is the reproducible artefact.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
OUT="${1:-$REPO/runs/video}"
COMMIT="$(python3 -c "import json,sys;print(json.load(open('$HERE/provenance.json'))['commit'])")"
SNAP="$(mktemp -d)"

echo "commit:   $COMMIT"
echo "snapshot: $SNAP"
git -C "$REPO" archive "$COMMIT" | tar -x -C "$SNAP"
ln -s "$REPO/.venv" "$SNAP/.venv"
ln -s "$REPO/data" "$SNAP/data"
mkdir -p "$OUT"
ln -s "$OUT" "$SNAP/runs_out"

cd "$SNAP"
export PYTORCH_ENABLE_MPS_FALLBACK=1 TOKENIZERS_PARALLELISM=false
.venv/bin/python -m cozmo.cli run --input data/sample/c00a170fe1 --tier video \
    --out "runs_out/c00a170fe1" --video-rotation 90
for room in bedroom_1 bedroom_2 bedroom_2_repeat kitchen hall; do
  .venv/bin/python -m cozmo.cli run --input "data/own/$room" --tier video \
      --out "runs_out/$room" || echo "$room failed, which is part of the before state"
done
echo "regenerated into $OUT"
