from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Callable

from research.python.researchops.artifacts.stores.base import ArtifactStore

from .contracts import TrackingContract
from .exceptions import MLflowIntegrityError
from .metric_mapper import map_model_metrics
from .model_uri import require_canonical_logged_model_uri
from .models import DownloadedTrainingRelease, RunSnapshot, TrackedModelRun, TrainingTrackingResult
from .parameter_mapper import common_parameters, model_parameters
from .run_identity import tracking_key
from .tracking_gateway import TrackingGateway
from .training_release import download_training_release, load_input_example


_STATE_ORDER = {
    "DISCOVERED": 0,
    "RUN_CREATED": 1,
    "METADATA_LOGGED": 2,
    "MODEL_LOGGED": 3,
    "MODEL_VERSION_REGISTERED": 4,
    "RECEIPT_PUBLISHED": 5,
    "CANDIDATE_EVALUATED": 6,
    "COMPLETE": 7,
}


def _state(snapshot: RunSnapshot) -> str:
    return snapshot.tags.get("researchops.integration_state", "RUN_CREATED")


def _find_or_create(
    gateway: TrackingGateway,
    *,
    experiment_id: str,
    run_name: str,
    tracking_key_value: str,
    tags: dict[str, str],
) -> tuple[str, RunSnapshot | None]:
    found = gateway.find_runs(experiment_id, tracking_key_value)
    if len(found) > 1:
        raise MLflowIntegrityError(f"Duplicate MLflow runs for tracking key {tracking_key_value}")
    if found:
        return found[0].run_id, found[0]
    run_id = gateway.create_run(experiment_id, run_name, tags)
    gateway.set_tags(run_id, {"researchops.integration_state": "RUN_CREATED"})
    return run_id, None


def _default_model_loader(path: Path):
    import joblib

    loaded = joblib.load(path)
    if isinstance(loaded, dict):
        missing = [
            key
            for key in ("model_name", "feature_columns", "estimator")
            if key not in loaded
        ]
        if missing:
            raise MLflowIntegrityError(
                f"Invalid trained-model bundle at {path}: missing keys {missing}"
            )
        model = loaded["estimator"]
    else:
        # Retain compatibility with historical artifacts that stored a fitted
        # estimator directly instead of the governed dictionary bundle.
        model = loaded

    if not hasattr(model, "predict"):
        raise MLflowIntegrityError(
            f"Loaded model at {path} does not expose predict(): "
            f"{type(model).__name__}"
        )
    return model


def _default_signature_builder(model: Any, input_example: Any):
    from mlflow.models import infer_signature

    if not hasattr(model, "predict"):
        raise MLflowIntegrityError(
            f"Cannot infer MLflow signature for {type(model).__name__}: "
            "predict() is missing"
        )
    # mlflow.sklearn's pyfunc flavor invokes estimator.predict() by default.
    # Infer the signature from that same method so the recorded output schema
    # matches the model behavior loaded later via mlflow.pyfunc.
    prediction = model.predict(input_example)
    return infer_signature(input_example, prediction)


def _provenance_file(release: DownloadedTrainingRelease, directory: Path) -> Path:
    path = directory / "artifact_manifest_pointer.json"
    path.write_text(json.dumps({
        "artifact_id": release.manifest.artifact_id,
        "manifest_uri": release.manifest_uri,
        "manifest_sha256": release.manifest.manifest_sha256,
        "source_commit": release.manifest.source.source_commit,
        "stage_registry_sha256": release.manifest.producer.registry_sha256,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _model_metadata_files(
    release: DownloadedTrainingRelease,
    candidate,
    directory: Path,
    metrics: dict[str, float],
) -> tuple[Path, Path, Path]:
    root = directory / candidate.model_name
    root.mkdir(parents=True, exist_ok=True)
    hyperparameters = root / "hyperparameters.json"
    hyperparameters.write_text(
        json.dumps(candidate.metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    metric_path = root / "metrics.json"
    metric_path.write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    model_card = root / "model_card.md"
    model_card.write_text(
        "\n".join([
            f"# {candidate.model_name}",
            "",
            "## Governed identity",
            f"- Source artifact: `{release.manifest.artifact_id}`",
            f"- Source manifest SHA-256: `{release.manifest.manifest_sha256}`",
            f"- Source commit: `{release.manifest.source.source_commit}`",
            f"- Input level: `{release.manifest.metadata.get('model_input_level', 'preprocessed_feature_matrix')}`",
            f"- Selected as best: `{candidate.selected_as_best}`",
            "",
            "## Scope",
            "Binary Home Credit default-risk prediction. Metrics are copied from the verified training registry; this adapter does not recalculate them.",
            "",
            "## Limitations",
            *(f"- {item}" for item in (release.manifest.limitations or ("No additional limitations recorded.",))),
            "",
        ]),
        encoding="utf-8",
    )
    return hyperparameters, metric_path, model_card


def track_training_release(
    *,
    store: ArtifactStore,
    artifact_id: str,
    gateway: TrackingGateway,
    contract: TrackingContract,
    model_loader: Callable[[Path], Any] = _default_model_loader,
    signature_builder: Callable[[Any, Any], Any] = _default_signature_builder,
) -> TrainingTrackingResult:
    experiment_id = gateway.experiment_id(contract.training_experiment)
    with tempfile.TemporaryDirectory(prefix="researchops-mlflow-track-") as directory:
        work = Path(directory)
        release = download_training_release(store, artifact_id, work / "source")
        common = common_parameters(release)
        parent_key = tracking_key(release.manifest, model_name="__training_release__")
        parent_tags = {
            "researchops.project": "llm-xai",
            "researchops.run_kind": "TRAINING_RELEASE",
            "researchops.tracking_key": parent_key,
            "researchops.source_artifact_id": release.manifest.artifact_id,
            "researchops.source_manifest_uri": release.manifest_uri,
            "researchops.source_manifest_sha256": release.manifest.manifest_sha256,
            "researchops.source_commit": release.manifest.source.source_commit,
            "researchops.stage_registry_sha256": release.manifest.producer.registry_sha256,
            "researchops.pipeline_run_id": str(release.manifest.metadata.get("pipeline_run_id", "UNAVAILABLE")),
            "researchops.stage_run_id": release.manifest.producer.stage_run_id or "UNAVAILABLE",
            "researchops.environment_snapshot_id": release.manifest.source.environment_snapshot_id or "UNAVAILABLE",
            "researchops.dataset_release_id": str(release.manifest.metadata.get("dataset_release_id", "UNREGISTERED_LEGACY")),
            "researchops.feature_matrix_id": str(release.manifest.metadata.get("feature_matrix_artifact_id", "UNREGISTERED_LEGACY")),
            "researchops.split_id": str(release.manifest.metadata.get("split_artifact_id", "UNREGISTERED_LEGACY")),
            "researchops.preprocessing_version": str(release.manifest.metadata.get("preprocessing_version", "legacy_model_ready_v1")),
            "researchops.model_ready_status": str(release.manifest.metadata.get("model_ready_audit_status", "UNKNOWN")).upper(),
            "researchops.gate_status": "PENDING",
            "researchops.integration_state": "DISCOVERED",
        }
        parent_run_id, parent_snapshot = _find_or_create(
            gateway,
            experiment_id=experiment_id,
            run_name=f"training-release-{release.manifest.artifact_id[-8:]}",
            tracking_key_value=parent_key,
            tags=parent_tags,
        )
        parent_reused = parent_snapshot is not None
        parent_state = _state(parent_snapshot) if parent_snapshot else "RUN_CREATED"
        if _STATE_ORDER.get(parent_state, -1) < _STATE_ORDER["METADATA_LOGGED"]:
            gateway.log_params(parent_run_id, common)
            gateway.log_artifact(parent_run_id, release.registry_path, "training-release/registry")
            gateway.log_artifact(parent_run_id, release.training_manifest_path, "training-release/manifests")
            gateway.log_artifact(parent_run_id, _provenance_file(release, work), "training-release/provenance")
            gateway.set_tags(parent_run_id, {"researchops.integration_state": "METADATA_LOGGED"})

        tracked: list[TrackedModelRun] = []
        for candidate in release.registry.models:
            key = tracking_key(release.manifest, model_name=candidate.model_name)
            status = "SELECTED" if candidate.selected_as_best else "ELIGIBLE"
            tags = {
                **parent_tags,
                "mlflow.parentRunId": parent_run_id,
                "researchops.run_kind": "MODEL_CANDIDATE",
                "researchops.tracking_key": key,
                "researchops.model_name": candidate.model_name,
                "researchops.algorithm": str(candidate.metadata.get("algorithm", candidate.model_name)),
                "researchops.model_input_level": str(release.manifest.metadata.get("model_input_level", "preprocessed_feature_matrix")),
                "researchops.candidate_status": status,
                "researchops.integration_state": "DISCOVERED",
            }
            run_id, snapshot = _find_or_create(
                gateway,
                experiment_id=experiment_id,
                run_name=candidate.model_name,
                tracking_key_value=key,
                tags=tags,
            )
            reused = snapshot is not None
            state = _state(snapshot) if snapshot else "RUN_CREATED"
            model_uri = (snapshot.tags.get("researchops.logged_model_uri", "") if snapshot else "")
            if _STATE_ORDER.get(state, -1) >= _STATE_ORDER["MODEL_LOGGED"]:
                resolved_model_uri = gateway.resolve_logged_model_uri(run_id, "model")
                if resolved_model_uri is None:
                    raise MLflowIntegrityError(
                        f"Run {run_id} is marked MODEL_LOGGED but no MLflow 3 "
                        "logged model can be resolved"
                    )
                if model_uri != resolved_model_uri:
                    migration_tags = {
                        "researchops.logged_model_uri": resolved_model_uri,
                        "researchops.model_uri_contract": "mlflow3_logged_model_id_v1",
                    }
                    if model_uri:
                        migration_tags["researchops.previous_logged_model_uri"] = model_uri
                    gateway.set_tags(run_id, migration_tags)
                model_uri = require_canonical_logged_model_uri(resolved_model_uri)
            if _STATE_ORDER.get(state, -1) < _STATE_ORDER["METADATA_LOGGED"]:
                mapped_metrics = map_model_metrics(candidate, contract)
                gateway.log_params(run_id, {**common, **model_parameters(candidate)})
                gateway.log_metrics(run_id, mapped_metrics)
                hyperparameters, metric_file, model_card = _model_metadata_files(
                    release, candidate, work / "model-metadata", mapped_metrics
                )
                gateway.log_artifact(run_id, hyperparameters, "parameters")
                gateway.log_artifact(run_id, metric_file, "evaluation")
                gateway.log_artifact(run_id, model_card, "reports")
                gateway.log_artifact(run_id, _provenance_file(release, work), "provenance")
                gateway.log_artifact(run_id, release.feature_columns_paths[candidate.model_name], "schema")
                gateway.log_artifact(run_id, release.feature_mapping_paths[candidate.model_name], "schema")
                gateway.log_artifact(run_id, release.registry_path, "provenance")
                gateway.log_artifact(run_id, release.training_manifest_path, "provenance")
                for artifact in release.support_artifacts:
                    gateway.log_artifact(run_id, artifact, "support")
                gateway.set_tags(run_id, {"researchops.integration_state": "METADATA_LOGGED"})
                state = "METADATA_LOGGED"
            if _STATE_ORDER.get(state, -1) < _STATE_ORDER["MODEL_LOGGED"]:
                model = model_loader(release.model_paths[candidate.model_name])
                example = load_input_example(release, candidate.model_name)
                signature = signature_builder(model, example)
                model_uri = require_canonical_logged_model_uri(gateway.log_sklearn_model(
                    run_id,
                    model,
                    artifact_path="model",
                    input_example=example,
                    signature=signature,
                ))
                gateway.set_tags(run_id, {
                    "researchops.logged_model_uri": model_uri,
                    "researchops.model_uri_contract": "mlflow3_logged_model_id_v1",
                    "researchops.integration_state": "MODEL_LOGGED",
                })
                gateway.terminate(run_id)
            if not model_uri:
                raise MLflowIntegrityError(f"Model URI missing for completed run {run_id}")
            model_uri = require_canonical_logged_model_uri(model_uri)
            tracked.append(TrackedModelRun(
                model_name=candidate.model_name,
                run_id=run_id,
                model_uri=model_uri,
                tracking_key=key,
                selected_as_best=candidate.selected_as_best,
                reused=reused,
            ))

        gateway.set_tags(parent_run_id, {
            "researchops.selected_model": release.registry.best_model["model_name"],
            "researchops.integration_state": "COMPLETE",
        })
        gateway.terminate(parent_run_id)
        return TrainingTrackingResult(
            source_artifact_id=release.manifest.artifact_id,
            source_manifest_sha256=release.manifest.manifest_sha256,
            experiment_id=experiment_id,
            parent_run_id=parent_run_id,
            parent_reused=parent_reused,
            models=tuple(tracked),
        )
