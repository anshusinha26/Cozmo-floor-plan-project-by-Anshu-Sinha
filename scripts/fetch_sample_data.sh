#!/usr/bin/env bash
# Fetch the capture data. It is gitignored: too large for the repository and
# the supplied LiDAR scans are not ours to redistribute.
#
#   scripts/fetch_sample_data.sh
#   COZMO_DATA_URL='https://drive.google.com/drive/folders/...' scripts/fetch_sample_data.sh
#
# Defaults to the assessor-supplied sample folder. Downloads with gdown,
# unpacks any archives into data/sample/<scan_id>/, then checks that each scan
# has the Stray Scanner layout the LiDAR tier needs.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/data"
SAMPLE="$DEST/sample"
PY="${PYTHON:-$ROOT/.venv/bin/python}"
URL="${COZMO_DATA_URL:-https://drive.google.com/drive/folders/1rvcx0uEIwU6mIlEi8m5SF88jHK6ubAOu}"
FORCE="${1:-}"

mkdir -p "$SAMPLE"

layout_ok() {
  # A Stray Scanner export, whatever the folder is called.
  local d="$1"
  [ -f "$d/rgb.mp4" ] && [ -f "$d/odometry.csv" ] && [ -d "$d/depth" ] && [ -d "$d/confidence" ]
}

count_scans() {
  local n=0
  for d in "$SAMPLE"/*/; do
    [ -d "$d" ] || continue
    layout_ok "$d" && n=$((n + 1))
  done
  echo "$n"
}

if [ "$(count_scans)" -gt 0 ] && [ "$FORCE" != "--force" ]; then
  echo "data/sample already holds $(count_scans) scan(s); pass --force to download again"
else
  if ! command -v gdown >/dev/null 2>&1 && ! "$PY" -c "import gdown" >/dev/null 2>&1; then
    cat >&2 <<'MSG'
gdown is not installed. It normally arrives with `uv sync`; if you installed
some other way, add it and run again:

    uv pip install gdown

Or download the folder by hand from the URL below and unpack it so that
data/sample/<scan_id>/rgb.mp4 exists.
MSG
    echo "URL: $URL" >&2
    exit 1
  fi

  echo "Downloading capture data from:"
  echo "  $URL"
  TMP="$(mktemp -d)"
  trap 'rm -rf "$TMP"' EXIT
  if command -v gdown >/dev/null 2>&1; then
    gdown --folder "$URL" -O "$TMP" --remaining-ok
  else
    "$PY" -m gdown --folder "$URL" -O "$TMP" --remaining-ok
  fi

  # Unpack any archives, then move every scan folder into data/sample.
  find "$TMP" -type f \( -name '*.zip' -o -name '*.ZIP' \) -print0 |
    while IFS= read -r -d '' z; do
      echo "unzipping $(basename "$z")"
      unzip -q -o "$z" -d "${z%.*}"
      rm -f "$z"
    done

  # A scan is any directory containing odometry.csv. Its own name is the scan id.
  find "$TMP" -type f -name 'odometry.csv' -print0 |
    while IFS= read -r -d '' odo; do
      scan_dir="$(dirname "$odo")"
      scan_id="$(basename "$scan_dir")"
      echo "installing scan $scan_id"
      rm -rf "${SAMPLE:?}/$scan_id"
      mkdir -p "$SAMPLE"
      mv "$scan_dir" "$SAMPLE/$scan_id"
    done
fi

# Verify what we ended up with, and say exactly what is wrong if anything is.
echo
status=0
found=0
for d in "$SAMPLE"/*/; do
  [ -d "$d" ] || continue
  found=$((found + 1))
  name="$(basename "$d")"
  missing=""
  for want in rgb.mp4 odometry.csv; do
    [ -f "$d/$want" ] || missing="$missing $want"
  done
  for want in depth confidence; do
    [ -d "$d/$want" ] || missing="$missing $want/"
  done
  if [ -n "$missing" ]; then
    echo "  $name: INCOMPLETE, missing:$missing" >&2
    status=1
    continue
  fi
  n_depth="$(find "$d/depth" -name '*.png' | wc -l | tr -d ' ')"
  n_conf="$(find "$d/confidence" -name '*.png' | wc -l | tr -d ' ')"
  if [ "$n_depth" != "$n_conf" ]; then
    echo "  $name: INCOMPLETE, $n_depth depth frames against $n_conf confidence frames" >&2
    status=1
    continue
  fi
  echo "  $name: ok, $n_depth frames"
done

if [ "$found" -eq 0 ]; then
  echo "No scans in $SAMPLE. The download produced nothing usable." >&2
  exit 1
fi

if [ "$status" -ne 0 ]; then
  echo >&2
  echo "At least one scan is incomplete. The LiDAR tier needs rgb.mp4, odometry.csv," >&2
  echo "depth/ and confidence/ with one depth frame per confidence frame." >&2
  exit 1
fi

echo
echo "data/sample is ready. Hand-measured captures live in data/own and are shared separately."
