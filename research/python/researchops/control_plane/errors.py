from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ControlPlaneError(Exception):
    code: str
    message: str
    status_code: int
    details: dict[str, Any] | None = None


class InvalidCursorError(ControlPlaneError):
    def __init__(self, message: str = "Invalid or expired cursor") -> None:
        super().__init__("INVALID_CURSOR", message, 400)


class ResourceNotFoundError(ControlPlaneError):
    def __init__(self, resource: str, resource_id: str) -> None:
        super().__init__(
            "RESOURCE_NOT_FOUND",
            f"{resource} does not exist",
            404,
            {"resource": resource, "resource_id": resource_id},
        )


class DependencyUnavailableError(ControlPlaneError):
    def __init__(self, dependency: str, message: str | None = None) -> None:
        super().__init__(
            "DEPENDENCY_UNAVAILABLE",
            message or f"Dependency is unavailable: {dependency}",
            503,
            {"dependency": dependency},
        )


class StateConflictError(ControlPlaneError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__("STATE_CONFLICT", message, 409, details)


class PreconditionFailedError(ControlPlaneError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__("PRECONDITION_FAILED", message, 412, details)
