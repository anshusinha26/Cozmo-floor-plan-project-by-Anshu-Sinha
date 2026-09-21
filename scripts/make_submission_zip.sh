#!/usr/bin/env bash
# Package the repository for submission, history included.
#
#   scripts/make_submission_zip.sh [output.zip]
#
# Includes .git, so a reviewer can read the commit history and check that the
# fix loops were declared before the fixes rather than after. Excludes the
# things that are large, fetchable or machine-specific: capture data, model
# weights, caches, virtualenvs. The zip is written outside the repository so
# it never ends up inside the next one.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAME="$(basename "$ROOT")"
STAMP="$(date -u +%Y%m%d-%H%M)"
OUT="${1:-$(dirname "$ROOT")/${NAME}-submission-${STAMP}.zip}"
MAX_MB="${MAX_FILE_MB:-50}"

case "$OUT" in
  "$ROOT"/*) echo "refusing to write the zip inside the repository: $OUT" >&2; exit 2 ;;
esac

cd "$ROOT"

# Anything this size or larger is a cache or a download, never source.
LARGE=$(find . -type f -size +"${MAX_MB}"M \
          -not -path './.git/*' -not -path './.venv/*' -not -path './data/*' 2>/dev/null || true)
if [ -n "$LARGE" ]; then
  echo "excluding files over ${MAX_MB} MB:" >&2
  echo "$LARGE" | sed 's/^/  /' >&2
fi

EXCLUDES=(
  '.venv/*' '*/.venv/*'
  'data/*'                     # captures: gitignored, fetched by script
  '*/__pycache__/*' '*.pyc'
  '.pytest_cache/*'
  '*.egg-info/*'
  'runs/*' 'out/*'
  '.DS_Store' '*/.DS_Store'
  '*.safetensors' '*.pt' '*.bin' '*.ckpt'   # model weights, fetched by script
)
ARGS=()
for e in "${EXCLUDES[@]}"; do ARGS+=(-x "$e"); done
while IFS= read -r f; do
  [ -n "$f" ] && ARGS+=(-x "${f#./}")
done <<< "$LARGE"

rm -f "$OUT"
zip -q -r "$OUT" . "${ARGS[@]}"

SIZE=$(du -h "$OUT" | cut -f1)
COUNT=$(unzip -l "$OUT" | tail -1 | awk '{print $2}')
echo
echo "wrote $OUT"
echo "  $SIZE, $COUNT entries, git history included"
echo
echo "check what a reviewer receives:"
echo "  unzip -l '$OUT' | head -40"
