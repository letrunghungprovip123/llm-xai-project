from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Literal

import yaml
from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, Field, model_validator

from research.python.researchops.contracts.io import (
    canonical_json_sha256,
    project_root,
)

from ..flow_catalog.compiler import compile_payload as compile_flow_catalog
from ..flow_catalog.loader import load_flow_catalog


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DeploymentDefinition(StrictModel):
    flow_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    flow_name: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    deployment_name: str = Field(min_length=1)
    entrypoint: str = Field(
        pattern=(
            r"^(?:[^:]+:[A-Za-z_][A-Za-z0-9_]*|"
            r"(?:[A-Za-z_][A-Za-z0-9_]*\.)+[A-Za-z_][A-Za-z0-9_]*)$"
        )
    )
    work_queue_name: Literal[
        "release", "provider-llm", "cpu-heavy", "verification"
    ]
    manual_only: Literal[True] = True


class DeploymentCatalog(StrictModel):
    schema_version: Literal["prefect_deployments_v1"]
    status: Literal["ACTIVE"]
    work_pool_name: str = Field(min_length=1)
    source_directory: str = Field(pattern=r"^/")
    deployments: tuple[DeploymentDefinition, ...]

    @model_validator(mode="after")
    def identities_are_unique(self) -> "DeploymentCatalog":
        for label, values in (
            ("flow ID", [item.flow_id for item in self.deployments]),
            (
                "deployment identity",
                [
                    f"{item.flow_name}/{item.deployment_name}"
                    for item in self.deployments
                ],
            ),
            ("entrypoint", [item.entrypoint for item in self.deployments]),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate Prefect {label}")
        return self


def load_deployment_catalog(root: Path | None = None) -> DeploymentCatalog:
    resolved = (root or project_root()).resolve()
    path = resolved / "config/platform/prefect/prefect_deployments_v1.json"
    return DeploymentCatalog.model_validate_json(path.read_text(encoding="utf-8"))


def _entrypoint_parts(entrypoint: str) -> tuple[Literal["file", "module"], str, str]:
    if ":" in entrypoint:
        path_text, function_name = entrypoint.split(":", 1)
        return "file", path_text, function_name
    module_name, function_name = entrypoint.rsplit(".", 1)
    return "module", module_name, function_name


def _entrypoint_source_path(root: Path, entrypoint: str) -> Path | None:
    kind, location, _ = _entrypoint_parts(entrypoint)
    if kind == "file":
        candidate = root / location
        return candidate if candidate.is_file() else None
    module_path = root.joinpath(*location.split("."))
    module_file = module_path.with_suffix(".py")
    if module_file.is_file():
        return module_file
    package_file = module_path / "__init__.py"
    return package_file if package_file.is_file() else None


def _entrypoint_exists(root: Path, entrypoint: str) -> bool:
    _, _, function_name = _entrypoint_parts(entrypoint)
    path = _entrypoint_source_path(root, entrypoint)
    if path is None:
        return False
    # Avoid importing Prefect during deterministic validation. The official
    # module is statically inspected for the declared function symbol.
    source = path.read_text(encoding="utf-8")
    return (
        f"def {function_name}(" in source
        or f"{function_name} = _missing_prefect" in source
    )


FlowLoader = Callable[[str], Any]


def _load_prefect_flow(entrypoint: str) -> Any:
    from prefect.flows import load_flow_from_entrypoint

    return load_flow_from_entrypoint(entrypoint)


def validate_deployment_imports(
    root: Path | None = None,
    *,
    loader: FlowLoader | None = None,
) -> dict[str, object]:
    resolved = (root or project_root()).resolve()
    catalog = load_deployment_catalog(resolved)
    load = loader or _load_prefect_flow
    errors: list[str] = []
    loaded: list[str] = []
    previous_cwd = Path.cwd()
    inserted = False
    root_text = str(resolved)
    try:
        if root_text not in sys.path:
            sys.path.insert(0, root_text)
            inserted = True
        os.chdir(resolved)
        for deployment in catalog.deployments:
            try:
                flow_object = load(deployment.entrypoint)
                actual_name = str(getattr(flow_object, "name", ""))
                if actual_name and actual_name != deployment.flow_name:
                    errors.append(
                        f"{deployment.flow_id}: loaded flow name {actual_name!r} "
                        f"does not match {deployment.flow_name!r}"
                    )
                    continue
                loaded.append(deployment.flow_id)
            except Exception as exc:  # Prefect wraps user import failures
                errors.append(
                    f"{deployment.flow_id}: {type(exc).__name__}: {exc}"
                )
    finally:
        os.chdir(previous_cwd)
        if inserted:
            sys.path.remove(root_text)
    return {
        "schema_version": "prefect_deployment_import_validation_v1",
        "passed": not errors,
        "deployment_count": len(catalog.deployments),
        "loaded_count": len(loaded),
        "loaded_flow_ids": sorted(loaded),
        "errors": errors,
    }


def validate_deployment_catalog(root: Path | None = None) -> dict[str, object]:
    resolved = (root or project_root()).resolve()
    catalog = load_deployment_catalog(resolved)
    schema = json.loads(
        (
            resolved
            / "config/platform/schemas/prefect_deployments_v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    errors = [
        error.message
        for error in Draft202012Validator(schema).iter_errors(
            catalog.model_dump(mode="json")
        )
    ]
    flows = load_flow_catalog(root=resolved).by_id()
    deployment_by_flow = {item.flow_id: item for item in catalog.deployments}
    missing = sorted(set(flows) - set(deployment_by_flow))
    unknown = sorted(set(deployment_by_flow) - set(flows))
    if missing:
        errors.append(f"missing deployments for flows: {missing}")
    if unknown:
        errors.append(f"deployments reference unknown flows: {unknown}")
    for flow_id, deployment in deployment_by_flow.items():
        flow = flows.get(flow_id)
        if flow is None:
            continue
        if deployment.work_queue_name != flow.work_queue:
            errors.append(
                f"{flow_id}: queue mismatch deployment="
                f"{deployment.work_queue_name} flow={flow.work_queue}"
            )
        if not _entrypoint_exists(resolved, deployment.entrypoint):
            errors.append(f"{flow_id}: missing entrypoint {deployment.entrypoint}")
    return {
        "schema_version": "prefect_deployment_catalog_validation_v1",
        "passed": not errors,
        "deployment_count": len(catalog.deployments),
        "flow_count": len(flows),
        "missing_flow_ids": missing,
        "unknown_flow_ids": unknown,
        "manual_only": all(item.manual_only for item in catalog.deployments),
        "errors": errors,
    }


def render_prefect_yaml(root: Path | None = None) -> dict[str, object]:
    resolved = (root or project_root()).resolve()
    catalog = load_deployment_catalog(resolved)
    flow_lock = compile_flow_catalog(resolved)
    version = f"flow-catalog-{str(flow_lock['catalog_sha256'])[:16]}"
    payload = {
        "name": "llm-xai-researchops",
        "prefect-version": "3.7.8",
        "build": None,
        "push": None,
        "pull": [
            {
                "prefect.deployments.steps.set_working_directory": {
                    "directory": catalog.source_directory
                }
            }
        ],
        "deployments": [
            {
                "name": item.deployment_name,
                "version": version,
                "description": f"ResearchOps governed flow: {item.flow_id}",
                "tags": ["researchops", "manual-only", item.work_queue_name],
                "entrypoint": item.entrypoint,
                "work_pool": {
                    "name": catalog.work_pool_name,
                    "work_queue_name": item.work_queue_name,
                    "job_variables": {},
                },
                "schedules": [],
                "parameters": {},
            }
            for item in catalog.deployments
        ],
    }
    return payload


def write_prefect_yaml(
    root: Path | None = None, output_path: Path | None = None
) -> Path:
    resolved = (root or project_root()).resolve()
    target = output_path or resolved / "prefect.yaml"
    target.write_text(
        yaml.safe_dump(
            render_prefect_yaml(resolved),
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    return target


def deployment_lock_payload(root: Path | None = None) -> dict[str, object]:
    resolved = (root or project_root()).resolve()
    catalog = load_deployment_catalog(resolved)
    rendered = render_prefect_yaml(resolved)
    return {
        "schema_version": "prefect_deployments_lock_v1",
        "catalog_sha256": canonical_json_sha256(catalog.model_dump(mode="json")),
        "prefect_yaml_sha256": canonical_json_sha256(rendered),
        "deployment_count": len(catalog.deployments),
        "deployments": [
            item.model_dump(mode="json")
            for item in sorted(catalog.deployments, key=lambda value: value.flow_id)
        ],
    }


def write_deployment_lock(root: Path | None = None) -> Path:
    resolved = (root or project_root()).resolve()
    target = resolved / "config/platform/generated/prefect_deployments.lock.json"
    target.write_text(
        json.dumps(deployment_lock_payload(resolved), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def deployment_lock_matches(root: Path | None = None) -> bool:
    resolved = (root or project_root()).resolve()
    path = resolved / "config/platform/generated/prefect_deployments.lock.json"
    if not path.is_file():
        return False
    return json.loads(path.read_text(encoding="utf-8")) == deployment_lock_payload(
        resolved
    )


def bootstrap_deployments(
    root: Path | None = None,
    *,
    validate_imports: bool = True,
) -> None:
    resolved = (root or project_root()).resolve()
    if validate_imports:
        report = validate_deployment_imports(resolved)
        if not report["passed"]:
            raise RuntimeError(
                "Prefect deployment import preflight failed: "
                + "; ".join(str(item) for item in report["errors"])
            )
    subprocess.run(
        ["prefect", "--no-prompt", "deploy", "--all"],
        cwd=resolved,
        check=True,
    )
