#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-$(pwd)}"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
python "$ROOT/scripts/research/multidataset_m29_visualization_input_lock_0036.py" \
 --repo-root "$ROOT" \
 --protocol "$ROOT/config/research/replication/multidataset_visualization_v3.json" \
 --output "$ROOT/data/reports/llm_validation/multidataset_replication_v1/m29_visualization_input_lock_v1/multidataset_visualization_input_lock.json"
