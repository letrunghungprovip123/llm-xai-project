"""Deterministic Flow Catalog compiler and lock verification."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from research.python.researchops.contracts.io import canonical_json_sha256, project_root

from .loader import DEFAULT_CATALOG_PATH, catalog_path, load_flow_catalog, lock_path
from .models import FlowCatalog, FlowDefinition
from .validator import validate_flow_catalog


def _sorted_mapping(value: dict[str, str]) -> dict[str, str]:
    return {key: value[key] for key in sorted(value)}


def _flow_payload(flow: FlowDefinition) -> dict[str, Any]:
    payload = flow.model_dump(mode="json", exclude_none=True)
    payload["approval_policies"] = sorted(payload["approval_policies"])
    payload["tags"] = sorted(payload["tags"])
    payload["inputs"] = sorted(payload["inputs"], key=lambda item: item["name"])
    payload["nodes"] = sorted(payload["nodes"], key=lambda item: item["node_id"])
    for node in payload["nodes"]:
        node["input_mapping"] = _sorted_mapping(node.get("input_mapping", {}))
        node["parameter_mapping"] = _sorted_mapping(
            node.get("parameter_mapping", {})
        )
    payload["edges"] = sorted(
        payload["edges"],
        key=lambda item: (
            item["from_node"],
            item["from_output"],
            item["to_node"],
            item["to_input"],
        ),
    )
    payload["outputs"] = sorted(payload["outputs"], key=lambda item: item["name"])
    return payload


def normalized_catalog_payload(catalog: FlowCatalog) -> dict[str, Any]:
    return {
        "schema_version": catalog.schema_version,
        "status": catalog.status,
        "stage_registry_sha256": catalog.stage_registry_sha256,
        "flows": [
            _flow_payload(flow)
            for flow in sorted(catalog.flows, key=lambda item: item.id)
        ],
    }


def compile_payload(root: Path | None = None) -> dict[str, Any]:
    resolved_root = root or project_root()
    source_path = catalog_path(resolved_root)
    source_bytes = source_path.read_bytes()
    catalog = load_flow_catalog(source_path)
    report = validate_flow_catalog(catalog, root=resolved_root)
    if not report.passed:
        raise ValueError(
            "Cannot compile invalid Flow Catalog:\n- " + "\n- ".join(report.errors)
        )
    normalized = normalized_catalog_payload(catalog)
    return {
        "schema_version": "flow_catalog_lock_v1",
        "source_path": str(DEFAULT_CATALOG_PATH),
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "catalog_sha256": canonical_json_sha256(normalized),
        "stage_registry_sha256": catalog.stage_registry_sha256,
        "flow_count": len(catalog.flows),
        "executable_flow_count": report.executable_flow_count,
        "covered_stage_count": report.covered_stage_count,
        "catalog": normalized,
    }


def write_lock(root: Path | None = None, output_path: Path | None = None) -> Path:
    resolved_root = root or project_root()
    target = output_path or lock_path(resolved_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(compile_payload(resolved_root), indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    return target


def lock_matches(root: Path | None = None) -> bool:
    resolved_root = root or project_root()
    target = lock_path(resolved_root)
    if not target.is_file():
        return False
    committed = json.loads(target.read_text(encoding="utf-8"))
    return committed == compile_payload(resolved_root)
