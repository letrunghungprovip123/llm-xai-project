"""Validate table grains, joins and cohort reconciliation."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from .config import (
    EXPECTED_COUNTS,
    EXPECTED_STRATUM_COUNTS,
    EXPECTED_VALIDATION_STATUS_COUNTS,
    CLAIM_MEASUREMENT_RELEASE,
    VALIDATION_FILE_NAME,
)
from .case_metadata import extract_case_metadata
from .load import InputData


ValidationReport = dict[str, Any]


def _python_value(value: Any) -> Any:
    """Convert pandas and NumPy scalar values into JSON-safe Python values."""

    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass

    if isinstance(value, dict):
        return {str(key): _python_value(item) for key, item in value.items()}

    if isinstance(value, (list, tuple)):
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


def _duplicate_count(dataframe: pd.DataFrame, columns: list[str]) -> int:
    return int(dataframe.duplicated(subset=columns, keep=False).sum())


def _null_count(dataframe: pd.DataFrame, columns: list[str]) -> int:
    existing_columns = [column for column in columns if column in dataframe]
    return int(dataframe[existing_columns].isna().any(axis=1).sum())


def _package_case_consistency_issue_count(
    input_data: InputData,
) -> int:
    rows: list[dict[str, Any]] = []

    for package in input_data["evidence_packages"]:
        metadata = package.get("internal_metadata") or {}
        case_metadata = extract_case_metadata(package)
        ground_truth = metadata.get("ground_truth") or {}
        prediction = package.get("prediction") or {}

        rows.append(
            {
                "case_id": case_metadata.case_id,
                "selection_stratum": case_metadata.selection_stratum,
                "selection_rank": case_metadata.selection_rank,
                "true_label": ground_truth.get("true_label"),
                "predicted_class": prediction.get("predicted_class"),
                "probability": prediction.get("probability"),
                "threshold": prediction.get("threshold"),
            }
        )

    packages = pd.DataFrame(rows)
    fields = [
        "selection_stratum",
        "selection_rank",
        "true_label",
        "predicted_class",
        "probability",
        "threshold",
    ]
    issue_count = 0

    for field in fields:
        inconsistent_cases = (
            packages.groupby("case_id")[field].nunique(dropna=False) > 1
        )
        issue_count += int(inconsistent_cases.sum())

    return issue_count


def _generation_summary_mismatch_count(
    generations: pd.DataFrame,
    input_data: InputData,
) -> int:
    official = pd.DataFrame(input_data["generation_summaries"])
    official = official[
        [
            "generation_id",
            "usable",
            "total_claims",
            "supported_count",
            "unsupported_count",
            "contradicted_count",
            "not_verifiable_count",
            "not_applicable_count",
        ]
    ].copy()
    official_count_columns = [
        "total_claims",
        "supported_count",
        "unsupported_count",
        "contradicted_count",
        "not_verifiable_count",
        "not_applicable_count",
    ]
    official[official_count_columns] = (
        official[official_count_columns].fillna(0).astype(int)
    )
    official = official.rename(
        columns={
            "usable": "official_usable",
            "total_claims": "official_claim_count",
            "supported_count": "official_supported_count",
            "unsupported_count": "official_unsupported_count",
            "contradicted_count": "official_contradicted_count",
            "not_verifiable_count": "official_not_verifiable_count",
            "not_applicable_count": "official_not_applicable_count",
        }
    )

    generated = generations[
        [
            "generation_id",
            "usable",
            "claim_count",
            "supported_count",
            "unsupported_count",
            "contradicted_count",
            "not_verifiable_count",
            "not_applicable_count",
        ]
    ]

    comparison = generated.merge(
        official,
        on="generation_id",
        how="outer",
        validate="one_to_one",
        indicator=True,
    )

    mismatch = comparison["_merge"].ne("both")
    compared_columns = [
        ("usable", "official_usable"),
        ("claim_count", "official_claim_count"),
        ("supported_count", "official_supported_count"),
        ("unsupported_count", "official_unsupported_count"),
        ("contradicted_count", "official_contradicted_count"),
        ("not_verifiable_count", "official_not_verifiable_count"),
        ("not_applicable_count", "official_not_applicable_count"),
    ]

    for generated_column, official_column in compared_columns:
        mismatch |= comparison[generated_column].ne(
            comparison[official_column]
        )

    return int(mismatch.sum())


def _claim_generation_identity_mismatch_count(
    claims: pd.DataFrame,
    generations: pd.DataFrame,
) -> int:
    generation_identity = generations[
        [
            "generation_id",
            "case_id",
            "model_id",
            "evidence_level",
            "repeat_id",
        ]
    ].rename(
        columns={
            "case_id": "parent_case_id",
            "model_id": "parent_model_id",
            "evidence_level": "parent_evidence_level",
            "repeat_id": "parent_repeat_id",
        }
    )

    joined = claims[
        [
            "claim_id",
            "generation_id",
            "case_id",
            "model_id",
            "evidence_level",
            "repeat_id",
        ]
    ].merge(
        generation_identity,
        on="generation_id",
        how="left",
        validate="many_to_one",
        indicator=True,
    )

    mismatch = joined["_merge"].ne("both")
    mismatch |= joined["case_id"].astype(str).ne(
        joined["parent_case_id"].astype(str)
    )
    mismatch |= joined["model_id"].ne(joined["parent_model_id"])
    mismatch |= joined["evidence_level"].ne(
        joined["parent_evidence_level"]
    )
    mismatch |= joined["repeat_id"].ne(joined["parent_repeat_id"])

    return int(mismatch.sum())


def _claim_validation_identity_mismatch_count(claims: pd.DataFrame) -> int:
    mismatch = claims["validation_match_status"].ne("both")
    mismatch |= claims["generation_id"].ne(
        claims["validation_generation_id"]
    )
    mismatch |= claims["case_id"].astype(str).ne(
        claims["validation_case_id"].astype(str)
    )
    mismatch |= claims["model_id"].ne(claims["validation_model_id"])
    mismatch |= claims["evidence_level"].ne(
        claims["validation_evidence_level"]
    )
    mismatch |= claims["repeat_id"].ne(claims["validation_repeat_id"])

    return int(mismatch.sum())


def validate_data_mart(
    tables: dict[str, pd.DataFrame],
    input_data: InputData,
    expected_counts: dict[str, int] | None = None,
    expected_status_counts: dict[str, int] | None = None,
    expected_stratum_counts: dict[str, int] | None = None,
    release_context: dict[str, Any] | None = None,
) -> ValidationReport:
    """Run the complete data mart acceptance checks."""

    expected = EXPECTED_COUNTS if expected_counts is None else expected_counts
    expected_statuses = (
        EXPECTED_VALIDATION_STATUS_COUNTS
        if expected_status_counts is None
        else expected_status_counts
    )
    expected_strata = (
        EXPECTED_STRATUM_COUNTS
        if expected_stratum_counts is None
        else expected_stratum_counts
    )

    cases = tables["cases"]
    models = tables["models"]
    evidence_levels = tables["evidence_levels"]
    evidence_packages = tables["evidence_packages"]
    evidence_items = tables["evidence_items"]
    generations = tables["generations"]
    claims = tables["claims"]
    validations_raw = pd.DataFrame(input_data["validation_results"])
    summaries_raw = pd.DataFrame(input_data["generation_summaries"])

    checks: dict[str, dict[str, Any]] = {}

    active_release = (
        CLAIM_MEASUREMENT_RELEASE
        if release_context is None
        else release_context
    )
    release_status = active_release.get("release_status")
    allowed_release_statuses = set(
        active_release.get(
            "allowed_release_statuses",
            ["READY", "READY_WITH_LIMITATIONS"],
        )
    )
    _add_check(
        checks,
        "claim_measurement_release_status",
        sorted(allowed_release_statuses),
        release_status,
        release_status in allowed_release_statuses,
    )
    expected_primary_condition = active_release.get(
        "expected_primary_condition",
        "candidate",
    )
    observed_primary_condition = active_release.get(
        "decision", {}
    ).get("primary_condition")
    _add_check(
        checks,
        "single_primary_claim_release",
        expected_primary_condition,
        observed_primary_condition,
        observed_primary_condition == expected_primary_condition,
    )

    input_count_map = {
        "input_evidence_package_count": (
            expected["evidence_packages"],
            len(input_data["evidence_packages"]),
        ),
        "input_generation_count": (
            expected["generations"],
            len(input_data["generation_index"]),
        ),
        "input_claim_count": (
            expected["claims"],
            len(input_data["final_claims"]),
        ),
        "input_validation_result_count": (
            expected["validation_results"],
            len(input_data["validation_results"]),
        ),
        "input_generation_summary_count": (
            expected["generation_summaries"],
            len(input_data["generation_summaries"]),
        ),
    }
    for name, (expected_value, observed_value) in input_count_map.items():
        _add_check(
            checks,
            name,
            expected_value,
            observed_value,
            expected_value == observed_value,
        )

    table_count_map = {
        "case_count": (expected["cases"], len(cases)),
        "model_count": (expected["models"], len(models)),
        "evidence_level_count": (
            expected["evidence_levels"],
            len(evidence_levels),
        ),
        "evidence_package_count": (
            expected["evidence_packages"],
            len(evidence_packages),
        ),
        "generation_count": (expected["generations"], len(generations)),
        "usable_generation_count": (
            expected["usable_generations"],
            int(generations["usable"].eq(True).sum()),
        ),
        "unusable_generation_count": (
            expected["unusable_generations"],
            int(generations["usable"].eq(False).sum()),
        ),
        "claim_count": (expected["claims"], len(claims)),
    }
    for name, (expected_value, observed_value) in table_count_map.items():
        _add_check(
            checks,
            name,
            expected_value,
            observed_value,
            expected_value == observed_value,
        )

    unique_key_checks = {
        "duplicate_case_id_count": _duplicate_count(cases, ["case_id"]),
        "duplicate_model_id_count": _duplicate_count(models, ["model_id"]),
        "duplicate_evidence_level_count": _duplicate_count(
            evidence_levels,
            ["evidence_level"],
        ),
        "duplicate_evidence_package_id_count": _duplicate_count(
            evidence_packages,
            ["package_id"],
        ),
        "duplicate_case_evidence_package_count": _duplicate_count(
            evidence_packages,
            ["case_id", "evidence_level"],
        ),
        "duplicate_evidence_item_id_count": _duplicate_count(
            evidence_items,
            ["evidence_item_id"],
        ),
        "duplicate_generation_id_count": _duplicate_count(
            generations,
            ["generation_id"],
        ),
        "duplicate_generation_matrix_key_count": _duplicate_count(
            generations,
            ["case_id", "model_id", "evidence_level", "repeat_id"],
        ),
        "duplicate_claim_id_count": _duplicate_count(claims, ["claim_id"]),
        "duplicate_validation_id_count": _duplicate_count(
            validations_raw,
            ["validation_id"],
        ),
        "duplicate_generation_summary_id_count": _duplicate_count(
            summaries_raw,
            ["generation_id"],
        ),
    }
    for name, observed_value in unique_key_checks.items():
        _add_check(checks, name, 0, observed_value, observed_value == 0)

    critical_null_checks = {
        "case_critical_null_row_count": _null_count(
            cases,
            ["case_id", "selection_stratum", "true_label", "predicted_class"],
        ),
        "evidence_package_critical_null_row_count": _null_count(
            evidence_packages,
            ["package_id", "case_id", "evidence_level"],
        ),
        "generation_critical_null_row_count": _null_count(
            generations,
            ["generation_id", "case_id", "model_id", "evidence_level"],
        ),
        "claim_critical_null_row_count": _null_count(
            claims,
            ["claim_id", "generation_id", "validation_status"],
        ),
    }
    for name, observed_value in critical_null_checks.items():
        _add_check(checks, name, 0, observed_value, observed_value == 0)

    observed_strata = {
        str(key): int(value)
        for key, value in cases["selection_stratum"].value_counts().items()
    }
    _add_check(
        checks,
        "stratum_balance",
        expected_strata,
        observed_strata,
        observed_strata == expected_strata,
    )

    expected_levels = [f"S{index}" for index in range(6)]
    observed_levels = sorted(
        evidence_levels["evidence_level"].astype(str).tolist()
    )
    _add_check(
        checks,
        "evidence_level_set",
        expected_levels,
        observed_levels,
        observed_levels == expected_levels,
    )

    package_level_counts = (
        evidence_packages.groupby("case_id")["evidence_level"].nunique()
    )
    invalid_case_package_count = int(package_level_counts.ne(6).sum())
    _add_check(
        checks,
        "cases_without_complete_s0_s5_packages",
        0,
        invalid_case_package_count,
        invalid_case_package_count == 0,
    )

    package_consistency_issues = _package_case_consistency_issue_count(
        input_data
    )
    _add_check(
        checks,
        "inconsistent_case_metadata_across_packages",
        0,
        package_consistency_issues,
        package_consistency_issues == 0,
    )

    expected_matrix = {
        f"{model_id}::{evidence_level}": expected["cases"]
        for model_id in sorted(models["model_id"].astype(str))
        for evidence_level in expected_levels
    }
    observed_matrix_series = generations.groupby(
        ["model_id", "evidence_level"]
    ).size()
    observed_matrix = {
        f"{model_id}::{evidence_level}": int(count)
        for (model_id, evidence_level), count in observed_matrix_series.items()
    }
    _add_check(
        checks,
        "generation_model_evidence_matrix",
        expected_matrix,
        observed_matrix,
        observed_matrix == expected_matrix,
    )

    join_status_checks = {
        "generation_case_orphan_count": int(
            generations["case_join_status"].ne("both").sum()
        ),
        "generation_model_orphan_count": int(
            generations["model_join_status"].ne("both").sum()
        ),
        "generation_evidence_level_orphan_count": int(
            generations["evidence_level_join_status"].ne("both").sum()
        ),
        "generation_package_orphan_count": int(
            generations["package_join_status"].ne("both").sum()
        ),
        "evidence_item_package_orphan_count": int(
            (~evidence_items["package_id"].isin(evidence_packages["package_id"])).sum()
        ),
    }
    for name, observed_value in join_status_checks.items():
        _add_check(checks, name, 0, observed_value, observed_value == 0)

    package_identity_mismatch = (
        generations["case_id"].astype(str).ne(
            generations["package_case_id"].astype(str)
        )
        | generations["evidence_level"].ne(
            generations["package_evidence_level"]
        )
    )
    package_identity_mismatch_count = int(package_identity_mismatch.sum())
    _add_check(
        checks,
        "generation_package_identity_mismatch_count",
        0,
        package_identity_mismatch_count,
        package_identity_mismatch_count == 0,
    )

    claim_validation_identity_mismatch = (
        _claim_validation_identity_mismatch_count(claims)
    )
    _add_check(
        checks,
        "claim_validation_identity_mismatch_count",
        0,
        claim_validation_identity_mismatch,
        claim_validation_identity_mismatch == 0,
    )

    final_claim_ids = {str(record["claim_id"]) for record in input_data["final_claims"]}
    validation_claim_ids = {
        str(record["claim_id"]) for record in input_data["validation_results"]
    }
    orphan_validation_count = len(validation_claim_ids - final_claim_ids)
    missing_validation_count = len(final_claim_ids - validation_claim_ids)
    _add_check(
        checks,
        "orphan_validation_count",
        0,
        orphan_validation_count,
        orphan_validation_count == 0,
    )
    _add_check(
        checks,
        "missing_validation_count",
        0,
        missing_validation_count,
        missing_validation_count == 0,
    )

    claim_generation_identity_mismatch = (
        _claim_generation_identity_mismatch_count(claims, generations)
    )
    _add_check(
        checks,
        "claim_generation_identity_mismatch_count",
        0,
        claim_generation_identity_mismatch,
        claim_generation_identity_mismatch == 0,
    )

    unusable_generation_ids = set(
        generations.loc[generations["usable"].eq(False), "generation_id"]
    )
    claims_on_unusable = int(
        claims["generation_id"].isin(unusable_generation_ids).sum()
    )
    _add_check(
        checks,
        "claims_on_unusable_generations",
        0,
        claims_on_unusable,
        claims_on_unusable == 0,
    )

    usable_without_claims = int(
        (generations["usable"].eq(True) & generations["claim_count"].eq(0)).sum()
    )
    unusable_with_claims = int(
        (generations["usable"].eq(False) & generations["claim_count"].gt(0)).sum()
    )
    _add_check(
        checks,
        "usable_generations_without_claims",
        0,
        usable_without_claims,
        usable_without_claims == 0,
    )
    _add_check(
        checks,
        "unusable_generations_with_claims",
        0,
        unusable_with_claims,
        unusable_with_claims == 0,
    )

    aggregate_claim_count = int(generations["claim_count"].sum())
    _add_check(
        checks,
        "generation_claim_count_reconciliation",
        len(claims),
        aggregate_claim_count,
        aggregate_claim_count == len(claims),
    )

    status_counts = {
        str(key): int(value)
        for key, value in claims["validation_status"].value_counts().items()
    }
    _add_check(
        checks,
        "validation_status_counts",
        expected_statuses,
        status_counts,
        status_counts == expected_statuses,
    )

    status_partition_count = sum(
        int(generations[column].sum())
        for column in (
            "supported_count",
            "unsupported_count",
            "contradicted_count",
            "not_verifiable_count",
            "not_applicable_count",
        )
    )
    _add_check(
        checks,
        "validation_status_partition_reconciliation",
        len(claims),
        status_partition_count,
        status_partition_count == len(claims),
    )

    execution_error_count = int(
        claims["execution_status"].ne("SUCCESS").sum()
    )
    _add_check(
        checks,
        "claim_validation_execution_error_count",
        0,
        execution_error_count,
        execution_error_count == 0,
    )

    summary_mismatch_count = _generation_summary_mismatch_count(
        generations,
        input_data,
    )
    _add_check(
        checks,
        "generation_summary_mismatch_count",
        0,
        summary_mismatch_count,
        summary_mismatch_count == 0,
    )

    failed_check_count = sum(
        not check["passed"] for check in checks.values()
    )
    passed = failed_check_count == 0

    return {
        "data_mart_version": "1.1",
        "claim_measurement_release_id": active_release["release_id"],
        "claim_measurement_release_status": active_release["release_status"],
        "interpretation_scope": active_release["interpretation_scope"],
        "checks": checks,
        "check_count": len(checks),
        "failed_check_count": failed_check_count,
        "passed": passed,
        "exit_gate": "DATA_MART_READY" if passed else "DATA_MART_INVALID",
    }


def write_validation_report(
    report: ValidationReport,
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / VALIDATION_FILE_NAME

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(
            report,
            file,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        file.write("\n")


def print_validation_summary(report: ValidationReport) -> None:
    print("Data mart validation")
    print(f"- Checks: {report['check_count']}")
    print(f"- Failed: {report['failed_check_count']}")
    print(f"- Exit gate: {report['exit_gate']}")
