from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SHA256_RE = r"^[0-9a-f]{64}$"
ID_RE = r"^[A-Za-z0-9_.:-]+$"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GateScope(StrictModel):
    type: Literal["pipeline_run", "stage_run", "artifact", "release", "model_version"]
    id: str = Field(min_length=1, max_length=160, pattern=ID_RE)


class GateAdapterIdentity(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    version: int = Field(ge=1)


class GatePolicyIdentity(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$")
    version: str = Field(min_length=1, max_length=64)


class GateSource(StrictModel):
    artifact_id: str | None = Field(default=None, min_length=1, max_length=160)
    manifest_sha256: str | None = Field(default=None, pattern=SHA256_RE)
    contract: str = Field(pattern=r"^[a-z][a-z0-9_]*$")

    @model_validator(mode="after")
    def artifact_identity_is_complete(self) -> "GateSource":
        if bool(self.artifact_id) != bool(self.manifest_sha256):
            raise ValueError("artifact_id and manifest_sha256 must be provided together")
        return self


class GateEvidence(StrictModel):
    artifact_id: str
    manifest_sha256: str = Field(pattern=SHA256_RE)


class GateCheck(StrictModel):
    check_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$")
    passed: bool
    expected: Any = None
    observed: Any = None
    severity: Literal["INFO", "WARNING", "ERROR"] = "ERROR"
    message: str | None = None


class GateEvaluationDraft(StrictModel):
    schema_version: Literal["gate_evaluation_v1"] = "gate_evaluation_v1"
    gate_id: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    scope: GateScope
    outcome: Literal["PASSED", "FAILED"]
    blocking: bool = True
    severity: Literal["INFO", "WARNING", "ERROR"] = "ERROR"
    adapter: GateAdapterIdentity
    policy: GatePolicyIdentity
    source: GateSource
    evidence: GateEvidence | None = None
    expected: dict[str, Any] = Field(default_factory=dict)
    observed: dict[str, Any] = Field(default_factory=dict)
    checks: tuple[GateCheck, ...] = ()
    limitations: tuple[str, ...] = ()
    source_contracts: tuple[str, ...] = ()
    source_evaluation_ids: tuple[str, ...] = ()
    origin_pipeline_run_id: str | None = None
    origin_stage_run_id: str | None = None
    evaluated_at: datetime

    @field_validator("limitations")
    @classmethod
    def non_blank_limitations(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.strip() for item in values):
            raise ValueError("limitations must not contain blank entries")
        return values

    @model_validator(mode="after")
    def checks_match_outcome(self) -> "GateEvaluationDraft":
        if self.checks:
            all_passed = all(item.passed for item in self.checks)
            if all_passed != (self.outcome == "PASSED"):
                raise ValueError("outcome must agree with the normalized check results")
        return self

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "gate_id": self.gate_id,
            "scope": self.scope.model_dump(mode="json"),
            "adapter": self.adapter.model_dump(mode="json"),
            "policy": self.policy.model_dump(mode="json"),
            "source": self.source.model_dump(mode="json"),
            "evidence": self.evidence.model_dump(mode="json") if self.evidence else None,
            "source_evaluation_ids": sorted(self.source_evaluation_ids),
        }

    def payload_for_hash(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        # evaluated_at is evidence metadata, not evaluation identity or semantic payload.
        payload.pop("evaluated_at", None)
        return payload


class GateEvaluationView(StrictModel):
    id: str
    evaluation_key: str = Field(pattern=SHA256_RE)
    payload_sha256: str = Field(pattern=SHA256_RE)
    draft: GateEvaluationDraft
    created_at: datetime


class GateResultView(StrictModel):
    id: str
    gate_id: str
    scope: GateScope
    current_evaluation_id: str | None
    evaluation_outcome: Literal["PASSED", "FAILED"] | None
    effective_status: Literal["PENDING", "PASSED", "FAILED", "WAIVED"]
    blocking: bool
    severity: str
    updated_at: datetime
