from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from .common import StrictModel


class DependencyState(StrictModel):
    status: Literal["READY", "DEGRADED", "FAILED", "DISABLED"]
    detail: str | None = None


class HealthResponse(StrictModel):
    status: Literal["ok"] = "ok"
    service: str


class ReadinessResponse(StrictModel):
    ready: bool
    service: str
    dependencies: dict[str, DependencyState]


class VersionResponse(StrictModel):
    service: str
    api_version: str
    git_commit: str
    git_dirty: bool
    alembic_head: str | None
    database_revision: str | None
    stage_registry_sha256: str
    flow_catalog_sha256: str
    gate_catalog_sha256: str
    promotion_policy_sha256: str
    prefect_expected_version: str
    mlflow_expected_version: str


class CapabilityResponse(StrictModel):
    auth_mode: str
    artifact_profile: str
    prefect_enabled: bool
    mlflow_enabled: bool
    mutation_api_enabled: bool


class RegistryItem(StrictModel):
    id: str
    version: int | None = None
    title: str | None = None
    description: str | None = None
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunSummary(StrictModel):
    id: str
    flow_id: str
    status: str
    trigger_type: str
    requested_by: str
    source_commit: str
    created_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None
    updated_at: datetime


class RunDetail(RunSummary):
    registry_sha256: str
    environment_snapshot_id: str
    idempotency_key: str
    parameters: dict[str, Any]
    error_summary: str | None = None
    stage_counts: dict[str, int]
    prefect: dict[str, Any] | None = None


class StageRunView(StrictModel):
    id: str
    pipeline_run_id: str
    stage_id: str
    stage_version: int
    attempt: int
    status: str
    approval_policy: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    exit_code: int | None = None
    error_type: str | None = None
    error_message: str | None = None


class RunEventView(StrictModel):
    id: int
    pipeline_run_id: str
    stage_run_id: str | None = None
    event_type: str
    payload: dict[str, Any]
    occurred_at: datetime


class ArtifactSummary(StrictModel):
    id: str
    artifact_type: str
    schema_version: str
    status: str
    manifest_sha256: str
    producer_stage_run_id: str | None = None
    source_commit: str
    created_at: datetime
    verified_at: datetime | None = None
    certified_at: datetime | None = None
    limitations: list[Any]


class ArtifactDetail(ArtifactSummary):
    environment_snapshot_id: str | None = None
    metadata: dict[str, Any]


class ArtifactFileView(StrictModel):
    id: int
    relative_path: str
    sha256: str
    size_bytes: int
    row_count: int | None = None
    column_count: int | None = None
    media_type: str
    download_available: bool = False


class LineageNode(StrictModel):
    artifact_id: str
    artifact_type: str
    schema_version: str
    status: str
    manifest_sha256: str


class LineageEdgeView(StrictModel):
    parent_artifact_id: str
    child_artifact_id: str
    relationship_type: str


class LineageGraph(StrictModel):
    root_artifact_id: str
    nodes: list[LineageNode]
    edges: list[LineageEdgeView]
    truncated: bool


class GateSummary(StrictModel):
    id: str
    gate_id: str
    scope_type: str
    scope_id: str
    status: str
    evaluation_outcome: str | None = None
    effective_status: str | None = None
    current_evaluation_id: str | None = None
    blocking: bool
    severity: str
    updated_at: datetime
    waiver: dict[str, Any] | None = None


class GateEvaluationView(StrictModel):
    id: str
    evaluation_key: str
    payload_sha256: str
    gate_id: str
    scope_type: str
    scope_id: str
    outcome: str
    blocking: bool
    severity: str
    adapter_id: str
    adapter_version: int
    policy_id: str
    policy_version: str
    source_artifact_id: str | None = None
    source_manifest_sha256: str | None = None
    evidence_artifact_id: str | None = None
    evidence_manifest_sha256: str | None = None
    source_contract: str
    expected: dict[str, Any]
    observed: dict[str, Any]
    checks: list[Any]
    limitations: list[Any]
    source_contracts: list[Any]
    source_evaluation_ids: list[Any]
    evaluated_at: datetime


class ApprovalView(StrictModel):
    id: str
    target_type: str
    target_id: str
    policy: str
    status: str
    requested_by: str
    requested_at: datetime
    decided_by: str | None = None
    decided_at: datetime | None = None
    reason: str | None = None
    expires_at: datetime | None = None
    pipeline_run_id: str | None = None
    node_id: str | None = None
    stage_id: str | None = None
    details: dict[str, Any]


class ReleaseSummary(StrictModel):
    id: str
    release_type: str
    status: str
    manifest_artifact_id: str
    source_commit: str
    parent_release_id: str | None = None
    limitations: list[Any]
    created_at: datetime
    promoted_at: datetime | None = None
    superseded_at: datetime | None = None


class ReleaseDetail(ReleaseSummary):
    metadata: dict[str, Any]
    required_gates: list[str]
    observed_gates: list[str]
    missing_gates: list[str]
    policy_id: str | None = None
    policy_sha256: str | None = None


class ReleaseArtifactView(StrictModel):
    release_id: str
    artifact_id: str
    role: str
    created_at: datetime


class PromotionDecisionView(StrictModel):
    id: str
    target_type: str
    target_id: str
    target_kind: str
    policy_id: str
    policy_version: int
    policy_sha256: str
    expected_state: str
    target_state: str
    decision: str
    execution_status: str
    requested_by: str
    executed_by: str | None = None
    approval_id: str | None = None
    reason: str
    created_at: datetime
    executed_at: datetime | None = None


class ModelVersionView(StrictModel):
    model_name: str
    version: str
    aliases: list[str]
    status: str | None = None
    source: str | None = None
    run_id: str | None = None
    tags: dict[str, Any] = Field(default_factory=dict)
    registration_receipt_artifact_id: str | None = None
    gates: list[GateSummary] = Field(default_factory=list)
