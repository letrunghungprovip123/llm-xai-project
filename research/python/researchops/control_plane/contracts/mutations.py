from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, field_validator

from .common import StrictModel


class _ReasonedRequest(StrictModel):
    reason: str = Field(min_length=1, max_length=4000)

    @field_validator("reason")
    @classmethod
    def reason_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("reason must not be blank")
        return value


class RunTriggerRequest(_ReasonedRequest):
    flow_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    input_artifact_ids: dict[str, str] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)


class RunCancelRequest(_ReasonedRequest):
    expected_status: Literal["PENDING", "WAITING_APPROVAL", "RUNNING"]


class RunRetryRequest(_ReasonedRequest):
    expected_status: Literal["FAILED", "CANCELLED"]
    input_artifact_ids: dict[str, str] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)


class ApprovalDecisionRequest(_ReasonedRequest):
    expected_status: Literal["REQUESTED"] = "REQUESTED"


class WaiverGrantRequest(_ReasonedRequest):
    evaluation_id: str = Field(min_length=1)
    target_kind: str = Field(min_length=1, max_length=128)
    policy_id: str = Field(min_length=1, max_length=128)
    approval_id: str = Field(min_length=1)
    expires_at: datetime


class WaiverRevokeRequest(_ReasonedRequest):
    pass


class ArtifactActionRequest(_ReasonedRequest):
    expected_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReleasePromotionRequest(_ReasonedRequest):
    expected_status: Literal["DRAFT", "CANDIDATE", "READY_WITH_LIMITATIONS"]
    target_status: Literal["READY_WITH_LIMITATIONS", "CERTIFIED"]
    approval_id: str = Field(min_length=1)
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ModelPromotionRequest(_ReasonedRequest):
    approval_id: str = Field(min_length=1)
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class OperationView(StrictModel):
    id: str
    operation_type: str
    status: str
    requested_by: str
    target_type: str
    target_id: str
    prefect_flow_run_id: str | None = None
    pipeline_run_id: str | None = None
    promotion_decision_id: str | None = None
    request_id: str
    result: dict[str, Any]
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime


class OperationAccepted(StrictModel):
    operation_id: str
    status: str
    target_type: str
    target_id: str
    prefect_flow_run_id: str | None = None
    pipeline_run_id: str | None = None
    replayed: bool = False


class MutationResult(StrictModel):
    resource_type: str
    resource_id: str
    status: str
    replayed: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


def validate_idempotency_key(value: str) -> str:
    value = value.strip()
    if not value or len(value) > 255:
        raise ValueError("Idempotency-Key must contain 1-255 characters")
    return value
