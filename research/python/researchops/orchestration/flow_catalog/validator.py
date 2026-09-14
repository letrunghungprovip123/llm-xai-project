"""Cross-contract validation between Flow Catalog and Stage Registry."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import json

from research.python.researchops.stage_registry.compiler import compile_payload
from research.python.researchops.stage_registry.loader import (
    load_gate_catalog,
    load_stage_registry,
)
from research.python.researchops.stage_registry.models import StageDefinition
from research.python.researchops.contracts.io import project_root

from .graph import topological_order
from .models import FlowCatalog, FlowDefinition, FlowNode


@dataclass(frozen=True)
class FlowCatalogValidationReport:
    flow_count: int
    executable_flow_count: int
    planned_flow_count: int
    stage_count: int
    covered_stage_count: int
    missing_stage_ids: tuple[str, ...]
    unknown_stage_ids: tuple[str, ...]
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "flow_catalog_validation_v1",
            "passed": self.passed,
            "flow_count": self.flow_count,
            "executable_flow_count": self.executable_flow_count,
            "planned_flow_count": self.planned_flow_count,
            "stage_count": self.stage_count,
            "covered_stage_count": self.covered_stage_count,
            "missing_stage_ids": list(self.missing_stage_ids),
            "unknown_stage_ids": list(self.unknown_stage_ids),
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


def _expected_queue(stage: StageDefinition) -> str:
    if stage.behavior.provider_required:
        return "provider-llm"
    if stage.behavior.approval_policy == "RELEASE":
        return "release"
    if stage.behavior.concurrency_group in {"mlflow-registry", "release-promotion"}:
        return "release"
    if stage.behavior.concurrency_group == "cpu-heavy":
        return "cpu-heavy"
    return "verification"


def _expected_flow_queue(stages: list[StageDefinition]) -> str:
    if any(stage.behavior.provider_required for stage in stages):
        return "provider-llm"
    if any(stage.behavior.approval_policy == "RELEASE" for stage in stages):
        return "release"
    if any(stage.behavior.concurrency_group in {"mlflow-registry", "release-promotion"} for stage in stages):
        return "release"
    if any(stage.behavior.concurrency_group == "cpu-heavy" for stage in stages):
        return "cpu-heavy"
    return "verification"


def _expected_execution_mode(stages: list[StageDefinition]) -> str:
    if any("promotion" in stage.tags for stage in stages):
        return "PROMOTE_RELEASE"
    if any(stage.behavior.provider_required for stage in stages):
        return "RUN_PROVIDER_DEPENDENT"
    if any(stage.behavior.expensive for stage in stages):
        return "RUN_EXPENSIVE"
    return "RUN_DETERMINISTIC"


def _validate_flow(
    flow: FlowDefinition,
    stage_by_id: dict[str, StageDefinition],
    gate_ids: set[str],
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if flow.status == "PLANNED":
        warnings.append(f"{flow.id}: planned flow is intentionally non-executable")
        return errors, warnings

    node_by_id = {node.node_id: node for node in flow.nodes}
    flow_input_by_name = {item.name: item for item in flow.inputs}
    stages: list[StageDefinition] = []
    for node in flow.nodes:
        stage = stage_by_id.get(node.stage_id)
        if stage is None:
            errors.append(f"{flow.id}.{node.node_id}: unknown stage {node.stage_id}")
            continue
        stages.append(stage)
        if stage.status == "LEGACY":
            errors.append(f"{flow.id}.{node.node_id}: LEGACY stage is not executable")
        if stage.status == "OPTIONAL" and node.required:
            errors.append(
                f"{flow.id}.{node.node_id}: OPTIONAL stage must be an optional node"
            )
        if not node.required and not node.condition:
            errors.append(f"{flow.id}.{node.node_id}: optional node lacks condition")
        expected_queue = _expected_queue(stage)
        if node.work_queue != expected_queue:
            errors.append(
                f"{flow.id}.{node.node_id}: queue {node.work_queue!r} does not "
                f"match stage policy {expected_queue!r}"
            )
        unknown_mappings = set(node.input_mapping) - {
            binding.name for binding in stage.inputs
        }
        if unknown_mappings:
            errors.append(
                f"{flow.id}.{node.node_id}: unknown stage input mappings "
                f"{sorted(unknown_mappings)}"
            )
        for stage_input, flow_input_name in node.input_mapping.items():
            flow_input = flow_input_by_name.get(flow_input_name)
            if flow_input is None:
                errors.append(
                    f"{flow.id}.{node.node_id}.{stage_input}: unknown flow input "
                    f"{flow_input_name}"
                )
                continue
            binding = next(item for item in stage.inputs if item.name == stage_input)
            if binding.contract != flow_input.contract:
                errors.append(
                    f"{flow.id}.{node.node_id}.{stage_input}: contract mismatch "
                    f"stage={binding.contract} flow={flow_input.contract}"
                )

    incoming: dict[tuple[str, str], int] = {}
    consumed_outputs: set[tuple[str, str]] = set()
    for edge in flow.edges:
        source_node = node_by_id.get(edge.from_node)
        target_node = node_by_id.get(edge.to_node)
        if source_node is None or target_node is None:
            errors.append(
                f"{flow.id}: edge references unknown node "
                f"{edge.from_node}->{edge.to_node}"
            )
            continue
        source_stage = stage_by_id.get(source_node.stage_id)
        target_stage = stage_by_id.get(target_node.stage_id)
        if source_stage is None or target_stage is None:
            continue
        source = next(
            (item for item in source_stage.outputs if item.name == edge.from_output),
            None,
        )
        target = next(
            (item for item in target_stage.inputs if item.name == edge.to_input),
            None,
        )
        if source is None:
            errors.append(
                f"{flow.id}: {edge.from_node} has no output {edge.from_output}"
            )
            continue
        if target is None:
            errors.append(f"{flow.id}: {edge.to_node} has no input {edge.to_input}")
            continue
        if source.contract != target.contract:
            errors.append(
                f"{flow.id}: edge contract mismatch "
                f"{edge.from_node}.{edge.from_output}={source.contract} -> "
                f"{edge.to_node}.{edge.to_input}={target.contract}"
            )
        key = (edge.to_node, edge.to_input)
        incoming[key] = incoming.get(key, 0) + 1
        if incoming[key] > 1:
            errors.append(f"{flow.id}: multiple producers target {key[0]}.{key[1]}")
        consumed_outputs.add((edge.from_node, edge.from_output))

    for node in flow.nodes:
        stage = stage_by_id.get(node.stage_id)
        if stage is None:
            continue
        for binding in stage.inputs:
            count = incoming.get((node.node_id, binding.name), 0)
            mapped = binding.name in node.input_mapping
            if count and mapped:
                errors.append(
                    f"{flow.id}.{node.node_id}.{binding.name}: input is supplied "
                    "by both edge and flow input mapping"
                )
            if binding.required and count + int(mapped) != 1:
                errors.append(
                    f"{flow.id}.{node.node_id}.{binding.name}: required input "
                    "must have exactly one source"
                )

    exposed_outputs: set[tuple[str, str]] = set()
    for output in flow.outputs:
        node = node_by_id.get(output.from_node)
        if node is None:
            errors.append(f"{flow.id}.{output.name}: unknown source node {output.from_node}")
            continue
        stage = stage_by_id.get(node.stage_id)
        if stage is None:
            continue
        binding = next(
            (item for item in stage.outputs if item.name == output.from_output),
            None,
        )
        if binding is None:
            errors.append(
                f"{flow.id}.{output.name}: stage has no output {output.from_output}"
            )
            continue
        if binding.contract != output.contract:
            errors.append(
                f"{flow.id}.{output.name}: output contract mismatch "
                f"stage={binding.contract} flow={output.contract}"
            )
        exposed_outputs.add((output.from_node, output.from_output))

    for node in flow.nodes:
        stage = stage_by_id.get(node.stage_id)
        if stage is None:
            continue
        for binding in stage.outputs:
            if binding.required and (node.node_id, binding.name) not in (
                consumed_outputs | exposed_outputs
            ):
                errors.append(
                    f"{flow.id}.{node.node_id}.{binding.name}: required stage output "
                    "is neither consumed nor exposed"
                )

    consumed_flow_inputs = {
        flow_input
        for node in flow.nodes
        for flow_input in node.input_mapping.values()
    }
    for item in flow.inputs:
        if item.name not in consumed_flow_inputs:
            errors.append(f"{flow.id}.{item.name}: declared flow input is unused")

    try:
        topological_order(flow)
    except ValueError as exc:
        errors.append(str(exc))

    if stages:
        required_policies = {
            stage.behavior.approval_policy
            for stage in stages
            if stage.behavior.approval_policy != "NONE"
        }
        declared = set(flow.approval_policies)
        if required_policies != declared:
            errors.append(
                f"{flow.id}: approval policy mismatch expected="
                f"{sorted(required_policies)} observed={sorted(declared)}"
            )
        expected_queue = _expected_flow_queue(stages)
        if flow.work_queue != expected_queue:
            errors.append(
                f"{flow.id}: flow queue mismatch expected={expected_queue} "
                f"observed={flow.work_queue}"
            )
        expected_mode = _expected_execution_mode(stages)
        if flow.execution_mode != expected_mode:
            errors.append(
                f"{flow.id}: execution mode mismatch expected={expected_mode} "
                f"observed={flow.execution_mode}"
            )

    if flow.terminal_gate not in gate_ids:
        errors.append(f"{flow.id}: unknown terminal gate {flow.terminal_gate}")
    terminal_nodes = {
        output.from_node for output in flow.outputs if output.required
    }
    terminal_gates = {
        stage_by_id[node_by_id[node_id].stage_id].verification.success_gate
        for node_id in terminal_nodes
        if node_id in node_by_id
        and node_by_id[node_id].stage_id in stage_by_id
    }
    if flow.terminal_gate not in terminal_gates:
        errors.append(
            f"{flow.id}: terminal gate {flow.terminal_gate} is not emitted by "
            f"a required exposed output node; observed={sorted(terminal_gates)}"
        )
    return errors, warnings


def validate_flow_catalog(
    catalog: FlowCatalog,
    *,
    root: Path | None = None,
) -> FlowCatalogValidationReport:
    resolved_root = root or project_root()
    registry = load_stage_registry(root=resolved_root)
    stage_by_id = registry.by_id()
    gate_catalog = load_gate_catalog(resolved_root)
    gate_ids = {item["gate_id"] for item in gate_catalog["gates"]}
    errors: list[str] = []
    warnings: list[str] = []

    try:
        import jsonschema
    except ImportError as exc:  # pragma: no cover - dependency contract
        errors.append(f"Flow Catalog JSON Schema dependency is missing: {exc}")
    else:
        try:
            schema_path = (
                resolved_root
                / "config/platform/schemas/flow_catalog_v1.schema.json"
            )
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            jsonschema.Draft202012Validator(schema).validate(
                catalog.model_dump(mode="json")
            )
        except (OSError, json.JSONDecodeError, jsonschema.ValidationError) as exc:
            errors.append(f"Flow Catalog JSON Schema validation failed: {exc}")

    expected_registry_hash = compile_payload(resolved_root)["registry_sha256"]
    if catalog.stage_registry_sha256 != expected_registry_hash:
        errors.append(
            "Flow Catalog stage_registry_sha256 is stale: "
            f"expected={expected_registry_hash} "
            f"observed={catalog.stage_registry_sha256}"
        )

    covered: set[str] = set()
    unknown: set[str] = set()
    for flow in catalog.flows:
        for node in flow.nodes:
            if node.stage_id in stage_by_id:
                covered.add(node.stage_id)
            else:
                unknown.add(node.stage_id)
        flow_errors, flow_warnings = _validate_flow(flow, stage_by_id, gate_ids)
        errors.extend(flow_errors)
        warnings.extend(flow_warnings)

    expected_stages = {
        stage.id for stage in registry.stages if stage.status != "LEGACY"
    }
    missing = expected_stages - covered
    if missing:
        errors.append(f"Active/optional stages missing from Flow Catalog: {sorted(missing)}")
    return FlowCatalogValidationReport(
        flow_count=len(catalog.flows),
        executable_flow_count=sum(item.status != "PLANNED" for item in catalog.flows),
        planned_flow_count=sum(item.status == "PLANNED" for item in catalog.flows),
        stage_count=len(expected_stages),
        covered_stage_count=len(covered & expected_stages),
        missing_stage_ids=tuple(sorted(missing)),
        unknown_stage_ids=tuple(sorted(unknown)),
        errors=tuple(errors),
        warnings=tuple(warnings),
    )
