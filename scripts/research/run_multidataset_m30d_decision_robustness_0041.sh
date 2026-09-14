#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-$(pwd)}"; cd "$ROOT"
exec python scripts/research/run_multidataset_m30d_decision_robustness_0041.py
