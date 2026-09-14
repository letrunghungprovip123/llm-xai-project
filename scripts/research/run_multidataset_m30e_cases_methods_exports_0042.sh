#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-$(pwd)}"; cd "$ROOT"
exec python scripts/research/run_multidataset_m30e_cases_methods_exports_0042.py
