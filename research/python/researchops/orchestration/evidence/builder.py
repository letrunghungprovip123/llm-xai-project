from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from research.python.researchops.artifacts.models import (
    ArtifactParent,
    ArtifactProducer,
    ArtifactSource,
)
from research.python.researchops.artifacts.package_builder import ArtifactPackageBuilder
from research.python.researchops.artifacts.stores.base import ArtifactStore
from research.python.researchops.ops_core.repositories.protocols import OpsRepository
from research.python.researchops.ops_core.services.artifact_registration import (
    ArtifactRegistrationService,
)

from ..execution.contracts import (
    PipelineExecutionReceipt,
    ReceiptArtifactIdentity,
    StageExecutionResult,
)
from ..execution.redaction import redact_mapping, redact_text
from ..reporting import write_json_report


def _parents(
    manifests: Iterable[tuple[str, str]],
    *,
    relationship: str,
) -> list[ArtifactParent]:
    return [
        ArtifactParent(
            artifact_id=artifact_id,
            manifest_sha256=manifest_sha256,
            relationship=relationship,
        )
        for artifact_id, manifest_sha256 in sorted(set(manifests))
    ]


def build_stage_execution_evidence(
    *,
    directory: Path,
    result: StageExecutionResult,
    command_payload: Mapping[str, Any],
    environment_payload: Mapping[str, Any],
    inputs_payload: Mapping[str, Any],
    outputs_payload: Mapping[str, Any],
    stdout_text: str,
    stderr_text: str,
    source_commit: str,
    environment_snapshot_id: str,
    registry_sha256: str,
    parent_manifests: Iterable[tuple[str, str]],
    artifact_store: ArtifactStore,
    repository: OpsRepository,
    actor: str,
) -> tuple[str, str]:
    evidence_dir = directory / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    write_json_report(
        evidence_dir / "command.json", redact_mapping(command_payload)
    )
    write_json_report(
        evidence_dir / "environment.json", redact_mapping(environment_payload)
    )
    write_json_report(evidence_dir / "inputs.json", redact_mapping(inputs_payload))
    write_json_report(evidence_dir / "outputs.json", redact_mapping(outputs_payload))
    write_json_report(
        evidence_dir / "result.json", result.model_dump(mode="json")
    )
    (evidence_dir / "stdout.log").write_text(
        redact_text(stdout_text), encoding="utf-8"
    )
    (evidence_dir / "stderr.log").write_text(
        redact_text(stderr_text), encoding="utf-8"
    )

    package = (
        ArtifactPackageBuilder(
            artifact_type="stage_execution_evidence",
            schema_version="stage_execution_evidence_v1",
            producer=ArtifactProducer(
                stage_id=result.stage_id,
                stage_version=result.stage_version,
                stage_run_id=result.stage_run_id,
                registry_sha256=registry_sha256,
            ),
            source=ArtifactSource(
                source_commit=source_commit,
                environment_snapshot_id=environment_snapshot_id,
            ),
            parents=_parents(parent_manifests, relationship="execution_input"),
            metadata={
                "pipeline_run_id": result.pipeline_run_id,
                "node_id": result.node_id,
                "stage_id": result.stage_id,
                "attempt": result.attempt,
                "status": result.status,
                "orchestration_key": result.orchestration_key,
            },
        )
        .add_directory(evidence_dir)
        .build()
    )
    reference = artifact_store.put_package(package)
    registration = ArtifactRegistrationService(repository, artifact_store)
    registration.register(reference.artifact_id, actor=actor)
    return reference.artifact_id, reference.manifest_sha256


def build_pipeline_execution_receipt(
    *,
    directory: Path,
    flow_id: str,
    flow_version: int,
    flow_catalog_sha256: str,
    stage_registry_sha256: str,
    prefect_flow_run_id: str,
    pipeline_run_id: str,
    source_commit: str,
    environment_snapshot_id: str,
    terminal_status: str,
    inputs: Mapping[str, Mapping[str, str]],
    outputs: Mapping[str, Mapping[str, str]],
    stage_results: Iterable[StageExecutionResult],
    terminal_stage_id: str,
    terminal_stage_version: int,
    terminal_stage_run_id: str,
    artifact_store: ArtifactStore,
    repository: OpsRepository,
    actor: str,
) -> tuple[str, str]:
    receipt_dir = directory / "pipeline-receipt"
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt = PipelineExecutionReceipt(
        flow_id=flow_id,
        flow_version=flow_version,
        flow_catalog_sha256=flow_catalog_sha256,
        stage_registry_sha256=stage_registry_sha256,
        prefect_flow_run_id=prefect_flow_run_id,
        pipeline_run_id=pipeline_run_id,
        source_commit=source_commit,
        environment_snapshot_id=environment_snapshot_id,
        terminal_status=terminal_status,
        inputs={
            name: ReceiptArtifactIdentity.model_validate(value)
            for name, value in inputs.items()
        },
        outputs={
            name: ReceiptArtifactIdentity.model_validate(value)
            for name, value in outputs.items()
        },
        stages=tuple(stage_results),
    )
    receipt_path = receipt_dir / "pipeline_execution_receipt.json"
    write_json_report(receipt_path, receipt.model_dump(mode="json"))

    parent_ids: list[tuple[str, str]] = []
    for group in (inputs, outputs):
        for item in group.values():
            if item.get("artifact_id") and item.get("manifest_sha256"):
                parent_ids.append((item["artifact_id"], item["manifest_sha256"]))

    package = (
        ArtifactPackageBuilder(
            artifact_type="pipeline_execution_receipt",
            schema_version="pipeline_execution_receipt_v1",
            producer=ArtifactProducer(
                stage_id=terminal_stage_id,
                stage_version=terminal_stage_version,
                stage_run_id=terminal_stage_run_id,
                registry_sha256=stage_registry_sha256,
            ),
            source=ArtifactSource(
                source_commit=source_commit,
                environment_snapshot_id=environment_snapshot_id,
            ),
            parents=_parents(parent_ids, relationship="pipeline_evidence"),
            metadata={
                "flow_id": flow_id,
                "pipeline_run_id": pipeline_run_id,
                "prefect_flow_run_id": prefect_flow_run_id,
                "terminal_status": terminal_status,
            },
        )
        .add_file(
            receipt_path,
            relative_path="pipeline_execution_receipt.json",
            media_type="application/json",
        )
        .build()
    )
    reference = artifact_store.put_package(package)
    ArtifactRegistrationService(repository, artifact_store).register(
        reference.artifact_id, actor=actor
    )
    return reference.artifact_id, reference.manifest_sha256
