#!/usr/bin/env bash
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
cd "$ROOT"
PYTHON="$ROOT/.venv/bin/python3"
REPORT_DIR="${RESEARCHOPS_MLFLOW_FRESH_STATE_DIR:-/tmp/researchops-mlflow-phase5-fresh-state}"
MODEL_SOURCE_DIR="${RESEARCHOPS_MODEL_SOURCE_DIR:-$ROOT/artifacts/models}"

[[ -x "$PYTHON" ]] || { echo "ERROR: missing $PYTHON" >&2; exit 2; }
[[ -d "$MODEL_SOURCE_DIR" ]] || {
  echo "ERROR: model source directory not found: $MODEL_SOURCE_DIR" >&2
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

export MLFLOW_FRESH_POSTGRES_DB="${MLFLOW_FRESH_POSTGRES_DB:-mlflow_phase5_acceptance}"
export MLFLOW_FRESH_POSTGRES_USER="${MLFLOW_FRESH_POSTGRES_USER:-mlflow_phase5_acceptance_app}"
export MLFLOW_FRESH_POSTGRES_PASSWORD="${MLFLOW_FRESH_POSTGRES_PASSWORD:-$(openssl rand -hex 18)}"
export MLFLOW_FRESH_S3_BUCKET="${MLFLOW_FRESH_S3_BUCKET:-llm-xai-mlflow-phase5-acceptance}"
export MLFLOW_FRESH_S3_ACCESS_KEY="${MLFLOW_FRESH_S3_ACCESS_KEY:-mlflow-phase5-acceptance}"
export MLFLOW_FRESH_S3_SECRET_KEY="${MLFLOW_FRESH_S3_SECRET_KEY:-$(openssl rand -hex 18)}"
export MLFLOW_FRESH_BACKEND_STORE_URI="postgresql+psycopg://${MLFLOW_FRESH_POSTGRES_USER}:${MLFLOW_FRESH_POSTGRES_PASSWORD}@researchops-postgres:5432/${MLFLOW_FRESH_POSTGRES_DB}"
export MLFLOW_FRESH_ARTIFACTS_DESTINATION="s3://${MLFLOW_FRESH_S3_BUCKET}/mlartifacts"

# Start only the shared infrastructure required by the isolated acceptance
# namespace. Production/current-state databases and buckets are not reset.
docker compose --profile researchops-mlflow-fresh up -d \
  researchops-postgres researchops-minio

# Reset only the isolated acceptance DB and bucket. Production/current-state
# databases, buckets and Docker volumes are never touched.
docker compose --profile researchops-mlflow-fresh stop researchops-mlflow-fresh >/dev/null 2>&1 || true
docker exec -e PGPASSWORD="$RESEARCHOPS_POSTGRES_PASSWORD" \
  llm-xai-researchops-postgres psql \
  -U "$RESEARCHOPS_POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${MLFLOW_FRESH_POSTGRES_DB}' AND pid <> pg_backend_pid();" \
  -c "DROP DATABASE IF EXISTS \"${MLFLOW_FRESH_POSTGRES_DB}\";" >/dev/null

"$PYTHON" - <<'PY'
import os
import boto3
client=boto3.client(
    "s3",
    endpoint_url="http://127.0.0.1:9000",
    aws_access_key_id=os.environ["RESEARCHOPS_S3_ACCESS_KEY"],
    aws_secret_access_key=os.environ["RESEARCHOPS_S3_SECRET_KEY"],
    region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
)
bucket=os.environ["MLFLOW_FRESH_S3_BUCKET"]
try:
    versions=client.get_paginator("list_object_versions")
    for page in versions.paginate(Bucket=bucket):
        objects=[
            {"Key": item["Key"], "VersionId": item["VersionId"]}
            for field in ("Versions", "DeleteMarkers")
            for item in page.get(field, [])
        ]
        if objects:
            client.delete_objects(Bucket=bucket, Delete={"Objects": objects, "Quiet": True})
    client.delete_bucket(Bucket=bucket)
except client.exceptions.NoSuchBucket:
    pass
PY

docker compose --profile researchops-mlflow-fresh up -d --build \
  researchops-mlflow-fresh-db-init \
  researchops-mlflow-fresh-minio-init \
  researchops-mlflow-fresh-migrate \
  researchops-mlflow-fresh

for attempt in $(seq 1 120); do
  status="$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' \
    llm-xai-researchops-mlflow-fresh 2>/dev/null || true)"
  [[ "$status" == "healthy" ]] && break
  sleep 2
done
[[ "${status:-}" == "healthy" ]] || {
  docker compose --profile researchops-mlflow-fresh logs --tail=300 researchops-mlflow-fresh
  exit 1
}

export MLFLOW_TRACKING_URI="http://127.0.0.1:5001"
export MLFLOW_EXPECTED_VERSION="3.14.0"
export MLFLOW_S3_ENDPOINT_URL="http://127.0.0.1:9000"
export AWS_ACCESS_KEY_ID="$MLFLOW_FRESH_S3_ACCESS_KEY"
export AWS_SECRET_ACCESS_KEY="$MLFLOW_FRESH_S3_SECRET_KEY"

"$PYTHON" - "$MODEL_SOURCE_DIR" "$REPORT_DIR/acceptance.json" <<'PY'
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import mlflow
import numpy as np

from research.python.researchops.artifacts.stores.filesystem import FilesystemArtifactStore
from research.python.researchops.mlflow_tracking.bootstrap import bootstrap_experiments
from research.python.researchops.mlflow_tracking.client import RealMLflowGateway
from research.python.researchops.mlflow_tracking.contracts import (
    load_experiment_catalog,
    load_registry_policy,
    load_tracking_contract,
)
from research.python.researchops.mlflow_tracking.package_training import build_training_release_package
from research.python.researchops.mlflow_tracking.receipts import build_receipt, publish_receipt
from research.python.researchops.mlflow_tracking.reconciliation import reconcile_mlflow
from research.python.researchops.mlflow_tracking.registry import register_training_models
from research.python.researchops.mlflow_tracking.registry_gateway import RealRegistryGateway
from research.python.researchops.mlflow_tracking.reporting import write_json_report
from research.python.researchops.mlflow_tracking.settings import MLflowSettings
from research.python.researchops.mlflow_tracking.tracking import track_training_release
from research.python.researchops.mlflow_tracking.tracking_gateway import RealTrackingGateway
from research.python.researchops.mlflow_tracking.training_release import (
    download_training_release,
    load_input_example,
    verify_training_release_portability,
)

model_source_dir=Path(__import__("sys").argv[1])
report_path=Path(__import__("sys").argv[2])
settings=MLflowSettings.from_environment()
gateway=RealMLflowGateway(settings)
version=gateway.version_report()
assert version.passed, version
bootstrap_experiments(gateway, load_experiment_catalog())

with tempfile.TemporaryDirectory(prefix="phase5-fresh-artifacts-") as directory:
    store=FilesystemArtifactStore(Path(directory) / "store")
    with build_training_release_package(
        model_source_dir=model_source_dir,
    ) as build:
        source=store.put_package(build.package)
    portability=verify_training_release_portability(store, source.artifact_id)
    assert portability["passed"] is True, portability

    tracking_gateway=RealTrackingGateway(settings.tracking_uri)
    registry_gateway=RealRegistryGateway(settings.tracking_uri)
    contract=load_tracking_contract()
    policy=load_registry_policy()

    first_tracking=track_training_release(
        store=store,
        artifact_id=source.artifact_id,
        gateway=tracking_gateway,
        contract=contract,
    )
    first_registration=register_training_models(
        tracking=first_tracking,
        source_manifest=build.package.manifest,
        gateway=registry_gateway,
        policy=policy,
    )
    first_receipt=build_receipt(
        tracking=first_tracking,
        registration=first_registration,
        mlflow_version=settings.expected_version,
    )
    first_receipt_ref, first_receipt_reused=publish_receipt(
        store=store,
        source_artifact_id=source.artifact_id,
        receipt=first_receipt,
    )
    assert first_receipt_reused is False

    second_tracking=track_training_release(
        store=store,
        artifact_id=source.artifact_id,
        gateway=tracking_gateway,
        contract=contract,
    )
    second_registration=register_training_models(
        tracking=second_tracking,
        source_manifest=build.package.manifest,
        gateway=registry_gateway,
        policy=policy,
    )
    second_receipt=build_receipt(
        tracking=second_tracking,
        registration=second_registration,
        mlflow_version=settings.expected_version,
    )
    second_receipt_ref, second_receipt_reused=publish_receipt(
        store=store,
        source_artifact_id=source.artifact_id,
        receipt=second_receipt,
    )

    assert first_tracking.parent_run_id == second_tracking.parent_run_id
    assert [item.run_id for item in first_tracking.models] == [item.run_id for item in second_tracking.models]
    assert [item.version for item in first_registration.versions] == [item.version for item in second_registration.versions]
    assert first_receipt_ref.artifact_id == second_receipt_ref.artifact_id
    assert all(item.reused for item in second_tracking.models)
    assert all(item.reused for item in second_registration.versions)
    assert second_receipt_reused is True
    assert all(item.model_uri.startswith("models:/m-") for item in second_tracking.models)

    mlflow.set_tracking_uri(settings.tracking_uri)
    with tempfile.TemporaryDirectory(prefix="phase5-fresh-load-") as load_dir:
        release=download_training_release(store, source.artifact_id, Path(load_dir))
        example=load_input_example(release, second_tracking.selected_model.model_name)
        by_version=mlflow.pyfunc.load_model(
            f"models:/{policy.registered_model_name}/{second_registration.candidate.version}"
        )
        by_alias=mlflow.pyfunc.load_model(
            f"models:/{policy.registered_model_name}@candidate"
        )
        assert np.array_equal(
            np.asarray(by_version.predict(example)),
            np.asarray(by_alias.predict(example)),
        )

    reconciliation=reconcile_mlflow(
        store=store,
        gateway=registry_gateway,
        policy=policy,
    )
    assert reconciliation.passed, reconciliation.to_dict()
    write_json_report(
        report_path,
        {
            "schema_version": "researchops_mlflow_phase5_fresh_acceptance_v1",
            "passed": True,
            "source_artifact_id": source.artifact_id,
            "receipt_artifact_id": second_receipt_ref.artifact_id,
            "candidate_version": second_registration.candidate.version,
            "model_uris": [item.model_uri for item in second_tracking.models],
            "portability": portability,
            "reconciliation": reconciliation.to_dict(),
        },
    )

print("MLFLOW_FRESH_TRACKING_IDEMPOTENCY=PASS")
print("MLFLOW_FRESH_REGISTRY_IDEMPOTENCY=PASS")
print("MLFLOW_FRESH_RECEIPT_IDEMPOTENCY=PASS")
print("MLFLOW_FRESH_LOAD_BY_VERSION_ALIAS=PASS")
print("MLFLOW_FRESH_RECONCILIATION=PASS")
PY

echo "PHASE_5_FRESH_STATE_ACCEPTANCE=PASS"
echo "PHASE_5_PORTABILITY=PASS"
echo "PHASE_5_CONSOLIDATED=COMPLETE"
