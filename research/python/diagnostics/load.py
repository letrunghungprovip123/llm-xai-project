"""Load approved Data Mart and Statistical Core inputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .config import (
    CASES_PATH,
    CLAIMS_PATH,
    DATA_MART_GATE,
    DATA_MART_VALIDATION_PATH,
    EVIDENCE_ITEMS_PATH,
    EVIDENCE_LEVELS_PATH,
    EVIDENCE_PACKAGES_PATH,
    GENERATION_METRICS_PATH,
    GENERATIONS_PATH,
    METRIC_GATE,
    METRIC_VALIDATION_PATH,
    MODELS_PATH,
    REQUIRED_CASE_COLUMNS,
    REQUIRED_CLAIM_COLUMNS,
    REQUIRED_EVIDENCE_LEVEL_COLUMNS,
    REQUIRED_GENERATION_COLUMNS,
    REQUIRED_ITEM_COLUMNS,
    REQUIRED_METRIC_COLUMNS,
    REQUIRED_MODEL_COLUMNS,
    REQUIRED_PACKAGE_COLUMNS,
    STATISTICAL_GATE,
    STATISTICAL_VALIDATION_PATH,
)


LoadedInputs = dict[str, Any]


def require_file(file_path: Path) -> None:
    """Require one input file and show its full path on failure."""

    if not file_path.is_file():
        raise FileNotFoundError(
            f"Required diagnostics input does not exist: {file_path}"
        )


def read_json_file(file_path: Path) -> dict[str, Any]:
    """Read one JSON object from disk."""

    require_file(file_path)

    try:
        value = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Invalid JSON in {file_path}: {error}"
        ) from error

    if not isinstance(value, dict):
        raise ValueError(f"Expected one JSON object in {file_path}.")

    return value


def read_csv_file(file_path: Path) -> pd.DataFrame:
    """Read one CSV without applying implicit schema transformations."""

    require_file(file_path)
    return pd.read_csv(file_path, low_memory=False)


def require_columns(
    dataframe: pd.DataFrame,
    required_columns: set[str],
    table_name: str,
) -> None:
    """Require the columns used by this diagnostics batch."""

    missing_columns = sorted(
        required_columns - set(dataframe.columns)
    )

    if missing_columns:
        raise ValueError(
            f"{table_name} is missing required columns: "
            f"{missing_columns}"
        )


def require_gate(
    report: dict[str, Any],
    expected_gate: str,
    report_name: str,
) -> None:
    """Stop when an upstream batch was not approved."""

    passed = report.get("passed") is True
    failed_check_count = report.get("failed_check_count")
    observed_gate = report.get("exit_gate")

    if (
        not passed
        or failed_check_count != 0
        or observed_gate != expected_gate
    ):
        raise ValueError(
            f"Diagnostics requires {report_name} to pass with gate "
            f"{expected_gate}. Observed passed={passed}, "
            f"failed_check_count={failed_check_count}, "
            f"exit_gate={observed_gate}."
        )


def load_diagnostic_inputs(
    input_paths: dict[str, Path] | None = None,
) -> LoadedInputs:
    """Load approved relational inputs used by diagnostics.

    ``input_paths=None`` preserves the historical Home Credit path contract.
    Multi-dataset callers must provide every required path explicitly.
    """

    paths = {
        "data_mart_validation": DATA_MART_VALIDATION_PATH,
        "metric_validation": METRIC_VALIDATION_PATH,
        "statistical_validation": STATISTICAL_VALIDATION_PATH,
        "claims": CLAIMS_PATH,
        "generations": GENERATIONS_PATH,
        "generation_metrics": GENERATION_METRICS_PATH,
        "cases": CASES_PATH,
        "models": MODELS_PATH,
        "evidence_levels": EVIDENCE_LEVELS_PATH,
        "evidence_packages": EVIDENCE_PACKAGES_PATH,
        "evidence_items": EVIDENCE_ITEMS_PATH,
    } if input_paths is None else input_paths
    required_path_keys = {
        "data_mart_validation", "metric_validation", "statistical_validation",
        "claims", "generations", "generation_metrics", "cases", "models",
        "evidence_levels", "evidence_packages", "evidence_items",
    }
    missing_path_keys = sorted(required_path_keys - set(paths))
    if missing_path_keys:
        raise ValueError(
            "Diagnostics input path mapping is incomplete: "
            f"{missing_path_keys}"
        )

    data_mart_validation = read_json_file(paths["data_mart_validation"])
    metric_validation = read_json_file(paths["metric_validation"])
    statistical_validation = read_json_file(paths["statistical_validation"])

    require_gate(
        data_mart_validation,
        DATA_MART_GATE,
        "Data Mart",
    )
    require_gate(
        metric_validation,
        METRIC_GATE,
        "Metric Engineering",
    )
    require_gate(
        statistical_validation,
        STATISTICAL_GATE,
        "Statistical Analysis Core",
    )

    claims = read_csv_file(paths["claims"])
    generations = read_csv_file(paths["generations"])
    generation_metrics = read_csv_file(paths["generation_metrics"])
    cases = read_csv_file(paths["cases"])
    models = read_csv_file(paths["models"])
    evidence_levels = read_csv_file(paths["evidence_levels"])
    evidence_packages = read_csv_file(paths["evidence_packages"])
    evidence_items = read_csv_file(paths["evidence_items"])

    require_columns(claims, REQUIRED_CLAIM_COLUMNS, "claims.csv")
    require_columns(
        generations,
        REQUIRED_GENERATION_COLUMNS,
        "generations.csv",
    )
    require_columns(
        generation_metrics,
        REQUIRED_METRIC_COLUMNS,
        "generation_metrics.csv",
    )
    require_columns(cases, REQUIRED_CASE_COLUMNS, "cases.csv")
    require_columns(models, REQUIRED_MODEL_COLUMNS, "models.csv")
    require_columns(
        evidence_levels,
        REQUIRED_EVIDENCE_LEVEL_COLUMNS,
        "evidence_levels.csv",
    )
    require_columns(
        evidence_packages,
        REQUIRED_PACKAGE_COLUMNS,
        "evidence_packages.csv",
    )
    require_columns(
        evidence_items,
        REQUIRED_ITEM_COLUMNS,
        "evidence_items.csv",
    )

    return {
        "data_mart_validation": data_mart_validation,
        "metric_validation": metric_validation,
        "statistical_validation": statistical_validation,
        "claims": claims,
        "generations": generations,
        "generation_metrics": generation_metrics,
        "cases": cases,
        "models": models,
        "evidence_levels": evidence_levels,
        "evidence_packages": evidence_packages,
        "evidence_items": evidence_items,
    }
