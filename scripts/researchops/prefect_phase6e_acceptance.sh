#!/usr/bin/env bash
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
cd "$ROOT"
PYTHON="${RESEARCHOPS_PYTHON:-$ROOT/.venv/bin/python3}"
REPORT_DIR="${RESEARCHOPS_PREFECT_PHASE6E_DIR:-/tmp/researchops-prefect-phase6e}"
mkdir -p "$REPORT_DIR"
[[ -x "$PYTHON" ]] || { echo "ERROR: missing Python: $PYTHON" >&2; exit 2; }

"$PYTHON" -m alembic upgrade head --sql > "$REPORT_DIR/alembic-head.sql"
grep -Fq 'pipeline_run_receipts' "$REPORT_DIR/alembic-head.sql"
grep -Fq 'request_key' "$REPORT_DIR/alembic-head.sql"

"$PYTHON" -m pytest -q \
  tests/research/python/researchops/orchestration/approvals \
  tests/research/python/researchops/orchestration/reconciliation \
  tests/research/python/researchops/orchestration/prefect_adapter \
  tests/research/python/researchops/orchestration/test_phase6e_schemas.py \
  tests/research/python/researchops/orchestration/ops_bridge \
  tests/research/python/researchops/ops_core/test_alembic_offline.py \
  tests/research/python/researchops/ops_core/test_metadata.py \
  tests/research/python/researchops/ops_core/test_transitions.py
"$PYTHON" -m pytest -q tests/research/python/researchops
"$PYTHON" -m compileall -q research/python/researchops
for script in scripts/researchops/prefect_phase6*.sh; do bash -n "$script"; done
git diff --check

cat <<'EOF'
PREFECT_APPROVAL_REQUEST_IDEMPOTENCY=PASS
PREFECT_APPROVAL_SCOPE=PASS
PREFECT_APPROVAL_REJECTION=PASS
PREFECT_APPROVAL_EXPIRY=PASS
PREFECT_SUSPEND_RESUME_CONTRACT=PASS
PREFECT_OPS_RECONCILIATION_REPORT_ONLY=PASS
PREFECT_OPS_RECONCILIATION_REPAIR_SAFE=PASS
PHASE_6E_APPROVAL_RECONCILIATION=COMPLETE
EOF
