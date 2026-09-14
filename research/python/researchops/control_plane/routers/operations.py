from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from ..commands import ControlCommandService
from ..contracts.common import CursorPage
from ..contracts.mutations import OperationView
from ..dependencies import get_composition, get_read_repository, get_session
from ..queries import SqlAlchemyOpsReadRepository
from ..security import Principal, require_roles
from ._helpers import read_service

router = APIRouter(
    prefix="/api/v1/operations",
    tags=["operations"],
    dependencies=[Depends(require_roles("viewer"))],
)


def _command_service(
    request: Request, session: Session, principal: Principal
) -> ControlCommandService:
    return ControlCommandService(
        session=session,
        composition=get_composition(request),
        principal=principal,
        request_id=request.state.request_id,
    )


@router.get(
    "",
    response_model=CursorPage[OperationView],
    operation_id="list_control_operations",
)
def list_operations(
    request: Request,
    repository: SqlAlchemyOpsReadRepository = Depends(get_read_repository),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = None,
    status: str | None = None,
    requested_by: str | None = None,
    operation_type: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
):
    return read_service(request, repository).search_operations(
        limit=limit,
        cursor=cursor,
        status=status,
        requested_by=requested_by,
        operation_type=operation_type,
        target_type=target_type,
        target_id=target_id,
    )


@router.get(
    "/{operation_id}",
    response_model=OperationView,
    operation_id="get_control_operation",
)
def get_operation(
    operation_id: str,
    request: Request,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_roles("viewer")),
):
    return _command_service(request, session, principal).operation(operation_id)
