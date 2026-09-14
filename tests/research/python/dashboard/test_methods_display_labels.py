"""Display-label contract tests that prepare Page 7 for later i18n."""

from __future__ import annotations

from research.python.dashboard.display_labels import (
    display_label,
    reporting_role_label,
    research_status_label,
)


def test_display_labels_preserve_scientific_acronyms() -> None:
    assert display_label("planned_llm_generations") == "Planned LLM generations"
    assert display_label("end_to_end_faithfulness_yield") == "End-to-end faithfulness yield"
    assert display_label("candidate_v4_delta") == "Candidate–V4 delta"
    assert display_label("parent_source_tree_sha256") == "Parent source tree SHA-256"
    assert display_label("rq6") == "RQ6"


def test_display_labels_hide_raw_reporting_codes_from_primary_ui() -> None:
    assert reporting_role_label("CERTIFIED_HEADLINE") == "Certified headline"
    assert reporting_role_label("CERTIFIED_SUPPORTING") == "Certified supporting"
    assert research_status_label("ACTIVE") == "Active"
    assert (
        research_status_label("ACTIVE_AFTER_BASELINE_COMPARISON_READY")
        == "Active after baseline certification"
    )


def test_unknown_identifiers_use_sentence_case_not_title_case() -> None:
    assert display_label("selected_feature_mention_rate") == "Selected feature mention rate"
    assert display_label("llm_vs_template_case_pairs") == "LLM–Template case pairs"
