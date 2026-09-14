"""Cross-contract and repository validation for the Stage Registry."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from research.python.researchops.contracts.io import project_root

from .command_renderer import resolve_command
from .compiler import lock_matches
from .graph import topological_order
from .loader import (
    load_artifact_catalog,
    load_gate_catalog,
    load_stage_registry,
    registry_path,
)
from .models import StageRegistry


@dataclass(frozen=True)
class StageRegistryIssue:
    code: str
    message: str
    stage_id: str | None = None


@dataclass(frozen=True)
class StageRegistryValidationReport:
    stage_count: int
    active_count: int
    optional_count: int
    legacy_count: int
    dispatcher_stage_count: int
    issues: tuple[StageRegistryIssue, ...]

    @property
    def passed(self) -> bool:
        return not self.issues

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "stage_registry_validation_v1",
            "passed": self.passed,
            "stage_count": self.stage_count,
            "active_count": self.active_count,
            "optional_count": self.optional_count,
            "legacy_count": self.legacy_count,
            "dispatcher_stage_count": self.dispatcher_stage_count,
            "issues": [
                {
                    "code": issue.code,
                    "message": issue.message,
                    "stage_id": issue.stage_id,
                }
                for issue in self.issues
            ],
        }


def dispatcher_stage_names(root: Path) -> set[str]:
    text = (root / "research/ts/cli.ts").read_text(encoding="utf-8")
    return set(re.findall(r'^\s+"([^"]+)":\s*\{', text, flags=re.MULTILINE))


def _catalog_artifacts(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item["artifact_type"]): item
        for item in payload.get("artifact_types", [])
        if isinstance(item, dict) and "artifact_type" in item
    }


def _catalog_gates(payload: dict[str, Any]) -> set[str]:
    return {
        str(item["gate_id"])
        for item in payload.get("gates", [])
        if isinstance(item, dict) and "gate_id" in item
    }


def validate_stage_registry(root: Path | None = None) -> StageRegistryValidationReport:
    resolved_root = (root or project_root()).resolve()
    issues: list[StageRegistryIssue] = []
    try:
        registry = load_stage_registry(registry_path(resolved_root))
    except (OSError, ValueError, ValidationError) as exc:
        issues.append(StageRegistryIssue("registry_parse_failed", str(exc)))
        return StageRegistryValidationReport(0, 0, 0, 0, 0, tuple(issues))

    artifact_catalog = _catalog_artifacts(load_artifact_catalog(resolved_root))
    gate_catalog = _catalog_gates(load_gate_catalog(resolved_root))
    producers: dict[str, str] = {}

    for stage in registry.stages:
        resolution = resolve_command(stage, resolved_root)
        if not resolution.structurally_valid:
            issues.append(
                StageRegistryIssue(
                    "command_unresolved",
                    "; ".join(resolution.details),
                    stage.id,
                )
            )
        for binding in (*stage.inputs, *stage.outputs):
            if binding.contract not in artifact_catalog:
                issues.append(
                    StageRegistryIssue(
                        "unknown_artifact_contract", binding.contract, stage.id
                    )
                )
        if stage.verification.success_gate not in gate_catalog:
            issues.append(
                StageRegistryIssue(
                    "unknown_success_gate",
                    stage.verification.success_gate,
                    stage.id,
                )
            )
        if stage.verification.execution_gate not in gate_catalog:
            issues.append(
                StageRegistryIssue(
                    "unknown_execution_gate",
                    stage.verification.execution_gate,
                    stage.id,
                )
            )
        if stage.verification.report_glob is not None:
            output_patterns = {
                pattern
                for output in stage.outputs
                for pattern in output.discovery_patterns
            }
            # The report need not equal a discovery pattern, but at least one output
            # pattern must be broad enough to include it. Static exact path/glob
            # equivalence is intentionally conservative and fail-closed.
            report = stage.verification.report_glob
            if report not in output_patterns and not any(
                pattern.endswith("/**") or pattern.endswith("/**/*")
                for pattern in output_patterns
            ):
                issues.append(
                    StageRegistryIssue(
                        "semantic_report_not_bound_to_output",
                        f"report={report!r} outputs={sorted(output_patterns)!r}",
                        stage.id,
                    )
                )
        if stage.behavior.provider_required and not stage.secrets:
            issues.append(
                StageRegistryIssue(
                    "provider_secret_missing",
                    "Provider stage must name at least one secret environment variable.",
                    stage.id,
                )
            )
        for output in stage.outputs:
            if stage.status == "LEGACY":
                continue
            previous = producers.get(output.contract)
            if previous is not None:
                issues.append(
                    StageRegistryIssue(
                        "conflicting_output_producer",
                        f"{output.contract}: {previous} and {stage.id}",
                        stage.id,
                    )
                )
            producers[output.contract] = stage.id

    for stage in registry.stages:
        for binding in stage.inputs:
            artifact = artifact_catalog.get(binding.contract, {})
            external = bool(artifact.get("external"))
            if binding.required and not external and binding.contract not in producers:
                issues.append(
                    StageRegistryIssue(
                        "missing_input_producer", binding.contract, stage.id
                    )
                )

    dispatcher = dispatcher_stage_names(resolved_root)
    declared_dispatcher = {
        stage.legacy_dispatcher_stage
        for stage in registry.stages
        if stage.legacy_dispatcher_stage is not None
    }
    for missing in sorted(dispatcher - declared_dispatcher):
        issues.append(
            StageRegistryIssue(
                "dispatcher_stage_not_registered",
                missing,
            )
        )
    for unknown in sorted(declared_dispatcher - dispatcher):
        issues.append(
            StageRegistryIssue(
                "registered_dispatcher_stage_missing",
                str(unknown),
            )
        )

    try:
        topological_order(registry)
    except ValueError as exc:
        issues.append(StageRegistryIssue("dependency_cycle", str(exc)))

    if not lock_matches(resolved_root):
        issues.append(
            StageRegistryIssue(
                "compiled_lock_drift",
                "Run `python3 -m research.python.researchops.stage_registry compile`.",
            )
        )

    counts = {
        status: sum(stage.status == status for stage in registry.stages)
        for status in ("ACTIVE", "OPTIONAL", "LEGACY")
    }
    return StageRegistryValidationReport(
        stage_count=len(registry.stages),
        active_count=counts["ACTIVE"],
        optional_count=counts["OPTIONAL"],
        legacy_count=counts["LEGACY"],
        dispatcher_stage_count=len(dispatcher),
        issues=tuple(issues),
    )
