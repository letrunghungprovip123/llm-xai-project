"""Đọc các upstream outputs đã được phê duyệt."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .config import (
    CLAIM_MECHANISM_SUMMARY_PATH,
    DIAGNOSTIC_GATE,
    DIAGNOSTIC_VALIDATION_PATH,
    EVIDENCE_LEVELS_PATH,
    GENERATION_DIAGNOSTICS_PATH,
    GENERATION_MECHANISM_SUMMARY_PATH,
    GENERATION_METRICS_PATH,
    METRIC_GATE,
    METRIC_VALIDATION_PATH,
    MODELS_PATH,
    PAIRED_TESTS_PATH,
    REQUIRED_CLAIM_SUMMARY_COLUMNS,
    REQUIRED_DIAGNOSTIC_VERSION,
    REQUIRED_EVIDENCE_COLUMNS,
    REQUIRED_GENERATION_DIAGNOSTIC_COLUMNS,
    REQUIRED_GENERATION_METRIC_COLUMNS,
    REQUIRED_GENERATION_SUMMARY_COLUMNS,
    REQUIRED_MODEL_COLUMNS,
    REQUIRED_PAIRED_TEST_COLUMNS,
    STATISTICAL_GATE,
    STATISTICAL_VALIDATION_PATH,
)


LoadedInputs = dict[str, Any]


def require_file(file_path: Path) -> None:
    """Dừng sớm và báo đúng file còn thiếu."""

    if not file_path.is_file():
        raise FileNotFoundError(
            f"Required decision-support input does not exist: {file_path}"
        )


def read_json(file_path: Path) -> dict[str, Any]:
    """Đọc một JSON object có kiểm tra cấu trúc tối thiểu."""

    require_file(file_path)
    try:
        value = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid JSON in {file_path}: {error}") from error

    if not isinstance(value, dict):
        raise ValueError(f"Expected one JSON object in {file_path}.")
    return value


def read_csv(file_path: Path) -> pd.DataFrame:
    """Đọc CSV nhưng không tự thay đổi schema nguồn."""

    require_file(file_path)
    return pd.read_csv(file_path, low_memory=False)


def require_columns(
    dataframe: pd.DataFrame,
    required_columns: set[str],
    table_name: str,
) -> None:
    """Chỉ yêu cầu các cột phase này thật sự sử dụng."""

    missing = sorted(required_columns - set(dataframe.columns))
    if missing:
        raise ValueError(f"{table_name} is missing required columns: {missing}")


def gate_is_ready(report: dict[str, Any], expected_gate: str) -> bool:
    """Một upstream gate chỉ hợp lệ khi pass và không còn failed check."""

    return (
        report.get("passed") is True
        and report.get("failed_check_count") == 0
        and report.get("exit_gate") == expected_gate
    )


def require_upstream_gates(
    metric_report: dict[str, Any],
    statistical_report: dict[str, Any],
    diagnostic_report: dict[str, Any],
) -> None:
    """Bảo đảm ba upstream phases đã được phê duyệt."""

    gates = [
        ("Metric Engineering", metric_report, METRIC_GATE),
        ("Statistical Analysis", statistical_report, STATISTICAL_GATE),
        ("Diagnostics", diagnostic_report, DIAGNOSTIC_GATE),
    ]
    for label, report, expected_gate in gates:
        if not gate_is_ready(report, expected_gate):
            raise ValueError(
                f"{label} gate is not ready. Expected {expected_gate}, "
                f"observed passed={report.get('passed')}, "
                f"failed_check_count={report.get('failed_check_count')}, "
                f"exit_gate={report.get('exit_gate')}."
            )

    observed_version = diagnostic_report.get("diagnostic_version")
    if observed_version != REQUIRED_DIAGNOSTIC_VERSION:
        raise ValueError(
            "Decision Support requires hardened Diagnostics "
            f"{REQUIRED_DIAGNOSTIC_VERSION}; observed {observed_version}."
        )


def load_decision_inputs() -> LoadedInputs:
    """Đọc toàn bộ input cần thiết cho 18 decision options."""

    metric_validation = read_json(METRIC_VALIDATION_PATH)
    statistical_validation = read_json(STATISTICAL_VALIDATION_PATH)
    diagnostic_validation = read_json(DIAGNOSTIC_VALIDATION_PATH)
    require_upstream_gates(
        metric_validation,
        statistical_validation,
        diagnostic_validation,
    )

    generation_diagnostics = read_csv(GENERATION_DIAGNOSTICS_PATH)
    generation_metrics = read_csv(GENERATION_METRICS_PATH)
    claim_summary = read_csv(CLAIM_MECHANISM_SUMMARY_PATH)
    generation_summary = read_csv(GENERATION_MECHANISM_SUMMARY_PATH)
    paired_tests = read_csv(PAIRED_TESTS_PATH)
    models = read_csv(MODELS_PATH)
    evidence_levels = read_csv(EVIDENCE_LEVELS_PATH)

    require_columns(
        generation_diagnostics,
        REQUIRED_GENERATION_DIAGNOSTIC_COLUMNS,
        "generation_diagnostics.csv",
    )
    require_columns(
        generation_metrics,
        REQUIRED_GENERATION_METRIC_COLUMNS,
        "generation_metrics.csv",
    )
    require_columns(
        claim_summary,
        REQUIRED_CLAIM_SUMMARY_COLUMNS,
        "claim_mechanism_summary.csv",
    )
    require_columns(
        generation_summary,
        REQUIRED_GENERATION_SUMMARY_COLUMNS,
        "generation_mechanism_summary.csv",
    )
    require_columns(models, REQUIRED_MODEL_COLUMNS, "models.csv")
    require_columns(
        evidence_levels,
        REQUIRED_EVIDENCE_COLUMNS,
        "evidence_levels.csv",
    )
    require_columns(
        paired_tests,
        REQUIRED_PAIRED_TEST_COLUMNS,
        "paired_tests.csv",
    )

    return {
        "metric_validation": metric_validation,
        "statistical_validation": statistical_validation,
        "diagnostic_validation": diagnostic_validation,
        "generation_diagnostics": generation_diagnostics,
        "generation_metrics": generation_metrics,
        "claim_mechanism_summary": claim_summary,
        "generation_mechanism_summary": generation_summary,
        "paired_tests": paired_tests,
        "models": models,
        "evidence_levels": evidence_levels,
    }
