from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ..contracts.common import CursorPage
from ..contracts.resources import ApprovalView
from ..dependencies import get_read_repository
from ..queries import SqlAlchemyOpsReadRepository
from ..security import require_roles
from ._helpers import read_service

router = APIRouter(prefix="/api/v1/approvals", tags=["approvals"], dependencies=[Depends(require_roles("viewer"))])


@router.get("", response_model=CursorPage[ApprovalView], operation_id="list_approvals")
def list_approvals(
    request: Request, repository: SqlAlchemyOpsReadRepository = Depends(get_read_repository),
    limit: int = Query(default=50, ge=1, le=200), cursor: str | None = None,
    status: str | None = None, policy: str | None = None,
    target_type: str | None = None, target_id: str | None = None,
    pipeline_run_id: str | None = None, requested_by: str | None = None,
):
    return read_service(request, repository).search_approvals(
        limit=limit, cursor=cursor, status=status, policy=policy,
        target_type=target_type, target_id=target_id,
        pipeline_run_id=pipeline_run_id, requested_by=requested_by,
    )


@router.get("/{approval_id}", response_model=ApprovalView, operation_id="get_approval")
def get_approval(approval_id: str, request: Request, repository: SqlAlchemyOpsReadRepository = Depends(get_read_repository)):
    return read_service(request, repository).get_approval(approval_id)
