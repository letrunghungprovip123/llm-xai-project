from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import (
    BATCH_NAME,
    BATCH_SHORT_NAME,
    BUILDER_VERSION,
    DEFAULT_MAX_CONCEPTS_FOR_LLM,
    DEFAULT_TOP_K_FOR_LLM,
    IR_SCHEMA_VERSION,
    SOURCE_BATCH_NAME,
    SOURCE_QUALITY_BATCH_NAME,
    STATUS_FAILED,
    STATUS_PASSED,
    STATUS_PASSED_WITH_WARNINGS,
    ensure_output_dirs_for_mode,
    get_ir_jsonl_output_path,
    get_ir_manifest_output_path,
    get_ir_quality_report_output_path,
    get_ir_summary_output_path,
)
from .ir_builder import ExplanationIRBuildResult
from .ir_schema import utc_now_iso


@dataclass
class ExplanationIRArtifactPaths:
    explanation_ir_jsonl: Path
    explanation_ir_summary_csv: Path
    explanation_ir_quality_report_json: Path
    explanation_ir_manifest_json: Path


@dataclass
class ExplanationIRArtifactSaveResult:
    status: str
    run_mode: str
    artifact_paths: ExplanationIRArtifactPaths
    quality_report: Dict[str, Any]
    manifest: Dict[str, Any]
    output_path_status: Dict[str, bool]
    warnings: List[str]
    errors: List[str]


def write_json(path: str | Path, data: Dict[str, Any]) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    with p.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return p


def write_jsonl(path: str | Path, records: List[Dict[str, Any]]) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    with p.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False))
            f.write("\n")

    return p


def write_csv(path: str | Path, rows: List[Dict[str, Any]]) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    if not rows:
        with p.open("w", encoding="utf-8", newline="") as f:
            f.write("")
        return p

    fields = list(rows[0].keys())

    with p.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()

        for row in rows:
            writer.writerow(row)

    return p


def determine_status(
    build_result: ExplanationIRBuildResult,
    loader_warnings: List[str],
) -> str:
    if not build_result.ir_records:
        return STATUS_FAILED

    for record in build_result.ir_records:
        quality = record.get("quality") or {}

        if quality.get("status") == "failed":
            return STATUS_FAILED

    if build_result.errors:
        return STATUS_FAILED

    if build_result.missing_gplus_count > 0:
        return STATUS_PASSED_WITH_WARNINGS

    if loader_warnings or build_result.warnings:
        return STATUS_PASSED_WITH_WARNINGS

    for record in build_result.ir_records:
        quality = record.get("quality") or {}

        if quality.get("status") == "warning":
            return STATUS_PASSED_WITH_WARNINGS

    return STATUS_PASSED


def build_quality_report(
    build_result: ExplanationIRBuildResult,
    run_mode: str,
    has_ground_truth: bool,
    input_path: str | Path,
    xai_quality_summary_path: Optional[str | Path],
    xai_concept_aggregation_path: Optional[str | Path],
    xai_quality_manifest_path: Optional[str | Path],
    artifact_paths: ExplanationIRArtifactPaths,
    status: str,
    warnings: List[str],
    errors: List[str],
) -> Dict[str, Any]:
    records = build_result.ir_records

    passed_records = 0
    warning_records = 0
    failed_records = 0

    readiness_counts: Dict[str, int] = {}
    stability_counts: Dict[str, int] = {}

    total_allowed_claims = 0
    total_forbidden_claims = 0
    total_feature_factors = 0
    total_concepts = 0

    missing_quality_metric_count = 0
    low_top10_coverage_count = 0

    for record in records:
        quality = record.get("quality") or {}

        if quality.get("status") == "passed":
            passed_records += 1
        elif quality.get("status") == "warning":
            warning_records += 1
        elif quality.get("status") == "failed":
            failed_records += 1

        readiness = (record.get("evidence_readiness") or {}).get("status", "unknown")
        readiness_counts[readiness] = readiness_counts.get(readiness, 0) + 1

        metrics = record.get("xai_quality_metrics") or {}
        stability = (metrics.get("stability") or {}).get("status", "unknown")
        stability_counts[stability] = stability_counts.get(stability, 0) + 1

        total_allowed_claims += len(record.get("allowed_claims") or [])
        total_forbidden_claims += len(record.get("forbidden_claims") or [])
        total_feature_factors += len(record.get("feature_factors") or [])
        total_concepts += len((record.get("concept_evidence") or {}).get("all_concepts") or [])

        if metrics.get("status") == "missing":
            missing_quality_metric_count += 1
        else:
            top10 = ((metrics.get("topk_coverage") or {}).get("top10"))
            if top10 is not None and top10 < 0.5:
                low_top10_coverage_count += 1

    return {
        "batch_name": BATCH_NAME,
        "batch_short_name": BATCH_SHORT_NAME,
        "status": status,
        "created_at": utc_now_iso(),
        "run_mode": run_mode,
        "has_ground_truth": has_ground_truth,
        "ir_schema_version": IR_SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        "purpose": (
            "Build quality-aware and selection-ready Explanation IR for "
            "Adaptive Evidence Selection and Evidence Exposure S0-S5."
        ),
        "inputs": {
            "xai_local_evidence_path": str(input_path),
            "xai_quality_summary_path": str(xai_quality_summary_path)
            if xai_quality_summary_path
            else None,
            "xai_concept_aggregation_path": str(xai_concept_aggregation_path)
            if xai_concept_aggregation_path
            else None,
            "xai_quality_manifest_path": str(xai_quality_manifest_path)
            if xai_quality_manifest_path
            else None,
        },
        "outputs": {
            "explanation_ir_v2_jsonl": str(artifact_paths.explanation_ir_jsonl),
            "explanation_ir_v2_summary_csv": str(artifact_paths.explanation_ir_summary_csv),
            "explanation_ir_v2_quality_report_json": str(
                artifact_paths.explanation_ir_quality_report_json
            ),
            "explanation_ir_v2_manifest_json": str(
                artifact_paths.explanation_ir_manifest_json
            ),
        },
        "record_counts": {
            "output_ir_record_count": len(records),
            "passed_record_count": passed_records,
            "warning_record_count": warning_records,
            "failed_record_count": failed_records,
        },
        "batch_g_plus_join": {
            "joined_gplus_count": build_result.joined_gplus_count,
            "missing_gplus_count": build_result.missing_gplus_count,
        },
        "claim_counts": {
            "total_allowed_claims": total_allowed_claims,
            "total_forbidden_claims": total_forbidden_claims,
        },
        "factor_counts": {
            "total_feature_factors": total_feature_factors,
            "total_concepts": total_concepts,
        },
        "readiness_counts": readiness_counts,
        "stability_counts": stability_counts,
        "quality_checks": {
            "all_records_have_xai_quality_metrics": all(
                "xai_quality_metrics" in x for x in records
            ),
            "all_records_have_concept_evidence": all(
                "concept_evidence" in x for x in records
            ),
            "all_records_have_evidence_readiness": all(
                "evidence_readiness" in x for x in records
            ),
            "all_records_have_evidence_views": all(
                "evidence_views" in x for x in records
            ),
            "all_records_have_exposure_contract": all(
                "evidence_exposure_contract" in x for x in records
            ),
            "all_records_have_adaptive_selection_contract": all(
                "adaptive_selection_contract" in x for x in records
            ),
            "all_records_have_claim_policy": all(
                "claim_policy" in x for x in records
            ),
            "all_records_have_validation_contract": all(
                "validation_contract" in x for x in records
            ),
            "missing_quality_metric_count": missing_quality_metric_count,
            "low_top10_coverage_count": low_top10_coverage_count,
        },
        "warnings": warnings,
        "errors": errors,
    }


def build_manifest(
    build_result: ExplanationIRBuildResult,
    run_mode: str,
    has_ground_truth: bool,
    input_path: str | Path,
    xai_quality_summary_path: Optional[str | Path],
    xai_concept_aggregation_path: Optional[str | Path],
    xai_quality_manifest_path: Optional[str | Path],
    artifact_paths: ExplanationIRArtifactPaths,
    quality_report: Dict[str, Any],
    status: str,
    warnings: List[str],
    errors: List[str],
) -> Dict[str, Any]:
    return {
        "batch": {
            "name": BATCH_NAME,
            "short_name": BATCH_SHORT_NAME,
            "status": status,
            "created_at": utc_now_iso(),
            "schema_version": IR_SCHEMA_VERSION,
            "builder_version": BUILDER_VERSION,
        },
        "purpose": (
            "Convert Batch G evidence and Batch G+ quality metrics into "
            "Explanation IR v2 for Adaptive Evidence Selection, Evidence Exposure "
            "Controller and Batch J validation."
        ),
        "run_mode": run_mode,
        "has_ground_truth": has_ground_truth,
        "upstream": {
            "xai_evidence_batch": SOURCE_BATCH_NAME,
            "xai_quality_batch": SOURCE_QUALITY_BATCH_NAME,
        },
        "downstream": {
            "next_batch": "Adaptive Evidence Selection / Evidence Exposure Controller",
            "validator_batch": "Batch J - Claim-level Faithfulness Validator",
            "main_downstream_input": str(artifact_paths.explanation_ir_jsonl),
        },
        "inputs": {
            "xai_local_evidence": str(input_path),
            "xai_quality_summary": str(xai_quality_summary_path)
            if xai_quality_summary_path
            else None,
            "xai_concept_aggregation": str(xai_concept_aggregation_path)
            if xai_concept_aggregation_path
            else None,
            "xai_quality_manifest": str(xai_quality_manifest_path)
            if xai_quality_manifest_path
            else None,
        },
        "outputs": {
            "explanation_ir_v2_jsonl": str(artifact_paths.explanation_ir_jsonl),
            "explanation_ir_v2_summary_csv": str(artifact_paths.explanation_ir_summary_csv),
            "quality_report": str(artifact_paths.explanation_ir_quality_report_json),
            "manifest": str(artifact_paths.explanation_ir_manifest_json),
        },
        "config": {
            "default_top_k_for_llm": DEFAULT_TOP_K_FOR_LLM,
            "default_max_concepts_for_llm": DEFAULT_MAX_CONCEPTS_FOR_LLM,
            "cosine_redundancy_core_enabled": False,
        },
        "schema_contract": {
            "main_output": "explanation_ir_v2.jsonl",
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
                "xai_quality_metrics",
                "evidence_readiness",
                "feature_factors",
                "risk_increasing_factors",
                "risk_decreasing_factors",
                "concept_summaries",
                "concept_evidence",
                "contribution_accounting",
                "feature_tiers",
                "evidence_views",
                "allowed_claims",
                "forbidden_claims",
                "claim_policy",
                "llm_input_contract",
                "validation_contract",
                "evidence_exposure_contract",
                "adaptive_selection_contract",
                "evidence_trace",
                "quality",
                "metadata",
            ],
        },
        "build_summary": {
            "ir_record_count": len(build_result.ir_records),
            "summary_row_count": len(build_result.summary_rows),
            "joined_gplus_count": build_result.joined_gplus_count,
            "missing_gplus_count": build_result.missing_gplus_count,
            "warning_count": len(warnings),
            "error_count": len(errors),
        },
        "quality_report": quality_report,
    }


def output_status(paths: ExplanationIRArtifactPaths) -> Dict[str, bool]:
    return {
        "explanation_ir_v2_jsonl": paths.explanation_ir_jsonl.exists(),
        "explanation_ir_v2_summary_csv": paths.explanation_ir_summary_csv.exists(),
        "explanation_ir_v2_quality_report_json": paths.explanation_ir_quality_report_json.exists(),
        "explanation_ir_v2_manifest_json": paths.explanation_ir_manifest_json.exists(),
    }


def save_explanation_ir_artifacts(
    build_result: ExplanationIRBuildResult,
    run_mode: str,
    has_ground_truth: bool,
    input_path: str | Path,
    xai_quality_summary_path: Optional[str | Path] = None,
    xai_concept_aggregation_path: Optional[str | Path] = None,
    xai_quality_manifest_path: Optional[str | Path] = None,
    loader_warnings: Optional[List[str]] = None,
) -> ExplanationIRArtifactSaveResult:
    loader_warnings = loader_warnings or []
    ensure_output_dirs_for_mode(run_mode)

    paths = ExplanationIRArtifactPaths(
        explanation_ir_jsonl=get_ir_jsonl_output_path(run_mode),
        explanation_ir_summary_csv=get_ir_summary_output_path(run_mode),
        explanation_ir_quality_report_json=get_ir_quality_report_output_path(run_mode),
        explanation_ir_manifest_json=get_ir_manifest_output_path(run_mode),
    )

    warnings = list(loader_warnings) + list(build_result.warnings)
    errors = list(build_result.errors)

    status = determine_status(build_result, loader_warnings)

    write_jsonl(paths.explanation_ir_jsonl, build_result.ir_records)
    write_csv(paths.explanation_ir_summary_csv, build_result.summary_rows)

    quality_report = build_quality_report(
        build_result=build_result,
        run_mode=run_mode,
        has_ground_truth=has_ground_truth,
        input_path=input_path,
        xai_quality_summary_path=xai_quality_summary_path,
        xai_concept_aggregation_path=xai_concept_aggregation_path,
        xai_quality_manifest_path=xai_quality_manifest_path,
        artifact_paths=paths,
        status=status,
        warnings=warnings,
        errors=errors,
    )

    write_json(paths.explanation_ir_quality_report_json, quality_report)

    manifest = build_manifest(
        build_result=build_result,
        run_mode=run_mode,
        has_ground_truth=has_ground_truth,
        input_path=input_path,
        xai_quality_summary_path=xai_quality_summary_path,
        xai_concept_aggregation_path=xai_concept_aggregation_path,
        xai_quality_manifest_path=xai_quality_manifest_path,
        artifact_paths=paths,
        quality_report=quality_report,
        status=status,
        warnings=warnings,
        errors=errors,
    )

    write_json(paths.explanation_ir_manifest_json, manifest)

    path_status = output_status(paths)

    if not all(path_status.values()):
        status = STATUS_FAILED
        errors.append("One or more output files were not created.")

    return ExplanationIRArtifactSaveResult(
        status=status,
        run_mode=run_mode,
        artifact_paths=paths,
        quality_report=quality_report,
        manifest=manifest,
        output_path_status=path_status,
        warnings=warnings,
        errors=errors,
    )