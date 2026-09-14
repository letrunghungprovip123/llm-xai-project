from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from research.python.researchops.artifacts.models import ArtifactProducer, ArtifactSource
from research.python.researchops.artifacts.package_builder import ArtifactPackageBuilder
from research.python.researchops.artifacts.stores.filesystem import FilesystemArtifactStore
from research.python.researchops.ops_core.db.base import Base
from research.python.researchops.ops_core.repositories.sqlalchemy import SqlAlchemyOpsRepository
from research.python.researchops.ops_core.services.artifact_registration import ArtifactRegistrationService
from research.python.researchops.orchestration.execution.contracts import (
    DiscoveredOutput,
    StageExecutionResult,
)
from research.python.researchops.orchestration.execution.errors import PolicyDeniedError
from research.python.researchops.orchestration.approvals.prefect_boundary import PrefectApprovalBoundary
from research.python.researchops.orchestration.identity import stage_orchestration_key
from research.python.researchops.orchestration.ops_bridge.service import OpsBridgeService
from research.python.researchops.orchestration.prefect_adapter import (
    flow_engine as flow_engine_module,
)
from research.python.researchops.orchestration.prefect_adapter.flow_engine import (
    FlowInvocationContext,
    execute_catalog_flow,
    prefect_retry_delay_schedule,
)
from research.python.researchops.orchestration.runtime import OrchestrationRuntime
from research.python.researchops.stage_registry.loader import load_stage_registry


def _runtime(tmp_path: Path) -> OrchestrationRuntime:
    engine = create_engine(f"sqlite:///{tmp_path / 'ops.db'}")
    Base.metadata.create_all(engine)
    return OrchestrationRuntime(
        root=Path.cwd(),
        execution_root=tmp_path / "executions",
        artifact_store=FilesystemArtifactStore(tmp_path / "store"),
        session_factory=sessionmaker(engine, expire_on_commit=False),
    )


def _invocation(run_id: str) -> FlowInvocationContext:
    return FlowInvocationContext(
        prefect_flow_run_id=run_id,
        orchestrator_version="3.7.8",
        deployment_name="prefect-acceptance-fixture/local",
        work_pool_name="researchops-local-process",
        work_queue_name="verification",
    )


def _stage_runner(runtime: OrchestrationRuntime):
    registry = load_stage_registry().by_id()
    registry_sha = json.loads(
        Path("config/platform/generated/stage_registry.lock.json").read_text()
    )["registry_sha256"]

    def run(**kwargs):
        stage = registry[kwargs["stage_id"]]
        stage_key = stage_orchestration_key(
            flow_key=kwargs["flow_orchestration_key"],
            node_id=kwargs["node_id"],
            stage=stage,
            input_artifacts={},
            parameters=kwargs["parameters"],
        )
        with runtime.session_factory() as session:
            repo = SqlAlchemyOpsRepository(session)
            bridge = OpsBridgeService(repo, orchestrator_version="3.7.8")
            handle = bridge.create_or_reuse_stage(
                pipeline_run_id=kwargs["pipeline_run_id"],
                node_id=kwargs["node_id"],
                stage_id=stage.id,
                stage_version=stage.version,
                stage_key=stage_key,
                command_snapshot={
                    "executable": stage.runtime.executable,
                    "args": list(stage.runtime.args),
                },
                approval_policy=stage.behavior.approval_policy,
                prefect_flow_run_id="flow-fixture",
                prefect_task_run_id=f"task-{kwargs['node_id']}",
                deployment_name="local",
                work_pool_name="researchops-local-process",
                work_queue_name=kwargs["work_queue_name"],
            )
            if handle.reused:
                item = handle.outputs[0]
                manifest = runtime.artifact_store.get_manifest(item.artifact_id)
                now = datetime.now(timezone.utc)
                session.commit()
                return StageExecutionResult(
                    pipeline_run_id=kwargs["pipeline_run_id"],
                    stage_run_id=handle.stage_run.id,
                    node_id=kwargs["node_id"],
                    stage_id=stage.id,
                    stage_version=stage.version,
                    status="REUSED",
                    attempt=handle.stage_run.attempt,
                    orchestration_key=stage_key,
                    command=(stage.runtime.executable, *stage.runtime.args),
                    started_at=handle.stage_run.started_at or now,
                    ended_at=handle.stage_run.ended_at or now,
                    exit_code=0,
                    outputs=(
                        DiscoveredOutput(
                            name=item.output_name,
                            contract=item.contract,
                            artifact_id=item.artifact_id,
                            manifest_sha256=item.manifest_sha256,
                            file_count=len(manifest.files),
                        ),
                    ),
                )
            bridge.transition_stage(handle.stage_run, "RUNNING")
            source = runtime.execution_root / kwargs["pipeline_run_id"] / "fixture.json"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text('{"passed":true}\n', encoding="utf-8")
            artifact_id = "artifact_orchestration_acceptance_result_01J00000000000000000000001"
            package = (
                ArtifactPackageBuilder(
                    artifact_id=artifact_id,
                    artifact_type="orchestration_acceptance_result",
                    schema_version="orchestration_acceptance_result_v1",
                    producer=ArtifactProducer(
                        stage_id=stage.id,
                        stage_version=stage.version,
                        stage_run_id=handle.stage_run.id,
                        registry_sha256=registry_sha,
                    ),
                    source=ArtifactSource(source_commit=kwargs["source_commit"]),
                    metadata={"environment_snapshot_id": kwargs["environment_snapshot_id"]},
                )
                .add_file(source, relative_path="orchestration_acceptance_result.json")
                .build()
            )
            runtime.artifact_store.put_package(package)
            ArtifactRegistrationService(repo, runtime.artifact_store).register(
                artifact_id, actor="test"
            )
            bridge.record_stage_output(
                stage_run_id=handle.stage_run.id,
                output_name="result",
                contract="orchestration_acceptance_result",
                artifact_id=artifact_id,
                manifest_sha256=package.manifest.manifest_sha256,
            )
            bridge.transition_stage(handle.stage_run, "SUCCEEDED", exit_code=0)
            session.commit()
            now = datetime.now(timezone.utc)
            return StageExecutionResult(
                pipeline_run_id=kwargs["pipeline_run_id"],
                stage_run_id=handle.stage_run.id,
                node_id=kwargs["node_id"],
                stage_id=stage.id,
                stage_version=stage.version,
                status="SUCCEEDED",
                attempt=handle.stage_run.attempt,
                orchestration_key=stage_key,
                command=(stage.runtime.executable, *stage.runtime.args),
                started_at=now,
                ended_at=now,
                exit_code=0,
                outputs=(
                    DiscoveredOutput(
                        name="result",
                        contract="orchestration_acceptance_result",
                        artifact_id=artifact_id,
                        manifest_sha256=package.manifest.manifest_sha256,
                        file_count=1,
                    ),
                ),
            )

    return run


def test_flow_engine_creates_receipt_and_reuses_completed_flow(tmp_path: Path):
    runtime = _runtime(tmp_path)
    first = execute_catalog_flow(
        flow_id="prefect_acceptance_fixture",
        parameters={"enable_acceptance_fixture": True, "simulation": "normal"},
        runtime=runtime,
        invocation=_invocation("flow-fixture"),
        stage_runner=_stage_runner(runtime),
        requested_by="test",
    )
    assert first.status == "SUCCEEDED"
    assert first.reused is False
    assert first.receipt is not None
    assert runtime.artifact_store.verify(first.receipt.artifact_id).passed
    assert set(first.outputs) == {"orchestration_acceptance_result"}

    second = execute_catalog_flow(
        flow_id="prefect_acceptance_fixture",
        parameters={"enable_acceptance_fixture": True, "simulation": "normal"},
        runtime=runtime,
        invocation=_invocation("flow-fixture-retry"),
        stage_runner=_stage_runner(runtime),
        requested_by="test",
    )
    assert second.status == "REUSED"
    assert second.reused is True
    assert second.pipeline_run_id == first.pipeline_run_id
    assert second.receipt == first.receipt


def test_protected_flow_fails_closed_without_approval_boundary(tmp_path: Path):
    runtime = _runtime(tmp_path)
    with pytest.raises(PolicyDeniedError, match="approval boundary"):
        execute_catalog_flow(
            flow_id="prefect_approval_acceptance_fixture",
            parameters={"enable_approval_acceptance": True, "simulation": "normal"},
            runtime=runtime,
            invocation=_invocation("protected-flow"),
            stage_runner=_stage_runner(runtime),
            requested_by="test",
        )
    with runtime.session_factory() as session:
        repo = SqlAlchemyOpsRepository(session)
        runs = repo.list_pipeline_runs()
        assert len(runs) == 1
        assert runs[0].status == "FAILED"


def test_prefect_suspend_control_signal_preserves_waiting_approval_state(tmp_path: Path):
    runtime = _runtime(tmp_path)

    Pause = type("Pause", (BaseException,), {})
    Pause.__module__ = "prefect.exceptions"

    def suspend(**kwargs):
        del kwargs
        raise Pause()

    boundary = PrefectApprovalBoundary(
        runtime,
        suspend_callable=suspend,
        prefect_flow_run_id="suspended-prefect-flow",
    )
    with pytest.raises(Pause):
        execute_catalog_flow(
            flow_id="prefect_approval_acceptance_fixture",
            parameters={"enable_approval_acceptance": True, "simulation": "normal"},
            runtime=runtime,
            invocation=_invocation("suspended-prefect-flow"),
            stage_runner=_stage_runner(runtime),
            approval_boundary=boundary,
            requested_by="test",
        )
    with runtime.session_factory() as session:
        repo = SqlAlchemyOpsRepository(session)
        pipeline = repo.list_pipeline_runs()[0]
        assert pipeline.status == "WAITING_APPROVAL"
        assert repo.list_approvals(status="REQUESTED")[0].pipeline_run_id == pipeline.id


def test_non_pause_prefect_error_does_not_preserve_waiting_approval(tmp_path: Path):
    runtime = _runtime(tmp_path)

    ValidationError = type("ValidationError", (RuntimeError,), {})
    ValidationError.__module__ = "prefect.input.run_input"

    def suspend(**kwargs):
        del kwargs
        raise ValidationError("invalid FlowRunInput key")

    boundary = PrefectApprovalBoundary(
        runtime,
        suspend_callable=suspend,
        prefect_flow_run_id="invalid-prefect-input-flow",
    )
    with pytest.raises(ValidationError, match="invalid FlowRunInput key"):
        execute_catalog_flow(
            flow_id="prefect_approval_acceptance_fixture",
            parameters={"enable_approval_acceptance": True, "simulation": "normal"},
            runtime=runtime,
            invocation=_invocation("invalid-prefect-input-flow"),
            stage_runner=_stage_runner(runtime),
            approval_boundary=boundary,
            requested_by="test",
        )
    with runtime.session_factory() as session:
        repo = SqlAlchemyOpsRepository(session)
        pipeline = repo.list_pipeline_runs()[0]
        assert pipeline.status == "FAILED"
        assert "invalid FlowRunInput key" in (pipeline.error_summary or "")


def test_prefect_retry_delay_schedule_uses_supported_list_contract():
    assert prefect_retry_delay_schedule(0) is None
    assert prefect_retry_delay_schedule(-1) is None

    one_retry = prefect_retry_delay_schedule(1)
    multiple_retries = prefect_retry_delay_schedule(3)

    assert one_retry == [5]
    assert multiple_retries == [5, 10, 15]
    assert isinstance(one_retry, list)
    assert isinstance(multiple_retries, list)
    assert not isinstance(multiple_retries, tuple)


def test_default_stage_runner_passes_prefect_compatible_retry_delay_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    runtime = _runtime(tmp_path)
    delegate = _stage_runner(runtime)
    observed: dict[str, object] = {}

    class FakeTask:
        def with_options(self, **options):
            observed.update(options)
            return delegate

    monkeypatch.setattr(flow_engine_module, "_build_stage_task", lambda: FakeTask())

    result = execute_catalog_flow(
        flow_id="prefect_acceptance_fixture",
        parameters={"enable_acceptance_fixture": True, "simulation": "normal"},
        runtime=runtime,
        invocation=_invocation("flow-prefect-retry-options"),
        requested_by="test",
    )

    assert result.status == "SUCCEEDED"
    assert observed["retries"] == 2
    assert observed["retry_delay_seconds"] == [5, 10]
    assert isinstance(observed["retry_delay_seconds"], list)
