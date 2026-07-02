"""
Artifact saving for Batch I - LLM Explanation Layer.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from ml.scripts.llm_explanation_layer.config import (
    BATCH_NAME,
    BATCH_SHORT_NAME,
    BATCH_STATUS_FAILED,
    BATCH_STATUS_PASSED,
    BATCH_STATUS_PASSED_WITH_WARNINGS,
    EXPLANATION_SCHEMA_VERSION,
    GENERATOR_NAME_TEMPLATE,
    GENERATOR_TYPE_TEMPLATE,
    GENERATOR_VERSION,
    get_explanation_jsonl_output_path,
    get_explanation_manifest_output_path,
    get_explanation_quality_report_output_path,
    get_explanation_summary_output_path,
    ensure_output_dirs_for_mode,
)
from ml.scripts.llm_explanation_layer.explanation_schema import (
    LLMExplanationBuildResult,
    utc_now_iso,
)


def save_jsonl(
    records: List[Dict[str, Any]],
    path: str | Path,
) -> None:
    """Save records as JSONL."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                    allow_nan=False,
                )
                + "\n"
            )


def save_json(
    data: Dict[str, Any],
    path: str | Path,
) -> None:
    """Save dictionary as JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )


def determine_batch_status(build_result: LLMExplanationBuildResult) -> str:
    """Determine batch-level status."""
    if build_result.errors:
        return BATCH_STATUS_FAILED

    if not build_result.explanation_records:
        return BATCH_STATUS_FAILED

    warning_records = [
        record
        for record in build_result.explanation_records
        if record.quality.warnings
    ]

    failed_records = [
        record
        for record in build_result.explanation_records
        if record.quality.errors
    ]

    if failed_records:
        return BATCH_STATUS_FAILED

    if warning_records or build_result.warnings:
        return BATCH_STATUS_PASSED_WITH_WARNINGS

    return BATCH_STATUS_PASSED


def build_quality_report(
    build_result: LLMExplanationBuildResult,
    run_mode: str,
    input_path: str | Path,
    output_jsonl_path: str | Path,
    output_summary_path: str | Path,
) -> Dict[str, Any]:
    """Build quality report JSON."""
    records = build_result.explanation_records

    total_records = len(records)

    warning_records = [
        record for record in records
        if record.quality.warnings
    ]

    failed_records = [
        record for record in records
        if record.quality.errors
    ]

    total_characters = sum(
        record.quality.character_count
        for record in records
    )

    avg_characters = (
        total_characters / total_records
        if total_records > 0
        else 0.0
    )

    return {
        "batch_name": BATCH_NAME,
        "batch_short_name": BATCH_SHORT_NAME,
        "run_mode": run_mode,
        "generator": {
            "generator_type": GENERATOR_TYPE_TEMPLATE,
            "generator_name": GENERATOR_NAME_TEMPLATE,
            "generator_version": GENERATOR_VERSION,
            "uses_external_ai_api": False,
        },
        "status": determine_batch_status(build_result),
        "input": {
            "input_path": str(input_path),
        },
        "outputs": {
            "llm_explanations_jsonl": str(output_jsonl_path),
            "summary_csv": str(output_summary_path),
        },
        "counts": {
            "total_records": total_records,
            "generated_records": total_records - len(failed_records),
            "warning_records": len(warning_records),
            "failed_records": len(failed_records),
            "batch_warning_count": len(build_result.warnings),
            "batch_error_count": len(build_result.errors),
        },
        "text_stats": {
            "total_characters": total_characters,
            "average_characters_per_record": avg_characters,
        },
        "warnings": build_result.warnings[:100],
        "errors": build_result.errors[:100],
        "created_at": utc_now_iso(),
    }


def build_manifest(
    build_result: LLMExplanationBuildResult,
    run_mode: str,
    input_path: str | Path,
    output_jsonl_path: str | Path,
    output_summary_path: str | Path,
    output_quality_report_path: str | Path,
) -> Dict[str, Any]:
    """Build manifest JSON."""
    return {
        "batch_name": BATCH_NAME,
        "batch_short_name": BATCH_SHORT_NAME,
        "run_mode": run_mode,
        "explanation_schema_version": EXPLANATION_SCHEMA_VERSION,
        "generator": {
            "generator_type": GENERATOR_TYPE_TEMPLATE,
            "generator_name": GENERATOR_NAME_TEMPLATE,
            "generator_version": GENERATOR_VERSION,
            "uses_external_ai_api": False,
        },
        "source": {
            "source_batch": "Batch H - Concept-aware Explanation IR Layer",
            "input_path": str(input_path),
        },
        "outputs": {
            "llm_explanations_jsonl": str(output_jsonl_path),
            "summary_csv": str(output_summary_path),
            "quality_report_json": str(output_quality_report_path),
        },
        "record_count": len(build_result.explanation_records),
        "status": determine_batch_status(build_result),
        "created_at": utc_now_iso(),
    }


def save_llm_explanation_artifacts(
    build_result: LLMExplanationBuildResult,
    run_mode: str,
    input_path: str | Path,
    generator_type: str = GENERATOR_TYPE_TEMPLATE,
) -> Dict[str, Path]:
    """
    Save all Batch I artifacts.

    Returns:
        Dictionary of artifact paths.
    """
    ensure_output_dirs_for_mode(run_mode, generator_type)

    output_jsonl_path = get_explanation_jsonl_output_path(
        run_mode,
        generator_type,
    )
    output_summary_path = get_explanation_summary_output_path(
        run_mode,
        generator_type,
    )
    output_quality_report_path = get_explanation_quality_report_output_path(
        run_mode,
        generator_type,
    )
    output_manifest_path = get_explanation_manifest_output_path(
        run_mode,
        generator_type,
    )

    save_jsonl(
        build_result.explanation_record_dicts,
        output_jsonl_path,
    )

    summary_df = pd.DataFrame(build_result.summary_rows)
    output_summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_df.to_csv(output_summary_path, index=False)

    quality_report = build_quality_report(
        build_result=build_result,
        run_mode=run_mode,
        input_path=input_path,
        output_jsonl_path=output_jsonl_path,
        output_summary_path=output_summary_path,
    )
    save_json(quality_report, output_quality_report_path)

    manifest = build_manifest(
        build_result=build_result,
        run_mode=run_mode,
        input_path=input_path,
        output_jsonl_path=output_jsonl_path,
        output_summary_path=output_summary_path,
        output_quality_report_path=output_quality_report_path,
    )
    save_json(manifest, output_manifest_path)

    return {
        "llm_explanations_jsonl": output_jsonl_path,
        "summary_csv": output_summary_path,
        "quality_report_json": output_quality_report_path,
        "manifest_json": output_manifest_path,
    }