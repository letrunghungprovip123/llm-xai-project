"""Pydantic models for the declarative Stage Registry."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


StageStatus = Literal["ACTIVE", "OPTIONAL", "LEGACY"]
RuntimeType = Literal["python", "npm"]
ApprovalPolicy = Literal["NONE", "EXPENSIVE", "PROVIDER", "RELEASE"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RuntimeSpec(StrictModel):
    type: RuntimeType
    executable: str = Field(min_length=1)
    args: tuple[str, ...]
    working_directory: str = "."

    @field_validator("working_directory")
    @classmethod
    def project_relative_working_directory(cls, value: str) -> str:
        if value.startswith(("/", "~")) or ":\\" in value:
            raise ValueError("working_directory must be project-relative")
        return value


class BehaviorSpec(StrictModel):
    deterministic: bool
    expensive: bool
    provider_required: bool
    approval_policy: ApprovalPolicy
    timeout_seconds: int = Field(gt=0)
    retries: int = Field(ge=0, le=10)
    concurrency_group: str = Field(min_length=1)

    @model_validator(mode="after")
    def approval_matches_risk(self) -> "BehaviorSpec":
        if self.provider_required and self.approval_policy != "PROVIDER":
            raise ValueError("provider_required stages require PROVIDER approval")
        if self.expensive and self.approval_policy == "NONE":
            raise ValueError("expensive stages require an approval policy")
        return self


class ArtifactBinding(StrictModel):
    name: str = Field(min_length=1)
    contract: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    required: bool = True
    discovery_glob: str | None = None
    discovery_globs: tuple[str, ...] = ()

    @field_validator("discovery_glob")
    @classmethod
    def project_relative_glob(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if value.startswith(("/", "~")) or ":\\" in value:
            raise ValueError("discovery_glob must be project-relative")
        return value

    @field_validator("discovery_globs")
    @classmethod
    def project_relative_globs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("discovery_globs must not contain duplicates")
        for value in values:
            if value.startswith(("/", "~")) or ":\\" in value:
                raise ValueError("discovery_globs must be project-relative")
        return values

    @property
    def discovery_patterns(self) -> tuple[str, ...]:
        if self.discovery_globs:
            return self.discovery_globs
        assert self.discovery_glob is not None
        return (self.discovery_glob,)


class VerificationSpec(StrictModel):
    # success_gate remains the declared semantic/scientific gate for compatibility
    # with the Flow Catalog terminal-gate contract. The executor must never infer it
    # merely from exit code or output existence.
    success_gate: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    execution_gate: str = Field(
        default="STAGE_EXECUTION_SUCCEEDED", pattern=r"^[A-Z][A-Z0-9_]*$"
    )
    adapter_id: str = Field(default="execution_success_v1", pattern=r"^[a-z][a-z0-9_]*$")
    adapter_version: int = Field(default=1, ge=1)
    report_glob: str | None = None
    failure_evidence_globs: tuple[str, ...] = ()
    command: RuntimeSpec | None = None

    @field_validator("report_glob")
    @classmethod
    def project_relative_report_glob(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if value.startswith(("/", "~")) or ":\\" in value:
            raise ValueError("report_glob must be project-relative")
        return value

    @field_validator("failure_evidence_globs")
    @classmethod
    def project_relative_failure_globs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("failure_evidence_globs must not contain duplicates")
        for value in values:
            if value.startswith(("/", "~")) or ":\\" in value:
                raise ValueError("failure_evidence_globs must be project-relative")
        return values


class ResourceSpec(StrictModel):
    cpu: float = Field(gt=0)
    memory_mb: int = Field(gt=0)
    gpu: bool


class StageDefinition(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
    version: int = Field(ge=1)
    title: str = Field(min_length=1)
    owner: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    status: StageStatus
    runtime: RuntimeSpec
    behavior: BehaviorSpec
    inputs: tuple[ArtifactBinding, ...]
    outputs: tuple[ArtifactBinding, ...]
    verification: VerificationSpec
    resources: ResourceSpec
    secrets: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    legacy_dispatcher_stage: str | None = None
    notes: tuple[str, ...] = ()

    @field_validator("secrets")
    @classmethod
    def validate_secret_names(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            if re.fullmatch(r"[A-Z][A-Z0-9_]*", value) is None:
                raise ValueError(f"Invalid secret environment name: {value}")
        return values

    @model_validator(mode="after")
    def stage_has_output_and_consistent_runtime(self) -> "StageDefinition":
        if not self.outputs:
            raise ValueError("every stage must declare at least one output")
        if any(bool(output.discovery_glob) == bool(output.discovery_globs) for output in self.outputs):
            raise ValueError(
                "every stage output must declare exactly one of discovery_glob or discovery_globs"
            )
        input_names = [binding.name for binding in self.inputs]
        output_names = [binding.name for binding in self.outputs]
        if len(input_names) != len(set(input_names)):
            raise ValueError("stage input names must be unique")
        if len(output_names) != len(set(output_names)):
            raise ValueError("stage output names must be unique")
        if self.runtime.type == "python" and self.runtime.executable != "python3":
            raise ValueError("python runtime must use python3")
        if self.runtime.type == "npm" and self.runtime.executable != "npm":
            raise ValueError("npm runtime must use npm")
        return self


class StageRegistry(StrictModel):
    schema_version: Literal["stage_registry_v1"]
    status: Literal["ACTIVE"]
    stages: tuple[StageDefinition, ...]

    @model_validator(mode="after")
    def unique_stage_ids(self) -> "StageRegistry":
        ids = [stage.id for stage in self.stages]
        if len(ids) != len(set(ids)):
            raise ValueError("stage IDs must be unique")
        return self

    def by_id(self) -> dict[str, StageDefinition]:
        return {stage.id: stage for stage in self.stages}
