"""Curated English display labels for the certified dashboard.

This module deliberately separates stable semantic identifiers from UI copy.
Future i18n work should translate these semantic keys instead of attempting to
localize raw snake_case values at runtime.
"""

from __future__ import annotations

import re


DISPLAY_LABELS: dict[str, str] = {
    # Metrics and certified report numbers.
    "end_to_end_faithfulness_yield": "End-to-end faithfulness yield",
    "p10_end_to_end_yield": "P10 end-to-end yield",
    "usability_rate": "Usability rate",
    "conservative_faithfulness": "Conservative faithfulness",
    "verifiability": "Verifiability",
    "resolved_faithfulness": "Resolved faithfulness",
    "supported_claim_count": "Supported claim count",
    "candidate_v4_delta": "Candidate–V4 delta",
    "mean_end_to_end_operational_faithfulness": "Mean operational E2E faithfulness",
    "micro_conservative_faithfulness": "Micro conservative faithfulness",
    "micro_verifiability": "Micro verifiability",
    "micro_resolved_faithfulness": "Micro resolved faithfulness",
    "planned_llm_generations": "Planned LLM generations",
    "usable_llm_generations": "Usable LLM generations",
    "unusable_llm_generations": "Unusable LLM generations",
    "final_atomic_claims": "Final atomic claims",
    "applicable_claims": "Applicable claims",
    "resolved_claims": "Resolved claims",
    "primary_planned_pair_count": "Primary planned pair count",
    "primary_adjusted_significant_pair_count": "Primary adjusted significant pair count",
    # Report sections and roles.
    "denominator": "Denominator",
    "primary_metric": "Primary metrics",
    "claim_status": "Claim statuses",
    "planned_contrasts": "Planned contrasts",
    "CERTIFIED_HEADLINE": "Certified headline",
    "CERTIFIED_SUPPORTING": "Certified supporting",
    # Research and page identifiers.
    "executive_overview": "Executive overview",
    "performance_reliability": "Effectiveness and reliability",
    "mechanisms_diagnostics": "Evidence, mechanisms and diagnostics",
    "decision_studio": "Decision studio",
    "measurement_robustness": "Measurement robustness",
    "template_baseline_comparison": "Template baseline comparison",
    "case_explorer": "Case explorer",
    "reproducibility": "Reproducibility and methods",
    "ACTIVE": "Active",
    "ACTIVE_AFTER_BASELINE_COMPARISON_READY": "Active after baseline certification",
    # Visibility / supporting labels.
    "SUPPORTING_OR_IDENTIFIER": "Supporting field or identifier",
    "DASHBOARD_ENABLED": "Dashboard-facing tiers",
}


_TOKEN_LABELS: dict[str, str] = {
    "api": "API",
    "ci": "CI",
    "csv": "CSV",
    "e2e": "E2E",
    "id": "ID",
    "json": "JSON",
    "llm": "LLM",
    "llms": "LLMs",
    "p10": "P10",
    "rq": "RQ",
    "sha": "SHA",
    "shap": "SHAP",
    "ui": "UI",
    "url": "URL",
    "v4": "V4",
}


_RQ_PATTERN = re.compile(r"^rq(\d+)$", re.IGNORECASE)
_S_PATTERN = re.compile(r"^s(\d+)$", re.IGNORECASE)


def display_label(value: object) -> str:
    """Return a human-facing label without corrupting scientific acronyms.

    Raw technical identifiers remain available separately in audit details and
    exports. This function is intentionally deterministic and locale-neutral.
    """

    text = str(value).strip()
    if not text:
        return ""
    if text in DISPLAY_LABELS:
        return DISPLAY_LABELS[text]

    normalized = text.replace("–", "_").replace("-", "_")
    tokens = [token for token in normalized.split("_") if token]
    if not tokens:
        return text

    rendered: list[str] = []
    for token in tokens:
        lower = token.lower()
        rq_match = _RQ_PATTERN.match(lower)
        s_match = _S_PATTERN.match(lower)
        if rq_match:
            rendered.append(f"RQ{rq_match.group(1)}")
        elif s_match:
            rendered.append(f"S{s_match.group(1)}")
        elif lower == "sha256":
            rendered.append("SHA-256")
        elif lower in _TOKEN_LABELS:
            rendered.append(_TOKEN_LABELS[lower])
        else:
            rendered.append(lower)

    # Preserve common paired scientific identities.
    result = " ".join(rendered)
    result = result.replace("Candidate V4", "Candidate–V4")
    result = result.replace("LLM Template", "LLM–Template")
    result = result.replace("LLM vs template", "LLM–Template")
    result = result.replace("S1 S4", "S1–S4")

    first = result.split(" ", 1)[0]
    if first not in set(_TOKEN_LABELS.values()) and not _RQ_PATTERN.match(first) and not _S_PATTERN.match(first):
        result = result[:1].upper() + result[1:]
    return result


def reporting_role_label(value: object) -> str:
    return DISPLAY_LABELS.get(str(value), display_label(value))


def research_status_label(value: object) -> str:
    return DISPLAY_LABELS.get(str(value), display_label(value))


def gate_state_label(passed: bool) -> str:
    return "Ready" if passed else "Blocked"
