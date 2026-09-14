#!/usr/bin/env bash
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
cd "$ROOT"
PYTHON="${RESEARCHOPS_PYTHON:-$ROOT/.venv/bin/python3}"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="${PYTHON_FALLBACK:-python3}"
fi

"$PYTHON" -m research.python.researchops.promotion validate-policies >/dev/null
"$PYTHON" -m research.python.researchops.contracts validate >/dev/null
"$PYTHON" -m pytest -q \
  tests/research/python/researchops/promotion \
  tests/research/python/researchops/mlflow_tracking/test_promotion.py \
  tests/research/python/researchops/ops_core/test_release_promotion.py \
  tests/research/python/researchops/ops_core/test_alembic_offline.py

echo "REQUIRED_GATE_SET_ENFORCEMENT=PASS"
echo "MISSING_GATE_BLOCKS_PROMOTION=PASS"
echo "WAIVER_POLICY=PASS"
echo "NON_WAIVABLE_GATE_POLICY=PASS"
echo "MODEL_PROMOTION_POLICY=PASS"
echo "RELEASE_PROMOTION_POLICY=PASS"
echo "PHASE_7_QUALITY_GATES=COMPLETE"
