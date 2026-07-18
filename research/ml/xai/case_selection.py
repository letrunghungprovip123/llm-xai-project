from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .config import (
    DEFAULT_THRESHOLD_FALLBACK,
    ID_COLUMN,
    RUN_MODE_EVALUATION,
    RUN_MODE_INFERENCE,
    XAI_CONFIG,
    XAI_SELECTED_CASES_CSV_PATH,
    get_case_groups_for_mode,
    mode_has_ground_truth,
    validate_run_mode,
)
from .loaders import (
    XAIInputs,
    find_prediction_label_column,
)


GROUND_TRUTH_CASE_TYPES = {
    "true_positive",
    "false_positive",
    "false_negative",
}

SUPPORTED_CASE_TYPES = {
    "top_high_risk",
    "low_risk",
    "true_positive",
    "false_positive",
    "false_negative",
    "near_threshold",
}


@dataclass(frozen=True)
class SelectedCasesResult:
    selected_cases: pd.DataFrame
    group_counts: dict[str, int]
    warnings: list[str]
    run_mode: str
    has_ground_truth: bool


def case_type_requires_ground_truth(case_type: str) -> bool:
    return case_type in GROUND_TRUTH_CASE_TYPES


def validate_case_groups_for_mode(
    *,
    case_groups: tuple[str, ...],
    run_mode: str,
    has_ground_truth: bool,
) -> None:
    unsupported = [
        case_type
        for case_type in case_groups
        if case_type not in SUPPORTED_CASE_TYPES
    ]

    if unsupported:
        raise ValueError(
            f"Unsupported case groups: {unsupported}. "
            f"Supported case groups are: {sorted(SUPPORTED_CASE_TYPES)}"
        )

    ground_truth_groups = [
        case_type
        for case_type in case_groups
        if case_type_requires_ground_truth(case_type)
    ]

    if ground_truth_groups and not has_ground_truth:
        raise ValueError(
            "These case groups require y_true/ground truth, but current "
            f"run_mode={run_mode!r} has no ground truth: {ground_truth_groups}"
        )


def get_effective_threshold(
    inputs: XAIInputs,
    predictions: pd.DataFrame,
) -> float:
    threshold_candidates = [
        "threshold",
        "decision_threshold",
        "default_threshold",
    ]

    for column in threshold_candidates:
        if column in predictions.columns:
            values = predictions[column].dropna().unique()

            if len(values) == 1:
                return float(values[0])

    return float(
        getattr(
            inputs.model_bundle,
            "default_threshold",
            DEFAULT_THRESHOLD_FALLBACK,
        )
    )


def build_evidence_id(
    *,
    model_name: str,
    model_version: str,
    sk_id_curr: int,
    case_type: str,
) -> str:
    safe_case_type = str(case_type).replace(" ", "_").lower()

    return (
        f"xai_{model_name}_{model_version}_{int(sk_id_curr)}_{safe_case_type}"
    )


def prepare_predictions_for_selection(inputs: XAIInputs) -> pd.DataFrame:
    predictions = inputs.predictions.copy()

    label_column = find_prediction_label_column(predictions)

    if label_column != "y_pred":
        predictions["y_pred"] = predictions[label_column]

    required_columns = [
        ID_COLUMN,
        "row_index",
        "y_proba",
        "y_pred",
    ]

    missing = [
        column for column in required_columns
        if column not in predictions.columns
    ]

    if missing:
        raise ValueError(
            f"Predictions are missing columns required for case selection: {missing}"
        )

    predictions[ID_COLUMN] = predictions[ID_COLUMN].astype(int)
    predictions["row_index"] = predictions["row_index"].astype(int)
    predictions["y_proba"] = predictions["y_proba"].astype(float)
    predictions["y_pred"] = predictions["y_pred"].astype(int)

    if inputs.has_ground_truth:
        if "y_true" not in predictions.columns:
            raise ValueError(
                "Evaluation mode requires y_true in predictions."
            )

        predictions["y_true"] = predictions["y_true"].astype(int)

    else:
        if "y_true" not in predictions.columns:
            predictions["y_true"] = pd.NA

    threshold = get_effective_threshold(inputs, predictions)

    predictions["threshold"] = float(threshold)
    predictions["abs_distance_to_threshold"] = (
        predictions["y_proba"] - float(threshold)
    ).abs()

    return predictions


def take_unique_cases(
    *,
    candidates: pd.DataFrame,
    case_type: str,
    cases_per_group: int,
    selected_ids: set[int],
) -> pd.DataFrame:
    rows = []

    for _, row in candidates.iterrows():
        sk_id_curr = int(row[ID_COLUMN])

        if sk_id_curr in selected_ids:
            continue

        selected_ids.add(sk_id_curr)

        row_dict = row.to_dict()
        row_dict["case_type"] = case_type
        row_dict["selection_rank"] = len(rows) + 1

        rows.append(row_dict)

        if len(rows) >= cases_per_group:
            break

    if not rows:
        return pd.DataFrame(columns=list(candidates.columns) + ["case_type", "selection_rank"])

    return pd.DataFrame(rows)


def get_case_candidates(
    *,
    predictions: pd.DataFrame,
    case_type: str,
    has_ground_truth: bool,
) -> pd.DataFrame:
    if case_type_requires_ground_truth(case_type) and not has_ground_truth:
        raise ValueError(
            f"case_type={case_type!r} requires y_true, but ground truth is unavailable."
        )

    if case_type == "top_high_risk":
        return predictions.sort_values(
            by=["y_proba", ID_COLUMN],
            ascending=[False, True],
        )

    if case_type == "low_risk":
        return predictions.sort_values(
            by=["y_proba", ID_COLUMN],
            ascending=[True, True],
        )

    if case_type == "near_threshold":
        return predictions.sort_values(
            by=["abs_distance_to_threshold", ID_COLUMN],
            ascending=[True, True],
        )

    if case_type == "true_positive":
        candidates = predictions[
            (predictions["y_true"] == 1)
            & (predictions["y_pred"] == 1)
        ]

        return candidates.sort_values(
            by=["y_proba", ID_COLUMN],
            ascending=[False, True],
        )

    if case_type == "false_positive":
        candidates = predictions[
            (predictions["y_true"] == 0)
            & (predictions["y_pred"] == 1)
        ]

        return candidates.sort_values(
            by=["y_proba", ID_COLUMN],
            ascending=[False, True],
        )

    if case_type == "false_negative":
        candidates = predictions[
            (predictions["y_true"] == 1)
            & (predictions["y_pred"] == 0)
        ]

        return candidates.sort_values(
            by=["y_proba", ID_COLUMN],
            ascending=[False, True],
        )

    raise ValueError(f"Unsupported case_type: {case_type}")


def validate_selected_cases(
    *,
    selected_cases: pd.DataFrame,
    inputs: XAIInputs,
    case_groups: tuple[str, ...],
) -> None:
    if selected_cases.empty:
        raise ValueError("No XAI cases were selected.")

    required_columns = [
        "evidence_id",
        ID_COLUMN,
        "row_index",
        "case_type",
        "selection_rank",
        "y_proba",
        "y_pred",
        "threshold",
        "abs_distance_to_threshold",
        "model_name",
        "model_version",
        "model_family",
        "dataset_branch",
        "feature_count",
    ]

    if inputs.has_ground_truth:
        required_columns.append("y_true")

    missing = [
        column for column in required_columns
        if column not in selected_cases.columns
    ]

    if missing:
        raise ValueError(
            f"Selected cases are missing required columns: {missing}"
        )

    if selected_cases["evidence_id"].duplicated().any():
        duplicated = selected_cases.loc[
            selected_cases["evidence_id"].duplicated(),
            "evidence_id",
        ].tolist()

        raise ValueError(f"Duplicate evidence_id values found: {duplicated}")

    if selected_cases[ID_COLUMN].duplicated().any():
        duplicated = selected_cases.loc[
            selected_cases[ID_COLUMN].duplicated(),
            ID_COLUMN,
        ].tolist()

        raise ValueError(f"Duplicate selected {ID_COLUMN} values found: {duplicated}")

    if selected_cases["row_index"].min() < 0:
        raise ValueError("Selected cases contain negative row_index values.")

    if selected_cases["row_index"].max() >= len(inputs.X):
        raise ValueError(
            "Selected cases contain row_index outside X row range."
        )

    if not selected_cases["y_proba"].between(0, 1).all():
        raise ValueError("Selected cases y_proba values must be in [0, 1].")

    invalid_case_types = sorted(
        set(selected_cases["case_type"]) - set(case_groups)
    )

    if invalid_case_types:
        raise ValueError(
            f"Selected cases contain invalid case types for current mode: {invalid_case_types}"
        )

    if inputs.has_ground_truth:
        invalid_y_true_values = sorted(
            set(selected_cases["y_true"].dropna().astype(int)) - {0, 1}
        )

        if invalid_y_true_values:
            raise ValueError(
                f"Selected cases contain invalid y_true values: {invalid_y_true_values}"
            )


def select_representative_cases(
    inputs: XAIInputs,
    *,
    cases_per_group: int | None = None,
    case_groups: tuple[str, ...] | None = None,
    run_mode: str | None = None,
) -> SelectedCasesResult:
    if run_mode is None:
        run_mode = inputs.run_mode

    run_mode = validate_run_mode(run_mode)
    has_ground_truth = mode_has_ground_truth(run_mode)

    if has_ground_truth != inputs.has_ground_truth:
        raise ValueError(
            "run_mode ground-truth setting does not match loaded inputs. "
            f"run_mode={run_mode!r}, mode_has_ground_truth={has_ground_truth}, "
            f"inputs.has_ground_truth={inputs.has_ground_truth}"
        )

    if cases_per_group is None:
        cases_per_group = XAI_CONFIG.cases_per_group

    if case_groups is None:
        case_groups = get_case_groups_for_mode(run_mode)

    validate_case_groups_for_mode(
        case_groups=case_groups,
        run_mode=run_mode,
        has_ground_truth=has_ground_truth,
    )

    predictions = prepare_predictions_for_selection(inputs)

    selected_parts = []
    selected_ids: set[int] = set()
    warnings: list[str] = []
    group_counts: dict[str, int] = {}

    for case_type in case_groups:
        candidates = get_case_candidates(
            predictions=predictions,
            case_type=case_type,
            has_ground_truth=has_ground_truth,
        )

        selected = take_unique_cases(
            candidates=candidates,
            case_type=case_type,
            cases_per_group=cases_per_group,
            selected_ids=selected_ids,
        )

        selected_count = int(len(selected))
        group_counts[case_type] = selected_count

        if selected_count < cases_per_group:
            warnings.append(
                f"Case group {case_type!r} selected only {selected_count} "
                f"of requested {cases_per_group} cases."
            )

        if selected_count > 0:
            selected_parts.append(selected)

    if not selected_parts:
        raise ValueError("No representative cases were selected.")

    selected_cases = pd.concat(
        selected_parts,
        ignore_index=True,
    )

    selected_cases["model_name"] = inputs.model_bundle.model_name
    selected_cases["model_version"] = inputs.model_bundle.model_version
    selected_cases["model_family"] = inputs.model_bundle.model_family
    selected_cases["dataset_branch"] = inputs.model_bundle.dataset_branch
    selected_cases["feature_count"] = inputs.model_bundle.feature_count
    selected_cases["run_mode"] = run_mode
    selected_cases["has_ground_truth"] = bool(has_ground_truth)

    selected_cases["evidence_id"] = selected_cases.apply(
        lambda row: build_evidence_id(
            model_name=inputs.model_bundle.model_name,
            model_version=inputs.model_bundle.model_version,
            sk_id_curr=int(row[ID_COLUMN]),
            case_type=str(row["case_type"]),
        ),
        axis=1,
    )

    output_columns = [
        "evidence_id",
        ID_COLUMN,
        "row_index",
        "case_type",
        "selection_rank",
        "y_true",
        "y_proba",
        "y_pred",
        "threshold",
        "abs_distance_to_threshold",
        "model_name",
        "model_version",
        "model_family",
        "dataset_branch",
        "feature_count",
        "run_mode",
        "has_ground_truth",
    ]

    selected_cases = selected_cases[
        [
            column
            for column in output_columns
            if column in selected_cases.columns
        ]
    ]

    validate_selected_cases(
        selected_cases=selected_cases,
        inputs=inputs,
        case_groups=case_groups,
    )

    return SelectedCasesResult(
        selected_cases=selected_cases,
        group_counts=group_counts,
        warnings=warnings,
        run_mode=run_mode,
        has_ground_truth=has_ground_truth,
    )


def save_selected_cases(
    result: SelectedCasesResult,
    path: Path = XAI_SELECTED_CASES_CSV_PATH,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    result.selected_cases.to_csv(path, index=False)
    return path


def summarize_selected_cases(
    result: SelectedCasesResult,
) -> dict[str, Any]:
    selected_cases = result.selected_cases

    return {
        "run_mode": result.run_mode,
        "has_ground_truth": result.has_ground_truth,
        "total_selected_cases": int(len(selected_cases)),
        "group_counts": result.group_counts,
        "warnings": result.warnings,
        "case_type_order": selected_cases["case_type"].tolist(),
        "first_5_evidence_ids": selected_cases["evidence_id"].head(5).tolist(),
        "y_proba_min": float(selected_cases["y_proba"].min()),
        "y_proba_max": float(selected_cases["y_proba"].max()),
        "y_proba_mean": float(selected_cases["y_proba"].mean()),
    }


__all__ = [
    "GROUND_TRUTH_CASE_TYPES",
    "SUPPORTED_CASE_TYPES",
    "SelectedCasesResult",
    "case_type_requires_ground_truth",
    "validate_case_groups_for_mode",
    "get_effective_threshold",
    "build_evidence_id",
    "prepare_predictions_for_selection",
    "take_unique_cases",
    "get_case_candidates",
    "validate_selected_cases",
    "select_representative_cases",
    "save_selected_cases",
    "summarize_selected_cases",
]