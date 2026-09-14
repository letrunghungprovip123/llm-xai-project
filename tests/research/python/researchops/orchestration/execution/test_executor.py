from __future__ import annotations

import json
from pathlib import Path

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
from research.python.researchops.ops_core.db.models import EnvironmentSnapshot
from research.python.researchops.ops_core.repositories.sqlalchemy import SqlAlchemyOpsRepository
from research.python.researchops.ops_core.services.artifact_registration import ArtifactRegistrationService
from research.python.researchops.orchestration.execution.executor import StageExecutor
from research.python.researchops.orchestration.ops_bridge.service import OpsBridgeService
from research.python.researchops.stage_registry.loader import load_stage_registry


def test_executor_uses_argument_list_allowlist_and_registers_evidence(tmp_path: Path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    script = project / "write_receipt.py"
    script.write_text(
        """from pathlib import Path\nimport json, os\np=Path('artifacts/researchops/test/mlflow_registration_receipt.json')\np.parent.mkdir(parents=True, exist_ok=True)\np.write_text(json.dumps({'leaked': 'RESEARCHOPS_TEST_LEAK' in os.environ, 'stage': os.environ['RESEARCHOPS_STAGE_ID']})+'\\n')\n""",
        encoding="utf-8",
    )
    monkeypatch.setenv("RESEARCHOPS_TEST_LEAK", "must-not-pass")

    engine = create_engine(f"sqlite:///{tmp_path / 'ops.db'}")
    Base.metadata.create_all(engine)
    store = FilesystemArtifactStore(tmp_path / "store")
    registry_sha = json.loads(
        Path("config/platform/generated/stage_registry.lock.json").read_text()
    )["registry_sha256"]
    input_file = tmp_path / "model.joblib"
    input_file.write_bytes(b"portable-model")
    input_package = (
        ArtifactPackageBuilder(
            artifact_id="artifact_trained_model_01J00000000000000000000000",
            artifact_type="trained_model",
            schema_version="trained_model_v1",
            producer=ArtifactProducer(
                stage_id="ops.mlflow_register",
                stage_version=1,
                stage_run_id=None,
                registry_sha256=registry_sha,
            ),
            source=ArtifactSource(source_commit="a" * 40),
        )
        .add_file(input_file, relative_path="models/model.joblib")
        .build()
    )
    store.put_package(input_package)

    with Session(engine) as session:
        repo = SqlAlchemyOpsRepository(session)
        ArtifactRegistrationService(repo, store).register(
            input_package.manifest.artifact_id, actor="test"
        )
        environment = EnvironmentSnapshot(
            id="env_01J00000000000000000000000",
            python_version="3.12",
            operating_system="test",
            architecture="arm64",
            dependency_lock_sha256="b" * 64,
            git_commit="a" * 40,
            git_dirty=False,
            details={},
        )
        bridge = OpsBridgeService(repo, orchestrator_version="3.7.8")
        bridge.persist_environment(environment)
        pipeline = bridge.create_or_reuse_pipeline(
            flow_id="register_verified_training_release",
            flow_key="c" * 64,
            flow_catalog_sha256="d" * 64,
            source_commit="a" * 40,
            environment_snapshot_id=environment.id,
            parameters={},
            requested_by="test",
            trigger_type="TEST",
            prefect_flow_run_id="flow-test",
            deployment_name="test",
            work_pool_name="pool",
            work_queue_name="release",
        )
        stage = load_stage_registry().by_id()["ops.mlflow_register"]
        stage = stage.model_copy(
            update={
                "runtime": stage.runtime.model_copy(
                    update={"args": (str(script),), "working_directory": "."}
                ),
                "secrets": (),
            }
        )
        stage_handle = bridge.create_or_reuse_stage(
            pipeline_run_id=pipeline.pipeline_run.id,
            node_id="mlflow_register",
            stage_id=stage.id,
            stage_version=stage.version,
            stage_key="e" * 64,
            command_snapshot={},
            approval_policy="NONE",
            prefect_flow_run_id="flow-test",
            prefect_task_run_id="task-test",
            deployment_name="test",
            work_pool_name="pool",
            work_queue_name="release",
        )
        bridge.transition_stage(stage_handle.stage_run, "RUNNING")
        session.commit()

        result = StageExecutor(
            repository=repo,
            artifact_store=store,
            ops_bridge=bridge,
            project_root=project,
            execution_root=tmp_path / "executions",
            actor="test",
        ).execute(
            stage=stage,
            node_id="mlflow_register",
            pipeline_run_id=pipeline.pipeline_run.id,
            stage_run_id=stage_handle.stage_run.id,
            orchestration_key="e" * 64,
            input_artifact_ids={
                "trained_models": input_package.manifest.artifact_id
            },
            parameters={},
            source_commit="a" * 40,
            environment_snapshot_id=environment.id,
            stage_registry_sha256=registry_sha,
            flow_id="register_verified_training_release",
            attempt=1,
        )
        bridge.transition_stage(stage_handle.stage_run, "SUCCEEDED", exit_code=0)
        session.commit()

        assert result.status == "SUCCEEDED"
        assert result.command[0] == "python3"
        assert result.evidence_artifact_id is not None
        assert store.verify(result.evidence_artifact_id).passed
        assert len(result.outputs) == 1
        assert store.verify(result.outputs[0].artifact_id).passed
        generated = json.loads(
            (project / "artifacts/researchops/test/mlflow_registration_receipt.json").read_text()
        )
        assert generated == {"leaked": False, "stage": "ops.mlflow_register"}
        execution_gate = repo.get_gate_result(
            "STAGE_EXECUTION_SUCCEEDED", "stage_run", stage_handle.stage_run.id
        )
        assert execution_gate is not None
        assert execution_gate.status == "PASSED"
        assert execution_gate.details["semantic_gate"] == "MLFLOW_MODEL_REGISTERED"
        assert repo.get_gate_result(
            "MLFLOW_MODEL_REGISTERED", "stage_run", stage_handle.stage_run.id
        ) is None


def test_executor_links_canonical_referenced_output_without_repackaging(
    tmp_path: Path,
    monkeypatch,
):
    project = tmp_path / "project"
    project.mkdir()
    script = project / "write_stage_report.py"

    engine = create_engine(f"sqlite:///{tmp_path / 'ops-reference.db'}")
    Base.metadata.create_all(engine)
    store = FilesystemArtifactStore(tmp_path / "store-reference")
    registry_sha = "c" * 64
    source_file = tmp_path / "source-model.joblib"
    source_file.write_bytes(b"portable-model")
    source_package = (
        ArtifactPackageBuilder(
            artifact_id="artifact_trained_model_01J00000000000000000000000",
            artifact_type="trained_model",
            schema_version="trained_model_v1",
            producer=ArtifactProducer(
                stage_id="ml.train",
                stage_version=1,
                stage_run_id=None,
                registry_sha256=registry_sha,
            ),
            source=ArtifactSource(source_commit="a" * 40),
        )
        .add_file(source_file, relative_path="models/model.joblib")
        .build()
    )
    store.put_package(source_package)
    receipt_file = tmp_path / "receipt.json"
    receipt_file.write_text('{"schema_version":"mlflow_registration_receipt_v1"}\n')
    receipt_package = (
        ArtifactPackageBuilder(
            artifact_id=(
                "artifact_mlflow_registration_receipt_01J00000000000000000000000"
            ),
            artifact_type="mlflow_registration_receipt",
            schema_version="mlflow_registration_receipt_v1",
            producer=ArtifactProducer(
                stage_id="ops.mlflow_register",
                stage_version=1,
                stage_run_id=None,
                registry_sha256=registry_sha,
            ),
            source=ArtifactSource(source_commit="a" * 40),
            parents=[
                ArtifactParent(
                    artifact_id=source_package.manifest.artifact_id,
                    manifest_sha256=source_package.manifest.manifest_sha256,
                    relationship="derived_from",
                )
            ],
        )
        .add_file(receipt_file, relative_path="receipt.json")
        .build()
    )
    store.put_package(receipt_package)
    script.write_text(
        """from pathlib import Path\nimport json, os\np=Path(os.environ['RESEARCHOPS_REPORT_PATH'])\np.write_text(json.dumps({'schema_version':'stage_command_result_v1','outputs':{'receipt':{'artifact_id':os.environ['TEST_RECEIPT_ID'],'artifact_type':'mlflow_registration_receipt','manifest_sha256':os.environ['TEST_RECEIPT_SHA'],'source_inputs':['trained_models']}},'metadata':{'receipt_reused':True,'api_key':'should-not-persist'}})+'\\n')\n""",
        encoding="utf-8",
    )

    with Session(engine) as session:
        repo = SqlAlchemyOpsRepository(session)
        registration = ArtifactRegistrationService(repo, store)
        registration.register(source_package.manifest.artifact_id, actor="test")
        registration.register(receipt_package.manifest.artifact_id, actor="test")
        environment = EnvironmentSnapshot(
            id="env_01J00000000000000000000000",
            python_version="3.12",
            operating_system="test",
            architecture="arm64",
            dependency_lock_sha256="b" * 64,
            git_commit="a" * 40,
            git_dirty=False,
            details={},
        )
        bridge = OpsBridgeService(repo, orchestrator_version="3.7.8")
        bridge.persist_environment(environment)
        pipeline = bridge.create_or_reuse_pipeline(
            flow_id="register_verified_training_release",
            flow_key="d" * 64,
            flow_catalog_sha256="e" * 64,
            source_commit="a" * 40,
            environment_snapshot_id=environment.id,
            parameters={},
            requested_by="test",
            trigger_type="TEST",
            prefect_flow_run_id="flow-reference",
            deployment_name="test",
            work_pool_name="pool",
            work_queue_name="release",
        )
        stage = load_stage_registry().by_id()["ops.mlflow_register"]
        stage = stage.model_copy(
            update={
                "runtime": stage.runtime.model_copy(
                    update={"args": (str(script),), "working_directory": "."}
                ),
                "secrets": ("TEST_RECEIPT_ID", "TEST_RECEIPT_SHA"),
            }
        )
        monkeypatch.setenv(
            "TEST_RECEIPT_ID", receipt_package.manifest.artifact_id
        )
        monkeypatch.setenv(
            "TEST_RECEIPT_SHA", receipt_package.manifest.manifest_sha256
        )
        stage_handle = bridge.create_or_reuse_stage(
            pipeline_run_id=pipeline.pipeline_run.id,
            node_id="mlflow_register",
            stage_id=stage.id,
            stage_version=stage.version,
            stage_key="f" * 64,
            command_snapshot={},
            approval_policy="NONE",
            prefect_flow_run_id="flow-reference",
            prefect_task_run_id="task-reference",
            deployment_name="test",
            work_pool_name="pool",
            work_queue_name="release",
        )
        bridge.transition_stage(stage_handle.stage_run, "RUNNING")
        session.commit()
        receipt_count_before = len(
            [
                artifact_id
                for artifact_id in store.list_artifact_ids()
                if store.get_manifest(artifact_id).artifact_type
                == "mlflow_registration_receipt"
            ]
        )
        result = StageExecutor(
            repository=repo,
            artifact_store=store,
            ops_bridge=bridge,
            project_root=project,
            execution_root=tmp_path / "executions-reference",
            actor="test",
        ).execute(
            stage=stage,
            node_id="mlflow_register",
            pipeline_run_id=pipeline.pipeline_run.id,
            stage_run_id=stage_handle.stage_run.id,
            orchestration_key="f" * 64,
            input_artifact_ids={
                "trained_models": source_package.manifest.artifact_id
            },
            parameters={},
            source_commit="a" * 40,
            environment_snapshot_id=environment.id,
            stage_registry_sha256=registry_sha,
            flow_id="register_verified_training_release",
            attempt=1,
        )
        receipt_count_after = len(
            [
                artifact_id
                for artifact_id in store.list_artifact_ids()
                if store.get_manifest(artifact_id).artifact_type
                == "mlflow_registration_receipt"
            ]
        )
        bridge.transition_stage(stage_handle.stage_run, "SUCCEEDED", exit_code=0)
        session.commit()
        assert result.outputs[0].artifact_id == receipt_package.manifest.artifact_id
        assert result.metadata["command_result"]["receipt_reused"] is True
        assert result.metadata["command_result"]["api_key"] == "***"
        assert receipt_count_after == receipt_count_before == 1
        assert (
            stage_handle.stage_run.id
            not in repo.succeeded_stage_runs_without_artifacts()
        )
