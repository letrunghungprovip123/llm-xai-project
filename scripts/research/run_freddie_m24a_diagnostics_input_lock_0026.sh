#!/usr/bin/env bash
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
source "$ROOT/scripts/research/freddie_m24_m26_common_0026.sh"
freddie_m24_m26_paths "$ROOT"
m24_m26_assert_no_provider_execution
for file in \
  "$FREDDIE_DIAGNOSTICS_PROTOCOL" \
  "$FREDDIE_ANALYSIS_INPUT_LOCK" \
  "$FREDDIE_DATA_MART_DIR/data_mart_manifest.json" \
  "$FREDDIE_METRIC_DIR/metric_manifest.json" \
  "$FREDDIE_STAT_DIR/statistical_manifest.json"
do
  m24_m26_require_file "$file"
done
mkdir -p "$FREDDIE_DIAGNOSTICS_LOCK_DIR"
PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" \
python3 "$ROOT/scripts/research/freddie_m24_diagnostics_input_lock_0026.py" \
  --repo-root "$ROOT" \
  --protocol "$FREDDIE_DIAGNOSTICS_PROTOCOL" \
  --analysis-lock "$FREDDIE_ANALYSIS_INPUT_LOCK" \
  --data-mart-dir "$FREDDIE_DATA_MART_DIR" \
  --metric-dir "$FREDDIE_METRIC_DIR" \
  --stat-dir "$FREDDIE_STAT_DIR" \
  --output "$FREDDIE_DIAGNOSTICS_LOCK"
