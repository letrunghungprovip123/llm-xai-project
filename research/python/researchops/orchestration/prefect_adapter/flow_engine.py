from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Protocol

from pydantic import BaseModel, ConfigDict, Field

from research.python.researchops.ops_core.db.models import PipelineRunReceipt
from research.python.researchops.ops_core.repositories.sqlalchemy import (
    SqlAlchemyOpsRepository,
)
from research.python.researchops.stage_registry.loader import load_stage_registry
from research.python.researchops.stage_registry.models import StageDefinition

from ..environment import capture_environment
from ..evidence.builder import build_pipeline_execution_receipt
from ..execution.contracts import (
    ReceiptArtifactIdentity,
    StageExecutionResult,
)
from ..execution.errors import PolicyDeniedError, SchemaContractError
from ..flow_catalog.compiler import compile_payload as compile_flow_catalog
from ..flow_catalog.graph import topological_order
from ..flow_catalog.loader import load_flow_catalog
from ..flow_catalog.models import FlowDefinition, FlowNode
from ..identity import ArtifactIdentity, flow_orchestration_key
from ..ops_bridge.service import OpsBridgeService
from ..runtime import OrchestrationRuntime, load_orchestration_runtime


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FlowExecutionResult(StrictModel):
    schema_version: str = "flow_execution_result_v1"
    flow_id: str
    flow_version: int
    pipeline_run_id: str
    prefect_flow_run_id: str
    status: str
    reused: bool
    orchestration_key: str
    outputs: dict[str, ReceiptArtifactIdentity] = Field(default_factory=dict)
    receipt: ReceiptArtifactIdentity | None = None
    stages: tuple[StageExecutionResult, ...] = ()


@dataclass(frozen=True)
class FlowInvocationContext:
    prefect_flow_run_id: str
    orchestrator_version: str
    deployment_name: str | None
    work_pool_name: str | None
    work_queue_name: str | None


class ApprovalBoundary(Protocol):
    def require(
        self,
        *,
        stage: StageDefinition,
        pipeline_run_id: str,
        node_id: str,
        requested_by: str,
    ) -> None: ...


StageRunner = Callable[..., StageExecutionResult]


def _is_prefect_pause_signal(exc: BaseException) -> bool:
    """Recognize only Prefect's intentional suspend control-flow exception."""

    exception_type = type(exc)
    return (
        exception_type.__name__ == "Pause"
        and exception_type.__module__.startswith("prefect")
    )


def prefect_retry_delay_schedule(retries: int) -> list[int] | None:
    """Return Prefect-compatible retry delays for the configured retry count.

    Prefect accepts a scalar, list, or callable for ``retry_delay_seconds``.
    Keep this boundary explicit because internal immutable tuples are not a valid
    Prefect task option even though they are otherwise common in our contracts.
    """

    if retries <= 0:
        return None
    return [5 * (index + 1) for index in range(retries)]


def prefect_invocation_context(flow: FlowDefinition) -> FlowInvocationContext:
    import prefect
    from prefect import runtime

    deployment_name = None
    try:
        deployment_name = str(runtime.deployment.name or "") or None
    except Exception:
        deployment_name = None
    return FlowInvocationContext(
        prefect_flow_run_id=str(runtime.flow_run.id),
        orchestrator_version=prefect.__version__,
        deployment_name=deployment_name,
        work_pool_name="researchops-local-process",
        work_queue_name=flow.work_queue,
    )


def node_is_enabled(node: FlowNode, parameters: Mapping[str, Any]) -> bool:
    if node.required:
        return True
    assert node.condition is not None
    return bool(parameters.get(node.condition, False))


def resolve_node_inputs(
    *,
    flow: FlowDefinition,
    node: FlowNode,
    flow_inputs: Mapping[str, str],
    node_results: Mapping[str, StageExecutionResult],
) -> dict[str, str]:
    result: dict[str, str] = {}
    for stage_input, flow_input in node.input_mapping.items():
        if flow_input in flow_inputs:
            result[stage_input] = flow_inputs[flow_input]
    for edge in flow.edges:
        if edge.to_node != node.node_id:
            continue
        source = node_results.get(edge.from_node)
        if source is None:
            continue
        by_name = source.output_artifact_ids()
        if edge.from_output in by_name:
            result[edge.to_input] = by_name[edge.from_output]
    return result


def resolve_node_parameters(
    node: FlowNode, parameters: Mapping[str, Any]
) -> dict[str, Any]:
    result = {
        target: parameters[source]
        for target, source in node.parameter_mapping.items()
        if source in parameters
    }
    if "allow_existing_outputs" in parameters:
        result["allow_existing_outputs"] = bool(
            parameters["allow_existing_outputs"]
        )
    return result


def collect_flow_outputs(
    *,
    flow: FlowDefinition,
    node_results: Mapping[str, StageExecutionResult],
    artifact_store: Any,
) -> dict[str, ReceiptArtifactIdentity]:
    result: dict[str, ReceiptArtifactIdentity] = {}
    missing: list[str] = []
    for output in flow.outputs:
        stage_result = node_results.get(output.from_node)
        artifact_id = None
        if stage_result is not None:
            artifact_id = stage_result.output_artifact_ids().get(output.from_output)
        if artifact_id is None:
            if output.required:
                missing.append(output.name)
            continue
        manifest = artifact_store.get_manifest(artifact_id)
        if manifest.artifact_type != output.contract:
            raise SchemaContractError(
                f"Flow output contract mismatch for {flow.id}.{output.name}: "
                f"expected={output.contract} observed={manifest.artifact_type}"
            )
        result[output.name] = ReceiptArtifactIdentity(
            artifact_id=artifact_id,
            artifact_type=manifest.artifact_type,
            manifest_sha256=manifest.manifest_sha256,
        )
    if missing:
        raise SchemaContractError(
            f"Required flow outputs are missing for {flow.id}: {sorted(missing)}"
        )
    return result


def _verified_flow_inputs(
    *,
    flow: FlowDefinition,
    input_artifact_ids: Mapping[str, str],
    artifact_store: Any,
) -> dict[str, ArtifactIdentity]:
    expected = {item.name: item for item in flow.inputs}
    unknown = set(input_artifact_ids) - set(expected)
    if unknown:
        raise SchemaContractError(f"Unknown flow inputs: {sorted(unknown)}")
    result: dict[str, ArtifactIdentity] = {}
    for name, binding in expected.items():
        artifact_id = input_artifact_ids.get(name)
        if artifact_id is None:
            if binding.required:
                raise SchemaContractError(f"Required flow input is missing: {name}")
            continue
        verification = artifact_store.verify(artifact_id)
        if not verification.passed:
            raise SchemaContractError(
                f"Flow input verification failed for {artifact_id}: "
                + "; ".join(verification.errors)
            )
        manifest = artifact_store.get_manifest(artifact_id)
        if manifest.artifact_type != binding.contract:
            raise SchemaContractError(
                f"Flow input contract mismatch for {name}: "
                f"expected={binding.contract} observed={manifest.artifact_type}"
            )
        result[name] = ArtifactIdentity.from_manifest(manifest)
    return result


def _receipt_identity(runtime: OrchestrationRuntime, record: PipelineRunReceipt):
    manifest = runtime.artifact_store.get_manifest(record.artifact_id)
    return ReceiptArtifactIdentity(
        artifact_id=record.artifact_id,
        artifact_type=manifest.artifact_type,
        manifest_sha256=record.manifest_sha256,
    )


def _reused_flow_result(
    *,
    flow: FlowDefinition,
    runtime: OrchestrationRuntime,
    pipeline_run_id: str,
    prefect_flow_run_id: str,
    flow_key: str,
) -> FlowExecutionResult:
    with runtime.session_factory() as session:
        repository = SqlAlchemyOpsRepository(session)
        receipt = repository.get_pipeline_run_receipt(pipeline_run_id)
        if receipt is None:
            raise PolicyDeniedError(
                f"Successful pipeline lacks immutable receipt: {pipeline_run_id}"
            )
        stage_results: list[StageExecutionResult] = []
        node_results: dict[str, StageExecutionResult] = {}
        node_by_stage = {node.stage_id: node.node_id for node in flow.nodes}
        for stage_run in repository.list_stage_runs(pipeline_run_id):
            outputs = []
            for item in repository.stage_outputs(stage_run.id):
                manifest = runtime.artifact_store.get_manifest(item.artifact_id)
                from ..execution.contracts import DiscoveredOutput

                outputs.append(
                    DiscoveredOutput(
                        name=item.output_name,
                        contract=item.contract,
                        artifact_id=item.artifact_id,
                        manifest_sha256=item.manifest_sha256,
                        file_count=max(1, len(manifest.files)),
                    )
                )
            now = datetime.now(timezone.utc)
            result = StageExecutionResult(
                pipeline_run_id=pipeline_run_id,
                stage_run_id=stage_run.id,
                node_id=str(stage_run.command_snapshot.get("node_id") or node_by_stage.get(stage_run.stage_id, stage_run.stage_id.replace(".", "_"))),
                stage_id=stage_run.stage_id,
                stage_version=stage_run.stage_version,
                status="REUSED",
                attempt=stage_run.attempt,
                orchestration_key=str(stage_run.command_snapshot.get("orchestration_key") or "0" * 64),
                command=tuple(
                    [str(stage_run.command_snapshot.get("executable") or "unknown")]
                    + [str(item) for item in stage_run.command_snapshot.get("args", [])]
                ),
                started_at=stage_run.started_at or now,
                ended_at=stage_run.ended_at or now,
                exit_code=stage_run.exit_code,
                outputs=tuple(outputs),
                evidence_artifact_id=stage_run.stdout_artifact_id,
                metadata={"idempotent_reuse": True},
            )
            stage_results.append(result)
            node_results[result.node_id] = result
        outputs = collect_flow_outputs(
            flow=flow,
            node_results=node_results,
            artifact_store=runtime.artifact_store,
        )
        return FlowExecutionResult(
            flow_id=flow.id,
            flow_version=flow.version,
            pipeline_run_id=pipeline_run_id,
            prefect_flow_run_id=prefect_flow_run_id,
            status="REUSED",
            reused=True,
            orchestration_key=flow_key,
            outputs=outputs,
            receipt=_receipt_identity(runtime, receipt),
            stages=tuple(stage_results),
        )


def execute_catalog_flow(
    *,
    flow_id: str,
    input_artifact_ids: Mapping[str, str] | None = None,
    parameters: Mapping[str, Any] | None = None,
    requested_by: str = "prefect-user",
    trigger_type: str = "PREFECT_DEPLOYMENT",
    runtime: OrchestrationRuntime | None = None,
    invocation: FlowInvocationContext | None = None,
    stage_runner: StageRunner | None = None,
    approval_boundary: ApprovalBoundary | None = None,
) -> FlowExecutionResult:
    runtime = runtime or load_orchestration_runtime()
    inputs = dict(input_artifact_ids or {})
    params = dict(parameters or {})
    catalog = load_flow_catalog(root=runtime.root)
    flow = catalog.by_id().get(flow_id)
    if flow is None or flow.status == "PLANNED":
        raise SchemaContractError(f"Unknown or non-executable flow: {flow_id}")
    invocation = invocation or prefect_invocation_context(flow)
    registry = load_stage_registry(root=runtime.root)
    stage_by_id = registry.by_id()
    flow_lock = compile_flow_catalog(runtime.root)
    flow_catalog_sha = str(flow_lock["catalog_sha256"])
    stage_registry_sha = str(flow_lock["stage_registry_sha256"])
    verified_inputs = _verified_flow_inputs(
        flow=flow,
        input_artifact_ids=inputs,
        artifact_store=runtime.artifact_store,
    )
    captured = capture_environment(runtime.root)
    flow_key = flow_orchestration_key(
        flow=flow,
        flow_catalog_sha256=flow_catalog_sha,
        stage_registry_sha256=stage_registry_sha,
        input_artifacts=verified_inputs,
        parameters=params,
        source_commit=captured.source_commit,
        dependency_lock_sha256=captured.dependency_lock_sha256,
    )

    with runtime.session_factory() as session:
        repository = SqlAlchemyOpsRepository(session)
        bridge = OpsBridgeService(
            repository,
            orchestrator_version=invocation.orchestrator_version,
        )
        bridge.persist_environment(captured.record)
        handle = bridge.create_or_reuse_pipeline(
            flow_id=flow.id,
            flow_key=flow_key,
            flow_catalog_sha256=flow_catalog_sha,
            source_commit=captured.source_commit,
            environment_snapshot_id=captured.record.id,
            parameters={
                **params,
                "__researchops_control": {
                    "input_artifact_ids": inputs,
                    "flow_parameters": params,
                },
            },
            requested_by=requested_by,
            trigger_type=trigger_type,
            prefect_flow_run_id=invocation.prefect_flow_run_id,
            deployment_name=invocation.deployment_name,
            work_pool_name=invocation.work_pool_name,
            work_queue_name=invocation.work_queue_name,
        )
        session.commit()
        pipeline_run_id = handle.pipeline_run.id
        if handle.reused:
            return _reused_flow_result(
                flow=flow,
                runtime=runtime,
                pipeline_run_id=pipeline_run_id,
                prefect_flow_run_id=invocation.prefect_flow_run_id,
                flow_key=flow_key,
            )

    if stage_runner is None:
        task = _build_stage_task()

        def stage_runner(**kwargs: Any) -> StageExecutionResult:
            stage = stage_by_id[kwargs["stage_id"]]
            retry_delays = prefect_retry_delay_schedule(stage.behavior.retries)
            configured = task.with_options(
                name=f"{flow.id}.{kwargs['node_id']}",
                retries=stage.behavior.retries,
                retry_delay_seconds=retry_delays,
                timeout_seconds=stage.behavior.timeout_seconds + 30,
            )
            return configured(**kwargs)

    node_results: dict[str, StageExecutionResult] = {}
    try:
        with runtime.session_factory() as session:
            repository = SqlAlchemyOpsRepository(session)
            bridge = OpsBridgeService(
                repository,
                orchestrator_version=invocation.orchestrator_version,
            )
            pipeline = repository.get_pipeline_run(pipeline_run_id)
            assert pipeline is not None
            bridge.transition_pipeline(pipeline, "RUNNING")
            session.commit()

        node_by_id = {node.node_id: node for node in flow.nodes}
        for node_id in topological_order(flow):
            node = node_by_id[node_id]
            if not node_is_enabled(node, params):
                continue
            stage = stage_by_id[node.stage_id]
            if stage.behavior.approval_policy != "NONE":
                if approval_boundary is None:
                    raise PolicyDeniedError(
                        f"Protected stage requires approval boundary: {stage.id}"
                    )
                approval_boundary.require(
                    stage=stage,
                    pipeline_run_id=pipeline_run_id,
                    node_id=node.node_id,
                    requested_by=requested_by,
                )
            result = stage_runner(
                pipeline_run_id=pipeline_run_id,
                flow_id=flow.id,
                flow_orchestration_key=flow_key,
                node_id=node.node_id,
                stage_id=stage.id,
                input_artifact_ids=resolve_node_inputs(
                    flow=flow,
                    node=node,
                    flow_inputs=inputs,
                    node_results=node_results,
                ),
                parameters=resolve_node_parameters(node, params),
                source_commit=captured.source_commit,
                environment_snapshot_id=captured.record.id,
                stage_registry_sha256=stage_registry_sha,
                deployment_name=invocation.deployment_name,
                work_pool_name=invocation.work_pool_name,
                work_queue_name=node.work_queue,
            )
            node_results[node.node_id] = result

        outputs = collect_flow_outputs(
            flow=flow,
            node_results=node_results,
            artifact_store=runtime.artifact_store,
        )
        terminal = list(node_results.values())[-1]
        receipt_dir = runtime.execution_root / pipeline_run_id
        input_receipts = {
            name: ReceiptArtifactIdentity(
                artifact_id=item.artifact_id,
                artifact_type=item.artifact_type,
                manifest_sha256=item.manifest_sha256,
            ).model_dump(mode="json")
            for name, item in verified_inputs.items()
        }
        output_receipts = {
            name: item.model_dump(mode="json") for name, item in outputs.items()
        }
        with runtime.session_factory() as session:
            repository = SqlAlchemyOpsRepository(session)
            receipt_id, receipt_sha = build_pipeline_execution_receipt(
                directory=receipt_dir,
                flow_id=flow.id,
                flow_version=flow.version,
                flow_catalog_sha256=flow_catalog_sha,
                stage_registry_sha256=stage_registry_sha,
                prefect_flow_run_id=invocation.prefect_flow_run_id,
                pipeline_run_id=pipeline_run_id,
                source_commit=captured.source_commit,
                environment_snapshot_id=captured.record.id,
                terminal_status="SUCCEEDED",
                inputs=input_receipts,
                outputs=output_receipts,
                stage_results=node_results.values(),
                terminal_stage_id=terminal.stage_id,
                terminal_stage_version=terminal.stage_version,
                terminal_stage_run_id=terminal.stage_run_id,
                artifact_store=runtime.artifact_store,
                repository=repository,
                actor="prefect-worker",
            )
            existing = repository.get_pipeline_run_receipt(pipeline_run_id)
            if existing is None:
                repository.add_pipeline_run_receipt(
                    PipelineRunReceipt(
                        pipeline_run_id=pipeline_run_id,
                        artifact_id=receipt_id,
                        manifest_sha256=receipt_sha,
                    )
                )
            elif (
                existing.artifact_id != receipt_id
                or existing.manifest_sha256 != receipt_sha
            ):
                raise PolicyDeniedError(
                    f"Pipeline receipt identity drift: {pipeline_run_id}"
                )
            bridge = OpsBridgeService(
                repository,
                orchestrator_version=invocation.orchestrator_version,
            )
            pipeline = repository.get_pipeline_run(pipeline_run_id)
            assert pipeline is not None
            bridge.transition_pipeline(pipeline, "SUCCEEDED")
            session.commit()
        return FlowExecutionResult(
            flow_id=flow.id,
            flow_version=flow.version,
            pipeline_run_id=pipeline_run_id,
            prefect_flow_run_id=invocation.prefect_flow_run_id,
            status="SUCCEEDED",
            reused=False,
            orchestration_key=flow_key,
            outputs=outputs,
            receipt=ReceiptArtifactIdentity(
                artifact_id=receipt_id,
                artifact_type="pipeline_execution_receipt",
                manifest_sha256=receipt_sha,
            ),
            stages=tuple(node_results.values()),
        )
    except BaseException as exc:
        exception_name = type(exc).__name__.lower()
        with runtime.session_factory() as session:
            repository = SqlAlchemyOpsRepository(session)
            pipeline = repository.get_pipeline_run(pipeline_run_id)
            is_prefect_suspend_signal = (
                pipeline is not None
                and pipeline.status == "WAITING_APPROVAL"
                and _is_prefect_pause_signal(exc)
            )
            if is_prefect_suspend_signal:
                # Suspending a deployed flow intentionally exits the current process.
                # The Ops DB WAITING_APPROVAL state must survive until Prefect reschedules
                # the same flow run after an authoritative decision is recorded.
                session.rollback()
                raise
            target = "CANCELLED" if "cancel" in exception_name else "FAILED"
            if pipeline is not None and pipeline.status not in {
                "SUCCEEDED",
                "FAILED",
                "CANCELLED",
            }:
                bridge = OpsBridgeService(
                    repository,
                    orchestrator_version=invocation.orchestrator_version,
                )
                if pipeline.status == "PENDING" and target == "FAILED":
                    bridge.transition_pipeline(pipeline, "RUNNING")
                bridge.transition_pipeline(pipeline, target, error_summary=str(exc))
                session.commit()
        raise


def _build_stage_task():
    from .tasks import build_prefect_stage_task

    return build_prefect_stage_task()
