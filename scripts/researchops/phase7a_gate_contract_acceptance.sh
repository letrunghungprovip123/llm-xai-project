#!/usr/bin/env bash
set -euo pipefail
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
cd "$ROOT"
PYTHON="${RESEARCHOPS_PYTHON:-$ROOT/.venv/bin/python3}"
if [[ ! -x "$PYTHON" ]]; then PYTHON=python3; fi

"$PYTHON" -m pytest -q \
  tests/research/python/researchops/gates \
  tests/research/python/researchops/ops_core/test_metadata.py \
  tests/research/python/researchops/ops_core/test_alembic_offline.py \
  tests/research/python/researchops/ops_core/test_alembic_config.py

echo "UNIFIED_GATE_SCHEMA=PASS"
echo "GATE_EVALUATION_IDEMPOTENCY=PASS"
echo "GATE_EVIDENCE_BINDING=PASS"
echo "GATE_CURRENT_STATE_PROJECTION=PASS"
echo "PHASE_7A_GATE_CONTRACT=COMPLETE"
