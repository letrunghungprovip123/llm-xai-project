from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session

from .composition import ControlPlaneComposition
from .queries.repository import SqlAlchemyOpsReadRepository


def get_composition(request: Request) -> ControlPlaneComposition:
    composition = getattr(request.app.state, "composition", None)
    if composition is None:
        raise RuntimeError("Control plane composition is not initialized")
    return composition


def get_session(request: Request) -> Iterator[Session]:
    composition = get_composition(request)
    with composition.session_factory() as session:
        yield session


def get_read_repository(request: Request) -> Iterator[SqlAlchemyOpsReadRepository]:
    composition = get_composition(request)
    with composition.session_factory() as session:
        yield SqlAlchemyOpsReadRepository(session)
