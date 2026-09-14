"""Typed immutable contracts used by the dashboard presentation layer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import pandas as pd


@dataclass(frozen=True)
class DatasetContract:
    """Manifest contract for one presentation dataset."""

    name: str
    path: Path
    row_count: int
    column_count: int
    sha256: str


@dataclass(frozen=True)
class GateStatus:
    """One certified release gate exposed in the application shell."""

    gate_id: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class ReleaseMetadata:
    """Release identity and gate state displayed by the dashboard."""

    analytical_release_id: str
    visualization_release_id: str
    visualization_version: str
    parent_release_id: str
    parent_git_commit: str
    parent_git_branch: str
    parent_source_tree_sha256: str
    research_question_count: int
    dataset_count: int
    validation_check_count: int
    gates: tuple[GateStatus, ...]

    @property
    def short_commit(self) -> str:
        return self.parent_git_commit[:8]


@dataclass(frozen=True)
class OverviewKpi:
    """One report-facing KPI card."""

    metric_id: str
    label: str
    value: int | float
    display_value: str
    subtext: str | None
    denominator: str
    source: str
    tooltip: str
    variant: str = "default"


@dataclass(frozen=True)
class OverviewFinding:
    """A deterministic finding derived from certified results."""

    finding_id: str
    title: str
    statement: str
    source: str
    target_path: str | None
    tone: str


@dataclass(frozen=True)
class OverviewData:
    """Complete immutable view model required by Executive Overview."""

    release: ReleaseMetadata
    kpis: tuple[OverviewKpi, ...]
    option_performance: pd.DataFrame
    omnibus_tests: pd.DataFrame
    unusable_generations: pd.DataFrame
    findings: tuple[OverviewFinding, ...]


@dataclass(frozen=True)
class EffectivenessData:
    """Immutable certified inputs required by Page 2."""

    release: ReleaseMetadata
    option_performance: pd.DataFrame
    descriptive_statistics: pd.DataFrame
    omnibus_tests: pd.DataFrame
    paired_tests: pd.DataFrame
    conditional_paired_tests: pd.DataFrame
    complete_case_omnibus_tests: pd.DataFrame
    sensitivity_summary: pd.DataFrame
    unusable_generations: pd.DataFrame
    case_metrics: pd.DataFrame


@dataclass(frozen=True)
class FocusedOption:
    """One model–evidence configuration selected for contextual emphasis."""

    option_id: str
    model_id: str
    model_label: str
    evidence_level: str
    evidence_label: str
    mean_e2e: float
    median_e2e: float
    p10_e2e: float
    usability_rate: float
    planned_count: int
    usable_count: int
    unusable_count: int
    pipeline_loss: float
    mean_latency_seconds: float | None
    mean_total_tokens: float | None


@dataclass(frozen=True)
class EvidenceConditionProfile:
    """Human-facing summary of one categorical evidence condition."""

    evidence_level: str
    evidence_label: str
    evidence_order: int
    intended_role: str
    selection_method: str
    case_count: int
    median_selected_evidence_count: float
    median_evidence_item_count: float | None
    median_feature_item_count: float | None
    median_concept_item_count: float | None
    mean_coverage: float | None
    mean_diversity: float | None
    median_adaptive_k: float | None
    median_concept_group_count: float | None
    has_semantic_guidance: bool
    has_concept_evidence: bool
    has_structural_skeleton: bool
    median_backend_factor_slots: float
    median_required_sections: float


@dataclass(frozen=True)
class MechanismsData:
    """Immutable certified inputs and derived views required by Page 3."""

    release: ReleaseMetadata
    evidence_design: pd.DataFrame
    evidence_profiles: tuple[EvidenceConditionProfile, ...]
    evidence_utilization: pd.DataFrame
    narrative_structure: pd.DataFrame
    mechanism_breakdowns: pd.DataFrame
    pipeline_failures: pd.DataFrame
    claim_status_by_option: pd.DataFrame
    claim_difficulty_by_type: pd.DataFrame
    pipeline_stage_summary: pd.DataFrame
    failure_matrix: pd.DataFrame
    narrative_model_summary: pd.DataFrame
    safe_phrase_summary: pd.DataFrame


@dataclass(frozen=True)
class DecisionCriterion:
    """One certified criterion available to the Decision Studio."""

    criterion_id: str
    label: str
    direction: str
    group: str
    criterion_order: int
    default_weight: float
    unit: str


@dataclass(frozen=True)
class ScenarioDefinition:
    """One frozen deployment-priority scenario."""

    scenario_id: str
    label: str
    description: str
    scenario_order: int
    weights: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class CustomDecisionResult:
    """Exploratory What-if result separated from certified scenarios."""

    raw_weights: Mapping[str, float]
    normalized_weights: Mapping[str, float]
    ranking: pd.DataFrame
    contributions: pd.DataFrame
    recommended_option_id: str | None


@dataclass(frozen=True)
class DecisionData:
    """Immutable certified inputs required by Page 4."""

    release: ReleaseMetadata
    scenarios: tuple[ScenarioDefinition, ...]
    criteria: tuple[DecisionCriterion, ...]
    scenario_options: pd.DataFrame
    criterion_contributions: pd.DataFrame
    recommendation_evidence: pd.DataFrame


@dataclass(frozen=True)
class MeasurementShift:
    """One Candidate–V4 measurement shift for a model–evidence option."""

    model_id: str
    model_label: str
    evidence_level: str
    metric_id: str
    candidate_value: float | None
    sensitivity_value: float | None
    delta: float | None
    paired_count: int


@dataclass(frozen=True)
class BaselineComparison:
    """One case-paired LLM–Template comparison summary."""

    model_id: str
    model_label: str
    evidence_scope: str
    metric_id: str
    llm_value: float | None
    template_value: float | None
    paired_delta: float | None
    paired_case_count: int




@dataclass(frozen=True)
class CaseSummary:
    """Privacy-preserving identity and cohort context for one canonical case."""

    case_id: int
    selection_stratum: str
    prediction_outcome: str
    true_label_text: str
    predicted_label: str
    prediction_probability: float
    decision_threshold: float
    distance_from_threshold: float
    complete_llm_case: bool
    unusable_slot_count: int


@dataclass(frozen=True)
class CaseGeneration:
    """One generator × evidence result for a selected canonical case."""

    case_id: int
    generator_family: str
    generator_id: str
    generator_label: str
    evidence_level: str
    usable: bool
    end_to_end_faithfulness_yield: float
    conservative_faithfulness: float | None
    verifiability: float | None
    supported_count: int
    output_word_count: int


@dataclass(frozen=True)
class FocusedCaseData:
    """Immutable view model for the complete Case Explorer drill-down."""

    release: ReleaseMetadata
    case_summary: CaseSummary
    generations: pd.DataFrame
    evidence_packages: pd.DataFrame
    evidence_package: pd.Series
    utilization: pd.Series
    narrative_structure: pd.Series
    validator_pair: pd.Series
    template_pair: pd.Series


@dataclass(frozen=True)
class RobustnessData:
    """Immutable certified inputs required by Page 5."""

    release: ReleaseMetadata
    validator_pairs: pd.DataFrame
    validator_summary: pd.DataFrame
    validator_tests: pd.DataFrame
    baseline_generations: pd.DataFrame
    baseline_options: pd.DataFrame
    baseline_pairs: pd.DataFrame
    baseline_summary: pd.DataFrame
    baseline_tests: pd.DataFrame


@dataclass(frozen=True)
class ReleaseAudit:
    """Certified lineage and presentation-release identity for Page 7."""

    analytical_release_id: str
    visualization_release_id: str
    visualization_version: str
    parent_release_id: str
    parent_git_commit: str
    parent_git_branch: str
    source_tree_sha256: str
    verified_parent_artifact_count: int
    verified_baseline_artifact_count: int
    dataset_count: int
    validation_check_count: int

    @property
    def short_commit(self) -> str:
        return self.parent_git_commit[:8]

    @property
    def short_tree_sha(self) -> str:
        return self.source_tree_sha256[:12]


@dataclass(frozen=True)
class ValidationGateRecord:
    """One frozen upstream or presentation validation gate."""

    layer_id: str
    layer_label: str
    exit_gate: str
    expected_gate: str
    passed: bool
    check_count: int | None
    failed_check_count: int | None
    source_artifact: str
    meaning: str


@dataclass(frozen=True)
class ResearchQuestionRecord:
    """One parsed research-question registry entry."""

    rq_id: str
    rq_order: int
    title: str
    question: str
    status: str
    population: str
    inference_unit: str
    primary_metrics: tuple[str, ...]
    supporting_metrics: tuple[str, ...]
    primary_sources: tuple[str, ...]
    dashboard_pages: tuple[str, ...]
    interpretation_restrictions: tuple[str, ...]


@dataclass(frozen=True)
class MethodsData:
    """Immutable certified view model for Reproducibility & Methods."""

    release: ReleaseMetadata
    release_audit: ReleaseAudit
    validation_gates: tuple[ValidationGateRecord, ...]
    certified_numbers: pd.DataFrame
    research_questions: tuple[ResearchQuestionRecord, ...]
    metric_visibility: pd.DataFrame
    visualization_dictionary: pd.DataFrame
    artifact_inventory: pd.DataFrame
    statistical_families: pd.DataFrame
    denominator_ledger: pd.DataFrame
    limitations: pd.DataFrame
    reproduction_steps: pd.DataFrame


@dataclass(frozen=True)
class ReleaseGuardResult:
    """Result of fail-closed validation before any page is rendered."""

    ready: bool
    release: ReleaseMetadata | None
    datasets: Mapping[str, DatasetContract]
    errors: tuple[str, ...]
    validation_payload: Mapping[str, Any]
    manifest_payload: Mapping[str, Any]

    def require_ready(self) -> ReleaseMetadata:
        """Return metadata or raise one consolidated error."""

        if not self.ready or self.release is None:
            details = "\n- ".join(self.errors) or "Unknown release error."
            raise RuntimeError(
                "Certified dashboard release is not ready:\n- " + details
            )
        return self.release
