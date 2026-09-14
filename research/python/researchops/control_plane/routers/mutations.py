from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..commands import ControlCommandService
from ..contracts.mutations import (
    ApprovalDecisionRequest,
    ArtifactActionRequest,
    ModelPromotionRequest,
    MutationResult,
    OperationAccepted,
    ReleasePromotionRequest,
    RunCancelRequest,
    RunRetryRequest,
    RunTriggerRequest,
    WaiverGrantRequest,
    WaiverRevokeRequest,
    validate_idempotency_key,
)
from ..dependencies import get_composition, get_session
from ..security import Principal, require_roles

router = APIRouter(tags=["control-actions"])


def _idempotency_key(
    value: Annotated[
        str, Header(alias="Idempotency-Key", min_length=1, max_length=255)
    ],
) -> str:
    try:
        return validate_idempotency_key(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


IdempotencyKey = Annotated[str, Depends(_idempotency_key)]


def _service(request: Request, session: Session, principal: Principal) -> ControlCommandService:
    return ControlCommandService(
        session=session,
        composition=get_composition(request),
        principal=principal,
        request_id=request.state.request_id,
    )


@router.post("/api/v1/runs", response_model=OperationAccepted, status_code=status.HTTP_202_ACCEPTED, operation_id="trigger_run")
async def trigger_run(body: RunTriggerRequest, request: Request, idempotency_key: IdempotencyKey, session: Session = Depends(get_session), principal: Principal = Depends(require_roles("operator"))):
    return await _service(request, session, principal).submit_run(body, idempotency_key=idempotency_key)


@router.post("/api/v1/runs/{run_id}/cancel", response_model=OperationAccepted, status_code=status.HTTP_202_ACCEPTED, operation_id="cancel_run")
async def cancel_run(run_id: str, body: RunCancelRequest, request: Request, idempotency_key: IdempotencyKey, session: Session = Depends(get_session), principal: Principal = Depends(require_roles("operator"))):
    return await _service(request, session, principal).cancel_run(run_id, body, idempotency_key=idempotency_key)


@router.post("/api/v1/runs/{run_id}/retry", response_model=OperationAccepted, status_code=status.HTTP_202_ACCEPTED, operation_id="retry_run")
async def retry_run(run_id: str, body: RunRetryRequest, request: Request, idempotency_key: IdempotencyKey, session: Session = Depends(get_session), principal: Principal = Depends(require_roles("operator"))):
    return await _service(request, session, principal).retry_run(run_id, body, idempotency_key=idempotency_key)


@router.post("/api/v1/approvals/{approval_id}/approve", response_model=MutationResult, operation_id="approve_request")
def approve(approval_id: str, body: ApprovalDecisionRequest, request: Request, idempotency_key: IdempotencyKey, session: Session = Depends(get_session), principal: Principal = Depends(require_roles("approver"))):
    return _service(request, session, principal).decide_approval(approval_id, body, decision="APPROVED", idempotency_key=idempotency_key)


@router.post("/api/v1/approvals/{approval_id}/reject", response_model=MutationResult, operation_id="reject_request")
def reject(approval_id: str, body: ApprovalDecisionRequest, request: Request, idempotency_key: IdempotencyKey, session: Session = Depends(get_session), principal: Principal = Depends(require_roles("approver"))):
    return _service(request, session, principal).decide_approval(approval_id, body, decision="REJECTED", idempotency_key=idempotency_key)


@router.post("/api/v1/gates/{gate_result_id}/waivers", response_model=MutationResult, operation_id="grant_gate_waiver")
def grant_waiver(gate_result_id: str, body: WaiverGrantRequest, request: Request, idempotency_key: IdempotencyKey, session: Session = Depends(get_session), principal: Principal = Depends(require_roles("approver"))):
    return _service(request, session, principal).grant_waiver(gate_result_id, body, idempotency_key=idempotency_key)


@router.post("/api/v1/waivers/{waiver_id}/revoke", response_model=MutationResult, operation_id="revoke_gate_waiver")
def revoke_waiver(waiver_id: str, body: WaiverRevokeRequest, request: Request, idempotency_key: IdempotencyKey, session: Session = Depends(get_session), principal: Principal = Depends(require_roles("approver"))):
    return _service(request, session, principal).revoke_waiver(waiver_id, body, idempotency_key=idempotency_key)


@router.post("/api/v1/artifacts/{artifact_id}/verifications", response_model=MutationResult, operation_id="verify_artifact")
def verify_artifact(artifact_id: str, body: ArtifactActionRequest, request: Request, idempotency_key: IdempotencyKey, session: Session = Depends(get_session), principal: Principal = Depends(require_roles("operator"))):
    return _service(request, session, principal).verify_artifact(artifact_id, body, idempotency_key=idempotency_key)


@router.post("/api/v1/artifacts/{artifact_id}/evaluations", response_model=MutationResult, operation_id="reevaluate_artifact")
def reevaluate_artifact(artifact_id: str, body: ArtifactActionRequest, request: Request, idempotency_key: IdempotencyKey, session: Session = Depends(get_session), principal: Principal = Depends(require_roles("operator"))):
    return _service(request, session, principal).reevaluate_artifact(artifact_id, body, idempotency_key=idempotency_key)


@router.post("/api/v1/releases/{release_id}/promotions", response_model=OperationAccepted, status_code=status.HTTP_202_ACCEPTED, operation_id="promote_release")
async def promote_release(release_id: str, body: ReleasePromotionRequest, request: Request, idempotency_key: IdempotencyKey, session: Session = Depends(get_session), principal: Principal = Depends(require_roles("release-manager"))):
    return await _service(request, session, principal).promote_release(release_id, body, idempotency_key=idempotency_key)


@router.post("/api/v1/models/{model_name}/versions/{version}/promotions", response_model=OperationAccepted, status_code=status.HTTP_202_ACCEPTED, operation_id="promote_model_version")
async def promote_model(model_name: str, version: str, body: ModelPromotionRequest, request: Request, idempotency_key: IdempotencyKey, session: Session = Depends(get_session), principal: Principal = Depends(require_roles("release-manager"))):
    return await _service(request, session, principal).promote_model(model_name, version, body, idempotency_key=idempotency_key)
