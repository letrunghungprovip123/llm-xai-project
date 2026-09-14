from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from research.python.researchops.artifacts.stores.filesystem import (
    FilesystemArtifactStore,
)
from research.python.researchops.ops_core.db.base import Base
from research.python.researchops.ops_core.db.models import EnvironmentSnapshot
from research.python.researchops.ops_core.repositories.sqlalchemy import (
    SqlAlchemyOpsRepository,
)
from research.python.researchops.orchestration.flow_catalog.compiler import (
    compile_payload,
)
from research.python.researchops.orchestration.ops_bridge.service import (
    OpsBridgeService,
)
from research.python.researchops.orchestration.reconciliation.gateway import (
    PrefectRuntimeSnapshot,
)
from research.python.researchops.orchestration.reconciliation.models import (
    PrefectFlowRunSnapshot,
    PrefectTaskRunSnapshot,
)
from research.python.researchops.orchestration.reconciliation.service import (
    ReconciliationService,
)
from research.python.researchops.orchestration.runtime import OrchestrationRuntime


class FakeGateway:
    def __init__(self, snapshot: PrefectRuntimeSnapshot) -> None:
        self.value = snapshot

    def snapshot(self) -> PrefectRuntimeSnapshot:
        return self.value


def _runtime(tmp_path: Path) -> OrchestrationRuntime:
    engine = create_engine(f"sqlite:///{tmp_path / 'ops.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    return OrchestrationRuntime(
        root=Path.cwd(),
        execution_root=tmp_path / "executions",
        artifact_store=FilesystemArtifactStore(tmp_path / "store"),
        session_factory=factory,
    )


def _create_pipeline(
    runtime: OrchestrationRuntime,
    *,
    flow_key: str,
    flow_run_id: str,
    parameters: dict | None = None,
    target_status: str = "RUNNING",
) -> str:
    with runtime.session_factory() as session:
        repo = SqlAlchemyOpsRepository(session)
        env = EnvironmentSnapshot(
            id="env_01J00000000000000000000000",
            python_version="3.12",
            operating_system="test",
            architecture="arm64",
            dependency_lock_sha256="a" * 64,
            git_commit="b" * 40,
            git_dirty=False,
            details={},
        )
        bridge = OpsBridgeService(repo, orchestrator_version="3.7.8")
        bridge.persist_environment(env)
        handle = bridge.create_or_reuse_pipeline(
            flow_id="verify_source_environment",
            flow_key=flow_key,
            flow_catalog_sha256=str(compile_payload()["catalog_sha256"]),
            source_commit="b" * 40,
            environment_snapshot_id=env.id,
            parameters=parameters or {},
            requested_by="test",
            trigger_type="TEST",
            prefect_flow_run_id=flow_run_id,
            deployment_name="local",
            work_pool_name="researchops-local-process",
            work_queue_name="verification",
        )
        if target_status != "PENDING":
            bridge.transition_pipeline(handle.pipeline_run, "RUNNING")
        if target_status in {"FAILED", "CANCELLED", "SUCCEEDED"}:
            bridge.transition_pipeline(handle.pipeline_run, target_status)
        session.commit()
        return handle.pipeline_run.id


def _setup(tmp_path: Path):
    runtime = _runtime(tmp_path)
    flow_run_id = "prefect-flow-reconcile"
    pipeline_id = _create_pipeline(
        runtime,
        flow_key="c" * 64,
        flow_run_id=flow_run_id,
    )
    return runtime, pipeline_id, flow_run_id


def _flow_snapshot(
    flow_run_id: str,
    state_name: str,
    acceptance_session: str | None = None,
) -> PrefectFlowRunSnapshot:
    parameters = {}
    if acceptance_session is not None:
        parameters = {
            "parameters": {"acceptance_session": acceptance_session}
        }
    return PrefectFlowRunSnapshot(
        flow_run_id=flow_run_id,
        state_name=state_name,
        parameters=parameters,
    )


def test_clean_running_state_reconciles_without_issues(tmp_path: Path):
    runtime, _, flow_run_id = _setup(tmp_path)
    snapshot = PrefectRuntimeSnapshot(
        flow_runs=(_flow_snapshot(flow_run_id, "RUNNING"),),
        task_runs=(),
    )
    report = ReconciliationService(runtime, FakeGateway(snapshot)).run()
    assert report.passed is True
    assert report.issue_count == 0
    assert report.checked_pipeline_runs == 1


def test_terminal_failure_mismatch_is_reported_then_safely_repaired(
    tmp_path: Path,
):
    runtime, pipeline_id, flow_run_id = _setup(tmp_path)
    snapshot = PrefectRuntimeSnapshot(
        flow_runs=(_flow_snapshot(flow_run_id, "FAILED"),),
        task_runs=(),
    )
    report = ReconciliationService(runtime, FakeGateway(snapshot)).run(
        "report-only"
    )
    issue = next(
        item for item in report.issues if item.code == "FLOW_STATE_MISMATCH"
    )
    assert report.passed is False
    assert issue.repairable is True
    assert issue.repaired is False
    with runtime.session_factory() as session:
        assert (
            SqlAlchemyOpsRepository(session).get_pipeline_run(pipeline_id).status
            == "RUNNING"
        )

    repaired = ReconciliationService(runtime, FakeGateway(snapshot)).run(
        "repair-safe"
    )
    issue = next(
        item for item in repaired.issues if item.code == "FLOW_STATE_MISMATCH"
    )
    assert issue.repaired is True
    assert repaired.passed is True
    with runtime.session_factory() as session:
        assert (
            SqlAlchemyOpsRepository(session).get_pipeline_run(pipeline_id).status
            == "FAILED"
        )


def test_unbound_prefect_flow_fails_closed(tmp_path: Path):
    runtime, _, _ = _setup(tmp_path)
    snapshot = PrefectRuntimeSnapshot(
        flow_runs=(_flow_snapshot("unknown-prefect-flow", "COMPLETED"),),
        task_runs=(),
    )
    report = ReconciliationService(runtime, FakeGateway(snapshot)).run()
    assert report.passed is False
    assert {item.code for item in report.issues} >= {
        "PREFECT_FLOW_WITHOUT_OPS_BINDING",
        "OPS_PIPELINE_PREFECT_RUN_MISSING",
    }


def test_acceptance_session_scope_ignores_historical_runs(tmp_path: Path):
    runtime = _runtime(tmp_path)
    current_session = "phase6-current"
    current_flow = "prefect-current"
    _create_pipeline(
        runtime,
        flow_key="1" * 64,
        flow_run_id=current_flow,
        parameters={
            "acceptance_session": current_session,
            "acceptance_scenario": "normal-idempotency",
        },
    )
    old_flow = "prefect-old"
    _create_pipeline(
        runtime,
        flow_key="2" * 64,
        flow_run_id=old_flow,
        parameters={
            "acceptance_session": "phase6-old",
            "acceptance_scenario": "approval-approve",
        },
        target_status="FAILED",
    )
    snapshot = PrefectRuntimeSnapshot(
        flow_runs=(
            _flow_snapshot(current_flow, "RUNNING", current_session),
            _flow_snapshot(old_flow, "SUSPENDED", "phase6-old"),
            _flow_snapshot("unbound-old", "CANCELLED", "phase6-old"),
        ),
        task_runs=(),
    )

    report = ReconciliationService(
        runtime,
        FakeGateway(snapshot),
        acceptance_session=current_session,
    ).run("report-only")

    assert report.passed is True
    assert report.issue_count == 0
    assert report.checked_pipeline_runs == 1
    assert report.checked_flow_runs == 1


def test_acceptance_session_keeps_unbound_current_flow_as_error(tmp_path: Path):
    runtime = _runtime(tmp_path)
    current_session = "phase6-current"
    snapshot = PrefectRuntimeSnapshot(
        flow_runs=(
            _flow_snapshot(
                "unbound-current",
                "CANCELLED",
                current_session,
            ),
        ),
        task_runs=(),
    )

    report = ReconciliationService(
        runtime,
        FakeGateway(snapshot),
        acceptance_session=current_session,
    ).run("report-only")

    assert report.passed is False
    assert report.checked_flow_runs == 1
    assert {item.code for item in report.issues} == {
        "PREFECT_FLOW_WITHOUT_OPS_BINDING"
    }


def test_acceptance_cancellation_reconciles_failed_ops_terminal_state(
    tmp_path: Path,
):
    runtime = _runtime(tmp_path)
    current_session = "phase6-current"
    flow_run_id = "prefect-cancelled"
    pipeline_id = _create_pipeline(
        runtime,
        flow_key="3" * 64,
        flow_run_id=flow_run_id,
        parameters={
            "acceptance_session": current_session,
            "acceptance_scenario": "cancellation",
        },
        target_status="FAILED",
    )
    task_run_id = "prefect-cancelled-task"
    with runtime.session_factory() as session:
        repo = SqlAlchemyOpsRepository(session)
        bridge = OpsBridgeService(repo, orchestrator_version="3.7.8")
        stage_handle = bridge.create_or_reuse_stage(
            pipeline_run_id=pipeline_id,
            node_id="acceptance-cancellation",
            stage_id="data.audit",
            stage_version=1,
            stage_key="4" * 64,
            command_snapshot={},
            approval_policy="NONE",
            prefect_flow_run_id=flow_run_id,
            prefect_task_run_id=task_run_id,
            deployment_name="local",
            work_pool_name="researchops-local-process",
            work_queue_name="verification",
        )
        bridge.transition_stage(stage_handle.stage_run, "RUNNING")
        bridge.transition_stage(
            stage_handle.stage_run,
            "FAILED",
            error_type="CancelledError",
            error_message="Worker observed external cancellation",
        )
        stage_run_id = stage_handle.stage_run.id
        session.commit()

    snapshot = PrefectRuntimeSnapshot(
        flow_runs=(
            _flow_snapshot(flow_run_id, "CANCELLED", current_session),
        ),
        task_runs=(
            PrefectTaskRunSnapshot(
                task_run_id=task_run_id,
                flow_run_id=flow_run_id,
                state_name="CANCELLED",
            ),
        ),
    )

    reported = ReconciliationService(
        runtime,
        FakeGateway(snapshot),
        acceptance_session=current_session,
    ).run("report-only")
    issue = next(
        item for item in reported.issues if item.code == "FLOW_STATE_MISMATCH"
    )
    assert reported.passed is False
    assert issue.repairable is True
    assert issue.repaired is False

    repaired = ReconciliationService(
        runtime,
        FakeGateway(snapshot),
        acceptance_session=current_session,
    ).run("repair-safe")
    issue = next(
        item for item in repaired.issues if item.code == "FLOW_STATE_MISMATCH"
    )
    assert repaired.passed is True
    assert issue.repaired is True

    with runtime.session_factory() as session:
        repo = SqlAlchemyOpsRepository(session)
        assert repo.get_pipeline_run(pipeline_id).status == "CANCELLED"
        assert repo.get_stage_run(stage_run_id).status == "CANCELLED"
        event_types = [
            item.event_type for item in repo.list_run_events(pipeline_id)
        ]
        assert "pipeline.status_reconciled" in event_types
        assert "stage.status_reconciled" in event_types

    clean = ReconciliationService(
        runtime,
        FakeGateway(snapshot),
        acceptance_session=current_session,
    ).run("report-only")
    assert clean.passed is True
    assert clean.error_count == 0


def test_empty_acceptance_scope_fails_closed(tmp_path: Path):
    runtime = _runtime(tmp_path)
    report = ReconciliationService(
        runtime,
        FakeGateway(PrefectRuntimeSnapshot(flow_runs=(), task_runs=())),
        acceptance_session="phase6-missing",
    ).run()
    assert report.passed is False
    assert {item.code for item in report.issues} == {
        "RECONCILIATION_SCOPE_EMPTY"
    }
