#!/usr/bin/env bash
# Fetch every model weight the pipeline can use. Run once after `uv sync`.
#
#   scripts/fetch_weights.sh
#
# About 1.9 GB into the HuggingFace cache (~/.cache/huggingface). Nothing in
# the repository downloads weights during a run: if they are missing, the
# damage module fails and says to run this.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-$ROOT/.venv/bin/python}"

echo "Fetching OWLv2 (damage detection, Apache 2.0)"
"$PY" "$ROOT/scripts/fetch_damage_weights.py"

echo "Fetching SigLIP (crop verifier, Apache 2.0)"
"$PY" - <<'PYEOF'
from transformers import AutoModel, AutoProcessor

from cozmo.damage.filters import CropVerifier

AutoProcessor.from_pretrained(CropVerifier.DEFAULT_MODEL)
AutoModel.from_pretrained(CropVerifier.DEFAULT_MODEL)
print("done")
PYEOF

echo
echo "Weights are cached. Reconstruction itself needs no weights at all."
