#!/usr/bin/env bash
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
cd "$ROOT"

PYTHON="$ROOT/.venv/bin/python3"
if [[ ! -x "$PYTHON" ]]; then
  echo "ERROR: missing project virtual environment: $PYTHON" >&2
  exit 2
fi
export PATH="$ROOT/.venv/bin:$PATH"

DB_ENV=".env.researchops-db.local"
STORAGE_ENV=".env.researchops-storage.local"
MLFLOW_ENV=".env.researchops-mlflow.local"
REPORT_DIR="${RESEARCHOPS_MLFLOW_ACCEPTANCE_DIR:-/tmp/researchops-mlflow-phase5}"
mkdir -p "$REPORT_DIR"

for file in "$DB_ENV" "$STORAGE_ENV"; do
  if [[ ! -f "$file" ]]; then
    echo "ERROR: missing $file; Phase 3-4 live acceptance must exist first." >&2
    exit 2
  fi
done

if [[ ! -f "$MLFLOW_ENV" ]]; then
  "$PYTHON" -m research.python.researchops.mlflow_tracking \
    init-local-env --output "$MLFLOW_ENV"
fi
chmod 600 "$MLFLOW_ENV"

for file in "$DB_ENV" "$STORAGE_ENV" "$MLFLOW_ENV"; do
  set -a
  # shellcheck disable=SC1090
  source "$file"
  set +a
done

required=(
  RESEARCHOPS_DATABASE_URL
  RESEARCHOPS_TEST_DATABASE_URL
  RESEARCHOPS_POSTGRES_USER
  RESEARCHOPS_POSTGRES_PASSWORD
  RESEARCHOPS_S3_ACCESS_KEY
  RESEARCHOPS_S3_SECRET_KEY
  MLFLOW_TRACKING_URI
  MLFLOW_BACKEND_STORE_URI
  MLFLOW_S3_BUCKET
  MLFLOW_S3_ACCESS_KEY
  MLFLOW_S3_SECRET_KEY
  MLFLOW_ARTIFACTS_DESTINATION
)
for name in "${required[@]}"; do
  [[ -n "${!name:-}" ]] || { echo "ERROR: missing $name" >&2; exit 2; }
done

case "$MLFLOW_POSTGRES_PASSWORD:$MLFLOW_S3_SECRET_KEY" in
  *change-me*|*local-password*)
    echo "ERROR: MLflow secrets still use example values." >&2
    exit 2
    ;;
esac

if git status --short --untracked-files=all | grep -F "$MLFLOW_ENV"; then
  echo "ERROR: $MLFLOW_ENV appears in Git status." >&2
  exit 2
fi

echo "============================================================"
echo "1. DETERMINISTIC PHASE 5 VALIDATION"
echo "============================================================"
"$PYTHON" -m pip check
"$PYTHON" -m research.python.researchops.mlflow_tracking validate-contracts \
  --report-path "$REPORT_DIR/contracts.json" \
  | tee "$REPORT_DIR/contracts.log"
"$PYTHON" -m research.python.researchops.stage_registry validate
"$PYTHON" -m research.python.researchops.stage_registry coverage
"$PYTHON" -m research.python.researchops.stage_registry compile --check
"$PYTHON" -m pytest -q tests/research/python/researchops/mlflow_tracking

docker compose --profile researchops-mlflow config \
  > "$REPORT_DIR/docker-compose-mlflow.yml"
grep -Fq "researchops-mlflow:" "$REPORT_DIR/docker-compose-mlflow.yml"
echo "MLFLOW_COMPOSE_CONFIG=PASS"

echo
echo "============================================================"
echo "2. START POSTGRESQL, MINIO, MIGRATION AND MLFLOW"
echo "============================================================"
scripts/researchops/mlflow_local.sh up

for attempt in $(seq 1 90); do
  status="$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' \
    llm-xai-researchops-mlflow 2>/dev/null || true)"
  echo "MLflow health: $status"
  [[ "$status" == "healthy" ]] && break
  sleep 2
done
[[ "${status:-}" == "healthy" ]] || {
  docker compose --profile researchops-mlflow logs --tail=250 researchops-mlflow
  exit 1
}
echo "MLFLOW_CONTAINER_HEALTH=PASS"

docker inspect --format='{{.State.ExitCode}}' llm-xai-researchops-mlflow-db-init | grep -Fxq 0
docker inspect --format='{{.State.ExitCode}}' llm-xai-researchops-mlflow-minio-init | grep -Fxq 0
docker inspect --format='{{.State.ExitCode}}' llm-xai-researchops-mlflow-migrate | grep -Fxq 0
echo "MLFLOW_BOOTSTRAP_CONTAINERS=PASS"

docker exec llm-xai-researchops-mlflow python - <<'PY'
from mlflow.store.model_registry.sqlalchemy_store import SqlAlchemyStore

assert getattr(
    SqlAlchemyStore,
    "_researchops_postgresql_model_version_compat_v1",
    False,
), "MLflow PostgreSQL model-version compatibility shim is not active"
print("MLFLOW_POSTGRES_MODEL_VERSION_COMPAT=PASS")
PY

echo
echo "============================================================"
echo "3. VERSION, DATABASE AND BUCKET ACCEPTANCE"
echo "============================================================"
"$PYTHON" -m research.python.researchops.mlflow_tracking health \
  --report-path "$REPORT_DIR/version.json" \
  | tee "$REPORT_DIR/version.log"

VERSION_PASSED="$("$PYTHON" - "$REPORT_DIR/version.json" <<'PY'
import json, sys
p=json.load(open(sys.argv[1]))
assert p["passed"] is True, p
assert p["expected_version"] == p["client_version"] == p["server_version"] == "3.14.0", p
print("PASS")
PY
)"
[[ "$VERSION_PASSED" == "PASS" ]]
echo "MLFLOW_VERSION_MATCH=PASS"

MLFLOW_TABLE_COUNT="$(
  docker exec -e PGPASSWORD="$MLFLOW_POSTGRES_PASSWORD" \
    llm-xai-researchops-postgres psql \
    -U "$MLFLOW_POSTGRES_USER" -d "$MLFLOW_POSTGRES_DB" -tAc \
    "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';" \
  | tr -d '[:space:]'
)"
[[ "$MLFLOW_TABLE_COUNT" =~ ^[0-9]+$ ]] && (( MLFLOW_TABLE_COUNT > 10 ))
echo "MLFLOW_DATABASE_TABLE_COUNT=$MLFLOW_TABLE_COUNT"
echo "MLFLOW_DATABASE_MIGRATION=PASS"

"$PYTHON" - <<'PY'
import os

import boto3
from botocore.exceptions import ClientError

endpoint_url = "http://127.0.0.1:9000"
region_name = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
bucket = os.environ["MLFLOW_S3_BUCKET"]

# Bucket configuration is a control-plane concern. Verify versioning with the
# existing ResearchOps MinIO administrator credentials rather than expanding
# the runtime MLflow user's least-privilege policy.
admin_client = boto3.client(
    "s3",
    endpoint_url=endpoint_url,
    aws_access_key_id=os.environ["RESEARCHOPS_S3_ACCESS_KEY"],
    aws_secret_access_key=os.environ["RESEARCHOPS_S3_SECRET_KEY"],
    region_name=region_name,
)
versioning = admin_client.get_bucket_versioning(Bucket=bucket)
assert versioning.get("Status") == "Enabled", versioning
print("MLFLOW_BUCKET_VERSIONING=PASS")

# Runtime data-plane operations must succeed with only the bucket-scoped
# MLflow credentials.
scoped_client = boto3.client(
    "s3",
    endpoint_url=endpoint_url,
    aws_access_key_id=os.environ["MLFLOW_S3_ACCESS_KEY"],
    aws_secret_access_key=os.environ["MLFLOW_S3_SECRET_KEY"],
    region_name=region_name,
)
key = "acceptance/scoped-client-probe.txt"
scoped_client.put_object(Bucket=bucket, Key=key, Body=b"phase5")
assert scoped_client.get_object(Bucket=bucket, Key=key)["Body"].read() == b"phase5"
scoped_client.delete_object(Bucket=bucket, Key=key)
print("MLFLOW_BUCKET_RW=PASS")

try:
    scoped_client.list_objects_v2(
        Bucket=os.environ["RESEARCHOPS_S3_BUCKET"],
        MaxKeys=1,
    )
except ClientError as error:
    error_code = error.response.get("Error", {}).get("Code")
    if error_code not in {"AccessDenied", "AllAccessDisabled"}:
        raise
    print("MLFLOW_BUCKET_ISOLATION=PASS")
else:
    raise SystemExit("MLflow scoped user can access the ResearchOps artifact bucket")
PY

echo
echo "============================================================"
echo "4. EXPERIMENT BOOTSTRAP AND PROXY SMOKE"
echo "============================================================"
"$PYTHON" -m research.python.researchops.mlflow_tracking bootstrap-experiments \
  --report-path "$REPORT_DIR/experiments-first.json" \
  | tee "$REPORT_DIR/experiments-first.log"
"$PYTHON" -m research.python.researchops.mlflow_tracking bootstrap-experiments \
  --report-path "$REPORT_DIR/experiments-second.json" \
  | tee "$REPORT_DIR/experiments-second.log"

"$PYTHON" - "$REPORT_DIR/experiments-first.json" "$REPORT_DIR/experiments-second.json" <<'PY'
import json, sys
first=json.load(open(sys.argv[1]))
second=json.load(open(sys.argv[2]))
assert first["passed"] and second["passed"]
assert len(first["experiments"]) == len(second["experiments"]) == 6
assert all(not item["created"] for item in second["experiments"])
print("MLFLOW_EXPERIMENT_BOOTSTRAP_IDEMPOTENT=PASS")
PY

env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
  "$PYTHON" -m research.python.researchops.mlflow_tracking smoke-test \
  --report-path "$REPORT_DIR/smoke.json" \
  2>&1 | tee "$REPORT_DIR/smoke.log"
"$PYTHON" - "$REPORT_DIR/smoke.json" <<'PY'
import json, sys
p=json.load(open(sys.argv[1]))
assert p["passed"] is True and p["artifact_proxy_round_trip"] is True, p
print("MLFLOW_ARTIFACT_PROXY=PASS")
PY

echo
echo "============================================================"
echo "5. PACKAGE VERIFIED TRAINING RELEASE"
echo "============================================================"
MODEL_SOURCE_DIR="${RESEARCHOPS_MODEL_SOURCE_DIR:-$ROOT/artifacts/models}"
"$PYTHON" -m research.python.researchops.mlflow_tracking package-training-release \
  --artifact-profile development-minio \
  --model-source-dir "$MODEL_SOURCE_DIR" \
  --report-path "$REPORT_DIR/training-package.json" \
  | tee "$REPORT_DIR/training-package.log"
SOURCE_ARTIFACT_ID="$("$PYTHON" - "$REPORT_DIR/training-package.json" <<'PY'
import json, sys
p=json.load(open(sys.argv[1]))
assert p["artifact_id"].startswith("artifact_trained_model_")
print(p["artifact_id"])
PY
)"
echo "SOURCE_ARTIFACT_ID=$SOURCE_ARTIFACT_ID"

"$PYTHON" -m research.python.researchops.mlflow_tracking \
  verify-training-release-portability \
  --artifact-profile development-minio \
  --artifact-id "$SOURCE_ARTIFACT_ID" \
  --report-path "$REPORT_DIR/training-portability.json" \
  | tee "$REPORT_DIR/training-portability.log"
"$PYTHON" - "$REPORT_DIR/training-portability.json" <<'PY'
import json, sys
p=json.load(open(sys.argv[1]))
assert p["passed"] is True, p
print("MLFLOW_TRAINING_RELEASE_PORTABILITY=PASS")
PY

echo
echo "============================================================"
echo "6. TRACK, REGISTER, RECEIPT AND IDEMPOTENCY"
echo "============================================================"
env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
  "$PYTHON" -m research.python.researchops.mlflow_tracking register-training-release \
  --artifact-profile development-minio \
  --artifact-id "$SOURCE_ARTIFACT_ID" \
  --report-path "$REPORT_DIR/register-first.json" \
  2>&1 | tee "$REPORT_DIR/register-first.log"

env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
  "$PYTHON" -m research.python.researchops.mlflow_tracking register-training-release \
  --artifact-profile development-minio \
  --artifact-id "$SOURCE_ARTIFACT_ID" \
  --report-path "$REPORT_DIR/register-second.json" \
  2>&1 | tee "$REPORT_DIR/register-second.log"

"$PYTHON" - "$REPORT_DIR/register-first.json" "$REPORT_DIR/register-second.json" <<'PY'
import json, sys
first=json.load(open(sys.argv[1])); second=json.load(open(sys.argv[2]))
assert first["receipt_artifact_id"] == second["receipt_artifact_id"]
assert first["tracking"]["parent_run_id"] == second["tracking"]["parent_run_id"]
assert first["registry"]["candidate_version"] == second["registry"]["candidate_version"]
assert [m["run_id"] for m in first["tracking"]["models"]] == [m["run_id"] for m in second["tracking"]["models"]]
assert [m["version"] for m in first["registry"]["versions"]] == [m["version"] for m in second["registry"]["versions"]]
assert second["receipt_reused"] is True
assert all(m["reused"] for m in second["tracking"]["models"])
assert all(m["reused"] for m in second["registry"]["versions"])
assert len(first["tracking"]["models"]) == len(first["registry"]["versions"]) == 3
print("MLFLOW_TRACKING_IDEMPOTENCY=PASS")
print("MLFLOW_MODEL_VERSION_IDEMPOTENCY=PASS")
print("MLFLOW_RECEIPT_IDEMPOTENCY=PASS")
PY

echo
echo "============================================================"
echo "7. LOAD MODEL BY VERSION AND CANDIDATE ALIAS"
echo "============================================================"
env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
  "$PYTHON" - "$REPORT_DIR/register-first.json" <<'PY'
import json
import os
import sys
import tempfile
from pathlib import Path

import mlflow
import numpy as np

from research.python.researchops.artifacts.profiles import load_store
from research.python.researchops.mlflow_tracking.training_release import (
    download_training_release,
    load_input_example,
)

payload=json.load(open(sys.argv[1]))
model_name=payload["registry"]["registered_model_name"]
version=payload["registry"]["candidate_version"]
artifact_id=payload["tracking"]["source_artifact_id"]
selected=payload["tracking"]["selected_model"]
mlflow.set_tracking_uri(os.environ["MLFLOW_TRACKING_URI"])
with tempfile.TemporaryDirectory(prefix="mlflow-phase5-load-") as directory:
    release=download_training_release(load_store("development-minio"), artifact_id, Path(directory))
    example=load_input_example(release, selected)
    by_version=mlflow.pyfunc.load_model(f"models:/{model_name}/{version}")
    by_alias=mlflow.pyfunc.load_model(f"models:/{model_name}@candidate")
    version_prediction=np.asarray(by_version.predict(example))
    alias_prediction=np.asarray(by_alias.predict(example))
    assert np.array_equal(version_prediction, alias_prediction)
print("MLFLOW_LOAD_BY_VERSION=PASS")
print("MLFLOW_LOAD_BY_ALIAS=PASS")
print("MLFLOW_ALIAS_PREDICTION_MATCH=PASS")
PY

echo
echo "============================================================"
echo "8. TWO-WAY RECONCILIATION"
echo "============================================================"
env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
  "$PYTHON" -m research.python.researchops.mlflow_tracking reconcile \
  --artifact-profile development-minio \
  --mode report-only \
  --report-path "$REPORT_DIR/reconciliation.json" \
  2>&1 | tee "$REPORT_DIR/reconciliation.log"
"$PYTHON" - "$REPORT_DIR/reconciliation.json" <<'PY'
import json, sys
p=json.load(open(sys.argv[1]))
assert p["passed"] is True, p
assert len(p["receipt_artifact_ids"]) >= 1
print("MLFLOW_RECONCILIATION=PASS")
PY

echo
echo "============================================================"
echo "9. FINAL RESEARCHOPS VERIFICATION"
echo "============================================================"
"$PYTHON" -m pytest -q tests/research/python/researchops
"$PYTHON" -m research.python.researchops.contracts validate
"$PYTHON" -m research.python.researchops.stage_registry validate
"$PYTHON" -m research.python.researchops.stage_registry coverage
"$PYTHON" -m research.python.researchops.stage_registry compile --check
"$PYTHON" -m compileall -q research/python/researchops
git diff --check

cat > "$REPORT_DIR/summary.json" <<JSON
{
  "schema_version": "researchops_mlflow_phase5_acceptance_v1",
  "passed": true,
  "mlflow_version": "3.14.0",
  "source_artifact_id": "$SOURCE_ARTIFACT_ID",
  "tracking_report": "$REPORT_DIR/register-first.json",
  "portability_report": "$REPORT_DIR/training-portability.json",
  "reconciliation_report": "$REPORT_DIR/reconciliation.json"
}
JSON

echo
echo "============================================================"
echo "MLFLOW_PHASE5_LIVE_ACCEPTANCE=PASS"
echo "PHASE_5A_INFRASTRUCTURE=COMPLETE"
echo "PHASE_5B_VERIFIED_TRACKING=COMPLETE"
echo "PHASE_5C_REGISTRY_RECEIPT_RECONCILIATION=COMPLETE"
echo "PHASE_5_CURRENT_STATE_ACCEPTANCE=PASS"
echo "Reports: $REPORT_DIR"
echo "============================================================"
