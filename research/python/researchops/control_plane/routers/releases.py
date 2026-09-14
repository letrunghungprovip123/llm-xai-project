from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ..contracts.common import CursorPage
from ..contracts.resources import GateSummary, PromotionDecisionView, ReleaseArtifactView, ReleaseDetail, ReleaseSummary
from ..dependencies import get_read_repository
from ..queries import SqlAlchemyOpsReadRepository
from ..security import require_roles
from ._helpers import read_service

router = APIRouter(prefix="/api/v1/releases", tags=["releases"], dependencies=[Depends(require_roles("viewer"))])


@router.get("", response_model=CursorPage[ReleaseSummary], operation_id="list_releases")
def list_releases(
    request: Request, repository: SqlAlchemyOpsReadRepository = Depends(get_read_repository),
    limit: int = Query(default=50, ge=1, le=200), cursor: str | None = None,
    release_type: str | None = None, status: str | None = None,
    source_commit: str | None = None,
):
    return read_service(request, repository).search_releases(
        limit=limit, cursor=cursor, release_type=release_type,
        status=status, source_commit=source_commit,
    )


@router.get("/{release_id}", response_model=ReleaseDetail, operation_id="get_release")
def get_release(release_id: str, request: Request, repository: SqlAlchemyOpsReadRepository = Depends(get_read_repository)):
    return read_service(request, repository).get_release(release_id)


@router.get("/{release_id}/artifacts", response_model=list[ReleaseArtifactView], operation_id="list_release_artifacts")
def artifacts(release_id: str, request: Request, repository: SqlAlchemyOpsReadRepository = Depends(get_read_repository)):
    return read_service(request, repository).release_artifacts(release_id)


@router.get("/{release_id}/gates", response_model=list[GateSummary], operation_id="list_release_gates")
def gates(release_id: str, request: Request, repository: SqlAlchemyOpsReadRepository = Depends(get_read_repository)):
    service = read_service(request, repository)
    service.get_release(release_id)
    return service.scope_gates("release", release_id)


@router.get("/{release_id}/promotion-decisions", response_model=list[PromotionDecisionView], operation_id="list_release_promotion_decisions")
def decisions(release_id: str, request: Request, repository: SqlAlchemyOpsReadRepository = Depends(get_read_repository)):
    service = read_service(request, repository)
    service.get_release(release_id)
    return service.promotion_decisions("release", release_id)
