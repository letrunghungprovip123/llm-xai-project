#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-$(pwd)}"; cd "$ROOT"
exec python scripts/research/run_multidataset_m30c_effectiveness_mechanisms_0040.py
