#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-$(pwd)}"; export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
python "$ROOT/scripts/research/multidataset_m30b_overview_0039.py" --repo-root "$ROOT"
