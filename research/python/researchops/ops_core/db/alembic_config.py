from __future__ import annotations

import os

from alembic.config import Config

_DATABASE_URL_ATTRIBUTE = "database_url"
_DATABASE_URL_ENVIRONMENT_VARIABLE = "RESEARCHOPS_DATABASE_URL"


def set_explicit_database_url(config: Config, url: str) -> None:
    """Attach an explicit per-invocation database URL to an Alembic config.

    Programmatic callers such as tests must be able to target a disposable
    database even when RESEARCHOPS_DATABASE_URL points at the operational DB.
    """

    if not url:
        raise ValueError("Alembic database URL must not be empty")
    config.attributes[_DATABASE_URL_ATTRIBUTE] = url
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))


def resolve_database_url(config: Config) -> str:
    """Resolve URL precedence: explicit invocation, environment, then ini."""

    explicit = config.attributes.get(_DATABASE_URL_ATTRIBUTE)
    if explicit:
        return str(explicit)

    environment = os.getenv(_DATABASE_URL_ENVIRONMENT_VARIABLE)
    if environment:
        return environment

    configured = config.get_main_option("sqlalchemy.url")
    if not configured:
        raise RuntimeError("Alembic database URL is not configured")
    return configured


def apply_resolved_database_url(config: Config) -> str:
    """Resolve and install the effective URL into Alembic's main options."""

    url = resolve_database_url(config)
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return url
