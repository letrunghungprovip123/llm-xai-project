from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

import pandas as pd

from research.python.dashboard.i18n import format_integer, format_percent, format_p_value

if TYPE_CHECKING:
    from .repository import DashboardRepositoryV3


VI_LOCALE = "vi"
MODEL_LABELS = {
    "qwen3_8b": "Qwen3 8B",
    "deepseek_v4_flash": "DeepSeek V4 Flash",
    "phi4_mini_instruct": "Phi-4 Mini Instruct",
}
VALIDATION_STATUSES = (
    "SUPPORTED",
    "NOT_VERIFIABLE",
    "UNSUPPORTED",
    "CONTRADICTED",
    "NOT_APPLICABLE",
)
REPLICATION_ORDER = (
    "REPLICATED",
    "DIRECTIONALLY_REPLICATED",
    "DIRECTION_CONFLICT",
    "INCONCLUSIVE",
)


@dataclass(frozen=True)
class OverviewMetricValue:
    dataset_scope: str
    dataset_label: str
    raw_value: Any
    display_value: str
    report_number_id: str


@dataclass(frozen=True)
class OverviewMetricCard:
    key: str
    label: str
    values: tuple[OverviewMetricValue, ...]
    analysis_lane: str
    primary: bool = False


@dataclass(frozen=True)
class OverviewModelV3:
    scope: str
    locale: str
    title: str
    subtitle: str
    cards: tuple[OverviewMetricCard, ...]
    option_rows: tuple[dict[str, Any], ...]
    effects: tuple[dict[str, Any], ...]
    validation_rows: tuple[dict[str, Any], ...]
    replication_counts: tuple[dict[str, Any], ...]
    rank_stability: dict[str, Any] | None
    replication_scope: str | None
    robust_recommendation_status: str | None
    limitations: tuple[dict[str, Any], ...]


_DATASET_LABELS = {
    "HOME_CREDIT": "Home Credit",
    "FREDDIE": "Freddie Mac",
}

_METRICS = (
    ("planned_generations", "Planned generations", False),
    ("usable_generations", "Usable generations", False),
    ("final_claims", "Atomic claims", False),
    ("primary_e2e", "End-to-End Faithfulness", True),
)


def _metric_display(key: str, value: Any) -> str:
    if key == "primary_e2e":
        return format_percent(VI_LOCALE, value, decimals=2)
    return format_integer(VI_LOCALE, value)


def _metric_value(summary: dict[str, Any], scope: str, key: str) -> OverviewMetricValue:
    return OverviewMetricValue(
        dataset_scope=scope,
        dataset_label=_DATASET_LABELS[scope],
        raw_value=summary[key],
        display_value=_metric_display(key, summary[key]),
        report_number_id=str(summary[f"{key}_report_number_id"]),
    )


def _cards_for_study(summary: dict[str, Any], scope: str) -> tuple[OverviewMetricCard, ...]:
    return tuple(
        OverviewMetricCard(
            key=key,
            label=label,
            values=(_metric_value(summary, scope, key),),
            analysis_lane=str(summary.get("analysis_lane", "PRIMARY")),
            primary=primary,
        )
        for key, label, primary in _METRICS
    )


def _cards_for_cross(
    home_credit: dict[str, Any],
    freddie: dict[str, Any],
) -> tuple[OverviewMetricCard, ...]:
    return tuple(
        OverviewMetricCard(
            key=key,
            label=label,
            values=(
                _metric_value(home_credit, "HOME_CREDIT", key),
                _metric_value(freddie, "FREDDIE", key),
            ),
            analysis_lane="PRIMARY",
            primary=primary,
        )
        for key, label, primary in _METRICS
    )


def _study_option_rows(frame: pd.DataFrame, scope: str) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    ordered = frame.sort_values(["evidence_order", "model_id"], kind="stable")
    for row in ordered.to_dict(orient="records"):
        item = dict(row)
        item["dataset_scope"] = scope
        item["dataset_label"] = _DATASET_LABELS[scope]
        item["model_label"] = MODEL_LABELS.get(str(row["model_id"]), str(row["model_id"]))
        item["mean_e2e_display"] = format_percent(VI_LOCALE, row["mean_e2e"], decimals=2)
        item["p10_e2e_display"] = format_percent(VI_LOCALE, row["p10_e2e"], decimals=2)
        item["usability_display"] = format_percent(VI_LOCALE, row["usability_rate"], decimals=2)
        rows.append(item)
    return tuple(rows)


def _cross_option_rows(frame: pd.DataFrame) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    ordered = frame.sort_values(["evidence_order", "model_id"], kind="stable")
    for row in ordered.to_dict(orient="records"):
        item = dict(row)
        item["model_label"] = MODEL_LABELS.get(str(row["model_id"]), str(row["model_id"]))
        for prefix in ("home_credit", "freddie"):
            value = row[f"{prefix}_mean_end_to_end_faithfulness_yield"]
            item[f"{prefix}_mean_e2e_display"] = format_percent(VI_LOCALE, value, decimals=2)
            p10 = row.get(f"{prefix}_p10_end_to_end_faithfulness_yield")
            usability = row.get(f"{prefix}_usability_rate")
            item[f"{prefix}_p10_e2e_display"] = format_percent(VI_LOCALE, p10, decimals=2) if pd.notna(p10) else "—"
            item[f"{prefix}_usability_display"] = format_percent(VI_LOCALE, usability, decimals=2) if pd.notna(usability) else "—"
        rows.append(item)
    return tuple(rows)


def _study_effect_rows(frame: pd.DataFrame) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for row in frame.to_dict(orient="records"):
        item = dict(row)
        p = row.get("p_value_used")
        item["p_value_display"] = format_p_value(VI_LOCALE, p, decimals=4) if pd.notna(p) else "—"
        rows.append(item)
    return tuple(rows)


def _cross_effect_rows(frame: pd.DataFrame) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for row in frame.to_dict(orient="records"):
        item = dict(row)
        item["home_credit_p_value_display"] = format_p_value(
            VI_LOCALE, row.get("home_credit_p_value"), decimals=4
        )
        item["freddie_p_value_display"] = format_p_value(
            VI_LOCALE, row.get("freddie_p_value"), decimals=4
        )
        rows.append(item)
    return tuple(rows)


def _validation_row(summary: dict[str, Any], scope: str) -> dict[str, Any]:
    counts = {status: int(summary[f"{status.lower()}_claims"]) for status in VALIDATION_STATUSES}
    report_ids = {
        status: str(summary[f"{status.lower()}_report_number_id"])
        for status in VALIDATION_STATUSES
    }
    total = sum(counts.values())
    return {
        "dataset_scope": scope,
        "dataset_label": _DATASET_LABELS[scope],
        "total_claims": total,
        "counts": counts,
        "report_number_ids": report_ids,
    }


def _replication_summary(concordance: pd.DataFrame) -> tuple[dict[str, Any], ...]:
    if concordance.empty:
        return ()
    observed = concordance["replication_status"].astype(str).value_counts().to_dict()
    return tuple(
        {"status": status, "count": int(observed.get(status, 0))}
        for status in REPLICATION_ORDER
    )


def _overview_limitations(frame: pd.DataFrame) -> tuple[dict[str, Any], ...]:
    preferred = {"MODEL_REVISION_UNKNOWN", "TWO_CREDIT_RISK_DATASETS_ONLY"}
    selected = frame.loc[frame["limitation_id"].astype(str).isin(preferred)]
    return tuple(selected.to_dict(orient="records"))


def build_overview_model(
    repo: DashboardRepositoryV3,
    scope: str,
    locale: object = VI_LOCALE,
) -> OverviewModelV3:
    """Build the certified Overview presentation model.

    The dashboard is Vietnamese-first by product design. ``locale`` is retained
    only for backwards-compatible callback signatures; the presentation model
    is intentionally fixed to Vietnamese and keeps scientific English terms
    unchanged.
    """

    del locale
    resolved = repo.validate_scope(scope)
    subtitle = (
        "Đánh giá faithfulness của LLM-generated explanations dưới sáu evidence conditions "
        "trên Home Credit và Freddie Mac."
    )

    if resolved != "CROSS_DATASET":
        view = repo.study_overview(resolved)
        options = repo.study_table("option_performance", resolved)
        return OverviewModelV3(
            scope=resolved,
            locale=VI_LOCALE,
            title="Tổng quan nghiên cứu",
            subtitle=subtitle,
            cards=_cards_for_study(view.summary, resolved),
            option_rows=_study_option_rows(options, resolved),
            effects=_study_effect_rows(view.effects),
            validation_rows=(_validation_row(view.summary, resolved),),
            replication_counts=(),
            rank_stability=None,
            replication_scope=None,
            robust_recommendation_status=None,
            limitations=_overview_limitations(view.limitations),
        )

    view = repo.cross_overview()
    options = repo.table("cross_dataset_option_performance")
    concordance = repo.table("contrast_concordance")
    rank = repo.table("rank_stability")
    rank_row = rank.iloc[0].to_dict() if len(rank) else None
    return OverviewModelV3(
        scope=resolved,
        locale=VI_LOCALE,
        title="Tổng quan nghiên cứu",
        subtitle=subtitle,
        cards=_cards_for_cross(view.home_credit, view.freddie),
        option_rows=_cross_option_rows(options),
        effects=_cross_effect_rows(view.effects),
        validation_rows=(
            _validation_row(view.home_credit, "HOME_CREDIT"),
            _validation_row(view.freddie, "FREDDIE"),
        ),
        replication_counts=_replication_summary(concordance),
        rank_stability=rank_row,
        replication_scope=view.replication_scope,
        robust_recommendation_status=view.robust_recommendation_status,
        limitations=_overview_limitations(view.limitations),
    )
