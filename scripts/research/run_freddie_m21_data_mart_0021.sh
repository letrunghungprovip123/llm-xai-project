#!/usr/bin/env bash
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
source "$ROOT/scripts/research/freddie_m21_m23_common_0020.sh"
freddie_analysis_paths "$ROOT"
freddie_assert_no_provider_execution
freddie_require_file "$FREDDIE_ANALYSIS_INPUT_LOCK"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
python3 "$ROOT/scripts/research/freddie_m21_data_mart_0021.py" \
  --repo-root "$ROOT" \
  --protocol "$FREDDIE_ANALYSIS_PROTOCOL" \
  --input-lock "$FREDDIE_ANALYSIS_INPUT_LOCK" \
  --output-dir "$FREDDIE_DATA_MART_DIR"
