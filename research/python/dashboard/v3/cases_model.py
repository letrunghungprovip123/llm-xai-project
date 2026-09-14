from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import parse_qs

import pandas as pd

from research.python.dashboard.i18n import format_percent, normalize_locale

from .effectiveness_model import MODEL_LABELS
from .i18n import vt
from .repository import DashboardRepositoryV3


VALID_DATASETS = ("HOME_CREDIT", "FREDDIE")
VALID_EVIDENCE = tuple(f"S{i}" for i in range(6))
VALID_TABS = ("landscape", "diagnostics", "claims")
STRATUM_ORDER = (
    "top_high_risk",
    "low_risk",
    "true_positive",
    "false_positive",
    "false_negative",
    "near_threshold",
)
STRATUM_LABELS = {
    "top_high_risk": "Top high-risk",
    "low_risk": "Low-risk",
    "true_positive": "True positive",
    "false_positive": "False positive",
    "false_negative": "False negative",
    "near_threshold": "Near threshold",
}
STATUS_ORDER = ("SUPPORTED", "NOT_VERIFIABLE", "UNSUPPORTED", "CONTRADICTED", "NOT_APPLICABLE")


def _query_value(raw: dict[str, list[str]], *keys: str) -> str | None:
    for key in keys:
        value = str((raw.get(key) or [""])[0]).strip()
        if value:
            return value
    return None


def parse_cases_state(search: str | None) -> dict[str, str | None]:
    raw = parse_qs((search or "").lstrip("?"))
    dataset = _query_value(raw, "dataset", "scope")
    case_id = _query_value(raw, "case", "case_id")
    model_id = _query_value(raw, "model")
    evidence = _query_value(raw, "evidence")
    stratum = _query_value(raw, "stratum")
    tab = _query_value(raw, "tab")
    if dataset not in VALID_DATASETS:
        dataset = None
    if model_id not in MODEL_LABELS:
        model_id = None
    if evidence not in VALID_EVIDENCE:
        evidence = None
    if stratum not in STRATUM_ORDER:
        stratum = None
    if tab not in VALID_TABS:
        tab = None
    return {
        "dataset": dataset,
        "case_id": case_id,
        "model_id": model_id,
        "evidence": evidence,
        "stratum": stratum,
        "tab": tab,
    }


def parse_cases_search(search: str | None) -> tuple[str | None, str | None, str | None, str | None]:
    """Backward-compatible Page 2/3 drill-through parser."""
    state = parse_cases_state(search)
    return state["dataset"], state["case_id"], state["model_id"], state["evidence"]


def _single_study_scope(value: object) -> str | None:
    text = str(value or "")
    return text if text in VALID_DATASETS else None


def _canonical_state_value(state: Mapping[str, Any] | None, key: str) -> str | None:
    if not isinstance(state, Mapping):
        return None
    value = state.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def canonical_cases_state(model: "CasesModelV3") -> dict[str, str]:
    """Return the complete canonical UI state for one certified Case selection.

    The selected-generation store is the only canonical state object consumed by
    downstream Case callbacks.  Keeping stratum/tab beside the generation
    identity lets control echo events be compared without consulting component
    state inside the resolver.
    """
    return {
        **model.selected_identity,
        "stratum": model.selected_stratum,
        "tab": model.initial_tab,
    }


def initial_cases_intent(global_scope: object, search: str | None) -> dict[str, str | None]:
    """Resolve first-paint intent. Explicit URL state outranks global scope."""
    query = parse_cases_state(search)
    dataset = query["dataset"] or _single_study_scope(global_scope) or "HOME_CREDIT"
    # A canonical case id is more specific than a stratum.  When both are
    # supplied, derive the stratum from the exact case instead of allowing a
    # stale/inconsistent stratum to discard the requested case.
    stratum = None if query["case_id"] else query["stratum"]
    return {
        "kind": "initialize",
        "dataset": dataset,
        "case_id": query["case_id"],
        "model_id": query["model_id"],
        "evidence_level": query["evidence"],
        "stratum": stratum,
        "tab": query["tab"] or "landscape",
    }


def url_cases_intent(search: str | None, canonical: Mapping[str, Any] | None) -> dict[str, str | None] | None:
    """Resolve an in-page URL change without consulting global/local controls."""
    query = parse_cases_state(search)
    if not any(query.values()):
        return None
    current_dataset = _single_study_scope(_canonical_state_value(canonical, "dataset")) or "HOME_CREDIT"
    requested_case = query["case_id"] or _canonical_state_value(canonical, "case_id")
    return {
        "kind": "url",
        "dataset": query["dataset"] or current_dataset,
        "case_id": requested_case,
        "model_id": query["model_id"] or _canonical_state_value(canonical, "model_id"),
        "evidence_level": query["evidence"] or _canonical_state_value(canonical, "evidence_level"),
        "stratum": None if query["case_id"] else (query["stratum"] or _canonical_state_value(canonical, "stratum")),
        "tab": query["tab"] or _canonical_state_value(canonical, "tab") or "landscape",
    }


def control_cases_intent(field: str, value: object, canonical: Mapping[str, Any] | None) -> dict[str, str | None] | None:
    """Translate one genuine control change into deterministic Case intent.

    Only the control that actually triggered is trusted.  Every other field is
    taken from the canonical selected-generation Store, so transient DMC values
    produced while Select.data/value are reconciled cannot reset unrelated
    state.  Returning ``None`` means the event is either invalid or merely an
    echo of resolver-owned control output.
    """
    if not isinstance(canonical, Mapping):
        return None

    dataset = _single_study_scope(_canonical_state_value(canonical, "dataset")) or "HOME_CREDIT"
    case_id = _canonical_state_value(canonical, "case_id")
    model_id = _canonical_state_value(canonical, "model_id")
    evidence = _canonical_state_value(canonical, "evidence_level")
    stratum = _canonical_state_value(canonical, "stratum")
    tab = _canonical_state_value(canonical, "tab") or "landscape"

    intent: dict[str, str | None] = {
        "kind": "control",
        "dataset": dataset,
        "case_id": case_id,
        "model_id": model_id,
        "evidence_level": evidence,
        "stratum": stratum,
        "tab": tab,
    }

    if field == "dataset":
        requested = _single_study_scope(value)
        if requested is None or requested == dataset:
            return None
        intent["dataset"] = requested
        # A case/stratum belongs to one study.  Crossing datasets must resolve
        # a fresh valid case deterministically rather than carrying stale ids.
        intent["case_id"] = None
        intent["stratum"] = None
        return intent

    if field == "stratum":
        requested = str(value or "")
        if requested not in STRATUM_ORDER or requested == stratum:
            return None
        intent["stratum"] = requested
        intent["case_id"] = None
        return intent

    if field == "case_id":
        requested = str(value or "").strip()
        if not requested or requested == case_id:
            return None
        intent["case_id"] = requested
        # Exact case identity is more specific than a possibly stale stratum.
        intent["stratum"] = None
        return intent

    if field == "model_id":
        requested = str(value or "")
        if requested not in MODEL_LABELS or requested == model_id:
            return None
        intent["model_id"] = requested
        return intent

    if field == "evidence_level":
        requested = str(value or "")
        if requested not in VALID_EVIDENCE or requested == evidence:
            return None
        intent["evidence_level"] = requested
        return intent

    if field == "tab":
        requested = str(value or "")
        if requested not in VALID_TABS or requested == tab:
            return None
        intent["tab"] = requested
        return intent

    return None

def landscape_cases_intent(selection: Mapping[str, Any] | None, canonical: Mapping[str, Any] | None) -> dict[str, str] | None:
    """Convert one certified usable Plotly point into canonical Case intent."""
    if not isinstance(selection, Mapping) or str(selection.get("usable") or "") != "USABLE":
        return None
    ds = _single_study_scope(selection.get("dataset"))
    case = str(selection.get("case_id") or "").strip()
    model = str(selection.get("model_id") or "")
    evidence = str(selection.get("evidence_level") or "")
    generation_id = str(selection.get("generation_id") or "").strip()
    if ds is None or not case or model not in MODEL_LABELS or evidence not in VALID_EVIDENCE or not generation_id:
        return None
    if _canonical_state_value(canonical, "generation_id") == generation_id:
        return None
    return {
        "kind": "landscape",
        "dataset": ds,
        "case_id": case,
        "model_id": model,
        "evidence_level": evidence,
        "stratum": _canonical_state_value(canonical, "stratum") or STRATUM_ORDER[0],
        "tab": _canonical_state_value(canonical, "tab") or "landscape",
    }


def _to_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return False
    return str(value).strip().lower() in {"1", "true", "yes"}


def _safe_int(value: object, default: int = 0) -> int:
    if value is None or pd.isna(value):
        return default
    return int(value)


def _safe_float(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _display_percent(locale: str, value: object) -> str:
    return format_percent(locale, value, decimals=2) if value is not None and pd.notna(value) else "—"


def _generation_display(locale: str, row: Mapping[str, Any]) -> dict[str, Any]:
    generation = dict(row)
    for metric in (
        "end_to_end_faithfulness_yield",
        "resolved_faithfulness",
        "verifiability",
        "conservative_faithfulness",
    ):
        generation[f"{metric}_display"] = _display_percent(locale, generation.get(metric))
    model_id = str(generation.get("model_id", ""))
    generation["model_label"] = MODEL_LABELS.get(model_id, model_id)
    generation["is_unusable"] = _to_bool(generation.get("is_unusable"))
    generation["usable"] = _to_bool(generation.get("usable"))
    return generation


@dataclass(frozen=True)
class CasesModelV3:
    scope: str
    locale: str
    title: str
    case_ids: tuple[str, ...]
    model_ids: tuple[str, ...]
    evidence_levels: tuple[str, ...]
    selected_case_id: str
    selected_model_id: str
    selected_evidence_level: str
    case_summary: dict[str, Any]
    generation: dict[str, Any]
    claims: tuple[dict[str, Any], ...]
    capabilities: dict[str, Any]
    strata: tuple[str, ...]
    selected_stratum: str
    initial_tab: str
    generation_rows: tuple[dict[str, Any], ...]
    case_records: tuple[dict[str, Any], ...]
    status_counts: tuple[dict[str, Any], ...]
    claim_type_status: tuple[dict[str, Any], ...]
    section_profile: tuple[dict[str, Any], ...]
    stratum_case_ids: tuple[str, ...]

    @property
    def selected_generation_id(self) -> str:
        return str(self.generation["generation_id"])

    @property
    def selected_identity(self) -> dict[str, str]:
        return {
            "dataset": self.scope,
            "case_id": self.selected_case_id,
            "generation_id": self.selected_generation_id,
            "model_id": self.selected_model_id,
            "evidence_level": self.selected_evidence_level,
        }


def _case_universe(index: pd.DataFrame, generations: pd.DataFrame) -> pd.DataFrame:
    strata = (
        generations[["case_id", "selection_stratum", "case_order"]]
        .drop_duplicates(subset=["case_id"])
        .copy()
    )
    strata["case_id"] = strata["case_id"].astype(str)
    base = index.copy()
    base["case_id"] = base["case_id"].astype(str)
    merged = base.merge(strata, on="case_id", how="left", validate="one_to_one")
    if merged["selection_stratum"].isna().any():
        raise ValueError("Every certified case must have one selection_stratum")
    return merged.sort_values(["case_order", "case_id"], kind="stable").reset_index(drop=True)


def _valid_strata(case_universe: pd.DataFrame) -> tuple[str, ...]:
    present = set(case_universe["selection_stratum"].astype(str))
    return tuple(value for value in STRATUM_ORDER if value in present)


def _status_counts(generation: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    source = {
        "SUPPORTED": "supported_count",
        "NOT_VERIFIABLE": "not_verifiable_count",
        "UNSUPPORTED": "unsupported_count",
        "CONTRADICTED": "contradicted_count",
        "NOT_APPLICABLE": "not_applicable_count",
    }
    total = _safe_int(generation.get("claim_count"))
    rows: list[dict[str, Any]] = []
    for status in STATUS_ORDER:
        count = _safe_int(generation.get(source[status]))
        rows.append({
            "validation_status": status,
            "claim_count": count,
            "share": (count / total) if total else None,
            "denominator": total,
        })
    return tuple(rows)


def _claim_type_status(claim_rows: pd.DataFrame) -> tuple[dict[str, Any], ...]:
    if claim_rows.empty:
        return ()
    grouped = (
        claim_rows.groupby(["claim_type", "validation_status"], dropna=False)
        .size()
        .reset_index(name="claim_count")
    )
    totals = grouped.groupby("claim_type")["claim_count"].sum().to_dict()
    rows: list[dict[str, Any]] = []
    for _, row in grouped.iterrows():
        claim_type = str(row["claim_type"])
        count = int(row["claim_count"])
        denom = int(totals.get(claim_type, 0))
        rows.append({
            "claim_type": claim_type,
            "validation_status": str(row["validation_status"]),
            "claim_count": count,
            "share_within_type": count / denom if denom else None,
            "claim_type_denominator": denom,
        })
    return tuple(rows)


def _section_profile(claim_rows: pd.DataFrame) -> tuple[dict[str, Any], ...]:
    if claim_rows.empty:
        return ()
    grouped = claim_rows.groupby("source_section", dropna=False).size().reset_index(name="claim_count")
    grouped["source_section"] = grouped["source_section"].fillna("N/A").astype(str)
    grouped = grouped.sort_values(["claim_count", "source_section"], ascending=[False, True], kind="stable")
    return tuple(grouped.to_dict(orient="records"))


def build_cases_model(
    repo: DashboardRepositoryV3,
    scope: str,
    locale: object,
    *,
    case_id: str | None = None,
    model_id: str | None = None,
    evidence_level: str | None = None,
    stratum: str | None = None,
    tab: str | None = None,
    search: str | None = None,
) -> CasesModelV3:
    loc = normalize_locale(locale)
    resolved = repo.validate_scope(scope)
    if resolved == "CROSS_DATASET":
        raise ValueError("Case Explorer requires a study scope; CROSS_DATASET is a comparison scope")

    query = parse_cases_state(search)
    if query["dataset"] in (None, resolved):
        case_id = query["case_id"] or case_id
        model_id = query["model_id"] or model_id
        evidence_level = query["evidence"] or evidence_level
        stratum = query["stratum"] or stratum
        tab = query["tab"] or tab

    index = repo.study_table("case_index", resolved)
    generations = repo.study_table("case_generation_metrics", resolved)
    claims = repo.study_table("case_claim_diagnostics", resolved)
    caps = repo.study_table("case_detail_capabilities", resolved)
    if len(caps) != 1:
        raise ValueError(f"Expected one case capability row for {resolved}")

    universe = _case_universe(index, generations)
    strata = _valid_strata(universe)

    requested_case = str(case_id) if case_id is not None else None
    requested_stratum = str(stratum) if stratum is not None else None
    case_to_stratum = dict(zip(universe["case_id"].astype(str), universe["selection_stratum"].astype(str)))
    if requested_stratum not in strata:
        requested_stratum = case_to_stratum.get(requested_case) if requested_case in case_to_stratum else None
    selected_stratum = requested_stratum if requested_stratum in strata else strata[0]

    all_case_ids = tuple(universe["case_id"].astype(str).tolist())
    stratum_cases = universe.loc[universe["selection_stratum"].astype(str).eq(selected_stratum)]
    stratum_case_ids = tuple(stratum_cases["case_id"].astype(str).tolist())
    selected_case = requested_case if requested_case in stratum_case_ids else stratum_case_ids[0]

    case_generations = generations.loc[generations["case_id"].astype(str).eq(selected_case)].copy()
    case_generations = case_generations.sort_values(["model_order", "evidence_order"], kind="stable")
    if len(case_generations) != 18:
        raise ValueError(f"Expected exactly 18 certified generations for case {selected_case}; got {len(case_generations)}")

    model_ids = tuple(
        case_generations[["model_id", "model_order"]]
        .drop_duplicates()
        .sort_values("model_order", kind="stable")["model_id"]
        .astype(str)
        .tolist()
    )
    selected_model = str(model_id) if model_id is not None and str(model_id) in model_ids else model_ids[0]
    model_generations = case_generations.loc[case_generations["model_id"].astype(str).eq(selected_model)]
    evidence_levels = tuple(
        model_generations.sort_values("evidence_order", kind="stable")["evidence_level"].astype(str).tolist()
    )
    selected_evidence = str(evidence_level) if evidence_level is not None and str(evidence_level) in evidence_levels else evidence_levels[0]
    selected = model_generations.loc[model_generations["evidence_level"].astype(str).eq(selected_evidence)]
    if len(selected) != 1:
        raise ValueError("Selected case/model/evidence identity must resolve to exactly one certified generation")

    generation = _generation_display(loc, selected.iloc[0].to_dict())
    generation_rows = tuple(_generation_display(loc, row) for row in case_generations.to_dict(orient="records"))

    claim_rows = claims.loc[claims["generation_id"].astype(str).eq(str(generation["generation_id"]))].reset_index(drop=True)
    expected_claims = _safe_int(generation.get("claim_count"))
    if len(claim_rows) != expected_claims:
        raise ValueError(
            f"Claim diagnostics count mismatch for {generation['generation_id']}: expected {expected_claims}, got {len(claim_rows)}"
        )

    case_row = universe.loc[universe["case_id"].astype(str).eq(selected_case)]
    if len(case_row) != 1:
        raise ValueError("Case identity is not unique")
    case_summary = case_row.iloc[0].to_dict()
    case_summary["selection_stratum"] = selected_stratum
    case_summary["stratum_label"] = STRATUM_LABELS.get(selected_stratum, selected_stratum)

    capabilities = caps.iloc[0].to_dict()
    for key in ("raw_generation_text", "raw_claim_text", "evidence_source_text"):
        if str(capabilities.get(key)) != "NOT_AVAILABLE_IN_M28_AUTHORIZED_LINEAGE":
            raise ValueError(f"Unexpected case-detail capability state for {key}: {capabilities.get(key)!r}")

    active_tab = str(tab) if tab in VALID_TABS else "landscape"
    return CasesModelV3(
        resolved,
        loc,
        f"{vt(loc,'cases')} · {vt(loc,resolved)}",
        all_case_ids,
        model_ids,
        evidence_levels,
        selected_case,
        selected_model,
        selected_evidence,
        case_summary,
        generation,
        tuple(claim_rows.to_dict(orient="records")),
        capabilities,
        strata,
        selected_stratum,
        active_tab,
        generation_rows,
        tuple(universe.to_dict(orient="records")),
        _status_counts(generation),
        _claim_type_status(claim_rows),
        _section_profile(claim_rows),
        stratum_case_ids,
    )


def claim_by_id(model: CasesModelV3, claim_id: str | None) -> dict[str, Any] | None:
    if not claim_id:
        return None
    return next((dict(row) for row in model.claims if str(row.get("claim_id")) == str(claim_id)), None)


def generation_from_landscape_click(click_data: dict[str, Any] | None) -> dict[str, str] | None:
    if not click_data:
        return None
    try:
        point = click_data["points"][0]
        custom = point.get("customdata")
        if not isinstance(custom, (list, tuple)) or len(custom) < 6:
            return None
        return {
            "dataset": str(custom[0]),
            "case_id": str(custom[1]),
            "model_id": str(custom[2]),
            "evidence_level": str(custom[3]),
            "generation_id": str(custom[4]),
            "usable": str(custom[5]),
        }
    except (KeyError, IndexError, TypeError):
        return None


def case_option_records(model: CasesModelV3) -> list[dict[str, str]]:
    records = []
    for row in model.case_records:
        if str(row.get("selection_stratum")) != model.selected_stratum:
            continue
        case_id = str(row["case_id"])
        complete = _to_bool(row.get("complete_case"))
        usable = _safe_int(row.get("usable_generation_count"))
        records.append({"value": case_id, "label": f"{case_id} · {'complete' if complete else f'{usable}/18 usable'}"})
    return records


def stratum_options(model: CasesModelV3) -> list[dict[str, str]]:
    return [{"value": value, "label": STRATUM_LABELS.get(value, value)} for value in model.strata]
