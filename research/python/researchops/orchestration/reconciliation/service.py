from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any, Literal

from research.python.researchops.ops_core.repositories.sqlalchemy import (
    SqlAlchemyOpsRepository,
)

from ..approvals.service import ApprovalService
from ..flow_catalog.compiler import compile_payload as compile_flow_catalog
from ..ops_bridge.service import OpsBridgeService
from ..runtime import OrchestrationRuntime
from .gateway import PrefectRuntimeSnapshot, PrefectSnapshotGateway
from .models import (
    PrefectFlowRunSnapshot,
    PrefectTaskRunSnapshot,
    ReconciliationIssue,
    ReconciliationReport,
)

_PREFECT_TERMINAL_TO_OPS = {
    "COMPLETED": "SUCCEEDED",
    "FAILED": "FAILED",
    "CRASHED": "FAILED",
    "CANCELLED": "CANCELLED",
}
_PREFECT_WAITING = {"PAUSED", "SUSPENDED"}
_OPS_TERMINAL = {"SUCCEEDED", "FAILED", "CANCELLED"}


def _prefect_acceptance_session(parameters: Mapping[str, Any]) -> str | None:
    """Read the session from a deployed flow's nested or direct parameters."""

    nested = parameters.get("parameters")
    if isinstance(nested, Mapping):
        value = nested.get("acceptance_session")
        if value:
            return str(value)
    value = parameters.get("acceptance_session")
    return str(value) if value else None


def _pipeline_acceptance_session(pipeline: Any) -> str | None:
    value = (pipeline.parameters or {}).get("acceptance_session")
    return str(value) if value else None


def _is_acceptance_cancellation(pipeline: Any, session_id: str | None) -> bool:
    if session_id is None:
        return False
    parameters = pipeline.parameters or {}
    return (
        _pipeline_acceptance_session(pipeline) == session_id
        and str(parameters.get("acceptance_scenario") or "") == "cancellation"
    )


class ReconciliationService:
    def __init__(
        self,
        runtime: OrchestrationRuntime,
        gateway: PrefectSnapshotGateway,
        *,
        orchestrator_version: str = "3.7.8",
        acceptance_session: str | None = None,
    ) -> None:
        self.runtime = runtime
        self.gateway = gateway
        self.orchestrator_version = orchestrator_version
        self.acceptance_session = acceptance_session

    def run(
        self, mode: Literal["report-only", "repair-safe"] = "report-only"
    ) -> ReconciliationReport:
        if mode not in {"report-only", "repair-safe"}:
            raise ValueError(f"Unsupported reconciliation mode: {mode}")
        snapshot = self.gateway.snapshot()
        current_catalog_sha = str(
            compile_flow_catalog(self.runtime.root)["catalog_sha256"]
        )
        issues: list[ReconciliationIssue] = []
        checked_stages = 0

        with self.runtime.session_factory() as session:
            repository = SqlAlchemyOpsRepository(session)
            bridge = OpsBridgeService(
                repository, orchestrator_version=self.orchestrator_version
            )
            all_pipelines = repository.list_pipeline_runs()
            if self.acceptance_session is None:
                pipelines = all_pipelines
            else:
                pipelines = [
                    item
                    for item in all_pipelines
                    if _pipeline_acceptance_session(item) == self.acceptance_session
                ]
            pipeline_ids = {item.id for item in pipelines}

            all_bindings = repository.list_orchestration_bindings()
            bindings = (
                all_bindings
                if self.acceptance_session is None
                else [
                    item
                    for item in all_bindings
                    if item.pipeline_run_id in pipeline_ids
                ]
            )
            flow_bindings = [
                item for item in bindings if item.prefect_task_run_id is None
            ]
            task_bindings = [
                item for item in bindings if item.prefect_task_run_id is not None
            ]
            flow_binding_by_prefect = {
                item.prefect_flow_run_id: item for item in flow_bindings
            }
            task_binding_by_prefect = {}
            for item in sorted(
                task_bindings, key=lambda value: value.attempt_number
            ):
                task_binding_by_prefect[item.prefect_task_run_id] = item

            if self.acceptance_session is None:
                flow_runs = snapshot.flow_runs
            else:
                flow_runs = tuple(
                    item
                    for item in snapshot.flow_runs
                    if _prefect_acceptance_session(item.parameters)
                    == self.acceptance_session
                )
            flow_run_ids = {item.flow_run_id for item in flow_runs}
            task_runs = tuple(
                item
                for item in snapshot.task_runs
                if self.acceptance_session is None
                or item.flow_run_id in flow_run_ids
            )
            prefect_flows = {item.flow_run_id: item for item in flow_runs}
            prefect_tasks = {item.task_run_id: item for item in task_runs}

            def add(issue: ReconciliationIssue) -> None:
                issues.append(issue)

            if (
                self.acceptance_session is not None
                and not pipelines
                and not flow_runs
            ):
                add(
                    ReconciliationIssue(
                        code="RECONCILIATION_SCOPE_EMPTY",
                        severity="ERROR",
                        message=(
                            "No Prefect or Ops records were found for acceptance "
                            f"session {self.acceptance_session}."
                        ),
                    )
                )

            for item in flow_runs:
                binding = flow_binding_by_prefect.get(item.flow_run_id)
                if binding is None:
                    add(
                        ReconciliationIssue(
                            code="PREFECT_FLOW_WITHOUT_OPS_BINDING",
                            severity="ERROR",
                            message="Prefect flow run has no ResearchOps binding.",
                            prefect_flow_run_id=item.flow_run_id,
                        )
                    )
                    continue
                pipeline = repository.get_pipeline_run(binding.pipeline_run_id)
                if pipeline is None:
                    add(
                        ReconciliationIssue(
                            code="PREFECT_FLOW_BINDING_WITHOUT_PIPELINE",
                            severity="ERROR",
                            message=(
                                "Prefect flow binding references a missing pipeline run."
                            ),
                            prefect_flow_run_id=item.flow_run_id,
                            pipeline_run_id=binding.pipeline_run_id,
                        )
                    )
                    continue
                expected = _PREFECT_TERMINAL_TO_OPS.get(item.state_name)
                if item.state_name in _PREFECT_WAITING:
                    expected = "WAITING_APPROVAL"
                if expected is not None and pipeline.status != expected:
                    observed_status = pipeline.status
                    repaired = False
                    terminal_cancellation_repair = (
                        pipeline.status == "FAILED"
                        and expected == "CANCELLED"
                        and _is_acceptance_cancellation(
                            pipeline, self.acceptance_session
                        )
                    )
                    repairable = terminal_cancellation_repair or (
                        pipeline.status not in _OPS_TERMINAL
                        and expected in {"FAILED", "CANCELLED"}
                    )
                    if mode == "repair-safe" and repairable:
                        if terminal_cancellation_repair:
                            bridge.reconcile_external_cancellation(
                                pipeline,
                                reason=(
                                    "Prefect confirmed external cancellation for "
                                    f"acceptance session {self.acceptance_session}"
                                ),
                            )
                        else:
                            if pipeline.status == "PENDING":
                                bridge.transition_pipeline(pipeline, "RUNNING")
                            if (
                                pipeline.status == "WAITING_APPROVAL"
                                and expected == "FAILED"
                            ):
                                bridge.transition_pipeline(
                                    pipeline,
                                    "FAILED",
                                    error_summary=(
                                        "Backfilled from verified Prefect terminal state"
                                    ),
                                )
                            elif pipeline.status == "RUNNING":
                                bridge.transition_pipeline(
                                    pipeline,
                                    expected,
                                    error_summary=(
                                        "Backfilled from verified Prefect terminal state"
                                    ),
                                )
                        repaired = pipeline.status == expected
                    add(
                        ReconciliationIssue(
                            code="FLOW_STATE_MISMATCH",
                            severity="ERROR",
                            message=(
                                f"Prefect={item.state_name} Ops={observed_status} "
                                f"expected={expected}"
                            ),
                            pipeline_run_id=pipeline.id,
                            prefect_flow_run_id=item.flow_run_id,
                            repairable=repairable,
                            repaired=repaired,
                        )
                    )

            for item in task_runs:
                binding = task_binding_by_prefect.get(item.task_run_id)
                if binding is None:
                    add(
                        ReconciliationIssue(
                            code="PREFECT_TASK_WITHOUT_OPS_BINDING",
                            severity="ERROR",
                            message="Prefect task run has no ResearchOps stage binding.",
                            prefect_flow_run_id=item.flow_run_id,
                            prefect_task_run_id=item.task_run_id,
                        )
                    )
                elif not binding.stage_run_id or repository.get_stage_run(
                    binding.stage_run_id
                ) is None:
                    add(
                        ReconciliationIssue(
                            code="PREFECT_TASK_BINDING_WITHOUT_STAGE",
                            severity="ERROR",
                            message=(
                                "Prefect task binding references a missing stage run."
                            ),
                            pipeline_run_id=binding.pipeline_run_id,
                            stage_run_id=binding.stage_run_id,
                            prefect_flow_run_id=item.flow_run_id,
                            prefect_task_run_id=item.task_run_id,
                        )
                    )
                else:
                    stage = repository.get_stage_run(binding.stage_run_id)
                    pipeline = repository.get_pipeline_run(binding.pipeline_run_id)
                    assert stage is not None
                    expected = _PREFECT_TERMINAL_TO_OPS.get(item.state_name)
                    if expected is not None and stage.status != expected:
                        observed_status = stage.status
                        terminal_cancellation_repair = (
                            stage.status == "FAILED"
                            and expected == "CANCELLED"
                            and pipeline is not None
                            and _is_acceptance_cancellation(
                                pipeline, self.acceptance_session
                            )
                        )
                        repairable = terminal_cancellation_repair or (
                            stage.status not in _OPS_TERMINAL
                            and expected in {"FAILED", "CANCELLED"}
                        )
                        repaired = False
                        if mode == "repair-safe" and repairable:
                            if terminal_cancellation_repair:
                                bridge.reconcile_external_stage_cancellation(
                                    stage,
                                    reason=(
                                        "Prefect confirmed external cancellation for "
                                        f"acceptance session {self.acceptance_session}"
                                    ),
                                )
                            else:
                                if stage.status == "PENDING":
                                    bridge.transition_stage(stage, "RUNNING")
                                if (
                                    stage.status == "WAITING_APPROVAL"
                                    and expected == "FAILED"
                                ):
                                    bridge.transition_stage(
                                        stage,
                                        "FAILED",
                                        error_type="PrefectTerminalStateBackfill",
                                        error_message=(
                                            "Backfilled from Prefect task state"
                                        ),
                                    )
                                elif stage.status == "RUNNING":
                                    bridge.transition_stage(
                                        stage,
                                        expected,
                                        error_type="PrefectTerminalStateBackfill",
                                        error_message=(
                                            "Backfilled from Prefect task state"
                                        ),
                                    )
                            repaired = stage.status == expected
                        add(
                            ReconciliationIssue(
                                code="TASK_STATE_MISMATCH",
                                severity="ERROR",
                                message=(
                                    f"Prefect={item.state_name} Ops={observed_status} "
                                    f"expected={expected}"
                                ),
                                pipeline_run_id=binding.pipeline_run_id,
                                stage_run_id=stage.id,
                                prefect_flow_run_id=item.flow_run_id,
                                prefect_task_run_id=item.task_run_id,
                                repairable=repairable,
                                repaired=repaired,
                            )
                        )

            for pipeline in pipelines:
                stages = repository.list_stage_runs(pipeline.id)
                checked_stages += len(stages)
                flow_links = [
                    item
                    for item in flow_bindings
                    if item.pipeline_run_id == pipeline.id
                ]
                if not flow_links:
                    add(
                        ReconciliationIssue(
                            code="OPS_PIPELINE_WITHOUT_PREFECT_BINDING",
                            severity="ERROR",
                            message="Ops pipeline run has no Prefect flow binding.",
                            pipeline_run_id=pipeline.id,
                        )
                    )
                elif not any(
                    item.prefect_flow_run_id in prefect_flows
                    for item in flow_links
                ):
                    add(
                        ReconciliationIssue(
                            code="OPS_PIPELINE_PREFECT_RUN_MISSING",
                            severity="ERROR",
                            message="Ops pipeline bindings are absent from Prefect.",
                            pipeline_run_id=pipeline.id,
                        )
                    )
                if pipeline.registry_sha256 != current_catalog_sha:
                    add(
                        ReconciliationIssue(
                            code="FLOW_CATALOG_HASH_MISMATCH",
                            severity="WARNING",
                            message=(
                                f"Pipeline catalog={pipeline.registry_sha256} "
                                f"current={current_catalog_sha}"
                            ),
                            pipeline_run_id=pipeline.id,
                        )
                    )
                if repository.get_environment_snapshot(
                    pipeline.environment_snapshot_id
                ) is None:
                    add(
                        ReconciliationIssue(
                            code="MISSING_ENVIRONMENT_SNAPSHOT",
                            severity="ERROR",
                            message="Pipeline environment snapshot is missing.",
                            pipeline_run_id=pipeline.id,
                        )
                    )
                if (
                    pipeline.status == "SUCCEEDED"
                    and repository.get_pipeline_run_receipt(pipeline.id) is None
                ):
                    add(
                        ReconciliationIssue(
                            code="SUCCEEDED_PIPELINE_MISSING_RECEIPT",
                            severity="ERROR",
                            message="Successful pipeline lacks immutable receipt.",
                            pipeline_run_id=pipeline.id,
                        )
                    )
                for stage in stages:
                    stage_links = [
                        item for item in task_bindings if item.stage_run_id == stage.id
                    ]
                    if not stage_links:
                        add(
                            ReconciliationIssue(
                                code="OPS_STAGE_WITHOUT_PREFECT_BINDING",
                                severity="ERROR",
                                message="Ops stage run has no Prefect task binding.",
                                pipeline_run_id=pipeline.id,
                                stage_run_id=stage.id,
                            )
                        )
                    elif not any(
                        item.prefect_task_run_id in prefect_tasks
                        for item in stage_links
                    ):
                        add(
                            ReconciliationIssue(
                                code="OPS_STAGE_PREFECT_TASK_MISSING",
                                severity="ERROR",
                                message="Ops stage bindings are absent from Prefect.",
                                pipeline_run_id=pipeline.id,
                                stage_run_id=stage.id,
                            )
                        )
                    if stage.status == "SUCCEEDED" and not repository.stage_outputs(
                        stage.id
                    ):
                        add(
                            ReconciliationIssue(
                                code="SUCCEEDED_STAGE_MISSING_OUTPUT",
                                severity="ERROR",
                                message="Successful stage has no registered output.",
                                pipeline_run_id=pipeline.id,
                                stage_run_id=stage.id,
                            )
                        )

            flow_identity_counts = Counter(
                (item.prefect_flow_run_id, item.attempt_number)
                for item in flow_bindings
            )
            task_identity_counts = Counter(
                (
                    item.prefect_flow_run_id,
                    item.prefect_task_run_id,
                    item.attempt_number,
                )
                for item in task_bindings
            )
            for identity, count in flow_identity_counts.items():
                if count > 1:
                    add(
                        ReconciliationIssue(
                            code="DUPLICATE_FLOW_BINDING",
                            severity="ERROR",
                            message=f"Duplicate Prefect flow binding: {identity}",
                            prefect_flow_run_id=identity[0],
                        )
                    )
            for identity, count in task_identity_counts.items():
                if count > 1:
                    add(
                        ReconciliationIssue(
                            code="DUPLICATE_TASK_BINDING",
                            severity="ERROR",
                            message=f"Duplicate Prefect task binding: {identity}",
                            prefect_flow_run_id=identity[0],
                            prefect_task_run_id=identity[1],
                        )
                    )

            approval_service = ApprovalService(repository)
            pending_approvals = repository.list_approvals(status="REQUESTED")
            if self.acceptance_session is not None:
                pending_approvals = [
                    item
                    for item in pending_approvals
                    if item.pipeline_run_id in pipeline_ids
                ]
            for approval in pending_approvals:
                before = approval.status
                approval_service.expire_if_needed(
                    approval, actor="prefect-reconciliation"
                )
                if approval.status == "EXPIRED":
                    repaired = mode == "repair-safe" and before != approval.status
                    pipeline = (
                        repository.get_pipeline_run(approval.pipeline_run_id)
                        if approval.pipeline_run_id
                        else None
                    )
                    if (
                        mode == "repair-safe"
                        and pipeline is not None
                        and pipeline.status == "WAITING_APPROVAL"
                    ):
                        bridge.transition_pipeline(
                            pipeline,
                            "FAILED",
                            error_summary=f"Approval expired: {approval.id}",
                        )
                        repaired = True
                    add(
                        ReconciliationIssue(
                            code="STALE_WAITING_APPROVAL",
                            severity="WARNING",
                            message="Pending approval has expired.",
                            pipeline_run_id=approval.pipeline_run_id,
                            approval_id=approval.id,
                            repairable=True,
                            repaired=repaired,
                        )
                    )
            if mode == "report-only":
                session.rollback()
            else:
                session.commit()

        error_count = sum(
            1 for item in issues if item.severity == "ERROR" and not item.repaired
        )
        warning_count = sum(1 for item in issues if item.severity == "WARNING")
        repaired_count = sum(1 for item in issues if item.repaired)
        return ReconciliationReport(
            mode=mode,
            passed=error_count == 0,
            checked_pipeline_runs=len(pipelines),
            checked_stage_runs=checked_stages,
            checked_flow_runs=len(flow_runs),
            checked_task_runs=len(task_runs),
            issue_count=len(issues),
            error_count=error_count,
            warning_count=warning_count,
            repaired_count=repaired_count,
            issues=tuple(issues),
        )


__all__ = [
    "PrefectFlowRunSnapshot",
    "PrefectTaskRunSnapshot",
    "ReconciliationReport",
    "ReconciliationService",
]
