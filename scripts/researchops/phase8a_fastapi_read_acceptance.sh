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
"$PYTHON" -m research.python.researchops.orchestration.prefect_adapter.deployment_cli compile-check
"$PYTHON" -m pytest -q \
  tests/research/python/researchops/control_plane/test_api_read.py \
  tests/research/python/researchops/control_plane/test_auth.py \
  tests/research/python/researchops/control_plane/test_openapi.py \
  tests/research/python/researchops/control_plane/test_live_postgresql_api.py::test_live_postgresql_read_control_plane

echo "FASTAPI_READ_MODEL=PASS"
echo "CURSOR_PAGINATION=PASS"
echo "OPENAPI_READ_CONTRACT=PASS"
echo "API_ERROR_CONTRACT=PASS"
echo "API_SECRET_REDACTION=PASS"
echo "CONTROL_PLANE_READINESS=PASS"
echo "PHASE_8A_FASTAPI_READ_API=COMPLETE"
