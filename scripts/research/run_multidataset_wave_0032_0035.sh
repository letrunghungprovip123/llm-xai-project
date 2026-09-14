#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

bash "$ROOT/scripts/research/run_multidataset_m27a_robustness_input_lock_0032.sh" "$ROOT"
bash "$ROOT/scripts/research/run_multidataset_m27b_robustness_0033.sh" "$ROOT"
bash "$ROOT/scripts/research/run_multidataset_m28a_analytical_release_input_lock_0034.sh" "$ROOT"
bash "$ROOT/scripts/research/run_multidataset_m28b_analytical_release_0035.sh" "$ROOT"

echo "MULTIDATASET_M27_M28_0032_0035=PASS"
