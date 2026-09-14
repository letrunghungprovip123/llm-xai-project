#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=freddie_m24_m26_common_0026.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/freddie_m24_m26_common_0026.sh"

multidataset_m27_m28_paths() {
  local root="$1"
  freddie_m24_m26_paths "$root"
  MULTIDATASET_M27_PROTOCOL="$root/config/research/replication/multidataset_robustness_v1.json"
  MULTIDATASET_M27_LOCK_DIR="$MULTIDATASET_ANALYSIS_ROOT/m27_robustness_input_lock_v1"
  MULTIDATASET_M27_LOCK="$MULTIDATASET_M27_LOCK_DIR/multidataset_robustness_input_lock.json"
  MULTIDATASET_M27_DIR="$MULTIDATASET_ANALYSIS_ROOT/robustness_v1"
  MULTIDATASET_M28_PROTOCOL="$root/config/research/replication/multidataset_analytical_release_v1.json"
  MULTIDATASET_M28_LOCK_DIR="$MULTIDATASET_ANALYSIS_ROOT/m28_analytical_release_input_lock_v1"
  MULTIDATASET_M28_LOCK="$MULTIDATASET_M28_LOCK_DIR/multidataset_analytical_release_input_lock.json"
  MULTIDATASET_M28_DIR="$MULTIDATASET_ANALYSIS_ROOT/certified_analytical_release_v1"
}
