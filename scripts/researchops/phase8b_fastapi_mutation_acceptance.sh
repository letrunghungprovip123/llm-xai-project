#!/usr/bin/env bash
set -euo pipefail
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
cd "$ROOT"
PYTHON="${RESEARCHOPS_PYTHON:-$ROOT/.venv/bin/python3}"
if [[ ! -x "$PYTHON" ]]; then PYTHON="python3"; fi
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

"$PYTHON" -m research.python.researchops.control_plane.openapi check
"$PYTHON" -m research.python.researchops.contracts validate
"$PYTHON" -m research.python.researchops.stage_registry validate
"$PYTHON" -m research.python.researchops.stage_registry compile --check
"$PYTHON" -m research.python.researchops.orchestration.flow_catalog validate
"$PYTHON" -m research.python.researchops.orchestration.flow_catalog compile --check
"$PYTHON" -m research.python.researchops.orchestration.prefect_adapter.deployment_cli validate
"$PYTHON" -m research.python.researchops.orchestration.prefect_adapter.deployment_cli compile-check
"$PYTHON" -m pytest -q \
  tests/research/python/researchops/control_plane/test_api_mutations.py \
  tests/research/python/researchops/control_plane/test_openapi_mutations.py \
  tests/research/python/researchops/control_plane/test_live_postgresql_api.py::test_live_postgresql_mutation_idempotency_and_audit \
  tests/research/python/researchops/control_plane/test_prefect_gateway.py \
  tests/research/python/researchops/orchestration/ops_bridge \
  tests/research/python/researchops/orchestration/prefect_adapter/test_flow_engine.py

echo "API_AUTHENTICATION=PASS"
echo "API_AUTHORIZATION=PASS"
echo "API_MUTATION_IDEMPOTENCY=PASS"
echo "API_OPTIMISTIC_CONCURRENCY=PASS"
echo "API_AUDIT_TRAIL=PASS"
echo "ASYNC_RUN_CONTROL=PASS"
echo "APPROVAL_CONTROL_API=PASS"
echo "WAIVER_CONTROL_API=PASS"
echo "ARTIFACT_REEVALUATION_API=PASS"
echo "MODEL_PROMOTION_OPERATION=PASS"
echo "RELEASE_PROMOTION_OPERATION=PASS"
echo "PROMOTION_OPERATION_RECONCILIATION=PASS"
echo "PHASE_8B_CONTROL_ACTIONS=COMPLETE"
