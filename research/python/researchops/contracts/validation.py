"""Validation for Phase 1 ResearchOps governance contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .io import canonical_json_sha256, load_json, project_root


@dataclass(frozen=True)
class ContractValidationIssue:
    """One deterministic governance validation failure."""

    contract: str
    code: str
    message: str


@dataclass(frozen=True)
class ContractValidationReport:
    """Complete Phase 1 validation result."""

    checked_contracts: tuple[str, ...]
    hashes: dict[str, str]
    issues: tuple[ContractValidationIssue, ...]

    @property
    def passed(self) -> bool:
        return not self.issues

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "researchops_contract_validation_v1",
            "passed": self.passed,
            "checked_contracts": list(self.checked_contracts),
            "hashes": dict(sorted(self.hashes.items())),
            "issues": [
                {
                    "contract": issue.contract,
                    "code": issue.code,
                    "message": issue.message,
                }
                for issue in self.issues
            ],
        }


CONTRACT_PATHS = {
    "id_conventions": Path("config/platform/id_conventions_v1.json"),
    "lifecycle_states": Path("config/platform/lifecycle_states_v1.json"),
    "gate_catalog": Path("config/platform/gate_catalog_v1.json"),
    "artifact_types": Path("config/platform/artifact_types_v1.json"),
    "promotion_policies": Path("config/platform/promotion_policies_v1.json"),
    "dashboard_route_composition": Path(
        "config/research/dashboard_route_composition_v1.json"
    ),
}


def _issue(
    issues: list[ContractValidationIssue],
    contract: str,
    code: str,
    message: str,
) -> None:
    issues.append(ContractValidationIssue(contract, code, message))


def _duplicates(values: Iterable[str]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates


def _validate_id_conventions(
    payload: dict[str, Any], issues: list[ContractValidationIssue]
) -> None:
    contract = "id_conventions"
    if payload.get("schema_version") != "id_conventions_v1":
        _issue(issues, contract, "schema_version", "Unexpected schema version.")

    conventions = payload.get("conventions")
    if not isinstance(conventions, list) or not conventions:
        _issue(issues, contract, "missing_conventions", "No conventions declared.")
        return

    names = [str(item.get("name")) for item in conventions if isinstance(item, dict)]
    for duplicate in sorted(_duplicates(names)):
        _issue(issues, contract, "duplicate_name", f"Duplicate convention: {duplicate}")

    for item in conventions:
        if not isinstance(item, dict):
            _issue(issues, contract, "invalid_entry", "Convention must be an object.")
            continue
        name = str(item.get("name", ""))
        pattern = item.get("pattern")
        examples = item.get("valid_examples", [])
        if not isinstance(pattern, str):
            _issue(issues, contract, "missing_pattern", f"{name}: pattern missing.")
            continue
        try:
            compiled = re.compile(pattern)
        except re.error as exc:
            _issue(issues, contract, "invalid_pattern", f"{name}: {exc}")
            continue
        for example in examples:
            if not isinstance(example, str) or compiled.fullmatch(example) is None:
                _issue(
                    issues,
                    contract,
                    "invalid_example",
                    f"{name}: valid example does not match: {example!r}",
                )


def _validate_lifecycle_states(
    payload: dict[str, Any], issues: list[ContractValidationIssue]
) -> None:
    contract = "lifecycle_states"
    if payload.get("schema_version") != "lifecycle_states_v1":
        _issue(issues, contract, "schema_version", "Unexpected schema version.")

    resources = payload.get("resources")
    if not isinstance(resources, list) or not resources:
        _issue(issues, contract, "missing_resources", "No lifecycle resources declared.")
        return

    resource_names = [
        str(resource.get("resource"))
        for resource in resources
        if isinstance(resource, dict)
    ]
    for duplicate in sorted(_duplicates(resource_names)):
        _issue(issues, contract, "duplicate_resource", duplicate)

    for resource in resources:
        if not isinstance(resource, dict):
            _issue(issues, contract, "invalid_resource", "Resource must be an object.")
            continue
        name = str(resource.get("resource", ""))
        states = resource.get("states", [])
        transitions = resource.get("transitions", [])
        initial = resource.get("initial_state")
        terminal = resource.get("terminal_states", [])
        if not isinstance(states, list) or not all(isinstance(value, str) for value in states):
            _issue(issues, contract, "invalid_states", f"{name}: invalid states.")
            continue
        state_set = set(states)
        if len(state_set) != len(states):
            _issue(issues, contract, "duplicate_state", f"{name}: duplicate state.")
        if initial not in state_set:
            _issue(issues, contract, "invalid_initial", f"{name}: invalid initial state.")
        for state in terminal:
            if state not in state_set:
                _issue(issues, contract, "invalid_terminal", f"{name}: {state}")
        transition_pairs: list[str] = []
        for transition in transitions:
            if not isinstance(transition, dict):
                _issue(issues, contract, "invalid_transition", f"{name}: not an object.")
                continue
            source = transition.get("from")
            target = transition.get("to")
            transition_pairs.append(f"{source}->{target}")
            if source not in state_set or target not in state_set:
                _issue(
                    issues,
                    contract,
                    "unknown_transition_state",
                    f"{name}: {source}->{target}",
                )
            if source == target:
                _issue(issues, contract, "self_transition", f"{name}: {source}")
        for duplicate in sorted(_duplicates(transition_pairs)):
            _issue(issues, contract, "duplicate_transition", f"{name}: {duplicate}")


def _validate_gate_catalog(
    payload: dict[str, Any], issues: list[ContractValidationIssue]
) -> None:
    contract = "gate_catalog"
    if payload.get("schema_version") != "gate_catalog_v1":
        _issue(issues, contract, "schema_version", "Unexpected schema version.")
    gates = payload.get("gates")
    if not isinstance(gates, list) or not gates:
        _issue(issues, contract, "missing_gates", "No gates declared.")
        return
    ids = [str(gate.get("gate_id")) for gate in gates if isinstance(gate, dict)]
    for duplicate in sorted(_duplicates(ids)):
        _issue(issues, contract, "duplicate_gate", duplicate)
    for gate in gates:
        if not isinstance(gate, dict):
            _issue(issues, contract, "invalid_gate", "Gate must be an object.")
            continue
        gate_id = str(gate.get("gate_id", ""))
        if re.fullmatch(r"[A-Z][A-Z0-9_]*", gate_id) is None:
            _issue(issues, contract, "invalid_gate_id", gate_id)
        if gate.get("category") not in {
            "SOURCE",
            "DATA",
            "MODEL",
            "XAI",
            "LLM",
            "ANALYTICS",
            "RELEASE",
            "DASHBOARD",
            "ORCHESTRATION",
        }:
            _issue(issues, contract, "invalid_gate_category", gate_id)


def _validate_artifact_types(
    payload: dict[str, Any], issues: list[ContractValidationIssue]
) -> None:
    contract = "artifact_types"
    if payload.get("schema_version") != "artifact_types_v1":
        _issue(issues, contract, "schema_version", "Unexpected schema version.")
    artifacts = payload.get("artifact_types")
    if not isinstance(artifacts, list) or not artifacts:
        _issue(issues, contract, "missing_artifact_types", "No artifact types declared.")
        return
    ids = [str(item.get("artifact_type")) for item in artifacts if isinstance(item, dict)]
    for duplicate in sorted(_duplicates(ids)):
        _issue(issues, contract, "duplicate_artifact_type", duplicate)
    for item in artifacts:
        if not isinstance(item, dict):
            _issue(issues, contract, "invalid_artifact_type", "Entry must be an object.")
            continue
        artifact_type = str(item.get("artifact_type", ""))
        if re.fullmatch(r"[a-z][a-z0-9_]*", artifact_type) is None:
            _issue(issues, contract, "invalid_artifact_type_id", artifact_type)
        if item.get("storage_class") not in {
            "EXTERNAL",
            "ARTIFACT",
            "RELEASE",
            "CERTIFICATION",
        }:
            _issue(issues, contract, "invalid_storage_class", artifact_type)


def _union_for_sections(
    source_pages: dict[str, dict[str, Any]],
    section_ids: list[str],
    field: str,
) -> set[str]:
    values: set[str] = set()
    for section_id in section_ids:
        page = source_pages.get(section_id)
        if page is None:
            continue
        field_values = page.get(field, [])
        if isinstance(field_values, list):
            values.update(str(value) for value in field_values)
    return values


def _validate_dashboard_route_composition(
    payload: dict[str, Any],
    root: Path,
    artifact_types: dict[str, Any],
    gate_catalog: dict[str, Any],
    issues: list[ContractValidationIssue],
) -> None:
    contract = "dashboard_route_composition"
    if payload.get("schema_version") != "dashboard_route_composition_v1":
        _issue(issues, contract, "schema_version", "Unexpected schema version.")

    source_path = root / str(payload.get("source_contract", ""))
    if not source_path.is_file():
        _issue(issues, contract, "missing_source_contract", str(source_path))
        return
    source = load_json(source_path)
    source_pages_list = source.get("pages", [])
    source_pages = {
        str(page["page_id"]): page
        for page in source_pages_list
        if isinstance(page, dict) and "page_id" in page
    }

    physical_pages = payload.get("physical_pages")
    if not isinstance(physical_pages, list):
        _issue(issues, contract, "missing_physical_pages", "Expected a list.")
        return

    expected_page_ids = [
        "overview",
        "effectiveness",
        "mechanisms",
        "decision",
        "robustness",
        "cases",
        "methods",
    ]
    expected_routes = {
        "overview": "/",
        "effectiveness": "/effectiveness",
        "mechanisms": "/mechanisms",
        "decision": "/decision",
        "robustness": "/robustness",
        "cases": "/cases",
        "methods": "/methods",
    }
    actual_page_ids = [
        str(page.get("page_id")) for page in physical_pages if isinstance(page, dict)
    ]
    if actual_page_ids != expected_page_ids:
        _issue(
            issues,
            contract,
            "physical_page_order",
            f"Expected {expected_page_ids}, observed {actual_page_ids}",
        )

    mapped_sections: list[str] = []
    artifact_ids = {
        str(item.get("artifact_type"))
        for item in artifact_types.get("artifact_types", [])
        if isinstance(item, dict)
    }
    for page in physical_pages:
        if not isinstance(page, dict):
            _issue(issues, contract, "invalid_physical_page", "Not an object.")
            continue
        page_id = str(page.get("page_id", ""))
        if page.get("route") != expected_routes.get(page_id):
            _issue(issues, contract, "route_mismatch", page_id)
        sections = [str(value) for value in page.get("conceptual_sections", [])]
        mapped_sections.extend(sections)
        unknown = sorted(set(sections) - set(source_pages))
        if unknown:
            _issue(issues, contract, "unknown_conceptual_section", f"{page_id}: {unknown}")
        expected_rqs = _union_for_sections(source_pages, sections, "rq_ids")
        actual_rqs = {str(value) for value in page.get("rq_ids", [])}
        if actual_rqs != expected_rqs:
            _issue(
                issues,
                contract,
                "rq_union_mismatch",
                f"{page_id}: expected {sorted(expected_rqs)}, observed {sorted(actual_rqs)}",
            )
        expected_datasets = _union_for_sections(
            source_pages, sections, "required_datasets"
        )
        actual_datasets = {
            str(value) for value in page.get("required_datasets", [])
        }
        if actual_datasets != expected_datasets:
            _issue(
                issues,
                contract,
                "dataset_union_mismatch",
                f"{page_id}: expected {sorted(expected_datasets)}, "
                f"observed {sorted(actual_datasets)}",
            )
        missing_types = sorted(actual_datasets - artifact_ids)
        if missing_types:
            _issue(
                issues,
                contract,
                "unregistered_dataset_type",
                f"{page_id}: {missing_types}",
            )
        required_views = page.get("required_views")
        if not isinstance(required_views, list) or not required_views:
            _issue(issues, contract, "missing_required_views", page_id)

    source_sections = list(source_pages)
    if sorted(mapped_sections) != sorted(source_sections):
        _issue(
            issues,
            contract,
            "conceptual_coverage",
            f"Expected {sorted(source_sections)}, observed {sorted(mapped_sections)}",
        )
    for duplicate in sorted(_duplicates(mapped_sections)):
        _issue(issues, contract, "duplicate_conceptual_section", duplicate)

    gate_ids = {
        str(item.get("gate_id"))
        for item in gate_catalog.get("gates", [])
        if isinstance(item, dict)
    }
    required_gates = set(str(value) for value in payload.get("required_gates", []))
    missing_gates = sorted(required_gates - gate_ids)
    if missing_gates:
        _issue(issues, contract, "unregistered_required_gate", str(missing_gates))



def _validate_promotion_policies(
    payload: dict[str, Any],
    lifecycle: dict[str, Any],
    gate_catalog: dict[str, Any],
    issues: list[ContractValidationIssue],
) -> None:
    contract = "promotion_policies"
    try:
        from research.python.researchops.promotion.contracts import (
            PromotionPolicyCatalog,
        )

        catalog = PromotionPolicyCatalog.model_validate(payload)
    except Exception as exc:
        _issue(issues, contract, "invalid_contract", str(exc))
        return
    gate_ids = {
        str(item.get("gate_id"))
        for item in gate_catalog.get("gates", [])
        if isinstance(item, dict)
    }
    release_resource = next(
        (
            item
            for item in lifecycle.get("resources", [])
            if isinstance(item, dict) and item.get("resource") == "release"
        ),
        {},
    )
    release_transitions = {
        (str(item.get("from")), str(item.get("to")))
        for item in release_resource.get("transitions", [])
        if isinstance(item, dict)
    }
    for policy in catalog.policies:
        missing = sorted(set(policy.required_gates) - gate_ids)
        if missing:
            _issue(
                issues,
                contract,
                "unknown_required_gate",
                f"{policy.policy_id}: {missing}",
            )
        if policy.target_type == "release":
            for source in policy.from_states:
                target = (
                    policy.waived_to_state
                    if source == "CANDIDATE"
                    and policy.waiver_mode != "FORBIDDEN"
                    and policy.waived_to_state is not None
                    else policy.to_state
                )
                if (source, policy.to_state) not in release_transitions and (
                    source, target
                ) not in release_transitions:
                    _issue(
                        issues,
                        contract,
                        "invalid_release_transition",
                        f"{policy.policy_id}: {source} -> {policy.to_state}",
                    )


def _validate_no_absolute_developer_paths(
    payloads: dict[str, dict[str, Any]],
    issues: list[ContractValidationIssue],
) -> None:
    for name, payload in payloads.items():
        rendered = str(payload)
        if "/Users/" in rendered or "C:\\Users\\" in rendered:
            _issue(
                issues,
                name,
                "developer_absolute_path",
                "Active platform contract contains a developer-specific absolute path.",
            )


def validate_all_contracts(root: Path | None = None) -> ContractValidationReport:
    """Validate all Phase 1 contracts and return a stable report."""

    resolved_root = root.resolve() if root is not None else project_root()
    payloads: dict[str, dict[str, Any]] = {}
    hashes: dict[str, str] = {}
    issues: list[ContractValidationIssue] = []

    for name, relative_path in CONTRACT_PATHS.items():
        path = resolved_root / relative_path
        if not path.is_file():
            _issue(issues, name, "missing_contract", str(relative_path))
            continue
        try:
            payload = load_json(path)
        except (OSError, ValueError) as exc:
            _issue(issues, name, "invalid_json", str(exc))
            continue
        payloads[name] = payload
        hashes[str(relative_path)] = canonical_json_sha256(payload)

    if "id_conventions" in payloads:
        _validate_id_conventions(payloads["id_conventions"], issues)
    if "lifecycle_states" in payloads:
        _validate_lifecycle_states(payloads["lifecycle_states"], issues)
    if "gate_catalog" in payloads:
        _validate_gate_catalog(payloads["gate_catalog"], issues)
    if "artifact_types" in payloads:
        _validate_artifact_types(payloads["artifact_types"], issues)
    if {"promotion_policies", "lifecycle_states", "gate_catalog"}.issubset(payloads):
        _validate_promotion_policies(
            payloads["promotion_policies"],
            payloads["lifecycle_states"],
            payloads["gate_catalog"],
            issues,
        )
    if {
        "dashboard_route_composition",
        "artifact_types",
        "gate_catalog",
    }.issubset(payloads):
        _validate_dashboard_route_composition(
            payloads["dashboard_route_composition"],
            resolved_root,
            payloads["artifact_types"],
            payloads["gate_catalog"],
            issues,
        )

    _validate_no_absolute_developer_paths(payloads, issues)
    return ContractValidationReport(
        checked_contracts=tuple(sorted(payloads)),
        hashes=hashes,
        issues=tuple(issues),
    )
