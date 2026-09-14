#!/usr/bin/env bash
set -euo pipefail

# shellcheck source=freddie_m18_m20_common_0014.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/freddie_m18_m20_common_0014.sh"

freddie_analysis_paths() {
  local root="$1"
  freddie_paths "$root"
  FREDDIE_ANALYSIS_PROTOCOL="$root/config/research/replication/freddie_sflld_2024_analysis_v1.json"
  FREDDIE_REPLICATION_ROOT="${FREDDIE_FINALIZATION_ROOT%/claim_finalization}"
  FREDDIE_ANALYSIS_ROOT="$FREDDIE_REPLICATION_ROOT/analysis"
  FREDDIE_ANALYSIS_INPUT_LOCK_DIR="$FREDDIE_ANALYSIS_ROOT/input_lock_v1"
  FREDDIE_ANALYSIS_INPUT_LOCK="$FREDDIE_ANALYSIS_INPUT_LOCK_DIR/freddie_analysis_input_lock.json"
  FREDDIE_DATA_MART_DIR="$FREDDIE_ANALYSIS_ROOT/data_mart_v1"
  FREDDIE_METRIC_DIR="$FREDDIE_ANALYSIS_ROOT/metric_v1"
  FREDDIE_STAT_DIR="$FREDDIE_ANALYSIS_ROOT/statistical_analysis_v1"
  FREDDIE_CLAIMS_V3="$FREDDIE_SEMANTIC_V3_DIR/claims_final.jsonl"
  FREDDIE_VALIDATION_RESULTS="$FREDDIE_VALIDATION_OUT_DIR/claim_validation_results.jsonl"
  FREDDIE_GENERATION_SUMMARIES="$FREDDIE_VALIDATION_OUT_DIR/generation_validation_summary.jsonl"
  FREDDIE_VALIDATION_MANIFEST="$FREDDIE_VALIDATION_OUT_DIR/claim_validation_manifest.json"
  FREDDIE_M20_INPUT_LOCK="$FREDDIE_VALIDATION_LOCK_DIR/freddie_validation_input_lock.json"
}
