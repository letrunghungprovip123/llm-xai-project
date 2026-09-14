from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any
from urllib.parse import parse_qs

import pandas as pd

from research.python.dashboard.i18n import normalize_locale

from .i18n import vt
from .repository import DashboardRepositoryV3


VALID_TABS = ("study", "metrics", "traceability", "findings")
CAPABILITY_GAP = "NOT_MATERIALIZED_IN_VISUALIZATION_DATA_V3"


def _query_value(raw: dict[str, list[str]], *keys: str) -> str | None:
    for key in keys:
        value = str((raw.get(key) or [""])[0]).strip()
        if value:
            return value
    return None


def parse_methods_search(search: str | None) -> dict[str, str | None]:
    raw = parse_qs((search or "").lstrip("?"))
    tab = _query_value(raw, "tab")
    if tab not in VALID_TABS:
        tab = None
    return {
        "tab": tab,
        "metric_key": _query_value(raw, "metric_key"),
        "metric": _query_value(raw, "metric"),
        "report": _query_value(raw, "report", "report_number_id"),
        "table": _query_value(raw, "table", "table_name"),
        "finding": _query_value(raw, "finding", "finding_id"),
    }


def _metric_key(row: dict[str, Any]) -> str:
    return f"{row['metric_id']}::{row['family']}::{row['analysis_lane']}"


def _split_ref(value: object) -> tuple[str, ...]:
    if value is None or pd.isna(value):
        return ()
    text = str(value).strip()
    if not text:
        return ()
    for separator in ("|", ";"):
        if separator in text:
            return tuple(part.strip() for part in text.split(separator) if part.strip())
    return (text,)


@dataclass(frozen=True)
class MethodsModelV3:
    locale: str
    title: str
    release: dict[str, Any]
    research_questions: tuple[dict[str, Any], ...]
    metric_dictionary: tuple[dict[str, Any], ...]
    limitations: tuple[dict[str, Any], ...]
    findings: tuple[dict[str, Any], ...]
    method_evidence: dict[str, Any]
    report_source_index: tuple[dict[str, Any], ...]
    visualization_dictionary: tuple[dict[str, Any], ...]
    initial_tab: str
    selected_metric_key: str
    selected_report_id: str
    selected_table_name: str
    selected_finding_id: str

    @property
    def metric_keys(self) -> tuple[str, ...]:
        return tuple(str(row["metric_key"]) for row in self.metric_dictionary)

    @property
    def report_ids(self) -> tuple[str, ...]:
        return tuple(str(row["report_number_id"]) for row in self.report_source_index)

    @property
    def table_names(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(str(row["table_name"]) for row in self.visualization_dictionary))

    @property
    def finding_ids(self) -> tuple[str, ...]:
        return tuple(str(row["finding_id"]) for row in self.findings)


def _release_metadata(repo: DashboardRepositoryV3) -> dict[str, Any]:
    parent = repo.release.files[0].path.parent
    path = parent / "release_metadata.json"
    if not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def build_methods_model(repo: DashboardRepositoryV3, locale: object, *, search: str | None = None) -> MethodsModelV3:
    loc = normalize_locale(locale)
    omnibus = repo.table("omnibus_effects")
    contrasts = repo.table("planned_contrasts")
    margins = repo.table("margin_sensitivity_summary")
    primary_margin = margins.loc[margins["analysis_status"].astype(str).eq("PRIMARY_CERTIFIED")]
    release_metadata = _release_metadata(repo)
    if release_metadata.get("scientific_recomputation_allowed") is not False:
        raise ValueError("Certified visualization release must forbid scientific recomputation")

    methods = {
        "omnibus_test_methods": tuple(sorted(set(omnibus["test_method"].astype(str)))),
        "contrast_adjustments": tuple(sorted(set(contrasts["adjustment_method"].astype(str)))),
        "primary_subject_count": tuple(sorted(set(int(v) for v in omnibus["subject_count"]))),
        "primary_margin": float(primary_margin.iloc[0]["margin"]) if len(primary_margin) == 1 else None,
        "replication_scope": repo.release.replication_scope,
        "robust_recommendation_status": repo.release.robust_recommendation_status,
        "metric_formula_capability": CAPABILITY_GAP,
        "validator_readiness_capability": CAPABILITY_GAP,
        "template_readiness_capability": CAPABILITY_GAP,
        "scientific_recomputation_allowed": False,
    }
    release = {
        "release_id": repo.release.release_id,
        "version": repo.release.version,
        "parent_release_id": repo.release.parent_release_id,
        "replication_scope": repo.release.replication_scope,
        "robust_recommendation_status": repo.release.robust_recommendation_status,
        "table_count": repo.release.table_count,
        "visualization_version": release_metadata.get("visualization_version", repo.release.version),
        "scientific_recomputation_allowed": False,
    }

    research_questions = tuple(repo.table("research_questions").to_dict(orient="records"))
    metric_rows = repo.table("metric_dictionary").sort_values(["analysis_lane", "family", "metric_id"], kind="stable").to_dict(orient="records")
    enriched_metrics = []
    for row in metric_rows:
        rec = dict(row)
        rec["metric_key"] = _metric_key(rec)
        enriched_metrics.append(rec)
    limitations = tuple(repo.table("limitations").sort_values(["severity", "category", "limitation_id"], ascending=[True, True, True], kind="stable").to_dict(orient="records"))
    findings = tuple(repo.table("findings").sort_values(["research_question_id", "finding_id"], kind="stable").to_dict(orient="records"))
    reports = tuple(repo.table("report_source_index").sort_values("report_number_id", kind="stable").to_dict(orient="records"))
    schema = tuple(repo.table("visualization_dictionary").sort_values(["table_name", "column_name"], kind="stable").to_dict(orient="records"))

    query = parse_methods_search(search)
    metric_keys = [str(row["metric_key"]) for row in enriched_metrics]
    report_ids = [str(row["report_number_id"]) for row in reports]
    table_names = list(dict.fromkeys(str(row["table_name"]) for row in schema))
    finding_ids = [str(row["finding_id"]) for row in findings]

    primary_e2e = [key for key in metric_keys if key.startswith("end_to_end_faithfulness_yield::") and key.endswith("::PRIMARY")]
    default_metric = primary_e2e[0] if primary_e2e else metric_keys[0]
    requested_metric_key = query["metric_key"]
    requested_metric_id = query["metric"]
    if requested_metric_key in metric_keys:
        selected_metric = str(requested_metric_key)
    elif requested_metric_id:
        matching = [key for key in metric_keys if key.split("::", 1)[0] == requested_metric_id]
        # Bare metric_id remains a backward-compatible navigation hint only when
        # it uniquely identifies a registry row.  Ambiguous metric ids must not
        # silently claim exact provenance; canonical deep-links use metric_key.
        selected_metric = matching[0] if len(matching) == 1 else default_metric
    else:
        selected_metric = default_metric

    selected_report = str(query["report"]) if query["report"] in report_ids else report_ids[0]
    selected_table = str(query["table"]) if query["table"] in table_names else table_names[0]
    selected_finding = str(query["finding"]) if query["finding"] in finding_ids else finding_ids[0]
    initial_tab = str(query["tab"]) if query["tab"] in VALID_TABS else "study"

    return MethodsModelV3(
        loc,
        vt(loc, "methods"),
        release,
        research_questions,
        tuple(enriched_metrics),
        limitations,
        findings,
        methods,
        reports,
        schema,
        initial_tab,
        selected_metric,
        selected_report,
        selected_table,
        selected_finding,
    )


def metric_by_key(model: MethodsModelV3, metric_key: str | None) -> dict[str, Any] | None:
    if not metric_key:
        return None
    return next((dict(row) for row in model.metric_dictionary if str(row.get("metric_key")) == str(metric_key)), None)


def report_by_id(model: MethodsModelV3, report_id: str | None) -> dict[str, Any] | None:
    if not report_id:
        return None
    return next((dict(row) for row in model.report_source_index if str(row.get("report_number_id")) == str(report_id)), None)


def schema_for_table(model: MethodsModelV3, table_name: str | None) -> list[dict[str, Any]]:
    if not table_name:
        return []
    return [dict(row) for row in model.visualization_dictionary if str(row.get("table_name")) == str(table_name)]


def limitation_by_id(model: MethodsModelV3, limitation_id: str | None) -> dict[str, Any] | None:
    if not limitation_id:
        return None
    return next((dict(row) for row in model.limitations if str(row.get("limitation_id")) == str(limitation_id)), None)


def finding_by_id(model: MethodsModelV3, finding_id: str | None) -> dict[str, Any] | None:
    if not finding_id:
        return None
    row = next((dict(item) for item in model.findings if str(item.get("finding_id")) == str(finding_id)), None)
    if row is None:
        return None
    report_refs = _split_ref(row.get("supporting_report_numbers"))
    limitation_refs = _split_ref(row.get("limitation_refs"))
    row["supporting_report_refs"] = report_refs
    row["limitation_ref_ids"] = limitation_refs
    row["supporting_reports"] = tuple(filter(None, (report_by_id(model, ref) for ref in report_refs)))
    row["limitations"] = tuple(filter(None, (limitation_by_id(model, ref) for ref in limitation_refs)))
    return row
