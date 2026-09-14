from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Generic, TypeVar

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from research.python.researchops.ops_core.db.models import (
    Approval,
    ArtifactFileRecord,
    ArtifactRecord,
    ControlOperation,
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

from .cursor import CursorPosition

T = TypeVar("T")


@dataclass(frozen=True)
class QueryPage(Generic[T]):
    items: list[T]
    has_more: bool


class SqlAlchemyOpsReadRepository:
    """Read-optimized SQLAlchemy queries for the control plane.

    This repository intentionally returns ORM entities only to the application
    query service. Routers never serialize these entities directly.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _after(created_column, id_column, position: CursorPosition | None):
        if position is None:
            return None
        return or_(
            created_column < position.created_at,
            and_(created_column == position.created_at, id_column < position.id),
        )

    def search_runs(
        self,
        *,
        limit: int,
        position: CursorPosition | None,
        flow_id: str | None = None,
        status: str | None = None,
        requested_by: str | None = None,
        source_commit: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
    ) -> QueryPage[PipelineRun]:
        query = select(PipelineRun)
        for condition in (
            PipelineRun.flow_id == flow_id if flow_id else None,
            PipelineRun.status == status if status else None,
            PipelineRun.requested_by == requested_by if requested_by else None,
            PipelineRun.source_commit == source_commit if source_commit else None,
            PipelineRun.created_at >= created_after if created_after else None,
            PipelineRun.created_at < created_before if created_before else None,
            self._after(PipelineRun.created_at, PipelineRun.id, position),
        ):
            if condition is not None:
                query = query.where(condition)
        rows = list(
            self.session.scalars(
                query.order_by(PipelineRun.created_at.desc(), PipelineRun.id.desc()).limit(limit + 1)
            )
        )
        return QueryPage(rows[:limit], len(rows) > limit)

    def search_operations(
        self,
        *,
        limit: int,
        position: CursorPosition | None,
        status: str | None = None,
        requested_by: str | None = None,
        operation_type: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
    ) -> QueryPage[ControlOperation]:
        query = select(ControlOperation)
        for condition in (
            ControlOperation.status == status if status else None,
            ControlOperation.requested_by == requested_by if requested_by else None,
            ControlOperation.operation_type == operation_type if operation_type else None,
            ControlOperation.target_type == target_type if target_type else None,
            ControlOperation.target_id == target_id if target_id else None,
            self._after(ControlOperation.created_at, ControlOperation.id, position),
        ):
            if condition is not None:
                query = query.where(condition)
        rows = list(
            self.session.scalars(
                query.order_by(
                    ControlOperation.created_at.desc(),
                    ControlOperation.id.desc(),
                ).limit(limit + 1)
            )
        )
        return QueryPage(rows[:limit], len(rows) > limit)

    def get_run(self, run_id: str) -> PipelineRun | None:
        return self.session.get(PipelineRun, run_id)

    def stage_runs(self, run_id: str) -> list[StageRun]:
        return list(
            self.session.scalars(
                select(StageRun)
                .where(StageRun.pipeline_run_id == run_id)
                .order_by(StageRun.created_at, StageRun.attempt, StageRun.id)
            )
        )

    def run_events(self, run_id: str) -> list[RunEvent]:
        return list(
            self.session.scalars(
                select(RunEvent)
                .where(RunEvent.pipeline_run_id == run_id)
                .order_by(RunEvent.occurred_at, RunEvent.id)
            )
        )

    def run_outputs(self, run_id: str) -> list[StageRunOutput]:
        return list(
            self.session.scalars(
                select(StageRunOutput)
                .join(StageRun, StageRun.id == StageRunOutput.stage_run_id)
                .where(StageRun.pipeline_run_id == run_id)
                .order_by(StageRunOutput.stage_run_id, StageRunOutput.output_name)
            )
        )

    def run_receipt(self, run_id: str) -> PipelineRunReceipt | None:
        return self.session.get(PipelineRunReceipt, run_id)

    def run_prefect_binding(self, run_id: str) -> OrchestrationBinding | None:
        return self.session.scalar(
            select(OrchestrationBinding)
            .where(
                OrchestrationBinding.pipeline_run_id == run_id,
                OrchestrationBinding.prefect_task_run_id.is_(None),
            )
            .order_by(OrchestrationBinding.attempt_number.desc())
            .limit(1)
        )

    def search_artifacts(
        self,
        *,
        limit: int,
        position: CursorPosition | None,
        artifact_type: str | None = None,
        schema_version: str | None = None,
        status: str | None = None,
        producer_stage_run_id: str | None = None,
        source_commit: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
    ) -> QueryPage[ArtifactRecord]:
        query = select(ArtifactRecord)
        for condition in (
            ArtifactRecord.artifact_type == artifact_type if artifact_type else None,
            ArtifactRecord.schema_version == schema_version if schema_version else None,
            ArtifactRecord.status == status if status else None,
            ArtifactRecord.producer_stage_run_id == producer_stage_run_id if producer_stage_run_id else None,
            ArtifactRecord.source_commit == source_commit if source_commit else None,
            ArtifactRecord.created_at >= created_after if created_after else None,
            ArtifactRecord.created_at < created_before if created_before else None,
            self._after(ArtifactRecord.created_at, ArtifactRecord.id, position),
        ):
            if condition is not None:
                query = query.where(condition)
        rows = list(
            self.session.scalars(
                query.order_by(ArtifactRecord.created_at.desc(), ArtifactRecord.id.desc()).limit(limit + 1)
            )
        )
        return QueryPage(rows[:limit], len(rows) > limit)

    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None:
        return self.session.get(ArtifactRecord, artifact_id)

    def artifact_files(self, artifact_id: str) -> list[ArtifactFileRecord]:
        return list(
            self.session.scalars(
                select(ArtifactFileRecord)
                .where(ArtifactFileRecord.artifact_id == artifact_id)
                .order_by(ArtifactFileRecord.relative_path)
            )
        )

    def artifact_release_memberships(self, artifact_id: str) -> list[ReleaseArtifact]:
        return list(
            self.session.scalars(
                select(ReleaseArtifact)
                .where(ReleaseArtifact.artifact_id == artifact_id)
                .order_by(ReleaseArtifact.release_id, ReleaseArtifact.role)
            )
        )

    def lineage_edges(self, artifact_ids: set[str]) -> list[LineageEdge]:
        if not artifact_ids:
            return []
        return list(
            self.session.scalars(
                select(LineageEdge)
                .where(
                    or_(
                        LineageEdge.parent_artifact_id.in_(artifact_ids),
                        LineageEdge.child_artifact_id.in_(artifact_ids),
                    )
                )
                .order_by(
                    LineageEdge.parent_artifact_id,
                    LineageEdge.child_artifact_id,
                    LineageEdge.relationship_type,
                )
            )
        )

    def artifacts_by_ids(self, artifact_ids: set[str]) -> list[ArtifactRecord]:
        if not artifact_ids:
            return []
        return list(
            self.session.scalars(
                select(ArtifactRecord)
                .where(ArtifactRecord.id.in_(artifact_ids))
                .order_by(ArtifactRecord.id)
            )
        )

    def direct_parents(self, artifact_id: str) -> list[str]:
        return list(
            self.session.scalars(
                select(LineageEdge.parent_artifact_id)
                .where(LineageEdge.child_artifact_id == artifact_id)
                .order_by(LineageEdge.parent_artifact_id)
            )
        )

    def direct_children(self, artifact_id: str) -> list[str]:
        return list(
            self.session.scalars(
                select(LineageEdge.child_artifact_id)
                .where(LineageEdge.parent_artifact_id == artifact_id)
                .order_by(LineageEdge.child_artifact_id)
            )
        )

    def search_gates(
        self,
        *,
        limit: int,
        position: CursorPosition | None,
        gate_id: str | None = None,
        scope_type: str | None = None,
        scope_id: str | None = None,
        effective_status: str | None = None,
        blocking: bool | None = None,
    ) -> QueryPage[GateResult]:
        query = select(GateResult)
        for condition in (
            GateResult.gate_id == gate_id if gate_id else None,
            GateResult.scope_type == scope_type if scope_type else None,
            GateResult.scope_id == scope_id if scope_id else None,
            GateResult.effective_status == effective_status if effective_status else None,
            GateResult.blocking == blocking if blocking is not None else None,
            self._after(GateResult.updated_at, GateResult.id, position),
        ):
            if condition is not None:
                query = query.where(condition)
        rows = list(
            self.session.scalars(
                query.order_by(GateResult.updated_at.desc(), GateResult.id.desc()).limit(limit + 1)
            )
        )
        return QueryPage(rows[:limit], len(rows) > limit)

    def get_gate_result_by_id(self, gate_result_id: str) -> GateResult | None:
        return self.session.get(GateResult, gate_result_id)

    def scope_gates(self, scope_type: str, scope_id: str) -> list[GateResult]:
        return list(
            self.session.scalars(
                select(GateResult)
                .where(GateResult.scope_type == scope_type, GateResult.scope_id == scope_id)
                .order_by(GateResult.gate_id)
            )
        )

    def gate_history(self, gate_id: str, scope_type: str, scope_id: str) -> list[GateEvaluation]:
        return list(
            self.session.scalars(
                select(GateEvaluation)
                .where(
                    GateEvaluation.gate_id == gate_id,
                    GateEvaluation.scope_type == scope_type,
                    GateEvaluation.scope_id == scope_id,
                )
                .order_by(GateEvaluation.evaluated_at.desc(), GateEvaluation.id.desc())
            )
        )

    def get_gate_evaluation(self, evaluation_id: str) -> GateEvaluation | None:
        return self.session.get(GateEvaluation, evaluation_id)

    def active_waiver(self, gate_result_id: str, evaluation_id: str | None) -> GateWaiver | None:
        if evaluation_id is None:
            return None
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

    def search_approvals(
        self,
        *,
        limit: int,
        position: CursorPosition | None,
        status: str | None = None,
        policy: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        pipeline_run_id: str | None = None,
        requested_by: str | None = None,
    ) -> QueryPage[Approval]:
        query = select(Approval)
        for condition in (
            Approval.status == status if status else None,
            Approval.policy == policy if policy else None,
            Approval.target_type == target_type if target_type else None,
            Approval.target_id == target_id if target_id else None,
            Approval.pipeline_run_id == pipeline_run_id if pipeline_run_id else None,
            Approval.requested_by == requested_by if requested_by else None,
            self._after(Approval.requested_at, Approval.id, position),
        ):
            if condition is not None:
                query = query.where(condition)
        rows = list(
            self.session.scalars(
                query.order_by(Approval.requested_at.desc(), Approval.id.desc()).limit(limit + 1)
            )
        )
        return QueryPage(rows[:limit], len(rows) > limit)

    def get_approval(self, approval_id: str) -> Approval | None:
        return self.session.get(Approval, approval_id)

    def search_releases(
        self,
        *,
        limit: int,
        position: CursorPosition | None,
        release_type: str | None = None,
        status: str | None = None,
        source_commit: str | None = None,
    ) -> QueryPage[ReleaseRecord]:
        query = select(ReleaseRecord)
        for condition in (
            ReleaseRecord.release_type == release_type if release_type else None,
            ReleaseRecord.status == status if status else None,
            ReleaseRecord.source_commit == source_commit if source_commit else None,
            self._after(ReleaseRecord.created_at, ReleaseRecord.id, position),
        ):
            if condition is not None:
                query = query.where(condition)
        rows = list(
            self.session.scalars(
                query.order_by(ReleaseRecord.created_at.desc(), ReleaseRecord.id.desc()).limit(limit + 1)
            )
        )
        return QueryPage(rows[:limit], len(rows) > limit)

    def get_release(self, release_id: str) -> ReleaseRecord | None:
        return self.session.get(ReleaseRecord, release_id)

    def release_artifacts(self, release_id: str) -> list[ReleaseArtifact]:
        return list(
            self.session.scalars(
                select(ReleaseArtifact)
                .where(ReleaseArtifact.release_id == release_id)
                .order_by(ReleaseArtifact.role, ReleaseArtifact.artifact_id)
            )
        )

    def promotion_decisions(self, target_type: str, target_id: str) -> list[PromotionDecision]:
        return list(
            self.session.scalars(
                select(PromotionDecision)
                .where(PromotionDecision.target_type == target_type, PromotionDecision.target_id == target_id)
                .order_by(PromotionDecision.created_at.desc(), PromotionDecision.id.desc())
            )
        )
