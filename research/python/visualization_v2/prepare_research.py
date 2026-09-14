"""Build the four research-complete presentation marts and registries."""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd

from .config import VISUALIZATION_VERSION


def corrected_evidence_levels(levels: pd.DataFrame) -> pd.DataFrame:
    output = levels.copy()
    output.loc[output["evidence_level"] == "S0", "evidence_label"] = (
        "Prediction-only control"
    )
    return output


def dominant_value(values: pd.Series) -> object:
    non_null = values.dropna().astype(str)
    if non_null.empty:
        return None
    counts = non_null.value_counts()
    return counts.index[0]


def build_evidence_design_summary(input_data: dict[str, Any]) -> pd.DataFrame:
    packages = input_data["evidence_packages"].copy()
    items = input_data["evidence_items"].copy()
    item_summary = items.groupby("package_id", as_index=False).agg(
        evidence_item_count=("evidence_item_id", "count"),
        feature_item_count=(
            "item_type", lambda values: int((values == "feature").sum())
        ),
        concept_item_count=(
            "item_type", lambda values: int((values == "concept").sum())
        ),
        distinct_feature_count=(
            "feature_id", lambda values: int(values.dropna().nunique())
        ),
        distinct_concept_count=(
            "concept_id", lambda values: int(values.dropna().nunique())
        ),
        allowed_item_count=(
            "is_allowed",
            lambda values: int(values.fillna(False).astype(bool).sum()),
        ),
        out_of_contract_item_count=(
            "is_out_of_contract",
            lambda values: int(values.fillna(False).astype(bool).sum()),
        ),
        selected_abs_shap_sum=("selected_abs_shap_sum", "sum"),
        maximum_abs_shap_value=("abs_shap_value", "max"),
    )
    output = packages.merge(
        item_summary,
        on="package_id",
        how="left",
        validate="one_to_one",
    )
    levels = corrected_evidence_levels(input_data["evidence_levels"])
    output = output.drop(columns=["evidence_order"], errors="ignore").merge(
        levels[["evidence_level", "evidence_label", "evidence_order", "intended_role"]],
        on="evidence_level",
        how="left",
        validate="many_to_one",
    )
    output["research_question_id"] = "RQ3"
    output["grain"] = "case_x_evidence_condition"
    output["evidence_condition_is_ordinal"] = False
    output.insert(0, "visualization_version", VISUALIZATION_VERSION)
    preferred = [
        "visualization_version",
        "research_question_id",
        "grain",
        "package_id",
        "case_id",
        "source_ir_id",
        "evidence_level",
        "evidence_label",
        "evidence_order",
        "intended_role",
        "selection_method",
        "selected_evidence_count",
        "evidence_item_count",
        "feature_item_count",
        "concept_item_count",
        "distinct_feature_count",
        "distinct_concept_count",
        "allowed_item_count",
        "out_of_contract_item_count",
        "selected_feature_ids_json",
        "selected_concept_ids_json",
        "coverage",
        "coverage_threshold",
        "coverage_status",
        "coverage_gap",
        "adaptive_k",
        "fixed_top_k",
        "normalized_entropy",
        "entropy_level",
        "total_abs_shap_mass",
        "selected_abs_shap_sum",
        "maximum_abs_shap_value",
        "concept_group_count",
        "unique_concept_count",
        "mixed_concept_group_count",
        "grouped_supporting_feature_count",
        "has_semantic_guidance",
        "has_concept_evidence",
        "has_structural_skeleton",
        "backend_factor_slot_count",
        "required_section_count",
        "policy_must_include_uncertainty",
        "policy_must_include_distributed_note",
        "policy_must_include_partial_note",
        "policy_avoid_single_cause_wording",
        "policy_must_follow_backend_skeleton",
        "policy_must_not_add_outside_skeleton",
        "evidence_condition_is_ordinal",
    ]
    return output[[column for column in preferred if column in output.columns]].sort_values(
        ["evidence_order", "case_id"], kind="stable"
    ).reset_index(drop=True)


def build_claim_reason_summary(claims: pd.DataFrame) -> pd.DataFrame:
    if "primary_reason_code" not in claims.columns:
        return pd.DataFrame({"generation_id": claims["generation_id"].unique()})
    rows: list[dict[str, object]] = []
    for generation_id, group in claims.groupby("generation_id", sort=False):
        unresolved = group.loc[
            group["validation_status"].isin(
                ["NOT_VERIFIABLE", "UNSUPPORTED", "CONTRADICTED"]
            )
        ]
        rows.append(
            {
                "generation_id": generation_id,
                "dominant_primary_reason_code": dominant_value(
                    group["primary_reason_code"]
                ),
                "dominant_error_reason_code": dominant_value(
                    unresolved["primary_reason_code"]
                ),
                "distinct_primary_reason_code_count": int(
                    group["primary_reason_code"].dropna().nunique()
                ),
            }
        )
    return pd.DataFrame(rows)


def llm_generation_base(input_data: dict[str, Any]) -> pd.DataFrame:
    generations = input_data["generations"].copy()
    metrics = input_data["generation_metrics"].copy()
    metric_columns = [
        "generation_id",
        "resolved_faithfulness",
        "verifiability",
        "conservative_faithfulness",
        "end_to_end_faithfulness_yield",
        "not_verifiable_rate",
        "unsupported_rate",
        "contradiction_rate",
        "supported_claims_per_1000_total_tokens",
        "latency_seconds",
        "is_unusable",
        "is_strict_pipeline_success",
    ]
    output = generations.merge(
        metrics[metric_columns],
        on="generation_id",
        how="left",
        validate="one_to_one",
        suffixes=("", "_metric"),
    )
    output = output.merge(
        build_claim_reason_summary(input_data["claims"]),
        on="generation_id",
        how="left",
        validate="one_to_one",
    )
    output["evidence_label"] = output["evidence_label"].replace(
        {"Prediction-only baseline": "Prediction-only control"}
    )
    output["generator_family"] = "LLM"
    output["generator_id"] = output["model_id"]
    output["generator_label"] = output["model_label"]
    output["generator_order"] = output["model_order"]
    output["eligible_for_decision_ranking"] = True
    return output


def baseline_generation_base(input_data: dict[str, Any]) -> pd.DataFrame:
    baseline = input_data["baseline_generation_metrics"].copy()
    cases = input_data["cases"].copy()
    packages = input_data["evidence_packages"].copy()
    levels = corrected_evidence_levels(input_data["evidence_levels"])
    output = baseline.merge(
        cases,
        on="case_id",
        how="left",
        validate="many_to_one",
        suffixes=("", "_case"),
    ).merge(
        packages,
        on=["case_id", "evidence_level", "package_id"],
        how="left",
        validate="one_to_one",
        suffixes=("", "_package"),
    ).merge(
        levels[["evidence_level", "evidence_label", "evidence_order", "intended_role"]],
        on="evidence_level",
        how="left",
        validate="many_to_one",
    )
    output["generator_family"] = "TEMPLATE"
    output["generator_id"] = "template_baseline"
    output["generator_label"] = "Deterministic Template Baseline"
    output["generator_order"] = 4
    output["model_id"] = "template_baseline"
    output["model_label"] = "Deterministic Template Baseline"
    output["model_order"] = 4
    output["eligible_for_decision_ranking"] = False
    output["is_unusable"] = ~output["usable"].astype(bool)
    output["is_strict_pipeline_success"] = output["usable"].astype(bool)
    output["supported_claims_per_1000_total_tokens"] = np.nan
    output["dominant_primary_reason_code"] = "STRUCTURED_TEMPLATE_ADAPTER"
    output["dominant_error_reason_code"] = None
    output["distinct_primary_reason_code_count"] = np.nan
    return output


def build_evidence_utilization_summary(input_data: dict[str, Any]) -> pd.DataFrame:
    llm = llm_generation_base(input_data)
    baseline = baseline_generation_base(input_data)
    columns = [
        "generation_id",
        "generator_family",
        "generator_id",
        "generator_label",
        "generator_order",
        "eligible_for_decision_ranking",
        "case_id",
        "selection_stratum",
        "prediction_outcome",
        "distance_from_threshold",
        "evidence_level",
        "evidence_label",
        "evidence_order",
        "package_id",
        "selected_evidence_count",
        "selected_feature_mention_count",
        "selected_feature_mention_rate",
        "concept_evidence_count",
        "concept_mention_count",
        "concept_mention_rate",
        "top1_mention_rate",
        "top3_mention_rate",
        "top5_mention_rate",
        "invalid_declared_feature_count",
        "invalid_declared_concept_count",
        "coverage",
        "normalized_entropy",
        "concept_group_count",
        "mixed_concept_group_count",
        "claim_count",
        "supported_count",
        "not_verifiable_count",
        "unsupported_count",
        "contradicted_count",
        "resolved_faithfulness",
        "verifiability",
        "conservative_faithfulness",
        "end_to_end_faithfulness_yield",
        "dominant_primary_reason_code",
        "dominant_error_reason_code",
        "distinct_primary_reason_code_count",
    ]
    for frame in (llm, baseline):
        for column in columns:
            if column not in frame.columns:
                frame[column] = np.nan
    output = pd.concat([llm[columns], baseline[columns]], ignore_index=True)
    output.insert(0, "visualization_version", VISUALIZATION_VERSION)
    output.insert(1, "research_question_id", "RQ3")
    output.insert(2, "grain", "generation")
    return output.sort_values(
        ["generator_order", "evidence_order", "case_id"], kind="stable"
    ).reset_index(drop=True)


def build_narrative_structure_summary(input_data: dict[str, Any]) -> pd.DataFrame:
    llm = llm_generation_base(input_data)
    baseline = baseline_generation_base(input_data)
    columns = [
        "generation_id",
        "generator_family",
        "generator_id",
        "generator_label",
        "generator_order",
        "eligible_for_decision_ranking",
        "case_id",
        "selection_stratum",
        "evidence_level",
        "evidence_label",
        "evidence_order",
        "usable",
        "runtime_status",
        "output_char_count",
        "output_word_count",
        "sentence_count",
        "total_factor_count",
        "main_factor_count",
        "supporting_factor_count",
        "technical_term_count",
        "technical_term_ratio",
        "has_prediction_summary",
        "has_factors",
        "has_uncertainty_note",
        "has_distributed_evidence_note",
        "has_safe_summary",
        "uncertainty_required",
        "uncertainty_compliant",
        "distributed_note_required",
        "distributed_note_compliant",
        "partial_evidence_note_required",
        "partial_evidence_note_compliant",
        "single_cause_violation",
        "forbidden_phrase_violation",
        "has_backend_skeleton_section",
        "has_structural_skeleton",
        "end_to_end_faithfulness_yield",
        "conservative_faithfulness",
        "latency_seconds",
        "total_token_count",
    ]
    for frame in (llm, baseline):
        for column in columns:
            if column not in frame.columns:
                frame[column] = np.nan
    output = pd.concat([llm[columns], baseline[columns]], ignore_index=True)
    output["uncertainty_policy_pass"] = np.where(
        output["uncertainty_required"].fillna(False).astype(bool),
        output["uncertainty_compliant"].fillna(False).astype(bool),
        True,
    )
    output["distributed_policy_pass"] = np.where(
        output["distributed_note_required"].fillna(False).astype(bool),
        output["distributed_note_compliant"].map(
            lambda value: bool(value) if pd.notna(value) else False
        ),
        True,
    )
    output["partial_evidence_policy_pass"] = np.where(
        output["partial_evidence_note_required"].fillna(False).astype(bool),
        output["partial_evidence_note_compliant"].map(
            lambda value: bool(value) if pd.notna(value) else False
        ),
        True,
    )
    output["overall_policy_compliant"] = (
        output["uncertainty_policy_pass"]
        & output["distributed_policy_pass"]
        & output["partial_evidence_policy_pass"]
        & ~output["single_cause_violation"].fillna(False).astype(bool)
        & ~output["forbidden_phrase_violation"].fillna(False).astype(bool)
    )
    output.insert(0, "visualization_version", VISUALIZATION_VERSION)
    output.insert(1, "research_question_id", "RQ3")
    output.insert(2, "grain", "generation")
    output["human_naturalness_measured"] = False
    return output.sort_values(
        ["generator_order", "evidence_order", "case_id"], kind="stable"
    ).reset_index(drop=True)


def build_case_heterogeneity_summary(input_data: dict[str, Any]) -> pd.DataFrame:
    llm = llm_generation_base(input_data)
    baseline = baseline_generation_base(input_data)
    columns = [
        "generation_id",
        "generator_family",
        "generator_id",
        "generator_label",
        "generator_order",
        "eligible_for_decision_ranking",
        "case_id",
        "source_ir_id",
        "row_index",
        "selection_stratum",
        "selection_rank",
        "has_ground_truth",
        "true_label",
        "true_label_text",
        "predicted_class",
        "predicted_label",
        "prediction_probability",
        "decision_threshold",
        "threshold_comparison",
        "prediction_correct",
        "prediction_outcome",
        "distance_from_threshold",
        "evidence_level",
        "evidence_label",
        "evidence_order",
        "usable",
        "is_unusable",
        "runtime_status",
        "claim_count",
        "supported_count",
        "not_verifiable_count",
        "unsupported_count",
        "contradicted_count",
        "resolved_faithfulness",
        "verifiability",
        "conservative_faithfulness",
        "end_to_end_faithfulness_yield",
        "output_word_count",
        "latency_seconds",
    ]
    for frame in (llm, baseline):
        for column in columns:
            if column not in frame.columns:
                frame[column] = np.nan
    output = pd.concat([llm[columns], baseline[columns]], ignore_index=True)
    output["threshold_distance_band"] = pd.cut(
        output["distance_from_threshold"].astype(float),
        bins=[-np.inf, 0.01, 0.05, 0.20, np.inf],
        labels=["NEAR_0_01", "NEAR_0_05", "MID_0_20", "FAR_GT_0_20"],
        right=True,
    ).astype("string")
    output["complete_llm_case"] = output["case_id"].isin(
        input_data["generation_metrics"]
        .groupby("case_id")["usable"]
        .agg(lambda values: bool(values.astype(bool).all()))
        .loc[lambda values: values]
        .index
    )
    output.insert(0, "visualization_version", VISUALIZATION_VERSION)
    output.insert(1, "research_question_ids", "RQ1|RQ2|RQ3|RQ6")
    output.insert(2, "grain", "generation")
    return output.sort_values(
        ["case_id", "generator_order", "evidence_order"], kind="stable"
    ).reset_index(drop=True)


def build_rq_registry(contract: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for order, rq in enumerate(contract["research_questions"], start=1):
        row = {
            "visualization_version": VISUALIZATION_VERSION,
            "rq_order": order,
            "rq_id": rq["rq_id"],
            "title": rq["title"],
            "question": rq["question"],
            "status": rq["status"],
            "population": rq["population"],
            "unit_of_inference": rq["unit_of_inference"],
        }
        for field in [
            "primary_metrics",
            "supporting_metrics",
            "primary_sources",
            "dashboard_pages",
            "interpretation_restrictions",
        ]:
            row[f"{field}_json"] = json.dumps(
                rq.get(field, []), ensure_ascii=False, separators=(",", ":")
            )
        rows.append(row)
    return pd.DataFrame(rows)


def build_metric_visibility_registry(contract: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for tier, metric_ids in contract["tiers"].items():
        for metric_id in metric_ids:
            rows.append(
                {
                    "visualization_version": VISUALIZATION_VERSION,
                    "metric_id": metric_id,
                    "visibility_tier": tier,
                    "dashboard_enabled": tier in {"A_HEADLINE", "B_EXPLANATORY"},
                    "requires_additional_data": tier == "D_DISABLED_UNTIL_BETTER_DATA",
                }
            )
    return pd.DataFrame(rows)



def build_certified_report_numbers(
    report_numbers: dict[str, Any],
) -> pd.DataFrame:
    """Flatten the frozen report headline numbers for dashboard cards.

    The table intentionally excludes inferential rows, which are carried by
    their certified statistical datasets. Every row records the reporting
    role and denominator semantics so UI components never infer them.
    """

    rows: list[dict[str, object]] = []
    denominator_labels = {
        "planned_llm_generations": "all planned LLM generations",
        "usable_llm_generations": "usable LLM generations",
        "unusable_llm_generations": "unusable LLM generations",
        "final_atomic_claims": "all finalized atomic claims",
        "applicable_claims": "applicable finalized claims",
        "resolved_claims": "resolved finalized claims",
    }
    for metric_id, value in report_numbers.get("denominators", {}).items():
        rows.append(
            {
                "visualization_version": VISUALIZATION_VERSION,
                "report_section": "denominator",
                "metric_id": metric_id,
                "value": value,
                "value_type": "count",
                "denominator": denominator_labels.get(
                    metric_id, "not applicable"
                ),
                "reporting_role": "CERTIFIED_HEADLINE",
                "source_contract": "report_numbers.json",
            }
        )

    primary_denominators = {
        "mean_end_to_end_operational_faithfulness": "648 planned generations",
        "usability_rate": "648 planned generations",
        "micro_conservative_faithfulness": "14,655 applicable claims",
        "micro_verifiability": "14,667 finalized claims",
        "micro_resolved_faithfulness": "13,637 resolved claims",
    }
    for metric_id, value in report_numbers.get("primary_metrics", {}).items():
        rows.append(
            {
                "visualization_version": VISUALIZATION_VERSION,
                "report_section": "primary_metric",
                "metric_id": metric_id,
                "value": value,
                "value_type": "rate",
                "denominator": primary_denominators.get(
                    metric_id, "see metric dictionary"
                ),
                "reporting_role": "CERTIFIED_HEADLINE",
                "source_contract": "report_numbers.json",
            }
        )

    for status, value in report_numbers.get("claim_status_counts", {}).items():
        rows.append(
            {
                "visualization_version": VISUALIZATION_VERSION,
                "report_section": "claim_status",
                "metric_id": f"claim_status_{status.lower()}",
                "value": value,
                "value_type": "count",
                "denominator": "14,667 finalized atomic claims",
                "reporting_role": "CERTIFIED_SUPPORTING",
                "source_contract": "report_numbers.json",
            }
        )

    for metric_id in [
        "primary_planned_pair_count",
        "primary_adjusted_significant_pair_count",
    ]:
        rows.append(
            {
                "visualization_version": VISUALIZATION_VERSION,
                "report_section": "planned_contrasts",
                "metric_id": metric_id,
                "value": report_numbers[metric_id],
                "value_type": "count",
                "denominator": "33 frozen primary planned contrasts",
                "reporting_role": "CERTIFIED_SUPPORTING",
                "source_contract": "report_numbers.json",
            }
        )
    return pd.DataFrame(rows)


def build_release_metadata(input_data: dict[str, Any]) -> pd.DataFrame:
    report_manifest = input_data["report_manifest"]
    baseline_manifest = input_data["baseline_manifest"]
    return pd.DataFrame(
        [
            {
                "visualization_version": VISUALIZATION_VERSION,
                "parent_analytical_release": input_data["dashboard_contract"].get(
                    "parent_analytical_release"
                ),
                "parent_analytical_gate": input_data["report_readiness"][
                    "exit_gate"
                ],
                "parent_release_id": report_manifest.get("release_id"),
                "parent_release_schema": report_manifest.get("schema_version"),
                "parent_git_commit": report_manifest.get("source_commit"),
                "parent_git_branch": report_manifest.get("git_branch"),
                "parent_source_tree_sha256": report_manifest.get(
                    "source_tree_sha256"
                ),
                "verified_parent_artifact_count": len(
                    input_data["verified_report_paths"]
                ),
                "baseline_gate": input_data["baseline_validation"][
                    "exit_gate"
                ],
                "baseline_comparison_version": baseline_manifest.get(
                    "baseline_comparison_version"
                ),
                "baseline_structured_adapter_version": baseline_manifest.get(
                    "structured_adapter_version"
                ),
                "verified_baseline_artifact_count": len(
                    input_data["verified_baseline_paths"]
                ),
                "primary_claim_measurement_release": baseline_manifest.get(
                    "primary_claim_measurement_release"
                ),
                "statistical_gate": input_data["statistical_validation"][
                    "exit_gate"
                ],
                "validator_sensitivity_gate": input_data[
                    "validator_sensitivity_validation"
                ]["exit_gate"],
                "template_is_fourth_llm": False,
                "template_eligible_for_decision_ranking": False,
                "research_question_count": len(
                    input_data["rq_contract"]["research_questions"]
                ),
                "dashboard_page_count": len(
                    input_data["dashboard_contract"]["pages"]
                ),
                "human_naturalness_evaluated": False,
                "claim_extraction_channel_identical_to_llm": False,
                "template_latency_measurement_floor_limited": True,
            }
        ]
    )
