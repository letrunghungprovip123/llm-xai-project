from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PageInfo(StrictModel):
    limit: int = Field(ge=1)
    has_more: bool
    next_cursor: str | None = None


T = TypeVar("T")


class CursorPage(StrictModel, Generic[T]):
    items: list[T]
    page: PageInfo


class ErrorBody(StrictModel):
    code: str
    message: str
    request_id: str
    details: dict = Field(default_factory=dict)


class ErrorResponse(StrictModel):
    error: ErrorBody


class TimestampRange(StrictModel):
    created_after: datetime | None = None
    created_before: datetime | None = None
