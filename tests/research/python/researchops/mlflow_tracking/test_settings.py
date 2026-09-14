from pathlib import Path

import pytest

from research.python.researchops.mlflow_tracking.exceptions import MLflowConfigurationError
from research.python.researchops.mlflow_tracking.settings import MLflowSettings, write_local_environment


def _environment(monkeypatch):
    values = {
        "MLFLOW_TRACKING_URI": "http://127.0.0.1:5000",
        "MLFLOW_INTERNAL_TRACKING_URI": "http://researchops-mlflow:5000",
        "MLFLOW_BACKEND_STORE_URI": "postgresql+psycopg://mlflow_app:secret@researchops-postgres:5432/mlflow",
        "MLFLOW_ARTIFACTS_DESTINATION": "s3://llm-xai-mlflow/mlartifacts",
        "MLFLOW_S3_ENDPOINT_URL": "http://researchops-minio:9000",
        "MLFLOW_S3_BUCKET": "llm-xai-mlflow",
        "MLFLOW_ALLOWED_HOSTS": "localhost:*,127.0.0.1:*,researchops-mlflow:*",
        "MLFLOW_VERSION": "3.14.0",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_settings_redact_database_password(monkeypatch):
    _environment(monkeypatch)
    settings = MLflowSettings.from_environment()
    assert settings.redacted_dict()["backend_store_uri"] == (
        "postgresql+psycopg://mlflow_app:***@researchops-postgres:5432/mlflow"
    )


def test_settings_require_dedicated_artifact_prefix(monkeypatch):
    _environment(monkeypatch)
    monkeypatch.setenv("MLFLOW_ARTIFACTS_DESTINATION", "s3://wrong/path")
    with pytest.raises(MLflowConfigurationError, match="dedicated bucket"):
        MLflowSettings.from_environment()


def test_local_environment_is_private_and_not_overwritten(tmp_path: Path):
    path = write_local_environment(tmp_path / ".env.researchops-mlflow.local")
    assert oct(path.stat().st_mode & 0o777) == "0o600"
    text = path.read_text()
    assert "MLFLOW_VERSION=3.14.0" in text
    assert "change-me" not in text
    with pytest.raises(MLflowConfigurationError, match="Refusing"):
        write_local_environment(path)
