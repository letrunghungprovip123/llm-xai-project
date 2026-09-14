"""Strict contracts for the declarative ResearchOps flow catalog."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

FlowStatus = Literal["ACTIVE", "OPTIONAL", "PLANNED"]
ExecutionMode = Literal[
    "VERIFY_ONLY",
    "RUN_DETERMINISTIC",
    "RUN_EXPENSIVE",
    "RUN_PROVIDER_DEPENDENT",
    "PROMOTE_RELEASE",
]
ApprovalPolicy = Literal["EXPENSIVE", "PROVIDER", "RELEASE"]
WorkQueue = Literal["release", "provider-llm", "cpu-heavy", "verification"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FlowInput(StrictModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    contract: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    required: bool = True
    description: str = Field(min_length=1)


class FlowNode(StrictModel):
    node_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    stage_id: str = Field(pattern=r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
    required: bool = True
    condition: str | None = None
    work_queue: WorkQueue
    input_mapping: dict[str, str] = Field(default_factory=dict)
    parameter_mapping: dict[str, str] = Field(default_factory=dict)

    @field_validator("condition")
    @classmethod
    def condition_is_stable_identifier(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if re.fullmatch(r"[a-z][a-z0-9_.-]*", value) is None:
            raise ValueError("condition must be a stable lowercase identifier")
        return value

    @model_validator(mode="after")
    def optional_nodes_are_explicit(self) -> "FlowNode":
        if not self.required and not self.condition:
            raise ValueError("optional flow nodes require an explicit condition")
        if self.required and self.condition is not None:
            raise ValueError("required flow nodes cannot declare a condition")
        return self


class FlowEdge(StrictModel):
    from_node: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    from_output: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    to_node: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    to_input: str = Field(pattern=r"^[a-z][a-z0-9_]*$")

    @model_validator(mode="after")
    def no_self_edge(self) -> "FlowEdge":
        if self.from_node == self.to_node:
            raise ValueError("flow edges cannot be self-referential")
        return self


class FlowOutput(StrictModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    contract: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    from_node: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    from_output: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    required: bool = True
    description: str = Field(min_length=1)


class FlowDefinition(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    version: int = Field(ge=1)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    status: FlowStatus
    execution_mode: ExecutionMode
    work_queue: WorkQueue
    approval_policies: tuple[ApprovalPolicy, ...] = ()
    inputs: tuple[FlowInput, ...]
    nodes: tuple[FlowNode, ...]
    edges: tuple[FlowEdge, ...] = ()
    outputs: tuple[FlowOutput, ...]
    terminal_gate: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    tags: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def local_identity_is_unique(self) -> "FlowDefinition":
        for label, values in (
            ("flow input", [item.name for item in self.inputs]),
            ("node", [item.node_id for item in self.nodes]),
            ("flow output", [item.name for item in self.outputs]),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate {label} identifiers in flow {self.id}")
        policies = list(self.approval_policies)
        if len(policies) != len(set(policies)):
            raise ValueError(f"duplicate approval policies in flow {self.id}")
        if self.status != "PLANNED" and not self.nodes:
            raise ValueError("non-planned flows must contain at least one node")
        if self.status == "PLANNED" and self.nodes:
            raise ValueError("planned flows cannot pretend to have executable nodes")
        return self


class FlowCatalog(StrictModel):
    schema_version: Literal["flow_catalog_v1"]
    status: Literal["ACTIVE"]
    stage_registry_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    flows: tuple[FlowDefinition, ...]

    @model_validator(mode="after")
    def flow_ids_are_unique(self) -> "FlowCatalog":
        ids = [item.id for item in self.flows]
        if len(ids) != len(set(ids)):
            raise ValueError("flow IDs must be unique")
        return self

    def by_id(self) -> dict[str, FlowDefinition]:
        return {item.id: item for item in self.flows}
