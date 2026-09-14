from __future__ import annotations

from dataclasses import dataclass

from research.python.researchops.artifacts.models import ArtifactManifestV3

from .contracts import RegistryPolicy
from .exceptions import MLflowIntegrityError
from .models import TrainingTrackingResult
from .model_uri import (
    is_canonical_logged_model_uri,
    is_historical_run_model_uri,
    require_canonical_logged_model_uri,
)
from .registry_gateway import ModelVersionSnapshot, RegistryGateway


@dataclass(frozen=True)
class RegisteredModelVersion:
    model_name: str
    run_id: str
    model_uri: str
    tracking_key: str
    version: str
    selected_as_best: bool
    reused: bool
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class RegistryRegistrationResult:
    registered_model_name: str
    source_artifact_id: str
    source_manifest_sha256: str
    versions: tuple[RegisteredModelVersion, ...]

    @property
    def candidate(self) -> RegisteredModelVersion:
        return next(item for item in self.versions if item.selected_as_best)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "mlflow_registry_registration_result_v1",
            "registered_model_name": self.registered_model_name,
            "source_artifact_id": self.source_artifact_id,
            "source_manifest_sha256": self.source_manifest_sha256,
            "candidate_version": self.candidate.version,
            "versions": [item.__dict__ for item in self.versions],
        }


def _find_existing(
    versions: tuple[ModelVersionSnapshot, ...],
    tracking_key: str,
) -> ModelVersionSnapshot | None:
    matches = [
        item
        for item in versions
        if item.tags.get("researchops.tracking_key") == tracking_key
        and item.tags.get("researchops.registry_record_status")
        != "SUPERSEDED_SOURCE_URI"
    ]
    if len(matches) > 1:
        raise MLflowIntegrityError(
            f"Duplicate model versions for tracking key {tracking_key}"
        )
    return matches[0] if matches else None


def register_training_models(
    *,
    tracking: TrainingTrackingResult,
    source_manifest: ArtifactManifestV3,
    gateway: RegistryGateway,
    policy: RegistryPolicy,
) -> RegistryRegistrationResult:
    if tracking.source_artifact_id != source_manifest.artifact_id:
        raise MLflowIntegrityError("Tracking result artifact ID does not match manifest")
    if tracking.source_manifest_sha256 != source_manifest.manifest_sha256:
        raise MLflowIntegrityError("Tracking result manifest hash does not match source")

    model_name = policy.registered_model_name
    gateway.ensure_registered_model(
        model_name,
        "Governed Home Credit binary credit-risk predictor. "
        "Versions are linked to immutable ResearchOps artifacts.",
    )
    existing_versions = gateway.list_versions(model_name)
    results: list[RegisteredModelVersion] = []

    for tracked in tracking.models:
        require_canonical_logged_model_uri(tracked.model_uri)
        candidate_status = "SELECTED" if tracked.selected_as_best else "ELIGIBLE"
        tags = {
            "researchops.project": "llm-xai",
            "researchops.source_artifact_id": source_manifest.artifact_id,
            "researchops.source_manifest_sha256": source_manifest.manifest_sha256,
            "researchops.source_manifest_verified": "PASSED",
            "researchops.source_commit": source_manifest.source.source_commit,
            "researchops.stage_registry_sha256": source_manifest.producer.registry_sha256,
            "researchops.tracking_key": tracked.tracking_key,
            "researchops.model_name": tracked.model_name,
            "researchops.candidate_status": candidate_status,
            "researchops.gate_status": "PENDING",
            "researchops.registry_record_status": "ACTIVE",
            "researchops.model_uri_contract": "mlflow3_logged_model_id_v1",
        }
        existing = _find_existing(existing_versions, tracked.tracking_key)
        if existing is not None and (
            existing.run_id != tracked.run_id or existing.source != tracked.model_uri
        ):
            legacy_source_migration = (
                existing.run_id == tracked.run_id
                and is_historical_run_model_uri(existing.source)
                and is_canonical_logged_model_uri(tracked.model_uri)
            )
            if not legacy_source_migration:
                raise MLflowIntegrityError(
                    f"Existing version {existing.version} does not match its tracked run"
                )
            gateway.set_version_tags(
                model_name,
                existing.version,
                {
                    "researchops.registry_record_status": "SUPERSEDED_SOURCE_URI",
                    "researchops.candidate_status": "SUPERSEDED",
                    "researchops.superseded_by_model_uri": tracked.model_uri,
                },
            )
            existing = None
        reused = existing is not None
        if existing is None:
            current = gateway.create_version(
                model_name,
                source=tracked.model_uri,
                run_id=tracked.run_id,
                description=(
                    f"{tracked.model_name} produced from immutable artifact "
                    f"{source_manifest.artifact_id}."
                ),
                tags=tags,
            )
            existing_versions = (*existing_versions, current)
        else:
            for key in (
                "researchops.source_artifact_id",
                "researchops.source_manifest_sha256",
            ):
                observed = existing.tags.get(key)
                if observed not in {None, tags[key]}:
                    raise MLflowIntegrityError(
                        f"Model version {existing.version} has conflicting {key}"
                    )
            gateway.set_version_tags(model_name, existing.version, tags)
            current = gateway.get_version(model_name, existing.version) or existing

        aliases: tuple[str, ...] = ()
        if tracked.selected_as_best:
            previous_candidate = gateway.alias_version(model_name, "candidate")
            if previous_candidate is not None and previous_candidate != current.version:
                gateway.set_version_tags(
                    model_name,
                    previous_candidate,
                    {"researchops.candidate_status": "SUPERSEDED"},
                )
            gateway.set_alias(model_name, "candidate", current.version)
            aliases = ("candidate",)
            gateway.set_run_tags(
                tracked.run_id,
                {
                    "researchops.model_version": current.version,
                    "researchops.candidate_status": "SELECTED",
                    "researchops.integration_state": "CANDIDATE_EVALUATED",
                },
            )
        else:
            gateway.set_run_tags(
                tracked.run_id,
                {
                    "researchops.model_version": current.version,
                    "researchops.candidate_status": "ELIGIBLE",
                    "researchops.integration_state": "MODEL_VERSION_REGISTERED",
                },
            )
        results.append(
            RegisteredModelVersion(
                model_name=tracked.model_name,
                run_id=tracked.run_id,
                model_uri=tracked.model_uri,
                tracking_key=tracked.tracking_key,
                version=current.version,
                selected_as_best=tracked.selected_as_best,
                reused=reused,
                aliases=aliases,
            )
        )

    candidate = next(item for item in results if item.selected_as_best)
    if gateway.alias_version(model_name, "candidate") != candidate.version:
        raise MLflowIntegrityError("Candidate alias assignment did not persist")
    return RegistryRegistrationResult(
        registered_model_name=model_name,
        source_artifact_id=source_manifest.artifact_id,
        source_manifest_sha256=source_manifest.manifest_sha256,
        versions=tuple(results),
    )
