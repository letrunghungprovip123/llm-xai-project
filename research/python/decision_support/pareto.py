"""Tính Pareto frontier trực tiếp trên 18 options của từng scenario."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .config import FLOAT_TOLERANCE


def option_dominates(
    option_a: pd.Series,
    option_b: pd.Series,
    objective_rules: pd.DataFrame,
) -> bool:
    """A dominates B khi không tệ hơn mọi criterion và tốt hơn ít nhất một."""

    never_worse = True
    strictly_better = False

    for rule in objective_rules.itertuples(index=False):
        criterion_id = str(rule.criterion_id)
        a_value = float(option_a[criterion_id])
        b_value = float(option_b[criterion_id])

        if rule.direction == "MAX":
            if a_value + FLOAT_TOLERANCE < b_value:
                never_worse = False
                break
            if a_value > b_value + FLOAT_TOLERANCE:
                strictly_better = True
        elif rule.direction == "MIN":
            if a_value - FLOAT_TOLERANCE > b_value:
                never_worse = False
                break
            if a_value + FLOAT_TOLERANCE < b_value:
                strictly_better = True
        else:
            raise ValueError(f"Unknown Pareto direction: {rule.direction}")

    return never_worse and strictly_better


def build_pareto_frontier(
    ranking_base: pd.DataFrame,
    scenario_definitions: pd.DataFrame,
) -> pd.DataFrame:
    """Giữ đủ 90 rows, kể cả ineligible options."""

    rows: list[dict[str, object]] = []

    for scenario_id, group in ranking_base.groupby(
        "scenario_id",
        sort=False,
    ):
        objectives = scenario_definitions.loc[
            (scenario_definitions["scenario_id"] == scenario_id)
            & (scenario_definitions["rule_type"] == "WEIGHTED_OBJECTIVE")
        ]
        scorable = group.loc[
            group["eligible"].astype(bool)
            & group["score_available"].astype(bool)
        ]

        for _, option in group.iterrows():
            dominated_by: list[str] = []
            dominates: list[str] = []

            if bool(option["eligible"]) and bool(option["score_available"]):
                for _, other in scorable.iterrows():
                    if other["option_id"] == option["option_id"]:
                        continue
                    if option_dominates(other, option, objectives):
                        dominated_by.append(str(other["option_id"]))
                    if option_dominates(option, other, objectives):
                        dominates.append(str(other["option_id"]))

            rows.append(
                {
                    "scenario_order": int(option["scenario_order"]),
                    "scenario_id": scenario_id,
                    "option_id": option["option_id"],
                    "eligible": bool(option["eligible"]),
                    "score_available": bool(option["score_available"]),
                    "is_pareto_optimal": (
                        bool(option["eligible"])
                        and bool(option["score_available"])
                        and len(dominated_by) == 0
                    ),
                    "dominated_by_count": len(dominated_by),
                    "dominates_count": len(dominates),
                    "dominated_by_option_ids": json.dumps(
                        sorted(dominated_by),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                }
            )

    return pd.DataFrame(rows)
