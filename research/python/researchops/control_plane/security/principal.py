from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .roles import ALL_ROLES


class Principal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: str = Field(min_length=1, max_length=255)
    roles: frozenset[str]
    display_name: str | None = None
    authentication_method: str = Field(min_length=1)

    def has_any_role(self, required: set[str] | frozenset[str]) -> bool:
        return bool(self.roles.intersection(required)) or "admin" in self.roles

    @classmethod
    def local(cls, *, subject: str, roles: frozenset[str]) -> "Principal":
        unknown = set(roles) - ALL_ROLES
        if unknown:
            raise ValueError(f"Unknown local roles: {sorted(unknown)}")
        return cls(
            subject=subject,
            roles=roles,
            display_name="Local developer",
            authentication_method="local",
        )
