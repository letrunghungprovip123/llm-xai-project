#!/usr/bin/env bash
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
"$ROOT/scripts/research/run_freddie_m18a_offline_freeze_0014.sh"
"$ROOT/scripts/research/run_freddie_m18b_offline_replay_0015.sh"
"$ROOT/scripts/research/run_freddie_m19a_finalization_preflight_0016.sh"
"$ROOT/scripts/research/run_freddie_m19b_finalization_0017.sh"
"$ROOT/scripts/research/run_freddie_m20a_validation_input_lock_0018.sh"
"$ROOT/scripts/research/run_freddie_m20_validation_0019.sh"
echo "FREDDIE_M18_M20_0014_0019=PASS"
