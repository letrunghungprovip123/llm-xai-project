from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from research.python.researchops.artifacts.ids import new_ulid
from research.python.researchops.ops_core.db.models import ApiIdempotencyRequest

from ..errors import StateConflictError


def canonical_request_sha256(payload: Any) -> str:
    return hashlib.sha256(
        (json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class IdempotencyReservation:
    record: ApiIdempotencyRequest
    replayed: bool


class ApiIdempotencyService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _find(
        self,
        *,
        principal_subject: str,
        http_method: str,
        route_template: str,
        idempotency_key: str,
    ) -> ApiIdempotencyRequest | None:
        return self.session.scalar(
            select(ApiIdempotencyRequest).where(
                ApiIdempotencyRequest.principal_subject == principal_subject,
                ApiIdempotencyRequest.http_method == http_method,
                ApiIdempotencyRequest.route_template == route_template,
                ApiIdempotencyRequest.idempotency_key == idempotency_key,
            )
        )

    @staticmethod
    def _validate_replay(
        existing: ApiIdempotencyRequest,
        *,
        digest: str,
        allow_processing_replay: bool,
    ) -> IdempotencyReservation:
        if existing.request_sha256 != digest:
            raise StateConflictError(
                "Idempotency key was reused with a different request",
                {"idempotency_request_id": existing.id},
            )
        if existing.status == "PROCESSING" and not allow_processing_replay:
            raise StateConflictError(
                "Equivalent request is still processing",
                {"idempotency_request_id": existing.id},
            )
        return IdempotencyReservation(existing, True)

    def lookup(
        self,
        *,
        principal_subject: str,
        http_method: str,
        route_template: str,
        idempotency_key: str,
        request_payload: Any,
        allow_processing_replay: bool = False,
    ) -> IdempotencyReservation | None:
        existing = self._find(
            principal_subject=principal_subject,
            http_method=http_method,
            route_template=route_template,
            idempotency_key=idempotency_key,
        )
        if existing is None:
            return None
        return self._validate_replay(
            existing,
            digest=canonical_request_sha256(request_payload),
            allow_processing_replay=allow_processing_replay,
        )

    def reserve(
        self,
        *,
        principal_subject: str,
        http_method: str,
        route_template: str,
        idempotency_key: str,
        request_payload: Any,
        allow_processing_replay: bool = False,
    ) -> IdempotencyReservation:
        digest = canonical_request_sha256(request_payload)
        existing = self._find(
            principal_subject=principal_subject,
            http_method=http_method,
            route_template=route_template,
            idempotency_key=idempotency_key,
        )
        if existing is not None:
            return self._validate_replay(
                existing,
                digest=digest,
                allow_processing_replay=allow_processing_replay,
            )

        record = ApiIdempotencyRequest(
            id=f"api_request_{new_ulid()}",
            principal_subject=principal_subject,
            http_method=http_method,
            route_template=route_template,
            idempotency_key=idempotency_key,
            request_sha256=digest,
            status="PROCESSING",
            response_body={},
            created_at=datetime.now(timezone.utc),
        )
        # Query-then-insert alone is racy under concurrent requests. Isolate the
        # insert in a savepoint; if the unique key wins elsewhere, roll back only
        # the savepoint and deterministically replay the winning row.
        try:
            with self.session.begin_nested():
                self.session.add(record)
                self.session.flush()
        except IntegrityError:
            existing = self._find(
                principal_subject=principal_subject,
                http_method=http_method,
                route_template=route_template,
                idempotency_key=idempotency_key,
            )
            if existing is None:
                raise
            return self._validate_replay(
                existing,
                digest=digest,
                allow_processing_replay=allow_processing_replay,
            )
        return IdempotencyReservation(record, False)

    def complete(
        self,
        record: ApiIdempotencyRequest,
        *,
        response_status: int,
        response_body: dict[str, Any],
        resource_type: str,
        resource_id: str,
    ) -> None:
        record.status = "COMPLETED"
        record.response_status = response_status
        record.response_body = response_body
        record.resource_type = resource_type
        record.resource_id = resource_id
        record.completed_at = datetime.now(timezone.utc)
        self.session.flush()

    def fail(self, record: ApiIdempotencyRequest, *, code: str, response_body: dict[str, Any], response_status: int) -> None:
        record.status = "FAILED"
        record.error_code = code
        record.response_body = response_body
        record.response_status = response_status
        record.completed_at = datetime.now(timezone.utc)
        self.session.flush()
