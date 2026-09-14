from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ControlPlaneSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RESEARCHOPS_API_",
        extra="ignore",
        case_sensitive=False,
    )

    service_name: str = "researchops-control-plane"
    api_version: str = "v1"
    environment: str = "local"
    auth_mode: Literal["local", "jwt"] = "local"
    local_subject: str = "local-developer"
    local_roles: str = "viewer,operator,reviewer,approver,release-manager,admin"
    cursor_secret: str = "researchops-local-cursor-secret-change-me"
    cursor_ttl_seconds: int = Field(default=86400, ge=60, le=604800)
    default_page_size: int = Field(default=50, ge=1, le=200)
    max_page_size: int = Field(default=200, ge=1, le=500)
    lineage_max_depth: int = Field(default=8, ge=1, le=32)
    lineage_max_nodes: int = Field(default=1000, ge=10, le=10000)
    dependency_timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    critical_dependency_timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    docs_enabled: bool = True
    jwt_issuer: str | None = None
    jwt_audience: str | None = None
    jwt_jwks_url: str | None = None
    jwt_roles_claim: str = "roles"
    jwt_subject_claim: str = "sub"

    @field_validator("local_roles")
    @classmethod
    def validate_local_roles(cls, value: str) -> str:
        from .security.roles import ALL_ROLES

        roles = [item.strip() for item in value.split(",") if item.strip()]
        if not roles:
            raise ValueError("local_roles must contain at least one role")
        unknown = set(roles) - ALL_ROLES
        if unknown:
            raise ValueError(f"Unknown local roles: {sorted(unknown)}")
        return value

    @model_validator(mode="after")
    def validate_auth(self) -> "ControlPlaneSettings":
        if self.max_page_size < self.default_page_size:
            raise ValueError("max_page_size cannot be smaller than default_page_size")
        if self.environment.lower() not in {"local", "test"} and self.auth_mode == "local":
            raise ValueError("Non-local environments require jwt authentication")
        if self.auth_mode == "jwt":
            missing = [
                name
                for name, value in (
                    ("jwt_issuer", self.jwt_issuer),
                    ("jwt_audience", self.jwt_audience),
                    ("jwt_jwks_url", self.jwt_jwks_url),
                )
                if not value
            ]
            if missing:
                raise ValueError(f"JWT auth requires: {', '.join(missing)}")
            if len(self.cursor_secret) < 32:
                raise ValueError("JWT/shared mode requires a cursor_secret of at least 32 characters")
        return self

    @property
    def local_role_set(self) -> frozenset[str]:
        return frozenset(item.strip() for item in self.local_roles.split(",") if item.strip())


@lru_cache(maxsize=1)
def load_control_plane_settings() -> ControlPlaneSettings:
    return ControlPlaneSettings()
