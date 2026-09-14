from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ..contracts.common import CursorPage
from ..contracts.resources import GateEvaluationView, GateSummary
from ..dependencies import get_read_repository
from ..queries import SqlAlchemyOpsReadRepository
from ..security import require_roles
from ._helpers import read_service

router = APIRouter(tags=["quality-gates"], dependencies=[Depends(require_roles("viewer"))])


@router.get("/api/v1/gates", response_model=CursorPage[GateSummary], operation_id="list_gates")
def list_gates(
    request: Request, repository: SqlAlchemyOpsReadRepository = Depends(get_read_repository),
    limit: int = Query(default=50, ge=1, le=200), cursor: str | None = None,
    gate_id: str | None = None, scope_type: str | None = None, scope_id: str | None = None,
    effective_status: str | None = None, blocking: bool | None = None,
):
    return read_service(request, repository).search_gates(
        limit=limit, cursor=cursor, gate_id=gate_id, scope_type=scope_type,
        scope_id=scope_id, effective_status=effective_status, blocking=blocking,
    )


@router.get("/api/v1/gates/{gate_result_id}", response_model=GateSummary, operation_id="get_gate")
def get_gate(gate_result_id: str, request: Request, repository: SqlAlchemyOpsReadRepository = Depends(get_read_repository)):
    return read_service(request, repository).get_gate(gate_result_id)


@router.get("/api/v1/gates/{gate_result_id}/history", response_model=list[GateEvaluationView], operation_id="get_gate_history")
def history(gate_result_id: str, request: Request, repository: SqlAlchemyOpsReadRepository = Depends(get_read_repository)):
    return read_service(request, repository).gate_history(gate_result_id)


@router.get("/api/v1/gate-evaluations/{evaluation_id}", response_model=GateEvaluationView, operation_id="get_gate_evaluation")
def evaluation(evaluation_id: str, request: Request, repository: SqlAlchemyOpsReadRepository = Depends(get_read_repository)):
    return read_service(request, repository).get_evaluation(evaluation_id)


@router.get("/api/v1/scopes/{scope_type}/{scope_id}/gates", response_model=list[GateSummary], operation_id="list_scope_gates")
def scope_gates(scope_type: str, scope_id: str, request: Request, repository: SqlAlchemyOpsReadRepository = Depends(get_read_repository)):
    return read_service(request, repository).scope_gates(scope_type, scope_id)
