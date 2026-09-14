from pathlib import Path

import yaml


def test_worker_is_writable_and_waits_for_artifact_and_deployment_bootstrap():
    payload = yaml.safe_load(Path("docker-compose.yml").read_text())
    services = payload["services"]
    worker = services["researchops-prefect-worker"]
    assert worker["volumes"] == ["./:/workspace"]
    assert set(worker["depends_on"]) >= {
        "researchops-prefect-deploy",
        "researchops-prefect-artifact-bootstrap",
    }
    assert worker["environment"]["RESEARCHOPS_DATABASE_URL"]
    assert worker["environment"]["RESEARCHOPS_ARTIFACT_PROFILE"]
    assert worker["environment"]["MLFLOW_TRACKING_URI"]


def test_deployment_and_artifact_bootstrap_are_one_shot_services():
    payload = yaml.safe_load(Path("docker-compose.yml").read_text())
    services = payload["services"]
    deploy = services["researchops-prefect-deploy"]
    artifact = services["researchops-prefect-artifact-bootstrap"]
    assert deploy["restart"] == "no"
    assert artifact["restart"] == "no"
    assert deploy["volumes"] == ["./:/workspace:ro"]
    assert artifact["depends_on"]["researchops-minio"]["condition"] == "service_healthy"
