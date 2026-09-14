#!/usr/bin/env bash
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
source "$ROOT/scripts/research/freddie_m24_m26_common_0026.sh"
freddie_m24_m26_paths "$ROOT"
m24_m26_assert_no_provider_execution
PROTOCOL="$ROOT/config/research/replication/multidataset_replication_v1.json"
HOME_VALIDATION_ROOT="$ROOT/data/reports/llm_validation/validation_v1"
for file in "$PROTOCOL" "$FREDDIE_ANALYSIS_INPUT_LOCK" "$FREDDIE_DIAGNOSTICS_DIR/diagnostics_manifest.json" "$HOME_VALIDATION_ROOT/canonicalization/generation_index.jsonl" "$HOME_VALIDATION_ROOT/analysis/data_mart/generation_metrics.csv" "$HOME_VALIDATION_ROOT/analysis/statistical_analysis/paired_tests.csv" "$HOME_VALIDATION_ROOT/analysis/diagnostics/diagnostic_validation.json"; do
  m24_m26_require_file "$file"
done
mkdir -p "$MULTIDATASET_M25_LOCK_DIR"
PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" \
python3 "$ROOT/scripts/research/multidataset_m25_input_lock_0028.py" \
  --repo-root "$ROOT" --protocol "$PROTOCOL" \
  --freddie-analysis-lock "$FREDDIE_ANALYSIS_INPUT_LOCK" \
  --freddie-metric-dir "$FREDDIE_METRIC_DIR" \
  --freddie-stat-dir "$FREDDIE_STAT_DIR" \
  --freddie-diagnostics-dir "$FREDDIE_DIAGNOSTICS_DIR" \
  --home-validation-root "$HOME_VALIDATION_ROOT" \
  --output "$MULTIDATASET_M25_LOCK"
