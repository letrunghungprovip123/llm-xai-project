from __future__ import annotations

import re

from .exceptions import MLflowIntegrityError


_CANONICAL_LOGGED_MODEL_URI = re.compile(r"^models:/m-[A-Za-z0-9_-]+$")
_HISTORICAL_RUN_URI = re.compile(r"^runs:/[^/]+/.+$")


def is_canonical_logged_model_uri(value: str) -> bool:
    return _CANONICAL_LOGGED_MODEL_URI.fullmatch(value) is not None


def require_canonical_logged_model_uri(value: str) -> str:
    if not is_canonical_logged_model_uri(value):
        raise MLflowIntegrityError(
            "New MLflow model identities must use the MLflow 3 logged-model "
            f"URI contract models:/m-...; observed {value!r}"
        )
    return value


def is_historical_run_model_uri(value: str) -> bool:
    return _HISTORICAL_RUN_URI.fullmatch(value) is not None


def receipt_model_uri_is_supported(value: str) -> bool:
    """Historical receipts remain readable, but new runs must be canonical."""

    return is_canonical_logged_model_uri(value) or is_historical_run_model_uri(value)
