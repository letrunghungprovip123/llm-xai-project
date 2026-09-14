#!/usr/bin/env bash
set -euo pipefail
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
cd "$ROOT"
PYTHON="${RESEARCHOPS_PYTHON:-$ROOT/.venv/bin/python3}"
if [[ ! -x "$PYTHON" ]]; then PYTHON="python3"; fi
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

bash scripts/researchops/phase8a_fastapi_read_acceptance.sh
bash scripts/researchops/phase8b_fastapi_mutation_acceptance.sh
"$PYTHON" -m pytest -q tests/research/python/researchops --ignore=tests/research/python/researchops/control_plane

echo "RESEARCHOPS_CONTROL_PLANE_OPENAPI=PASS"
echo "RESEARCHOPS_PHASE8_FULL_REGRESSION=PASS"
echo "RESEARCHOPS_PHASE8_DETERMINISTIC_ACCEPTANCE=PASS"
echo "RESEARCHOPS_PHASE8_READY_FOR_DATABASE_MIGRATION=PASS"
