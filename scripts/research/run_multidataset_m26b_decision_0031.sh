#!/usr/bin/env bash
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
source "$ROOT/scripts/research/freddie_m24_m26_common_0026.sh"
freddie_m24_m26_paths "$ROOT"
m24_m26_assert_no_provider_execution
m24_m26_require_file "$MULTIDATASET_M26_POLICY_LOCK"
PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" \
python3 "$ROOT/scripts/research/multidataset_m26_decision_0031.py" \
  --repo-root "$ROOT" --policy-lock "$MULTIDATASET_M26_POLICY_LOCK" --output-dir "$MULTIDATASET_M26_DIR"
