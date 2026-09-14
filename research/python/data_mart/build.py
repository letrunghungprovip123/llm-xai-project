"""Build the relational Batch 12 analytical tables.

This module deliberately performs only data preparation.  It creates stable
keys, raw counts and diagnostic flags, but it does not calculate research
quality metrics or statistical comparisons.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .config import (
    EVIDENCE_LEVEL_DEFINITIONS,
    MODEL_LABELS,
    TABLE_FILE_NAMES,
)
from .case_metadata import extract_case_metadata
from .load import InputData, JsonRecord


OUTPUT_DROP_COLUMNS = {
    "claims": [
        "source_span_start",
        "source_span_end",
        "source_input_sha256",
        "extractor_provider",
        "extractor_model_id",
        "extractor_version",
        "extractor_prompt_version",
        "extractor_prompt_sha256",
        "extractor_status",
        "model_normalized_claim_key",
        "validation_generation_id",
        "validation_case_id",
        "validation_model_id",
        "validation_evidence_level",
        "validation_repeat_id",
        "validation_match_status",
        "source_record_keys_json",
        "expected_json",
        "observed_json",
    ],
    "generations": [
        "case_selection_stratum_source",
        "case_prediction_outcome_source",
        "case_true_label_source",
        "selected_evidence_count_source",
        "coverage_source",
        "coverage_threshold_source",
        "coverage_status_source",
        "adaptive_k_source",
        "entropy_level_source",
        "normalized_entropy_source",
        "concept_group_count_source",
        "mixed_concept_group_count_source",
        "has_concept_evidence_source",
        "raw_output",
        "cleaned_output",
        "parsed_output_json",
        "case_join_status",
        "model_join_status",
        "evidence_level_join_status",
        "package_case_id",
        "package_evidence_level",
        "package_join_status",
        "claim_aggregate_join_status",
    ],
}


CLAIM_TYPES = (
    "prediction",
    "feature_presence",
    "feature_direction",
    "concept_presence",
    "concept_direction",
    "numeric",
    "ranking",
    "magnitude",
    "uncertainty",
    "limitation",
    "distributed_evidence",
    "recommendation",
)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _json_text(value: Any) -> str:
    """Serialize nested values consistently for CSV outputs."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _case_id_from_package(package: JsonRecord) -> str:
    return extract_case_metadata(package).case_id


def _prediction_outcome(true_label: Any, predicted_class: Any) -> str | None:
    if true_label not in (0, 1) or predicted_class not in (0, 1):
        return None

    outcomes = {
        (1, 1): "TP",
        (0, 0): "TN",
        (0, 1): "FP",
        (1, 0): "FN",
    }
    return outcomes[(int(true_label), int(predicted_class))]


def _require_dataframe_columns(
    dataframe: pd.DataFrame,
    required_columns: set[str],
    table_name: str,
) -> None:
    missing_columns = sorted(required_columns - set(dataframe.columns))

    if missing_columns:
        raise ValueError(
            f"{table_name} is missing required columns: {missing_columns}"
        )


def build_cases_table(
    evidence_packages: list[JsonRecord],
) -> pd.DataFrame:
    """Build one case row from each case's S0 evidence package."""

    rows: list[dict[str, Any]] = []
    s0_packages = [
        package
        for package in evidence_packages
        if package.get("evidence_level") == "S0"
    ]

    for package in s0_packages:
        internal_metadata = _dict(package.get("internal_metadata"))
        case_metadata = extract_case_metadata(package)
        ground_truth = _dict(internal_metadata.get("ground_truth"))
        prediction = _dict(package.get("prediction"))

        true_label = ground_truth.get("true_label")
        predicted_class = prediction.get("predicted_class")
        probability = prediction.get("probability")
        threshold = prediction.get("threshold")

        distance_from_threshold = None
        if isinstance(probability, (int, float)) and isinstance(
            threshold,
            (int, float),
        ):
            distance_from_threshold = abs(float(probability) - float(threshold))

        rows.append(
            {
                "case_id": _case_id_from_package(package),
                "source_ir_id": package.get("source_ir_id"),
                "source_evidence_id": package.get("source_evidence_id"),
                "row_index": case_metadata.row_index,
                "selection_stratum": case_metadata.selection_stratum,
                "selection_rank": case_metadata.selection_rank,
                "has_ground_truth": ground_truth.get("has_ground_truth"),
                "true_label": true_label,
                "true_label_text": ground_truth.get("true_label_text"),
                "predicted_class": predicted_class,
                "predicted_label": prediction.get("predicted_label"),
                "prediction_probability": probability,
                "decision_threshold": threshold,
                "threshold_comparison": prediction.get(
                    "threshold_comparison"
                ),
                "is_above_threshold": prediction.get("is_above_threshold"),
                "prediction_correct": (
                    true_label == predicted_class
                    if true_label is not None and predicted_class is not None
                    else None
                ),
                "prediction_outcome": _prediction_outcome(
                    true_label,
                    predicted_class,
                ),
                "distance_from_threshold": distance_from_threshold,
            }
        )

    return (
        pd.DataFrame(rows)
        .sort_values(["selection_stratum", "selection_rank", "case_id"])
        .reset_index(drop=True)
    )


def build_models_table(
    generation_index: list[JsonRecord],
) -> pd.DataFrame:
    """Build one row per generation model from pinned generation metadata."""

    model_records: dict[str, dict[str, Any]] = {}

    for generation in generation_index:
        model_id = str(generation.get("model_id"))
        record = _dict(generation.get("generation_record"))
        decoding = _dict(record.get("decoding_config"))

        candidate = {
            "model_id": model_id,
            "model_order": generation.get("model_order"),
            "model_label": MODEL_LABELS.get(model_id, model_id),
            "model_provider": record.get("model_provider"),
            "remote_model_id": record.get("remote_model_id"),
            "model_family": record.get("model_family"),
            "model_revision": generation.get("model_revision"),
            "revision_status": generation.get("revision_status"),
            "temperature": decoding.get("temperature"),
            "top_p": decoding.get("top_p"),
            "max_tokens": decoding.get("max_tokens"),
            "frequency_penalty": decoding.get("frequency_penalty"),
            "presence_penalty": decoding.get("presence_penalty"),
            "output_constraint_mode": record.get("output_constraint_mode"),
            "prompt_version": generation.get("prompt_version"),
            "output_schema_version": generation.get(
                "output_schema_version"
            ),
        }

        if model_id not in model_records:
            model_records[model_id] = candidate

    return (
        pd.DataFrame(model_records.values())
        .sort_values(["model_order", "model_id"])
        .reset_index(drop=True)
    )


def build_evidence_levels_table() -> pd.DataFrame:
    """Build the fixed S0-S5 experimental evidence definitions."""

    return (
        pd.DataFrame(EVIDENCE_LEVEL_DEFINITIONS)
        .sort_values("evidence_order")
        .reset_index(drop=True)
    )


def build_evidence_packages_table(
    evidence_packages: list[JsonRecord],
) -> pd.DataFrame:
    """Flatten package-level evidence volume, policy and selection metadata."""

    evidence_order = {
        definition["evidence_level"]: definition["evidence_order"]
        for definition in EVIDENCE_LEVEL_DEFINITIONS
    }
    rows: list[dict[str, Any]] = []

    for package in evidence_packages:
        selected_evidence = [
            item
            for item in _list(package.get("selected_evidence"))
            if isinstance(item, dict)
        ]
        concept_evidence = [
            item
            for item in _list(package.get("concept_evidence"))
            if isinstance(item, dict)
        ]
        selection = _dict(package.get("selection_metrics"))
        policy = _dict(package.get("narrative_policy"))
        constraints = _dict(package.get("constraints"))
        claim_policy = _dict(constraints.get("claim_policy"))
        audit_trace = _dict(package.get("audit_trace"))
        skeleton = _dict(package.get("backend_explanation_skeleton"))
        xai_quality = _dict(package.get("xai_quality_metrics"))

        selected_feature_ids = [
            str(item["feature_id"])
            for item in selected_evidence
            if item.get("feature_id") is not None
        ]
        allowed_feature_ids = [
            str(value)
            for value in _list(constraints.get("allowed_feature_ids"))
        ]
        allowed_concept_ids = [
            str(value)
            for value in _list(constraints.get("allowed_concept_ids"))
        ]
        selected_concept_ids = [
            str(item["concept"])
            for item in concept_evidence
            if item.get("concept") is not None
        ]
        out_of_contract_feature_ids = sorted(
            set(selected_feature_ids) - set(allowed_feature_ids)
        )
        out_of_contract_concept_ids = sorted(
            set(selected_concept_ids) - set(allowed_concept_ids)
        )

        rows.append(
            {
                "package_id": package.get("package_id"),
                "case_id": _case_id_from_package(package),
                "source_ir_id": package.get("source_ir_id"),
                "source_evidence_id": package.get("source_evidence_id"),
                "trace_id": package.get("trace_id"),
                "run_mode": package.get("run_mode"),
                "ir_schema_version": package.get("ir_schema_version"),
                "evidence_package_schema_version": package.get(
                    "evidence_package_schema_version"
                ),
                "evidence_level": package.get("evidence_level"),
                "evidence_order": evidence_order.get(
                    str(package.get("evidence_level"))
                ),
                "selected_evidence_count": len(selected_evidence),
                "concept_evidence_count": len(concept_evidence),
                "safe_phrase_count": sum(
                    bool(item.get("safe_phrase"))
                    for item in selected_evidence
                ),
                "allowed_feature_count": len(allowed_feature_ids),
                "allowed_concept_count": len(allowed_concept_ids),
                "exposed_feature_count": len(selected_feature_ids),
                "exposed_concept_count": len(selected_concept_ids),
                "out_of_contract_feature_count": len(
                    out_of_contract_feature_ids
                ),
                "out_of_contract_concept_count": len(
                    out_of_contract_concept_ids
                ),
                "has_semantic_guidance": any(
                    item.get("display_name") or item.get("safe_phrase")
                    for item in selected_evidence
                ),
                "has_concept_evidence": bool(concept_evidence),
                "has_structural_skeleton": bool(skeleton),
                "backend_factor_slot_count": len(
                    _list(skeleton.get("main_factor_slots"))
                ),
                "required_section_count": len(
                    _list(skeleton.get("required_section_order"))
                ),
                "fixed_top_k": selection.get("fixed_top_k"),
                "adaptive_k": selection.get("adaptive_k"),
                "coverage": selection.get("coverage"),
                "coverage_threshold": selection.get("coverage_threshold"),
                "coverage_status": selection.get("coverage_status"),
                "coverage_gap": selection.get("coverage_gap"),
                "reached_k_max": selection.get("reached_k_max"),
                "is_compacted": selection.get("is_compacted"),
                "normalized_entropy": selection.get("normalized_entropy"),
                "entropy_level": selection.get("entropy_level"),
                "total_abs_shap_mass": selection.get(
                    "total_abs_shap_mass"
                ),
                "top10_coverage_from_gplus": selection.get(
                    "top10_coverage_from_gplus"
                ),
                "top20_coverage_from_gplus": selection.get(
                    "top20_coverage_from_gplus"
                ),
                "concept_group_count": selection.get(
                    "concept_group_count"
                ),
                "unique_concept_count": selection.get(
                    "unique_concept_count"
                ),
                "mixed_concept_group_count": selection.get(
                    "mixed_concept_group_count"
                ),
                "grouped_supporting_feature_count": selection.get(
                    "grouped_supporting_feature_count"
                ),
                "policy_must_include_uncertainty": policy.get(
                    "must_include_uncertainty"
                ),
                "policy_avoid_single_cause_wording": policy.get(
                    "avoid_single_cause_wording"
                ),
                "policy_allow_main_reason_wording": policy.get(
                    "allow_main_reason_wording"
                ),
                "policy_must_include_distributed_note": policy.get(
                    "must_include_distributed_evidence_note"
                ),
                "policy_must_include_partial_note": policy.get(
                    "must_include_partial_evidence_note"
                ),
                "policy_must_not_claim_complete": policy.get(
                    "must_not_claim_evidence_is_complete"
                ),
                "policy_mention_mixed_signals": policy.get(
                    "mention_mixed_signals"
                ),
                "policy_backend_controls_factor_order": policy.get(
                    "backend_controls_factor_order"
                ),
                "policy_must_follow_backend_skeleton": policy.get(
                    "must_follow_backend_skeleton"
                ),
                "policy_must_not_add_outside_skeleton": policy.get(
                    "must_not_add_factor_outside_skeleton"
                ),
                "allow_prediction_claim": claim_policy.get(
                    "allow_prediction_claim"
                ),
                "allow_uncertainty_claim": claim_policy.get(
                    "allow_uncertainty_claim"
                ),
                "allow_feature_claim": claim_policy.get(
                    "allow_feature_claim"
                ),
                "allow_concept_claim": claim_policy.get(
                    "allow_concept_claim"
                ),
                "allow_direction_claim": claim_policy.get(
                    "allow_direction_claim"
                ),
                "allow_magnitude_claim": claim_policy.get(
                    "allow_magnitude_claim"
                ),
                "allow_causal_claim": claim_policy.get(
                    "allow_causal_claim"
                ),
                "allow_financial_advice": claim_policy.get(
                    "allow_financial_advice"
                ),
                "selection_method": audit_trace.get("selection_method"),
                "xai_quality_status": xai_quality.get("status"),
                "selected_feature_ids_json": _json_text(
                    selected_feature_ids
                ),
                "selected_concept_ids_json": _json_text(
                    selected_concept_ids
                ),
                "allowed_feature_ids_json": _json_text(
                    allowed_feature_ids
                ),
                "allowed_concept_ids_json": _json_text(
                    allowed_concept_ids
                ),
                "out_of_contract_feature_ids_json": _json_text(
                    out_of_contract_feature_ids
                ),
                "out_of_contract_concept_ids_json": _json_text(
                    out_of_contract_concept_ids
                ),
                "forbidden_rule_ids_json": _json_text(
                    _list(constraints.get("forbidden_rule_ids"))
                ),
            }
        )

    return (
        pd.DataFrame(rows)
        .sort_values(["case_id", "evidence_order", "package_id"])
        .reset_index(drop=True)
    )


def build_evidence_items_table(
    evidence_packages: list[JsonRecord],
) -> pd.DataFrame:
    """Create one row per exposed feature and one row per concept group."""

    rows: list[dict[str, Any]] = []

    for package in evidence_packages:
        package_id = str(package.get("package_id"))
        case_id = _case_id_from_package(package)
        evidence_level = package.get("evidence_level")
        constraints = _dict(package.get("constraints"))
        allowed_feature_ids = {
            str(value)
            for value in _list(constraints.get("allowed_feature_ids"))
        }
        allowed_concept_ids = {
            str(value)
            for value in _list(constraints.get("allowed_concept_ids"))
        }

        selected_evidence = [
            item
            for item in _list(package.get("selected_evidence"))
            if isinstance(item, dict)
        ]
        for item_order, item in enumerate(selected_evidence, start=1):
            feature_id = (
                str(item.get("feature_id"))
                if item.get("feature_id") is not None
                else None
            )
            concept_id = (
                str(item.get("concept"))
                if item.get("concept") is not None
                else None
            )
            is_allowed = (
                feature_id in allowed_feature_ids
                if feature_id is not None
                else False
            )

            rows.append(
                {
                    "evidence_item_id": (
                        f"{package_id}::feature::{item_order:03d}"
                    ),
                    "package_id": package_id,
                    "case_id": case_id,
                    "evidence_level": evidence_level,
                    "item_type": "feature",
                    "item_order": item_order,
                    "feature_id": feature_id,
                    "concept_id": concept_id,
                    "feature_name": item.get("feature_name"),
                    "display_name": item.get("display_name"),
                    "display_name_source": item.get(
                        "display_name_source"
                    ),
                    "concept_display_name": item.get(
                        "concept_display_name"
                    ),
                    "feature_value": item.get("value"),
                    "shap_value": item.get("shap_value"),
                    "abs_shap_value": item.get("abs_shap_value"),
                    "direction": item.get("direction"),
                    "rank": item.get("rank"),
                    "strength": item.get("strength"),
                    "safe_phrase": item.get("safe_phrase"),
                    "is_allowed": is_allowed,
                    "is_out_of_contract": not is_allowed,
                    "representative_feature_id": None,
                    "feature_count": 1,
                    "supporting_feature_count": 0,
                    "selected_abs_shap_sum": item.get(
                        "abs_shap_value"
                    ),
                    "selected_feature_ids_json": _json_text(
                        [feature_id] if feature_id is not None else []
                    ),
                }
            )

        concept_evidence = [
            item
            for item in _list(package.get("concept_evidence"))
            if isinstance(item, dict)
        ]
        for item_order, item in enumerate(concept_evidence, start=1):
            concept_id = (
                str(item.get("concept"))
                if item.get("concept") is not None
                else None
            )
            representative = _dict(item.get("representative_feature"))
            supporting_features = [
                feature
                for feature in _list(item.get("supporting_features"))
                if isinstance(feature, dict)
            ]
            is_allowed = (
                concept_id in allowed_concept_ids
                if concept_id is not None
                else False
            )

            rows.append(
                {
                    "evidence_item_id": (
                        f"{package_id}::concept::{item_order:03d}"
                    ),
                    "package_id": package_id,
                    "case_id": case_id,
                    "evidence_level": evidence_level,
                    "item_type": "concept",
                    "item_order": item_order,
                    "feature_id": None,
                    "concept_id": concept_id,
                    "feature_name": None,
                    "display_name": None,
                    "display_name_source": None,
                    "concept_display_name": item.get(
                        "concept_display_name"
                    ),
                    "feature_value": None,
                    "shap_value": None,
                    "abs_shap_value": None,
                    "direction": item.get("direction"),
                    "rank": None,
                    "strength": None,
                    "safe_phrase": None,
                    "is_allowed": is_allowed,
                    "is_out_of_contract": not is_allowed,
                    "representative_feature_id": representative.get(
                        "feature_id"
                    ),
                    "feature_count": item.get("feature_count"),
                    "supporting_feature_count": len(supporting_features),
                    "selected_abs_shap_sum": item.get(
                        "selected_abs_shap_sum"
                    ),
                    "selected_feature_ids_json": _json_text(
                        _list(item.get("selected_feature_ids"))
                    ),
                }
            )

    columns = [
        "evidence_item_id",
        "package_id",
        "case_id",
        "evidence_level",
        "item_type",
        "item_order",
        "feature_id",
        "concept_id",
        "feature_name",
        "display_name",
        "display_name_source",
        "concept_display_name",
        "feature_value",
        "shap_value",
        "abs_shap_value",
        "direction",
        "rank",
        "strength",
        "safe_phrase",
        "is_allowed",
        "is_out_of_contract",
        "representative_feature_id",
        "feature_count",
        "supporting_feature_count",
        "selected_abs_shap_sum",
        "selected_feature_ids_json",
    ]

    if not rows:
        return pd.DataFrame(columns=columns)

    return (
        pd.DataFrame(rows, columns=columns)
        .sort_values(
            ["case_id", "evidence_level", "item_type", "item_order"]
        )
        .reset_index(drop=True)
    )


def build_claims_table(
    final_claims: list[JsonRecord],
    validation_results: list[JsonRecord],
) -> pd.DataFrame:
    """Join final claims to deterministic validation results one-to-one."""

    claims = pd.DataFrame(final_claims)
    validations = pd.DataFrame(validation_results)

    _require_dataframe_columns(
        claims,
        {
            "claim_id",
            "generation_id",
            "case_id",
            "model_id",
            "evidence_level",
            "claim_type",
            "claim_subtype",
        },
        "final claims",
    )
    _require_dataframe_columns(
        validations,
        {
            "validation_id",
            "claim_id",
            "generation_id",
            "case_id",
            "model_id",
            "evidence_level",
            "execution_status",
            "validation_status",
            "policy_status",
        },
        "validation results",
    )

    validation_columns = [
        "validation_id",
        "claim_id",
        "generation_id",
        "case_id",
        "model_id",
        "evidence_level",
        "repeat_id",
        "execution_status",
        "validation_status",
        "evidence_status",
        "policy_status",
        "validation_coverage",
        "reason_code",
        "primary_reason_code",
        "reason_codes",
        "expected",
        "observed",
        "message",
        "normalizations_applied",
        "source_record_keys",
        "unresolved_facts",
        "numeric_comparison",
        "feature_exposure_status",
        "concept_exposure_status",
        "error",
    ]
    validation_columns = [
        column for column in validation_columns if column in validations.columns
    ]
    validations = validations[validation_columns].rename(
        columns={
            "generation_id": "validation_generation_id",
            "case_id": "validation_case_id",
            "model_id": "validation_model_id",
            "evidence_level": "validation_evidence_level",
            "repeat_id": "validation_repeat_id",
        }
    )

    merged = claims.merge(
        validations,
        on="claim_id",
        how="left",
        validate="one_to_one",
        indicator=True,
    )
    merged["validation_match_status"] = merged["_merge"].astype(str)
    merged = merged.drop(columns=["_merge"])

    expected_records = [
        _dict(value) for value in merged.get("expected", pd.Series([{}] * len(merged)))
    ]
    observed_records = [
        _dict(value) for value in merged.get("observed", pd.Series([{}] * len(merged)))
    ]

    nested_fields = (
        "prediction_label",
        "probability",
        "numeric_value",
        "numeric_unit",
        "numeric_role",
        "feature_id",
        "concept_id",
        "direction",
        "magnitude",
        "rank",
        "certainty",
        "causal_strength",
        "exposure_status",
    )
    for field in nested_fields:
        merged[f"expected_{field}"] = [
            record.get(field) for record in expected_records
        ]
        merged[f"observed_{field}"] = [
            record.get(field) for record in observed_records
        ]

    for column in (
        "reason_codes",
        "normalizations_applied",
        "source_record_keys",
        "unresolved_facts",
        "numeric_comparison",
        "error",
        "expected",
        "observed",
    ):
        if column in merged.columns:
            merged[f"{column}_json"] = merged[column].map(_json_text)
            merged = merged.drop(columns=[column])

    merged["is_supported"] = merged["validation_status"].eq("SUPPORTED")
    merged["is_unsupported"] = merged["validation_status"].eq(
        "UNSUPPORTED"
    )
    merged["is_contradicted"] = merged["validation_status"].eq(
        "CONTRADICTED"
    )
    merged["is_not_verifiable"] = merged["validation_status"].eq(
        "NOT_VERIFIABLE"
    )
    merged["is_not_applicable"] = merged["validation_status"].eq(
        "NOT_APPLICABLE"
    )
    merged["is_resolved"] = merged["validation_status"].isin(
        ["SUPPORTED", "UNSUPPORTED", "CONTRADICTED"]
    )
    merged["is_applicable"] = ~merged["is_not_applicable"]
    merged["is_semantic_unresolved"] = (
        merged["claim_subtype"].fillna("").astype(str).str.startswith(
            "UNRESOLVED_"
        )
        | merged["reason_code"].eq("SEMANTIC_SUBTYPE_UNRESOLVED")
    )
    merged["is_policy_violation"] = merged["policy_status"].eq(
        "VIOLATION"
    )

    return (
        merged.sort_values(
            ["generation_id", "local_claim_index", "claim_id"],
            na_position="last",
        )
        .reset_index(drop=True)
    )


def _build_generation_base_table(
    generation_index: list[JsonRecord],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    for generation in generation_index:
        record = _dict(generation.get("generation_record"))
        runtime = _dict(record.get("runtime_metrics"))
        schema = _dict(record.get("schema_metrics"))
        content = _dict(record.get("content_metrics"))
        input_snapshot = _dict(record.get("input_snapshot"))
        prompt = _dict(record.get("prompt_metrics"))
        evidence_mentions = _dict(record.get("evidence_mention_metrics"))
        policy = _dict(record.get("policy_metrics"))
        decoding = _dict(record.get("decoding_config"))
        parsed_output = _dict(record.get("parsed_output"))
        case_metadata = _dict(record.get("case_metadata"))

        rows.append(
            {
                "generation_id": generation.get("generation_id"),
                "canonical_key": generation.get("canonical_key"),
                "cohort_key": generation.get("cohort_key"),
                "matrix_role": generation.get("matrix_role"),
                "model_order": generation.get("model_order"),
                "case_order": generation.get("case_order"),
                "evidence_order": generation.get("evidence_level_order"),
                "run_id": generation.get("run_id"),
                "experiment_stage": generation.get("experiment_stage"),
                "model_id": generation.get("model_id"),
                "model_revision": generation.get("model_revision"),
                "revision_status": generation.get("revision_status"),
                "case_id": str(generation.get("case_id")),
                "source_ir_id": generation.get("source_ir_id"),
                "evidence_level": generation.get("evidence_level"),
                "repeat_id": generation.get("repeat_id"),
                "package_id": generation.get("package_id"),
                "source_evidence_id": generation.get(
                    "source_evidence_id"
                ),
                "prompt_id": generation.get("prompt_id"),
                "prompt_version": generation.get("prompt_version"),
                "output_schema_version": generation.get(
                    "output_schema_version"
                ),
                "input_package_sha256": generation.get(
                    "input_package_sha256"
                ),
                "input_package_hash_verified": generation.get(
                    "input_package_hash_verified"
                ),
                "prompt_message_sha256": generation.get(
                    "prompt_message_sha256"
                ),
                "prompt_hash_verified": generation.get(
                    "prompt_hash_verified"
                ),
                "runtime_status": generation.get("runtime_status"),
                "finish_reason": generation.get("finish_reason"),
                "truncated_response": generation.get(
                    "truncated_response"
                ),
                "raw_json_parse_success": generation.get(
                    "raw_json_parse_success"
                ),
                "schema_valid": generation.get("schema_valid"),
                "usable": generation.get("usable"),
                "usability_reason_codes_json": _json_text(
                    _list(generation.get("usability_reason_codes"))
                ),
                "source_generation_path": generation.get(
                    "source_generation_path"
                ),
                "source_generation_file_sha256": generation.get(
                    "source_generation_file_sha256"
                ),
                "source_generation_line": generation.get(
                    "source_generation_line"
                ),
                "model_provider": record.get("model_provider"),
                "remote_model_id": record.get("remote_model_id"),
                "model_family": record.get("model_family"),
                "generation_seed": record.get("generation_seed"),
                "request_order_index": record.get("request_order_index"),
                "output_constraint_mode": record.get(
                    "output_constraint_mode"
                ),
                "created_at": record.get("created_at"),
                "case_selection_stratum_source": case_metadata.get(
                    "selection_stratum"
                ),
                "case_prediction_outcome_source": case_metadata.get(
                    "prediction_outcome"
                ),
                "case_true_label_source": case_metadata.get("true_label"),
                "temperature": decoding.get("temperature"),
                "top_p": decoding.get("top_p"),
                "max_tokens": decoding.get("max_tokens"),
                "frequency_penalty": decoding.get("frequency_penalty"),
                "presence_penalty": decoding.get("presence_penalty"),
                "selected_evidence_count_source": input_snapshot.get(
                    "selected_evidence_count"
                ),
                "coverage_source": input_snapshot.get("coverage"),
                "coverage_threshold_source": input_snapshot.get(
                    "coverage_threshold"
                ),
                "coverage_status_source": input_snapshot.get(
                    "coverage_status"
                ),
                "adaptive_k_source": input_snapshot.get("adaptive_k"),
                "entropy_level_source": input_snapshot.get("entropy_level"),
                "normalized_entropy_source": input_snapshot.get(
                    "normalized_entropy"
                ),
                "concept_group_count_source": input_snapshot.get(
                    "concept_group_count"
                ),
                "mixed_concept_group_count_source": input_snapshot.get(
                    "mixed_concept_group_count"
                ),
                "has_concept_evidence_source": input_snapshot.get(
                    "has_concept_evidence"
                ),
                "prompt_char_count": prompt.get("prompt_char_count"),
                "prompt_estimated_token_count": prompt.get(
                    "prompt_estimated_token_count"
                ),
                "has_backend_skeleton_section": prompt.get(
                    "has_backend_skeleton_section"
                ),
                "latency_ms": runtime.get("latency_ms"),
                "retry_count": runtime.get("retry_count"),
                "input_token_count": runtime.get("input_token_count"),
                "output_token_count": runtime.get("output_token_count"),
                "total_token_count": runtime.get("total_token_count"),
                "provider_api_cost_usd": runtime.get(
                    "provider_api_cost_usd"
                ),
                "infrastructure_cost_usd": runtime.get(
                    "infrastructure_cost_usd"
                ),
                "total_cost_usd": runtime.get("total_cost_usd"),
                "runtime_error_type": runtime.get("error_type"),
                "runtime_error_message": runtime.get("error_message"),
                "empty_response": runtime.get("empty_response"),
                "cleanup_type": schema.get("cleanup_type"),
                "json_parse_success": schema.get("json_parse_success"),
                "missing_required_field_count": schema.get(
                    "missing_required_field_count"
                ),
                "schema_validation_error_count": schema.get(
                    "validation_error_count"
                ),
                "output_char_count": content.get("output_char_count"),
                "output_word_count": content.get("output_word_count"),
                "sentence_count": content.get("sentence_count"),
                "total_factor_count": content.get("total_factor_count"),
                "main_factor_count": content.get("main_factor_count"),
                "supporting_factor_count": content.get(
                    "supporting_factor_count"
                ),
                "has_prediction_summary": content.get(
                    "has_prediction_summary"
                ),
                "has_factors": content.get("has_factors"),
                "has_uncertainty_note": content.get(
                    "has_uncertainty_note"
                ),
                "has_distributed_evidence_note": content.get(
                    "has_distributed_evidence_note"
                ),
                "has_safe_summary": content.get("has_safe_summary"),
                "technical_term_count": content.get(
                    "technical_term_count"
                ),
                "technical_term_ratio": content.get(
                    "technical_term_ratio"
                ),
                "selected_feature_mention_count": evidence_mentions.get(
                    "selected_feature_mention_count"
                ),
                "selected_feature_mention_rate": evidence_mentions.get(
                    "selected_feature_mention_rate"
                ),
                "concept_mention_count": evidence_mentions.get(
                    "concept_mention_count"
                ),
                "concept_mention_rate": evidence_mentions.get(
                    "concept_mention_rate"
                ),
                "top1_mention_rate": evidence_mentions.get(
                    "top1_mention_rate"
                ),
                "top3_mention_rate": evidence_mentions.get(
                    "top3_mention_rate"
                ),
                "top5_mention_rate": evidence_mentions.get(
                    "top5_mention_rate"
                ),
                "invalid_declared_feature_count": evidence_mentions.get(
                    "invalid_declared_feature_count"
                ),
                "invalid_declared_concept_count": evidence_mentions.get(
                    "invalid_declared_concept_count"
                ),
                "uncertainty_required": policy.get(
                    "uncertainty_required"
                ),
                "uncertainty_compliant": policy.get(
                    "uncertainty_compliant"
                ),
                "distributed_note_required": policy.get(
                    "distributed_note_required"
                ),
                "distributed_note_compliant": policy.get(
                    "distributed_note_compliant"
                ),
                "partial_evidence_note_required": policy.get(
                    "partial_evidence_note_required"
                ),
                "partial_evidence_note_compliant": policy.get(
                    "partial_evidence_note_compliant"
                ),
                "single_cause_violation": policy.get(
                    "single_cause_violation"
                ),
                "forbidden_phrase_violation": policy.get(
                    "forbidden_phrase_violation"
                ),
                "forbidden_phrase_matches_json": _json_text(
                    _list(policy.get("forbidden_phrase_matches"))
                ),
                "prediction_summary": parsed_output.get(
                    "prediction_summary"
                ),
                "uncertainty_note": parsed_output.get("uncertainty_note"),
                "distributed_evidence_note": parsed_output.get(
                    "distributed_evidence_note"
                ),
                "safe_summary": parsed_output.get("safe_summary"),
                "factors_json": _json_text(
                    _list(parsed_output.get("factors"))
                ),
                "raw_output": record.get("raw_output"),
                "cleaned_output": record.get("cleaned_output"),
                "parsed_output_json": _json_text(
                    record.get("parsed_output")
                ),
            }
        )

    return pd.DataFrame(rows)


def _build_claim_aggregates(
    claims: pd.DataFrame,
    claim_types: tuple[str, ...] | None = None,
) -> pd.DataFrame:
    working = claims.copy()
    active_claim_types = CLAIM_TYPES if claim_types is None else claim_types

    aggregate_spec: dict[str, tuple[str, str]] = {
        "claim_count": ("claim_id", "count"),
        "supported_count": ("is_supported", "sum"),
        "unsupported_count": ("is_unsupported", "sum"),
        "contradicted_count": ("is_contradicted", "sum"),
        "not_verifiable_count": ("is_not_verifiable", "sum"),
        "not_applicable_count": ("is_not_applicable", "sum"),
        "resolved_count": ("is_resolved", "sum"),
        "applicable_count": ("is_applicable", "sum"),
        "semantic_unresolved_count": ("is_semantic_unresolved", "sum"),
        "policy_violation_count": ("is_policy_violation", "sum"),
        "claim_type_count": ("claim_type", "nunique"),
    }

    for claim_type in active_claim_types:
        column_name = f"{claim_type}_claim_count"
        working[column_name] = working["claim_type"].eq(claim_type)
        aggregate_spec[column_name] = (column_name, "sum")

    return (
        working.groupby("generation_id", as_index=False)
        .agg(**aggregate_spec)
        .reset_index(drop=True)
    )


def build_generations_table(
    generation_index: list[JsonRecord],
    cases: pd.DataFrame,
    models: pd.DataFrame,
    evidence_levels: pd.DataFrame,
    evidence_packages: pd.DataFrame,
    claims: pd.DataFrame,
    claim_types: tuple[str, ...] | None = None,
) -> pd.DataFrame:
    """Build one row for every planned generation slot.

    The generation index is the master table.  Claim aggregates are left
    joined so all ten unusable generations remain present with zero claims.
    """

    generations = _build_generation_base_table(generation_index)

    case_columns = [
        "case_id",
        "selection_stratum",
        "selection_rank",
        "true_label",
        "true_label_text",
        "predicted_class",
        "predicted_label",
        "prediction_probability",
        "decision_threshold",
        "threshold_comparison",
        "is_above_threshold",
        "prediction_correct",
        "prediction_outcome",
        "distance_from_threshold",
    ]
    generations = generations.merge(
        cases[case_columns],
        on="case_id",
        how="left",
        validate="many_to_one",
        indicator="case_join_status",
    )

    model_columns = ["model_id", "model_label"]
    generations = generations.merge(
        models[model_columns],
        on="model_id",
        how="left",
        validate="many_to_one",
        indicator="model_join_status",
    )

    evidence_level_columns = [
        "evidence_level",
        "evidence_label",
        "intended_role",
    ]
    generations = generations.merge(
        evidence_levels[evidence_level_columns],
        on="evidence_level",
        how="left",
        validate="many_to_one",
        indicator="evidence_level_join_status",
    )

    package_columns = [
        "package_id",
        "case_id",
        "evidence_level",
        "selected_evidence_count",
        "concept_evidence_count",
        "safe_phrase_count",
        "allowed_feature_count",
        "allowed_concept_count",
        "exposed_feature_count",
        "exposed_concept_count",
        "out_of_contract_feature_count",
        "out_of_contract_concept_count",
        "has_semantic_guidance",
        "has_concept_evidence",
        "has_structural_skeleton",
        "backend_factor_slot_count",
        "coverage",
        "coverage_threshold",
        "coverage_status",
        "adaptive_k",
        "normalized_entropy",
        "entropy_level",
        "concept_group_count",
        "mixed_concept_group_count",
    ]
    package_lookup = evidence_packages[package_columns].rename(
        columns={
            "case_id": "package_case_id",
            "evidence_level": "package_evidence_level",
        }
    )
    generations = generations.merge(
        package_lookup,
        on="package_id",
        how="left",
        validate="many_to_one",
        indicator="package_join_status",
    )

    active_claim_types = CLAIM_TYPES if claim_types is None else claim_types
    claim_aggregates = _build_claim_aggregates(
        claims,
        claim_types=active_claim_types,
    )
    generations = generations.merge(
        claim_aggregates,
        on="generation_id",
        how="left",
        validate="one_to_one",
        indicator="claim_aggregate_join_status",
    )

    count_columns = [
        "claim_count",
        "supported_count",
        "unsupported_count",
        "contradicted_count",
        "not_verifiable_count",
        "not_applicable_count",
        "resolved_count",
        "applicable_count",
        "semantic_unresolved_count",
        "policy_violation_count",
        "claim_type_count",
        *(f"{claim_type}_claim_count" for claim_type in active_claim_types),
    ]
    generations[count_columns] = (
        generations[count_columns].fillna(0).astype(int)
    )

    return (
        generations.sort_values(
            ["model_order", "case_order", "evidence_order", "generation_id"]
        )
        .reset_index(drop=True)
    )


def build_data_mart(
    input_data: InputData,
    claim_types: tuple[str, ...] | None = None,
) -> dict[str, pd.DataFrame]:
    """Build all analytical tables in dependency order.

    ``claim_types=None`` preserves the historical Home Credit aggregate schema.
    Dataset-specific callers may explicitly opt into additional known types.
    """

    cases = build_cases_table(input_data["evidence_packages"])
    models = build_models_table(input_data["generation_index"])
    evidence_levels = build_evidence_levels_table()
    evidence_packages = build_evidence_packages_table(
        input_data["evidence_packages"]
    )
    evidence_items = build_evidence_items_table(
        input_data["evidence_packages"]
    )
    claims = build_claims_table(
        input_data["final_claims"],
        input_data["validation_results"],
    )
    generations = build_generations_table(
        input_data["generation_index"],
        cases,
        models,
        evidence_levels,
        evidence_packages,
        claims,
        claim_types=claim_types,
    )

    return {
        "cases": cases,
        "models": models,
        "evidence_levels": evidence_levels,
        "evidence_packages": evidence_packages,
        "evidence_items": evidence_items,
        "generations": generations,
        "claims": claims,
    }


def write_data_mart(
    tables: dict[str, pd.DataFrame],
    output_dir: Path,
) -> None:
    """Write deterministic UTF-8 CSV outputs for analysis and Tableau."""

    output_dir.mkdir(parents=True, exist_ok=True)

    for table_name, file_name in TABLE_FILE_NAMES.items():
        dataframe = tables[table_name].drop(
            columns=OUTPUT_DROP_COLUMNS.get(table_name, []),
            errors="ignore",
        )
        dataframe.to_csv(
            output_dir / file_name,
            index=False,
            encoding="utf-8",
            lineterminator="\n",
            float_format="%.12g",
        )
