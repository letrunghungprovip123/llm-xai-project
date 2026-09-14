#!/usr/bin/env bash
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
cd "$ROOT"
PYTHON="${RESEARCHOPS_PYTHON:-$ROOT/.venv/bin/python3}"
REPORT_DIR="${RESEARCHOPS_PREFECT_PHASE6C_DIR:-/tmp/researchops-prefect-phase6c}"
mkdir -p "$REPORT_DIR"

[[ -x "$PYTHON" ]] || { echo "ERROR: missing Python: $PYTHON" >&2; exit 2; }

"$PYTHON" -m research.python.researchops.orchestration validate-execution-contracts \
  --report-path "$REPORT_DIR/execution-contracts.json" >/dev/null
"$PYTHON" - "$REPORT_DIR/execution-contracts.json" <<'PY'
import json
import sys
report = json.load(open(sys.argv[1], encoding="utf-8"))
assert report["passed"] is True, report
assert len(report["checked"]) == 2, report
print("STAGE_EXECUTION_CONTRACTS=PASS")
print("PIPELINE_RECEIPT_CONTRACT=PASS")
PY

"$PYTHON" -m pytest -q \
  tests/research/python/researchops/orchestration/execution \
  tests/research/python/researchops/orchestration/ops_bridge \
  tests/research/python/researchops/ops_core/test_alembic_offline.py \
  tests/research/python/researchops/ops_core/test_metadata.py
"$PYTHON" -m pytest -q tests/research/python/researchops
"$PYTHON" -m compileall -q research/python/researchops
bash -n scripts/researchops/prefect_phase6c_acceptance.sh
git diff --check

cat <<'EOF'
STAGE_EXECUTOR_NO_SHELL=PASS
ENVIRONMENT_ALLOWLIST=PASS
FLOW_IDEMPOTENCY=PASS
STAGE_IDEMPOTENCY=PASS
OPS_PREFECT_BINDING=PASS
EXECUTION_EVIDENCE=PASS
PIPELINE_RECEIPT=PASS
RETRY_CLASSIFICATION=PASS
PHASE_6C_EXECUTION_BRIDGE=COMPLETE
EOF
