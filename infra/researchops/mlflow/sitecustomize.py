"""MLflow 3.14 PostgreSQL model-version compatibility shim.

MLflow's REST contract transports model-version numbers as strings, while the
SQLAlchemy model stores ``model_versions.version`` as an integer. On
PostgreSQL, MLflow 3.14.0 can therefore generate ``INTEGER = VARCHAR`` queries
for registry read/update APIs. SQLite silently coerces the values, which is why
this does not appear in lightweight tests.

This module is loaded automatically through ``PYTHONPATH`` in the pinned
ResearchOps MLflow image. It normalizes numeric version strings to integers at
the SQLAlchemy-store boundary. The shim is intentionally version-gated and can
be deleted once the pinned MLflow release contains the upstream fix.
"""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable

_TARGET_MLFLOW_VERSION = "3.14.0"
_PATCH_MARKER = "_researchops_postgresql_model_version_compat_v1"


def coerce_model_version(value: Any) -> Any:
    """Convert a decimal model-version string to an integer.

    Non-decimal values are left unchanged so MLflow's own validation continues
    to own user-facing error handling.
    """

    if isinstance(value, bool) or isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdecimal():
            return int(stripped)
    return value


def _wrap_version_argument(
    method: Callable[..., Any],
    *,
    position: int,
) -> Callable[..., Any]:
    """Wrap a store method whose ``version`` argument has a known position."""

    @wraps(method)
    def wrapped(self, *args, **kwargs):
        if "version" in kwargs:
            kwargs["version"] = coerce_model_version(kwargs["version"])
        elif len(args) > position:
            mutable = list(args)
            mutable[position] = coerce_model_version(mutable[position])
            args = tuple(mutable)
        return method(self, *args, **kwargs)

    return wrapped


def install_mlflow_postgresql_compat() -> bool:
    """Install the compatibility shim and return whether it is active."""

    try:
        import mlflow
        from mlflow.store.model_registry.sqlalchemy_store import SqlAlchemyStore
    except ImportError:
        return False

    if str(getattr(mlflow, "__version__", "")) != _TARGET_MLFLOW_VERSION:
        return False
    if getattr(SqlAlchemyStore, _PATCH_MARKER, False):
        return True

    # Positions are indexed in ``args`` after ``self``.
    methods = {
        "_get_sql_model_version": 2,  # session, name, version, eager
        "_get_sql_model_version_including_deleted": 1,  # name, version
        "_get_model_version_tag": 2,  # session, name, version, key
        "get_model_version": 1,  # name, version
        "get_model_version_download_uri": 1,
        "update_model_version": 1,
        "transition_model_version_stage": 1,
        "delete_model_version": 1,
        "set_model_version_tag": 1,
        "delete_model_version_tag": 1,
        "set_registered_model_alias": 2,  # name, alias, version
    }

    for method_name, position in methods.items():
        original = getattr(SqlAlchemyStore, method_name, None)
        if original is None:
            continue
        setattr(
            SqlAlchemyStore,
            method_name,
            _wrap_version_argument(original, position=position),
        )

    setattr(SqlAlchemyStore, _PATCH_MARKER, True)
    return True


COMPATIBILITY_ACTIVE = install_mlflow_postgresql_compat()
