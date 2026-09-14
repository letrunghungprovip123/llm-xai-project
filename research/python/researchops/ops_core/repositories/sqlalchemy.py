from __future__ import annotations

from collections import deque

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import (
    Approval,
    ArtifactFileRecord,
    ArtifactRecord,
    AuditEvent,
    EnvironmentSnapshot,
    GateEvaluation,
    GateResult,
    GateWaiver,
    LineageEdge,
    OrchestrationBinding,
    PipelineRun,
    PipelineRunReceipt,
    PromotionDecision,
    ReleaseArtifact,
    ReleaseRecord,
    RunEvent,
    StageRun,
    StageRunOutput,
)


class SqlAlchemyOpsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None:
        return self.session.get(ArtifactRecord, artifact_id)

    def get_artifact_by_manifest_hash(self, sha256: str) -> ArtifactRecord | None:
        return self.session.scalar(
            select(ArtifactRecord).where(ArtifactRecord.manifest_sha256 == sha256)
        )

    def list_artifact_ids(self) -> set[str]:
        return set(self.session.scalars(select(ArtifactRecord.id)))

    def add_artifact(self, record: ArtifactRecord) -> None:
        self.session.add(record)

    def add_artifact_file(self, record: ArtifactFileRecord) -> None:
        self.session.add(record)

    def add_lineage_edge(self, edge: LineageEdge) -> None:
        self.session.add(edge)

    def _walk(self, artifact_id: str, *, forward: bool) -> set[str]:
        visited: set[str] = set()
        queue = deque([artifact_id])
        while queue:
            current = queue.popleft()
            column = (
                LineageEdge.parent_artifact_id
                if forward
                else LineageEdge.child_artifact_id
            )
            target = (
                LineageEdge.child_artifact_id
                if forward
                else LineageEdge.parent_artifact_id
            )
            for item in self.session.scalars(select(target).where(column == current)):
                if item not in visited:
                    visited.add(item)
                    queue.append(item)
        visited.discard(artifact_id)
        return visited

    def descendants(self, artifact_id: str) -> set[str]:
        return self._walk(artifact_id, forward=True)

    def ancestors(self, artifact_id: str) -> set[str]:
        return self._walk(artifact_id, forward=False)

    def get_release(self, release_id: str) -> ReleaseRecord | None:
        return self.session.get(ReleaseRecord, release_id)

    def add_release(self, record: ReleaseRecord) -> None:
        self.session.add(record)

    def add_release_artifact(self, record: ReleaseArtifact) -> None:
        self.session.add(record)

    def release_artifact_ids(self, release_id: str) -> set[str]:
        return set(
            self.session.scalars(
                select(ReleaseArtifact.artifact_id).where(
                    ReleaseArtifact.release_id == release_id
                )
            )
        )

    def blocking_gates(self, scope_type: str, scope_id: str) -> list[GateResult]:
        return list(
            self.session.scalars(
                select(GateResult).where(
                    GateResult.scope_type == scope_type,
                    GateResult.scope_id == scope_id,
                    GateResult.blocking.is_(True),
                )
            )
        )

    def get_gate_result(
        self, gate_id: str, scope_type: str, scope_id: str
    ) -> GateResult | None:
        return self.session.scalar(
            select(GateResult).where(
                GateResult.gate_id == gate_id,
                GateResult.scope_type == scope_type,
                GateResult.scope_id == scope_id,
            )
        )

    def add_gate_result(self, record: GateResult) -> None:
        self.session.add(record)

    def get_gate_evaluation(self, evaluation_id: str) -> GateEvaluation | None:
        return self.session.get(GateEvaluation, evaluation_id)

    def get_gate_evaluation_by_key(self, key: str) -> GateEvaluation | None:
        return self.session.scalar(
            select(GateEvaluation).where(GateEvaluation.evaluation_key == key)
        )

    def list_gate_evaluations(
        self, gate_id: str, scope_type: str, scope_id: str
    ) -> list[GateEvaluation]:
        return list(
            self.session.scalars(
                select(GateEvaluation)
                .where(
                    GateEvaluation.gate_id == gate_id,
                    GateEvaluation.scope_type == scope_type,
                    GateEvaluation.scope_id == scope_id,
                )
                .order_by(GateEvaluation.evaluated_at, GateEvaluation.id)
            )
        )

    def add_gate_evaluation(self, record: GateEvaluation) -> None:
        self.session.add(record)

    def get_gate_result_by_id(self, gate_result_id: str) -> GateResult | None:
        return self.session.get(GateResult, gate_result_id)

    def approvals(self, target_type: str, target_id: str) -> list[Approval]:
        return list(
            self.session.scalars(
                select(Approval).where(
                    Approval.target_type == target_type,
                    Approval.target_id == target_id,
                )
            )
        )

    def get_approval(self, approval_id: str) -> Approval | None:
        return self.session.get(Approval, approval_id)

    def get_approval_by_request_key(self, request_key: str) -> Approval | None:
        return self.session.scalar(
            select(Approval).where(Approval.request_key == request_key)
        )

    def list_approvals(
        self, *, status: str | None = None, pipeline_run_id: str | None = None
    ) -> list[Approval]:
        query = select(Approval)
        if status is not None:
            query = query.where(Approval.status == status)
        if pipeline_run_id is not None:
            query = query.where(Approval.pipeline_run_id == pipeline_run_id)
        return list(self.session.scalars(query.order_by(Approval.requested_at, Approval.id)))

    def add_approval(self, record: Approval) -> None:
        self.session.add(record)

    def get_gate_waiver(self, waiver_id: str) -> GateWaiver | None:
        return self.session.get(GateWaiver, waiver_id)

    def get_gate_waiver_by_request_key(self, key: str) -> GateWaiver | None:
        return self.session.scalar(
            select(GateWaiver).where(GateWaiver.request_key == key)
        )

    def active_gate_waiver(
        self, gate_result_id: str, evaluation_id: str
    ) -> GateWaiver | None:
        return self.session.scalar(
            select(GateWaiver)
            .where(
                GateWaiver.gate_result_id == gate_result_id,
                GateWaiver.evaluation_id == evaluation_id,
                GateWaiver.status == "ACTIVE",
            )
            .order_by(GateWaiver.created_at.desc(), GateWaiver.id.desc())
            .limit(1)
        )

    def list_gate_waivers(
        self, *, scope_type: str | None = None, scope_id: str | None = None
    ) -> list[GateWaiver]:
        query = select(GateWaiver)
        if scope_type is not None:
            query = query.where(GateWaiver.scope_type == scope_type)
        if scope_id is not None:
            query = query.where(GateWaiver.scope_id == scope_id)
        return list(self.session.scalars(query.order_by(GateWaiver.created_at, GateWaiver.id)))

    def add_gate_waiver(self, record: GateWaiver) -> None:
        self.session.add(record)

    def get_promotion_decision(self, decision_id: str) -> PromotionDecision | None:
        return self.session.get(PromotionDecision, decision_id)

    def get_promotion_decision_by_key(self, key: str) -> PromotionDecision | None:
        return self.session.scalar(
            select(PromotionDecision).where(PromotionDecision.idempotency_key == key)
        )

    def list_promotion_decisions(
        self, *, target_type: str | None = None, target_id: str | None = None
    ) -> list[PromotionDecision]:
        query = select(PromotionDecision)
        if target_type is not None:
            query = query.where(PromotionDecision.target_type == target_type)
        if target_id is not None:
            query = query.where(PromotionDecision.target_id == target_id)
        return list(self.session.scalars(query.order_by(PromotionDecision.created_at, PromotionDecision.id)))

    def add_promotion_decision(self, record: PromotionDecision) -> None:
        self.session.add(record)

    def get_environment_snapshot(self, snapshot_id: str) -> EnvironmentSnapshot | None:
        return self.session.get(EnvironmentSnapshot, snapshot_id)

    def add_environment_snapshot(self, record: EnvironmentSnapshot) -> None:
        self.session.add(record)

    def get_pipeline_run(self, run_id: str) -> PipelineRun | None:
        return self.session.get(PipelineRun, run_id)

    def get_pipeline_run_by_idempotency_key(self, key: str) -> PipelineRun | None:
        return self.session.scalar(
            select(PipelineRun).where(PipelineRun.idempotency_key == key)
        )

    def list_pipeline_runs(self) -> list[PipelineRun]:
        return list(self.session.scalars(select(PipelineRun)))

    def add_pipeline_run(self, record: PipelineRun) -> None:
        self.session.add(record)

    def get_pipeline_run_receipt(
        self, pipeline_run_id: str
    ) -> PipelineRunReceipt | None:
        return self.session.get(PipelineRunReceipt, pipeline_run_id)

    def add_pipeline_run_receipt(self, record: PipelineRunReceipt) -> None:
        self.session.add(record)

    def get_stage_run(self, stage_run_id: str) -> StageRun | None:
        return self.session.get(StageRun, stage_run_id)

    def list_stage_runs(self, pipeline_run_id: str) -> list[StageRun]:
        return list(
            self.session.scalars(
                select(StageRun)
                .where(StageRun.pipeline_run_id == pipeline_run_id)
                .order_by(StageRun.created_at, StageRun.attempt)
            )
        )

    def add_stage_run(self, record: StageRun) -> None:
        self.session.add(record)

    def add_run_event(self, record: RunEvent) -> None:
        self.session.add(record)

    def list_run_events(self, pipeline_run_id: str) -> list[RunEvent]:
        return list(
            self.session.scalars(
                select(RunEvent)
                .where(RunEvent.pipeline_run_id == pipeline_run_id)
                .order_by(RunEvent.occurred_at, RunEvent.id)
            )
        )

    def get_orchestration_binding_by_key(
        self, orchestrator: str, key: str, attempt_number: int
    ) -> OrchestrationBinding | None:
        return self.session.scalar(
            select(OrchestrationBinding).where(
                OrchestrationBinding.orchestrator == orchestrator,
                OrchestrationBinding.orchestration_key == key,
                OrchestrationBinding.attempt_number == attempt_number,
            )
        )

    def get_orchestration_binding_for_prefect(
        self,
        orchestrator: str,
        prefect_flow_run_id: str,
        prefect_task_run_id: str | None,
    ) -> OrchestrationBinding | None:
        query = select(OrchestrationBinding).where(
            OrchestrationBinding.orchestrator == orchestrator,
            OrchestrationBinding.prefect_flow_run_id == prefect_flow_run_id,
        )
        if prefect_task_run_id is None:
            query = query.where(OrchestrationBinding.prefect_task_run_id.is_(None))
        else:
            query = query.where(
                OrchestrationBinding.prefect_task_run_id == prefect_task_run_id
            )
        return self.session.scalar(
            query.order_by(OrchestrationBinding.attempt_number.desc()).limit(1)
        )

    def list_orchestration_bindings(self) -> list[OrchestrationBinding]:
        return list(self.session.scalars(select(OrchestrationBinding)))

    def orchestration_bindings_by_key(
        self, orchestrator: str, key: str
    ) -> list[OrchestrationBinding]:
        return list(
            self.session.scalars(
                select(OrchestrationBinding)
                .where(
                    OrchestrationBinding.orchestrator == orchestrator,
                    OrchestrationBinding.orchestration_key == key,
                )
                .order_by(OrchestrationBinding.attempt_number)
            )
        )

    def add_orchestration_binding(self, record: OrchestrationBinding) -> None:
        self.session.add(record)

    def get_stage_output(
        self, stage_run_id: str, output_name: str
    ) -> StageRunOutput | None:
        return self.session.get(StageRunOutput, (stage_run_id, output_name))

    def stage_outputs(self, stage_run_id: str) -> list[StageRunOutput]:
        return list(
            self.session.scalars(
                select(StageRunOutput)
                .where(StageRunOutput.stage_run_id == stage_run_id)
                .order_by(StageRunOutput.output_name)
            )
        )

    def add_stage_output(self, record: StageRunOutput) -> None:
        self.session.add(record)

    def artifacts_for_stage_run(self, stage_run_id: str) -> set[str]:
        produced = set(
            self.session.scalars(
                select(ArtifactRecord.id).where(
                    ArtifactRecord.producer_stage_run_id == stage_run_id
                )
            )
        )
        linked = set(
            self.session.scalars(
                select(StageRunOutput.artifact_id).where(
                    StageRunOutput.stage_run_id == stage_run_id
                )
            )
        )
        return produced | linked

    def succeeded_stage_runs_without_artifacts(self) -> set[str]:
        produced = select(ArtifactRecord.producer_stage_run_id).where(
            ArtifactRecord.producer_stage_run_id.is_not(None)
        )
        linked = select(StageRunOutput.stage_run_id)
        return set(
            self.session.scalars(
                select(StageRun.id).where(
                    StageRun.status == "SUCCEEDED",
                    StageRun.id.not_in(produced),
                    StageRun.id.not_in(linked),
                )
            )
        )

    def add_audit_event(self, record: AuditEvent) -> None:
        self.session.add(record)

    def flush(self) -> None:
        self.session.flush()
