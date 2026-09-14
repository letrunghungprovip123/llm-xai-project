from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from research.python.researchops.artifacts.ids import new_ulid
from research.python.researchops.ops_core.db.models import (
    ControlOperation,
    OrchestrationBinding,
    PipelineRun,
    PromotionDecision,
)


class ControlOperationService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        operation_type: str,
        requested_by: str,
        target_type: str,
        target_id: str,
        request_id: str,
        idempotency_request_id: str,
        request_payload: dict[str, Any],
    ) -> ControlOperation:
        now = datetime.now(timezone.utc)
        record = ControlOperation(
            id=f"op_{new_ulid()}",
            operation_type=operation_type,
            status="PENDING",
            requested_by=requested_by,
            target_type=target_type,
            target_id=target_id,
            request_id=request_id,
            idempotency_request_id=idempotency_request_id,
            request_payload=request_payload,
            result={},
            created_at=now,
            updated_at=now,
        )
        self.session.add(record)
        self.session.flush()
        return record

    def mark_running(self, operation: ControlOperation) -> None:
        operation.status = "RUNNING"
        operation.started_at = operation.started_at or datetime.now(timezone.utc)
        self.session.flush()

    def succeed(self, operation: ControlOperation, *, result: dict[str, Any]) -> None:
        operation.status = "SUCCEEDED"
        operation.result = result
        operation.completed_at = datetime.now(timezone.utc)
        self.session.flush()

    def fail(self, operation: ControlOperation, *, code: str, message: str, partial: bool = False, result: dict[str, Any] | None = None) -> None:
        operation.status = "FAILED_PARTIAL" if partial else "FAILED"
        operation.error_code = code
        operation.error_message = message
        operation.result = result or {}
        operation.completed_at = datetime.now(timezone.utc)
        self.session.flush()

    def get(self, operation_id: str) -> ControlOperation | None:
        return self.session.get(ControlOperation, operation_id)

    def list(self, *, status: str | None = None, requested_by: str | None = None) -> list[ControlOperation]:
        query = select(ControlOperation)
        if status is not None:
            query = query.where(ControlOperation.status == status)
        if requested_by is not None:
            query = query.where(ControlOperation.requested_by == requested_by)
        return list(self.session.scalars(query.order_by(ControlOperation.created_at.desc(), ControlOperation.id.desc())))

    def reconcile_prefect_binding(self, operation: ControlOperation) -> ControlOperation:
        if operation.prefect_flow_run_id and operation.pipeline_run_id is None:
            binding = self.session.scalar(
                select(OrchestrationBinding).where(
                    OrchestrationBinding.orchestrator == "prefect",
                    OrchestrationBinding.prefect_flow_run_id == operation.prefect_flow_run_id,
                    OrchestrationBinding.stage_run_id.is_(None),
                )
            )
            if binding is not None:
                operation.pipeline_run_id = binding.pipeline_run_id

        promotion_key = str(
            (operation.request_payload or {}).get("promotion_idempotency_key") or ""
        )
        if promotion_key and operation.promotion_decision_id is None:
            decision = self.session.scalar(
                select(PromotionDecision).where(
                    PromotionDecision.idempotency_key == promotion_key
                )
            )
            if decision is not None:
                operation.promotion_decision_id = decision.id

        decision = (
            self.session.get(PromotionDecision, operation.promotion_decision_id)
            if operation.promotion_decision_id
            else None
        )
        if decision is not None:
            operation.result = {
                **dict(operation.result or {}),
                "promotion_decision_id": decision.id,
                "promotion_execution_status": decision.execution_status,
            }
            if decision.execution_status == "COMPLETED":
                operation.status = "SUCCEEDED"
                operation.completed_at = decision.executed_at or datetime.now(timezone.utc)
            elif decision.execution_status == "FAILED_PARTIAL":
                operation.status = "FAILED_PARTIAL"
                operation.completed_at = decision.executed_at or datetime.now(timezone.utc)
            elif decision.execution_status == "FAILED":
                operation.status = "FAILED"
                operation.completed_at = decision.executed_at or datetime.now(timezone.utc)

        if operation.pipeline_run_id:
            pipeline = self.session.get(PipelineRun, operation.pipeline_run_id)
            if pipeline is not None:
                if pipeline.status in {"PENDING", "WAITING_APPROVAL", "RUNNING"}:
                    if operation.status == "PENDING":
                        operation.status = "RUNNING"
                        operation.started_at = (
                            operation.started_at or datetime.now(timezone.utc)
                        )
                elif decision is None or decision.execution_status == "PENDING":
                    is_promotion = operation.operation_type in {
                        "MODEL_PROMOTION",
                        "RELEASE_PROMOTION",
                    }
                    if is_promotion and pipeline.status == "SUCCEEDED":
                        # A successful promotion flow without a durable terminal
                        # PromotionDecision must never be surfaced as success.
                        # The decision is the auditable source of truth for the
                        # external/operational transition, not the Prefect shell.
                        operation.status = "FAILED"
                        operation.error_code = (
                            "PROMOTION_DECISION_MISSING"
                            if decision is None
                            else "PROMOTION_DECISION_INCOMPLETE"
                        )
                        operation.error_message = (
                            "Promotion flow completed without a durable terminal "
                            "promotion decision"
                        )
                    else:
                        operation.status = {
                            "SUCCEEDED": "SUCCEEDED",
                            "FAILED": "FAILED",
                            "CANCELLED": "CANCELLED",
                        }[pipeline.status]
                    operation.completed_at = (
                        pipeline.ended_at or datetime.now(timezone.utc)
                    )
        self.session.flush()
        return operation
