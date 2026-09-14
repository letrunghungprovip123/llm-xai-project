#!/usr/bin/env bash
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
source "$ROOT/scripts/research/freddie_m21_m23_common_0020.sh"
freddie_analysis_paths "$ROOT"
freddie_assert_no_provider_execution
PROTOCOL="$ROOT/config/research/replication/freddie_sflld_2024_statistical_v1.json"
LOCK_DIR="$FREDDIE_ANALYSIS_ROOT/statistical_input_lock_v1"
LOCK="$LOCK_DIR/freddie_statistical_input_lock.json"
freddie_require_file "$FREDDIE_METRIC_DIR/metric_manifest.json"
freddie_require_file "$FREDDIE_ANALYSIS_INPUT_LOCK"
mkdir -p "$LOCK_DIR"
PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 "$ROOT/scripts/research/freddie_statistical_input_lock_0024.py" \
 --repo-root "$ROOT" --analysis-lock "$FREDDIE_ANALYSIS_INPUT_LOCK" --metric-dir "$FREDDIE_METRIC_DIR" --protocol "$PROTOCOL" --data-mart-dir "$FREDDIE_DATA_MART_DIR" --output "$LOCK"
