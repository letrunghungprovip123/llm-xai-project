#!/usr/bin/env bash
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
cd "$ROOT"
PYTHON="$ROOT/.venv/bin/python3"
REPORT_DIR="${RESEARCHOPS_MLFLOW_CURRENT_STATE_DIR:-/tmp/researchops-mlflow-phase5-current-state}"
SOURCE_ARTIFACT_ID="${RESEARCHOPS_PHASE5_SOURCE_ARTIFACT_ID:-}"

[[ -x "$PYTHON" ]] || { echo "ERROR: missing $PYTHON" >&2; exit 2; }
[[ -n "$SOURCE_ARTIFACT_ID" ]] || {
  echo "ERROR: set RESEARCHOPS_PHASE5_SOURCE_ARTIFACT_ID to the accepted trained-model artifact." >&2
  exit 2
}
mkdir -p "$REPORT_DIR"

for file in .env.researchops-storage.local .env.researchops-db.local .env.researchops-mlflow.local; do
  [[ -f "$file" ]] || { echo "ERROR: missing $file" >&2; exit 2; }
  set -a
  # shellcheck disable=SC1090
  source "$file"
  set +a
done

"$PYTHON" -m research.python.researchops.mlflow_tracking health \
  --report-path "$REPORT_DIR/health.json" >/dev/null
"$PYTHON" -m research.python.researchops.mlflow_tracking inspect-training-release \
  --artifact-profile development-minio \
  --artifact-id "$SOURCE_ARTIFACT_ID" \
  --report-path "$REPORT_DIR/source.json" >/dev/null

env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
  "$PYTHON" -m research.python.researchops.mlflow_tracking register-training-release \
  --artifact-profile development-minio \
  --artifact-id "$SOURCE_ARTIFACT_ID" \
  --report-path "$REPORT_DIR/register-first.json" >/dev/null

env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
  "$PYTHON" -m research.python.researchops.mlflow_tracking register-training-release \
  --artifact-profile development-minio \
  --artifact-id "$SOURCE_ARTIFACT_ID" \
  --report-path "$REPORT_DIR/register-second.json" >/dev/null

"$PYTHON" - "$REPORT_DIR/register-first.json" "$REPORT_DIR/register-second.json" <<'PY'
import json, sys
first=json.load(open(sys.argv[1], encoding="utf-8"))
second=json.load(open(sys.argv[2], encoding="utf-8"))
assert first["tracking"]["parent_run_id"] == second["tracking"]["parent_run_id"]
assert first["receipt_artifact_id"] == second["receipt_artifact_id"]
assert first["registry"]["candidate_version"] == second["registry"]["candidate_version"]
assert all(item["reused"] for item in second["tracking"]["models"])
assert all(item["reused"] for item in second["registry"]["versions"])
assert second["receipt_reused"] is True
for item in second["tracking"]["models"]:
    assert item["model_uri"].startswith("models:/m-"), item
print("MLFLOW_CURRENT_STATE_IDEMPOTENCY=PASS")
print("MLFLOW_CURRENT_STATE_CANONICAL_MODEL_URI=PASS")
PY

env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
  "$PYTHON" -m research.python.researchops.mlflow_tracking reconcile \
  --artifact-profile development-minio \
  --mode report-only \
  --report-path "$REPORT_DIR/reconciliation.json" >/dev/null

"$PYTHON" - "$REPORT_DIR/reconciliation.json" <<'PY'
import json, sys
report=json.load(open(sys.argv[1], encoding="utf-8"))
assert report["passed"] is True, report
print("MLFLOW_CURRENT_STATE_RECONCILIATION=PASS")
PY

echo "PHASE_5_CURRENT_STATE_ACCEPTANCE=PASS"
