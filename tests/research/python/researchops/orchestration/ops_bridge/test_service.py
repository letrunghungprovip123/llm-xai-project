from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from research.python.researchops.ops_core.db.base import Base
from research.python.researchops.ops_core.db.models import EnvironmentSnapshot
from research.python.researchops.ops_core.repositories.sqlalchemy import SqlAlchemyOpsRepository
from research.python.researchops.orchestration.ops_bridge.service import OpsBridgeService


def _environment() -> EnvironmentSnapshot:
    return EnvironmentSnapshot(
        id="env_01J00000000000000000000000",
        python_version="3.12.0",
        node_version="v22.0.0",
        operating_system="test",
        architecture="arm64",
        dependency_lock_sha256="a" * 64,
        git_commit="b" * 40,
        git_dirty=False,
        details={},
    )


def test_pipeline_and_stage_idempotent_reuse(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'ops.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repo = SqlAlchemyOpsRepository(session)
        bridge = OpsBridgeService(repo, orchestrator_version="3.7.8")
        bridge.persist_environment(_environment())
        first = bridge.create_or_reuse_pipeline(
            flow_id="flow",
            flow_key="c" * 64,
            flow_catalog_sha256="d" * 64,
            source_commit="b" * 40,
            environment_snapshot_id=_environment().id,
            parameters={},
            requested_by="tester",
            trigger_type="TEST",
            prefect_flow_run_id="flow-1",
            deployment_name="flow-local",
            work_pool_name="pool",
            work_queue_name="verification",
        )
        bridge.transition_pipeline(first.pipeline_run, "RUNNING")
        stage = bridge.create_or_reuse_stage(
            pipeline_run_id=first.pipeline_run.id,
            node_id="node",
            stage_id="data.audit",
            stage_version=1,
            stage_key="e" * 64,
            command_snapshot={},
            approval_policy="NONE",
            prefect_flow_run_id="flow-1",
            prefect_task_run_id="task-1",
            deployment_name="flow-local",
            work_pool_name="pool",
            work_queue_name="verification",
        )
        bridge.transition_stage(stage.stage_run, "RUNNING")
        bridge.transition_stage(stage.stage_run, "SUCCEEDED", exit_code=0)
        bridge.transition_pipeline(first.pipeline_run, "SUCCEEDED")
        session.commit()

        second = bridge.create_or_reuse_pipeline(
            flow_id="flow",
            flow_key="c" * 64,
            flow_catalog_sha256="d" * 64,
            source_commit="b" * 40,
            environment_snapshot_id=_environment().id,
            parameters={},
            requested_by="tester",
            trigger_type="TEST",
            prefect_flow_run_id="flow-2",
            deployment_name="flow-local",
            work_pool_name="pool",
            work_queue_name="verification",
        )
        reused_stage = bridge.create_or_reuse_stage(
            pipeline_run_id=second.pipeline_run.id,
            node_id="node",
            stage_id="data.audit",
            stage_version=1,
            stage_key="e" * 64,
            command_snapshot={},
            approval_policy="NONE",
            prefect_flow_run_id="flow-2",
            prefect_task_run_id="task-2",
            deployment_name="flow-local",
            work_pool_name="pool",
            work_queue_name="verification",
        )
        assert second.reused
        assert second.pipeline_run.id == first.pipeline_run.id
        assert reused_stage.reused
        assert reused_stage.stage_run.id == stage.stage_run.id
        assert len(repo.orchestration_bindings_by_key("prefect", "c" * 64)) == 2
        assert len(repo.orchestration_bindings_by_key("prefect", "e" * 64)) == 2


def test_prefect_task_retry_can_bind_multiple_attempts_to_same_task_run():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repo = SqlAlchemyOpsRepository(session)
        env = _environment()
        repo.add_environment_snapshot(env)
        bridge = OpsBridgeService(repo, orchestrator_version="3.7.8")
        flow = bridge.create_or_reuse_pipeline(
            flow_id="flow",
            flow_key="f" * 64,
            flow_catalog_sha256="d" * 64,
            source_commit="b" * 40,
            environment_snapshot_id=env.id,
            parameters={},
            requested_by="tester",
            trigger_type="TEST",
            prefect_flow_run_id="flow-retry",
            deployment_name="flow-local",
            work_pool_name="pool",
            work_queue_name="verification",
        )
        first = bridge.create_or_reuse_stage(
            pipeline_run_id=flow.pipeline_run.id,
            node_id="node",
            stage_id="data.audit",
            stage_version=1,
            stage_key="9" * 64,
            command_snapshot={},
            approval_policy="NONE",
            prefect_flow_run_id="flow-retry",
            prefect_task_run_id="task-retry",
            deployment_name="flow-local",
            work_pool_name="pool",
            work_queue_name="verification",
        )
        bridge.transition_stage(first.stage_run, "RUNNING")
        bridge.transition_stage(first.stage_run, "FAILED", error_type="TransientNetworkError")
        second = bridge.create_or_reuse_stage(
            pipeline_run_id=flow.pipeline_run.id,
            node_id="node",
            stage_id="data.audit",
            stage_version=1,
            stage_key="9" * 64,
            command_snapshot={},
            approval_policy="NONE",
            prefect_flow_run_id="flow-retry",
            prefect_task_run_id="task-retry",
            deployment_name="flow-local",
            work_pool_name="pool",
            work_queue_name="verification",
        )
        session.commit()
        assert second.reused is False
        assert second.stage_run.attempt == 2
        bindings = repo.orchestration_bindings_by_key("prefect", "9" * 64)
        assert [item.attempt_number for item in bindings] == [1, 2]
        latest = repo.get_orchestration_binding_for_prefect(
            "prefect", "flow-retry", "task-retry"
        )
        assert latest is not None
        assert latest.attempt_number == 2


def test_same_prefect_flow_can_resume_waiting_pipeline_without_duplicate_binding():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repo = SqlAlchemyOpsRepository(session)
        env = _environment()
        repo.add_environment_snapshot(env)
        bridge = OpsBridgeService(repo, orchestrator_version="3.7.8")
        first = bridge.create_or_reuse_pipeline(
            flow_id="protected-flow",
            flow_key="7" * 64,
            flow_catalog_sha256="8" * 64,
            source_commit="b" * 40,
            environment_snapshot_id=env.id,
            parameters={},
            requested_by="tester",
            trigger_type="PREFECT_DEPLOYMENT",
            prefect_flow_run_id="same-prefect-flow",
            deployment_name="local",
            work_pool_name="pool",
            work_queue_name="verification",
        )
        bridge.transition_pipeline(first.pipeline_run, "RUNNING")
        bridge.transition_pipeline(first.pipeline_run, "WAITING_APPROVAL")
        session.commit()

        resumed = bridge.create_or_reuse_pipeline(
            flow_id="protected-flow",
            flow_key="7" * 64,
            flow_catalog_sha256="8" * 64,
            source_commit="b" * 40,
            environment_snapshot_id=env.id,
            parameters={},
            requested_by="tester",
            trigger_type="PREFECT_DEPLOYMENT",
            prefect_flow_run_id="same-prefect-flow",
            deployment_name="local",
            work_pool_name="pool",
            work_queue_name="verification",
        )
        assert resumed.pipeline_run.id == first.pipeline_run.id
        assert resumed.binding.id == first.binding.id
        assert resumed.reused is False
        assert len(repo.orchestration_bindings_by_key("prefect", "7" * 64)) == 1
