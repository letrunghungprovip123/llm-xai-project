"""Fail-closed verification for the immutable visualization-data-v2 release."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from research.python.common.hashing import sha256_file

from ..settings import (
    ANALYTICAL_RELEASE_ID,
    EXPECTED_VISUALIZATION_CHECK_COUNT,
    EXPECTED_VISUALIZATION_DATASET_COUNT,
    OVERVIEW_REQUIRED_DATASETS,
    REQUIRED_GATES,
    PROJECT_ROOT,
    VISUALIZATION_MANIFEST_PATH,
    VISUALIZATION_RELEASE_ID,
    VISUALIZATION_VALIDATION_PATH,
    VISUALIZATION_VERSION,
)
from .contracts import (
    DatasetContract,
    GateStatus,
    ReleaseGuardResult,
    ReleaseMetadata,
)
from .loaders import DashboardDataError, read_csv_frame, read_json_object


def _dataset_contracts(
    manifest: dict[str, Any],
    *,
    project_root: Path,
) -> tuple[dict[str, DatasetContract], list[str]]:
    errors: list[str] = []
    contracts: dict[str, DatasetContract] = {}
    artifacts = manifest.get("output_artifacts")
    if not isinstance(artifacts, list):
        return {}, ["visualization_manifest.output_artifacts must be a list"]

    for index, item in enumerate(artifacts, start=1):
        if not isinstance(item, dict):
            errors.append(f"Artifact #{index} is not an object")
            continue
        try:
            name = str(item["dataset_name"])
            relative_path = str(item["path"])
            row_count = int(item["row_count"])
            column_count = int(item["column_count"])
            expected_hash = str(item["sha256"])
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"Artifact #{index} has an invalid contract: {exc}")
            continue
        if name in contracts:
            errors.append(f"Duplicate dataset contract: {name}")
            continue
        path = project_root / relative_path
        contracts[name] = DatasetContract(
            name=name,
            path=path,
            row_count=row_count,
            column_count=column_count,
            sha256=expected_hash,
        )
    return contracts, errors


def _verify_dataset(contract: DatasetContract) -> list[str]:
    errors: list[str] = []
    if not contract.path.is_file():
        return [f"Missing certified dataset: {contract.name}: {contract.path}"]
    observed_hash = sha256_file(contract.path)
    if observed_hash != contract.sha256:
        errors.append(
            f"Hash mismatch for {contract.name}: expected {contract.sha256}, "
            f"observed {observed_hash}"
        )
    frame = read_csv_frame(contract.path)
    if len(frame) != contract.row_count:
        errors.append(
            f"Row-count mismatch for {contract.name}: expected "
            f"{contract.row_count}, observed {len(frame)}"
        )
    if len(frame.columns) != contract.column_count:
        errors.append(
            f"Column-count mismatch for {contract.name}: expected "
            f"{contract.column_count}, observed {len(frame.columns)}"
        )
    return errors


def verify_visualization_release(
    *,
    project_root: Path,
    manifest_path: Path = VISUALIZATION_MANIFEST_PATH,
    validation_path: Path = VISUALIZATION_VALIDATION_PATH,
    verify_all_datasets: bool = True,
) -> ReleaseGuardResult:
    """Verify release gates, artifact hashes, schemas and Page-1 inputs."""

    errors: list[str] = []
    try:
        manifest = read_json_object(manifest_path)
        validation = read_json_object(validation_path)
    except DashboardDataError as exc:
        return ReleaseGuardResult(
            ready=False,
            release=None,
            datasets={},
            errors=(str(exc),),
            validation_payload={},
            manifest_payload={},
        )

    if manifest.get("schema_version") != "visualization_manifest_v2":
        errors.append("Unexpected visualization manifest schema")
    if manifest.get("visualization_version") != VISUALIZATION_VERSION:
        errors.append("Visualization version does not match dashboard contract")
    if manifest.get("parent_analytical_gate") != REQUIRED_GATES[0]:
        errors.append("Parent report release gate is not REPORT_WRITING_READY")
    if manifest.get("baseline_gate") != REQUIRED_GATES[1]:
        errors.append("Template Baseline gate is not BASELINE_COMPARISON_READY")

    if validation.get("passed") is not True:
        errors.append("Visualization validation did not pass")
    if validation.get("failed_check_count") != 0:
        errors.append("Visualization validation contains failed checks")
    if validation.get("exit_gate") != REQUIRED_GATES[2]:
        errors.append("Visualization gate is not VISUALIZATION_DATA_V2_READY")
    if validation.get("check_count") != EXPECTED_VISUALIZATION_CHECK_COUNT:
        errors.append(
            "Visualization validation check count differs from the frozen "
            f"contract ({EXPECTED_VISUALIZATION_CHECK_COUNT})"
        )
    if validation.get("research_question_count") != 6:
        errors.append("Visualization release must expose exactly six RQs")
    if validation.get("template_is_fourth_llm") is not False:
        errors.append("Template must not be represented as a fourth LLM")

    contracts, contract_errors = _dataset_contracts(
        manifest,
        project_root=project_root,
    )
    errors.extend(contract_errors)
    if len(contracts) != EXPECTED_VISUALIZATION_DATASET_COUNT:
        errors.append(
            "Visualization dataset count differs from the frozen contract: "
            f"expected {EXPECTED_VISUALIZATION_DATASET_COUNT}, "
            f"observed {len(contracts)}"
        )

    missing_overview = sorted(set(OVERVIEW_REQUIRED_DATASETS) - set(contracts))
    if missing_overview:
        errors.append(f"Overview datasets missing from manifest: {missing_overview}")

    names_to_verify = set(contracts) if verify_all_datasets else set(OVERVIEW_REQUIRED_DATASETS)
    for name in sorted(names_to_verify):
        contract = contracts.get(name)
        if contract is None:
            continue
        try:
            errors.extend(_verify_dataset(contract))
        except DashboardDataError as exc:
            errors.append(str(exc))

    release: ReleaseMetadata | None = None
    release_contract = contracts.get("release_metadata")
    if release_contract is not None and release_contract.path.is_file():
        try:
            release_frame = read_csv_frame(release_contract.path)
            if len(release_frame) != 1:
                errors.append("release_metadata must contain exactly one row")
            else:
                row = release_frame.iloc[0]
                if str(row.get("parent_analytical_release")) != ANALYTICAL_RELEASE_ID:
                    errors.append("Parent analytical release ID does not match")
                gates = (
                    GateStatus(
                        gate_id=REQUIRED_GATES[0],
                        passed=str(row.get("parent_analytical_gate")) == REQUIRED_GATES[0],
                        detail="Certified thesis analytical release",
                    ),
                    GateStatus(
                        gate_id=REQUIRED_GATES[1],
                        passed=str(row.get("baseline_gate")) == REQUIRED_GATES[1],
                        detail="216 deterministic Template reference runs",
                    ),
                    GateStatus(
                        gate_id=REQUIRED_GATES[2],
                        passed=validation.get("exit_gate") == REQUIRED_GATES[2],
                        detail=(
                            f"{len(contracts)} datasets · "
                            f"{validation.get('check_count')} checks"
                        ),
                    ),
                )
                if not all(item.passed for item in gates):
                    errors.append("One or more dashboard release gates are not ready")
                release = ReleaseMetadata(
                    analytical_release_id=ANALYTICAL_RELEASE_ID,
                    visualization_release_id=VISUALIZATION_RELEASE_ID,
                    visualization_version=str(row.get("visualization_version")),
                    parent_release_id=str(row.get("parent_release_id")),
                    parent_git_commit=str(row.get("parent_git_commit")),
                    parent_git_branch=str(row.get("parent_git_branch")),
                    parent_source_tree_sha256=str(
                        row.get("parent_source_tree_sha256")
                    ),
                    research_question_count=int(row.get("research_question_count")),
                    dataset_count=len(contracts),
                    validation_check_count=int(validation.get("check_count", 0)),
                    gates=gates,
                )
        except (DashboardDataError, TypeError, ValueError) as exc:
            errors.append(f"Invalid release metadata: {exc}")

    return ReleaseGuardResult(
        ready=not errors and release is not None,
        release=release,
        datasets=contracts,
        errors=tuple(errors),
        validation_payload=validation,
        manifest_payload=manifest,
    )


@lru_cache(maxsize=1)
def get_visualization_release_guard() -> ReleaseGuardResult:
    """Verify the frozen visualization release once per app process."""

    return verify_visualization_release(project_root=PROJECT_ROOT)
