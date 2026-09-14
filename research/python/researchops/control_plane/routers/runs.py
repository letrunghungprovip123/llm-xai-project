from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from ..contracts.common import CursorPage
from ..contracts.resources import RunDetail, RunEventView, RunSummary, StageRunView
from ..dependencies import get_read_repository
from ..queries import SqlAlchemyOpsReadRepository
from ..security import require_roles
from ._helpers import read_service

router = APIRouter(prefix="/api/v1/runs", tags=["runs"], dependencies=[Depends(require_roles("viewer"))])


@router.get("", response_model=CursorPage[RunSummary], operation_id="list_runs")
def list_runs(
    request: Request,
    repository: SqlAlchemyOpsReadRepository = Depends(get_read_repository),
    limit: int = Query(default=50, ge=1, le=200), cursor: str | None = None,
    flow_id: str | None = None, status: str | None = None,
    requested_by: str | None = None, source_commit: str | None = None,
    created_after: datetime | None = None, created_before: datetime | None = None,
):
    return read_service(request, repository).search_runs(
        limit=limit, cursor=cursor, flow_id=flow_id, status=status,
        requested_by=requested_by, source_commit=source_commit,
        created_after=created_after, created_before=created_before,
    )


@router.get("/{run_id}", response_model=RunDetail, operation_id="get_run")
def get_run(run_id: str, request: Request, repository: SqlAlchemyOpsReadRepository = Depends(get_read_repository)):
    return read_service(request, repository).get_run(run_id)


@router.get("/{run_id}/stages", response_model=list[StageRunView], operation_id="list_run_stages")
def stages(run_id: str, request: Request, repository: SqlAlchemyOpsReadRepository = Depends(get_read_repository)):
    return read_service(request, repository).run_stages(run_id)


@router.get("/{run_id}/events", response_model=list[RunEventView], operation_id="list_run_events")
def events(run_id: str, request: Request, repository: SqlAlchemyOpsReadRepository = Depends(get_read_repository)):
    return read_service(request, repository).run_events(run_id)


@router.get("/{run_id}/outputs", response_model=list[dict[str, Any]], operation_id="list_run_outputs")
def outputs(run_id: str, request: Request, repository: SqlAlchemyOpsReadRepository = Depends(get_read_repository)):
    service = read_service(request, repository)
    service.get_run(run_id)
    return [
        {
            "stage_run_id": item.stage_run_id, "output_name": item.output_name,
            "artifact_id": item.artifact_id, "artifact_type": item.artifact_type,
            "manifest_sha256": item.manifest_sha256, "created_at": item.created_at,
        }
        for item in repository.run_outputs(run_id)
    ]


@router.get("/{run_id}/receipt", response_model=dict[str, Any] | None, operation_id="get_run_receipt")
def receipt(run_id: str, request: Request, repository: SqlAlchemyOpsReadRepository = Depends(get_read_repository)):
    service = read_service(request, repository)
    service.get_run(run_id)
    item = repository.run_receipt(run_id)
    if item is None:
        return None
    return {
        "pipeline_run_id": item.pipeline_run_id,
        "artifact_id": item.artifact_id,
        "manifest_sha256": item.manifest_sha256,
        "created_at": item.created_at,
    }
