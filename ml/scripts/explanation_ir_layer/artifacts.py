"""
Artifact saving utilities for Batch H - Concept-aware Explanation IR Layer.

This module saves:
- explanation_ir.jsonl
- explanation_ir_summary.csv
- explanation_ir_quality_report.json
- explanation_ir_manifest_<mode>.json

Important:
- This module does not build IR records.
- This module only persists outputs and creates lineage/quality metadata.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from ml.scripts.explanation_ir_layer.config import (
    BATCH_NAME,
    BATCH_SHORT_NAME,
    SOURCE_BATCH_NAME,
    IR_SCHEMA_VERSION,
    BUILDER_VERSION,
    STATUS_FAILED,
    STATUS_PASSED,
    STATUS_PASSED_WITH_WARNINGS,
    DEFAULT_MAX_CONCEPT_SUMMARIES,
    DEFAULT_MAX_FEATURE_FACTORS_PER_DIRECTION,
    STRONG_ABS_SHAP_THRESHOLD,
    MODERATE_ABS_SHAP_THRESHOLD,
    NEUTRAL_SHAP_EPSILON,
    ensure_output_dirs_for_mode,
    get_ir_jsonl_output_path,
    get_ir_manifest_output_path,
    get_ir_quality_report_output_path,
    get_ir_summary_output_path,
    get_output_paths_for_mode,
)
from ml.scripts.explanation_ir_layer.ir_builder import ExplanationIRBuildResult
from ml.scripts.explanation_ir_layer.ir_schema import utc_now_iso


# =============================================================================
# Dataclasses
# =============================================================================

@dataclass(frozen=True)
class ExplanationIRArtifactPaths:
    """
    Paths created by Batch H.
    """

    explanation_ir_jsonl: Path
    explanation_ir_summary_csv: Path
    explanation_ir_quality_report_json: Path
    explanation_ir_manifest_json: Path


@dataclass(frozen=True)
class ExplanationIRArtifactSaveResult:
    """
    Result of saving Batch H artifacts.
    """

    status: str
    run_mode: str
    artifact_paths: ExplanationIRArtifactPaths
    quality_report: Dict[str, Any]
    manifest: Dict[str, Any]
    output_path_status: Dict[str, bool]
    warnings: List[str]
    errors: List[str]


# =============================================================================
# Generic file helpers
# =============================================================================

def write_json(path: str | Path, data: Dict[str, Any]) -> Path:
    """
    Write dictionary as pretty JSON.
    """
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return output_path


def write_jsonl(path: str | Path, records: List[Dict[str, Any]]) -> Path:
    """
    Write list of dictionaries as JSONL.
    """
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False))
            f.write("\n")

    return output_path


def check_output_path_status(paths: ExplanationIRArtifactPaths) -> Dict[str, bool]:
    """
    Check whether expected output files exist.
    """
    return {
        "explanation_ir_jsonl": paths.explanation_ir_jsonl.exists(),
        "explanation_ir_summary_csv": paths.explanation_ir_summary_csv.exists(),
        "explanation_ir_quality_report_json": paths.explanation_ir_quality_report_json.exists(),
        "explanation_ir_manifest_json": paths.explanation_ir_manifest_json.exists(),
    }


# =============================================================================
# Status logic
# =============================================================================

def determine_batch_status(
    build_result: ExplanationIRBuildResult,
    extra_warnings: Optional[List[str]] = None,
    extra_errors: Optional[List[str]] = None,
) -> str:
    """
    Determine batch-level status.

    Simple v1 rule:
        FAILED:
            no IR records were produced, or there are fatal save/build errors.

        PASSED_WITH_WARNINGS:
            output exists but there are warnings or record-level errors.

        PASSED:
            records produced and no warnings/errors.
    """
    warnings = list(build_result.warnings)
    errors = list(build_result.errors)

    if extra_warnings:
        warnings.extend(extra_warnings)

    if extra_errors:
        errors.extend(extra_errors)

    if len(build_result.ir_records) == 0:
        return STATUS_FAILED

    if errors:
        return STATUS_PASSED_WITH_WARNINGS

    if warnings:
        return STATUS_PASSED_WITH_WARNINGS

    return STATUS_PASSED


# =============================================================================
# Quality report
# =============================================================================

def build_quality_report(
    build_result: ExplanationIRBuildResult,
    run_mode: str,
    has_ground_truth: bool,
    input_path: str | Path,
    artifact_paths: ExplanationIRArtifactPaths,
    status: str,
    warnings: Optional[List[str]] = None,
    errors: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Build Batch H quality report.
    """
    warnings = warnings or []
    errors = errors or []

    total_allowed_claims = sum(
        len(record.allowed_claims)
        for record in build_result.ir_records
    )
    total_forbidden_claims = sum(
        len(record.forbidden_claims)
        for record in build_result.ir_records
    )
    total_feature_factors = sum(
        len(record.feature_factors)
        for record in build_result.ir_records
    )
    total_concept_summaries = sum(
        len(record.concept_summaries)
        for record in build_result.ir_records
    )

    failed_record_count = sum(
        1
        for record in build_result.ir_records
        if record.quality.status == "failed"
    )
    warning_record_count = sum(
        1
        for record in build_result.ir_records
        if record.quality.status == "warning"
    )
    passed_record_count = sum(
        1
        for record in build_result.ir_records
        if record.quality.status == "passed"
    )

    records_with_empty_allowed_claims = sum(
        1
        for record in build_result.ir_records
        if len(record.allowed_claims) == 0
    )

    records_with_empty_forbidden_claims = sum(
        1
        for record in build_result.ir_records
        if len(record.forbidden_claims) == 0
    )

    records_with_no_risk_increasing_factors = sum(
        1
        for record in build_result.ir_records
        if len(record.risk_increasing_factors) == 0
    )

    records_with_no_risk_decreasing_factors = sum(
        1
        for record in build_result.ir_records
        if len(record.risk_decreasing_factors) == 0
    )

    all_records_have_llm_input_contract = all(
        record.llm_input_contract is not None
        for record in build_result.ir_records
    )

    all_records_have_validation_contract = all(
        record.validation_contract is not None
        for record in build_result.ir_records
    )

    all_records_trace_to_evidence = all(
        bool(record.source_evidence_id) and record.evidence_trace is not None
        for record in build_result.ir_records
    )

    all_claims_have_truth_conditions = all(
        claim.truth_condition is not None
        for record in build_result.ir_records
        for claim in record.allowed_claims
    )

    all_factors_have_direction = all(
        bool(factor.direction)
        for record in build_result.ir_records
        for factor in record.feature_factors
    )

    all_factors_have_strength = all(
        bool(factor.strength)
        for record in build_result.ir_records
        for factor in record.feature_factors
    )

    quality_report = {
        "batch_name": BATCH_NAME,
        "batch_short_name": BATCH_SHORT_NAME,
        "status": status,
        "created_at": utc_now_iso(),
        "run_mode": run_mode,
        "has_ground_truth": has_ground_truth,
        "ir_schema_version": IR_SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        "purpose": (
            "Convert structured XAI evidence into concept-aware Explanation IR "
            "for LLM generation and faithfulness validation."
        ),
        "inputs": {
            "xai_local_evidence_path": str(input_path),
        },
        "outputs": {
            "explanation_ir_jsonl": str(artifact_paths.explanation_ir_jsonl),
            "explanation_ir_summary_csv": str(artifact_paths.explanation_ir_summary_csv),
            "explanation_ir_quality_report_json": str(
                artifact_paths.explanation_ir_quality_report_json
            ),
            "explanation_ir_manifest_json": str(
                artifact_paths.explanation_ir_manifest_json
            ),
        },
        "record_counts": {
            "output_ir_record_count": len(build_result.ir_records),
            "passed_record_count": passed_record_count,
            "warning_record_count": warning_record_count,
            "failed_record_count": failed_record_count,
        },
        "claim_counts": {
            "total_allowed_claims": total_allowed_claims,
            "total_forbidden_claims": total_forbidden_claims,
            "records_with_empty_allowed_claims": records_with_empty_allowed_claims,
            "records_with_empty_forbidden_claims": records_with_empty_forbidden_claims,
        },
        "factor_counts": {
            "total_feature_factors": total_feature_factors,
            "total_concept_summaries": total_concept_summaries,
            "records_with_no_risk_increasing_factors": records_with_no_risk_increasing_factors,
            "records_with_no_risk_decreasing_factors": records_with_no_risk_decreasing_factors,
        },
        "quality_checks": {
            "all_records_have_llm_input_contract": all_records_have_llm_input_contract,
            "all_records_have_validation_contract": all_records_have_validation_contract,
            "all_records_trace_to_evidence": all_records_trace_to_evidence,
            "all_claims_have_truth_conditions": all_claims_have_truth_conditions,
            "all_factors_have_direction": all_factors_have_direction,
            "all_factors_have_strength": all_factors_have_strength,
        },
        "warnings": list(build_result.warnings) + warnings,
        "errors": list(build_result.errors) + errors,
    }

    return quality_report


# =============================================================================
# Manifest
# =============================================================================

def build_manifest(
    build_result: ExplanationIRBuildResult,
    run_mode: str,
    has_ground_truth: bool,
    input_path: str | Path,
    artifact_paths: ExplanationIRArtifactPaths,
    quality_report: Dict[str, Any],
    output_path_status: Dict[str, bool],
) -> Dict[str, Any]:
    """
    Build Batch H manifest.

    The manifest focuses on lineage and reproducibility.
    """
    manifest = {
        "batch": {
            "name": BATCH_NAME,
            "short_name": BATCH_SHORT_NAME,
            "status": quality_report["status"],
            "created_at": utc_now_iso(),
            "schema_version": IR_SCHEMA_VERSION,
            "builder_version": BUILDER_VERSION,
        },
        "purpose": (
            "Convert structured XAI evidence into concept-aware Explanation IR "
            "for LLM generation and faithfulness validation."
        ),
        "run_mode": run_mode,
        "has_ground_truth": has_ground_truth,
        "inputs": {
            "xai_local_evidence": str(input_path),
        },
        "outputs": {
            "explanation_ir_jsonl": str(artifact_paths.explanation_ir_jsonl),
            "explanation_ir_summary_csv": str(artifact_paths.explanation_ir_summary_csv),
            "quality_report": str(artifact_paths.explanation_ir_quality_report_json),
            "manifest": str(artifact_paths.explanation_ir_manifest_json),
        },
        "output_path_status": output_path_status,
        "upstream": {
            "batch": SOURCE_BATCH_NAME,
            "xai_method": "SHAP",
            "expected_primary_input": "data/reports/xai/xai_local_evidence.jsonl",
        },
        "downstream": {
            "next_batch": "Batch I - LLM Explanation Layer",
            "validator_batch": "Batch J - Faithfulness Validator",
            "main_downstream_input": str(artifact_paths.explanation_ir_jsonl),
        },
        "config": {
            "max_feature_factors_per_direction": DEFAULT_MAX_FEATURE_FACTORS_PER_DIRECTION,
            "max_concept_summaries": DEFAULT_MAX_CONCEPT_SUMMARIES,
            "strong_abs_shap_threshold": STRONG_ABS_SHAP_THRESHOLD,
            "moderate_abs_shap_threshold": MODERATE_ABS_SHAP_THRESHOLD,
            "neutral_shap_epsilon": NEUTRAL_SHAP_EPSILON,
        },
        "schema_contract": {
            "main_output": "explanation_ir.jsonl",
            "record_shape_includes": [
                "ir_id",
                "source_evidence_id",
                "trace_id",
                "run_mode",
                "has_ground_truth",
                "model",
                "customer",
                "prediction_summary",
                "xai_summary",
                "feature_factors",
                "risk_increasing_factors",
                "risk_decreasing_factors",
                "concept_summaries",
                "allowed_claims",
                "forbidden_claims",
                "llm_input_contract",
                "validation_contract",
                "evidence_trace",
                "quality",
                "metadata",
            ],
        },
        "quality_report": quality_report,
        "build_summary": {
            "ir_record_count": len(build_result.ir_records),
            "summary_row_count": int(len(build_result.summary_df)),
            "warning_count": len(build_result.warnings),
            "error_count": len(build_result.errors),
        },
    }

    return manifest


# =============================================================================
# Public save function
# =============================================================================

def get_artifact_paths_for_mode(run_mode: str) -> ExplanationIRArtifactPaths:
    """
    Build artifact paths for a resolved mode.
    """
    return ExplanationIRArtifactPaths(
        explanation_ir_jsonl=get_ir_jsonl_output_path(run_mode),
        explanation_ir_summary_csv=get_ir_summary_output_path(run_mode),
        explanation_ir_quality_report_json=get_ir_quality_report_output_path(run_mode),
        explanation_ir_manifest_json=get_ir_manifest_output_path(run_mode),
    )


def save_explanation_ir_artifacts(
    build_result: ExplanationIRBuildResult,
    run_mode: str,
    has_ground_truth: bool,
    input_path: str | Path,
) -> ExplanationIRArtifactSaveResult:
    """
    Save all Batch H artifacts.
    """
    ensure_output_dirs_for_mode(run_mode)
    artifact_paths = get_artifact_paths_for_mode(run_mode)

    save_warnings: List[str] = []
    save_errors: List[str] = []

    status = determine_batch_status(
        build_result=build_result,
        extra_warnings=save_warnings,
        extra_errors=save_errors,
    )

    try:
        write_jsonl(
            artifact_paths.explanation_ir_jsonl,
            build_result.ir_record_dicts,
        )
    except Exception as exc:
        save_errors.append(f"Failed to save explanation_ir.jsonl: {exc}")

    try:
        build_result.summary_df.to_csv(
            artifact_paths.explanation_ir_summary_csv,
            index=False,
        )
    except Exception as exc:
        save_errors.append(f"Failed to save explanation_ir_summary.csv: {exc}")

    # Recompute status after possible save errors.
    status = determine_batch_status(
        build_result=build_result,
        extra_warnings=save_warnings,
        extra_errors=save_errors,
    )

    quality_report = build_quality_report(
        build_result=build_result,
        run_mode=run_mode,
        has_ground_truth=has_ground_truth,
        input_path=input_path,
        artifact_paths=artifact_paths,
        status=status,
        warnings=save_warnings,
        errors=save_errors,
    )

    try:
        write_json(
            artifact_paths.explanation_ir_quality_report_json,
            quality_report,
        )
    except Exception as exc:
        save_errors.append(f"Failed to save explanation_ir_quality_report.json: {exc}")

    output_path_status = check_output_path_status(artifact_paths)

    manifest = build_manifest(
        build_result=build_result,
        run_mode=run_mode,
        has_ground_truth=has_ground_truth,
        input_path=input_path,
        artifact_paths=artifact_paths,
        quality_report=quality_report,
        output_path_status=output_path_status,
    )

    try:
        write_json(
            artifact_paths.explanation_ir_manifest_json,
            manifest,
        )
    except Exception as exc:
        save_errors.append(f"Failed to save explanation_ir_manifest.json: {exc}")

    output_path_status = check_output_path_status(artifact_paths)

    # Final status after all save attempts.
    final_status = determine_batch_status(
        build_result=build_result,
        extra_warnings=save_warnings,
        extra_errors=save_errors,
    )

    if final_status != quality_report["status"]:
        quality_report["status"] = final_status
        manifest["batch"]["status"] = final_status
        manifest["quality_report"]["status"] = final_status

        # Best effort update so files reflect final status.
        try:
            write_json(
                artifact_paths.explanation_ir_quality_report_json,
                quality_report,
            )
            write_json(
                artifact_paths.explanation_ir_manifest_json,
                manifest,
            )
        except Exception as exc:
            save_errors.append(f"Failed to update final status files: {exc}")

    return ExplanationIRArtifactSaveResult(
        status=final_status,
        run_mode=run_mode,
        artifact_paths=artifact_paths,
        quality_report=quality_report,
        manifest=manifest,
        output_path_status=output_path_status,
        warnings=list(build_result.warnings) + save_warnings,
        errors=list(build_result.errors) + save_errors,
    )