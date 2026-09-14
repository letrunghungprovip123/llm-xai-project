"""Validate metric formulas and their relational link to the base mart."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .config import (
    BASE_EXIT_GATE,
    DERIVED_METRIC_COLUMNS,
    EXPECTED_COUNTS,
    FINAL_EXIT_GATE,
    IDENTITY_COLUMNS,
    INVALID_EXIT_GATE,
    METRIC_ENGINEERING_VERSION,
    METRIC_EXIT_GATE,
    METRIC_VALIDATION_PATH,
    RATE_COLUMNS,
    SOURCE_COUNT_COLUMNS,
    SOURCE_RUNTIME_COLUMNS,
)


ValidationReport = dict[str, Any]


def _python_value(value: Any) -> Any:
    """Convert pandas and NumPy values into JSON-safe Python values."""

    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass

    if isinstance(value, dict):
        return {
            str(key): _python_value(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [_python_value(item) for item in value]

    return value


def _add_check(
    checks: dict[str, dict[str, Any]],
    name: str,
    expected: Any,
    observed: Any,
    passed: bool,
    details: str | None = None,
) -> None:
    check = {
        "expected": _python_value(expected),
        "observed": _python_value(observed),
        "passed": bool(passed),
    }

    if details:
        check["details"] = details

    checks[name] = check


def _expected_ratio(
    numerator: pd.Series,
    denominator: pd.Series,
    usable: pd.Series | None = None,
) -> pd.Series:
    """Recalculate a ratio independently for validation."""

    result = pd.Series(
        np.nan,
        index=numerator.index,
        dtype="float64",
    )
    valid_rows = denominator > 0

    if usable is not None:
        valid_rows = valid_rows & usable.astype(bool)

    result.loc[valid_rows] = (
        numerator.loc[valid_rows].astype(float)
        / denominator.loc[valid_rows].astype(float)
    )

    return result


def _series_mismatch_count(
    observed: pd.Series,
    expected: pd.Series,
    tolerance: float = 1e-12,
) -> int:
    """Count numeric or object mismatches while treating paired NaN as equal."""

    if pd.api.types.is_numeric_dtype(observed) and pd.api.types.is_numeric_dtype(
        expected
    ):
        equal_values = np.isclose(
            observed.astype(float),
            expected.astype(float),
            rtol=0.0,
            atol=tolerance,
            equal_nan=True,
        )
        return int((~equal_values).sum())

    paired_null = observed.isna() & expected.isna()
    equal_values = observed.eq(expected) | paired_null
    return int((~equal_values).sum())


def _formula_mismatch_count(
    metrics: pd.DataFrame,
    metric_column: str,
    expected: pd.Series,
) -> int:
    return _series_mismatch_count(
        metrics[metric_column],
        expected,
    )


def _identity_mismatch_count(
    generations: pd.DataFrame,
    metrics: pd.DataFrame,
) -> int:
    duplicate_count = int(
        metrics["generation_id"].duplicated(keep=False).sum()
    )
    if duplicate_count > 0:
        return duplicate_count

    source_columns = ["generation_id", *IDENTITY_COLUMNS[1:]]
    joined = metrics[source_columns].merge(
        generations[source_columns],
        on="generation_id",
        how="outer",
        validate="one_to_one",
        suffixes=("_metric", "_source"),
        indicator=True,
    )

    mismatch = joined["_merge"] != "both"

    for column in IDENTITY_COLUMNS[1:]:
        metric_column = f"{column}_metric"
        source_column = f"{column}_source"
        paired_null = (
            joined[metric_column].isna()
            & joined[source_column].isna()
        )
        mismatch = mismatch | ~(
            joined[metric_column].eq(joined[source_column])
            | paired_null
        )

    return int(mismatch.sum())


def _source_column_mismatch_count(
    generations: pd.DataFrame,
    metrics: pd.DataFrame,
    columns: list[str],
) -> int:
    duplicate_count = int(
        metrics["generation_id"].duplicated(keep=False).sum()
    )
    if duplicate_count > 0:
        return duplicate_count

    source = generations.set_index("generation_id")[columns]
    observed = metrics.set_index("generation_id")[columns]
    observed = observed.reindex(source.index)

    mismatch_count = 0
    for column in columns:
        mismatch_count += _series_mismatch_count(
            observed[column],
            source[column],
        )

    return mismatch_count


def _claim_status_counts(claims: pd.DataFrame) -> dict[str, int]:
    observed = {
        str(status): int(count)
        for status, count in claims["validation_status"]
        .value_counts()
        .sort_index()
        .items()
    }
    return {
        status: observed.get(status, 0)
        for status in (
            "SUPPORTED",
            "UNSUPPORTED",
            "CONTRADICTED",
            "NOT_VERIFIABLE",
            "NOT_APPLICABLE",
        )
    }


def validate_metric_outputs(
    outputs: dict[str, pd.DataFrame],
    input_data: dict[str, Any],
    expected_counts: dict[str, int] | None = None,
) -> ValidationReport:
    """Validate formulas, cohort preservation and dictionary coverage."""

    expected = EXPECTED_COUNTS if expected_counts is None else expected_counts
    generations = input_data["generations"]
    claims = input_data["claims"]
    data_mart_validation = input_data["data_mart_validation"]
    metrics = outputs["generation_metrics"]
    metric_dictionary = outputs["metric_dictionary"]

    checks: dict[str, dict[str, Any]] = {}

    base_gate_ready = (
        data_mart_validation.get("passed") is True
        and data_mart_validation.get("failed_check_count") == 0
        and data_mart_validation.get("exit_gate") == BASE_EXIT_GATE
    )
    _add_check(
        checks,
        "base_data_mart_gate",
        BASE_EXIT_GATE,
        data_mart_validation.get("exit_gate"),
        base_gate_ready,
    )

    _add_check(
        checks,
        "source_generation_count",
        expected["generations"],
        len(generations),
        len(generations) == expected["generations"],
    )
    _add_check(
        checks,
        "source_claim_count",
        expected["claims"],
        len(claims),
        len(claims) == expected["claims"],
    )
    _add_check(
        checks,
        "generation_metric_count",
        expected["generations"],
        len(metrics),
        len(metrics) == expected["generations"],
    )

    duplicate_generation_count = int(
        metrics.duplicated(
            subset=["generation_id"],
            keep=False,
        ).sum()
    )
    _add_check(
        checks,
        "duplicate_generation_metric_id_count",
        0,
        duplicate_generation_count,
        duplicate_generation_count == 0,
    )

    missing_metric_generation_count = len(
        set(generations["generation_id"])
        - set(metrics["generation_id"])
    )
    orphan_metric_generation_count = len(
        set(metrics["generation_id"])
        - set(generations["generation_id"])
    )
    _add_check(
        checks,
        "missing_generation_metric_count",
        0,
        missing_metric_generation_count,
        missing_metric_generation_count == 0,
    )
    _add_check(
        checks,
        "orphan_generation_metric_count",
        0,
        orphan_metric_generation_count,
        orphan_metric_generation_count == 0,
    )

    identity_mismatch_count = _identity_mismatch_count(
        generations,
        metrics,
    )
    _add_check(
        checks,
        "generation_metric_identity_mismatch_count",
        0,
        identity_mismatch_count,
        identity_mismatch_count == 0,
    )

    source_count_mismatch_count = _source_column_mismatch_count(
        generations,
        metrics,
        SOURCE_COUNT_COLUMNS,
    )
    _add_check(
        checks,
        "generation_metric_source_count_mismatch_count",
        0,
        source_count_mismatch_count,
        source_count_mismatch_count == 0,
    )

    source_runtime_mismatch_count = _source_column_mismatch_count(
        generations,
        metrics,
        SOURCE_RUNTIME_COLUMNS,
    )
    _add_check(
        checks,
        "generation_metric_source_runtime_mismatch_count",
        0,
        source_runtime_mismatch_count,
        source_runtime_mismatch_count == 0,
    )

    raw_partition_mismatch_count = int(
        (
            metrics["claim_count"]
            != (
                metrics["supported_count"]
                + metrics["unsupported_count"]
                + metrics["contradicted_count"]
                + metrics["not_verifiable_count"]
                + metrics["not_applicable_count"]
            )
        ).sum()
    )
    _add_check(
        checks,
        "claim_status_partition_mismatch_count",
        0,
        raw_partition_mismatch_count,
        raw_partition_mismatch_count == 0,
    )

    resolved_count_mismatch = int(
        (
            metrics["resolved_count"]
            != (
                metrics["supported_count"]
                + metrics["unsupported_count"]
                + metrics["contradicted_count"]
            )
        ).sum()
    )
    _add_check(
        checks,
        "resolved_count_formula_mismatch_count",
        0,
        resolved_count_mismatch,
        resolved_count_mismatch == 0,
    )

    applicable_count_mismatch = int(
        (
            metrics["applicable_count"]
            != (
                metrics["claim_count"]
                - metrics["not_applicable_count"]
            )
        ).sum()
    )
    _add_check(
        checks,
        "applicable_count_formula_mismatch_count",
        0,
        applicable_count_mismatch,
        applicable_count_mismatch == 0,
    )

    status_mapping = {
        "SUPPORTED": "supported_count",
        "UNSUPPORTED": "unsupported_count",
        "CONTRADICTED": "contradicted_count",
        "NOT_VERIFIABLE": "not_verifiable_count",
        "NOT_APPLICABLE": "not_applicable_count",
    }
    claim_status_counts = _claim_status_counts(claims)
    generation_status_counts = {
        status: int(metrics[column].sum())
        for status, column in status_mapping.items()
    }
    _add_check(
        checks,
        "claim_to_generation_status_reconciliation",
        claim_status_counts,
        generation_status_counts,
        claim_status_counts == generation_status_counts,
    )

    usable = metrics["usable"].astype(bool)
    applicable = metrics["applicable_count"]
    resolved = metrics["resolved_count"]
    supported = metrics["supported_count"]
    unsupported = metrics["unsupported_count"]
    contradicted = metrics["contradicted_count"]
    not_verifiable = metrics["not_verifiable_count"]

    expected_formulas = {
        "resolved_faithfulness": _expected_ratio(
            supported,
            resolved,
            usable,
        ),
        "verifiability": _expected_ratio(
            resolved,
            applicable,
            usable,
        ),
        "conservative_faithfulness": _expected_ratio(
            supported,
            applicable,
            usable,
        ),
        "not_verifiable_rate": _expected_ratio(
            not_verifiable,
            applicable,
            usable,
        ),
        "unsupported_rate": _expected_ratio(
            unsupported,
            applicable,
            usable,
        ),
        "contradiction_rate": _expected_ratio(
            contradicted,
            applicable,
            usable,
        ),
        "resolved_error_rate": _expected_ratio(
            unsupported + contradicted,
            resolved,
            usable,
        ),
    }

    for metric_name, expected_series in expected_formulas.items():
        mismatch_count = _formula_mismatch_count(
            metrics,
            metric_name,
            expected_series,
        )
        _add_check(
            checks,
            f"{metric_name}_formula_mismatch_count",
            0,
            mismatch_count,
            mismatch_count == 0,
        )

    expected_end_to_end = pd.Series(
        0.0,
        index=metrics.index,
        dtype="float64",
    )
    eligible_rows = usable & (applicable > 0)
    expected_end_to_end.loc[eligible_rows] = (
        supported.loc[eligible_rows].astype(float)
        / applicable.loc[eligible_rows].astype(float)
    )
    end_to_end_mismatch = _formula_mismatch_count(
        metrics,
        "end_to_end_faithfulness_yield",
        expected_end_to_end,
    )
    _add_check(
        checks,
        "end_to_end_faithfulness_yield_formula_mismatch_count",
        0,
        end_to_end_mismatch,
        end_to_end_mismatch == 0,
    )

    expected_eligible = usable & (applicable > 0)
    eligible_mismatch = _series_mismatch_count(
        metrics["quality_metric_eligible"],
        expected_eligible,
    )
    _add_check(
        checks,
        "quality_metric_eligible_formula_mismatch_count",
        0,
        eligible_mismatch,
        eligible_mismatch == 0,
    )

    expected_strict_supported = (
        usable
        & (applicable > 0)
        & (supported == applicable)
    )
    strict_supported_mismatch = _series_mismatch_count(
        metrics["is_strict_all_supported"],
        expected_strict_supported,
    )
    _add_check(
        checks,
        "strict_all_supported_formula_mismatch_count",
        0,
        strict_supported_mismatch,
        strict_supported_mismatch == 0,
    )

    expected_error_flag = (
        usable & ((unsupported + contradicted) > 0)
    )
    error_flag_mismatch = _series_mismatch_count(
        metrics["has_faithfulness_error"],
        expected_error_flag,
    )
    _add_check(
        checks,
        "faithfulness_error_flag_mismatch_count",
        0,
        error_flag_mismatch,
        error_flag_mismatch == 0,
    )

    relation_rows = (
        metrics["resolved_faithfulness"].notna()
        & metrics["verifiability"].notna()
        & metrics["conservative_faithfulness"].notna()
    )
    relation_expected = (
        metrics.loc[relation_rows, "resolved_faithfulness"]
        * metrics.loc[relation_rows, "verifiability"]
    )
    relation_mismatch_count = _series_mismatch_count(
        metrics.loc[relation_rows, "conservative_faithfulness"],
        relation_expected,
    )
    _add_check(
        checks,
        "conservative_identity_mismatch_count",
        0,
        relation_mismatch_count,
        relation_mismatch_count == 0,
        "conservative = resolved faithfulness × verifiability",
    )

    rate_out_of_bounds_count = 0
    for column in RATE_COLUMNS:
        non_null = metrics[column].dropna()
        rate_out_of_bounds_count += int(
            ((non_null < 0) | (non_null > 1)).sum()
        )
    _add_check(
        checks,
        "rate_out_of_bounds_count",
        0,
        rate_out_of_bounds_count,
        rate_out_of_bounds_count == 0,
    )

    numeric_values = metrics.select_dtypes(include=[np.number])
    infinite_value_count = int(
        np.isinf(numeric_values.to_numpy(dtype=float)).sum()
    )
    _add_check(
        checks,
        "infinite_metric_value_count",
        0,
        infinite_value_count,
        infinite_value_count == 0,
    )

    unusable_rows = ~usable
    unusable_count = int(unusable_rows.sum())
    _add_check(
        checks,
        "unusable_generation_count",
        expected["unusable_generations"],
        unusable_count,
        unusable_count == expected["unusable_generations"],
    )
    _add_check(
        checks,
        "usable_generation_count",
        expected["usable_generations"],
        int(usable.sum()),
        int(usable.sum()) == expected["usable_generations"],
    )

    unusable_nonzero_yield_count = int(
        (
            metrics.loc[
                unusable_rows,
                "end_to_end_faithfulness_yield",
            ]
            != 0
        ).sum()
    )
    _add_check(
        checks,
        "unusable_generation_nonzero_yield_count",
        0,
        unusable_nonzero_yield_count,
        unusable_nonzero_yield_count == 0,
    )

    nullable_quality_columns = [
        "resolved_faithfulness",
        "verifiability",
        "conservative_faithfulness",
        "not_verifiable_rate",
        "unsupported_rate",
        "contradiction_rate",
        "resolved_error_rate",
    ]
    unusable_nonnull_quality_count = int(
        metrics.loc[
            unusable_rows,
            nullable_quality_columns,
        ].notna().sum().sum()
    )
    _add_check(
        checks,
        "unusable_generation_nonnull_quality_metric_count",
        0,
        unusable_nonnull_quality_count,
        unusable_nonnull_quality_count == 0,
    )

    expected_parse_success = (
        metrics["raw_json_parse_success"].astype(bool)
        & metrics["json_parse_success"].astype(bool)
    )
    expected_strict_pipeline = (
        usable
        & (metrics["runtime_status"] == "SUCCESS")
        & ~metrics["truncated_response"].astype(bool)
        & expected_parse_success
        & metrics["schema_valid"].astype(bool)
        & (metrics["claim_count"] > 0)
    )
    reliability_expectations = {
        "is_unusable": ~usable,
        "is_truncated": metrics["truncated_response"].astype(bool),
        "is_parse_success": expected_parse_success,
        "is_schema_valid": metrics["schema_valid"].astype(bool),
        "is_first_attempt_success": usable & (metrics["retry_count"] == 0),
        "was_retried": metrics["retry_count"] > 0,
        "is_strict_pipeline_success": expected_strict_pipeline,
    }
    reliability_mismatch_count = 0
    for column, expected_series in reliability_expectations.items():
        reliability_mismatch_count += _series_mismatch_count(
            metrics[column],
            expected_series,
        )
    _add_check(
        checks,
        "reliability_formula_mismatch_count",
        0,
        reliability_mismatch_count,
        reliability_mismatch_count == 0,
    )

    expected_efficiency = {
        "latency_seconds": metrics["latency_ms"].astype(float) / 1000.0,
        "output_tokens_per_second": _expected_ratio(
            metrics["output_token_count"],
            metrics["latency_ms"].astype(float) / 1000.0,
        ),
        "claims_per_second": _expected_ratio(
            metrics["claim_count"],
            metrics["latency_ms"].astype(float) / 1000.0,
        ),
        "supported_claims_per_second": _expected_ratio(
            metrics["supported_count"],
            metrics["latency_ms"].astype(float) / 1000.0,
        ),
        "latency_per_supported_claim_seconds": _expected_ratio(
            metrics["latency_ms"].astype(float) / 1000.0,
            metrics["supported_count"],
        ),
        "claims_per_1000_total_tokens": _expected_ratio(
            metrics["claim_count"],
            metrics["total_token_count"],
        ) * 1000.0,
        "supported_claims_per_1000_total_tokens": _expected_ratio(
            metrics["supported_count"],
            metrics["total_token_count"],
        ) * 1000.0,
        "output_tokens_per_supported_claim": _expected_ratio(
            metrics["output_token_count"],
            metrics["supported_count"],
        ),
    }
    efficiency_mismatch_count = 0
    for column, expected_series in expected_efficiency.items():
        efficiency_mismatch_count += _formula_mismatch_count(
            metrics,
            column,
            expected_series,
        )
    _add_check(
        checks,
        "efficiency_formula_mismatch_count",
        0,
        efficiency_mismatch_count,
        efficiency_mismatch_count == 0,
    )

    negative_efficiency_count = 0
    efficiency_columns = list(expected_efficiency)
    for column in efficiency_columns:
        negative_efficiency_count += int(
            (metrics[column].dropna() < 0).sum()
        )
    _add_check(
        checks,
        "negative_efficiency_metric_count",
        0,
        negative_efficiency_count,
        negative_efficiency_count == 0,
    )

    model_count = metrics["model_id"].nunique()
    evidence_count = metrics["evidence_level"].nunique()
    cell_counts = (
        metrics.groupby(
            ["model_id", "evidence_level"],
            dropna=False,
        )
        .size()
        .to_dict()
    )
    invalid_cell_count = sum(
        count
        != expected[
            "generations_per_model_evidence_cell"
        ]
        for count in cell_counts.values()
    )
    _add_check(
        checks,
        "model_count",
        expected["models"],
        model_count,
        model_count == expected["models"],
    )
    _add_check(
        checks,
        "evidence_level_count",
        expected["evidence_levels"],
        evidence_count,
        evidence_count == expected["evidence_levels"],
    )
    _add_check(
        checks,
        "model_evidence_cell_count",
        expected["model_evidence_cells"],
        len(cell_counts),
        len(cell_counts) == expected["model_evidence_cells"],
    )
    _add_check(
        checks,
        "invalid_model_evidence_cell_size_count",
        0,
        invalid_cell_count,
        invalid_cell_count == 0,
    )

    dictionary_ids = metric_dictionary["metric_id"].tolist()
    dictionary_duplicates = sum(
        count - 1
        for count in Counter(dictionary_ids).values()
        if count > 1
    )
    missing_dictionary_metrics = sorted(
        set(DERIVED_METRIC_COLUMNS) - set(dictionary_ids)
    )
    extra_dictionary_metrics = sorted(
        set(dictionary_ids) - set(DERIVED_METRIC_COLUMNS)
    )
    _add_check(
        checks,
        "duplicate_metric_dictionary_id_count",
        0,
        dictionary_duplicates,
        dictionary_duplicates == 0,
    )
    _add_check(
        checks,
        "missing_metric_dictionary_entries",
        [],
        missing_dictionary_metrics,
        not missing_dictionary_metrics,
    )
    _add_check(
        checks,
        "extra_metric_dictionary_entries",
        [],
        extra_dictionary_metrics,
        not extra_dictionary_metrics,
    )

    critical_null_count = int(
        metrics[[
            "metric_engineering_version",
            *IDENTITY_COLUMNS,
        ]]
        .isna()
        .any(axis=1)
        .sum()
    )
    _add_check(
        checks,
        "critical_identity_null_row_count",
        0,
        critical_null_count,
        critical_null_count == 0,
    )

    observed_versions = sorted(
        metrics["metric_engineering_version"]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )
    _add_check(
        checks,
        "metric_engineering_version_set",
        [METRIC_ENGINEERING_VERSION],
        observed_versions,
        observed_versions == [METRIC_ENGINEERING_VERSION],
    )

    failed_check_count = sum(
        not check["passed"]
        for check in checks.values()
    )
    passed = failed_check_count == 0

    return {
        "metric_engineering_version": METRIC_ENGINEERING_VERSION,
        "base_gate": BASE_EXIT_GATE,
        "metric_gate": METRIC_EXIT_GATE if passed else INVALID_EXIT_GATE,
        "check_count": len(checks),
        "checks": checks,
        "failed_check_count": failed_check_count,
        "passed": passed,
        "exit_gate": FINAL_EXIT_GATE if passed else INVALID_EXIT_GATE,
    }


def write_validation_report(
    report: ValidationReport,
    output_path: Path = METRIC_VALIDATION_PATH,
) -> None:
    """Write the metric validation gate as formatted JSON."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def print_validation_summary(report: ValidationReport) -> None:
    """Print a compact phase summary for terminal use."""

    print("Metric engineering validation")
    print(
        f"- Checks: {report['check_count']}"
    )
    print(
        f"- Failed: {report['failed_check_count']}"
    )
    print(
        f"- Exit gate: {report['exit_gate']}"
    )
