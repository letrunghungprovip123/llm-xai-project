from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..contracts.resources import ModelVersionView
from ..security import require_roles
from ._helpers import system_service

router = APIRouter(prefix="/api/v1/models", tags=["models"], dependencies=[Depends(require_roles("viewer"))])


@router.get("/{model_name}/versions", response_model=list[ModelVersionView], operation_id="list_model_versions")
def versions(model_name: str, request: Request):
    return system_service(request).model_versions(model_name)


@router.get("/{model_name}/versions/{version}", response_model=ModelVersionView, operation_id="get_model_version")
def version(model_name: str, version: str, request: Request):
    matches = [item for item in system_service(request).model_versions(model_name) if item.version == version]
    if not matches:
        from ..errors import ResourceNotFoundError
        raise ResourceNotFoundError("model version", f"{model_name}:{version}")
    return matches[0]
