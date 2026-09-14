from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MaterializedInput(StrictModel):
    name: str
    contract: str
    artifact_id: str
    manifest_sha256: str
    directory: Path


class DiscoveredOutput(StrictModel):
    name: str
    contract: str
    artifact_id: str
    manifest_sha256: str
    file_count: int = Field(ge=1)


class StageCommandOutputReference(StrictModel):
    artifact_id: str
    artifact_type: str
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_inputs: tuple[str, ...] = ()


class StageCommandResult(StrictModel):
    schema_version: Literal["stage_command_result_v1"] = "stage_command_result_v1"
    outputs: dict[str, StageCommandOutputReference]
    metadata: dict[str, Any] = Field(default_factory=dict)


class StageExecutionResult(StrictModel):
    schema_version: Literal["stage_execution_result_v1"] = "stage_execution_result_v1"
    pipeline_run_id: str
    stage_run_id: str
    node_id: str
    stage_id: str
    stage_version: int
    status: Literal["SUCCEEDED", "FAILED", "CANCELLED", "REUSED"]
    attempt: int
    orchestration_key: str
    command: tuple[str, ...]
    started_at: datetime
    ended_at: datetime
    exit_code: int | None = None
    outputs: tuple[DiscoveredOutput, ...] = ()
    evidence_artifact_id: str | None = None
    retryable: bool = False
    error_type: str | None = None
    error_category: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def output_artifact_ids(self) -> dict[str, str]:
        return {item.name: item.artifact_id for item in self.outputs}


class ReceiptArtifactIdentity(StrictModel):
    artifact_id: str
    artifact_type: str
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class PipelineExecutionReceipt(StrictModel):
    schema_version: Literal["pipeline_execution_receipt_v1"] = (
        "pipeline_execution_receipt_v1"
    )
    flow_id: str
    flow_version: int = Field(ge=1)
    flow_catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    stage_registry_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prefect_flow_run_id: str
    pipeline_run_id: str
    source_commit: str
    environment_snapshot_id: str
    terminal_status: Literal["SUCCEEDED", "FAILED", "CANCELLED"]
    inputs: dict[str, ReceiptArtifactIdentity]
    outputs: dict[str, ReceiptArtifactIdentity]
    stages: tuple[StageExecutionResult, ...]
