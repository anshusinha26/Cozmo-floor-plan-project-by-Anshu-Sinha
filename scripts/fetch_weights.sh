#!/usr/bin/env bash
# Pre-download every model weight any tier can use, so a run never blocks on a
# network fetch and an offline machine fails here rather than half way through
# a reconstruction.
#
#   scripts/fetch_weights.sh            everything
#   scripts/fetch_weights.sh damage     damage detection only
#   scripts/fetch_weights.sh video      video and photo tiers only
#
# Weights land in the Hugging Face cache. Set HF_HOME to move it, for example
# to a shared volume in CI.
#
# Measured sizes on disk, symlinks followed:
#
#   OWLv2                                damage detection      1.2 GB
#   SigLIP                               crop verifier         1.5 GB
#   Depth Pro                            video and photo       1.9 GB
#   Depth Anything V2 Metric Indoor L    video and photo       1.3 GB
#   MapAnything (Apache checkpoint)      chunk-boundary poses  1.4 GB
#
# The lidar tier needs none of them: it is classical geometry, so nothing in a
# lidar dimension came from a trained model.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-$ROOT/.venv/bin/python}"
[ -x "$PY" ] || PY="$(command -v python3)"
WHICH="${1:-all}"

echo "python:   $PY"
echo "HF_HOME:  ${HF_HOME:-<default: ~/.cache/huggingface>}"
echo "fetching: $WHICH"
echo

if [ "$WHICH" = "all" ] || [ "$WHICH" = "damage" ]; then
  echo "=== damage detection ==="
  echo "OWLv2 (Apache 2.0), open-vocabulary detection"
  "$PY" "$ROOT/scripts/fetch_damage_weights.py"

  echo "SigLIP (Apache 2.0), crop verifier"
  "$PY" - <<'PYEOF'
from transformers import AutoModel, AutoProcessor

from cozmo.damage.filters import CropVerifier

AutoProcessor.from_pretrained(CropVerifier.DEFAULT_MODEL)
AutoModel.from_pretrained(CropVerifier.DEFAULT_MODEL)
print("  ok")
PYEOF
fi

if [ "$WHICH" = "all" ] || [ "$WHICH" = "video" ]; then
  echo
  echo "=== video and photo tiers ==="
  "$PY" - <<'PYEOF'
import sys

from huggingface_hub import hf_hub_download, snapshot_download

# Depth Pro: metric scale, given the focal length COLMAP estimates.
# Depth Anything V2 Metric Indoor: the dense pass.
# MapAnything: relative poses across a chunk boundary, nothing else.
FILES = [("apple/DepthPro", "depth_pro.pt")]
SNAPSHOTS = [
    "depth-anything/Depth-Anything-V2-Metric-Indoor-Large-hf",
    "facebook/map-anything-apache",
]

failed = []
for repo, name in FILES:
    try:
        print(f"fetching {repo}:{name} ...", flush=True)
        print("  ->", hf_hub_download(repo, name))
    except Exception as e:
        failed.append(f"{repo}:{name}: {type(e).__name__}: {e}")
for repo in SNAPSHOTS:
    try:
        print(f"fetching {repo} ...", flush=True)
        print("  ->", snapshot_download(repo))
    except Exception as e:
        failed.append(f"{repo}: {type(e).__name__}: {e}")

if failed:
    print("\nFAILED:", file=sys.stderr)
    for f in failed:
        print("  " + f, file=sys.stderr)
    sys.exit(1)
PYEOF
fi

echo
echo "ffmpeg binary (bundled with imageio-ffmpeg, used for decoding):"
"$PY" -c "import imageio_ffmpeg; print(' ', imageio_ffmpeg.get_ffmpeg_exe())" 2>/dev/null ||
  echo "  not installed; it arrives with the video extra"

echo
echo "Weights are cached. The lidar tier needs none of them."
