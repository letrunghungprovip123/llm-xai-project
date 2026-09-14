"""Đánh giá hard constraints, chuẩn hóa và tính utility theo scenario."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .config import DECISION_VERSION, FLOAT_TOLERANCE, SCENARIOS


def build_scenario_definitions() -> pd.DataFrame:
    """Xuất toàn bộ giả định scenario thành bảng audit được."""

    rows: list[dict[str, object]] = []
    for scenario_order, scenario in enumerate(SCENARIOS):
        rule_order = 0
        for constraint in scenario["constraints"]:
            rows.append(
                {
                    "decision_version": DECISION_VERSION,
                    "scenario_order": scenario_order,
                    "scenario_id": scenario["scenario_id"],
                    "scenario_label": scenario["scenario_label"],
                    "scenario_description": scenario[
                        "scenario_description"
                    ],
                    "rule_type": "HARD_CONSTRAINT",
                    "criterion_id": constraint["criterion_id"],
                    "direction": "RANGE",
                    "weight": np.nan,
                    "minimum_value": constraint["minimum_value"],
                    "maximum_value": constraint["maximum_value"],
                    "normalization_method": None,
                    "criterion_order": rule_order,
                }
            )
            rule_order += 1

        for criterion_id, direction, weight in scenario["objectives"]:
            rows.append(
                {
                    "decision_version": DECISION_VERSION,
                    "scenario_order": scenario_order,
                    "scenario_id": scenario["scenario_id"],
                    "scenario_label": scenario["scenario_label"],
                    "scenario_description": scenario[
                        "scenario_description"
                    ],
                    "rule_type": "WEIGHTED_OBJECTIVE",
                    "criterion_id": criterion_id,
                    "direction": direction,
                    "weight": weight,
                    "minimum_value": np.nan,
                    "maximum_value": np.nan,
                    "normalization_method": "MIN_MAX_ELIGIBLE",
                    "criterion_order": rule_order,
                }
            )
            rule_order += 1

    return pd.DataFrame(rows).sort_values(
        ["scenario_order", "criterion_order"],
        kind="stable",
    ).reset_index(drop=True)


def constraint_passes(
    value: object,
    minimum_value: object,
    maximum_value: object,
) -> bool:
    """Một constraint null luôn fail thay vì tự điền zero."""

    if value is None or pd.isna(value):
        return False

    numeric_value = float(value)
    if minimum_value is not None and not pd.isna(minimum_value):
        if numeric_value + FLOAT_TOLERANCE < float(minimum_value):
            return False
    if maximum_value is not None and not pd.isna(maximum_value):
        if numeric_value - FLOAT_TOLERANCE > float(maximum_value):
            return False
    return True


def normalize_value(
    value: float,
    minimum: float,
    maximum: float,
    direction: str,
) -> float:
    """Chuẩn hóa benefit/cost criteria trong eligible option set."""

    if np.isclose(maximum, minimum, rtol=0.0, atol=FLOAT_TOLERANCE):
        return 1.0

    if direction == "MAX":
        normalized = (value - minimum) / (maximum - minimum)
    elif direction == "MIN":
        normalized = (maximum - value) / (maximum - minimum)
    else:
        raise ValueError(f"Unknown objective direction: {direction}")

    return float(np.clip(normalized, 0.0, 1.0))


def evaluate_constraints(
    options: pd.DataFrame,
    scenario_rules: pd.DataFrame,
) -> pd.DataFrame:
    """Giữ đủ 18 options và ghi rõ constraint nào bị fail."""

    constraints = scenario_rules.loc[
        scenario_rules["rule_type"] == "HARD_CONSTRAINT"
    ]
    rows: list[dict[str, object]] = []

    for option in options.itertuples(index=False):
        failed: list[str] = []
        for rule in constraints.itertuples(index=False):
            value = getattr(option, rule.criterion_id)
            if not constraint_passes(
                value,
                rule.minimum_value,
                rule.maximum_value,
            ):
                failed.append(str(rule.criterion_id))

        rows.append(
            {
                "option_id": option.option_id,
                "eligible": len(failed) == 0,
                "failed_constraint_count": len(failed),
                "failed_constraint_ids": json.dumps(
                    failed,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            }
        )

    return pd.DataFrame(rows)


def score_one_scenario(
    options: pd.DataFrame,
    scenario_rules: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Tính criterion rows và một ranking-base row cho mỗi option."""

    scenario_id = str(scenario_rules.iloc[0]["scenario_id"])
    scenario_order = int(scenario_rules.iloc[0]["scenario_order"])
    objective_rules = scenario_rules.loc[
        scenario_rules["rule_type"] == "WEIGHTED_OBJECTIVE"
    ].sort_values("criterion_order", kind="stable")

    state = evaluate_constraints(options, scenario_rules)
    option_state = options.merge(
        state,
        on="option_id",
        how="left",
        validate="one_to_one",
    )

    objective_ids = objective_rules["criterion_id"].tolist()
    option_state["score_available"] = (
        option_state[objective_ids].notna().all(axis=1)
        & option_state["eligible"]
    )

    scorable = option_state.loc[option_state["score_available"]]
    criterion_rows: list[dict[str, object]] = []

    for rule in objective_rules.itertuples(index=False):
        criterion_id = str(rule.criterion_id)
        direction = str(rule.direction)
        weight = float(rule.weight)
        scorable_values = pd.to_numeric(
            scorable[criterion_id],
            errors="coerce",
        )
        minimum = (
            float(scorable_values.min())
            if not scorable_values.empty
            else float("nan")
        )
        maximum = (
            float(scorable_values.max())
            if not scorable_values.empty
            else float("nan")
        )

        for option in option_state.itertuples(index=False):
            raw_value = getattr(option, criterion_id)
            can_score = bool(option.score_available) and not pd.isna(raw_value)
            normalized = (
                normalize_value(
                    float(raw_value),
                    minimum,
                    maximum,
                    direction,
                )
                if can_score
                else float("nan")
            )
            contribution = (
                normalized * weight if can_score else float("nan")
            )

            criterion_rows.append(
                {
                    "scenario_order": scenario_order,
                    "scenario_id": scenario_id,
                    "option_id": option.option_id,
                    "criterion_id": criterion_id,
                    "direction": direction,
                    "weight": weight,
                    "raw_value": raw_value,
                    "eligible": bool(option.eligible),
                    "score_available": bool(option.score_available),
                    "normalization_minimum": minimum,
                    "normalization_maximum": maximum,
                    "normalized_value": normalized,
                    "weighted_contribution": contribution,
                }
            )

    criterion_scores = pd.DataFrame(criterion_rows)
    utilities = (
        criterion_scores.loc[criterion_scores["score_available"]]
        .groupby("option_id", sort=False)["weighted_contribution"]
        .sum()
        .rename("utility_score")
        .reset_index()
    )

    ranking_base = option_state.merge(
        utilities,
        on="option_id",
        how="left",
        validate="one_to_one",
    )
    ranking_base.insert(0, "scenario_id", scenario_id)
    ranking_base.insert(0, "scenario_order", scenario_order)
    return criterion_scores, ranking_base


def build_scenario_scores(
    options: pd.DataFrame,
    scenario_definitions: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Tính scores cho đủ năm scenarios × 18 options."""

    criterion_frames: list[pd.DataFrame] = []
    ranking_frames: list[pd.DataFrame] = []

    for scenario_id, rules in scenario_definitions.groupby(
        "scenario_id",
        sort=False,
    ):
        del scenario_id
        criterion_scores, ranking_base = score_one_scenario(options, rules)
        criterion_frames.append(criterion_scores)
        ranking_frames.append(ranking_base)

    return (
        pd.concat(criterion_frames, ignore_index=True),
        pd.concat(ranking_frames, ignore_index=True),
    )
