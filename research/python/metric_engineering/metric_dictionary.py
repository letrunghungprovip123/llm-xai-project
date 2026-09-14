"""Define the materialized metrics in one auditable dictionary."""

from __future__ import annotations

import pandas as pd


METRIC_DEFINITIONS = [
    {
        "metric_id": "quality_metric_eligible",
        "display_name": "Quality metric eligible",
        "pillar": "quality",
        "grain": "generation",
        "formula": "usable AND applicable_count > 0",
        "numerator": "not_applicable",
        "denominator": "not_applicable",
        "eligibility_rule": "all planned generations",
        "zero_denominator_rule": "not_applicable",
        "unusable_rule": "false",
        "aggregation_guidance": "report as a count or rate",
        "direction": "descriptive",
        "minimum": 0,
        "maximum": 1,
        "interpretation": "Generation can produce applicable quality rates.",
    },
    {
        "metric_id": "resolved_faithfulness",
        "display_name": "Resolved faithfulness",
        "pillar": "quality",
        "grain": "generation",
        "formula": "supported_count / resolved_count",
        "numerator": "supported_count",
        "denominator": "resolved_count",
        "eligibility_rule": "usable AND resolved_count > 0",
        "zero_denominator_rule": "null",
        "unusable_rule": "null",
        "aggregation_guidance": "use micro ratio or report generation distribution",
        "direction": "higher_is_better",
        "minimum": 0,
        "maximum": 1,
        "interpretation": "Supported share among claims with a resolved verdict.",
    },
    {
        "metric_id": "verifiability",
        "display_name": "Verifiability",
        "pillar": "quality",
        "grain": "generation",
        "formula": "resolved_count / applicable_count",
        "numerator": "resolved_count",
        "denominator": "applicable_count",
        "eligibility_rule": "usable AND applicable_count > 0",
        "zero_denominator_rule": "null",
        "unusable_rule": "null",
        "aggregation_guidance": "use micro ratio or report generation distribution",
        "direction": "higher_is_better",
        "minimum": 0,
        "maximum": 1,
        "interpretation": "Applicable claims that receive a resolved verdict.",
    },
    {
        "metric_id": "conservative_faithfulness",
        "display_name": "Conservative faithfulness",
        "pillar": "quality",
        "grain": "generation",
        "formula": "supported_count / applicable_count",
        "numerator": "supported_count",
        "denominator": "applicable_count",
        "eligibility_rule": "usable AND applicable_count > 0",
        "zero_denominator_rule": "null",
        "unusable_rule": "null",
        "aggregation_guidance": "use micro ratio or report generation distribution",
        "direction": "higher_is_better",
        "minimum": 0,
        "maximum": 1,
        "interpretation": "Supported share when not-verifiable claims are non-successes.",
    },
    {
        "metric_id": "end_to_end_faithfulness_yield",
        "display_name": "End-to-end operational faithfulness yield",
        "pillar": "quality",
        "grain": "planned_generation",
        "formula": "conservative_faithfulness when eligible, otherwise 0",
        "numerator": "supported_count",
        "denominator": "applicable_count with planned-generation failure penalty",
        "eligibility_rule": "all planned generations",
        "zero_denominator_rule": "0",
        "unusable_rule": "0",
        "aggregation_guidance": "macro mean over all planned generations",
        "direction": "higher_is_better",
        "minimum": 0,
        "maximum": 1,
        "interpretation": "Primary operational endpoint: validator-based quality yield including generation pipeline failures.",
    },
    {
        "metric_id": "not_verifiable_rate",
        "display_name": "Not-verifiable rate",
        "pillar": "quality",
        "grain": "generation",
        "formula": "not_verifiable_count / applicable_count",
        "numerator": "not_verifiable_count",
        "denominator": "applicable_count",
        "eligibility_rule": "usable AND applicable_count > 0",
        "zero_denominator_rule": "null",
        "unusable_rule": "null",
        "aggregation_guidance": "use micro ratio or report generation distribution",
        "direction": "lower_is_better",
        "minimum": 0,
        "maximum": 1,
        "interpretation": "Applicable claims that cannot be resolved from evidence.",
    },
    {
        "metric_id": "unsupported_rate",
        "display_name": "Unsupported rate",
        "pillar": "quality",
        "grain": "generation",
        "formula": "unsupported_count / applicable_count",
        "numerator": "unsupported_count",
        "denominator": "applicable_count",
        "eligibility_rule": "usable AND applicable_count > 0",
        "zero_denominator_rule": "null",
        "unusable_rule": "null",
        "aggregation_guidance": "use micro ratio or report generation distribution",
        "direction": "lower_is_better",
        "minimum": 0,
        "maximum": 1,
        "interpretation": "Applicable claims unsupported by the evidence.",
    },
    {
        "metric_id": "contradiction_rate",
        "display_name": "Contradiction rate",
        "pillar": "quality",
        "grain": "generation",
        "formula": "contradicted_count / applicable_count",
        "numerator": "contradicted_count",
        "denominator": "applicable_count",
        "eligibility_rule": "usable AND applicable_count > 0",
        "zero_denominator_rule": "null",
        "unusable_rule": "null",
        "aggregation_guidance": "use micro ratio or report generation distribution",
        "direction": "lower_is_better",
        "minimum": 0,
        "maximum": 1,
        "interpretation": "Applicable claims contradicted by the evidence.",
    },
    {
        "metric_id": "resolved_error_rate",
        "display_name": "Resolved error rate",
        "pillar": "quality",
        "grain": "generation",
        "formula": "(unsupported_count + contradicted_count) / resolved_count",
        "numerator": "unsupported_count + contradicted_count",
        "denominator": "resolved_count",
        "eligibility_rule": "usable AND resolved_count > 0",
        "zero_denominator_rule": "null",
        "unusable_rule": "null",
        "aggregation_guidance": "use micro ratio or report generation distribution",
        "direction": "lower_is_better",
        "minimum": 0,
        "maximum": 1,
        "interpretation": "Error share among claims with a resolved verdict.",
    },
    {
        "metric_id": "is_strict_all_supported",
        "display_name": "Strict all-supported generation",
        "pillar": "quality",
        "grain": "generation",
        "formula": "usable AND applicable_count > 0 AND supported_count = applicable_count",
        "numerator": "not_applicable",
        "denominator": "not_applicable",
        "eligibility_rule": "all planned generations",
        "zero_denominator_rule": "not_applicable",
        "unusable_rule": "false",
        "aggregation_guidance": "mean gives strict all-supported generation rate",
        "direction": "higher_is_better",
        "minimum": 0,
        "maximum": 1,
        "interpretation": "No applicable claim is unsupported, contradicted or unverifiable.",
    },
    {
        "metric_id": "has_faithfulness_error",
        "display_name": "Has faithfulness error",
        "pillar": "quality",
        "grain": "generation",
        "formula": "usable AND unsupported_count + contradicted_count > 0",
        "numerator": "not_applicable",
        "denominator": "not_applicable",
        "eligibility_rule": "all planned generations",
        "zero_denominator_rule": "not_applicable",
        "unusable_rule": "false",
        "aggregation_guidance": "mean gives generation error incidence",
        "direction": "lower_is_better",
        "minimum": 0,
        "maximum": 1,
        "interpretation": "At least one resolved claim is erroneous.",
    },
]


_FLAG_DEFINITIONS = [
    ("is_unusable", "Unusable generation", "NOT usable", "lower_is_better"),
    ("is_truncated", "Truncated generation", "truncated_response", "lower_is_better"),
    ("is_parse_success", "Parse success", "raw_json_parse_success AND json_parse_success", "higher_is_better"),
    ("is_schema_valid", "Schema valid", "schema_valid", "higher_is_better"),
    ("is_first_attempt_success", "First-attempt success", "usable AND retry_count = 0", "higher_is_better"),
    ("was_retried", "Was retried", "retry_count > 0", "descriptive"),
    ("is_strict_pipeline_success", "Strict pipeline success", "usable AND runtime SUCCESS AND not truncated AND parse success AND schema valid AND claim_count > 0", "higher_is_better"),
]

for metric_id, display_name, formula, direction in _FLAG_DEFINITIONS:
    METRIC_DEFINITIONS.append(
        {
            "metric_id": metric_id,
            "display_name": display_name,
            "pillar": "reliability",
            "grain": "planned_generation",
            "formula": formula,
            "numerator": "not_applicable",
            "denominator": "not_applicable",
            "eligibility_rule": "all planned generations",
            "zero_denominator_rule": "not_applicable",
            "unusable_rule": "defined by formula",
            "aggregation_guidance": "mean gives planned-generation rate",
            "direction": direction,
            "minimum": 0,
            "maximum": 1,
            "interpretation": display_name,
        }
    )


_EFFICIENCY_DEFINITIONS = [
    ("latency_seconds", "Latency seconds", "latency_ms / 1000", "latency_ms", "1000", "lower_is_better", "Observed generation latency."),
    ("output_tokens_per_second", "Output tokens per second", "output_token_count / latency_seconds", "output_token_count", "latency_seconds", "higher_is_better", "Observed output-token throughput."),
    ("claims_per_second", "Claims per second", "claim_count / latency_seconds", "claim_count", "latency_seconds", "higher_is_better", "Finalized claims produced per second."),
    ("supported_claims_per_second", "Supported claims per second", "supported_count / latency_seconds", "supported_count", "latency_seconds", "higher_is_better", "Supported claims produced per second."),
    ("latency_per_supported_claim_seconds", "Latency per supported claim", "latency_seconds / supported_count", "latency_seconds", "supported_count", "lower_is_better", "Observed latency required per supported claim."),
    ("claims_per_1000_total_tokens", "Claims per 1000 total tokens", "claim_count * 1000 / total_token_count", "claim_count * 1000", "total_token_count", "higher_is_better", "Finalized claim yield per 1000 total tokens."),
    ("supported_claims_per_1000_total_tokens", "Supported claims per 1000 total tokens", "supported_count * 1000 / total_token_count", "supported_count * 1000", "total_token_count", "higher_is_better", "Supported claim yield per 1000 total tokens."),
    ("output_tokens_per_supported_claim", "Output tokens per supported claim", "output_token_count / supported_count", "output_token_count", "supported_count", "lower_is_better", "Output-token expenditure per supported claim."),
]

for (
    metric_id,
    display_name,
    formula,
    numerator,
    denominator,
    direction,
    interpretation,
) in _EFFICIENCY_DEFINITIONS:
    METRIC_DEFINITIONS.append(
        {
            "metric_id": metric_id,
            "display_name": display_name,
            "pillar": "speed" if "second" in metric_id else "token_efficiency",
            "grain": "generation",
            "formula": formula,
            "numerator": numerator,
            "denominator": denominator,
            "eligibility_rule": "denominator > 0",
            "zero_denominator_rule": "null",
            "unusable_rule": "calculated from observed resource values",
            "aggregation_guidance": "summarize distribution; do not average ratios blindly for micro analysis",
            "direction": direction,
            "minimum": 0,
            "maximum": None,
            "interpretation": interpretation,
        }
    )


def build_metric_dictionary() -> pd.DataFrame:
    """Return one row per materialized metric with reporting contracts."""

    dictionary = pd.DataFrame(METRIC_DEFINITIONS).reset_index(drop=True)
    primary_metric = "end_to_end_faithfulness_yield"
    conditional_metrics = {
        "resolved_faithfulness",
        "verifiability",
        "conservative_faithfulness",
    }

    dictionary["endpoint_role"] = "DESCRIPTIVE"
    dictionary.loc[
        dictionary["metric_id"].eq(primary_metric),
        "endpoint_role",
    ] = "PRIMARY"
    dictionary.loc[
        dictionary["metric_id"].isin(conditional_metrics),
        "endpoint_role",
    ] = "SECONDARY_CONDITIONAL"

    dictionary["inference_population"] = "not_for_primary_inference"
    dictionary.loc[
        dictionary["metric_id"].eq(primary_metric),
        "inference_population",
    ] = "all_648_planned_generations"
    dictionary.loc[
        dictionary["metric_id"].isin(conditional_metrics),
        "inference_population",
    ] = "usable_generations_with_defined_denominator"
    dictionary["statistical_unit"] = (
        "generation_repeated_within_canonical_case"
    )
    dictionary["validator_interpretation"] = (
        "operational_measurement_under_frozen_project_ontology"
    )

    return dictionary
