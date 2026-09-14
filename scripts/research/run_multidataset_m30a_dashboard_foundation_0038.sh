#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-$(pwd)}"; export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
python "$ROOT/scripts/research/multidataset_m30a_dashboard_foundation_0038.py" --repo-root "$ROOT"
