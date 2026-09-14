from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs

import numpy as np
import pandas as pd

from research.python.dashboard.i18n import format_percent, normalize_locale

from .effectiveness_model import DATASET_ID_TO_SCOPE, DATASET_LABELS, MODEL_LABELS
from .i18n import vt
from .repository import DashboardRepositoryV3


_REQUIRED_QUALITY_METRICS = (
    "end_to_end_faithfulness_yield",
    "resolved_faithfulness",
    "verifiability",
    "conservative_faithfulness",
)
_VALID_TABS = {"loss", "claims", "quality"}


@dataclass(frozen=True)
class MechanismsModelV3:
    scope: str
    locale: str
    title: str
    loss_rows: tuple[dict[str, Any], ...]
    claim_rows: tuple[dict[str, Any], ...]
    quality_rows: tuple[dict[str, Any], ...]
    findings: tuple[dict[str, Any], ...]
    limitations: tuple[dict[str, Any], ...]
    reason_profile_status: str
    initial_tab: str = "loss"
    focus_validation_status: str | None = None
    focus_model: str | None = None
    focus_evidence: str | None = None
    focus_dataset: str | None = None


def _parse_focus(search: str | None) -> tuple[str, str | None, str | None, str | None, str | None]:
    raw = parse_qs((search or "").lstrip("?"))
    tab = str((raw.get("tab") or [""])[0])
    validation = str((raw.get("validation_status") or [""])[0]) or None
    model = str((raw.get("model") or [""])[0]) or None
    evidence = str((raw.get("evidence") or [""])[0]) or None
    dataset = str((raw.get("dataset") or [""])[0]) or None
    if not tab:
        tab = "claims" if validation else ("quality" if model or evidence or dataset else "loss")
    if tab not in _VALID_TABS:
        tab = "loss"
    if validation not in {"SUPPORTED", "NOT_VERIFIABLE", "UNSUPPORTED", "CONTRADICTED", "NOT_APPLICABLE"}:
        validation = None
    if model not in MODEL_LABELS:
        model = None
    if evidence not in {"S0", "S1", "S2", "S3", "S4", "S5"}:
        evidence = None
    if dataset not in {"HOME_CREDIT", "FREDDIE"}:
        dataset = None
    return tab, validation, model, evidence, dataset


def _loss_rows(repo: DashboardRepositoryV3, scope: str, locale: str) -> tuple[dict[str, Any], ...]:
    loss = repo.table("failure_decomposition")
    summary = repo.table("study_summary")[["dataset_scope", "primary_e2e", "primary_e2e_report_number_id"]]
    frame = loss.merge(summary, on="dataset_scope", how="inner", validate="one_to_one")
    if scope != "CROSS_DATASET":
        frame = frame.loc[frame["dataset_scope"].astype(str).eq(scope)]
    expected = 2 if scope == "CROSS_DATASET" else 1
    if len(frame) != expected:
        raise ValueError(f"Expected {expected} certified loss-accounting rows for {scope}, found {len(frame)}")

    identity = (
        frame["primary_e2e"].astype(float)
        + frame["pipeline_loss"].astype(float)
        + frame["not_verifiable_loss"].astype(float)
        + frame["unsupported_loss"].astype(float)
        + frame["contradiction_loss"].astype(float)
    )
    if not np.allclose(identity.to_numpy(), np.ones(len(frame)), atol=1e-8):
        raise ValueError(f"Certified faithfulness accounting identity failed for {scope}: {identity.tolist()}")

    rows: list[dict[str, Any]] = []
    display_keys = (
        "primary_e2e",
        "pipeline_loss",
        "not_verifiable_loss",
        "unsupported_loss",
        "contradiction_loss",
        "safe_phrase_matched_claim_rate",
    )
    for row in frame.to_dict(orient="records"):
        item = dict(row)
        item["dataset_label"] = DATASET_LABELS.get(str(row["dataset_scope"]), str(row["dataset_scope"]))
        for key in display_keys:
            item[f"{key}_display"] = format_percent(locale, row[key], decimals=2)
        rows.append(item)
    return tuple(rows)


def _claim_rows(repo: DashboardRepositoryV3, scope: str) -> tuple[dict[str, Any], ...]:
    frame = repo.table("claim_type_profile")
    if scope != "CROSS_DATASET":
        frame = frame.loc[frame["dataset_scope"].astype(str).eq(scope)]
    else:
        if set(frame["dataset_scope"].astype(str)) != {"HOME_CREDIT", "FREDDIE"}:
            raise ValueError("Cross-dataset claim diagnostics require both certified study scopes")
    return tuple(frame.reset_index(drop=True).to_dict(orient="records"))


def _quality_rows(repo: DashboardRepositoryV3, scope: str) -> tuple[dict[str, Any], ...]:
    frame = repo.table("metric_sensitivity").copy()
    frame["dataset_scope"] = frame["dataset_id"].astype(str).map(DATASET_ID_TO_SCOPE)
    frame = frame.loc[frame["metric_id"].astype(str).isin(_REQUIRED_QUALITY_METRICS)]
    if scope != "CROSS_DATASET":
        frame = frame.loc[frame["dataset_scope"].eq(scope)]

    pivot = frame.pivot_table(
        index=["dataset_scope", "dataset_id", "option_id", "model_id", "evidence_level"],
        columns="metric_id",
        values="metric_mean",
        aggfunc="first",
    ).reset_index()
    missing = set(_REQUIRED_QUALITY_METRICS) - set(pivot.columns)
    if missing:
        raise ValueError(f"Missing certified quality metrics: {sorted(missing)}")
    expected = 36 if scope == "CROSS_DATASET" else 18
    if len(pivot) != expected:
        raise ValueError(f"Expected {expected} quality-profile options for {scope}, found {len(pivot)}")

    rows: list[dict[str, Any]] = []
    for row in pivot.to_dict(orient="records"):
        item = dict(row)
        item["dataset_label"] = DATASET_LABELS.get(str(row["dataset_scope"]), str(row["dataset_scope"]))
        item["model_label"] = MODEL_LABELS.get(str(row["model_id"]), str(row["model_id"]))
        rows.append(item)
    return tuple(rows)


def build_mechanisms_model(
    repo: DashboardRepositoryV3,
    scope: str,
    locale: object,
    *,
    search: str | None = None,
) -> MechanismsModelV3:
    loc = normalize_locale(locale)
    resolved = repo.validate_scope(scope)
    initial_tab, validation, focus_model, focus_evidence, focus_dataset = _parse_focus(search)
    if focus_dataset and resolved != "CROSS_DATASET" and focus_dataset != resolved:
        focus_dataset = None
    return MechanismsModelV3(
        scope=resolved,
        locale=loc,
        title=f"{vt(loc, 'mechanisms')} · {vt(loc, resolved)}",
        loss_rows=_loss_rows(repo, resolved, loc),
        claim_rows=_claim_rows(repo, resolved),
        quality_rows=_quality_rows(repo, resolved),
        findings=tuple(repo.findings_for(resolved).to_dict(orient="records")),
        limitations=tuple(repo.limitations_for(resolved).to_dict(orient="records")),
        reason_profile_status="NOT_AVAILABLE_IN_VISUALIZATION_DATA_V3",
        initial_tab=initial_tab,
        focus_validation_status=validation,
        focus_model=focus_model,
        focus_evidence=focus_evidence,
        focus_dataset=focus_dataset,
    )
