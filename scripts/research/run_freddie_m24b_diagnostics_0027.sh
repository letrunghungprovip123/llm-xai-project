#!/usr/bin/env bash
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
source "$ROOT/scripts/research/freddie_m24_m26_common_0026.sh"
freddie_m24_m26_paths "$ROOT"
m24_m26_assert_no_provider_execution
m24_m26_require_file "$FREDDIE_DIAGNOSTICS_LOCK"
PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" \
python3 "$ROOT/scripts/research/freddie_m24_diagnostics_0027.py" \
  --repo-root "$ROOT" \
  --lock "$FREDDIE_DIAGNOSTICS_LOCK" \
  --protocol "$FREDDIE_DIAGNOSTICS_PROTOCOL" \
  --output-dir "$FREDDIE_DIAGNOSTICS_DIR"
