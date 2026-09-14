from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from research.python.researchops.artifacts.ids import new_ulid
from research.python.researchops.ops_core.db.models import (
    EnvironmentSnapshot,
    OrchestrationBinding,
    PipelineRun,
    RunEvent,
    StageRun,
    StageRunOutput,
)
from research.python.researchops.ops_core.repositories.protocols import OpsRepository
from research.python.researchops.ops_core.services.state_transitions import LifecyclePolicy

from ..execution.errors import PolicyDeniedError


@dataclass(frozen=True)
class PipelineRunHandle:
    pipeline_run: PipelineRun
    binding: OrchestrationBinding
    reused: bool


@dataclass(frozen=True)
class StageRunHandle:
    stage_run: StageRun
    binding: OrchestrationBinding
    reused: bool
    outputs: tuple[StageRunOutput, ...] = ()


class OpsBridgeService:
    def __init__(self, repository: OpsRepository, *, orchestrator_version: str) -> None:
        self.repository = repository
        self.orchestrator_version = orchestrator_version
        self.lifecycle = LifecyclePolicy()

    def persist_environment(self, record: EnvironmentSnapshot) -> EnvironmentSnapshot:
        existing = self.repository.get_environment_snapshot(record.id)
        if existing is None:
            self.repository.add_environment_snapshot(record)
            self.repository.flush()
            return record
        return existing

    def create_or_reuse_pipeline(
        self,
        *,
        flow_id: str,
        flow_key: str,
        flow_catalog_sha256: str,
        source_commit: str,
        environment_snapshot_id: str,
        parameters: Mapping[str, Any],
        requested_by: str,
        trigger_type: str,
        prefect_flow_run_id: str,
        deployment_name: str | None,
        work_pool_name: str | None,
        work_queue_name: str | None,
    ) -> PipelineRunHandle:
        bindings = self.repository.orchestration_bindings_by_key("prefect", flow_key)
        invocation = len(bindings) + 1
        succeeded: PipelineRun | None = None
        active: PipelineRun | None = None
        same_prefect_active: tuple[PipelineRun, OrchestrationBinding] | None = None
        for binding in bindings:
            candidate = self.repository.get_pipeline_run(binding.pipeline_run_id)
            if candidate is None:
                continue
            if candidate.status == "SUCCEEDED":
                succeeded = candidate
            elif candidate.status in {"PENDING", "WAITING_APPROVAL", "RUNNING"}:
                if binding.prefect_flow_run_id == prefect_flow_run_id:
                    same_prefect_active = (candidate, binding)
                else:
                    active = candidate
        if same_prefect_active is not None:
            pipeline, existing_binding = same_prefect_active
            self._event(
                pipeline.id,
                None,
                "prefect.flow_resumed",
                {
                    "prefect_flow_run_id": prefect_flow_run_id,
                    "status": pipeline.status,
                },
            )
            return PipelineRunHandle(pipeline, existing_binding, False)
        if active is not None:
            raise PolicyDeniedError(
                f"Equivalent pipeline run is already active: {active.id}"
            )

        reused = succeeded is not None
        if reused:
            pipeline = succeeded
        else:
            pipeline = PipelineRun(
                id=f"run_{new_ulid()}",
                flow_id=flow_id,
                status="PENDING",
                trigger_type=trigger_type,
                requested_by=requested_by,
                registry_sha256=flow_catalog_sha256,
                source_commit=source_commit,
                environment_snapshot_id=environment_snapshot_id,
                idempotency_key=f"{flow_key}:attempt:{invocation}",
                parameters={
                    **dict(parameters),
                    "orchestration_key": flow_key,
                    "invocation": invocation,
                },
            )
            self.repository.add_pipeline_run(pipeline)
            self.repository.flush()
            self._event(
                pipeline.id,
                None,
                "pipeline.created",
                {"flow_id": flow_id, "orchestration_key": flow_key},
            )

        binding = OrchestrationBinding(
            id=f"binding_{new_ulid()}",
            orchestrator="prefect",
            orchestrator_version=self.orchestrator_version,
            pipeline_run_id=pipeline.id,
            stage_run_id=None,
            prefect_flow_run_id=prefect_flow_run_id,
            prefect_task_run_id=None,
            deployment_name=deployment_name,
            work_pool_name=work_pool_name,
            work_queue_name=work_queue_name,
            orchestration_key=flow_key,
            attempt_number=invocation,
            binding_metadata={"reused": reused, "kind": "FLOW"},
        )
        self.repository.add_orchestration_binding(binding)
        self.repository.flush()
        self._event(
            pipeline.id,
            None,
            "prefect.flow_bound",
            {
                "prefect_flow_run_id": prefect_flow_run_id,
                "reused": reused,
                "invocation": invocation,
            },
        )
        return PipelineRunHandle(pipeline, binding, reused)

    def create_or_reuse_stage(
        self,
        *,
        pipeline_run_id: str,
        node_id: str,
        stage_id: str,
        stage_version: int,
        stage_key: str,
        command_snapshot: Mapping[str, Any],
        approval_policy: str,
        prefect_flow_run_id: str,
        prefect_task_run_id: str,
        deployment_name: str | None,
        work_pool_name: str | None,
        work_queue_name: str | None,
    ) -> StageRunHandle:
        bindings = self.repository.orchestration_bindings_by_key("prefect", stage_key)
        invocation = len(bindings) + 1
        succeeded: StageRun | None = None
        active: StageRun | None = None
        for binding in bindings:
            if not binding.stage_run_id:
                continue
            candidate = self.repository.get_stage_run(binding.stage_run_id)
            if candidate is None:
                continue
            if candidate.status == "SUCCEEDED":
                succeeded = candidate
            elif candidate.status in {"PENDING", "WAITING_APPROVAL", "RUNNING"}:
                active = candidate
        if active is not None:
            raise PolicyDeniedError(
                f"Equivalent stage run is already active: {active.id}"
            )

        reused = succeeded is not None
        if reused:
            stage_run = succeeded
            outputs = tuple(self.repository.stage_outputs(stage_run.id))
        else:
            prior = self.repository.list_stage_runs(pipeline_run_id)
            attempt = 1 + max(
                (item.attempt for item in prior if item.stage_id == stage_id),
                default=0,
            )
            stage_run = StageRun(
                id=f"stage_run_{new_ulid()}",
                pipeline_run_id=pipeline_run_id,
                stage_id=stage_id,
                stage_version=stage_version,
                attempt=attempt,
                status="PENDING",
                command_snapshot={
                    **dict(command_snapshot),
                    "node_id": node_id,
                    "orchestration_key": stage_key,
                },
                approval_policy=approval_policy,
            )
            self.repository.add_stage_run(stage_run)
            self.repository.flush()
            outputs = ()
            self._event(
                pipeline_run_id,
                stage_run.id,
                "stage.created",
                {
                    "node_id": node_id,
                    "stage_id": stage_id,
                    "attempt": attempt,
                    "orchestration_key": stage_key,
                },
            )

        binding = OrchestrationBinding(
            id=f"binding_{new_ulid()}",
            orchestrator="prefect",
            orchestrator_version=self.orchestrator_version,
            pipeline_run_id=pipeline_run_id,
            stage_run_id=stage_run.id,
            prefect_flow_run_id=prefect_flow_run_id,
            prefect_task_run_id=prefect_task_run_id,
            deployment_name=deployment_name,
            work_pool_name=work_pool_name,
            work_queue_name=work_queue_name,
            orchestration_key=stage_key,
            attempt_number=invocation,
            binding_metadata={
                "reused": reused,
                "kind": "TASK",
                "node_id": node_id,
            },
        )
        self.repository.add_orchestration_binding(binding)
        self.repository.flush()
        self._event(
            pipeline_run_id,
            stage_run.id,
            "prefect.task_bound",
            {
                "prefect_task_run_id": prefect_task_run_id,
                "reused": reused,
                "invocation": invocation,
            },
        )
        return StageRunHandle(stage_run, binding, reused, outputs)

    def record_stage_output(
        self,
        *,
        stage_run_id: str,
        output_name: str,
        contract: str,
        artifact_id: str,
        manifest_sha256: str,
    ) -> StageRunOutput:
        existing = self.repository.get_stage_output(stage_run_id, output_name)
        if existing is not None:
            if (
                existing.artifact_id != artifact_id
                or existing.manifest_sha256 != manifest_sha256
                or existing.contract != contract
            ):
                raise PolicyDeniedError(
                    f"Stage output identity drift: {stage_run_id}.{output_name}"
                )
            return existing
        record = StageRunOutput(
            stage_run_id=stage_run_id,
            output_name=output_name,
            contract=contract,
            artifact_id=artifact_id,
            manifest_sha256=manifest_sha256,
        )
        self.repository.add_stage_output(record)
        self.repository.flush()
        return record

    def transition_pipeline(
        self,
        pipeline: PipelineRun,
        target: str,
        *,
        error_summary: str | None = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        before = pipeline.status
        self.lifecycle.require_allowed("pipeline_run", before, target)
        pipeline.status = target
        if target == "RUNNING" and pipeline.started_at is None:
            pipeline.started_at = now
        if target in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            pipeline.ended_at = now
        pipeline.error_summary = error_summary
        self.repository.flush()
        self._event(
            pipeline.id,
            None,
            "pipeline.status_changed",
            {"from": before, "to": target, "error_summary": error_summary},
        )

    def transition_stage(
        self,
        stage_run: StageRun,
        target: str,
        *,
        exit_code: int | None = None,
        error_type: str | None = None,
        error_category: str | None = None,
        retryable: bool | None = None,
        error_message: str | None = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        before = stage_run.status
        self.lifecycle.require_allowed("stage_run", before, target)
        stage_run.status = target
        if target == "RUNNING" and stage_run.started_at is None:
            stage_run.started_at = now
        if target in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            stage_run.ended_at = now
        stage_run.exit_code = exit_code
        stage_run.error_type = error_type
        stage_run.error_category = error_category
        stage_run.retryable = retryable
        stage_run.error_message = error_message
        self.repository.flush()
        self._event(
            stage_run.pipeline_run_id,
            stage_run.id,
            "stage.status_changed",
            {
                "from": before,
                "to": target,
                "exit_code": exit_code,
                "error_type": error_type,
                "error_category": error_category,
                "retryable": retryable,
            },
        )

    def reconcile_external_cancellation(
        self,
        pipeline: PipelineRun,
        *,
        reason: str,
    ) -> None:
        """Correct a provisional FAILED state after Prefect confirms cancellation.

        Normal lifecycle transitions keep terminal states immutable. This narrow
        reconciliation path exists because an externally cancelled worker can
        surface a generic termination exception before the Prefect API reaches
        its authoritative CANCELLED state. Only FAILED -> CANCELLED is allowed,
        and the correction is recorded as a dedicated run event.
        """

        if pipeline.status != "FAILED":
            raise PolicyDeniedError(
                "External cancellation reconciliation requires FAILED pipeline state"
            )
        now = datetime.now(timezone.utc)
        before = pipeline.status
        pipeline.status = "CANCELLED"
        pipeline.ended_at = now
        pipeline.error_summary = reason
        self.repository.flush()
        self._event(
            pipeline.id,
            None,
            "pipeline.status_reconciled",
            {
                "from": before,
                "to": "CANCELLED",
                "reason": reason,
                "authority": "prefect-terminal-state",
            },
        )

    def reconcile_external_stage_cancellation(
        self,
        stage_run: StageRun,
        *,
        reason: str,
    ) -> None:
        """Apply the matching audited FAILED -> CANCELLED stage correction."""

        if stage_run.status != "FAILED":
            raise PolicyDeniedError(
                "External cancellation reconciliation requires FAILED stage state"
            )
        now = datetime.now(timezone.utc)
        before = stage_run.status
        stage_run.status = "CANCELLED"
        stage_run.ended_at = now
        stage_run.error_type = "PrefectExternalCancellationReconciled"
        stage_run.error_message = reason
        self.repository.flush()
        self._event(
            stage_run.pipeline_run_id,
            stage_run.id,
            "stage.status_reconciled",
            {
                "from": before,
                "to": "CANCELLED",
                "reason": reason,
                "authority": "prefect-terminal-state",
            },
        )

    def _event(
        self,
        pipeline_run_id: str,
        stage_run_id: str | None,
        event_type: str,
        payload: Mapping[str, Any],
    ) -> None:
        self.repository.add_run_event(
            RunEvent(
                pipeline_run_id=pipeline_run_id,
                stage_run_id=stage_run_id,
                event_type=event_type,
                payload=dict(payload),
            )
        )
        self.repository.flush()
