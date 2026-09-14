from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from research.python.researchops.gates.orchestration import SemanticGateOrchestrator
from research.python.researchops.ops_core.repositories.sqlalchemy import (
    SqlAlchemyOpsRepository,
)
from research.python.researchops.stage_registry.loader import load_stage_registry

from ..execution.contracts import DiscoveredOutput, StageExecutionResult
from ..execution.errors import classify_error
from ..execution.executor import StageExecutor
from ..identity import ArtifactIdentity, stage_orchestration_key
from ..ops_bridge.service import OpsBridgeService
from ..runtime import load_orchestration_runtime


def should_retry_exception(exc: BaseException) -> bool:
    return classify_error(exc).retryable


def prefect_retry_condition(task: Any, task_run: Any, state: Any) -> bool:
    del task, task_run
    try:
        state.result()
    except BaseException as exc:
        return should_retry_exception(exc)
    return False


def _prefect_context() -> tuple[str, str, str]:
    import prefect
    from prefect import runtime

    flow_run_id = str(runtime.flow_run.id)
    task_run_id = str(runtime.task_run.id)
    return flow_run_id, task_run_id, prefect.__version__


def _reused_result(
    *,
    stage: Any,
    node_id: str,
    pipeline_run_id: str,
    orchestration_key: str,
    stage_run: Any,
    outputs: Any,
    artifact_store: Any,
) -> StageExecutionResult:
    discovered: list[DiscoveredOutput] = []
    for item in outputs:
        manifest = artifact_store.get_manifest(item.artifact_id)
        discovered.append(
            DiscoveredOutput(
                name=item.output_name,
                contract=item.contract,
                artifact_id=item.artifact_id,
                manifest_sha256=item.manifest_sha256,
                file_count=max(1, len(manifest.files)),
            )
        )
    now = datetime.now(timezone.utc)
    return StageExecutionResult(
        pipeline_run_id=pipeline_run_id,
        stage_run_id=stage_run.id,
        node_id=node_id,
        stage_id=stage.id,
        stage_version=stage.version,
        status="REUSED",
        attempt=stage_run.attempt,
        orchestration_key=orchestration_key,
        command=(stage.runtime.executable, *stage.runtime.args),
        started_at=stage_run.started_at or now,
        ended_at=stage_run.ended_at or now,
        exit_code=stage_run.exit_code,
        outputs=tuple(discovered),
        evidence_artifact_id=stage_run.stdout_artifact_id,
        metadata={"idempotent_reuse": True},
    )


def execute_stage_task_impl(
    *,
    pipeline_run_id: str,
    flow_id: str,
    flow_orchestration_key: str,
    node_id: str,
    stage_id: str,
    input_artifact_ids: Mapping[str, str],
    parameters: Mapping[str, Any],
    source_commit: str,
    environment_snapshot_id: str,
    stage_registry_sha256: str,
    deployment_name: str | None,
    work_pool_name: str | None,
    work_queue_name: str | None,
) -> StageExecutionResult:
    runtime = load_orchestration_runtime()
    stage = load_stage_registry(root=runtime.root).by_id()[stage_id]
    identities = {
        name: ArtifactIdentity.from_manifest(
            runtime.artifact_store.get_manifest(artifact_id)
        )
        for name, artifact_id in input_artifact_ids.items()
    }
    stage_key = stage_orchestration_key(
        flow_key=flow_orchestration_key,
        node_id=node_id,
        stage=stage,
        input_artifacts=identities,
        parameters=parameters,
    )
    prefect_flow_run_id, prefect_task_run_id, prefect_version = _prefect_context()

    with runtime.session_factory() as session:
        repository = SqlAlchemyOpsRepository(session)
        bridge = OpsBridgeService(repository, orchestrator_version=prefect_version)
        handle = bridge.create_or_reuse_stage(
            pipeline_run_id=pipeline_run_id,
            node_id=node_id,
            stage_id=stage.id,
            stage_version=stage.version,
            stage_key=stage_key,
            command_snapshot={
                "executable": stage.runtime.executable,
                "args": list(stage.runtime.args),
                "working_directory": stage.runtime.working_directory,
                "shell": False,
            },
            approval_policy=stage.behavior.approval_policy,
            prefect_flow_run_id=prefect_flow_run_id,
            prefect_task_run_id=prefect_task_run_id,
            deployment_name=deployment_name,
            work_pool_name=work_pool_name,
            work_queue_name=work_queue_name,
        )
        if handle.reused:
            session.commit()
            return _reused_result(
                stage=stage,
                node_id=node_id,
                pipeline_run_id=pipeline_run_id,
                orchestration_key=stage_key,
                stage_run=handle.stage_run,
                outputs=handle.outputs,
                artifact_store=runtime.artifact_store,
            )
        bridge.transition_stage(handle.stage_run, "RUNNING")
        session.commit()

        executor = StageExecutor(
            repository=repository,
            artifact_store=runtime.artifact_store,
            ops_bridge=bridge,
            project_root=runtime.root,
            execution_root=runtime.execution_root,
            semantic_gate_orchestrator=SemanticGateOrchestrator(
                repository=repository,
                artifact_store=runtime.artifact_store,
            ),
        )
        try:
            result = executor.execute(
                stage=stage,
                node_id=node_id,
                pipeline_run_id=pipeline_run_id,
                stage_run_id=handle.stage_run.id,
                orchestration_key=stage_key,
                input_artifact_ids=input_artifact_ids,
                parameters=parameters,
                source_commit=source_commit,
                environment_snapshot_id=environment_snapshot_id,
                stage_registry_sha256=stage_registry_sha256,
                flow_id=flow_id,
                attempt=handle.stage_run.attempt,
            )
        except BaseException as exc:
            classification = classify_error(exc)
            bridge.transition_stage(
                handle.stage_run,
                "FAILED",
                exit_code=getattr(exc, "exit_code", None),
                error_type=classification.error_type,
                error_category=classification.category,
                retryable=classification.retryable,
                error_message=classification.message,
            )
            session.commit()
            raise
        bridge.transition_stage(
            handle.stage_run,
            "SUCCEEDED",
            exit_code=result.exit_code,
        )
        session.commit()
        return result


def build_prefect_stage_task():
    from prefect import task

    return task(
        name="researchops-stage-execution",
        retries=0,
        retry_condition_fn=prefect_retry_condition,
        persist_result=True,
        log_prints=True,
    )(execute_stage_task_impl)
