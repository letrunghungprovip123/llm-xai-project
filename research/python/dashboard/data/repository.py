"""Immutable repository over the certified visualization-data-v2 release."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import json

import numpy as np
import pandas as pd

from ..settings import (
    EXPECTED_EVIDENCE_ORDER,
    EXPECTED_MODEL_ORDER,
    EXPECTED_OPTION_COUNT,
    EXPECTED_TEMPLATE_GENERATION_COUNT,
    EXPECTED_VALIDATOR_PAIR_COUNT,
    EXPECTED_VALIDATOR_SUMMARY_COUNT,
    EXPECTED_VALIDATOR_TEST_COUNT,
    EXPECTED_BASELINE_OPTION_COUNT,
    EXPECTED_BASELINE_PAIR_COUNT,
    EXPECTED_BASELINE_SUMMARY_COUNT,
    EXPECTED_BASELINE_TEST_COUNT,
    CASE_EXPLORER_REQUIRED_DATASETS,
    EXPECTED_CANONICAL_CASE_COUNT,
    EXPECTED_CASE_GENERATION_COUNT,
    EXPECTED_CASE_LLM_GENERATION_COUNT,
    EXPECTED_CASE_TEMPLATE_GENERATION_COUNT,
    EXPECTED_CASE_EVIDENCE_PACKAGE_COUNT,
    EXPECTED_COMPLETE_LLM_CASE_COUNT,
    EXPECTED_INCOMPLETE_LLM_CASE_COUNT,
    CASE_MATRIX_METRIC_LABELS,
    METHODS_REQUIRED_DATASETS,
    METHODS_VISIBILITY_TIER_ORDER,
    METHODS_VISIBILITY_TIER_LABELS,
    METHODS_VISIBILITY_TIER_DESCRIPTIONS,
    METHODS_REPRODUCTION_COMMANDS,
    DEFAULT_CASE_MATRIX_METRIC,
    DEFAULT_CASE_MODEL,
    DEFAULT_CASE_EVIDENCE,
    BASELINE_PAIR_METRIC_COLUMNS,
    DEFAULT_ROBUSTNESS_METRIC,
    DEFAULT_TEMPLATE_SCOPE,
    ROBUSTNESS_METRIC_LABELS,
    ROBUSTNESS_MODEL_LABELS,
    TEMPLATE_METRIC_LABELS,
    VALIDATOR_METRIC_COLUMNS,
    CONDITIONAL_METRIC_LABELS,
    DEFAULT_UTILIZATION_METRIC,
    UTILIZATION_METRIC_LABELS,
    DECISION_CRITERION_GROUPS,
    DECISION_SCENARIO_DESCRIPTIONS,
    DECISION_SCENARIO_IDS,
    DECISION_SCENARIO_LABELS,
    DEFAULT_DECISION_SCENARIO,
    WHAT_IF_BASE_SCENARIO,
    OFFICIAL_PAGE_PATHS,
    OVERVIEW_REQUIRED_CERTIFIED_METRICS,
    PROJECT_ROOT,
)
from .contracts import (
    CaseSummary,
    FocusedCaseData,
    CustomDecisionResult,
    DecisionCriterion,
    DecisionData,
    EffectivenessData,
    EvidenceConditionProfile,
    FocusedOption,
    MechanismsData,
    MethodsData,
    ReleaseAudit,
    ResearchQuestionRecord,
    ValidationGateRecord,
    OverviewData,
    OverviewFinding,
    OverviewKpi,
    ReleaseGuardResult,
    ReleaseMetadata,
    RobustnessData,
    ScenarioDefinition,
)
from .loaders import DashboardDataError, read_csv_frame, require_columns
from .release_guard import (
    get_visualization_release_guard,
    verify_visualization_release,
)


CERTIFIED_NUMBER_COLUMNS = {
    "metric_id",
    "value",
    "value_type",
    "denominator",
    "reporting_role",
    "source_contract",
}
OPTION_COLUMNS = {
    "option_id",
    "model_id",
    "model_label",
    "model_order",
    "evidence_level",
    "evidence_label",
    "evidence_order",
    "planned_generation_count",
    "mean_end_to_end_yield",
    "median_end_to_end_yield",
    "p10_end_to_end_yield",
    "usability_rate",
    "usable_generation_count",
    "unusable_generation_count",
}
OMNIBUS_COLUMNS = {
    "metric_id",
    "effect",
    "subject_count",
    "observation_count",
    "f_statistic",
    "p_value_used",
    "partial_eta_squared",
    "significant",
}
SENSITIVITY_COLUMNS = {
    "group_type",
    "metric_id",
    "generation_count",
    "candidate_mean",
    "v4_mean",
    "mean_delta_v4_minus_candidate",
}


def _format_count(value: float) -> str:
    return f"{int(round(value)):,}"


def _format_rate(value: float, digits: int = 2) -> str:
    return f"{value:.{digits}%}"


def _format_pp(value: float, digits: int = 2) -> str:
    sign = "+" if value >= 0 else "−"
    return f"{sign}{abs(value) * 100:.{digits}f} pp"


class DashboardRepository:
    """Load, validate and expose read-only Page-1 presentation data."""

    def __init__(
        self,
        *,
        project_root: Path = PROJECT_ROOT,
        guard_result: ReleaseGuardResult | None = None,
    ) -> None:
        self._project_root = project_root
        if guard_result is not None:
            self._guard = guard_result
        elif project_root == PROJECT_ROOT:
            self._guard = get_visualization_release_guard()
        else:
            self._guard = verify_visualization_release(project_root=project_root)
        self._release = self._guard.require_ready()
        self._frames: dict[str, pd.DataFrame] = {}

    @property
    def release(self) -> ReleaseMetadata:
        return self._release

    @property
    def guard_result(self) -> ReleaseGuardResult:
        return self._guard

    def _frame(self, dataset_name: str) -> pd.DataFrame:
        if dataset_name not in self._frames:
            contract = self._guard.datasets.get(dataset_name)
            if contract is None:
                raise DashboardDataError(
                    f"Dataset is not certified by manifest: {dataset_name}"
                )
            self._frames[dataset_name] = read_csv_frame(contract.path)
        return self._frames[dataset_name].copy(deep=True)

    def certified_numbers(self) -> pd.DataFrame:
        frame = self._frame("certified_report_numbers")
        require_columns(
            frame,
            CERTIFIED_NUMBER_COLUMNS,
            dataset_name="certified_report_numbers",
        )
        if frame["metric_id"].duplicated().any():
            duplicates = frame.loc[
                frame["metric_id"].duplicated(keep=False), "metric_id"
            ].tolist()
            raise DashboardDataError(
                f"Duplicate certified metric IDs: {duplicates}"
            )
        missing = sorted(
            set(OVERVIEW_REQUIRED_CERTIFIED_METRICS)
            - set(frame["metric_id"].astype(str))
        )
        if missing:
            raise DashboardDataError(
                f"Missing required certified metrics: {missing}"
            )
        return frame

    def option_performance(self) -> pd.DataFrame:
        frame = self._frame("option_performance")
        require_columns(
            frame,
            OPTION_COLUMNS,
            dataset_name="option_performance",
        )
        if len(frame) != EXPECTED_OPTION_COUNT:
            raise DashboardDataError(
                f"Expected {EXPECTED_OPTION_COUNT} LLM options, got {len(frame)}"
            )
        if frame["option_id"].duplicated().any():
            raise DashboardDataError("option_performance contains duplicate option IDs")
        model_order = tuple(
            frame.sort_values("model_order")["model_id"].drop_duplicates()
        )
        evidence_order = tuple(
            frame.sort_values("evidence_order")["evidence_level"].drop_duplicates()
        )
        if model_order != EXPECTED_MODEL_ORDER:
            raise DashboardDataError(
                f"Unexpected model order: {model_order}"
            )
        if evidence_order != EXPECTED_EVIDENCE_ORDER:
            raise DashboardDataError(
                f"Unexpected evidence order: {evidence_order}"
            )
        expected_keys = {
            (model, evidence)
            for model in EXPECTED_MODEL_ORDER
            for evidence in EXPECTED_EVIDENCE_ORDER
        }
        observed_keys = set(
            zip(frame["model_id"], frame["evidence_level"], strict=False)
        )
        if observed_keys != expected_keys:
            raise DashboardDataError("The 3 × 6 LLM option matrix is incomplete")
        if frame["model_id"].astype(str).str.contains("template", case=False).any():
            raise DashboardDataError("Template must not appear in the LLM option matrix")
        primary_values = frame["mean_end_to_end_yield"].astype(float)
        if primary_values.isna().any() or not primary_values.between(0, 1).all():
            raise DashboardDataError("Primary E2E values must be finite rates in [0, 1]")
        return frame.sort_values(["model_order", "evidence_order"]).reset_index(drop=True)

    def omnibus_tests(self) -> pd.DataFrame:
        frame = self._frame("omnibus_tests")
        require_columns(frame, OMNIBUS_COLUMNS, dataset_name="omnibus_tests")
        if set(frame["effect"]) != {"model", "evidence", "model:evidence"}:
            raise DashboardDataError("Primary omnibus effects are incomplete")
        if set(frame["subject_count"].astype(int)) != {36}:
            raise DashboardDataError("Omnibus inference must use 36 canonical cases")
        return frame.copy(deep=True)

    def unusable_generations(self) -> pd.DataFrame:
        frame = self._frame("unusable_generations")
        required = {
            "generation_id",
            "model_id",
            "model_label",
            "evidence_level",
            "is_truncated",
            "end_to_end_faithfulness_yield",
            "missingness_class",
        }
        require_columns(frame, required, dataset_name="unusable_generations")
        return frame.copy(deep=True)

    def validator_metric_summary(self) -> pd.DataFrame:
        frame = self._frame("validator_metric_summary")
        require_columns(
            frame,
            SENSITIVITY_COLUMNS,
            dataset_name="validator_metric_summary",
        )
        return frame.copy(deep=True)

    def _number_map(self) -> dict[str, pd.Series]:
        frame = self.certified_numbers().set_index("metric_id")
        return {str(index): row for index, row in frame.iterrows()}

    def _template_generation_count(self) -> int:
        contract = self._guard.datasets["baseline_generation_metrics"]
        if contract.row_count != EXPECTED_TEMPLATE_GENERATION_COUNT:
            raise DashboardDataError(
                "Template generation count differs from certified contract"
            )
        return contract.row_count

    def _build_kpis(self) -> tuple[OverviewKpi, ...]:
        numbers = self._number_map()
        planned = float(numbers["planned_llm_generations"]["value"])
        usable = float(numbers["usable_llm_generations"]["value"])
        unusable = float(numbers["unusable_llm_generations"]["value"])
        usability = float(numbers["usability_rate"]["value"])
        mean_e2e = float(
            numbers["mean_end_to_end_operational_faithfulness"]["value"]
        )
        claims = float(numbers["final_atomic_claims"]["value"])
        template_count = self._template_generation_count()

        return (
            OverviewKpi(
                metric_id="planned_llm_generations",
                label="Planned LLM generations",
                value=int(planned),
                display_value=_format_count(planned),
                subtext="36 cases · 3 models · 6 conditions",
                denominator=str(numbers["planned_llm_generations"]["denominator"]),
                source="certified_report_numbers.csv",
                tooltip=(
                    "Primary operational denominator: 36 canonical cases × "
                    "3 narrative models × 6 controlled evidence conditions."
                ),
            ),
            OverviewKpi(
                metric_id="usable_llm_generations",
                label="Usable generations",
                value=int(usable),
                display_value=_format_count(usable),
                subtext=f"{_format_count(unusable)} unusable",
                denominator=str(numbers["usable_llm_generations"]["denominator"]),
                source="certified_report_numbers.csv",
                tooltip=(
                    "Usable planned generations. The 10 unusable generations remain "
                    "inside the primary 648-generation operational denominator."
                ),
            ),
            OverviewKpi(
                metric_id="usability_rate",
                label="Usability",
                value=usability,
                display_value=_format_rate(usability),
                subtext="638 / 648 planned",
                denominator=str(numbers["usability_rate"]["denominator"]),
                source="certified_report_numbers.csv",
                tooltip="Usable generations divided by all planned LLM generations.",
            ),
            OverviewKpi(
                metric_id="mean_end_to_end_operational_faithfulness",
                label="Mean E2E faithfulness",
                value=mean_e2e,
                display_value=_format_rate(mean_e2e),
                subtext="Primary operational endpoint",
                denominator=str(
                    numbers["mean_end_to_end_operational_faithfulness"][
                        "denominator"
                    ]
                ),
                source="certified_report_numbers.csv",
                tooltip=(
                    "Macro mean over all 648 planned generations. Unusable generations "
                    "receive the frozen operational penalty of 0."
                ),
                variant="primary",
            ),
            OverviewKpi(
                metric_id="final_atomic_claims",
                label="Final atomic claims",
                value=int(claims),
                display_value=_format_count(claims),
                subtext="Validation units",
                denominator=str(numbers["final_atomic_claims"]["denominator"]),
                source="certified_report_numbers.csv",
                tooltip=(
                    "Finalized atomic claims are validation units and are not treated "
                    "as independent statistical observations."
                ),
            ),
            OverviewKpi(
                metric_id="template_reference_generations",
                label="Template reference runs",
                value=template_count,
                display_value=_format_count(template_count),
                subtext="Separate analytical layer",
                denominator="36 cases × 6 evidence conditions",
                source="visualization_manifest.json",
                tooltip=(
                    "Deterministic Template reference runs. Template is not included "
                    "in the 648 LLM denominator or the 18-option decision ranking."
                ),
                variant="reference",
            ),
        )

    def _build_findings(
        self,
        *,
        options: pd.DataFrame,
        omnibus: pd.DataFrame,
        unusable: pd.DataFrame,
        sensitivity: pd.DataFrame,
    ) -> tuple[OverviewFinding, ...]:
        significant_effects = omnibus.loc[omnibus["significant"].astype(bool), "effect"]
        effect_labels = {
            "model": "model",
            "evidence": "evidence condition",
            "model:evidence": "model × evidence interaction",
        }
        ordered_effects = [
            effect_labels[item]
            for item in ("model", "evidence", "model:evidence")
            if item in set(significant_effects)
        ]
        effect_statement = (
            ", ".join(ordered_effects[:-1])
            + (" and " + ordered_effects[-1] if len(ordered_effects) > 1 else ordered_effects[0])
            + " show statistically significant effects on operational faithfulness."
        )

        top = options.sort_values(
            ["mean_end_to_end_yield", "p10_end_to_end_yield"],
            ascending=False,
        ).iloc[0]
        top_statement = (
            f"{top['model_label']} · {top['evidence_level']} has the highest "
            f"observed mean E2E score ({_format_rate(float(top['mean_end_to_end_yield']))})."
        )

        evidence_counts = unusable["evidence_level"].value_counts()
        concentrated_level = str(evidence_counts.index[0]) if not evidence_counts.empty else ""
        if len(evidence_counts) == 1:
            failure_statement = (
                f"All {len(unusable)} unusable generations occur under "
                f"{concentrated_level}, forming a structured concentration "
                "that requires sensitivity analysis."
            )
        else:
            failure_statement = (
                f"The {len(unusable)} unusable generations are concentrated under "
                f"{concentrated_level}, indicating structured missingness."
            )

        overall = sensitivity.loc[
            (sensitivity["group_type"] == "overall")
            & (sensitivity["metric_id"] == "end_to_end_faithfulness_yield")
        ]
        if len(overall) != 1:
            raise DashboardDataError(
                "Validator sensitivity must contain one overall E2E summary"
            )
        delta = float(overall.iloc[0]["mean_delta_v4_minus_candidate"])
        sensitivity_statement = (
            "The alternative claim-measurement artifact changes overall mean "
            f"E2E by {_format_pp(delta)}, so measurement dependence must be reported."
        )

        return (
            OverviewFinding(
                finding_id="primary-effects",
                title="Primary effects",
                statement=effect_statement,
                source="omnibus_tests.csv",
                target_path=OFFICIAL_PAGE_PATHS["effectiveness"],
                tone="evidence",
            ),
            OverviewFinding(
                finding_id="highest-observed-option",
                title="Highest observed option",
                statement=top_statement,
                source="option_performance.csv",
                target_path=OFFICIAL_PAGE_PATHS["effectiveness"],
                tone="positive",
            ),
            OverviewFinding(
                finding_id="structured-failures",
                title="Structured S4 failures",
                statement=failure_statement,
                source="unusable_generations.csv",
                target_path=OFFICIAL_PAGE_PATHS["mechanisms"],
                tone="warning",
            ),
            OverviewFinding(
                finding_id="measurement-sensitivity",
                title="Measurement sensitivity",
                statement=sensitivity_statement,
                source="validator_metric_summary.csv",
                target_path=OFFICIAL_PAGE_PATHS["robustness"],
                tone="critical",
            ),
        )

    def overview_data(self) -> OverviewData:
        options = self.option_performance()
        omnibus = self.omnibus_tests()
        unusable = self.unusable_generations()
        sensitivity = self.validator_metric_summary()

        numbers = self._number_map()
        certified_unusable = int(
            round(float(numbers["unusable_llm_generations"]["value"]))
        )
        if len(unusable) != certified_unusable:
            raise DashboardDataError(
                "Unusable-generation table does not match certified headline count"
            )
        option_unusable = int(options["unusable_generation_count"].sum())
        if option_unusable != certified_unusable:
            raise DashboardDataError(
                "Option-level unusable counts do not match certified headline count"
            )
        planned = int(options["planned_generation_count"].sum())
        certified_planned = int(
            round(float(numbers["planned_llm_generations"]["value"]))
        )
        if planned != certified_planned:
            raise DashboardDataError(
                "Option-level planned denominator does not match certified release"
            )
        if not np.isfinite(options["mean_end_to_end_yield"].astype(float)).all():
            raise DashboardDataError("Overview option metrics contain non-finite values")

        return OverviewData(
            release=self.release,
            kpis=self._build_kpis(),
            option_performance=options.copy(deep=True),
            omnibus_tests=omnibus.copy(deep=True),
            unusable_generations=unusable.copy(deep=True),
            findings=self._build_findings(
                options=options,
                omnibus=omnibus,
                unusable=unusable,
                sensitivity=sensitivity,
            ),
        )


    def descriptive_statistics(self) -> pd.DataFrame:
        frame = self._frame("descriptive_statistics")
        require_columns(
            frame,
            {
                "analysis_population",
                "metric_id",
                "group_type",
                "model_id",
                "evidence_level",
                "planned_count",
                "observed_count",
                "missing_count",
                "mean",
                "median",
                "standard_deviation",
            },
            dataset_name="descriptive_statistics",
        )
        return frame

    def paired_tests(self) -> pd.DataFrame:
        frame = self._frame("paired_tests")
        require_columns(
            frame,
            {
                "metric_id",
                "contrast_family",
                "planned_pair_count",
                "observed_pair_count",
                "mean_difference",
                "adjusted_p_value",
                "rank_biserial_correlation",
                "significant_adjusted",
            },
            dataset_name="paired_tests",
        )
        if len(frame) != 33:
            raise DashboardDataError("Expected 33 certified operational contrasts")
        return frame

    def conditional_paired_tests(self) -> pd.DataFrame:
        frame = self._frame("conditional_paired_tests")
        require_columns(
            frame,
            {
                "metric_id",
                "contrast_family",
                "planned_pair_count",
                "observed_pair_count",
                "excluded_pair_count",
                "adjusted_p_value",
                "significant_adjusted",
            },
            dataset_name="conditional_paired_tests",
        )
        if len(frame) != 99:
            raise DashboardDataError("Expected 99 certified conditional contrasts")
        return frame

    def complete_case_omnibus_tests(self) -> pd.DataFrame:
        frame = self._frame("complete_case_omnibus_tests")
        require_columns(
            frame,
            {
                "effect",
                "subject_count",
                "p_value_used",
                "partial_eta_squared",
                "significant",
            },
            dataset_name="complete_case_omnibus_tests",
        )
        if len(frame) != 3:
            raise DashboardDataError("Expected three complete-case omnibus effects")
        return frame

    def statistical_sensitivity_summary(self) -> pd.DataFrame:
        frame = self._frame("statistical_sensitivity_summary")
        require_columns(
            frame,
            {
                "effect",
                "primary_subject_count",
                "primary_p_value",
                "primary_partial_eta_squared",
                "sensitivity_subject_count",
                "sensitivity_p_value",
                "sensitivity_partial_eta_squared",
                "significance_conclusion_stable",
            },
            dataset_name="statistical_sensitivity_summary",
        )
        if len(frame) != 3:
            raise DashboardDataError("Expected three statistical sensitivity rows")
        return frame

    def case_metrics(self) -> pd.DataFrame:
        frame = self._frame("case_heterogeneity_summary")
        require_columns(
            frame,
            {
                "generator_family",
                "generator_id",
                "generator_label",
                "generator_order",
                "eligible_for_decision_ranking",
                "case_id",
                "evidence_level",
                "evidence_order",
                "usable",
                "conservative_faithfulness",
                "verifiability",
                "resolved_faithfulness",
                "end_to_end_faithfulness_yield",
            },
            dataset_name="case_heterogeneity_summary",
        )
        llm = frame.loc[
            (frame["generator_family"] == "LLM")
            & frame["eligible_for_decision_ranking"].astype(bool)
        ].copy()
        if len(llm) != 648:
            raise DashboardDataError("Expected 648 LLM case-level rows")
        key = ["case_id", "generator_id", "evidence_level"]
        if llm.duplicated(key).any():
            raise DashboardDataError("Duplicate case × model × evidence rows")
        return llm.sort_values(
            ["generator_order", "evidence_order", "case_id"]
        ).reset_index(drop=True)

    def conditional_option_summary(self, metric_id: str) -> pd.DataFrame:
        if metric_id not in CONDITIONAL_METRIC_LABELS:
            raise DashboardDataError(f"Unsupported conditional metric: {metric_id}")
        descriptive = self.descriptive_statistics()
        summary = descriptive.loc[
            (descriptive["analysis_population"] == "METRIC_AVAILABLE")
            & (descriptive["metric_id"] == metric_id)
            & (descriptive["group_type"] == "model_evidence")
        ].copy()
        options = self.option_performance()[
            [
                "option_id",
                "model_id",
                "model_label",
                "model_order",
                "evidence_level",
                "evidence_label",
                "evidence_order",
                "mean_end_to_end_yield",
                "planned_generation_count",
            ]
        ]
        summary = summary.merge(
            options,
            on=["model_id", "evidence_level"],
            how="inner",
            validate="one_to_one",
        )
        if len(summary) != EXPECTED_OPTION_COUNT:
            raise DashboardDataError("Conditional summary must contain 18 options")
        for column in ("mean", "median"):
            values = pd.to_numeric(summary[column], errors="coerce")
            if not values.between(0, 1, inclusive="both").all():
                raise DashboardDataError(
                    f"Conditional metric outside [0, 1]: {metric_id}.{column}"
                )
        if not (
            summary["planned_count"]
            == summary["observed_count"] + summary["missing_count"]
        ).all():
            raise DashboardDataError("Conditional observed + missing identity failed")
        summary["metric_label"] = CONDITIONAL_METRIC_LABELS[metric_id]
        summary["operational_gap"] = (
            summary["mean"] - summary["mean_end_to_end_yield"]
        )
        return summary.sort_values(
            ["model_order", "evidence_order"]
        ).reset_index(drop=True)

    def focused_option(
        self,
        model_id: str | None,
        evidence_level: str | None,
    ) -> FocusedOption | None:
        if not model_id or not evidence_level:
            return None
        options = self.option_performance()
        selected = options.loc[
            (options["model_id"] == model_id)
            & (options["evidence_level"] == evidence_level)
        ]
        if len(selected) != 1:
            return None
        row = selected.iloc[0]

        def optional_float(column: str) -> float | None:
            value = pd.to_numeric(pd.Series([row.get(column)]), errors="coerce").iloc[0]
            return float(value) if pd.notna(value) else None

        return FocusedOption(
            option_id=str(row["option_id"]),
            model_id=str(row["model_id"]),
            model_label=str(row["model_label"]),
            evidence_level=str(row["evidence_level"]),
            evidence_label=str(row["evidence_label"]),
            mean_e2e=float(row["mean_end_to_end_yield"]),
            median_e2e=float(row["median_end_to_end_yield"]),
            p10_e2e=float(row["p10_end_to_end_yield"]),
            usability_rate=float(row["usability_rate"]),
            planned_count=int(row["planned_generation_count"]),
            usable_count=int(row["usable_generation_count"]),
            unusable_count=int(row["unusable_generation_count"]),
            pipeline_loss=float(row["mean_pipeline_loss"]),
            mean_latency_seconds=optional_float("mean_latency_seconds_planned"),
            mean_total_tokens=optional_float("mean_total_token_count_planned"),
        )

    def evidence_design_summary(self) -> pd.DataFrame:
        frame = self._frame("evidence_design_summary")
        require_columns(
            frame,
            {
                "case_id", "evidence_level", "evidence_label",
                "evidence_order", "intended_role", "selection_method",
                "selected_evidence_count", "evidence_item_count",
                "feature_item_count", "concept_item_count", "coverage",
                "normalized_entropy", "adaptive_k", "concept_group_count",
                "has_semantic_guidance", "has_concept_evidence",
                "has_structural_skeleton", "backend_factor_slot_count",
                "required_section_count", "evidence_condition_is_ordinal",
            },
            dataset_name="evidence_design_summary",
        )
        if len(frame) != 216:
            raise DashboardDataError("Expected 216 case × evidence packages")
        if frame.duplicated(["case_id", "evidence_level"]).any():
            raise DashboardDataError("Duplicate case × evidence design rows")
        counts = frame.groupby("evidence_level")["case_id"].nunique()
        if set(counts.index) != set(EXPECTED_EVIDENCE_ORDER) or not (counts == 36).all():
            raise DashboardDataError("Evidence design must contain 36 cases per condition")
        if frame["evidence_condition_is_ordinal"].astype(bool).any():
            raise DashboardDataError("Evidence conditions must remain categorical")
        return frame.sort_values(["evidence_order", "case_id"]).reset_index(drop=True)

    @staticmethod
    def _optional_float(value: object) -> float | None:
        parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
        return float(parsed) if pd.notna(parsed) else None

    def evidence_condition_profiles(self) -> tuple[EvidenceConditionProfile, ...]:
        frame = self.evidence_design_summary()
        profiles: list[EvidenceConditionProfile] = []
        for (_, level, label), group in frame.groupby(
            ["evidence_order", "evidence_level", "evidence_label"], sort=True
        ):
            first = group.iloc[0]
            profiles.append(
                EvidenceConditionProfile(
                    evidence_level=str(level),
                    evidence_label=str(label),
                    evidence_order=int(first["evidence_order"]),
                    intended_role=str(first["intended_role"]),
                    selection_method=str(first["selection_method"]),
                    case_count=int(group["case_id"].nunique()),
                    median_selected_evidence_count=float(group["selected_evidence_count"].median()),
                    median_evidence_item_count=self._optional_float(group["evidence_item_count"].dropna().median()),
                    median_feature_item_count=self._optional_float(group["feature_item_count"].dropna().median()),
                    median_concept_item_count=self._optional_float(group["concept_item_count"].dropna().median()),
                    mean_coverage=self._optional_float(group["coverage"].dropna().mean()),
                    mean_diversity=self._optional_float(group["normalized_entropy"].dropna().mean()),
                    median_adaptive_k=self._optional_float(group["adaptive_k"].dropna().median()),
                    median_concept_group_count=self._optional_float(group["concept_group_count"].dropna().median()),
                    has_semantic_guidance=bool(group["has_semantic_guidance"].astype(bool).any()),
                    has_concept_evidence=bool(group["has_concept_evidence"].astype(bool).any()),
                    has_structural_skeleton=bool(group["has_structural_skeleton"].astype(bool).any()),
                    median_backend_factor_slots=float(group["backend_factor_slot_count"].median()),
                    median_required_sections=float(group["required_section_count"].median()),
                )
            )
        if tuple(item.evidence_level for item in profiles) != EXPECTED_EVIDENCE_ORDER:
            raise DashboardDataError("Unexpected evidence profile order")
        return tuple(profiles)

    def evidence_utilization_summary(self) -> pd.DataFrame:
        frame = self._frame("evidence_utilization_summary")
        require_columns(
            frame,
            {
                "generator_family", "generator_id", "generator_label",
                "generator_order", "eligible_for_decision_ranking", "case_id",
                "evidence_level", "evidence_order", "selected_evidence_count",
                "selected_feature_mention_count", "selected_feature_mention_rate",
                "concept_evidence_count", "concept_mention_count",
                "concept_mention_rate", "top3_mention_rate", "claim_count",
                "supported_count", "end_to_end_faithfulness_yield",
                "dominant_primary_reason_code", "dominant_error_reason_code",
            },
            dataset_name="evidence_utilization_summary",
        )
        llm = frame.loc[
            (frame["generator_family"] == "LLM")
            & frame["eligible_for_decision_ranking"].astype(bool)
        ].copy()
        if len(llm) != 648:
            raise DashboardDataError("Expected 648 LLM utilization rows")
        if llm.duplicated(["generator_id", "case_id", "evidence_level"]).any():
            raise DashboardDataError("Duplicate LLM utilization identities")
        if llm["generator_id"].astype(str).str.contains("template", case=False).any():
            raise DashboardDataError("Template must not enter LLM mechanism analysis")
        return llm.sort_values(["generator_order", "evidence_order", "case_id"]).reset_index(drop=True)

    def narrative_structure_summary(self) -> pd.DataFrame:
        frame = self._frame("narrative_structure_summary")
        require_columns(
            frame,
            {
                "generator_family", "generator_id", "generator_label",
                "generator_order", "eligible_for_decision_ranking", "case_id",
                "evidence_level", "evidence_order", "usable", "runtime_status",
                "output_word_count", "sentence_count", "total_factor_count",
                "technical_term_ratio", "uncertainty_policy_pass",
                "distributed_policy_pass", "partial_evidence_policy_pass",
                "overall_policy_compliant", "single_cause_violation",
                "forbidden_phrase_violation", "human_naturalness_measured",
            },
            dataset_name="narrative_structure_summary",
        )
        llm = frame.loc[
            (frame["generator_family"] == "LLM")
            & frame["eligible_for_decision_ranking"].astype(bool)
        ].copy()
        if len(llm) != 648:
            raise DashboardDataError("Expected 648 LLM narrative rows")
        if llm["human_naturalness_measured"].astype(bool).any():
            raise DashboardDataError("Human naturalness must remain unmeasured")
        return llm.sort_values(["generator_order", "evidence_order", "case_id"]).reset_index(drop=True)

    def mechanism_breakdowns(self) -> pd.DataFrame:
        frame = self._frame("mechanism_breakdowns")
        require_columns(
            frame,
            {
                "group_type", "model_id", "evidence_level", "claim_type",
                "claim_count", "supported_count", "not_verifiable_count",
                "unsupported_count", "contradicted_count",
                "not_applicable_count", "model_label", "model_order",
                "evidence_order", "strong_safe_phrase_signal_rate_eligible",
                "safe_phrase_exposure_status",
            },
            dataset_name="mechanism_breakdowns",
        )
        overall = frame.loc[frame["group_type"] == "overall"]
        if len(overall) != 1 or int(overall.iloc[0]["claim_count"]) != 14667:
            raise DashboardDataError("Mechanism breakdown does not reconcile to 14,667 claims")
        required_groups = {"overall", "model", "evidence", "claim_type", "model_evidence", "model_evidence_claim_type", "stratum"}
        if not required_groups.issubset(set(frame["group_type"])):
            raise DashboardDataError("Mechanism breakdown group set is incomplete")
        return frame.copy(deep=True)

    def pipeline_failures_v2(self) -> pd.DataFrame:
        frame = self._frame("pipeline_failures")
        require_columns(
            frame,
            {
                "case_id", "model_id", "model_label", "model_order",
                "evidence_level", "evidence_order", "failure_category",
                "failure_category_label", "truncated_response",
                "raw_json_parse_success", "schema_valid", "latency_ms",
                "total_token_count", "finish_reason",
            },
            dataset_name="pipeline_failures",
        )
        if len(frame) != 10 or set(frame["evidence_level"]) != {"S4"}:
            raise DashboardDataError("Expected 10 S4 pipeline failures")
        counts = frame.groupby("model_id").size().to_dict()
        if counts != {"deepseek_v4_flash": 3, "phi4_mini_instruct": 7}:
            raise DashboardDataError(f"Unexpected failure distribution: {counts}")
        return frame.sort_values(["model_order", "case_id"]).reset_index(drop=True)

    def utilization_option_summary(self, metric_id: str = DEFAULT_UTILIZATION_METRIC) -> pd.DataFrame:
        if metric_id not in UTILIZATION_METRIC_LABELS:
            raise DashboardDataError(f"Unsupported utilization metric: {metric_id}")
        frame = self.evidence_utilization_summary().copy()
        if metric_id == "feature_use":
            frame["metric_value"] = pd.to_numeric(frame["selected_feature_mention_rate"], errors="coerce")
        elif metric_id == "concept_use":
            frame["metric_value"] = pd.to_numeric(frame["concept_mention_rate"], errors="coerce")
        else:
            claims = pd.to_numeric(frame["claim_count"], errors="coerce")
            supported = pd.to_numeric(frame["supported_count"], errors="coerce")
            frame["metric_value"] = np.where(claims > 0, supported / claims, np.nan)
        grouped = frame.groupby(
            ["generator_id", "generator_label", "generator_order", "evidence_level", "evidence_label", "evidence_order"],
            as_index=False,
        ).agg(
            mean_value=("metric_value", "mean"),
            median_value=("metric_value", "median"),
            observed_count=("metric_value", "count"),
            planned_count=("case_id", "count"),
            mean_e2e=("end_to_end_faithfulness_yield", "mean"),
            mean_selected_evidence=("selected_evidence_count", "mean"),
            mean_feature_mentions=("selected_feature_mention_count", "mean"),
            mean_concept_evidence=("concept_evidence_count", "mean"),
            mean_concept_mentions=("concept_mention_count", "mean"),
            mean_claims=("claim_count", "mean"),
            mean_supported=("supported_count", "mean"),
        )
        grouped["missing_count"] = grouped["planned_count"] - grouped["observed_count"]
        grouped["metric_id"] = metric_id
        grouped["metric_label"] = UTILIZATION_METRIC_LABELS[metric_id]
        if len(grouped) != 18:
            raise DashboardDataError("Utilization option summary must contain 18 rows")
        return grouped.sort_values(["generator_order", "evidence_order"]).reset_index(drop=True)

    def utilization_stage_profile(self, model_id: str, evidence_level: str) -> pd.DataFrame:
        frame = self.evidence_utilization_summary()
        selected = frame.loc[(frame["generator_id"] == model_id) & (frame["evidence_level"] == evidence_level)].copy()
        if len(selected) != 36:
            raise DashboardDataError("Focused utilization profile requires 36 cases")
        claims = pd.to_numeric(selected["claim_count"], errors="coerce")
        supported = pd.to_numeric(selected["supported_count"], errors="coerce")
        rows = [
            ("Feature evidence used", selected["selected_feature_mention_rate"].mean()),
            ("Concept evidence used", selected["concept_mention_rate"].mean()),
            ("Top-3 evidence mentioned", selected["top3_mention_rate"].mean()),
            ("Claims supported", np.nanmean(np.where(claims > 0, supported / claims, np.nan))),
        ]
        return pd.DataFrame(rows, columns=["stage", "rate"])

    def claim_status_by_option(self) -> pd.DataFrame:
        frame = self.mechanism_breakdowns()
        selected = frame.loc[frame["group_type"] == "model_evidence"].copy()
        if len(selected) != 18:
            raise DashboardDataError("Expected 18 model × evidence claim summaries")
        counts = ["supported_count", "not_verifiable_count", "unsupported_count", "contradicted_count", "not_applicable_count"]
        total = selected[counts].sum(axis=1)
        if not (total == selected["claim_count"]).all():
            raise DashboardDataError("Claim-status composition identity failed")
        for column in counts:
            selected[column.replace("_count", "_share")] = np.where(total > 0, selected[column] / total, np.nan)
        return selected.sort_values(["model_order", "evidence_order"]).reset_index(drop=True)

    def claim_difficulty_by_type(self) -> pd.DataFrame:
        frame = self.mechanism_breakdowns()
        selected = frame.loc[frame["group_type"] == "claim_type"].copy()
        total = selected["claim_count"].astype(float)
        selected["not_verifiable_share"] = selected["not_verifiable_count"] / total
        selected["unsupported_share"] = selected["unsupported_count"] / total
        selected["contradicted_share"] = selected["contradicted_count"] / total
        return selected.sort_values("claim_count", ascending=False).reset_index(drop=True)

    def pipeline_stage_summary(self) -> pd.DataFrame:
        narrative = self.narrative_structure_summary()
        failures = self.pipeline_failures_v2()
        rows: list[dict[str, object]] = []
        stages = ("Planned", "Runtime completed", "Parsed", "Schema valid", "Usable")
        for model_id in EXPECTED_MODEL_ORDER:
            group = narrative.loc[narrative["generator_id"] == model_id]
            label = str(group.iloc[0]["generator_label"])
            order = int(group.iloc[0]["generator_order"])
            failed = failures.loc[failures["model_id"] == model_id]
            values = {
                "Planned": len(group),
                "Runtime completed": int((group["runtime_status"] == "SUCCESS").sum()),
                "Parsed": len(group) - int((~failed["raw_json_parse_success"].astype(bool)).sum()),
                "Schema valid": len(group) - int((~failed["schema_valid"].astype(bool)).sum()),
                "Usable": int(group["usable"].astype(bool).sum()),
            }
            for stage_order, stage in enumerate(stages):
                rows.append({"model_id": model_id, "model_label": label, "model_order": order, "stage": stage, "stage_order": stage_order, "count": values[stage], "planned_count": len(group), "rate": values[stage] / len(group)})
        return pd.DataFrame(rows)

    def failure_matrix(self) -> pd.DataFrame:
        failures = self.pipeline_failures_v2()
        rows = []
        labels = {row.generator_id: (row.generator_label, int(row.generator_order)) for row in self.evidence_utilization_summary()[["generator_id", "generator_label", "generator_order"]].drop_duplicates().itertuples()}
        for model_id in EXPECTED_MODEL_ORDER:
            label, order = labels[model_id]
            for evidence_order, evidence in enumerate(EXPECTED_EVIDENCE_ORDER):
                count = int(((failures["model_id"] == model_id) & (failures["evidence_level"] == evidence)).sum())
                rows.append({"model_id": model_id, "model_label": label, "model_order": order, "evidence_level": evidence, "evidence_order": evidence_order, "failure_count": count})
        result = pd.DataFrame(rows)
        if int(result["failure_count"].sum()) != 10:
            raise DashboardDataError("Failure matrix must sum to 10")
        return result

    def narrative_model_summary(self) -> pd.DataFrame:
        frame = self.narrative_structure_summary().copy()
        grouped = frame.groupby(["generator_id", "generator_label", "generator_order"], as_index=False).agg(
            median_words=("output_word_count", "median"),
            median_sentences=("sentence_count", "median"),
            median_factors=("total_factor_count", "median"),
            median_technical_term_ratio=("technical_term_ratio", "median"),
            uncertainty_compliance=("uncertainty_policy_pass", "mean"),
            distributed_compliance=("distributed_policy_pass", "mean"),
            partial_evidence_compliance=("partial_evidence_policy_pass", "mean"),
            overall_policy_compliance=("overall_policy_compliant", "mean"),
            single_cause_violation_rate=("single_cause_violation", "mean"),
            forbidden_phrase_violation_rate=("forbidden_phrase_violation", "mean"),
        )
        return grouped.sort_values("generator_order").reset_index(drop=True)

    def safe_phrase_summary(self) -> pd.DataFrame:
        frame = self.mechanism_breakdowns()
        selected = frame.loc[frame["group_type"].isin(["overall", "model_evidence"])].copy()
        return selected.reset_index(drop=True)

    def mechanisms_data(self) -> MechanismsData:
        return MechanismsData(
            release=self.release,
            evidence_design=self.evidence_design_summary(),
            evidence_profiles=self.evidence_condition_profiles(),
            evidence_utilization=self.evidence_utilization_summary(),
            narrative_structure=self.narrative_structure_summary(),
            mechanism_breakdowns=self.mechanism_breakdowns(),
            pipeline_failures=self.pipeline_failures_v2(),
            claim_status_by_option=self.claim_status_by_option(),
            claim_difficulty_by_type=self.claim_difficulty_by_type(),
            pipeline_stage_summary=self.pipeline_stage_summary(),
            failure_matrix=self.failure_matrix(),
            narrative_model_summary=self.narrative_model_summary(),
            safe_phrase_summary=self.safe_phrase_summary(),
        )

    def scenario_options(self) -> pd.DataFrame:
        """Return the certified 5 × 18 decision-ranking matrix."""

        frame = self._frame("scenario_options")
        require_columns(
            frame,
            {
                "scenario_order", "scenario_id", "scenario_label",
                "scenario_description", "option_id", "model_id",
                "model_label", "model_order", "evidence_level",
                "evidence_order", "mean_end_to_end_yield",
                "p10_end_to_end_yield", "usability_rate",
                "mean_latency_seconds_planned",
                "mean_total_token_count_planned",
                "mean_supported_claims_per_1000_tokens", "eligible",
                "score_available", "utility_score", "utility_rank",
                "scenario_rank",
                "eligible_rank", "is_pareto_optimal",
                "recommendation_role", "reason_codes", "caution_codes",
                "is_primary_recommendation",
                "is_alternative_recommendation",
            },
            dataset_name="scenario_options",
        )
        if len(frame) != 90:
            raise DashboardDataError("scenario_options must contain 90 rows")
        if frame.duplicated(["scenario_id", "option_id"]).any():
            raise DashboardDataError("Duplicate scenario × option identity")
        if tuple(
            frame.sort_values("scenario_order")["scenario_id"].drop_duplicates()
        ) != DECISION_SCENARIO_IDS:
            raise DashboardDataError("Certified scenario order is incomplete")
        counts = frame.groupby("scenario_id").size().to_dict()
        if set(counts.values()) != {EXPECTED_OPTION_COUNT}:
            raise DashboardDataError("Each scenario must contain 18 LLM options")
        if frame["model_id"].astype(str).str.contains("template", case=False).any():
            raise DashboardDataError("Template must not enter decision ranking")
        primary_counts = frame.groupby("scenario_id")[
            "is_primary_recommendation"
        ].sum()
        if not (primary_counts == 1).all():
            raise DashboardDataError(
                "Each scenario requires exactly one primary recommendation"
            )
        return frame.sort_values(
            ["scenario_order", "scenario_rank", "model_order", "evidence_order"]
        ).reset_index(drop=True)

    def scenario_criterion_contributions(self) -> pd.DataFrame:
        """Return certified normalized values and weighted contributions."""

        frame = self._frame("scenario_criterion_contributions")
        require_columns(
            frame,
            {
                "scenario_order", "scenario_id", "option_id",
                "criterion_id", "criterion_label", "criterion_unit",
                "criterion_order", "direction", "weight", "raw_value",
                "eligible", "score_available", "normalized_value",
                "weighted_contribution", "scenario_label",
                "scenario_description",
            },
            dataset_name="scenario_criterion_contributions",
        )
        if len(frame) != 504:
            raise DashboardDataError(
                "scenario_criterion_contributions must contain 504 rows"
            )
        if frame.duplicated(
            ["scenario_id", "option_id", "criterion_id"]
        ).any():
            raise DashboardDataError(
                "Duplicate scenario × option × criterion identity"
            )
        available = frame.loc[
            frame["score_available"].astype(bool)
            & frame["normalized_value"].notna()
        ]
        expected = (
            available["normalized_value"].astype(float)
            * available["weight"].astype(float)
        )
        if not np.allclose(
            expected,
            available["weighted_contribution"].astype(float),
            atol=1e-12,
        ):
            raise DashboardDataError(
                "Weighted contribution identity is invalid"
            )
        return frame.sort_values(
            ["scenario_order", "option_id", "criterion_order"]
        ).reset_index(drop=True)

    def recommendation_evidence(self) -> pd.DataFrame:
        frame = self._frame("recommendation_evidence")
        require_columns(
            frame,
            {
                "scenario_order", "scenario_id", "recommended_option_id",
                "comparator_option_id", "comparison_available",
                "evidence_status", "recommended_option_label",
                "comparator_option_label", "adjusted_p_display",
                "effect_size_display",
            },
            dataset_name="recommendation_evidence",
        )
        if len(frame) != 85:
            raise DashboardDataError(
                "recommendation_evidence must contain 85 rows"
            )
        return frame.sort_values(
            ["scenario_order", "evidence_status_order", "comparator_option_id"]
        ).reset_index(drop=True)

    def decision_scenarios(self) -> tuple[ScenarioDefinition, ...]:
        options = self.scenario_options()
        contributions = self.scenario_criterion_contributions()
        scenarios: list[ScenarioDefinition] = []
        for row in (
            options[[
                "scenario_id", "scenario_label", "scenario_description",
                "scenario_order",
            ]]
            .drop_duplicates()
            .sort_values("scenario_order")
            .itertuples(index=False)
        ):
            weights = contributions.loc[
                contributions["scenario_id"] == row.scenario_id,
                ["criterion_id", "weight", "criterion_order"],
            ].drop_duplicates().sort_values("criterion_order")
            scenarios.append(
                ScenarioDefinition(
                    scenario_id=str(row.scenario_id),
                    label=DECISION_SCENARIO_LABELS.get(
                        str(row.scenario_id), str(row.scenario_label)
                    ),
                    description=DECISION_SCENARIO_DESCRIPTIONS.get(
                        str(row.scenario_id), str(row.scenario_description)
                    ),
                    scenario_order=int(row.scenario_order),
                    weights=tuple(
                        (str(item.criterion_id), float(item.weight))
                        for item in weights.itertuples(index=False)
                    ),
                )
            )
        return tuple(scenarios)

    def decision_criteria(self) -> tuple[DecisionCriterion, ...]:
        """Return the canonical What-if criterion registry from Balanced."""

        frame = self.scenario_criterion_contributions()
        selected = frame.loc[
            frame["scenario_id"] == WHAT_IF_BASE_SCENARIO
        ].copy()
        registry = (
            selected[[
                "criterion_id", "criterion_label", "direction",
                "criterion_order", "weight", "criterion_unit",
            ]]
            .drop_duplicates()
            .sort_values("criterion_order")
        )
        return tuple(
            DecisionCriterion(
                criterion_id=str(row.criterion_id),
                label=str(row.criterion_label),
                direction=str(row.direction),
                group=DECISION_CRITERION_GROUPS.get(
                    str(row.criterion_id), "Other"
                ),
                criterion_order=int(row.criterion_order),
                default_weight=float(row.weight),
                unit=str(row.criterion_unit),
            )
            for row in registry.itertuples(index=False)
        )

    def scenario_ranking(
        self,
        scenario_id: str = DEFAULT_DECISION_SCENARIO,
    ) -> pd.DataFrame:
        if scenario_id not in DECISION_SCENARIO_IDS:
            raise DashboardDataError(f"Unknown scenario: {scenario_id}")
        frame = self.scenario_options()
        return frame.loc[frame["scenario_id"] == scenario_id].sort_values(
            ["scenario_rank", "model_order", "evidence_order"]
        ).reset_index(drop=True)

    def scenario_recommendations(
        self,
        scenario_id: str = DEFAULT_DECISION_SCENARIO,
    ) -> pd.DataFrame:
        frame = self.scenario_ranking(scenario_id)
        selected = frame.loc[
            frame["recommendation_role"].isin(["PRIMARY", "ALTERNATIVE"])
        ].copy()
        return selected.sort_values(
            ["recommendation_rank", "scenario_rank"]
        ).reset_index(drop=True)

    def scenario_contribution_profile(
        self,
        scenario_id: str,
        option_id: str,
    ) -> pd.DataFrame:
        frame = self.scenario_criterion_contributions()
        selected = frame.loc[
            (frame["scenario_id"] == scenario_id)
            & (frame["option_id"] == option_id)
        ].copy()
        if selected.empty:
            raise DashboardDataError(
                f"No contribution profile for {scenario_id} / {option_id}"
            )
        return selected.sort_values("criterion_order").reset_index(drop=True)

    def custom_what_if(
        self,
        raw_weights: dict[str, float],
    ) -> CustomDecisionResult:
        """Compute exploratory utility from normalized values, never old contributions."""

        criteria = self.decision_criteria()
        known = {item.criterion_id for item in criteria}
        unknown = sorted(set(raw_weights) - known)
        if unknown:
            raise DashboardDataError(f"Unknown What-if criteria: {unknown}")
        cleaned = {
            item.criterion_id: max(0.0, float(raw_weights.get(item.criterion_id, 0.0)))
            for item in criteria
        }
        total = sum(cleaned.values())
        if total <= 0:
            empty = self.scenario_ranking(WHAT_IF_BASE_SCENARIO).copy()
            empty["custom_utility"] = np.nan
            empty["custom_rank"] = pd.NA
            return CustomDecisionResult(
                raw_weights=cleaned,
                normalized_weights={key: 0.0 for key in cleaned},
                ranking=empty,
                contributions=pd.DataFrame(),
                recommended_option_id=None,
            )
        normalized_weights = {
            key: value / total for key, value in cleaned.items()
        }
        base = self.scenario_criterion_contributions()
        base = base.loc[
            base["scenario_id"] == WHAT_IF_BASE_SCENARIO
        ].copy()
        base["custom_weight"] = base["criterion_id"].map(normalized_weights)
        base["custom_contribution"] = (
            base["normalized_value"].astype(float)
            * base["custom_weight"].astype(float)
        )
        base.loc[~base["score_available"].astype(bool), "custom_contribution"] = np.nan
        utility = (
            base.groupby("option_id", as_index=False)
            .agg(
                custom_utility=("custom_contribution", "sum"),
                contribution_count=("custom_contribution", "count"),
            )
        )
        ranking = self.scenario_ranking(WHAT_IF_BASE_SCENARIO).copy()
        ranking = ranking.merge(utility, on="option_id", how="left")
        required_count = len(criteria)
        ranking.loc[
            (~ranking["eligible"].astype(bool))
            | (ranking["contribution_count"] != required_count),
            "custom_utility",
        ] = np.nan
        p10 = base.loc[
            base["criterion_id"] == "p10_end_to_end_yield",
            ["option_id", "normalized_value"],
        ].rename(columns={"normalized_value": "tie_p10"})
        ranking = ranking.merge(p10, on="option_id", how="left")
        eligible = ranking.loc[ranking["custom_utility"].notna()].copy()
        eligible = eligible.sort_values(
            [
                "custom_utility", "tie_p10", "mean_end_to_end_yield",
                "model_order", "evidence_order",
            ],
            ascending=[False, False, False, True, True],
            kind="mergesort",
        )
        eligible["custom_rank"] = range(1, len(eligible) + 1)
        rank_map = eligible.set_index("option_id")["custom_rank"]
        ranking["custom_rank"] = ranking["option_id"].map(rank_map).astype("Int64")
        ranking = ranking.sort_values(
            ["custom_rank", "model_order", "evidence_order"],
            na_position="last",
        ).reset_index(drop=True)
        recommended = (
            str(eligible.iloc[0]["option_id"])
            if not eligible.empty
            else None
        )
        return CustomDecisionResult(
            raw_weights=cleaned,
            normalized_weights=normalized_weights,
            ranking=ranking,
            contributions=base.sort_values(
                ["option_id", "criterion_order"]
            ).reset_index(drop=True),
            recommended_option_id=recommended,
        )

    def decision_data(self) -> DecisionData:
        return DecisionData(
            release=self.release,
            scenarios=self.decision_scenarios(),
            criteria=self.decision_criteria(),
            scenario_options=self.scenario_options(),
            criterion_contributions=self.scenario_criterion_contributions(),
            recommendation_evidence=self.recommendation_evidence(),
        )

    def validator_generation_pairs(self) -> pd.DataFrame:
        frame = self._frame("validator_generation_pairs")
        required = {
            "generation_id", "case_id", "model_id", "evidence_level", "usable",
            *{
                column
                for mapping in VALIDATOR_METRIC_COLUMNS.values()
                for column in mapping.values()
            },
        }
        require_columns(frame, required, dataset_name="validator_generation_pairs")
        if len(frame) != EXPECTED_VALIDATOR_PAIR_COUNT:
            raise DashboardDataError(
                f"Expected {EXPECTED_VALIDATOR_PAIR_COUNT} Candidate–V4 pairs, got {len(frame)}"
            )
        if frame["generation_id"].duplicated().any():
            raise DashboardDataError("validator_generation_pairs contains duplicate generations")
        expected = {
            (model_id, evidence_level): 36
            for model_id in EXPECTED_MODEL_ORDER
            for evidence_level in EXPECTED_EVIDENCE_ORDER
        }
        observed = frame.groupby(["model_id", "evidence_level"]).size().to_dict()
        if observed != expected:
            raise DashboardDataError("Candidate–V4 pair matrix is not 3 × 6 × 36")
        for metric_id, columns in VALIDATOR_METRIC_COLUMNS.items():
            for role in ("candidate", "sensitivity"):
                values = pd.to_numeric(frame[columns[role]], errors="coerce")
                observed_values = values.dropna()
                if observed_values.empty or not observed_values.between(0, 1).all():
                    raise DashboardDataError(
                        f"Observed {metric_id} {role} values must be rates in [0, 1]"
                    )
            if metric_id == "end_to_end_faithfulness_yield":
                if frame[[columns["candidate"], columns["sensitivity"]]].isna().any().any():
                    raise DashboardDataError(
                        "Operational E2E measurements must be present for all paired generations"
                    )
        return frame.copy(deep=True)

    def validator_sensitivity_tests(self) -> pd.DataFrame:
        frame = self._frame("validator_sensitivity_tests")
        required = {
            "scope_family", "scope_id", "metric_id", "paired_case_count",
            "candidate_case_mean", "v4_case_mean",
            "mean_delta_v4_minus_candidate",
            "median_delta_v4_minus_candidate",
            "rank_biserial_correlation", "adjusted_p_value",
            "significant_adjusted", "interpretation",
        }
        require_columns(frame, required, dataset_name="validator_sensitivity_tests")
        if len(frame) != EXPECTED_VALIDATOR_TEST_COUNT:
            raise DashboardDataError(
                f"Expected {EXPECTED_VALIDATOR_TEST_COUNT} sensitivity tests, got {len(frame)}"
            )
        keys = ["scope_family", "scope_id", "metric_id"]
        if frame.duplicated(keys).any():
            raise DashboardDataError("validator_sensitivity_tests contains duplicate test keys")
        if set(frame["metric_id"].astype(str)) != set(ROBUSTNESS_METRIC_LABELS):
            raise DashboardDataError("Validator sensitivity metric family is incomplete")
        if not frame["paired_case_count"].astype(int).eq(36).all():
            raise DashboardDataError("Validator sensitivity inference must use 36 paired cases")
        return frame.copy(deep=True)

    def baseline_generation_metrics(self) -> pd.DataFrame:
        frame = self._frame("baseline_generation_metrics")
        required = {
            "generation_id", "case_id", "model_id", "evidence_level", "usable",
            "end_to_end_faithfulness_yield", "conservative_faithfulness",
            "verifiability", "supported_count", "supported_claims_per_100_words",
            "output_word_count", "policy_violation_count", "latency_ms",
            "latency_measurement_floor_limited",
        }
        require_columns(frame, required, dataset_name="baseline_generation_metrics")
        if len(frame) != EXPECTED_TEMPLATE_GENERATION_COUNT:
            raise DashboardDataError(
                f"Expected {EXPECTED_TEMPLATE_GENERATION_COUNT} Template generations, got {len(frame)}"
            )
        if frame["generation_id"].duplicated().any():
            raise DashboardDataError("baseline_generation_metrics contains duplicate generations")
        if set(frame["model_id"].astype(str)) != {"template_baseline"}:
            raise DashboardDataError("Template generation model identity is invalid")
        if not frame["usable"].astype(bool).all():
            raise DashboardDataError("All certified Template generations must be usable")
        latency = pd.to_numeric(frame["latency_ms"], errors="coerce")
        if latency.isna().any() or latency.lt(0).any() or latency.max() > 1:
            raise DashboardDataError(
                "Template runtime timing must remain within the certified 0–1 ms measurement floor"
            )
        expected_floor_flag = latency.eq(0)
        if not frame["latency_measurement_floor_limited"].astype(bool).eq(expected_floor_flag).all():
            raise DashboardDataError("Template latency floor flags are inconsistent with timing values")
        observed = frame.groupby("evidence_level").size().to_dict()
        if observed != {level: 36 for level in EXPECTED_EVIDENCE_ORDER}:
            raise DashboardDataError("Template generation matrix is not 6 × 36")
        return frame.copy(deep=True)

    def baseline_option_performance(self) -> pd.DataFrame:
        frame = self._frame("baseline_option_performance")
        required = {
            "generator_id", "generator_label", "evidence_level", "evidence_order",
            "planned_generation_count", "usable_generation_count", "usability_rate",
            "mean_end_to_end_yield", "mean_conservative_faithfulness",
            "mean_supported_claim_count", "mean_supported_claims_per_100_words",
            "mean_output_word_count", "eligible_for_llm_decision_ranking",
        }
        require_columns(frame, required, dataset_name="baseline_option_performance")
        if len(frame) != EXPECTED_BASELINE_OPTION_COUNT:
            raise DashboardDataError(
                f"Expected {EXPECTED_BASELINE_OPTION_COUNT} Template options, got {len(frame)}"
            )
        if tuple(frame.sort_values("evidence_order")["evidence_level"]) != EXPECTED_EVIDENCE_ORDER:
            raise DashboardDataError("Template evidence order is not S0–S5")
        if frame["eligible_for_llm_decision_ranking"].astype(bool).any():
            raise DashboardDataError("Template must remain excluded from LLM decision ranking")
        return frame.sort_values("evidence_order").reset_index(drop=True)

    def llm_vs_template_case_pairs(self) -> pd.DataFrame:
        frame = self._frame("llm_vs_template_case_pairs")
        required = {
            "llm_generation_id", "template_generation_id", "case_id", "model_id",
            "model_label", "model_order", "evidence_level", "evidence_order",
            "pairing_unit", "template_is_fourth_llm",
            "eligible_for_decision_ranking",
            *{
                column
                for mapping in BASELINE_PAIR_METRIC_COLUMNS.values()
                for column in mapping.values()
            },
        }
        require_columns(frame, required, dataset_name="llm_vs_template_case_pairs")
        if len(frame) != EXPECTED_BASELINE_PAIR_COUNT:
            raise DashboardDataError(
                f"Expected {EXPECTED_BASELINE_PAIR_COUNT} LLM–Template pairs, got {len(frame)}"
            )
        if frame["llm_generation_id"].duplicated().any():
            raise DashboardDataError("llm_vs_template_case_pairs contains duplicate LLM generations")
        if frame["template_is_fourth_llm"].astype(bool).any():
            raise DashboardDataError("Template is incorrectly marked as a fourth LLM")
        if frame["eligible_for_decision_ranking"].astype(bool).any():
            raise DashboardDataError("Template pairs must not enter decision ranking")
        if set(frame["pairing_unit"].astype(str)) != {"case_id_x_evidence_level"}:
            raise DashboardDataError("Unexpected LLM–Template pairing unit")
        observed = frame.groupby(["model_id", "evidence_level"]).size().to_dict()
        expected = {
            (model_id, evidence_level): 36
            for model_id in EXPECTED_MODEL_ORDER
            for evidence_level in EXPECTED_EVIDENCE_ORDER
        }
        if observed != expected:
            raise DashboardDataError("LLM–Template pair matrix is not 3 × 6 × 36")
        return frame.sort_values(["model_order", "evidence_order", "case_id"]).reset_index(drop=True)

    def llm_vs_template_summary(self) -> pd.DataFrame:
        frame = self._frame("llm_vs_template_summary")
        required = {
            "group_type", "model_id", "evidence_scope", "pair_count",
            "llm_mean_end_to_end_yield", "template_mean_end_to_end_yield",
            "mean_delta_end_to_end_yield", "llm_mean_supported_count",
            "template_mean_supported_count", "mean_delta_supported_count",
            "llm_mean_supported_claims_per_100_words",
            "template_mean_supported_claims_per_100_words",
            "mean_delta_supported_claims_per_100_words",
            "llm_mean_output_word_count", "template_mean_output_word_count",
            "mean_delta_output_word_count",
        }
        require_columns(frame, required, dataset_name="llm_vs_template_summary")
        if len(frame) != EXPECTED_BASELINE_SUMMARY_COUNT:
            raise DashboardDataError(
                f"Expected {EXPECTED_BASELINE_SUMMARY_COUNT} baseline summaries, got {len(frame)}"
            )
        return frame.copy(deep=True)

    def llm_vs_template_tests(self) -> pd.DataFrame:
        frame = self._frame("llm_vs_template_tests")
        required = {
            "analysis_role", "contrast_family", "metric_id", "model_id",
            "evidence_scope", "paired_case_count", "llm_mean", "template_mean",
            "mean_delta_llm_minus_template", "median_delta_llm_minus_template",
            "rank_biserial_correlation", "planned_pair_count", "excluded_pair_count",
            "adjusted_p_value", "significant_adjusted", "inference_unit",
            "claims_used_as_independent_units",
        }
        require_columns(frame, required, dataset_name="llm_vs_template_tests")
        if len(frame) != EXPECTED_BASELINE_TEST_COUNT:
            raise DashboardDataError(
                f"Expected {EXPECTED_BASELINE_TEST_COUNT} LLM–Template tests, got {len(frame)}"
            )
        keys = ["metric_id", "model_id", "evidence_scope"]
        if frame.duplicated(keys).any():
            raise DashboardDataError("llm_vs_template_tests contains duplicate test keys")
        if set(frame["metric_id"].astype(str)) != set(TEMPLATE_METRIC_LABELS):
            raise DashboardDataError("Template test metric family is incomplete")
        if not frame["planned_pair_count"].astype(int).eq(36).all():
            raise DashboardDataError("Template tests must plan 36 paired cases")
        if set(frame["inference_unit"].astype(str)) != {"paired_canonical_case"}:
            raise DashboardDataError("Template inference unit is not paired canonical case")
        if frame["claims_used_as_independent_units"].astype(bool).any():
            raise DashboardDataError("Claim rows must not be used as independent units")
        return frame.copy(deep=True)

    def measurement_shift_summary(
        self,
        metric_id: str = DEFAULT_ROBUSTNESS_METRIC,
        model_id: str | None = None,
    ) -> pd.DataFrame:
        if metric_id not in ROBUSTNESS_METRIC_LABELS:
            raise DashboardDataError(f"Unsupported robustness metric: {metric_id}")
        frame = self.validator_metric_summary()
        selected = frame.loc[
            (frame["group_type"] == "model_evidence")
            & (frame["metric_id"] == metric_id)
        ].copy()
        if model_id in EXPECTED_MODEL_ORDER:
            selected = selected.loc[selected["model_id"] == model_id].copy()
        options = self.option_performance()[
            ["model_id", "model_label", "model_order", "evidence_level", "evidence_order"]
        ]
        selected = selected.merge(
            options,
            on=["model_id", "evidence_level"],
            how="left",
            validate="one_to_one",
        )
        if len(selected) not in {6, 18}:
            raise DashboardDataError("Measurement shift summary has an unexpected option count")
        return selected.sort_values(["model_order", "evidence_order"]).reset_index(drop=True)

    def measurement_case_deltas(
        self,
        metric_id: str,
        model_id: str,
        evidence_level: str,
    ) -> pd.DataFrame:
        if metric_id not in VALIDATOR_METRIC_COLUMNS:
            raise DashboardDataError(f"Unsupported robustness metric: {metric_id}")
        if model_id not in EXPECTED_MODEL_ORDER or evidence_level not in EXPECTED_EVIDENCE_ORDER:
            raise DashboardDataError("Invalid measurement focus")
        columns = VALIDATOR_METRIC_COLUMNS[metric_id]
        frame = self.validator_generation_pairs()
        selected = frame.loc[
            (frame["model_id"] == model_id)
            & (frame["evidence_level"] == evidence_level),
            ["case_id", "model_id", "evidence_level", columns["candidate"], columns["sensitivity"], columns["delta"]],
        ].copy()
        if len(selected) != 36:
            raise DashboardDataError("Focused measurement distribution must contain 36 paired cases")
        return selected.rename(
            columns={
                columns["candidate"]: "candidate_value",
                columns["sensitivity"]: "sensitivity_value",
                columns["delta"]: "delta_value",
            }
        ).sort_values("case_id").reset_index(drop=True)

    def measurement_test(
        self,
        metric_id: str,
        *,
        scope_family: str,
        scope_id: str,
    ) -> pd.Series:
        tests = self.validator_sensitivity_tests()
        selected = tests.loc[
            (tests["metric_id"] == metric_id)
            & (tests["scope_family"] == scope_family)
            & (tests["scope_id"] == scope_id)
        ]
        if len(selected) != 1:
            raise DashboardDataError("Measurement sensitivity test focus is not unique")
        return selected.iloc[0].copy()

    def template_case_deltas(
        self,
        metric_id: str,
        model_id: str,
        evidence_scope: str = DEFAULT_TEMPLATE_SCOPE,
    ) -> pd.DataFrame:
        if metric_id not in BASELINE_PAIR_METRIC_COLUMNS:
            raise DashboardDataError(f"Unsupported Template metric: {metric_id}")
        if model_id not in EXPECTED_MODEL_ORDER:
            raise DashboardDataError(f"Unsupported Template comparison model: {model_id}")
        columns = BASELINE_PAIR_METRIC_COLUMNS[metric_id]
        frame = self.llm_vs_template_case_pairs()
        selected = frame.loc[frame["model_id"] == model_id].copy()
        if evidence_scope == DEFAULT_TEMPLATE_SCOPE:
            selected = selected.loc[selected["evidence_level"].isin(["S1", "S2", "S3", "S4"])]
            selected = (
                selected.groupby("case_id", as_index=False)[
                    [columns["llm"], columns["template"], columns["delta"]]
                ]
                .mean()
            )
        elif evidence_scope in EXPECTED_EVIDENCE_ORDER:
            selected = selected.loc[selected["evidence_level"] == evidence_scope, [
                "case_id", columns["llm"], columns["template"], columns["delta"]
            ]]
        else:
            raise DashboardDataError(f"Unsupported evidence scope: {evidence_scope}")
        if len(selected) != 36:
            raise DashboardDataError("Template paired distribution must contain 36 case pairs")
        return selected.rename(
            columns={
                columns["llm"]: "llm_value",
                columns["template"]: "template_value",
                columns["delta"]: "delta_value",
            }
        ).sort_values("case_id").reset_index(drop=True)

    def template_uplift_summary(
        self,
        metric_id: str,
        evidence_scope: str = DEFAULT_TEMPLATE_SCOPE,
    ) -> pd.DataFrame:
        if metric_id not in TEMPLATE_METRIC_LABELS:
            raise DashboardDataError(f"Unsupported Template metric: {metric_id}")
        tests = self.llm_vs_template_tests()
        selected = tests.loc[
            (tests["metric_id"] == metric_id)
            & (tests["evidence_scope"] == evidence_scope)
        ].copy()
        if len(selected) != 3:
            raise DashboardDataError("Template uplift summary must contain one row per LLM")
        selected["model_label"] = selected["model_id"].map(ROBUSTNESS_MODEL_LABELS)
        selected["model_order"] = selected["model_id"].map(
            {model_id: index for index, model_id in enumerate(EXPECTED_MODEL_ORDER, start=1)}
        )
        return selected.sort_values("model_order").reset_index(drop=True)

    def template_test(
        self,
        metric_id: str,
        model_id: str,
        evidence_scope: str = DEFAULT_TEMPLATE_SCOPE,
    ) -> pd.Series:
        selected = self.llm_vs_template_tests().loc[
            (self.llm_vs_template_tests()["metric_id"] == metric_id)
            & (self.llm_vs_template_tests()["model_id"] == model_id)
            & (self.llm_vs_template_tests()["evidence_scope"] == evidence_scope)
        ]
        if len(selected) != 1:
            raise DashboardDataError("Template paired test focus is not unique")
        return selected.iloc[0].copy()

    def case_heterogeneity_summary(self) -> pd.DataFrame:
        """Return the certified 864-row case-level presentation mart."""

        frame = self._frame("case_heterogeneity_summary")
        required = {
            "generation_id", "generator_family", "generator_id",
            "generator_label", "generator_order", "case_id",
            "selection_stratum", "selection_rank", "true_label_text",
            "predicted_label", "prediction_probability", "decision_threshold",
            "prediction_outcome", "distance_from_threshold", "evidence_level",
            "evidence_label", "evidence_order", "usable", "is_unusable",
            "runtime_status", "claim_count", "supported_count",
            "not_verifiable_count", "unsupported_count", "contradicted_count",
            "resolved_faithfulness", "verifiability",
            "conservative_faithfulness", "end_to_end_faithfulness_yield",
            "output_word_count", "latency_seconds", "complete_llm_case",
        }
        require_columns(frame, required, dataset_name="case_heterogeneity_summary")
        if len(frame) != 864:
            raise DashboardDataError(
                f"Expected 864 Case Explorer generation rows, got {len(frame)}"
            )
        key = ["case_id", "generator_id", "evidence_level"]
        if frame.duplicated(key).any():
            raise DashboardDataError(
                "case_heterogeneity_summary contains duplicate case × generator × evidence rows"
            )
        if frame["case_id"].nunique() != EXPECTED_CANONICAL_CASE_COUNT:
            raise DashboardDataError("Case Explorer must contain 36 canonical cases")
        counts = frame.groupby("case_id").size()
        if not counts.eq(EXPECTED_CASE_GENERATION_COUNT).all():
            raise DashboardDataError("Every canonical case must contain 24 generator slots")
        llm = frame.loc[frame["generator_family"] == "LLM"]
        template = frame.loc[frame["generator_family"] == "TEMPLATE"]
        if not llm.groupby("case_id").size().eq(EXPECTED_CASE_LLM_GENERATION_COUNT).all():
            raise DashboardDataError("Every case must contain 18 LLM slots")
        if not template.groupby("case_id").size().eq(EXPECTED_CASE_TEMPLATE_GENERATION_COUNT).all():
            raise DashboardDataError("Every case must contain six Template slots")
        if int(llm["is_unusable"].astype(bool).sum()) != 10:
            raise DashboardDataError("Case Explorer must retain all 10 unusable LLM generations")
        unusable_levels = set(llm.loc[llm["is_unusable"].astype(bool), "evidence_level"])
        if unusable_levels != {"S4"}:
            raise DashboardDataError("All unusable LLM rows must remain localized to S4")
        return frame.sort_values(
            ["case_id", "generator_order", "evidence_order"], kind="stable"
        ).reset_index(drop=True)

    def case_catalog(self) -> pd.DataFrame:
        """Build the stable 36-case catalog without ranking cases by performance."""

        frame = self.case_heterogeneity_summary()
        identity_columns = [
            "case_id", "selection_stratum", "selection_rank", "true_label_text",
            "predicted_label", "prediction_probability", "decision_threshold",
            "prediction_outcome", "distance_from_threshold", "complete_llm_case",
        ]
        for column in identity_columns[1:]:
            inconsistent = frame.groupby("case_id")[column].nunique(dropna=False).gt(1)
            if inconsistent.any():
                raise DashboardDataError(
                    f"Case identity field is inconsistent across generations: {column}"
                )
        catalog = frame[identity_columns].drop_duplicates("case_id").copy()
        llm = frame.loc[frame["generator_family"] == "LLM"]
        failure_counts = (
            llm.groupby("case_id", as_index=False)["is_unusable"]
            .sum()
            .rename(columns={"is_unusable": "unusable_slot_count"})
        )
        catalog = catalog.merge(
            failure_counts, on="case_id", how="left", validate="one_to_one"
        )
        catalog["unusable_slot_count"] = catalog["unusable_slot_count"].fillna(0).astype(int)
        catalog["usable_llm_slot_count"] = (
            EXPECTED_CASE_LLM_GENERATION_COUNT - catalog["unusable_slot_count"]
        )
        complete_count = int(catalog["complete_llm_case"].astype(bool).sum())
        if complete_count != EXPECTED_COMPLETE_LLM_CASE_COUNT:
            raise DashboardDataError(
                f"Expected {EXPECTED_COMPLETE_LLM_CASE_COUNT} complete LLM cases, got {complete_count}"
            )
        if len(catalog) - complete_count != EXPECTED_INCOMPLETE_LLM_CASE_COUNT:
            raise DashboardDataError("Expected nine cases with structured missingness")
        return catalog.sort_values(
            ["selection_rank", "case_id"], kind="stable"
        ).reset_index(drop=True)

    def case_summary(self, case_id: int) -> CaseSummary:
        """Return one privacy-preserving case summary."""

        selected = self.case_catalog().loc[lambda frame: frame["case_id"] == int(case_id)]
        if len(selected) != 1:
            raise DashboardDataError(f"Unknown canonical case: {case_id}")
        row = selected.iloc[0]
        return CaseSummary(
            case_id=int(row["case_id"]),
            selection_stratum=str(row["selection_stratum"]),
            prediction_outcome=str(row["prediction_outcome"]),
            true_label_text=str(row["true_label_text"]),
            predicted_label=str(row["predicted_label"]),
            prediction_probability=float(row["prediction_probability"]),
            decision_threshold=float(row["decision_threshold"]),
            distance_from_threshold=float(row["distance_from_threshold"]),
            complete_llm_case=bool(row["complete_llm_case"]),
            unusable_slot_count=int(row["unusable_slot_count"]),
        )

    def case_generations(self, case_id: int) -> pd.DataFrame:
        """Return all 18 LLM and six Template rows for one case."""

        frame = self.case_heterogeneity_summary()
        selected = frame.loc[frame["case_id"] == int(case_id)].copy()
        if len(selected) != EXPECTED_CASE_GENERATION_COUNT:
            raise DashboardDataError("Focused case must contain exactly 24 generation rows")
        return selected.sort_values(
            ["generator_order", "evidence_order"], kind="stable"
        ).reset_index(drop=True)

    def case_generation_matrix(
        self,
        case_id: int,
        metric_id: str = DEFAULT_CASE_MATRIX_METRIC,
    ) -> pd.DataFrame:
        """Return the 4 × 6 matrix values for one selected case."""

        if metric_id not in CASE_MATRIX_METRIC_LABELS:
            raise DashboardDataError(f"Unsupported Case Explorer matrix metric: {metric_id}")
        frame = self.case_generations(case_id).copy()
        frame["metric_value"] = pd.to_numeric(frame[metric_id], errors="coerce")
        conditional = metric_id in {"conservative_faithfulness", "verifiability"}
        if conditional:
            invalid = frame.loc[frame["is_unusable"].astype(bool), "metric_value"].notna()
            if invalid.any():
                raise DashboardDataError(
                    "Unusable conditional matrix cells must remain missing, not zero"
                )
        return frame[
            [
                "case_id", "generator_family", "generator_id", "generator_label",
                "generator_order", "evidence_level", "evidence_label",
                "evidence_order", "usable", "is_unusable", "runtime_status",
                "metric_value", "end_to_end_faithfulness_yield",
                "conservative_faithfulness", "verifiability", "supported_count",
                "output_word_count",
            ]
        ].copy()

    def case_evidence_packages(self, case_id: int) -> pd.DataFrame:
        """Return the six generator-independent evidence packages for one case."""

        frame = self.evidence_design_summary()
        selected = frame.loc[frame["case_id"] == int(case_id)].copy()
        if len(selected) != EXPECTED_CASE_EVIDENCE_PACKAGE_COUNT:
            raise DashboardDataError("Focused case must contain six evidence packages")
        if selected["evidence_level"].duplicated().any():
            raise DashboardDataError("Duplicate case × evidence package rows")
        return selected.sort_values("evidence_order", kind="stable").reset_index(drop=True)

    def case_evidence_package(self, case_id: int, evidence_level: str) -> pd.Series:
        selected = self.case_evidence_packages(case_id).loc[
            lambda frame: frame["evidence_level"] == evidence_level
        ]
        if len(selected) != 1:
            raise DashboardDataError("Focused evidence package is not unique")
        return selected.iloc[0].copy()

    def case_utilization(
        self,
        case_id: int,
        model_id: str = DEFAULT_CASE_MODEL,
        evidence_level: str = DEFAULT_CASE_EVIDENCE,
    ) -> pd.Series:
        if model_id not in EXPECTED_MODEL_ORDER or evidence_level not in EXPECTED_EVIDENCE_ORDER:
            raise DashboardDataError("Invalid focused LLM or evidence condition")
        frame = self.evidence_utilization_summary()
        selected = frame.loc[
            (frame["case_id"] == int(case_id))
            & (frame["generator_family"] == "LLM")
            & (frame["generator_id"] == model_id)
            & (frame["evidence_level"] == evidence_level)
        ]
        if len(selected) != 1:
            raise DashboardDataError("Focused evidence-utilization row is not unique")
        return selected.iloc[0].copy()

    def case_narrative_structure(
        self,
        case_id: int,
        model_id: str = DEFAULT_CASE_MODEL,
        evidence_level: str = DEFAULT_CASE_EVIDENCE,
    ) -> pd.Series:
        if model_id not in EXPECTED_MODEL_ORDER or evidence_level not in EXPECTED_EVIDENCE_ORDER:
            raise DashboardDataError("Invalid focused LLM or evidence condition")
        frame = self.narrative_structure_summary()
        selected = frame.loc[
            (frame["case_id"] == int(case_id))
            & (frame["generator_family"] == "LLM")
            & (frame["generator_id"] == model_id)
            & (frame["evidence_level"] == evidence_level)
        ]
        if len(selected) != 1:
            raise DashboardDataError("Focused narrative-structure row is not unique")
        row = selected.iloc[0].copy()
        if bool(row.get("human_naturalness_measured", False)):
            raise DashboardDataError("Human naturalness must remain explicitly unmeasured")
        return row

    def case_validator_pair(
        self,
        case_id: int,
        model_id: str = DEFAULT_CASE_MODEL,
        evidence_level: str = DEFAULT_CASE_EVIDENCE,
    ) -> pd.Series:
        frame = self.validator_generation_pairs()
        selected = frame.loc[
            (frame["case_id"] == int(case_id))
            & (frame["model_id"] == model_id)
            & (frame["evidence_level"] == evidence_level)
        ]
        if len(selected) != 1:
            raise DashboardDataError("Focused Candidate–V4 pair is not unique")
        return selected.iloc[0].copy()

    def case_template_pair(
        self,
        case_id: int,
        model_id: str = DEFAULT_CASE_MODEL,
        evidence_level: str = DEFAULT_CASE_EVIDENCE,
    ) -> pd.Series:
        frame = self.llm_vs_template_case_pairs()
        selected = frame.loc[
            (frame["case_id"] == int(case_id))
            & (frame["model_id"] == model_id)
            & (frame["evidence_level"] == evidence_level)
        ]
        if len(selected) != 1:
            raise DashboardDataError("Focused LLM–Template pair is not unique")
        row = selected.iloc[0].copy()
        if bool(row["template_is_fourth_llm"]):
            raise DashboardDataError("Template must not be represented as a fourth LLM")
        if bool(row["eligible_for_decision_ranking"]):
            raise DashboardDataError("Template must remain excluded from decision ranking")
        return row

    def focused_case_data(
        self,
        case_id: int,
        model_id: str = DEFAULT_CASE_MODEL,
        evidence_level: str = DEFAULT_CASE_EVIDENCE,
    ) -> FocusedCaseData:
        """Return every certified view required for one selected case state."""

        return FocusedCaseData(
            release=self.release,
            case_summary=self.case_summary(case_id),
            generations=self.case_generations(case_id),
            evidence_packages=self.case_evidence_packages(case_id),
            evidence_package=self.case_evidence_package(case_id, evidence_level),
            utilization=self.case_utilization(case_id, model_id, evidence_level),
            narrative_structure=self.case_narrative_structure(
                case_id, model_id, evidence_level
            ),
            validator_pair=self.case_validator_pair(case_id, model_id, evidence_level),
            template_pair=self.case_template_pair(case_id, model_id, evidence_level),
        )


    def release_metadata_frame(self) -> pd.DataFrame:
        """Return the single certified release-metadata row."""

        frame = self._frame("release_metadata")
        required = {
            "visualization_version",
            "parent_analytical_release",
            "parent_analytical_gate",
            "parent_release_id",
            "parent_git_commit",
            "parent_git_branch",
            "parent_source_tree_sha256",
            "verified_parent_artifact_count",
            "baseline_gate",
            "verified_baseline_artifact_count",
            "statistical_gate",
            "validator_sensitivity_gate",
            "template_is_fourth_llm",
            "template_eligible_for_decision_ranking",
            "research_question_count",
            "human_naturalness_evaluated",
            "template_latency_measurement_floor_limited",
        }
        require_columns(frame, required, dataset_name="release_metadata")
        if len(frame) != 1:
            raise DashboardDataError("release_metadata must contain exactly one row")
        row = frame.iloc[0]
        if bool(row["template_is_fourth_llm"]):
            raise DashboardDataError("Template must not be represented as a fourth LLM")
        if bool(row["template_eligible_for_decision_ranking"]):
            raise DashboardDataError("Template must remain excluded from decision ranking")
        if bool(row["human_naturalness_evaluated"]):
            raise DashboardDataError("Human naturalness must remain explicitly unevaluated")
        if not bool(row["template_latency_measurement_floor_limited"]):
            raise DashboardDataError("Template latency must remain measurement-floor limited")
        return frame

    def release_audit(self) -> ReleaseAudit:
        row = self.release_metadata_frame().iloc[0]
        return ReleaseAudit(
            analytical_release_id=str(row["parent_analytical_release"]),
            visualization_release_id=self.release.visualization_release_id,
            visualization_version=str(row["visualization_version"]),
            parent_release_id=str(row["parent_release_id"]),
            parent_git_commit=str(row["parent_git_commit"]),
            parent_git_branch=str(row["parent_git_branch"]),
            source_tree_sha256=str(row["parent_source_tree_sha256"]),
            verified_parent_artifact_count=int(row["verified_parent_artifact_count"]),
            verified_baseline_artifact_count=int(row["verified_baseline_artifact_count"]),
            dataset_count=len(self._guard.datasets),
            validation_check_count=int(self._guard.validation_payload.get("check_count", 0)),
        )

    def validation_gate_registry(self) -> tuple[ValidationGateRecord, ...]:
        """Expose frozen gate states without recalculating any gate in the browser."""

        row = self.release_metadata_frame().iloc[0]
        validation = self._guard.validation_payload
        definitions = (
            (
                "analytical_release",
                "Analytical release",
                str(row["parent_analytical_gate"]),
                "REPORT_WRITING_READY",
                None,
                None,
                "report_release_manifest.json",
                "Frozen report-facing analytical release and denominators.",
            ),
            (
                "statistical_core",
                "Statistical core",
                str(row["statistical_gate"]),
                "STATISTICAL_CORE_READY",
                None,
                None,
                "statistical_validation.json",
                "Case-level inference and planned comparison families.",
            ),
            (
                "validator_sensitivity",
                "Measurement sensitivity",
                str(row["validator_sensitivity_gate"]),
                "VALIDATOR_SENSITIVITY_READY",
                None,
                None,
                "validator_sensitivity_validation.json",
                "Candidate-primary and V4 sensitivity artifacts are available.",
            ),
            (
                "template_baseline",
                "Template baseline",
                str(row["baseline_gate"]),
                "BASELINE_COMPARISON_READY",
                None,
                None,
                "baseline_comparison_validation.json",
                "Deterministic narrative-generation reference comparison.",
            ),
            (
                "visualization_release",
                "Visualization release",
                str(validation.get("exit_gate", "")),
                "VISUALIZATION_DATA_V2_READY",
                int(validation.get("check_count", 0)),
                int(validation.get("failed_check_count", 0)),
                "visualization_validation.json",
                "Certified presentation marts and dashboard-facing invariants.",
            ),
        )
        return tuple(
            ValidationGateRecord(
                layer_id=layer_id,
                layer_label=label,
                exit_gate=observed,
                expected_gate=expected,
                passed=observed == expected and (failed in {None, 0}),
                check_count=checks,
                failed_check_count=failed,
                source_artifact=source,
                meaning=meaning,
            )
            for layer_id, label, observed, expected, checks, failed, source, meaning in definitions
        )

    @staticmethod
    def _json_tuple(value: object, *, field_name: str) -> tuple[str, ...]:
        try:
            parsed = json.loads(str(value))
        except json.JSONDecodeError as error:
            raise DashboardDataError(f"Invalid JSON in {field_name}: {error}") from error
        if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
            raise DashboardDataError(f"{field_name} must contain a JSON string list")
        return tuple(parsed)

    def research_question_registry(self) -> tuple[ResearchQuestionRecord, ...]:
        frame = self._frame("research_question_registry")
        required = {
            "rq_order",
            "rq_id",
            "title",
            "question",
            "status",
            "population",
            "unit_of_inference",
            "primary_metrics_json",
            "supporting_metrics_json",
            "primary_sources_json",
            "dashboard_pages_json",
            "interpretation_restrictions_json",
        }
        require_columns(frame, required, dataset_name="research_question_registry")
        if len(frame) != 6 or frame["rq_id"].nunique() != 6:
            raise DashboardDataError("Research-question registry must contain six unique RQs")
        rows = []
        for row in frame.sort_values("rq_order", kind="stable").itertuples(index=False):
            rows.append(
                ResearchQuestionRecord(
                    rq_id=str(row.rq_id),
                    rq_order=int(row.rq_order),
                    title=str(row.title),
                    question=str(row.question),
                    status=str(row.status),
                    population=str(row.population),
                    inference_unit=str(row.unit_of_inference),
                    primary_metrics=self._json_tuple(
                        row.primary_metrics_json, field_name="primary_metrics_json"
                    ),
                    supporting_metrics=self._json_tuple(
                        row.supporting_metrics_json, field_name="supporting_metrics_json"
                    ),
                    primary_sources=self._json_tuple(
                        row.primary_sources_json, field_name="primary_sources_json"
                    ),
                    dashboard_pages=self._json_tuple(
                        row.dashboard_pages_json, field_name="dashboard_pages_json"
                    ),
                    interpretation_restrictions=self._json_tuple(
                        row.interpretation_restrictions_json,
                        field_name="interpretation_restrictions_json",
                    ),
                )
            )
        return tuple(rows)

    def metric_visibility_registry(self) -> pd.DataFrame:
        frame = self._frame("metric_visibility_registry")
        required = {
            "metric_id",
            "visibility_tier",
            "dashboard_enabled",
            "requires_additional_data",
        }
        require_columns(frame, required, dataset_name="metric_visibility_registry")
        observed = tuple(
            tier for tier in METHODS_VISIBILITY_TIER_ORDER
            if tier in set(frame["visibility_tier"].astype(str))
        )
        if observed != METHODS_VISIBILITY_TIER_ORDER:
            raise DashboardDataError("Metric visibility registry must expose four frozen tiers")
        if frame["metric_id"].duplicated().any():
            raise DashboardDataError("Metric visibility registry has duplicate metric IDs")
        return frame.sort_values(
            ["visibility_tier", "metric_id"], kind="stable"
        ).reset_index(drop=True)

    def visualization_dictionary(self) -> pd.DataFrame:
        frame = self._frame("visualization_dictionary")
        required = {
            "dataset_name",
            "field_name",
            "pandas_dtype",
            "nullable",
            "visibility_tier",
            "is_identifier",
            "is_rate",
        }
        require_columns(frame, required, dataset_name="visualization_dictionary")
        if frame.duplicated(["dataset_name", "field_name"]).any():
            raise DashboardDataError("Visualization dictionary contains duplicate fields")
        expected = sum(
            contract.column_count
            for name, contract in self._guard.datasets.items()
            if name != "visualization_dictionary"
        )
        if len(frame) != expected:
            raise DashboardDataError(
                f"Visualization dictionary coverage mismatch: expected {expected}, got {len(frame)}"
            )
        return frame.sort_values(["dataset_name", "field_name"], kind="stable").reset_index(drop=True)

    def artifact_inventory(self) -> pd.DataFrame:
        role_map = {
            "release_metadata": "Release lineage",
            "certified_report_numbers": "Certified report values",
            "research_question_registry": "Research design",
            "metric_visibility_registry": "Metric-governance registry",
            "visualization_dictionary": "Field-level data dictionary",
        }
        rows = []
        for name, contract in sorted(self._guard.datasets.items()):
            rows.append(
                {
                    "dataset_name": name,
                    "row_count": int(contract.row_count),
                    "field_count": int(contract.column_count),
                    "sha256": contract.sha256,
                    "sha256_short": contract.sha256[:12],
                    "hash_verified": True,
                    "dashboard_role_id": name if name in role_map else "certified_presentation_dataset",
                    "dashboard_role": role_map.get(name, "Certified presentation dataset"),
                    "relative_path": str(contract.path.relative_to(self._project_root)),
                }
            )
        return pd.DataFrame(rows)

    def denominator_ledger(self) -> pd.DataFrame:
        numbers = self.certified_numbers().copy()
        domain_map = {
            "planned_llm_generations": "Generation population",
            "usable_llm_generations": "Generation population",
            "unusable_llm_generations": "Generation population",
            "final_atomic_claims": "Claim population",
            "applicable_claims": "Claim population",
            "resolved_claims": "Claim population",
        }
        selected = numbers.loc[numbers["metric_id"].isin(domain_map)].copy()
        selected["domain"] = selected["metric_id"].map(domain_map)
        selected["domain_id"] = selected["domain"].map({
            "Generation population": "generation_population",
            "Claim population": "claim_population",
        })
        if set(selected["metric_id"]) != set(domain_map):
            missing = sorted(set(domain_map) - set(selected["metric_id"]))
            raise DashboardDataError(f"Denominator ledger is missing: {missing}")
        selected["value"] = pd.to_numeric(selected["value"], errors="raise")

        catalog = self.case_catalog()
        complete_count = int(catalog["complete_llm_case"].astype(bool).sum())
        incomplete_count = int(len(catalog) - complete_count)
        case_rows = pd.DataFrame(
            [
                {
                    "domain_id": "generation_population",
                    "domain": "Generation population",
                    "metric_id": "canonical_cases",
                    "value": int(len(catalog)),
                    "denominator": "frozen canonical cohort",
                    "reporting_role": "CERTIFIED_SUPPORTING",
                },
                {
                    "domain_id": "generation_population",
                    "domain": "Generation population",
                    "metric_id": "complete_llm_cases",
                    "value": complete_count,
                    "denominator": "36 canonical cases",
                    "reporting_role": "CERTIFIED_SUPPORTING",
                },
                {
                    "domain_id": "generation_population",
                    "domain": "Generation population",
                    "metric_id": "incomplete_llm_cases",
                    "value": incomplete_count,
                    "denominator": "36 canonical cases",
                    "reporting_role": "CERTIFIED_SUPPORTING",
                },
            ]
        )
        if complete_count != EXPECTED_COMPLETE_LLM_CASE_COUNT:
            raise DashboardDataError("Methods denominator ledger has an invalid complete-case count")
        if incomplete_count != EXPECTED_INCOMPLETE_LLM_CASE_COUNT:
            raise DashboardDataError("Methods denominator ledger has an invalid incomplete-case count")

        output = pd.concat(
            [case_rows, selected[["domain_id", "domain", "metric_id", "value", "denominator", "reporting_role"]]],
            ignore_index=True,
        )
        return output.reset_index(drop=True)

    def statistical_family_summary(self) -> pd.DataFrame:
        rows = [
            {
                "family_id": "primary_omnibus",
                "family": "Primary omnibus effects",
                "frozen_output_count": len(self._frame("omnibus_tests")),
                "unit": "36 canonical cases",
                "role": "Model, evidence and interaction effects",
                "source": "omnibus_tests.csv",
            },
            {
                "family_id": "planned_primary_contrasts",
                "family": "Planned primary contrasts",
                "frozen_output_count": len(self._frame("paired_tests")),
                "unit": "Paired canonical case",
                "role": "Frozen primary comparisons",
                "source": "paired_tests.csv",
            },
            {
                "family_id": "conditional_semantic_contrasts",
                "family": "Conditional semantic contrasts",
                "frozen_output_count": len(self._frame("conditional_paired_tests")),
                "unit": "Observed paired cases",
                "role": "Conditional metrics with explicit exclusions",
                "source": "conditional_paired_tests.csv",
            },
            {
                "family_id": "candidate_v4_sensitivity",
                "family": "Candidate–V4 sensitivity",
                "frozen_output_count": len(self._frame("validator_sensitivity_tests")),
                "unit": "36 paired cases",
                "role": "Measurement-artifact robustness",
                "source": "validator_sensitivity_tests.csv",
            },
            {
                "family_id": "llm_template_comparison",
                "family": "LLM–Template comparison",
                "frozen_output_count": len(self._frame("llm_vs_template_tests")),
                "unit": "36 planned case pairs",
                "role": "Deterministic baseline extension",
                "source": "llm_vs_template_tests.csv",
            },
        ]
        return pd.DataFrame(rows)

    def limitations_registry(self) -> pd.DataFrame:
        rows = [
            {
                "limitation_id": "cohort_external_validity",
                "category_id": "cohort_external_validity",
                "category": "Cohort and external validity",
                "limitation": "The cohort contains 36 canonical cases.",
                "affected_scope": "RQ1–RQ6",
                "prevents": "Universal or population-wide generalization.",
                "remains_valid": "Within-cohort controlled comparisons.",
                "required_wording": "Findings are conditional on the frozen cohort, prompts, models and evidence construction.",
            },
            {
                "limitation_id": "measurement_system",
                "category_id": "measurement_system",
                "category": "Measurement system",
                "limitation": "Claim extraction and deterministic validation can introduce measurement error.",
                "affected_scope": "RQ1–RQ6",
                "prevents": "Treating Candidate or V4 as human ground truth.",
                "remains_valid": "Candidate-primary results with V4 sensitivity analysis.",
                "required_wording": "Candidate is primary; V4 is sensitivity-only.",
            },
            {
                "limitation_id": "structured_missingness",
                "category_id": "missingness_inference",
                "category": "Missingness and inference",
                "limitation": "Ten unusable LLM generations are structured S4 failures.",
                "affected_scope": "RQ1–RQ3",
                "prevents": "Imputing conditional scores or assuming missing completely at random.",
                "remains_valid": "Operational E2E with zero penalty and observed-pair conditional analyses.",
                "required_wording": "Conditional metrics remain missing for unusable generations.",
            },
            {
                "limitation_id": "template_baseline",
                "category_id": "template_baseline",
                "category": "Template baseline",
                "limitation": "Template is non-LLM only at narrative generation and uses a distinct structured extraction channel.",
                "affected_scope": "RQ6",
                "prevents": "Calling Template a fourth LLM or claiming precise zero latency.",
                "remains_valid": "Same-case, same-evidence deterministic-reference comparisons.",
                "required_wording": "Template is a deterministic reference; latency is measurement-floor limited.",
            },
            {
                "limitation_id": "human_quality_decisions",
                "category_id": "human_quality_decisions",
                "category": "Human quality and decisions",
                "limitation": "Human naturalness, usefulness, trust and preference were not evaluated.",
                "affected_scope": "RQ3–RQ6",
                "prevents": "Human-equivalence or user-preference claims.",
                "remains_valid": "Deterministic structure, evidence-use and claim-faithfulness analyses.",
                "required_wording": "Human-perceived quality was not evaluated; utility is not probability or statistical significance.",
            },
        ]
        return pd.DataFrame(rows)

    def reproduction_registry(self) -> pd.DataFrame:
        rows = []
        for order, (label, command) in enumerate(METHODS_REPRODUCTION_COMMANDS, start=1):
            rows.append(
                {
                    "step_order": order,
                    "step_id": (
                        "build_visualization_marts",
                        "run_dashboard_tests",
                        "start_dash_application",
                        "run_browser_e2e",
                    )[order - 1],
                    "step_label": label,
                    "command": command,
                    "status_id": "registered_command",
                    "status": "Registered command",
                }
            )
        return pd.DataFrame(rows)

    def methods_data(self) -> MethodsData:
        missing = sorted(set(METHODS_REQUIRED_DATASETS) - set(self._guard.datasets))
        if missing:
            raise DashboardDataError(f"Methods datasets missing from manifest: {missing}")
        gates = self.validation_gate_registry()
        if not all(item.passed for item in gates):
            raise DashboardDataError("One or more frozen methods gates are not ready")
        visibility = self.metric_visibility_registry()
        visibility = visibility.copy()
        visibility["tier_label"] = visibility["visibility_tier"].map(
            METHODS_VISIBILITY_TIER_LABELS
        )
        visibility["tier_description"] = visibility["visibility_tier"].map(
            METHODS_VISIBILITY_TIER_DESCRIPTIONS
        )
        return MethodsData(
            release=self.release,
            release_audit=self.release_audit(),
            validation_gates=gates,
            certified_numbers=self.certified_numbers(),
            research_questions=self.research_question_registry(),
            metric_visibility=visibility,
            visualization_dictionary=self.visualization_dictionary(),
            artifact_inventory=self.artifact_inventory(),
            statistical_families=self.statistical_family_summary(),
            denominator_ledger=self.denominator_ledger(),
            limitations=self.limitations_registry(),
            reproduction_steps=self.reproduction_registry(),
        )


    def robustness_data(self) -> RobustnessData:
        return RobustnessData(
            release=self.release,
            validator_pairs=self.validator_generation_pairs(),
            validator_summary=self.validator_metric_summary(),
            validator_tests=self.validator_sensitivity_tests(),
            baseline_generations=self.baseline_generation_metrics(),
            baseline_options=self.baseline_option_performance(),
            baseline_pairs=self.llm_vs_template_case_pairs(),
            baseline_summary=self.llm_vs_template_summary(),
            baseline_tests=self.llm_vs_template_tests(),
        )

    def effectiveness_data(self) -> EffectivenessData:
        options = self.option_performance()
        loss_columns = [
            "mean_end_to_end_yield",
            "mean_pipeline_loss",
            "mean_not_verifiable_loss",
            "mean_unsupported_loss",
            "mean_contradiction_loss",
        ]
        loss_total = options[loss_columns].astype(float).sum(axis=1)
        if not np.allclose(loss_total, 1.0, atol=1e-9):
            raise DashboardDataError(
                "Mutually exclusive operational success/loss identity failed"
            )
        omnibus = self.omnibus_tests()
        if set(omnibus["effect"]) != {"model", "evidence", "model:evidence"}:
            raise DashboardDataError("Primary omnibus effect set is incomplete")
        return EffectivenessData(
            release=self.release,
            option_performance=options,
            descriptive_statistics=self.descriptive_statistics(),
            omnibus_tests=omnibus,
            paired_tests=self.paired_tests(),
            conditional_paired_tests=self.conditional_paired_tests(),
            complete_case_omnibus_tests=self.complete_case_omnibus_tests(),
            sensitivity_summary=self.statistical_sensitivity_summary(),
            unusable_generations=self.unusable_generations(),
            case_metrics=self.case_metrics(),
        )


@lru_cache(maxsize=1)
def get_dashboard_repository() -> DashboardRepository:
    """Return the single immutable repository for the frozen release."""

    return DashboardRepository()
