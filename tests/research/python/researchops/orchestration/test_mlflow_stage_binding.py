from pathlib import Path

import yaml

from research.python.researchops.stage_registry.loader import load_stage_registry


def test_mlflow_stage_uses_typed_orchestration_adapter():
    stage = load_stage_registry().by_id()["ops.mlflow_register"]
    assert stage.version == 3
    assert stage.runtime.executable == "python3"
    assert stage.runtime.args == (
        "-m",
        "research.python.researchops.orchestration.stage_commands",
        "mlflow-register",
    )
    assert stage.outputs[0].name == "receipt"
    assert stage.outputs[0].contract == "mlflow_registration_receipt"
    assert {
        "RESEARCHOPS_ARTIFACT_PROFILE",
        "RESEARCHOPS_DATABASE_URL",
        "RESEARCHOPS_S3_BUCKET",
        "RESEARCHOPS_S3_ENDPOINT",
        "RESEARCHOPS_S3_ACCESS_KEY",
        "RESEARCHOPS_S3_SECRET_KEY",
        "RESEARCHOPS_S3_REGION",
        "RESEARCHOPS_S3_USE_SSL",
        "RESEARCHOPS_S3_KEY_PREFIX",
        "MLFLOW_VERSION",
        "MLFLOW_TRACKING_URI",
        "MLFLOW_INTERNAL_TRACKING_URI",
        "MLFLOW_BACKEND_STORE_URI",
        "MLFLOW_ARTIFACTS_DESTINATION",
        "MLFLOW_S3_ENDPOINT_URL",
        "MLFLOW_S3_BUCKET",
        "MLFLOW_S3_ACCESS_KEY",
        "MLFLOW_S3_SECRET_KEY",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_DEFAULT_REGION",
        "MLFLOW_ALLOWED_HOSTS",
    }.issubset(set(stage.secrets))


def test_prefect_worker_exposes_mlflow_runtime_environment():
    payload = yaml.safe_load(
        Path("docker-compose.yml").read_text(encoding="utf-8")
    )
    environment = payload["services"]["researchops-prefect-worker"]["environment"]
    required = {
        "MLFLOW_VERSION",
        "MLFLOW_TRACKING_URI",
        "MLFLOW_INTERNAL_TRACKING_URI",
        "MLFLOW_BACKEND_STORE_URI",
        "MLFLOW_ARTIFACTS_DESTINATION",
        "MLFLOW_S3_ENDPOINT_URL",
        "MLFLOW_S3_BUCKET",
        "MLFLOW_S3_ACCESS_KEY",
        "MLFLOW_S3_SECRET_KEY",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_DEFAULT_REGION",
        "MLFLOW_ALLOWED_HOSTS",
    }
    assert required.issubset(set(environment))
    assert environment["MLFLOW_TRACKING_URI"] == "http://researchops-mlflow:5000"
    assert environment["MLFLOW_INTERNAL_TRACKING_URI"] == "http://researchops-mlflow:5000"
    assert environment["MLFLOW_S3_ENDPOINT_URL"] == "http://researchops-minio:9000"
