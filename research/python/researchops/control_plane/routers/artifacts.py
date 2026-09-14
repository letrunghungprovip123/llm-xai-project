from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request

from ..contracts.common import CursorPage
from ..contracts.resources import ArtifactDetail, ArtifactFileView, ArtifactSummary, GateSummary, LineageGraph, ReleaseArtifactView
from ..dependencies import get_read_repository
from ..queries import SqlAlchemyOpsReadRepository
from ..security import require_roles
from ._helpers import read_service

router = APIRouter(prefix="/api/v1/artifacts", tags=["artifacts"], dependencies=[Depends(require_roles("viewer"))])


@router.get("", response_model=CursorPage[ArtifactSummary], operation_id="list_artifacts")
def list_artifacts(
    request: Request, repository: SqlAlchemyOpsReadRepository = Depends(get_read_repository),
    limit: int = Query(default=50, ge=1, le=200), cursor: str | None = None,
    artifact_type: str | None = None, schema_version: str | None = None,
    status: str | None = None, producer_stage_run_id: str | None = None,
    source_commit: str | None = None, created_after: datetime | None = None,
    created_before: datetime | None = None,
):
    return read_service(request, repository).search_artifacts(
        limit=limit, cursor=cursor, artifact_type=artifact_type,
        schema_version=schema_version, status=status,
        producer_stage_run_id=producer_stage_run_id, source_commit=source_commit,
        created_after=created_after, created_before=created_before,
    )


@router.get("/{artifact_id}", response_model=ArtifactDetail, operation_id="get_artifact")
def get_artifact(artifact_id: str, request: Request, repository: SqlAlchemyOpsReadRepository = Depends(get_read_repository)):
    return read_service(request, repository).get_artifact(artifact_id)


@router.get("/{artifact_id}/files", response_model=list[ArtifactFileView], operation_id="list_artifact_files")
def files(artifact_id: str, request: Request, repository: SqlAlchemyOpsReadRepository = Depends(get_read_repository)):
    return read_service(request, repository).artifact_files(artifact_id)


@router.get("/{artifact_id}/lineage", response_model=LineageGraph, operation_id="get_artifact_lineage")
def lineage(
    artifact_id: str, request: Request,
    repository: SqlAlchemyOpsReadRepository = Depends(get_read_repository),
    direction: Literal["ancestors", "descendants", "both"] = "both",
    depth: int = Query(default=3, ge=1, le=32),
):
    settings = request.app.state.settings
    return read_service(request, repository).artifact_lineage(
        artifact_id, direction=direction, depth=min(depth, settings.lineage_max_depth),
        max_nodes=settings.lineage_max_nodes,
    )


@router.get("/{artifact_id}/gates", response_model=list[GateSummary], operation_id="list_artifact_gates")
def gates(artifact_id: str, request: Request, repository: SqlAlchemyOpsReadRepository = Depends(get_read_repository)):
    service = read_service(request, repository)
    service.get_artifact(artifact_id)
    return service.scope_gates("artifact", artifact_id)


@router.get("/{artifact_id}/releases", response_model=list[ReleaseArtifactView], operation_id="list_artifact_releases")
def releases(artifact_id: str, request: Request, repository: SqlAlchemyOpsReadRepository = Depends(get_read_repository)):
    service = read_service(request, repository)
    service.get_artifact(artifact_id)
    return [
        ReleaseArtifactView(
            release_id=item.release_id, artifact_id=item.artifact_id,
            role=item.role, created_at=item.created_at,
        )
        for item in repository.artifact_release_memberships(artifact_id)
    ]
