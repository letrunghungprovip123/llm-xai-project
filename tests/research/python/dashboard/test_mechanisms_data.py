"""Certified Page-3 data-contract tests."""

from research.python.dashboard.data.repository import DashboardRepository


def test_mechanisms_sources_and_profiles_are_complete() -> None:
    repository = DashboardRepository()
    data = repository.mechanisms_data()
    assert len(data.evidence_design) == 216
    assert len(data.evidence_profiles) == 6
    assert tuple(item.evidence_level for item in data.evidence_profiles) == (
        "S0", "S1", "S2", "S3", "S4", "S5"
    )
    assert data.evidence_profiles[0].median_selected_evidence_count == 0
    assert data.evidence_profiles[4].has_concept_evidence is True
    assert data.evidence_profiles[5].has_structural_skeleton is True


def test_llm_mechanism_layer_excludes_template_and_reconciles_counts() -> None:
    data = DashboardRepository().mechanisms_data()
    assert len(data.evidence_utilization) == 648
    assert len(data.narrative_structure) == 648
    assert not data.evidence_utilization["generator_id"].str.contains("template", case=False).any()
    assert int(data.claim_status_by_option["claim_count"].sum()) == 14667
    assert len(data.claim_difficulty_by_type) == 12


def test_pipeline_and_utilization_views_preserve_certified_identities() -> None:
    repository = DashboardRepository()
    data = repository.mechanisms_data()
    assert len(data.pipeline_failures) == 10
    assert data.failure_matrix["failure_count"].sum() == 10
    counts = data.pipeline_failures.groupby("model_id").size().to_dict()
    assert counts == {"deepseek_v4_flash": 3, "phi4_mini_instruct": 7}
    assert len(data.pipeline_stage_summary) == 15
    assert len(repository.utilization_option_summary("feature_use")) == 18
    assert len(repository.utilization_option_summary("concept_use")) == 18
    assert len(repository.utilization_option_summary("supported_claim_yield")) == 18
