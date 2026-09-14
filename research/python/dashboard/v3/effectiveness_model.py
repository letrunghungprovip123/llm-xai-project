from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs

import pandas as pd

from research.python.dashboard.i18n import format_p_value, format_percent, normalize_locale

from .i18n import vt
from .repository import DashboardRepositoryV3


MODEL_LABELS = {
    "qwen3_8b": "Qwen3 8B",
    "deepseek_v4_flash": "DeepSeek V4 Flash",
    "phi4_mini_instruct": "Phi-4 Mini Instruct",
}
DATASET_LABELS = {"HOME_CREDIT": "Home Credit", "FREDDIE": "Freddie Mac"}
DATASET_ID_TO_SCOPE = {
    "home_credit_default_risk": "HOME_CREDIT",
    "freddie_sflld_2024": "FREDDIE",
}
PRIMARY_METRIC = "end_to_end_faithfulness_yield"
SECONDARY_METRICS = (
    "end_to_end_faithfulness_yield",
    "resolved_faithfulness",
    "verifiability",
    "conservative_faithfulness",
)
_VALID_TABS = {"primary", "secondary", "statistics"}


@dataclass(frozen=True)
class EffectivenessModelV3:
    scope: str
    locale: str
    title: str
    option_rows: tuple[dict[str, Any], ...]
    secondary_metric_rows: tuple[dict[str, Any], ...]
    effect_rows: tuple[dict[str, Any], ...]
    contrast_rows: tuple[dict[str, Any], ...]
    metric_dictionary_rows: tuple[dict[str, Any], ...]
    findings: tuple[dict[str, Any], ...]
    limitations: tuple[dict[str, Any], ...]
    initial_tab: str = "primary"
    focus_model: str | None = None
    focus_evidence: str | None = None
    focus_dataset: str | None = None
    # Compatibility field retained intentionally. Replication conclusions are no longer
    # rendered on Effectiveness; Page 2 is descriptive/statistical only.
    rank_rows: tuple[dict[str, Any], ...] = ()


def _parse_focus(search: str | None) -> tuple[str, str | None, str | None, str | None]:
    raw = parse_qs((search or "").lstrip("?"))
    tab = str((raw.get("tab") or ["primary"])[0])
    if tab not in _VALID_TABS:
        tab = "primary"
    model = str((raw.get("model") or [""])[0]) or None
    evidence = str((raw.get("evidence") or [""])[0]) or None
    dataset = str((raw.get("dataset") or [""])[0]) or None
    if model not in MODEL_LABELS:
        model = None
    if evidence not in {"S0", "S1", "S2", "S3", "S4", "S5"}:
        evidence = None
    if dataset not in {"HOME_CREDIT", "FREDDIE"}:
        dataset = None
    return tab, model, evidence, dataset


def _option_rows(frame: pd.DataFrame, locale: str) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for row in frame.sort_values(["evidence_order", "model_id"], kind="stable").to_dict(orient="records"):
        item = dict(row)
        item["dataset_label"] = DATASET_LABELS.get(str(row["dataset_scope"]), str(row["dataset_scope"]))
        item["model_label"] = MODEL_LABELS.get(str(row["model_id"]), str(row["model_id"]))
        for key in ("mean_e2e", "median_e2e", "p10_e2e", "bootstrap_ci_lower", "bootstrap_ci_upper", "usability_rate"):
            item[f"{key}_display"] = format_percent(locale, row[key], decimals=2)
        rows.append(item)
    return tuple(rows)


def _effect_rows(frame: pd.DataFrame, locale: str) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for row in frame.to_dict(orient="records"):
        item = dict(row)
        item["dataset_label"] = DATASET_LABELS.get(str(row["dataset_scope"]), str(row["dataset_scope"]))
        p = row.get("p_value_used")
        item["p_value_display"] = format_p_value(locale, p, decimals=4) if pd.notna(p) else "—"
        rows.append(item)
    return tuple(rows)


def _contrast_label(row: dict[str, Any]) -> str:
    a_model = MODEL_LABELS.get(str(row.get("condition_a_model_id")), str(row.get("condition_a_model_id")))
    b_model = MODEL_LABELS.get(str(row.get("condition_b_model_id")), str(row.get("condition_b_model_id")))
    a_evidence = str(row.get("condition_a_evidence_level"))
    b_evidence = str(row.get("condition_b_evidence_level"))
    family = str(row.get("contrast_family"))
    if family == "model_within_evidence":
        return f"{a_model} vs {b_model} · {a_evidence}"
    context_model = MODEL_LABELS.get(str(row.get("context_model_id")), str(row.get("context_model_id")))
    if context_model and context_model != "nan":
        return f"{context_model} · {a_evidence} vs {b_evidence}"
    return f"{a_model} {a_evidence} vs {b_model} {b_evidence}"


def _contrast_rows(frame: pd.DataFrame, locale: str) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(frame.to_dict(orient="records"), start=1):
        item = dict(row)
        item["dataset_label"] = DATASET_LABELS.get(str(row["dataset_scope"]), str(row["dataset_scope"]))
        item["contrast_label"] = _contrast_label(item)
        item["contrast_key"] = f"{row['dataset_scope']}::{row['contrast_family']}::{index:02d}"
        p = row.get("adjusted_p_value")
        item["adjusted_p_display"] = format_p_value(locale, p, decimals=4) if pd.notna(p) else "—"
        rows.append(item)
    return tuple(rows)


def _secondary_rows(repo: DashboardRepositoryV3, scope: str) -> tuple[dict[str, Any], ...]:
    frame = repo.table("metric_sensitivity").copy()
    frame["dataset_scope"] = frame["dataset_id"].astype(str).map(DATASET_ID_TO_SCOPE)
    frame = frame.loc[frame["metric_id"].astype(str).isin(SECONDARY_METRICS)]
    if scope != "CROSS_DATASET":
        frame = frame.loc[frame["dataset_scope"].eq(scope)]
    expected = 72 if scope != "CROSS_DATASET" else 144
    if len(frame) != expected:
        raise ValueError(f"Expected {expected} certified option × metric rows for {scope}, found {len(frame)}")
    rows: list[dict[str, Any]] = []
    for row in frame.to_dict(orient="records"):
        item = dict(row)
        item["dataset_label"] = DATASET_LABELS.get(str(row["dataset_scope"]), str(row["dataset_scope"]))
        item["model_label"] = MODEL_LABELS.get(str(row["model_id"]), str(row["model_id"]))
        rows.append(item)
    return tuple(rows)


def _metric_dictionary(repo: DashboardRepositoryV3) -> tuple[dict[str, Any], ...]:
    frame = repo.table("metric_dictionary")
    rows = frame.loc[frame["metric_id"].astype(str).isin(SECONDARY_METRICS)]
    return tuple(rows.to_dict(orient="records"))


def build_effectiveness_model(
    repo: DashboardRepositoryV3,
    scope: str,
    locale: object,
    *,
    search: str | None = None,
) -> EffectivenessModelV3:
    loc = normalize_locale(locale)
    resolved = repo.validate_scope(scope)
    initial_tab, focus_model, focus_evidence, focus_dataset = _parse_focus(search)
    if focus_dataset and resolved != "CROSS_DATASET" and focus_dataset != resolved:
        focus_dataset = None

    if resolved == "CROSS_DATASET":
        options = repo.table("option_performance")
        effects = repo.table("omnibus_effects")
        contrasts = repo.table("planned_contrasts")
        if len(options) != 36:
            raise ValueError(f"Expected 36 certified study options for cross-dataset comparison, found {len(options)}")
        if len(effects) != 6:
            raise ValueError(f"Expected 6 certified omnibus rows for cross-dataset comparison, found {len(effects)}")
        if len(contrasts) != 66:
            raise ValueError(f"Expected 66 certified planned-contrast rows for cross-dataset comparison, found {len(contrasts)}")
    else:
        options = repo.study_table("option_performance", resolved)
        effects = repo.study_table("omnibus_effects", resolved)
        contrasts = repo.study_table("planned_contrasts", resolved)
        if len(options) != 18:
            raise ValueError(f"Expected 18 certified options for {resolved}, found {len(options)}")
        if len(effects) != 3:
            raise ValueError(f"Expected 3 certified omnibus effects for {resolved}, found {len(effects)}")
        if len(contrasts) != 33:
            raise ValueError(f"Expected 33 certified planned contrasts for {resolved}, found {len(contrasts)}")

    return EffectivenessModelV3(
        scope=resolved,
        locale=loc,
        title=f"{vt(loc, 'effectiveness')} · {vt(loc, resolved)}",
        option_rows=_option_rows(options.reset_index(drop=True), loc),
        secondary_metric_rows=_secondary_rows(repo, resolved),
        effect_rows=_effect_rows(effects.reset_index(drop=True), loc),
        contrast_rows=_contrast_rows(contrasts.reset_index(drop=True), loc),
        metric_dictionary_rows=_metric_dictionary(repo),
        findings=tuple(repo.findings_for(resolved).to_dict(orient="records")),
        limitations=tuple(repo.limitations_for(resolved).to_dict(orient="records")),
        initial_tab=initial_tab,
        focus_model=focus_model,
        focus_evidence=focus_evidence,
        focus_dataset=focus_dataset,
    )
