"""Stable semantic identifiers mapped to localized domain labels."""

from __future__ import annotations

from .translator import t
from .types import LocaleCode


# These are scientific names, acronyms, model identities, standards, or file
# formats. They may remain unchanged on both locale surfaces without counting
# as accidental English/Vietnamese mixing.
TECHNICAL_ALLOWLIST: frozenset[str] = frozenset(
    {
        "AG Grid",
        "API",
        "Candidate",
        "CSV",
        "Dash",
        "DeepSeek V4 Flash",
        "E2E",
        "Holm",
        "Home Credit",
        "JSON",
        "LLM",
        "LLM-XAI",
        "P10",
        "Pareto",
        "Phi-4 Mini Instruct",
        "Plotly",
        "Qwen3 8B",
        "RQ1",
        "RQ2",
        "RQ3",
        "RQ4",
        "RQ5",
        "RQ6",
        "S0",
        "S1",
        "S2",
        "S3",
        "S4",
        "S5",
        "SHA-256",
        "SHAP",
        "Template",
        "V4",
    }
)


def is_technical_allowlisted(value: object) -> bool:
    return str(value).strip() in TECHNICAL_ALLOWLIST


def technical_label(value: object) -> str:
    """Return an explicitly allowlisted technical identity unchanged."""

    text = str(value).strip()
    if text not in TECHNICAL_ALLOWLIST:
        raise ValueError(f"Technical label is not allowlisted: {text!r}.")
    return text


def domain_label(
    locale: LocaleCode | str,
    namespace: str,
    identifier: object,
) -> str:
    """Translate one stable domain identity.

    No generic title-casing fallback is permitted. Unknown identifiers must be
    added deliberately to both catalogs before they appear in user-facing UI.
    """

    normalized_namespace = str(namespace).strip().lower()
    normalized_identifier = str(identifier).strip()
    if not normalized_namespace or not normalized_identifier:
        raise ValueError("Domain namespace and identifier must be non-empty.")
    return t(locale, f"domain.{normalized_namespace}.{normalized_identifier}")


def metric_label(locale: LocaleCode | str, metric_id: object) -> str:
    return domain_label(locale, "metric", metric_id)


def evidence_label(locale: LocaleCode | str, evidence_level: object) -> str:
    return domain_label(locale, "evidence", evidence_level)


def claim_status_label(locale: LocaleCode | str, status: object) -> str:
    return domain_label(locale, "claim_status", status)


def page_label(locale: LocaleCode | str, page_id: object) -> str:
    return domain_label(locale, "page", page_id)


def reporting_role_label(locale: LocaleCode | str, role: object) -> str:
    return domain_label(locale, "reporting_role", role)


def visibility_tier_label(locale: LocaleCode | str, tier: object) -> str:
    return domain_label(locale, "visibility_tier", tier)


def utilization_metric_label(locale: LocaleCode | str, metric_id: object) -> str:
    return domain_label(locale, "utilization_metric", metric_id)


def claim_type_label(locale: LocaleCode | str, claim_type: object) -> str:
    return domain_label(locale, "claim_type", claim_type)


def reason_code_label(locale: LocaleCode | str, reason_code: object) -> str:
    return domain_label(locale, "reason_code", reason_code)


def pipeline_stage_label(locale: LocaleCode | str, stage: object) -> str:
    return domain_label(locale, "pipeline_stage", stage)


def failure_type_label(locale: LocaleCode | str, failure_type: object) -> str:
    return domain_label(locale, "failure_type", failure_type)


__all__ = [
    "TECHNICAL_ALLOWLIST",
    "claim_type_label",
    "failure_type_label",
    "pipeline_stage_label",
    "reason_code_label",
    "utilization_metric_label",
    "claim_status_label",
    "domain_label",
    "evidence_label",
    "is_technical_allowlisted",
    "metric_label",
    "page_label",
    "reporting_role_label",
    "technical_label",
    "visibility_tier_label",
]
