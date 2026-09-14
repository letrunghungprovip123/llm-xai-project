#!/usr/bin/env bash
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
source "$ROOT/scripts/research/freddie_m21_m23_common_0020.sh"
freddie_analysis_paths "$ROOT"
freddie_assert_no_provider_execution
METRIC_PROTOCOL="$ROOT/config/research/replication/freddie_sflld_2024_metric_v1.json"
METRIC_LOCK_DIR="$FREDDIE_ANALYSIS_ROOT/metric_input_lock_v1"
METRIC_LOCK="$METRIC_LOCK_DIR/freddie_metric_input_lock.json"
freddie_require_file "$FREDDIE_ANALYSIS_INPUT_LOCK"
freddie_require_file "$FREDDIE_DATA_MART_DIR/data_mart_manifest.json"
mkdir -p "$METRIC_LOCK_DIR"
PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" \
python3 "$ROOT/scripts/research/freddie_metric_input_lock_0022.py" \
  --repo-root "$ROOT" \
  --analysis-lock "$FREDDIE_ANALYSIS_INPUT_LOCK" \
  --metric-protocol "$METRIC_PROTOCOL" \
  --data-mart-dir "$FREDDIE_DATA_MART_DIR" \
  --output "$METRIC_LOCK"
