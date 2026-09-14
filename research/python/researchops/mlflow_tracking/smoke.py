from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .contracts import load_tracking_contract
from .exceptions import MLflowIntegrationError
from .settings import MLflowSettings


def run_live_smoke(settings: MLflowSettings) -> dict[str, object]:
    try:
        import mlflow
        from mlflow.tracking import MlflowClient
    except ImportError as exc:
        raise MLflowIntegrationError("MLflow is not installed") from exc

    contract = load_tracking_contract()
    mlflow.set_tracking_uri(settings.tracking_uri)
    client = MlflowClient(tracking_uri=settings.tracking_uri)
    experiment = client.get_experiment_by_name(contract.training_experiment)
    if experiment is None:
        raise MLflowIntegrationError("Run bootstrap-experiments before smoke-test")

    with tempfile.TemporaryDirectory(prefix="researchops-mlflow-smoke-") as directory:
        artifact = Path(directory) / "smoke.json"
        artifact.write_text(json.dumps({"smoke": True}) + "\n", encoding="utf-8")
        with mlflow.start_run(experiment_id=experiment.experiment_id, run_name="researchops-infrastructure-smoke") as active:
            mlflow.set_tags({
                "researchops.project": "llm-xai",
                "researchops.run_kind": "INFRASTRUCTURE_SMOKE",
                "researchops.integration_state": "COMPLETE",
            })
            mlflow.log_param("smoke_contract", "mlflow_tracking_v1")
            mlflow.log_metric("smoke_metric", 1.0)
            mlflow.log_artifact(str(artifact), artifact_path="smoke")
            run_id = active.info.run_id

        downloaded = Path(directory) / "downloaded"
        downloaded.mkdir()
        path = client.download_artifacts(run_id, "smoke/smoke.json", str(downloaded))
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if payload != {"smoke": True}:
            raise MLflowIntegrationError("Artifact proxy round-trip mismatch")
        run = client.get_run(run_id)
        if run.data.params.get("smoke_contract") != "mlflow_tracking_v1":
            raise MLflowIntegrationError("Smoke parameter missing")
        if float(run.data.metrics.get("smoke_metric", 0.0)) != 1.0:
            raise MLflowIntegrationError("Smoke metric missing")

    return {
        "schema_version": "mlflow_infrastructure_smoke_v1",
        "passed": True,
        "run_id": run_id,
        "experiment_id": str(experiment.experiment_id),
        "artifact_proxy_round_trip": True,
    }
