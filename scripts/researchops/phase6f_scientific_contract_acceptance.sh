#!/usr/bin/env bash
set -euo pipefail
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
cd "$ROOT"
PYTHON="${RESEARCHOPS_PYTHON:-$ROOT/.venv/bin/python3}"
if [[ ! -x "$PYTHON" ]]; then PYTHON=python3; fi

"$PYTHON" -m research.python.researchops.stage_registry validate
"$PYTHON" -m research.python.researchops.stage_registry compile --check
"$PYTHON" -m research.python.researchops.orchestration.flow_catalog validate
"$PYTHON" -m research.python.researchops.orchestration.flow_catalog compile --check
"$PYTHON" -m research.python.researchops.orchestration.prefect_adapter.deployment_cli compile-check
"$PYTHON" -m pytest -q \
  tests/research/python/researchops/stage_registry \
  tests/research/python/researchops/orchestration/execution \
  tests/research/python/researchops/orchestration/test_scientific_contract_closure.py

echo "SCIENTIFIC_STAGE_COMMAND_CONTRACTS=PASS"
echo "SCIENTIFIC_OUTPUT_DISCOVERY_CONTRACTS=PASS"
echo "SCIENTIFIC_GATE_REPORT_BINDINGS=PASS"
echo "BLOCKED_STAGE_NONZERO_EXIT=PASS"
echo "SCIENTIFIC_FLOW_FIXTURE_ACCEPTANCE=PASS"
echo "PHASE_6F_SCIENTIFIC_CONTRACT_CLOSURE=COMPLETE"
