#!/usr/bin/env bash
# Pre-download every model weight the video tier needs, so a run never blocks on
# a network fetch and an offline machine fails here instead of half way through
# a reconstruction.
#
#   scripts/fetch_weights.sh
#
# Weights land in the Hugging Face cache. Set HF_HOME to move it somewhere else,
# for example a shared volume in CI.
set -euo pipefail

PYTHON="${PYTHON:-.venv/bin/python}"
if [ ! -x "$PYTHON" ]; then
  PYTHON="$(command -v python3)"
fi

echo "python:   $PYTHON"
echo "HF_HOME:  ${HF_HOME:-<default: ~/.cache/huggingface>}"
echo

"$PYTHON" - <<'PY'
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
print("\nall weights present")
PY

echo
echo "ffmpeg binary (bundled with imageio-ffmpeg, used for decoding):"
"$PYTHON" -c "import imageio_ffmpeg; print(' ', imageio_ffmpeg.get_ffmpeg_exe())"
