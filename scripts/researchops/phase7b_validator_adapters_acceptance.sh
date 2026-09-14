#!/usr/bin/env bash
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
cd "$ROOT"
PYTHON="${RESEARCHOPS_PYTHON:-$ROOT/.venv/bin/python3}"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="${PYTHON:-python3}"
fi

"$PYTHON" -m pytest -q \
  tests/research/python/researchops/gates/test_adapters.py \
  tests/research/python/researchops/gates/test_orchestration.py

echo "LEGACY_VALIDATOR_ADAPTERS=PASS"
echo "FAILED_GATE_EVIDENCE_PERSISTENCE=PASS"
echo "ARTIFACT_GATE_PROJECTION=PASS"
echo "MODEL_VERSION_GATE_PROJECTION=PASS"
echo "RELEASE_GATE_PROJECTION=PASS"
echo "PHASE_7B_VALIDATOR_ADAPTERS=COMPLETE"
