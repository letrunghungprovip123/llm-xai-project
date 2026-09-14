#!/usr/bin/env bash
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
source "$ROOT/scripts/research/freddie_m21_m23_common_0020.sh"
freddie_analysis_paths "$ROOT"
freddie_assert_no_provider_execution
METRIC_LOCK="$FREDDIE_ANALYSIS_ROOT/metric_input_lock_v1/freddie_metric_input_lock.json"
freddie_require_file "$METRIC_LOCK"
PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" \
python3 "$ROOT/scripts/research/freddie_m22_metrics_0023.py" \
  --repo-root "$ROOT" \
  --metric-lock "$METRIC_LOCK" \
  --output-dir "$FREDDIE_METRIC_DIR"
