#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=freddie_m21_m23_common_0020.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/freddie_m21_m23_common_0020.sh"

freddie_m24_m26_paths() {
  local root="$1"
  freddie_analysis_paths "$root"
  FREDDIE_DIAGNOSTICS_PROTOCOL="$root/config/research/replication/freddie_sflld_2024_diagnostics_v1.json"
  FREDDIE_DIAGNOSTICS_LOCK_DIR="$FREDDIE_ANALYSIS_ROOT/diagnostics_input_lock_v1"
  FREDDIE_DIAGNOSTICS_LOCK="$FREDDIE_DIAGNOSTICS_LOCK_DIR/freddie_diagnostics_input_lock.json"
  FREDDIE_DIAGNOSTICS_DIR="$FREDDIE_ANALYSIS_ROOT/diagnostics_v1"
  MULTIDATASET_ANALYSIS_ROOT="$root/data/reports/llm_validation/multidataset_replication_v1"
  MULTIDATASET_M25_LOCK_DIR="$MULTIDATASET_ANALYSIS_ROOT/m25_input_lock_v1"
  MULTIDATASET_M25_LOCK="$MULTIDATASET_M25_LOCK_DIR/multidataset_replication_input_lock.json"
  MULTIDATASET_M25_DIR="$MULTIDATASET_ANALYSIS_ROOT/replication_v1"
  MULTIDATASET_M26_POLICY_LOCK_DIR="$MULTIDATASET_ANALYSIS_ROOT/m26_policy_lock_v1"
  MULTIDATASET_M26_POLICY_LOCK="$MULTIDATASET_M26_POLICY_LOCK_DIR/multidataset_decision_policy_lock.json"
  MULTIDATASET_M26_DIR="$MULTIDATASET_ANALYSIS_ROOT/decision_v1"
}

m24_m26_require_file() {
  local file="$1"
  [[ -f "$file" ]] || { echo "Required file is missing: $file" >&2; return 1; }
}

m24_m26_assert_no_provider_execution() {
  freddie_assert_no_provider_execution
}
