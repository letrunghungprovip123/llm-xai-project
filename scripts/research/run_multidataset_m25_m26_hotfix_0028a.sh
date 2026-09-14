#!/usr/bin/env bash
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
source "$ROOT/scripts/research/freddie_m24_m26_common_0026.sh"
freddie_m24_m26_paths "$ROOT"
m24_m26_assert_no_provider_execution

"$ROOT/scripts/research/run_multidataset_m25a_input_lock_0028.sh"
"$ROOT/scripts/research/run_multidataset_m25b_replication_0029.sh"
"$ROOT/scripts/research/run_multidataset_m26a_policy_lock_0030.sh"
"$ROOT/scripts/research/run_multidataset_m26b_decision_0031.sh"

echo "MULTIDATASET_M25_M26_HOTFIX_0028A=PASS"
echo "MULTIDATASET_M24_M26_0026_0031=PASS"
