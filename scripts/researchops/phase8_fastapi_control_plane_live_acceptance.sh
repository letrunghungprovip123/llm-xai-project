#!/usr/bin/env bash
set -euo pipefail
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
cd "$ROOT"
PYTHON="${RESEARCHOPS_PYTHON:-$ROOT/.venv/bin/python3}"
ALEMBIC="${RESEARCHOPS_ALEMBIC:-$ROOT/.venv/bin/alembic}"
if [[ ! -x "$PYTHON" ]]; then PYTHON="python3"; fi
if [[ ! -x "$ALEMBIC" ]]; then ALEMBIC="alembic"; fi
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

if [[ -z "${RESEARCHOPS_DATABASE_URL:-}" ]]; then
  echo "ERROR: RESEARCHOPS_DATABASE_URL is required" >&2
  exit 2
fi
export RESEARCHOPS_TEST_DATABASE_URL="${RESEARCHOPS_TEST_DATABASE_URL:-$RESEARCHOPS_DATABASE_URL}"

"$ALEMBIC" upgrade head
CURRENT="$($ALEMBIC current | tail -n 1)"
if [[ "$CURRENT" != *"0008_control_plane_operations"* ]]; then
  echo "ERROR: expected Alembic head 0008_control_plane_operations, observed: $CURRENT" >&2
  exit 1
fi

bash scripts/researchops/phase8_fastapi_control_plane_acceptance.sh
"$PYTHON" -m pytest -q tests/research/python/researchops/control_plane/test_live_postgresql_api.py

echo "RESEARCHOPS_PHASE8_DATABASE_MIGRATION=PASS"
echo "RESEARCHOPS_CONTROL_PLANE_LIVE_ACCEPTANCE=PASS"
echo "RESEARCHOPS_PHASE8_CONTROL_PLANE=COMPLETE"
