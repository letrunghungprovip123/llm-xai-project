from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PrefectFlowRunSnapshot(StrictModel):
    flow_run_id: str
    state_name: str
    deployment_id: str | None = None
    flow_name: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    updated_at: str | None = None


class PrefectTaskRunSnapshot(StrictModel):
    task_run_id: str
    flow_run_id: str
    state_name: str
    task_name: str | None = None
    updated_at: str | None = None


class ReconciliationIssue(StrictModel):
    code: str
    severity: Literal["INFO", "WARNING", "ERROR"]
    message: str
    pipeline_run_id: str | None = None
    stage_run_id: str | None = None
    prefect_flow_run_id: str | None = None
    prefect_task_run_id: str | None = None
    approval_id: str | None = None
    repairable: bool = False
    repaired: bool = False


class ReconciliationReport(StrictModel):
    schema_version: str = "prefect_ops_reconciliation_v1"
    mode: Literal["report-only", "repair-safe"]
    passed: bool
    checked_pipeline_runs: int
    checked_stage_runs: int
    checked_flow_runs: int
    checked_task_runs: int
    issue_count: int
    error_count: int
    warning_count: int
    repaired_count: int
    issues: tuple[ReconciliationIssue, ...] = Field(default_factory=tuple)
