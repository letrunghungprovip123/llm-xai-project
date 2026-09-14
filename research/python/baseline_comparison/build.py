"""Build the deterministic Template Baseline analytical layer."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from .config import (
    BASELINE_COMPARISON_VERSION,
    OUTPUT_DIR,
    PROJECT_ROOT,
    OUTPUT_PATHS,
    STRUCTURED_ADAPTER_VERSION,
    VALIDATION_MODE,
)
from .inference import build_baseline_tests


_LABEL_PATTERN = re.compile(r"\b(high_default_risk|low_default_risk)\b")
_PERCENT_PATTERN = re.compile(r"([0-9]+(?:[.,][0-9]+)?)\s*%")


def safe_divide(numerator: float | int, denominator: float | int) -> float:
    if denominator == 0 or pd.isna(denominator):
        return float("nan")
    return float(numerator) / float(denominator)


def normalize_direction(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    normalized = str(value).strip().lower()
    mapping = {
        "increase_risk": "increase_risk",
        "increases_risk": "increase_risk",
        "decrease_risk": "decrease_risk",
        "decreases_risk": "decrease_risk",
        "mixed": "mixed",
    }
    return mapping.get(normalized, normalized or None)


def normalize_case_id(value: object) -> object:
    """Normalize numeric case identifiers across JSONL and CSV inputs."""

    text = str(value).strip()
    return int(text) if text.isdigit() else text


def stable_claim_id(*parts: object) -> str:
    text = "|".join("" if part is None else str(part) for part in parts)
    return "template_claim_" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def json_list(value: object) -> list[str]:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        parsed = json.loads(stripped)
        if not isinstance(parsed, list):
            raise ValueError("Expected a JSON array string.")
        return [str(item) for item in parsed]
    raise TypeError(f"Unsupported list value: {type(value).__name__}")


def direction_status(observed: str | None, expected: str | None) -> tuple[str, str]:
    if expected is None:
        return "NOT_VERIFIABLE", "EVIDENCE_DIRECTION_UNAVAILABLE"
    if observed == expected:
        return "SUPPORTED", "DIRECTION_MATCH"
    if observed in {"increase_risk", "decrease_risk"} and expected in {
        "increase_risk",
        "decrease_risk",
    }:
        return "CONTRADICTED", "DIRECTION_MISMATCH"
    return "NOT_VERIFIABLE", "DIRECTION_NOT_COMPARABLE"


def status_flags(status: str) -> dict[str, bool]:
    return {
        "is_supported": status == "SUPPORTED",
        "is_not_verifiable": status == "NOT_VERIFIABLE",
        "is_unsupported": status == "UNSUPPORTED",
        "is_contradicted": status == "CONTRADICTED",
        "is_not_applicable": status == "NOT_APPLICABLE",
        "is_resolved": status in {"SUPPORTED", "UNSUPPORTED", "CONTRADICTED"},
        "is_applicable": status != "NOT_APPLICABLE",
    }


def claim_row(
    *,
    generation_id: str,
    case_id: object,
    evidence_level: str,
    package_id: str,
    claim_index: int,
    source_section: str,
    claim_type: str,
    subject_type: str,
    source_text: str,
    status: str,
    reason_code: str,
    feature_id: str | None = None,
    concept_id: str | None = None,
    observed_direction: str | None = None,
    expected_direction: str | None = None,
    observed_value: float | None = None,
    expected_value: float | None = None,
    policy_status: str = "NOT_APPLICABLE",
) -> dict[str, object]:
    return {
        "baseline_comparison_version": BASELINE_COMPARISON_VERSION,
        "structured_adapter_version": STRUCTURED_ADAPTER_VERSION,
        "validation_mode": VALIDATION_MODE,
        "claim_id": stable_claim_id(
            generation_id,
            claim_index,
            claim_type,
            feature_id,
            concept_id,
        ),
        "generation_id": generation_id,
        "case_id": case_id,
        "model_id": "template_baseline",
        "evidence_level": evidence_level,
        "package_id": package_id,
        "claim_index": claim_index,
        "source_section": source_section,
        "claim_type": claim_type,
        "subject_type": subject_type,
        "feature_id": feature_id,
        "concept_id": concept_id,
        "source_text": source_text,
        "observed_direction": observed_direction,
        "expected_direction": expected_direction,
        "observed_value": observed_value,
        "expected_value": expected_value,
        "validation_status": status,
        "reason_code": reason_code,
        "policy_status": policy_status,
        **status_flags(status),
    }


def evidence_indexes(
    evidence_items: pd.DataFrame,
) -> tuple[dict[tuple[str, str], dict[str, object]], dict[tuple[str, str], dict[str, object]]]:
    feature_index: dict[tuple[str, str], dict[str, object]] = {}
    concept_rows: dict[tuple[str, str], list[pd.Series]] = {}
    for _, row in evidence_items.iterrows():
        package_id = str(row["package_id"])
        feature_id = row.get("feature_id")
        concept_id = row.get("concept_id")
        if pd.notna(feature_id):
            feature_index[(package_id, str(feature_id))] = {
                "direction": normalize_direction(row.get("direction")),
                "is_allowed": bool(row.get("is_allowed", True)),
            }
        if pd.notna(concept_id):
            concept_rows.setdefault((package_id, str(concept_id)), []).append(row)

    concept_index: dict[tuple[str, str], dict[str, object]] = {}
    for key, rows in concept_rows.items():
        directions = {
            normalize_direction(row.get("direction"))
            for row in rows
            if normalize_direction(row.get("direction")) is not None
        }
        direction = next(iter(directions)) if len(directions) == 1 else "mixed"
        concept_index[key] = {
            "direction": direction,
            "is_allowed": any(bool(row.get("is_allowed", True)) for row in rows),
        }
    return feature_index, concept_index


def build_baseline_claims(input_data: dict[str, Any]) -> pd.DataFrame:
    cases = input_data["cases"].set_index("case_id")
    feature_index, concept_index = evidence_indexes(input_data["evidence_items"])
    rows: list[dict[str, object]] = []

    for record in input_data["template_records"]:
        generation = record["generation_record"]
        parsed = generation["parsed_output"]
        policy = generation["policy_metrics"]
        generation_id = str(record["generation_id"])
        case_id = normalize_case_id(record["case_id"])
        evidence_level = str(record["evidence_level"])
        package_id = str(record["package_id"])
        case = cases.loc[case_id]
        claim_index = 0

        prediction_text = str(parsed.get("prediction_summary", ""))
        label_match = _LABEL_PATTERN.search(prediction_text)
        observed_label = label_match.group(1) if label_match else None
        expected_label = str(case["predicted_label"])
        claim_index += 1
        label_status = "SUPPORTED" if observed_label == expected_label else "CONTRADICTED"
        rows.append(
            claim_row(
                generation_id=generation_id,
                case_id=case_id,
                evidence_level=evidence_level,
                package_id=package_id,
                claim_index=claim_index,
                source_section="prediction_summary",
                claim_type="prediction",
                subject_type="prediction",
                source_text=prediction_text,
                status=label_status,
                reason_code=("EXACT_MATCH" if label_status == "SUPPORTED" else "LABEL_MISMATCH"),
            )
        )

        percent_match = _PERCENT_PATTERN.search(prediction_text)
        observed_probability = (
            float(percent_match.group(1).replace(",", ".")) / 100.0
            if percent_match
            else None
        )
        expected_probability = float(case["prediction_probability"])
        claim_index += 1
        score_supported = (
            observed_probability is not None
            and abs(observed_probability - expected_probability) <= 0.00005
        )
        rows.append(
            claim_row(
                generation_id=generation_id,
                case_id=case_id,
                evidence_level=evidence_level,
                package_id=package_id,
                claim_index=claim_index,
                source_section="prediction_summary",
                claim_type="numeric",
                subject_type="prediction",
                source_text=(percent_match.group(0) if percent_match else prediction_text),
                status=("SUPPORTED" if score_supported else "CONTRADICTED"),
                reason_code=("TOLERANCE_MATCH" if score_supported else "NUMERIC_MISMATCH"),
                observed_value=observed_probability,
                expected_value=expected_probability,
            )
        )

        for factor in parsed.get("factors", []) or []:
            factor_text = str(factor.get("explanation", ""))
            observed_direction = normalize_direction(factor.get("direction"))
            for feature_id in factor.get("declared_feature_ids", []) or []:
                feature_id = str(feature_id)
                evidence = feature_index.get((package_id, feature_id))
                claim_index += 1
                rows.append(
                    claim_row(
                        generation_id=generation_id,
                        case_id=case_id,
                        evidence_level=evidence_level,
                        package_id=package_id,
                        claim_index=claim_index,
                        source_section="factors",
                        claim_type="feature_presence",
                        subject_type="feature",
                        feature_id=feature_id,
                        source_text=factor_text,
                        status=("SUPPORTED" if evidence else "UNSUPPORTED"),
                        reason_code=("EXPOSED_MATCH" if evidence else "FEATURE_NOT_EXPOSED"),
                    )
                )
                expected_direction = evidence["direction"] if evidence else None
                status, reason = direction_status(observed_direction, expected_direction)
                if evidence is None:
                    status, reason = "NOT_VERIFIABLE", "FEATURE_NOT_EXPOSED"
                claim_index += 1
                rows.append(
                    claim_row(
                        generation_id=generation_id,
                        case_id=case_id,
                        evidence_level=evidence_level,
                        package_id=package_id,
                        claim_index=claim_index,
                        source_section="factors",
                        claim_type="feature_direction",
                        subject_type="feature",
                        feature_id=feature_id,
                        source_text=factor_text,
                        status=status,
                        reason_code=reason,
                        observed_direction=observed_direction,
                        expected_direction=expected_direction,
                    )
                )

            for concept_id in factor.get("declared_concept_ids", []) or []:
                concept_id = str(concept_id)
                evidence = concept_index.get((package_id, concept_id))
                claim_index += 1
                rows.append(
                    claim_row(
                        generation_id=generation_id,
                        case_id=case_id,
                        evidence_level=evidence_level,
                        package_id=package_id,
                        claim_index=claim_index,
                        source_section="factors",
                        claim_type="concept_presence",
                        subject_type="concept",
                        concept_id=concept_id,
                        source_text=factor_text,
                        status=("SUPPORTED" if evidence else "UNSUPPORTED"),
                        reason_code=("EXPOSED_MATCH" if evidence else "CONCEPT_NOT_EXPOSED"),
                    )
                )
                expected_direction = evidence["direction"] if evidence else None
                status, reason = direction_status(observed_direction, expected_direction)
                if evidence is None:
                    status, reason = "NOT_VERIFIABLE", "CONCEPT_NOT_EXPOSED"
                claim_index += 1
                rows.append(
                    claim_row(
                        generation_id=generation_id,
                        case_id=case_id,
                        evidence_level=evidence_level,
                        package_id=package_id,
                        claim_index=claim_index,
                        source_section="factors",
                        claim_type="concept_direction",
                        subject_type="concept",
                        concept_id=concept_id,
                        source_text=factor_text,
                        status=status,
                        reason_code=reason,
                        observed_direction=observed_direction,
                        expected_direction=expected_direction,
                    )
                )

        claim_index += 1
        uncertainty_required = bool(policy.get("uncertainty_required"))
        uncertainty_compliant = bool(policy.get("uncertainty_compliant"))
        rows.append(
            claim_row(
                generation_id=generation_id,
                case_id=case_id,
                evidence_level=evidence_level,
                package_id=package_id,
                claim_index=claim_index,
                source_section="uncertainty_note",
                claim_type="uncertainty",
                subject_type="policy",
                source_text=str(parsed.get("uncertainty_note", "")),
                status="NOT_APPLICABLE",
                reason_code=(
                    "POLICY_COMPLIANT"
                    if (not uncertainty_required or uncertainty_compliant)
                    else "POLICY_VIOLATION"
                ),
                policy_status=(
                    "COMPLIANT"
                    if (not uncertainty_required or uncertainty_compliant)
                    else "VIOLATION"
                ),
            )
        )

        claim_index += 1
        distributed_required = bool(policy.get("distributed_note_required"))
        distributed_value = policy.get("distributed_note_compliant")
        distributed_compliant = (
            True if not distributed_required else bool(distributed_value)
        )
        rows.append(
            claim_row(
                generation_id=generation_id,
                case_id=case_id,
                evidence_level=evidence_level,
                package_id=package_id,
                claim_index=claim_index,
                source_section="distributed_evidence_note",
                claim_type="distributed_evidence",
                subject_type="policy",
                source_text=str(parsed.get("distributed_evidence_note", "")),
                status="NOT_APPLICABLE",
                reason_code=("POLICY_COMPLIANT" if distributed_compliant else "POLICY_VIOLATION"),
                policy_status=("COMPLIANT" if distributed_compliant else "VIOLATION"),
            )
        )

    output = pd.DataFrame(rows)
    return output.sort_values(
        ["case_id", "evidence_level", "claim_index"],
        kind="stable",
    ).reset_index(drop=True)


def flatten_template_generation(record: dict[str, Any]) -> dict[str, object]:
    generation = record["generation_record"]
    content = generation["content_metrics"]
    policy = generation["policy_metrics"]
    mentions = generation["evidence_mention_metrics"]
    runtime = generation["runtime_metrics"]
    parsed = generation["parsed_output"]
    return {
        "generation_id": record["generation_id"],
        "case_id": normalize_case_id(record["case_id"]),
        "model_id": "template_baseline",
        "evidence_level": record["evidence_level"],
        "package_id": record["package_id"],
        "usable": bool(record["usable"]),
        "runtime_status": record["runtime_status"],
        "schema_valid": bool(record["schema_valid"]),
        "truncated_response": bool(record["truncated_response"]),
        "latency_ms": runtime.get("latency_ms"),
        "retry_count": runtime.get("retry_count"),
        "output_word_count": content.get("output_word_count"),
        "output_char_count": content.get("output_char_count"),
        "sentence_count": content.get("sentence_count"),
        "total_factor_count": content.get("total_factor_count"),
        "main_factor_count": content.get("main_factor_count"),
        "supporting_factor_count": content.get("supporting_factor_count"),
        "technical_term_count": content.get("technical_term_count"),
        "technical_term_ratio": content.get("technical_term_ratio"),
        "selected_feature_mention_count": mentions.get("selected_feature_mention_count"),
        "selected_feature_mention_rate": mentions.get("selected_feature_mention_rate"),
        "concept_mention_count": mentions.get("concept_mention_count"),
        "concept_mention_rate": mentions.get("concept_mention_rate"),
        "top1_mention_rate": mentions.get("top1_mention_rate"),
        "top3_mention_rate": mentions.get("top3_mention_rate"),
        "top5_mention_rate": mentions.get("top5_mention_rate"),
        "invalid_declared_feature_count": mentions.get("invalid_declared_feature_count"),
        "invalid_declared_concept_count": mentions.get("invalid_declared_concept_count"),
        "uncertainty_required": policy.get("uncertainty_required"),
        "uncertainty_compliant": policy.get("uncertainty_compliant"),
        "distributed_note_required": policy.get("distributed_note_required"),
        "distributed_note_compliant": policy.get("distributed_note_compliant"),
        "partial_evidence_note_required": policy.get("partial_evidence_note_required"),
        "partial_evidence_note_compliant": policy.get("partial_evidence_note_compliant"),
        "single_cause_violation": policy.get("single_cause_violation"),
        "forbidden_phrase_violation": policy.get("forbidden_phrase_violation"),
        "prediction_summary": parsed.get("prediction_summary"),
        "uncertainty_note": parsed.get("uncertainty_note"),
        "distributed_evidence_note": parsed.get("distributed_evidence_note"),
        "safe_summary": parsed.get("safe_summary"),
        "factors_json": json.dumps(
            parsed.get("factors", []),
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }


def build_baseline_generation_metrics(
    input_data: dict[str, Any],
    claims: pd.DataFrame,
) -> pd.DataFrame:
    generation_rows = [
        flatten_template_generation(record)
        for record in input_data["template_records"]
    ]
    generations = pd.DataFrame(generation_rows)
    status_counts = (
        claims.pivot_table(
            index="generation_id",
            columns="validation_status",
            values="claim_id",
            aggfunc="count",
            fill_value=0,
        )
        .reset_index()
    )
    for status in [
        "SUPPORTED",
        "NOT_VERIFIABLE",
        "UNSUPPORTED",
        "CONTRADICTED",
        "NOT_APPLICABLE",
    ]:
        if status not in status_counts.columns:
            status_counts[status] = 0
    status_counts = status_counts.rename(
        columns={
            "SUPPORTED": "supported_count",
            "NOT_VERIFIABLE": "not_verifiable_count",
            "UNSUPPORTED": "unsupported_count",
            "CONTRADICTED": "contradicted_count",
            "NOT_APPLICABLE": "not_applicable_count",
        }
    )
    claim_counts = claims.groupby("generation_id", as_index=False).agg(
        claim_count=("claim_id", "count"),
        policy_violation_count=("policy_status", lambda values: int((values == "VIOLATION").sum())),
    )
    metrics = generations.merge(
        status_counts,
        on="generation_id",
        how="left",
        validate="one_to_one",
    ).merge(
        claim_counts,
        on="generation_id",
        how="left",
        validate="one_to_one",
    )
    metrics["resolved_count"] = (
        metrics["supported_count"]
        + metrics["unsupported_count"]
        + metrics["contradicted_count"]
    )
    metrics["applicable_count"] = (
        metrics["resolved_count"] + metrics["not_verifiable_count"]
    )
    metrics["quality_metric_eligible"] = metrics["applicable_count"] > 0
    metrics["resolved_faithfulness"] = [
        safe_divide(supported, resolved)
        for supported, resolved in zip(metrics["supported_count"], metrics["resolved_count"])
    ]
    metrics["verifiability"] = [
        safe_divide(resolved, applicable)
        for resolved, applicable in zip(metrics["resolved_count"], metrics["applicable_count"])
    ]
    metrics["conservative_faithfulness"] = [
        safe_divide(supported, applicable)
        for supported, applicable in zip(metrics["supported_count"], metrics["applicable_count"])
    ]
    metrics["end_to_end_faithfulness_yield"] = np.where(
        metrics["usable"],
        metrics["conservative_faithfulness"],
        0.0,
    )
    metrics["not_verifiable_rate"] = [
        safe_divide(value, applicable)
        for value, applicable in zip(metrics["not_verifiable_count"], metrics["applicable_count"])
    ]
    metrics["unsupported_rate"] = [
        safe_divide(value, applicable)
        for value, applicable in zip(metrics["unsupported_count"], metrics["applicable_count"])
    ]
    metrics["contradiction_rate"] = [
        safe_divide(value, applicable)
        for value, applicable in zip(metrics["contradicted_count"], metrics["applicable_count"])
    ]
    metrics["supported_claims_per_100_words"] = [
        100.0 * safe_divide(supported, words)
        for supported, words in zip(metrics["supported_count"], metrics["output_word_count"])
    ]
    metrics["latency_seconds"] = metrics["latency_ms"].astype(float) / 1000.0
    metrics["latency_measurement_floor_limited"] = metrics["latency_ms"].fillna(0).eq(0)
    metrics.insert(0, "baseline_comparison_version", BASELINE_COMPARISON_VERSION)
    metrics.insert(1, "structured_adapter_version", STRUCTURED_ADAPTER_VERSION)
    return metrics.sort_values(
        ["case_id", "evidence_level"],
        kind="stable",
    ).reset_index(drop=True)


def quantile_10(values: pd.Series) -> float:
    return float(values.quantile(0.10, interpolation="linear"))


def build_baseline_option_performance(
    metrics: pd.DataFrame,
    evidence_levels: pd.DataFrame,
) -> pd.DataFrame:
    output = metrics.groupby("evidence_level", as_index=False).agg(
        planned_generation_count=("generation_id", "count"),
        usable_generation_count=("usable", "sum"),
        usability_rate=("usable", "mean"),
        mean_end_to_end_yield=("end_to_end_faithfulness_yield", "mean"),
        median_end_to_end_yield=("end_to_end_faithfulness_yield", "median"),
        p10_end_to_end_yield=("end_to_end_faithfulness_yield", quantile_10),
        mean_conservative_faithfulness=("conservative_faithfulness", "mean"),
        mean_verifiability=("verifiability", "mean"),
        mean_resolved_faithfulness=("resolved_faithfulness", "mean"),
        mean_supported_claim_count=("supported_count", "mean"),
        mean_supported_claims_per_100_words=(
            "supported_claims_per_100_words", "mean"
        ),
        mean_output_word_count=("output_word_count", "mean"),
        mean_latency_seconds=("latency_seconds", "mean"),
        policy_violation_count=("policy_violation_count", "sum"),
    )
    level_meta = evidence_levels[
        ["evidence_level", "evidence_order", "evidence_label", "intended_role"]
    ].copy()
    level_meta.loc[
        level_meta["evidence_level"] == "S0", "evidence_label"
    ] = "Prediction-only control"
    output = output.merge(
        level_meta,
        on="evidence_level",
        how="left",
        validate="one_to_one",
    )
    output.insert(0, "baseline_comparison_version", BASELINE_COMPARISON_VERSION)
    output.insert(1, "generator_id", "template_baseline")
    output.insert(2, "generator_label", "Deterministic Template Baseline")
    output["eligible_for_llm_decision_ranking"] = False
    return output.sort_values("evidence_order", kind="stable").reset_index(drop=True)


def build_pairs(
    input_data: dict[str, Any],
    baseline_metrics: pd.DataFrame,
) -> pd.DataFrame:
    llm_metrics = input_data["llm_generation_metrics"].copy()
    llm_structure = input_data["llm_generations"][
        ["generation_id", "output_word_count"]
    ].copy()
    llm_metrics = llm_metrics.merge(
        llm_structure,
        on="generation_id",
        how="left",
        validate="one_to_one",
    )
    models = input_data["models"][["model_id", "model_label"]]
    evidence = input_data["evidence_levels"][
        ["evidence_level", "evidence_label"]
    ].copy()
    evidence.loc[
        evidence["evidence_level"] == "S0", "evidence_label"
    ] = "Prediction-only control"
    llm_metrics = llm_metrics.merge(
        models,
        on="model_id",
        how="left",
        validate="many_to_one",
    ).merge(
        evidence,
        on="evidence_level",
        how="left",
        validate="many_to_one",
    )
    llm_metrics["supported_claims_per_100_words"] = [
        100.0 * safe_divide(supported, words)
        for supported, words in zip(
            llm_metrics["supported_count"],
            llm_metrics["output_word_count"],
        )
    ]
    template = baseline_metrics[
        [
            "case_id",
            "evidence_level",
            "generation_id",
            "end_to_end_faithfulness_yield",
            "conservative_faithfulness",
            "verifiability",
            "resolved_faithfulness",
            "supported_count",
            "output_word_count",
            "supported_claims_per_100_words",
            "latency_seconds",
        ]
    ].rename(
        columns={
            "generation_id": "template_generation_id",
            "end_to_end_faithfulness_yield": "template_end_to_end_faithfulness_yield",
            "conservative_faithfulness": "template_conservative_faithfulness",
            "verifiability": "template_verifiability",
            "resolved_faithfulness": "template_resolved_faithfulness",
            "supported_count": "template_supported_count",
            "output_word_count": "template_output_word_count",
            "supported_claims_per_100_words": "template_supported_claims_per_100_words",
            "latency_seconds": "template_latency_seconds",
        }
    )
    llm = llm_metrics[
        [
            "generation_id",
            "case_id",
            "model_id",
            "model_label",
            "model_order",
            "evidence_level",
            "evidence_label",
            "evidence_order",
            "selection_stratum",
            "end_to_end_faithfulness_yield",
            "conservative_faithfulness",
            "verifiability",
            "resolved_faithfulness",
            "supported_count",
            "output_word_count",
            "supported_claims_per_100_words",
            "latency_seconds",
        ]
    ].rename(
        columns={
            "generation_id": "llm_generation_id",
            "end_to_end_faithfulness_yield": "llm_end_to_end_faithfulness_yield",
            "conservative_faithfulness": "llm_conservative_faithfulness",
            "verifiability": "llm_verifiability",
            "resolved_faithfulness": "llm_resolved_faithfulness",
            "supported_count": "llm_supported_count",
            "output_word_count": "llm_output_word_count",
            "supported_claims_per_100_words": "llm_supported_claims_per_100_words",
            "latency_seconds": "llm_latency_seconds",
        }
    )
    pairs = llm.merge(
        template,
        on=["case_id", "evidence_level"],
        how="inner",
        validate="many_to_one",
    )
    delta_pairs = [
        "end_to_end_faithfulness_yield",
        "conservative_faithfulness",
        "verifiability",
        "resolved_faithfulness",
        "supported_count",
        "output_word_count",
        "supported_claims_per_100_words",
        "latency_seconds",
    ]
    for metric in delta_pairs:
        pairs[f"delta_{metric}_llm_minus_template"] = (
            pairs[f"llm_{metric}"] - pairs[f"template_{metric}"]
        )
    pairs.insert(0, "baseline_comparison_version", BASELINE_COMPARISON_VERSION)
    pairs["pairing_unit"] = "case_id_x_evidence_level"
    pairs["template_is_fourth_llm"] = False
    pairs["eligible_for_decision_ranking"] = False
    return pairs.sort_values(
        ["model_order", "evidence_order", "case_id"],
        kind="stable",
    ).reset_index(drop=True)


def summarize_group(group: pd.DataFrame) -> dict[str, object]:
    return {
        "pair_count": len(group),
        "llm_mean_end_to_end_yield": group[
            "llm_end_to_end_faithfulness_yield"
        ].mean(),
        "template_mean_end_to_end_yield": group[
            "template_end_to_end_faithfulness_yield"
        ].mean(),
        "mean_delta_end_to_end_yield": group[
            "delta_end_to_end_faithfulness_yield_llm_minus_template"
        ].mean(),
        "llm_mean_conservative_faithfulness": group[
            "llm_conservative_faithfulness"
        ].mean(),
        "template_mean_conservative_faithfulness": group[
            "template_conservative_faithfulness"
        ].mean(),
        "mean_delta_conservative_faithfulness": group[
            "delta_conservative_faithfulness_llm_minus_template"
        ].mean(),
        "llm_mean_verifiability": group["llm_verifiability"].mean(),
        "template_mean_verifiability": group[
            "template_verifiability"
        ].mean(),
        "mean_delta_verifiability": group[
            "delta_verifiability_llm_minus_template"
        ].mean(),
        "llm_mean_supported_count": group["llm_supported_count"].mean(),
        "template_mean_supported_count": group[
            "template_supported_count"
        ].mean(),
        "mean_delta_supported_count": group[
            "delta_supported_count_llm_minus_template"
        ].mean(),
        "llm_mean_supported_claims_per_100_words": group[
            "llm_supported_claims_per_100_words"
        ].mean(),
        "template_mean_supported_claims_per_100_words": group[
            "template_supported_claims_per_100_words"
        ].mean(),
        "mean_delta_supported_claims_per_100_words": group[
            "delta_supported_claims_per_100_words_llm_minus_template"
        ].mean(),
        "llm_mean_output_word_count": group["llm_output_word_count"].mean(),
        "template_mean_output_word_count": group[
            "template_output_word_count"
        ].mean(),
        "mean_delta_output_word_count": group[
            "delta_output_word_count_llm_minus_template"
        ].mean(),
    }


def build_summary(pairs: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for model_id, group in pairs.groupby("model_id", sort=False):
        rows.append(
            {
                "group_type": "model_overall",
                "model_id": model_id,
                "evidence_level": None,
                "evidence_scope": "S0-S5",
                **summarize_group(group),
            }
        )
    for (model_id, evidence_level), group in pairs.groupby(
        ["model_id", "evidence_level"],
        sort=False,
    ):
        rows.append(
            {
                "group_type": "model_evidence",
                "model_id": model_id,
                "evidence_level": evidence_level,
                "evidence_scope": evidence_level,
                **summarize_group(group),
            }
        )
    pooled = pairs.loc[pairs["evidence_level"].isin(["S1", "S2", "S3", "S4"])].copy()
    for model_id, group in pooled.groupby("model_id", sort=False):
        case_level = group.groupby("case_id", as_index=False).mean(numeric_only=True)
        rows.append(
            {
                "group_type": "model_s1_s4_case_aggregate",
                "model_id": model_id,
                "evidence_level": None,
                "evidence_scope": "S1-S4_CASE_MEAN",
                **summarize_group(case_level),
            }
        )
    output = pd.DataFrame(rows)
    output.insert(0, "baseline_comparison_version", BASELINE_COMPARISON_VERSION)
    return output


def build_metric_dictionary() -> pd.DataFrame:
    rows = [
        (
            "end_to_end_faithfulness_yield",
            "Operational faithfulness across all planned generations; "
            "unusable receives zero",
            "generation",
            "all planned generations",
            "higher",
        ),
        (
            "conservative_faithfulness",
            "Supported claims divided by all applicable claims",
            "generation",
            "applicable claims",
            "higher",
        ),
        (
            "verifiability",
            "Resolved claims divided by all applicable claims",
            "generation",
            "applicable claims",
            "higher",
        ),
        (
            "resolved_faithfulness",
            "Supported claims divided by resolved claims",
            "generation",
            "resolved claims",
            "higher",
        ),
        (
            "supported_claim_count",
            "Number of deterministically supported atomic claims",
            "generation",
            "generation",
            "higher_context_dependent",
        ),
        (
            "supported_claims_per_100_words",
            "Supported atomic claims per 100 output words",
            "generation",
            "output words",
            "higher_context_dependent",
        ),
        (
            "output_word_count",
            "Narrative output word count",
            "generation",
            "generation",
            "context_dependent",
        ),
        (
            "latency_seconds",
            "Observed generation latency; template zero values are "
            "measurement-floor limited",
            "generation",
            "generation",
            "lower",
        ),
    ]
    return pd.DataFrame(
        [
            {
                "baseline_comparison_version": BASELINE_COMPARISON_VERSION,
                "metric_id": metric_id,
                "definition": definition,
                "analysis_unit": unit,
                "denominator": denominator,
                "direction": direction,
                "template_claim_adapter": STRUCTURED_ADAPTER_VERSION,
                "human_naturalness_metric": False,
            }
            for metric_id, definition, unit, denominator, direction in rows
        ]
    )


def build_outputs(input_data: dict[str, Any]) -> dict[str, pd.DataFrame]:
    claims = build_baseline_claims(input_data)
    metrics = build_baseline_generation_metrics(input_data, claims)
    pairs = build_pairs(input_data, metrics)
    return {
        "baseline_claims": claims,
        "baseline_generation_metrics": metrics,
        "baseline_option_performance": build_baseline_option_performance(
            metrics,
            input_data["evidence_levels"],
        ),
        "llm_vs_template_case_pairs": pairs,
        "llm_vs_template_summary": build_summary(pairs),
        "llm_vs_template_tests": build_baseline_tests(pairs),
        "baseline_metric_dictionary": build_metric_dictionary(),
    }


def write_outputs(outputs: dict[str, pd.DataFrame]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, path in OUTPUT_PATHS.items():
        outputs[name].to_csv(path, index=False)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(
    input_paths: Iterable[Path],
    output_paths: Iterable[Path],
    parent_release: dict[str, Any],
    claim_release: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "baseline_comparison_manifest_v1",
        "baseline_comparison_version": BASELINE_COMPARISON_VERSION,
        "parent_exit_gate": parent_release.get("exit_gate"),
        "primary_claim_measurement_release": (
            claim_release.get("release_id")
            or claim_release.get("schema_version")
        ),
        "template_generator_id": "template_baseline",
        "template_is_fourth_llm": False,
        "eligible_for_decision_ranking": False,
        "structured_adapter_version": STRUCTURED_ADAPTER_VERSION,
        "validation_mode": VALIDATION_MODE,
        "claim_extraction_channel_identical_to_llm": False,
        "human_naturalness_evaluated": False,
        "template_latency_measurement_floor_limited": True,
        "input_artifacts": [
            {
                "path": str(path.resolve().relative_to(PROJECT_ROOT.resolve())),
                "sha256": sha256_file(path),
            }
            for path in input_paths
        ],
        "output_artifacts": [
            {
                "path": str(path.resolve().relative_to(PROJECT_ROOT.resolve())),
                "sha256": sha256_file(path),
            }
            for path in output_paths
        ],
    }
