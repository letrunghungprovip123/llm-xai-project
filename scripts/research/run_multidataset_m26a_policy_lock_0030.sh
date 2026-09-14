#!/usr/bin/env bash
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
source "$ROOT/scripts/research/freddie_m24_m26_common_0026.sh"
freddie_m24_m26_paths "$ROOT"
m24_m26_assert_no_provider_execution
POLICY="$ROOT/config/research/replication/multidataset_decision_policy_v1.json"
for file in "$POLICY" "$MULTIDATASET_M25_LOCK" "$MULTIDATASET_M25_DIR/replication_manifest.json"; do m24_m26_require_file "$file"; done
mkdir -p "$MULTIDATASET_M26_POLICY_LOCK_DIR"
PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" \
python3 "$ROOT/scripts/research/multidataset_m26_policy_lock_0030.py" \
  --repo-root "$ROOT" --policy "$POLICY" --m25-lock "$MULTIDATASET_M25_LOCK" --m25-dir "$MULTIDATASET_M25_DIR" --output "$MULTIDATASET_M26_POLICY_LOCK"
