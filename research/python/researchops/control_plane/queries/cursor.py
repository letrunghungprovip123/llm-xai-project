from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from research.python.researchops.contracts.io import canonical_json_bytes, canonical_json_sha256

from ..errors import InvalidCursorError


@dataclass(frozen=True)
class CursorPosition:
    created_at: datetime
    id: str


def normalize_utc(value: datetime) -> datetime:
    """Return an aware UTC datetime without interpreting naive DB values as local time.

    PostgreSQL returns timezone-aware values for TIMESTAMPTZ, while SQLite
    commonly returns naive values even for ``DateTime(timezone=True)``. Ops DB
    timestamps are defined as UTC, so a naive value must be *labelled* UTC.
    Calling ``astimezone()`` directly on a naive datetime would instead assume
    the host timezone and shift the cursor boundary (for example by seven hours
    on an Asia/Ho_Chi_Minh workstation).
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class CursorCodec:
    def __init__(self, secret: str, *, ttl_seconds: int) -> None:
        if not secret:
            raise ValueError("cursor secret must not be empty")
        self.secret = secret.encode("utf-8")
        self.ttl_seconds = ttl_seconds

    @staticmethod
    def filters_sha256(filters: dict[str, Any]) -> str:
        return canonical_json_sha256(filters)

    def encode(self, *, resource: str, position: CursorPosition, filters_sha256: str) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "v": 1,
            "resource": resource,
            "created_at": normalize_utc(position.created_at).isoformat(),
            "id": position.id,
            "filters_sha256": filters_sha256,
            "issued_at": now.isoformat(),
        }
        raw = canonical_json_bytes(payload)
        signature = hmac.new(self.secret, raw, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(raw + b"." + signature).rstrip(b"=").decode("ascii")

    def decode(self, token: str, *, resource: str, filters_sha256: str) -> CursorPosition:
        try:
            padded = token + "=" * (-len(token) % 4)
            decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
            # HMAC-SHA256 is exactly 32 bytes. Splitting with rsplit(b".") is
            # unsafe because the binary signature may itself contain 0x2e.
            if len(decoded) < 34 or decoded[-33:-32] != b".":
                raise InvalidCursorError()
            raw, signature = decoded[:-33], decoded[-32:]
            expected = hmac.new(self.secret, raw, hashlib.sha256).digest()
            if not hmac.compare_digest(signature, expected):
                raise InvalidCursorError()
            payload = json.loads(raw.decode("utf-8"))
            if payload.get("v") != 1 or payload.get("resource") != resource:
                raise InvalidCursorError()
            if payload.get("filters_sha256") != filters_sha256:
                raise InvalidCursorError("Cursor does not match the current filters")
            issued_at = datetime.fromisoformat(str(payload["issued_at"]))
            if issued_at.tzinfo is None:
                raise InvalidCursorError()
            if datetime.now(timezone.utc) - issued_at.astimezone(timezone.utc) > timedelta(seconds=self.ttl_seconds):
                raise InvalidCursorError("Cursor has expired")
            created_at = datetime.fromisoformat(str(payload["created_at"]))
            if created_at.tzinfo is None:
                raise InvalidCursorError()
            return CursorPosition(created_at=normalize_utc(created_at), id=str(payload["id"]))
        except InvalidCursorError:
            raise
        except Exception as exc:
            raise InvalidCursorError() from exc
