#!/usr/bin/env bash
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
source "$ROOT/scripts/research/freddie_m21_m23_common_0020.sh"
freddie_analysis_paths "$ROOT"
freddie_assert_no_provider_execution
"$ROOT/scripts/research/run_freddie_m21a_input_lock_0020.sh"
"$ROOT/scripts/research/run_freddie_m21_data_mart_0021.sh"
"$ROOT/scripts/research/run_freddie_m22a_metric_input_lock_0022.sh"
"$ROOT/scripts/research/run_freddie_m22b_metrics_0023.sh"
"$ROOT/scripts/research/run_freddie_m23a_statistical_input_lock_0024.sh"
"$ROOT/scripts/research/run_freddie_m23b_statistics_0025.sh"
echo "FREDDIE_M21_M23_0020_0025=PASS"
