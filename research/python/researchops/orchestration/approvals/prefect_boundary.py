from __future__ import annotations

from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field

from research.python.researchops.ops_core.repositories.sqlalchemy import (
    SqlAlchemyOpsRepository,
)
from research.python.researchops.stage_registry.models import StageDefinition

from ..execution.errors import PolicyDeniedError
from ..ops_bridge.service import OpsBridgeService
from ..runtime import OrchestrationRuntime, load_orchestration_runtime
from .service import ApprovalDecisionError, ApprovalService


class ApprovalResumeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approval_id: str = Field(min_length=1)
    acknowledgement: Literal["decision-recorded"] = "decision-recorded"


SuspendCallable = Callable[..., Any]


def _default_suspend(**kwargs: Any) -> Any:
    from prefect.flow_runs import suspend_flow_run

    return suspend_flow_run(**kwargs)


class PrefectApprovalBoundary:
    """Suspend a deployed Prefect flow while Ops DB remains authoritative."""

    def __init__(
        self,
        runtime: OrchestrationRuntime | None = None,
        *,
        suspend_callable: SuspendCallable | None = None,
        timeout_seconds: int | None = 86400,
        prefect_flow_run_id: str | None = None,
    ) -> None:
        self.runtime = runtime or load_orchestration_runtime()
        self.suspend_callable = suspend_callable or _default_suspend
        self.timeout_seconds = timeout_seconds
        self.prefect_flow_run_id = prefect_flow_run_id

    def _flow_run_id(self) -> str:
        if self.prefect_flow_run_id:
            return self.prefect_flow_run_id
        from prefect import runtime

        return str(runtime.flow_run.id)

    def require(
        self,
        *,
        stage: StageDefinition,
        pipeline_run_id: str,
        node_id: str,
        requested_by: str,
    ) -> None:
        flow_run_id = self._flow_run_id()
        with self.runtime.session_factory() as session:
            repository = SqlAlchemyOpsRepository(session)
            approval = ApprovalService(repository).request(
                pipeline_run_id=pipeline_run_id,
                node_id=node_id,
                stage_id=stage.id,
                policy=stage.behavior.approval_policy,
                requested_by=requested_by,
                prefect_flow_run_id=flow_run_id,
                timeout_seconds=self.timeout_seconds,
                details={"stage_version": stage.version},
            )
            pipeline = repository.get_pipeline_run(pipeline_run_id)
            assert pipeline is not None
            if approval.status == "APPROVED":
                try:
                    ApprovalService(repository).require_approved(
                        approval.id,
                        pipeline_run_id=pipeline_run_id,
                        node_id=node_id,
                        stage_id=stage.id,
                        policy=stage.behavior.approval_policy,
                    )
                except ApprovalDecisionError as exc:
                    if pipeline.status == "RUNNING":
                        OpsBridgeService(
                            repository, orchestrator_version="3.7.8"
                        ).transition_pipeline(
                            pipeline,
                            "FAILED",
                            error_summary=str(exc),
                        )
                    session.commit()
                    raise PolicyDeniedError(str(exc)) from exc
                session.commit()
                return
            if approval.status in {"REJECTED", "EXPIRED"}:
                if pipeline.status == "RUNNING":
                    OpsBridgeService(
                        repository, orchestrator_version="3.7.8"
                    ).transition_pipeline(
                        pipeline,
                        "FAILED",
                        error_summary=f"Approval {approval.status.lower()}: {approval.id}",
                    )
                session.commit()
                raise PolicyDeniedError(
                    f"Protected stage approval {approval.status.lower()}: {approval.id}"
                )
            if pipeline.status == "RUNNING":
                OpsBridgeService(
                    repository, orchestrator_version="3.7.8"
                ).transition_pipeline(pipeline, "WAITING_APPROVAL")
            session.commit()
            approval_id = approval.id
            resume_key = str(approval.details["resume_key"])

        resume_input = self.suspend_callable(
            wait_for_input=ApprovalResumeInput,
            timeout=self.timeout_seconds,
            key=resume_key,
        )
        if isinstance(resume_input, dict):
            resume_input = ApprovalResumeInput.model_validate(resume_input)
        if resume_input is None:
            raise PolicyDeniedError(
                "Prefect resumed a protected stage without the required approval input"
            )
        if resume_input.approval_id != approval_id:
            raise PolicyDeniedError(
                "Prefect resume input references a different approval"
            )

        with self.runtime.session_factory() as session:
            repository = SqlAlchemyOpsRepository(session)
            service = ApprovalService(repository)
            try:
                service.require_approved(
                    approval_id,
                    pipeline_run_id=pipeline_run_id,
                    node_id=node_id,
                    stage_id=stage.id,
                    policy=stage.behavior.approval_policy,
                )
            except ApprovalDecisionError as exc:
                pipeline = repository.get_pipeline_run(pipeline_run_id)
                if pipeline is not None and pipeline.status == "WAITING_APPROVAL":
                    OpsBridgeService(
                        repository, orchestrator_version="3.7.8"
                    ).transition_pipeline(
                        pipeline,
                        "FAILED",
                        error_summary=str(exc),
                    )
                session.commit()
                raise PolicyDeniedError(str(exc)) from exc
            pipeline = repository.get_pipeline_run(pipeline_run_id)
            assert pipeline is not None
            if pipeline.status == "WAITING_APPROVAL":
                OpsBridgeService(
                    repository, orchestrator_version="3.7.8"
                ).transition_pipeline(pipeline, "RUNNING")
            session.commit()
