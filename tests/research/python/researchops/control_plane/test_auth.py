from __future__ import annotations

from fastapi.testclient import TestClient

from research.python.researchops.control_plane.app import create_app
from research.python.researchops.control_plane.settings import ControlPlaneSettings


def test_jwt_mode_requires_configuration():
    try:
        ControlPlaneSettings(auth_mode="jwt", cursor_secret="x"*64)
    except ValueError as exc:
        assert "JWT auth requires" in str(exc)
    else:
        raise AssertionError("JWT mode accepted missing issuer/audience/JWKS")


def test_local_roles_are_validated():
    try:
        ControlPlaneSettings(local_roles="viewer,unknown")
    except ValueError as exc:
        assert "Unknown local roles" in str(exc)
    else:
        raise AssertionError("Unknown local role was accepted")


def test_nonlocal_environment_rejects_local_auth():
    try:
        ControlPlaneSettings(
            environment="staging",
            auth_mode="local",
            cursor_secret="x" * 64,
        )
    except ValueError as exc:
        assert "require jwt authentication" in str(exc)
    else:
        raise AssertionError("Staging accepted local authentication")
