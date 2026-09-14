#!/usr/bin/env bash
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
source "$ROOT/scripts/research/freddie_m24_m26_common_0026.sh"
freddie_m24_m26_paths "$ROOT"
m24_m26_assert_no_provider_execution
PROTOCOL="$ROOT/config/research/replication/multidataset_replication_v1.json"
m24_m26_require_file "$MULTIDATASET_M25_LOCK"
PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" \
python3 "$ROOT/scripts/research/multidataset_m25_replication_0029.py" \
  --repo-root "$ROOT" --lock "$MULTIDATASET_M25_LOCK" --protocol "$PROTOCOL" --output-dir "$MULTIDATASET_M25_DIR"
