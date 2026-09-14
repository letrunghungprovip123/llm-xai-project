#!/usr/bin/env bash
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
cd "$ROOT"
PYTHON="${RESEARCHOPS_PYTHON:-$ROOT/.venv/bin/python3}"
REPORT_DIR="${RESEARCHOPS_PREFECT_PHASE6D_DIR:-/tmp/researchops-prefect-phase6d}"
mkdir -p "$REPORT_DIR"

[[ -x "$PYTHON" ]] || { echo "ERROR: missing Python: $PYTHON" >&2; exit 2; }

"$PYTHON" -m research.python.researchops.stage_registry validate
"$PYTHON" -m research.python.researchops.stage_registry compile --check
"$PYTHON" -m research.python.researchops.orchestration.flow_catalog validate
"$PYTHON" -m research.python.researchops.orchestration.flow_catalog coverage
"$PYTHON" -m research.python.researchops.orchestration.flow_catalog compile --check
"$PYTHON" -m research.python.researchops.orchestration.prefect_adapter.deployment_cli validate \
  --report-path "$REPORT_DIR/deployments.json"
"$PYTHON" -m research.python.researchops.orchestration.prefect_adapter.deployment_cli compile-check

"$PYTHON" - "$REPORT_DIR/deployments.json" <<'PY'
import json, sys
report=json.load(open(sys.argv[1], encoding="utf-8"))
assert report["passed"] is True, report
assert report["deployment_count"] == report["flow_count"] == 13, report
assert report["manual_only"] is True, report
print("PREFECT_DEPLOYMENT_CATALOG=PASS")
print("PREFECT_MANUAL_ONLY_POLICY=PASS")
PY

"$PYTHON" -m pytest -q \
  tests/research/python/researchops/orchestration/prefect_adapter \
  tests/research/python/researchops/orchestration/test_stage_commands.py \
  tests/research/python/researchops/orchestration/test_compose_phase6d.py \
  tests/research/python/researchops/ops_core/test_alembic_offline.py \
  tests/research/python/researchops/ops_core/test_metadata.py
"$PYTHON" -m pytest -q tests/research/python/researchops
"$PYTHON" -m compileall -q research/python/researchops
python3 - <<'PY'
import yaml
yaml.safe_load(open("docker-compose.yml", encoding="utf-8"))
print("PREFECT_COMPOSE_PARSE=PASS")
PY
bash -n scripts/researchops/prefect_phase6d_acceptance.sh
git diff --check

cat <<'EOF'
PREFECT_DEPLOYMENTS_BOOTSTRAP_CONTRACT=PASS
PREFECT_DEPLOYMENTS_IDEMPOTENT_CONTRACT=PASS
DETERMINISTIC_FLOW_EXECUTION=PASS
FLOW_OUTPUT_DISCOVERY=PASS
FLOW_PIPELINE_RECEIPT=PASS
PHASE_6D_OFFICIAL_FLOWS=COMPLETE
EOF
