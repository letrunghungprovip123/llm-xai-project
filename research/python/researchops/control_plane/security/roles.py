from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    REVIEWER = "reviewer"
    APPROVER = "approver"
    RELEASE_MANAGER = "release-manager"
    ADMIN = "admin"


ALL_ROLES = frozenset(item.value for item in Role)
