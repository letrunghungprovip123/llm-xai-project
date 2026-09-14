"""Stable domain-ID localization tests."""

from __future__ import annotations

import pytest

from research.python.dashboard.i18n import (
    MissingTranslationError,
    claim_status_label,
    evidence_label,
    is_technical_allowlisted,
    metric_label,
    page_label,
    reporting_role_label,
    technical_label,
    visibility_tier_label,
)


def test_metric_labels_are_resolved_from_stable_ids() -> None:
    assert metric_label("vi", "verifiability") == "Khả năng kiểm chứng"
    assert metric_label("en", "verifiability") == "Verifiability"


def test_page_evidence_and_status_labels_are_localized() -> None:
    assert page_label("vi", "methods") == "Khả năng tái lập & Phương pháp"
    assert evidence_label("vi", "S4") == "S4 · Bằng chứng phong phú"
    assert claim_status_label("vi", "NOT_VERIFIABLE") == "Không thể kiểm chứng"


def test_reporting_and_visibility_roles_are_localized() -> None:
    assert (
        reporting_role_label("vi", "CERTIFIED_HEADLINE")
        == "Chỉ số chính đã chứng nhận"
    )
    assert (
        visibility_tier_label("en", "C_INTERNAL_VALIDATION")
        == "Internal validation"
    )


def test_unknown_domain_identity_never_uses_generic_title_case_fallback() -> None:
    with pytest.raises(MissingTranslationError):
        metric_label("vi", "unknown_metric")


def test_only_explicit_technical_names_can_remain_unchanged() -> None:
    assert is_technical_allowlisted("LLM")
    assert is_technical_allowlisted("Qwen3 8B")
    assert technical_label("SHA-256") == "SHA-256"
    with pytest.raises(ValueError):
        technical_label("Some English sentence")
