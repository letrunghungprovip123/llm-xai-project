from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from research.python.researchops.artifacts.models import (
    ArtifactPackage,
    ArtifactReference,
    ArtifactParent,
    ArtifactProducer,
    ArtifactSource,
)
from research.python.researchops.artifacts.package_builder import ArtifactPackageBuilder
from research.python.researchops.artifacts.stores.base import ArtifactStore

from .model_uri import receipt_model_uri_is_supported
from .models import TrainingTrackingResult
from .registry import RegistryRegistrationResult


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ReceiptModelVersion(StrictModel):
    model_name: str
    run_id: str
    model_uri: str
    tracking_key: str
    version: str
    selected_as_best: bool
    aliases: tuple[str, ...] = ()

    @field_validator("model_uri")
    @classmethod
    def validate_model_uri(cls, value: str) -> str:
        if not receipt_model_uri_is_supported(value):
            raise ValueError(
                "Receipt model_uri must be an MLflow 3 logged-model URI or "
                "a supported historical runs:/ URI"
            )
        return value


class MLflowRegistrationReceiptV1(StrictModel):
    schema_name: Literal["mlflow_registration_receipt_v1"] = (
        "mlflow_registration_receipt_v1"
    )
    source_model_artifact_id: str
    source_model_manifest_sha256: str
    experiment_id: str
    parent_run_id: str
    registered_model_name: str
    candidate_version: str
    mlflow_version: str
    versions: tuple[ReceiptModelVersion, ...]
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @model_validator(mode="after")
    def receipt_is_consistent(self) -> "MLflowRegistrationReceiptV1":
        if len(self.versions) != 3:
            raise ValueError("A training receipt must contain exactly three model versions")
        selected = [item for item in self.versions if item.selected_as_best]
        if len(selected) != 1:
            raise ValueError("Exactly one registered model version must be selected")
        if selected[0].version != self.candidate_version:
            raise ValueError("candidate_version does not match selected model")
        if selected[0].aliases != ("candidate",):
            raise ValueError("Selected model must carry only the candidate alias")
        if any(item.aliases for item in self.versions if not item.selected_as_best):
            raise ValueError("Non-selected versions must not receive aliases")
        return self


def build_receipt(
    *,
    tracking: TrainingTrackingResult,
    registration: RegistryRegistrationResult,
    mlflow_version: str,
) -> MLflowRegistrationReceiptV1:
    return MLflowRegistrationReceiptV1(
        source_model_artifact_id=tracking.source_artifact_id,
        source_model_manifest_sha256=tracking.source_manifest_sha256,
        experiment_id=tracking.experiment_id,
        parent_run_id=tracking.parent_run_id,
        registered_model_name=registration.registered_model_name,
        candidate_version=registration.candidate.version,
        mlflow_version=mlflow_version,
        versions=tuple(
            ReceiptModelVersion(
                model_name=item.model_name,
                run_id=item.run_id,
                model_uri=item.model_uri,
                tracking_key=item.tracking_key,
                version=item.version,
                selected_as_best=item.selected_as_best,
                aliases=item.aliases,
            )
            for item in registration.versions
        ),
    )


def build_receipt_package(
    *,
    store: ArtifactStore,
    source_artifact_id: str,
    receipt: MLflowRegistrationReceiptV1,
) -> tuple[ArtifactPackage, tempfile.TemporaryDirectory[str]]:
    source = store.get_manifest(source_artifact_id)
    if source.manifest_sha256 != receipt.source_model_manifest_sha256:
        raise ValueError("Receipt source manifest hash does not match artifact store")
    temporary = tempfile.TemporaryDirectory(prefix="researchops-mlflow-receipt-")
    path = Path(temporary.name) / "mlflow_registration_receipt.json"
    path.write_text(
        json.dumps(receipt.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    registry_lock = json.loads(
        Path("config/platform/generated/stage_registry.lock.json").read_text(encoding="utf-8")
    )
    package = ArtifactPackageBuilder(
        artifact_type="mlflow_registration_receipt",
        schema_version="mlflow_registration_receipt_v1",
        producer=ArtifactProducer(
            stage_id="ops.mlflow_register",
            stage_version=1,
            stage_run_id=None,
            registry_sha256=str(registry_lock["registry_sha256"]),
        ),
        source=ArtifactSource(
            source_commit=source.source.source_commit,
            environment_snapshot_id=source.source.environment_snapshot_id,
        ),
        parents=[
            ArtifactParent(
                artifact_id=source.artifact_id,
                manifest_sha256=source.manifest_sha256,
                relationship="registered_in_mlflow",
            )
        ],
        metadata={
            "registered_model_name": receipt.registered_model_name,
            "candidate_version": receipt.candidate_version,
            "experiment_id": receipt.experiment_id,
            "parent_run_id": receipt.parent_run_id,
        },
    ).add_file(
        path,
        relative_path="receipt/mlflow_registration_receipt.json",
        media_type="application/json",
    ).build()
    return package, temporary


def load_receipt(store: ArtifactStore, artifact_id: str, destination: Path) -> MLflowRegistrationReceiptV1:
    manifest = store.get_manifest(artifact_id)
    if manifest.artifact_type != "mlflow_registration_receipt":
        raise ValueError(f"Not an MLflow registration receipt: {artifact_id}")
    root = store.download(artifact_id, destination)
    matches = list((root / "files").rglob("mlflow_registration_receipt.json"))
    if len(matches) != 1:
        raise ValueError(f"Receipt artifact {artifact_id} has invalid file inventory")
    return MLflowRegistrationReceiptV1.model_validate_json(
        matches[0].read_text(encoding="utf-8")
    )


def _receipt_identity(receipt: MLflowRegistrationReceiptV1) -> dict[str, object]:
    return receipt.model_dump(mode="json", exclude={"created_at"})


def find_receipts_for_source(
    store: ArtifactStore,
    source_artifact_id: str,
) -> tuple[tuple[str, MLflowRegistrationReceiptV1], ...]:
    matches: list[tuple[str, MLflowRegistrationReceiptV1]] = []
    with tempfile.TemporaryDirectory(prefix="researchops-find-mlflow-receipt-") as directory:
        for index, artifact_id in enumerate(sorted(store.list_artifact_ids())):
            manifest = store.get_manifest(artifact_id)
            if manifest.artifact_type != "mlflow_registration_receipt":
                continue
            if not any(parent.artifact_id == source_artifact_id for parent in manifest.parents):
                continue
            matches.append((
                artifact_id,
                load_receipt(store, artifact_id, Path(directory) / str(index)),
            ))
    return tuple(sorted(matches, key=lambda item: item[1].created_at))


def find_receipt_for_source(
    store: ArtifactStore,
    source_artifact_id: str,
) -> tuple[str, MLflowRegistrationReceiptV1] | None:
    matches = find_receipts_for_source(store, source_artifact_id)
    return matches[-1] if matches else None

def publish_receipt(
    *,
    store: ArtifactStore,
    source_artifact_id: str,
    receipt: MLflowRegistrationReceiptV1,
) -> tuple[ArtifactReference, bool]:
    matches = find_receipts_for_source(store, source_artifact_id)
    identical = [
        (artifact_id, observed)
        for artifact_id, observed in matches
        if _receipt_identity(observed) == _receipt_identity(receipt)
    ]
    if len(identical) > 1:
        raise ValueError(
            "Duplicate identical MLflow receipts exist for the same source artifact"
        )
    if identical:
        return store.describe(identical[0][0]).reference, True
    package, temporary = build_receipt_package(
        store=store,
        source_artifact_id=source_artifact_id,
        receipt=receipt,
    )
    try:
        return store.put_package(package), False
    finally:
        temporary.cleanup()
