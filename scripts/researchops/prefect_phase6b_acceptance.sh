#!/usr/bin/env bash
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
cd "$ROOT"
PYTHON="${RESEARCHOPS_PYTHON:-$ROOT/.venv/bin/python3}"
REPORT_DIR="${RESEARCHOPS_PREFECT_PHASE6B_DIR:-/tmp/researchops-prefect-phase6b}"
mkdir -p "$REPORT_DIR"

[[ -x "$PYTHON" ]] || { echo "ERROR: missing Python: $PYTHON" >&2; exit 2; }

"$PYTHON" -m research.python.researchops.contracts validate \
  > "$REPORT_DIR/governance-contracts.txt"
"$PYTHON" -m research.python.researchops.stage_registry validate \
  > "$REPORT_DIR/stage-registry-validation.txt"
"$PYTHON" -m research.python.researchops.stage_registry coverage \
  > "$REPORT_DIR/stage-registry-coverage.txt"
"$PYTHON" -m research.python.researchops.stage_registry compile --check \
  > "$REPORT_DIR/stage-registry-lock.txt"

"$PYTHON" -m research.python.researchops.orchestration.flow_catalog validate \
  --report-path "$REPORT_DIR/flow-catalog-validation.json" >/dev/null
"$PYTHON" -m research.python.researchops.orchestration.flow_catalog coverage \
  --report-path "$REPORT_DIR/flow-catalog-coverage.json" >/dev/null
"$PYTHON" -m research.python.researchops.orchestration.flow_catalog compile --check \
  --report-path "$REPORT_DIR/flow-catalog-lock.json" >/dev/null

"$PYTHON" - "$REPORT_DIR/flow-catalog-validation.json" \
  "$REPORT_DIR/flow-catalog-coverage.json" \
  "$REPORT_DIR/flow-catalog-lock.json" <<'PY'
import json
import sys

validation = json.load(open(sys.argv[1], encoding="utf-8"))
coverage = json.load(open(sys.argv[2], encoding="utf-8"))
lock = json.load(open(sys.argv[3], encoding="utf-8"))
assert validation["passed"] is True, validation
assert validation["flow_count"] == 9, validation
assert validation["stage_count"] == 36, validation
assert validation["covered_stage_count"] == 36, validation
assert validation["missing_stage_ids"] == [], validation
assert validation["unknown_stage_ids"] == [], validation
assert coverage["passed"] is True, coverage
assert lock["passed"] is True, lock
print("FLOW_CATALOG_VALID=PASS")
print("FLOW_CATALOG_ACYCLIC=PASS")
print("FLOW_STAGE_COVERAGE=PASS")
print("FLOW_CONTRACT_COMPATIBILITY=PASS")
print("FLOW_APPROVAL_QUEUE_POLICY=PASS")
print("FLOW_CATALOG_LOCK_CURRENT=PASS")
PY

"$PYTHON" -m pytest -q tests/research/python/researchops/orchestration
"$PYTHON" -m pytest -q tests/research/python/researchops
"$PYTHON" -m compileall -q research/python/researchops
bash -n scripts/researchops/prefect_phase6a_acceptance.sh
bash -n scripts/researchops/prefect_phase6b_acceptance.sh
git diff --check

echo "PHASE_6B_FLOW_CATALOG=COMPLETE"
echo "Reports: $REPORT_DIR"
