#!/usr/bin/env bash
# Render docs/technical_report.md to PDF and report the page count.
#
#   scripts/build_report.sh [input.md] [output.pdf]
#
# Tries, in order: pandoc with a LaTeX engine, pandoc with wkhtmltopdf, then a
# pure-Python fallback that needs no system tools. The report has a hard limit
# of 6 pages, and this script fails if the render exceeds it.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${1:-$ROOT/docs/technical_report.md}"
OUT="${2:-$ROOT/docs/technical_report.pdf}"
PY="${PYTHON:-$ROOT/.venv/bin/python}"
LIMIT=6

page_count() {
  "$PY" - "$1" <<'PYEOF'
import re
import sys
from pathlib import Path

data = Path(sys.argv[1]).read_bytes()
# Count page objects without a PDF library: /Type /Page not followed by 's'.
n = len(re.findall(rb"/Type\s*/Page[^s]", data))
print(n if n else 0)
PYEOF
}

rendered=""

if command -v pandoc >/dev/null 2>&1; then
  echo "rendering with pandoc"
  if pandoc "$SRC" -o "$OUT" \
      -V geometry:margin=2cm -V fontsize=9pt -V colorlinks=true 2>/dev/null; then
    rendered="pandoc"
  elif command -v wkhtmltopdf >/dev/null 2>&1 &&
       pandoc "$SRC" -o "$OUT" --pdf-engine=wkhtmltopdf 2>/dev/null; then
    rendered="pandoc+wkhtmltopdf"
  fi
fi

if [ -z "$rendered" ]; then
  echo "pandoc with a working PDF engine not found; using the Python fallback"
  if "$PY" "$ROOT/scripts/md_to_pdf.py" "$SRC" "$OUT"; then
    rendered="reportlab"
  fi
fi

if [ -z "$rendered" ] || [ ! -f "$OUT" ]; then
  cat >&2 <<MSG

Could not render a PDF. Install one of these and run again:

    brew install pandoc basictex     # macOS, full quality
    apt-get install pandoc texlive   # Debian or Ubuntu
    uv pip install reportlab         # no system tools needed

Or read the Markdown directly: $SRC
MSG
  exit 1
fi

pages="$(page_count "$OUT")"
echo
echo "wrote $OUT via $rendered"
echo "pages: $pages (limit $LIMIT)"

if [ "$pages" -gt "$LIMIT" ] 2>/dev/null; then
  echo "OVER THE LIMIT by $((pages - LIMIT)) page(s). Cut the report, do not raise the limit." >&2
  exit 1
fi
