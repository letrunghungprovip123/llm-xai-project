from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs

import pandas as pd

from research.python.dashboard.i18n import format_p_value, format_percent, normalize_locale

from .effectiveness_model import DATASET_ID_TO_SCOPE, DATASET_LABELS, MODEL_LABELS
from .i18n import vt
from .repository import DashboardRepositoryV3


_VALID_TABS = {"population", "metric", "decision"}
_VALID_FAMILIES = {"all", "model_within_evidence", "evidence_vs_s0"}
_VALID_METRICS = {
    "ALL",
    "resolved_faithfulness",
    "verifiability",
    "conservative_faithfulness",
}
_VALID_EVIDENCE = {f"S{i}" for i in range(6)}
_VALID_MARGINS = {0.02, 0.03, 0.05}


@dataclass(frozen=True)
class RobustnessModelV3:
    scope: str
    locale: str
    title: str
    summary: tuple[dict[str, Any], ...]
    population_effects: tuple[dict[str, Any], ...]
    population_contrasts: tuple[dict[str, Any], ...]
    metric_rows: tuple[dict[str, Any], ...]
    margin_rows: tuple[dict[str, Any], ...]
    recommendation_rows: tuple[dict[str, Any], ...]
    limitations: tuple[dict[str, Any], ...]
    validator_status: str
    template_status: str
    initial_tab: str = "population"
    focus_family: str = "evidence_vs_s0"
    focus_metric: str = "ALL"
    focus_model: str | None = None
    focus_evidence: str | None = None
    focus_dataset: str | None = None
    focus_margin: float = 0.03


def _dataset_id(repo: DashboardRepositoryV3, scope: str) -> str:
    frame = repo.study_table("study_summary", scope)
    if len(frame) != 1:
        raise ValueError(f"Expected one study summary for {scope}")
    return str(frame.iloc[0]["dataset_id"])


def _parse_focus(search: str | None) -> tuple[str, str, str, str | None, str | None, str | None, float]:
    raw = parse_qs((search or "").lstrip("?"))
    tab = str((raw.get("tab") or ["population"])[0])
    family = str((raw.get("family") or ["evidence_vs_s0"])[0])
    metric = str((raw.get("metric") or ["ALL"])[0])
    model = str((raw.get("model") or [""])[0]) or None
    evidence = str((raw.get("evidence") or [""])[0]) or None
    dataset = str((raw.get("dataset") or [""])[0]) or None
    margin_raw = str((raw.get("margin") or ["0.03"])[0])
    if tab not in _VALID_TABS:
        tab = "population"
    if family not in _VALID_FAMILIES:
        family = "evidence_vs_s0"
    if metric not in _VALID_METRICS:
        metric = "ALL"
    if model not in MODEL_LABELS:
        model = None
    if evidence not in _VALID_EVIDENCE:
        evidence = None
    if dataset not in {"HOME_CREDIT", "FREDDIE"}:
        dataset = None
    try:
        margin = float(margin_raw)
    except ValueError:
        margin = 0.03
    if margin not in _VALID_MARGINS:
        margin = 0.03
    return tab, family, metric, model, evidence, dataset, margin


def _scope_frame(repo: DashboardRepositoryV3, name: str, scope: str) -> pd.DataFrame:
    frame = repo.table(name)
    if scope == "CROSS_DATASET":
        return frame.reset_index(drop=True)
    dataset_id = _dataset_id(repo, scope)
    return frame.loc[frame["dataset_id"].astype(str).eq(dataset_id)].reset_index(drop=True)


def _population_effect_rows(frame: pd.DataFrame, locale: str) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for row in frame.to_dict(orient="records"):
        item = dict(row)
        dataset_scope = DATASET_ID_TO_SCOPE.get(str(row["dataset_id"]), str(row["dataset_id"]))
        item["dataset_scope"] = dataset_scope
        item["dataset_label"] = DATASET_LABELS.get(dataset_scope, dataset_scope)
        item["primary_p_display"] = format_p_value(locale, row["p_value_used_primary"], decimals=4)
        item["complete_p_display"] = format_p_value(locale, row["p_value_used_complete_case"], decimals=4)
        rows.append(item)
    return tuple(rows)


def _contrast_rows(frame: pd.DataFrame, locale: str) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for row in frame.to_dict(orient="records"):
        item = dict(row)
        dataset_scope = DATASET_ID_TO_SCOPE.get(str(row["dataset_id"]), str(row["dataset_id"]))
        item["dataset_scope"] = dataset_scope
        item["dataset_label"] = DATASET_LABELS.get(dataset_scope, dataset_scope)
        item["primary_p_display"] = format_p_value(locale, row["adjusted_p_value_primary"], decimals=4)
        item["complete_p_display"] = format_p_value(locale, row["adjusted_p_value_complete_case"], decimals=4)
        rows.append(item)
    return tuple(rows)


def _metric_rows(frame: pd.DataFrame, locale: str) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for row in frame.to_dict(orient="records"):
        item = dict(row)
        dataset_scope = DATASET_ID_TO_SCOPE.get(str(row["dataset_id"]), str(row["dataset_id"]))
        item["dataset_scope"] = dataset_scope
        item["dataset_label"] = DATASET_LABELS.get(dataset_scope, dataset_scope)
        item["model_label"] = MODEL_LABELS.get(str(row["model_id"]), str(row["model_id"]))
        item["metric_mean_display"] = format_percent(locale, row["metric_mean"], decimals=2) if pd.notna(row["metric_mean"]) else "—"
        rows.append(item)
    return tuple(rows)


def build_robustness_model(
    repo: DashboardRepositoryV3,
    scope: str,
    locale: object,
    *,
    search: str | None = None,
) -> RobustnessModelV3:
    loc = normalize_locale(locale)
    resolved = repo.validate_scope(scope)
    initial_tab, family, metric, focus_model, focus_evidence, focus_dataset, focus_margin = _parse_focus(search)
    if focus_dataset and resolved != "CROSS_DATASET" and focus_dataset != resolved:
        focus_dataset = None

    population = _scope_frame(repo, "population_effect_sensitivity", resolved)
    contrasts = _scope_frame(repo, "population_contrast_sensitivity", resolved)
    metric_frame = _scope_frame(repo, "metric_sensitivity", resolved)
    expected_effects = 6 if resolved == "CROSS_DATASET" else 3
    expected_contrasts = 66 if resolved == "CROSS_DATASET" else 33
    expected_metrics = 144 if resolved == "CROSS_DATASET" else 72
    if len(population) != expected_effects:
        raise ValueError(f"Expected {expected_effects} population effect sensitivity rows for {resolved}, found {len(population)}")
    if len(contrasts) != expected_contrasts:
        raise ValueError(f"Expected {expected_contrasts} population contrast sensitivity rows for {resolved}, found {len(contrasts)}")
    if len(metric_frame) != expected_metrics:
        raise ValueError(f"Expected {expected_metrics} metric sensitivity rows for {resolved}, found {len(metric_frame)}")

    margin = repo.table("margin_sensitivity_summary")
    recommendation = repo.table("recommendation_sensitivity")
    if tuple(round(float(x), 2) for x in margin["margin"]) != (0.02, 0.03, 0.05):
        raise ValueError("Certified margin sensitivity registry must contain exactly 0.02, 0.03, 0.05")
    primary = margin.loc[margin["analysis_status"].astype(str).eq("PRIMARY_CERTIFIED")]
    if len(primary) != 1 or float(primary.iloc[0]["margin"]) != 0.03:
        raise ValueError("Exactly one PRIMARY_CERTIFIED δ=0.03 lane is required")

    return RobustnessModelV3(
        scope=resolved,
        locale=loc,
        title=f"{vt(loc, 'robustness')} · {vt(loc, resolved)}",
        summary=tuple(repo.table("robustness_summary").to_dict(orient="records")),
        population_effects=_population_effect_rows(population, loc),
        population_contrasts=_contrast_rows(contrasts, loc),
        metric_rows=_metric_rows(metric_frame, loc),
        margin_rows=tuple(margin.to_dict(orient="records")),
        recommendation_rows=tuple(recommendation.to_dict(orient="records")),
        limitations=tuple(repo.limitations_for(resolved).to_dict(orient="records")),
        validator_status="NOT_MATERIALIZED_IN_VISUALIZATION_DATA_V3",
        template_status="NOT_MATERIALIZED_IN_VISUALIZATION_DATA_V3",
        initial_tab=initial_tab,
        focus_family=family,
        focus_metric=metric,
        focus_model=focus_model,
        focus_evidence=focus_evidence,
        focus_dataset=focus_dataset,
        focus_margin=focus_margin,
    )
