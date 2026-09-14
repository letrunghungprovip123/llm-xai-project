"""Stable Page-1 figure registry used by downloads and static exports."""

from __future__ import annotations

from dataclasses import dataclass

from ..figures.overview import (
    FIG_OVERVIEW_E2E_HEATMAP,
    FIG_OVERVIEW_EVIDENCE_PROFILE,
)


@dataclass(frozen=True)
class FigureRegistryEntry:
    figure_id: str
    title: str
    source: str
    metric: str
    report_role: str


OVERVIEW_FIGURES = (
    FigureRegistryEntry(
        figure_id=FIG_OVERVIEW_E2E_HEATMAP,
        title="Operational faithfulness across model–evidence options",
        source="option_performance.csv",
        metric="mean_end_to_end_yield",
        report_role="Primary RQ1 figure",
    ),
    FigureRegistryEntry(
        figure_id=FIG_OVERVIEW_EVIDENCE_PROFILE,
        title="Evidence-condition profiles by model",
        source="option_performance.csv",
        metric="mean_end_to_end_yield",
        report_role="Supporting RQ1 figure",
    ),
)

from ..figures.effectiveness import (
    FIG_EFFECTIVENESS_CONDITIONAL_HEATMAP,
    FIG_EFFECTIVENESS_LOSS_DECOMPOSITION,
    FIG_EFFECTIVENESS_OPERATIONAL_CONDITIONAL_GAP,
    FIG_EFFECTIVENESS_PRIMARY_EFFECT_SIZES,
    FIG_EFFECTIVENESS_RELIABILITY_MAP,
)

EFFECTIVENESS_FIGURES = (
    FigureRegistryEntry(
        figure_id=FIG_EFFECTIVENESS_RELIABILITY_MAP,
        title="Average performance versus lower-tail reliability",
        source="option_performance.csv",
        metric="mean_end_to_end_yield × p10_end_to_end_yield",
        report_role="Primary RQ1 reliability figure",
    ),
    FigureRegistryEntry(
        figure_id=FIG_EFFECTIVENESS_LOSS_DECOMPOSITION,
        title="Operational loss decomposition",
        source="option_performance.csv",
        metric="mutually exclusive operational loss components",
        report_role="Supporting RQ1 diagnostic figure",
    ),
    FigureRegistryEntry(
        figure_id=FIG_EFFECTIVENESS_CONDITIONAL_HEATMAP,
        title="Conditional quality among usable generations",
        source="descriptive_statistics.csv",
        metric="selected conditional metric",
        report_role="Primary RQ2 conditional figure",
    ),
    FigureRegistryEntry(
        figure_id=FIG_EFFECTIVENESS_OPERATIONAL_CONDITIONAL_GAP,
        title="Operational versus conditional performance",
        source="descriptive_statistics.csv + option_performance.csv",
        metric="conditional minus operational E2E",
        report_role="Supporting RQ2 gap figure",
    ),
    FigureRegistryEntry(
        figure_id=FIG_EFFECTIVENESS_PRIMARY_EFFECT_SIZES,
        title="Primary experimental effect sizes",
        source="omnibus_tests.csv",
        metric="partial_eta_squared",
        report_role="Primary statistical evidence figure",
    ),
)

from ..figures.robustness import (
    FIG_ROBUSTNESS_MEASUREMENT_DELTA,
    FIG_ROBUSTNESS_MEASUREMENT_SHIFT,
    FIG_ROBUSTNESS_TEMPLATE_COVERAGE,
    FIG_ROBUSTNESS_TEMPLATE_DELTA,
    FIG_ROBUSTNESS_TEMPLATE_PROGRESSION,
    FIG_ROBUSTNESS_TEMPLATE_UPLIFT,
)

ROBUSTNESS_FIGURES = (
    FigureRegistryEntry(
        figure_id=FIG_ROBUSTNESS_MEASUREMENT_SHIFT,
        title="Candidate–V4 measurement shift profile",
        source="validator_metric_summary.csv",
        metric="selected Candidate–V4 metric",
        report_role="Primary RQ5 robustness figure",
    ),
    FigureRegistryEntry(
        figure_id=FIG_ROBUSTNESS_MEASUREMENT_DELTA,
        title="Case-level Candidate–V4 paired deltas",
        source="validator_generation_pairs.csv",
        metric="selected Candidate–V4 delta",
        report_role="Supporting RQ5 distribution figure",
    ),
    FigureRegistryEntry(
        figure_id=FIG_ROBUSTNESS_TEMPLATE_PROGRESSION,
        title="LLM and Template evidence-condition profiles",
        source="llm_vs_template_summary.csv + baseline_option_performance.csv",
        metric="selected RQ6 metric",
        report_role="Primary RQ6 profile figure",
    ),
    FigureRegistryEntry(
        figure_id=FIG_ROBUSTNESS_TEMPLATE_UPLIFT,
        title="Paired LLM uplift relative to Template",
        source="llm_vs_template_tests.csv",
        metric="five planned RQ6 metrics",
        report_role="Primary RQ6 paired-comparison figure",
    ),
    FigureRegistryEntry(
        figure_id=FIG_ROBUSTNESS_TEMPLATE_DELTA,
        title="Case-level LLM–Template paired deltas",
        source="llm_vs_template_case_pairs.csv",
        metric="selected LLM–Template delta",
        report_role="Supporting RQ6 distribution figure",
    ),
    FigureRegistryEntry(
        figure_id=FIG_ROBUSTNESS_TEMPLATE_COVERAGE,
        title="Informational coverage and operational faithfulness",
        source="llm_vs_template_summary.csv + baseline_option_performance.csv",
        metric="mean E2E × supported claims per generation",
        report_role="Exploratory RQ6 coverage figure",
    ),
)
