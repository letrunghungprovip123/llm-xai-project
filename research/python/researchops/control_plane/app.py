from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder

from .composition import ControlPlaneComposition, build_default_composition
from .contracts.common import ErrorBody, ErrorResponse
from .errors import ControlPlaneError
from .middleware import RequestContextMiddleware, SecurityHeadersMiddleware
from .routers import approvals, artifacts, gates, models, mutations, operations, releases, runs, system
from .settings import ControlPlaneSettings, load_control_plane_settings


def _error_payload(request: Request, *, code: str, message: str, details: dict | None = None) -> dict:
    return ErrorResponse(
        error=ErrorBody(
            code=code,
            message=message,
            request_id=getattr(request.state, "request_id", "unknown"),
            details=details or {},
        )
    ).model_dump(mode="json")


def create_app(
    *,
    settings: ControlPlaneSettings | None = None,
    composition: ControlPlaneComposition | None = None,
) -> FastAPI:
    resolved_settings = settings or load_control_plane_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if getattr(app.state, "composition", None) is None:
            app.state.composition = build_default_composition()
        yield

    app = FastAPI(
        title="LLM-XAI ResearchOps Control Plane",
        version=resolved_settings.api_version,
        description=(
            "Canonical HTTP control plane for ResearchOps runs, immutable artifacts, "
            "quality gates, releases, approvals, MLflow and Prefect."
        ),
        lifespan=lifespan,
        docs_url="/docs" if resolved_settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if resolved_settings.docs_enabled else None,
    )
    app.state.settings = resolved_settings
    app.state.composition = composition
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestContextMiddleware)

    @app.exception_handler(ControlPlaneError)
    async def control_plane_error(request: Request, exc: ControlPlaneError):
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(request, code=exc.code, message=exc.message, details=exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content=_error_payload(
                request,
                code="CONTRACT_VALIDATION_FAILED",
                message="Request validation failed",
                details={"errors": jsonable_encoder(exc.errors(), custom_encoder={Exception: str})},
            ),
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        code = {
            401: "AUTHENTICATION_REQUIRED",
            403: "PERMISSION_DENIED",
            404: "RESOURCE_NOT_FOUND",
            409: "STATE_CONFLICT",
            412: "PRECONDITION_FAILED",
            422: "CONTRACT_VALIDATION_FAILED",
        }.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(request, code=code, message=str(exc.detail)),
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content=_error_payload(
                request,
                code="INTERNAL_ERROR",
                message="Unexpected internal error",
                details={"type": type(exc).__name__},
            ),
        )

    for router in (
        system.router,
        runs.router,
        artifacts.router,
        gates.router,
        approvals.router,
        releases.router,
        models.router,
        operations.router,
        mutations.router,
    ):
        app.include_router(router)
    return app


app = create_app()
