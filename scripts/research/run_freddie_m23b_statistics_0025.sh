#!/usr/bin/env bash
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
source "$ROOT/scripts/research/freddie_m21_m23_common_0020.sh"
freddie_analysis_paths "$ROOT"
freddie_assert_no_provider_execution
LOCK="$FREDDIE_ANALYSIS_ROOT/statistical_input_lock_v1/freddie_statistical_input_lock.json"
PROTOCOL="$ROOT/config/research/replication/freddie_sflld_2024_statistical_v1.json"
freddie_require_file "$LOCK"
PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 "$ROOT/scripts/research/freddie_m23_statistics_0025.py" \
 --repo-root "$ROOT" --stat-lock "$LOCK" --protocol "$PROTOCOL" --output-dir "$FREDDIE_STAT_DIR"
