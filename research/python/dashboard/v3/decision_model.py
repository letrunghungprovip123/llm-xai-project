from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs

import pandas as pd

from research.python.dashboard.i18n import format_percent, normalize_locale

from .effectiveness_model import DATASET_ID_TO_SCOPE, DATASET_LABELS, MODEL_LABELS
from .i18n import vt
from .repository import DashboardRepositoryV3


SCENARIO_ORDER = (
    "QUALITY_FIRST",
    "RELIABILITY_FIRST",
    "BALANCED",
    "EFFICIENCY_AWARE",
    "INDEPENDENCE_SENSITIVE",
)
_VALID_TABS = {"certified", "tradeoffs", "scenarios"}
_VALID_EVIDENCE = {f"S{i}" for i in range(6)}


@dataclass(frozen=True)
class DecisionModelV3:
    scope: str
    locale: str
    title: str
    options: tuple[dict[str, Any], ...]
    recommendations: tuple[dict[str, Any], ...]
    dataset_recommendations: tuple[dict[str, Any], ...]
    ni_rows: tuple[dict[str, Any], ...]
    scenarios: tuple[dict[str, Any], ...]
    primary_margin: float
    robust_status: str | None
    decision_counts: dict[str, int]
    limitations: tuple[dict[str, Any], ...]
    initial_tab: str = "certified"
    focus_model: str | None = None
    focus_evidence: str | None = None
    focus_dataset: str | None = None
    focus_option: str | None = None
    focus_scenario: str = "BALANCED"


def _dataset_id(repo: DashboardRepositoryV3, scope: str) -> str:
    row = repo.study_table("study_summary", scope)
    if len(row) != 1:
        raise ValueError(f"Expected one study summary for {scope}")
    return str(row.iloc[0]["dataset_id"])


def _parse_focus(search: str | None) -> tuple[str, str | None, str | None, str | None, str | None, str]:
    raw = parse_qs((search or "").lstrip("?"))
    tab = str((raw.get("tab") or ["certified"])[0])
    if tab not in _VALID_TABS:
        tab = "certified"
    model = str((raw.get("model") or [""])[0]) or None
    evidence = str((raw.get("evidence") or [""])[0]) or None
    dataset = str((raw.get("dataset") or [""])[0]) or None
    option = str((raw.get("option") or [""])[0]) or None
    scenario = str((raw.get("scenario") or ["BALANCED"])[0])
    if model not in MODEL_LABELS:
        model = None
    if evidence not in _VALID_EVIDENCE:
        evidence = None
    if dataset not in {"HOME_CREDIT", "FREDDIE"}:
        dataset = None
    if option and "::" not in option:
        option = None
    if scenario not in SCENARIO_ORDER:
        scenario = "BALANCED"
    return tab, model, evidence, dataset, option, scenario


def _project_assessment_rows(repo: DashboardRepositoryV3, scope: str, locale: str) -> tuple[dict[str, Any], ...]:
    frame = repo.table("decision_option_assessment")
    if len(frame) != 18:
        raise ValueError(f"Expected 18 certified decision assessment rows, found {len(frame)}")

    rows: list[dict[str, Any]] = []
    for row in frame.sort_values(["evidence_order", "model_id"], kind="stable").to_dict(orient="records"):
        item = dict(row)
        item["dataset_scope"] = scope
        item["model_label"] = MODEL_LABELS.get(str(row["model_id"]), str(row["model_id"]))
        item["evidence_label"] = str(row["evidence_level"])
        if scope == "HOME_CREDIT":
            prefix = "home_credit"
            item.update(
                dataset_id=row[f"{prefix}_dataset_id"],
                dataset_label=DATASET_LABELS[scope],
                mean_e2e=row[f"{prefix}_mean_end_to_end_faithfulness_yield"],
                median_e2e=row[f"{prefix}_median_end_to_end_faithfulness_yield"],
                p10_e2e=row[f"{prefix}_p10_end_to_end_faithfulness_yield"],
                usability_rate=row[f"{prefix}_usability_rate"],
                mean_total_tokens=row[f"{prefix}_mean_total_token_count"],
                quality_rank=row[f"{prefix}_quality_rank"],
                hard_gate_pass=row[f"{prefix}_hard_gate_pass"],
                hard_gate_failures=row[f"{prefix}_hard_gate_failures"],
                non_inferior=row[f"{prefix}_non_inferior"],
                ni_status="NON_INFERIOR" if bool(row[f"{prefix}_non_inferior"]) else "INFERIOR",
                decision_metric_basis="DATASET_CERTIFIED",
            )
        elif scope == "FREDDIE":
            prefix = "freddie"
            item.update(
                dataset_id=row[f"{prefix}_dataset_id"],
                dataset_label=DATASET_LABELS[scope],
                mean_e2e=row[f"{prefix}_mean_end_to_end_faithfulness_yield"],
                median_e2e=row[f"{prefix}_median_end_to_end_faithfulness_yield"],
                p10_e2e=row[f"{prefix}_p10_end_to_end_faithfulness_yield"],
                usability_rate=row[f"{prefix}_usability_rate"],
                mean_total_tokens=row[f"{prefix}_mean_total_token_count"],
                quality_rank=row[f"{prefix}_quality_rank"],
                hard_gate_pass=row[f"{prefix}_hard_gate_pass"],
                hard_gate_failures=row[f"{prefix}_hard_gate_failures"],
                non_inferior=row[f"{prefix}_non_inferior"],
                ni_status="NON_INFERIOR" if bool(row[f"{prefix}_non_inferior"]) else "INFERIOR",
                decision_metric_basis="DATASET_CERTIFIED",
            )
        else:
            item.update(
                dataset_id="CROSS_DATASET",
                dataset_label="Cross-dataset",
                mean_e2e=row["worst_dataset_mean_e2e"],
                median_e2e=None,
                p10_e2e=row["worst_dataset_p10_e2e"],
                usability_rate=row["minimum_dataset_usability"],
                mean_total_tokens=row["maximum_dataset_mean_total_tokens"],
                quality_rank=None,
                hard_gate_pass=row["both_datasets_hard_gate_pass"],
                hard_gate_failures=None,
                non_inferior=row["robust_noninferior"],
                ni_status="NON_INFERIOR" if bool(row["robust_noninferior"]) else "INFERIOR",
                decision_metric_basis="CERTIFIED_WORST_CASE_CROSS_DATASET",
            )
        for key in ("mean_e2e", "p10_e2e", "usability_rate"):
            item[f"{key}_display"] = format_percent(locale, item[key], decimals=2) if pd.notna(item[key]) else "—"
        item["tokens_display"] = f"{float(item['mean_total_tokens']):,.0f}" if pd.notna(item.get("mean_total_tokens")) else "—"
        rows.append(item)
    return tuple(rows)


def _ni_rows(repo: DashboardRepositoryV3, scope: str, locale: str) -> tuple[dict[str, Any], ...]:
    frame = repo.table("noninferiority_results")
    if scope != "CROSS_DATASET":
        dataset_id = _dataset_id(repo, scope)
        frame = frame.loc[frame["dataset_id"].astype(str).eq(dataset_id)]
        expected = 15
    else:
        expected = 30
    if len(frame) != expected:
        raise ValueError(f"Expected {expected} certified NI rows for {scope}, found {len(frame)}")

    rows: list[dict[str, Any]] = []
    for row in frame.to_dict(orient="records"):
        item = dict(row)
        dataset_scope = DATASET_ID_TO_SCOPE.get(str(row["dataset_id"]), str(row["dataset_id"]))
        candidate = str(row["candidate_option_id"])
        candidate_model, candidate_evidence = candidate.split("::", 1)
        reference = str(row["reference_option_id"])
        reference_model, reference_evidence = reference.split("::", 1)
        item.update(
            dataset_scope=dataset_scope,
            dataset_label=DATASET_LABELS.get(dataset_scope, dataset_scope),
            candidate_model_id=candidate_model,
            candidate_model_label=MODEL_LABELS.get(candidate_model, candidate_model),
            candidate_evidence_level=candidate_evidence,
            reference_model_id=reference_model,
            reference_model_label=MODEL_LABELS.get(reference_model, reference_model),
            reference_evidence_level=reference_evidence,
            mean_difference_display=f"{float(row['mean_reference_minus_candidate']):.4f}",
            upper_bound_display=f"{float(row['upper_one_sided_bound_95']):.4f}",
            margin_display=f"δ={float(row['margin']):.2f}",
        )
        rows.append(item)
    return tuple(rows)


def _scenario_rows(repo: DashboardRepositoryV3, recs: pd.DataFrame) -> tuple[dict[str, Any], ...]:
    frame = repo.table("scenario_options")
    if len(frame) != 18 * len(SCENARIO_ORDER):
        raise ValueError(f"Expected 90 certified scenario-option rows, found {len(frame)}")
    result: list[dict[str, Any]] = []
    robust_recs = recs.loc[recs["recommendation_scope"].astype(str).eq("CROSS_DATASET_ROBUST")]
    by_scenario = {str(row["scenario_id"]): row for row in robust_recs.to_dict(orient="records")}
    for scenario in SCENARIO_ORDER:
        local = frame.loc[frame["scenario_id"].astype(str).eq(scenario)]
        if len(local) != 18:
            raise ValueError(f"Scenario {scenario} does not contain 18 certified options")
        pool_modes = set(local["pool_mode"].astype(str))
        enabled = set(local["scenario_enabled"].astype(bool))
        if len(pool_modes) != 1 or len(enabled) != 1:
            raise ValueError(f"Scenario {scenario} has inconsistent certified scenario state")
        utility_non_null = int(local["utility_score"].notna().sum())
        recommendation = by_scenario.get(scenario, {})
        result.append(
            {
                "scenario_id": scenario,
                "scenario_enabled": bool(next(iter(enabled))),
                "pool_mode": str(next(iter(pool_modes))),
                "scenario_eligible_count": int(local["scenario_eligible"].astype(bool).sum()),
                "utility_non_null_count": utility_non_null,
                "status": str(recommendation.get("status", "—")),
                "option_id": recommendation.get("option_id"),
                "recommendation_role": recommendation.get("recommendation_role"),
            }
        )
    return tuple(result)


def _decision_counts(rows: tuple[dict[str, Any], ...]) -> dict[str, int]:
    if len(rows) != 18:
        raise ValueError("Decision path requires exactly 18 certified assessment rows")
    return {
        "total": 18,
        "home_credit_hard_gate": sum(bool(row["home_credit_hard_gate_pass"]) for row in rows),
        "freddie_hard_gate": sum(bool(row["freddie_hard_gate_pass"]) for row in rows),
        "both_hard_gate": sum(bool(row["both_datasets_hard_gate_pass"]) for row in rows),
        "home_credit_ni": sum(bool(row["home_credit_non_inferior"]) for row in rows),
        "freddie_ni": sum(bool(row["freddie_non_inferior"]) for row in rows),
        "robust_ni": sum(bool(row["robust_noninferior"]) for row in rows),
        "robust_eligible": sum(bool(row["robust_eligible"]) for row in rows),
    }


def build_decision_model(
    repo: DashboardRepositoryV3,
    scope: str,
    locale: object,
    *,
    search: str | None = None,
) -> DecisionModelV3:
    loc = normalize_locale(locale)
    resolved = repo.validate_scope(scope)
    initial_tab, focus_model, focus_evidence, focus_dataset, focus_option, focus_scenario = _parse_focus(search)
    if focus_dataset and resolved != "CROSS_DATASET" and focus_dataset != resolved:
        focus_dataset = None

    assessment = repo.table("decision_option_assessment")
    if len(assessment) != 18:
        raise ValueError(f"Expected 18 decision_option_assessment rows, found {len(assessment)}")
    all_assessment_rows = tuple(assessment.to_dict(orient="records"))
    counts = _decision_counts(all_assessment_rows)

    margin = repo.table("margin_sensitivity_summary")
    primary = margin.loc[margin["analysis_status"].astype(str).eq("PRIMARY_CERTIFIED")]
    if len(primary) != 1:
        raise ValueError("Expected exactly one PRIMARY_CERTIFIED non-inferiority margin lane")
    primary_margin = float(primary.iloc[0]["margin"])
    if primary_margin != 0.03:
        raise ValueError(f"Certified primary NI margin drifted from 0.03: {primary_margin}")

    recs = repo.table("recommendations")
    dataset_recs = recs.loc[recs["recommendation_scope"].astype(str).isin(["HOME_CREDIT_PRIMARY", "FREDDIE_PRIMARY"])]
    if len(dataset_recs) != 2:
        raise ValueError("Expected exactly two certified dataset-primary recommendations")

    if resolved == "HOME_CREDIT":
        selected = recs.loc[recs["recommendation_scope"].astype(str).eq("HOME_CREDIT_PRIMARY")]
    elif resolved == "FREDDIE":
        selected = recs.loc[recs["recommendation_scope"].astype(str).eq("FREDDIE_PRIMARY")]
    else:
        selected = recs.loc[recs["recommendation_scope"].astype(str).eq("CROSS_DATASET_ROBUST")]

    robust_recs = recs.loc[recs["recommendation_scope"].astype(str).eq("CROSS_DATASET_ROBUST")]
    if tuple(robust_recs["scenario_id"].astype(str)) != SCENARIO_ORDER:
        raise ValueError("Certified scenario registry does not match the five frozen scenarios")
    robust_statuses = set(robust_recs["status"].astype(str))
    robust_status = robust_statuses.pop() if len(robust_statuses) == 1 else "MIXED_CERTIFIED_SCENARIO_STATUS"

    options = _project_assessment_rows(repo, resolved, loc)
    valid_ids = {str(row["option_id"]) for row in options}
    if focus_option not in valid_ids:
        focus_option = None
    if focus_option:
        focus_model, focus_evidence = focus_option.split("::", 1)
    elif focus_model and focus_evidence:
        candidate = f"{focus_model}::{focus_evidence}"
        if candidate in valid_ids:
            focus_option = candidate

    return DecisionModelV3(
        scope=resolved,
        locale=loc,
        title=f"{vt(loc, 'decision')} · {vt(loc, resolved)}",
        options=options,
        recommendations=tuple(selected.to_dict(orient="records")),
        dataset_recommendations=tuple(dataset_recs.to_dict(orient="records")),
        ni_rows=_ni_rows(repo, resolved, loc),
        scenarios=_scenario_rows(repo, recs),
        primary_margin=primary_margin,
        robust_status=robust_status,
        decision_counts=counts,
        limitations=tuple(repo.limitations_for(resolved).to_dict(orient="records")),
        initial_tab=initial_tab,
        focus_model=focus_model,
        focus_evidence=focus_evidence,
        focus_dataset=focus_dataset,
        focus_option=focus_option,
        focus_scenario=focus_scenario,
    )
