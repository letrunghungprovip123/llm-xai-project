#!/usr/bin/env bash
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
"$ROOT/scripts/research/run_freddie_m24a_diagnostics_input_lock_0026.sh"
"$ROOT/scripts/research/run_freddie_m24b_diagnostics_0027.sh"
"$ROOT/scripts/research/run_multidataset_m25a_input_lock_0028.sh"
"$ROOT/scripts/research/run_multidataset_m25b_replication_0029.sh"
"$ROOT/scripts/research/run_multidataset_m26a_policy_lock_0030.sh"
"$ROOT/scripts/research/run_multidataset_m26b_decision_0031.sh"
echo "FREDDIE_MULTIDATASET_M24_M26_0026_0031=PASS"
