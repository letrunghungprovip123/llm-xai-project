from __future__ import annotations

import re
from contextvars import ContextVar

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from research.python.researchops.artifacts.ids import new_ulid

_REQUEST_ID = ContextVar[str | None]("researchops_request_id", default=None)
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def current_request_id() -> str | None:
    return _REQUEST_ID.get()


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        supplied = request.headers.get("X-Request-ID")
        request_id = supplied if supplied and _REQUEST_ID_RE.fullmatch(supplied) else f"req_{new_ulid()}"
        token = _REQUEST_ID.set(request_id)
        request.state.request_id = request_id
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            _REQUEST_ID.reset(token)
