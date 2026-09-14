from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..settings import ControlPlaneSettings
from .principal import Principal
from .roles import ALL_ROLES

_bearer = HTTPBearer(auto_error=False)


class AuthenticationError(ValueError):
    pass


class JWTAuthenticator:
    def __init__(self, settings: ControlPlaneSettings) -> None:
        self.settings = settings
        self._client: Any | None = None

    def authenticate(self, token: str) -> Principal:
        import jwt

        if self._client is None:
            self._client = jwt.PyJWKClient(str(self.settings.jwt_jwks_url))
        signing_key = self._client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience=self.settings.jwt_audience,
            issuer=self.settings.jwt_issuer,
            options={"require": [self.settings.jwt_subject_claim]},
        )
        subject = str(payload[self.settings.jwt_subject_claim])
        raw_roles = payload.get(self.settings.jwt_roles_claim, [])
        if isinstance(raw_roles, str):
            roles = frozenset(item.strip() for item in raw_roles.split(",") if item.strip())
        elif isinstance(raw_roles, list):
            roles = frozenset(str(item) for item in raw_roles)
        else:
            raise AuthenticationError("JWT roles claim must be a string or array")
        roles = frozenset(item for item in roles if item in ALL_ROLES)
        return Principal(
            subject=subject,
            roles=roles,
            display_name=str(payload.get("name")) if payload.get("name") else None,
            authentication_method="jwt",
        )


def principal_for_request(request: Request, credentials: HTTPAuthorizationCredentials | None) -> Principal:
    settings: ControlPlaneSettings = request.app.state.settings
    if settings.auth_mode == "local":
        return Principal.local(subject=settings.local_subject, roles=settings.local_role_set)
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    try:
        return JWTAuthenticator(settings).authenticate(credentials.credentials)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token") from exc


async def get_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Principal:
    return principal_for_request(request, credentials)


def require_roles(*roles: str):
    required = frozenset(roles)

    async def dependency(principal: Principal = Depends(get_principal)) -> Principal:
        if not principal.has_any_role(required):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return principal

    return dependency
