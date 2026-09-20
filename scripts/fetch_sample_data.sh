#!/usr/bin/env bash
# Fetch the capture data. It is gitignored: too large for the repository and
# not ours to redistribute.
#
#   scripts/fetch_sample_data.sh
#
# Expects `gdown` (pip install gdown) or a manual download. After it runs,
# data/ holds:
#   data/sample/{c00a170fe1,1a8384c3f6,c7d28f72c6}   supplied Stray Scanner scans
#   data/own/{hall,bedroom_1,bedroom_2,bedroom_2_repeat,kitchen,app_comparision}
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/data"
# Set COZMO_DATA_URL to the shared Drive folder before running.
URL="${COZMO_DATA_URL:-}"

mkdir -p "$DEST"

if [ -d "$DEST/sample" ] && [ -d "$DEST/own" ]; then
  echo "data/ already present; nothing to do"
  exit 0
fi

if [ -z "$URL" ]; then
  cat >&2 <<'MSG'
No download URL set.

Set COZMO_DATA_URL to the shared Drive folder and run again:

    COZMO_DATA_URL='https://drive.google.com/drive/folders/...' scripts/fetch_sample_data.sh

Or download it by hand and unpack it so that these exist:

    data/sample/c00a170fe1/rgb.mp4
    data/own/bedroom_1/

Everything except the capture data is in the repository, so the tests and the
documents work without this step. Only the runs that read captures need it.
MSG
  exit 1
fi

if ! command -v gdown >/dev/null 2>&1; then
  echo "gdown not found; install it with: uv pip install gdown" >&2
  exit 1
fi

echo "Downloading capture data into $DEST"
gdown --folder "$URL" -O "$DEST"
echo "done"
