#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-$(pwd)}"
cd "$ROOT"
exec python scripts/research/run_multidataset_m30f_final_certification_0043.py "${@:2}"
