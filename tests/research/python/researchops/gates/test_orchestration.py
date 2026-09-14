from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from research.python.researchops.artifacts.models import (
    ArtifactParent,
    ArtifactProducer,
    ArtifactSource,
)
from research.python.researchops.artifacts.package_builder import ArtifactPackageBuilder
from research.python.researchops.artifacts.stores.filesystem import FilesystemArtifactStore
from research.python.researchops.ops_core.db.base import Base
from research.python.researchops.ops_core.db.models import (
    EnvironmentSnapshot,
    PipelineRun,
    StageRun,
)
from research.python.researchops.ops_core.repositories.sqlalchemy import SqlAlchemyOpsRepository
from research.python.researchops.ops_core.services.artifact_registration import (
    ArtifactRegistrationService,
)
from research.python.researchops.gates.orchestration import SemanticGateOrchestrator
from research.python.researchops.orchestration.execution.contracts import DiscoveredOutput
from research.python.researchops.orchestration.execution.errors import SchemaContractError
from research.python.researchops.stage_registry.loader import load_stage_registry

ENV_ID = "env_01J00000000000000000000000"
RUN_ID = "run_01J00000000000000000000000"
STAGE_RUN_ID = "stage_run_01J00000000000000000000000"
REGISTRY_SHA = "a" * 64
SOURCE_COMMIT = "b" * 40


def _seed_run(repo: SqlAlchemyOpsRepository, stage_id: str, stage_version: int) -> None:
    repo.add_environment_snapshot(
        EnvironmentSnapshot(
            id=ENV_ID,
            python_version="3.13",
            node_version="v22",
            operating_system="test",
            architecture="arm64",
            dependency_lock_sha256="c" * 64,
            git_commit=SOURCE_COMMIT,
            git_dirty=False,
            details={},
        )
    )
    repo.add_pipeline_run(
        PipelineRun(
            id=RUN_ID,
            flow_id="test_flow",
            status="RUNNING",
            trigger_type="TEST",
            requested_by="test",
            registry_sha256=REGISTRY_SHA,
            source_commit=SOURCE_COMMIT,
            environment_snapshot_id=ENV_ID,
            idempotency_key="test-run",
            parameters={},
        )
    )
    repo.add_stage_run(
        StageRun(
            id=STAGE_RUN_ID,
            pipeline_run_id=RUN_ID,
            stage_id=stage_id,
            stage_version=stage_version,
            attempt=1,
            status="RUNNING",
            command_snapshot={},
            approval_policy="NONE",
        )
    )
    repo.flush()


def _put_artifact(
    *,
    root: Path,
    store: FilesystemArtifactStore,
    repo: SqlAlchemyOpsRepository,
    artifact_type: str,
    stage_id: str,
    stage_version: int,
    relative_path: str,
    payload: dict | list,
    parents: tuple[tuple[str, str], ...] = (),
):
    source = root / "source" / artifact_type / relative_path
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(json.dumps(payload), encoding="utf-8")
    builder = ArtifactPackageBuilder(
        artifact_type=artifact_type,
        schema_version=f"{artifact_type}_v1",
        producer=ArtifactProducer(
            stage_id=stage_id,
            stage_version=stage_version,
            stage_run_id=STAGE_RUN_ID,
            registry_sha256=REGISTRY_SHA,
        ),
        source=ArtifactSource(
            source_commit=SOURCE_COMMIT,
            environment_snapshot_id=ENV_ID,
        ),
        parents=[
            ArtifactParent(
                artifact_id=artifact_id,
                manifest_sha256=manifest_sha,
                relationship="derived_from",
            )
            for artifact_id, manifest_sha in parents
        ],
    ).add_file(source, relative_path=f"payload/{relative_path}")
    reference = store.put_package(builder.build())
    ArtifactRegistrationService(repo, store).register(reference.artifact_id, actor="test")
    return reference


def _output(name: str, contract: str, reference) -> DiscoveredOutput:
    return DiscoveredOutput(
        name=name,
        contract=contract,
        artifact_id=reference.artifact_id,
        manifest_sha256=reference.manifest_sha256,
        file_count=1,
    )


def test_semantic_evaluation_records_artifact_and_stage_run_projection(
    tmp_path: Path,
) -> None:
    stage = load_stage_registry().by_id()["ml.model_ready_audit"]
    engine = create_engine(f"sqlite:///{tmp_path / 'ops.db'}")
    Base.metadata.create_all(engine)
    store = FilesystemArtifactStore(tmp_path / "store")
    with Session(engine) as session:
        repo = SqlAlchemyOpsRepository(session)
        _seed_run(repo, stage.id, stage.version)
        reference = _put_artifact(
            root=tmp_path,
            store=store,
            repo=repo,
            artifact_type="model_ready_report",
            stage_id=stage.id,
            stage_version=stage.version,
            relative_path="data/manifests/model_ready_audit_manifest.json",
            payload={"status": "passed", "error_count": 0, "errors": []},
        )
        result = SemanticGateOrchestrator(
            repository=repo, artifact_store=store, actor="test"
        ).evaluate_stage_success(
            stage=stage,
            outputs=(_output("audit", "model_ready_report", reference),),
            pipeline_run_id=RUN_ID,
            stage_run_id=STAGE_RUN_ID,
        )
        assert result.evaluation.outcome == "PASSED"
        artifact_gate = repo.get_gate_result("MODEL_READY", "artifact", reference.artifact_id)
        stage_gate = repo.get_gate_result("MODEL_READY", "stage_run", STAGE_RUN_ID)
        assert artifact_gate is not None and artifact_gate.effective_status == "PASSED"
        assert stage_gate is not None and stage_gate.effective_status == "PASSED"
        assert stage_gate.current_evaluation_id != artifact_gate.current_evaluation_id


def test_semantic_failure_is_persisted_and_fails_the_stage(tmp_path: Path) -> None:
    stage = load_stage_registry().by_id()["ml.model_ready_audit"]
    engine = create_engine(f"sqlite:///{tmp_path / 'ops.db'}")
    Base.metadata.create_all(engine)
    store = FilesystemArtifactStore(tmp_path / "store")
    with Session(engine) as session:
        repo = SqlAlchemyOpsRepository(session)
        _seed_run(repo, stage.id, stage.version)
        reference = _put_artifact(
            root=tmp_path,
            store=store,
            repo=repo,
            artifact_type="model_ready_report",
            stage_id=stage.id,
            stage_version=stage.version,
            relative_path="data/manifests/model_ready_audit_manifest.json",
            payload={"status": "blocked", "error_count": 1, "errors": ["bad"]},
        )
        with pytest.raises(SchemaContractError, match="Semantic gate failed"):
            SemanticGateOrchestrator(
                repository=repo, artifact_store=store, actor="test"
            ).evaluate_stage_success(
                stage=stage,
                outputs=(_output("audit", "model_ready_report", reference),),
                pipeline_run_id=RUN_ID,
                stage_run_id=STAGE_RUN_ID,
            )
        projection = repo.get_gate_result("MODEL_READY", "artifact", reference.artifact_id)
        assert projection is not None
        assert projection.effective_status == "FAILED"


def test_mlflow_receipt_projects_current_lineage_gates_to_model_version(
    tmp_path: Path,
) -> None:
    stages = load_stage_registry().by_id()
    model_stage = stages["ml.train"]
    ready_stage = stages["ml.model_ready_audit"]
    xai_stage = stages["xai.quality"]
    receipt_stage = stages["ops.mlflow_register"]
    engine = create_engine(f"sqlite:///{tmp_path / 'ops.db'}")
    Base.metadata.create_all(engine)
    store = FilesystemArtifactStore(tmp_path / "store")
    with Session(engine) as session:
        repo = SqlAlchemyOpsRepository(session)
        _seed_run(repo, receipt_stage.id, receipt_stage.version)
        trained = _put_artifact(
            root=tmp_path,
            store=store,
            repo=repo,
            artifact_type="trained_model",
            stage_id=model_stage.id,
            stage_version=model_stage.version,
            relative_path="models/model.bin",
            payload={"model": "binary-placeholder"},
        )
        parent = ((trained.artifact_id, trained.manifest_sha256),)
        ready = _put_artifact(
            root=tmp_path,
            store=store,
            repo=repo,
            artifact_type="model_ready_report",
            stage_id=ready_stage.id,
            stage_version=ready_stage.version,
            relative_path="data/manifests/model_ready_audit_manifest.json",
            payload={"status": "passed", "error_count": 0},
            parents=parent,
        )
        xai = _put_artifact(
            root=tmp_path,
            store=store,
            repo=repo,
            artifact_type="xai_quality_report",
            stage_id=xai_stage.id,
            stage_version=xai_stage.version,
            relative_path="data/manifests/xai_evidence_quality_manifest.json",
            payload={"status": "PASSED", "quality_gates": {"coverage": True}},
            parents=parent,
        )
        orchestrator = SemanticGateOrchestrator(
            repository=repo, artifact_store=store, actor="test"
        )
        orchestrator.evaluate_stage_success(
            stage=ready_stage,
            outputs=(_output("audit", "model_ready_report", ready),),
            pipeline_run_id=RUN_ID,
            stage_run_id=STAGE_RUN_ID,
        )
        orchestrator.evaluate_stage_success(
            stage=xai_stage,
            outputs=(_output("quality", "xai_quality_report", xai),),
            pipeline_run_id=RUN_ID,
            stage_run_id=STAGE_RUN_ID,
        )
        receipt_payload = {
            "schema_name": "mlflow_registration_receipt_v1",
            "source_model_artifact_id": trained.artifact_id,
            "registered_model_name": "credit-risk",
            "candidate_version": "3",
            "versions": [
                {"version": "1", "selected_as_best": False},
                {"version": "2", "selected_as_best": False},
                {"version": "3", "selected_as_best": True},
            ],
        }
        receipt = _put_artifact(
            root=tmp_path,
            store=store,
            repo=repo,
            artifact_type="mlflow_registration_receipt",
            stage_id=receipt_stage.id,
            stage_version=receipt_stage.version,
            relative_path="mlflow_registration_receipt.json",
            payload=receipt_payload,
            parents=parent,
        )
        orchestrator.evaluate_stage_success(
            stage=receipt_stage,
            outputs=(
                _output("receipt", "mlflow_registration_receipt", receipt),
            ),
            pipeline_run_id=RUN_ID,
            stage_run_id=STAGE_RUN_ID,
        )
        target = "credit-risk:3"
        for gate_id in (
            "MODEL_READY",
            "XAI_QUALITY_READY",
            "MLFLOW_MODEL_REGISTERED",
        ):
            projection = repo.get_gate_result(gate_id, "model_version", target)
            assert projection is not None, gate_id
            assert projection.effective_status == "PASSED"
            evaluation = repo.get_gate_evaluation(projection.current_evaluation_id)
            assert evaluation is not None
            assert evaluation.source_evaluation_ids


def test_failed_scientific_report_is_persisted_from_execution_evidence(
    tmp_path: Path,
) -> None:
    stage = load_stage_registry().by_id()["ml.model_ready_audit"]
    engine = create_engine(f"sqlite:///{tmp_path / 'failure-evidence.db'}")
    Base.metadata.create_all(engine)
    store = FilesystemArtifactStore(tmp_path / "failure-store")
    with Session(engine) as session:
        repo = SqlAlchemyOpsRepository(session)
        _seed_run(repo, stage.id, stage.version)
        report = (
            tmp_path
            / "failure-source"
            / "scientific_failure"
            / "data"
            / "manifests"
            / "model_ready_audit_manifest.json"
        )
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            json.dumps(
                {
                    "status": "blocked",
                    "error_count": 1,
                    "errors": ["model quality threshold failed"],
                }
            ),
            encoding="utf-8",
        )
        package = (
            ArtifactPackageBuilder(
                artifact_type="stage_execution_evidence",
                schema_version="stage_execution_evidence_v1",
                producer=ArtifactProducer(
                    stage_id=stage.id,
                    stage_version=stage.version,
                    stage_run_id=STAGE_RUN_ID,
                    registry_sha256=REGISTRY_SHA,
                ),
                source=ArtifactSource(
                    source_commit=SOURCE_COMMIT,
                    environment_snapshot_id=ENV_ID,
                ),
            )
            .add_file(
                report,
                relative_path=(
                    "scientific_failure/data/manifests/"
                    "model_ready_audit_manifest.json"
                ),
            )
            .build()
        )
        reference = store.put_package(package)
        ArtifactRegistrationService(repo, store).register(
            reference.artifact_id, actor="test"
        )
        result = SemanticGateOrchestrator(
            repository=repo, artifact_store=store, actor="test"
        ).evaluate_stage_failure(
            stage=stage,
            evidence_artifact_id=reference.artifact_id,
            pipeline_run_id=RUN_ID,
            stage_run_id=STAGE_RUN_ID,
        )
        assert result is not None
        assert result.evaluation.outcome == "FAILED"
        assert result.evaluation.evidence_artifact_id == reference.artifact_id
        projection = repo.get_gate_result(
            "MODEL_READY", "stage_run", STAGE_RUN_ID
        )
        assert projection is not None
        assert projection.effective_status == "FAILED"
        assert projection.current_evaluation_id == result.evaluation.id
