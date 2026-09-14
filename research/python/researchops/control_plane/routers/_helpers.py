from __future__ import annotations

from fastapi import Request

from ..queries import CursorCodec, ReadQueryService, SqlAlchemyOpsReadRepository, SystemQueryService


def read_service(request: Request, repository: SqlAlchemyOpsReadRepository) -> ReadQueryService:
    settings = request.app.state.settings
    return ReadQueryService(
        repository,
        CursorCodec(settings.cursor_secret, ttl_seconds=settings.cursor_ttl_seconds),
    )


def system_service(request: Request) -> SystemQueryService:
    return SystemQueryService(request.app.state.settings, request.app.state.composition)
