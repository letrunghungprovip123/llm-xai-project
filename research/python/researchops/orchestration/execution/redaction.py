from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

_SECRET_KEY = re.compile(
    r"(?:password|passwd|secret|token|api[_-]?key|access[_-]?key|private[_-]?key)",
    re.IGNORECASE,
)
_URL_CREDENTIAL = re.compile(r"(?P<scheme>[a-z][a-z0-9+.-]*://)(?P<user>[^:/\s]+):[^@\s]+@", re.IGNORECASE)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")


def redact_text(value: str) -> str:
    value = _URL_CREDENTIAL.sub(r"\g<scheme>\g<user>:***@", value)
    return _BEARER.sub("Bearer ***", value)


def redact_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in value.items():
        if _SECRET_KEY.search(key):
            result[key] = "***"
        elif isinstance(item, Mapping):
            result[key] = redact_mapping(item)
        elif isinstance(item, str):
            result[key] = redact_text(item)
        else:
            result[key] = item
    return result
