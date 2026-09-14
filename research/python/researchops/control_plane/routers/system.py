from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..contracts.resources import CapabilityResponse, HealthResponse, ReadinessResponse, RegistryItem, VersionResponse
from ..security import require_roles
from ._helpers import system_service

router = APIRouter(tags=["system"])


@router.get("/healthz", response_model=HealthResponse, operation_id="health")
def health(request: Request) -> HealthResponse:
    return system_service(request).health()


@router.get("/readyz", response_model=ReadinessResponse, operation_id="readiness")
async def readiness(request: Request) -> ReadinessResponse:
    return await system_service(request).readiness()


@router.get("/version", response_model=VersionResponse, operation_id="version")
def version(request: Request) -> VersionResponse:
    return system_service(request).version()


@router.get("/api/v1/capabilities", response_model=CapabilityResponse, operation_id="get_capabilities")
def capabilities(request: Request, _=Depends(require_roles("viewer"))) -> CapabilityResponse:
    return system_service(request).capabilities()


@router.get("/api/v1/stages", response_model=list[RegistryItem], operation_id="list_stages")
def stages(request: Request, _=Depends(require_roles("viewer"))) -> list[RegistryItem]:
    return system_service(request).stages()


@router.get("/api/v1/flows", response_model=list[RegistryItem], operation_id="list_flows")
def flows(request: Request, _=Depends(require_roles("viewer"))) -> list[RegistryItem]:
    return system_service(request).flows()


@router.get("/api/v1/deployments", response_model=list[RegistryItem], operation_id="list_deployments")
def deployments(request: Request, _=Depends(require_roles("viewer"))) -> list[RegistryItem]:
    return system_service(request).deployments()
