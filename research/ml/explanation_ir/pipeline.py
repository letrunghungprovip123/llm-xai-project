from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .artifacts import save_explanation_ir_artifacts
from .config import (
    BATCH_NAME,
    BATCH_SHORT_NAME,
    DEFAULT_RUN_MODE,
    get_config_summary,
)
from .ir_builder import build_explanation_ir_records
from .loaders import (
    load_xai_evidence_inputs,
    summarize_loaded_inputs,
)


def run_batch_h(
    run_mode: str = DEFAULT_RUN_MODE,
    input_path: Optional[str | Path] = None,
    xai_quality_summary_path: Optional[str | Path] = None,
    xai_concept_aggregation_path: Optional[str | Path] = None,
    xai_quality_manifest_path: Optional[str | Path] = None,
    print_config: bool = False,
    fail_on_warnings: bool = False,
) -> int:
    print(f"{BATCH_NAME} ({BATCH_SHORT_NAME})")
    print(f"mode: {run_mode}")

    if print_config:
        config = get_config_summary(
            run_mode=run_mode,
            input_path=input_path,
            xai_quality_summary_path=xai_quality_summary_path,
            xai_concept_aggregation_path=xai_concept_aggregation_path,
            xai_quality_manifest_path=xai_quality_manifest_path,
        )
        print(json.dumps(config, indent=2, ensure_ascii=False))

    try:
        inputs = load_xai_evidence_inputs(
            run_mode=run_mode,
            input_path=input_path,
            xai_quality_summary_path=xai_quality_summary_path,
            xai_concept_aggregation_path=xai_concept_aggregation_path,
            xai_quality_manifest_path=xai_quality_manifest_path,
        )
    except Exception as exc:
        print(f"[FAILED] load inputs: {exc}")
        return 1

    loaded_summary = summarize_loaded_inputs(inputs)

    print(f"resolved_mode: {inputs.run_mode}")
    print(f"evidence_records: {loaded_summary['evidence_record_count']}")
    print(f"quality_records: {loaded_summary['quality_metric_record_count']}")
    print(f"concept_records: {loaded_summary['concept_metric_record_count']}")
    print(f"loader_warnings: {loaded_summary['warning_count']}")

    if inputs.warnings:
        for warning in inputs.warnings[:8]:
            print(f"- {warning}")

        if len(inputs.warnings) > 8:
            print(f"... {len(inputs.warnings) - 8} more loader warnings")

    try:
        build_result = build_explanation_ir_records(
            evidence_records=inputs.evidence_records,
            run_mode=inputs.run_mode,
            has_ground_truth=inputs.has_ground_truth,
            source_file=inputs.xai_evidence_path,
            quality_by_evidence_id=inputs.quality_by_evidence_id,
            concepts_by_evidence_id=inputs.concepts_by_evidence_id,
        )
    except Exception as exc:
        print(f"[FAILED] build IR: {exc}")
        return 1

    print(f"ir_records: {len(build_result.ir_records)}")
    print(f"joined_gplus: {build_result.joined_gplus_count}")
    print(f"missing_gplus: {build_result.missing_gplus_count}")
    print(f"builder_warnings: {len(build_result.warnings)}")
    print(f"builder_errors: {len(build_result.errors)}")

    if not build_result.ir_records:
        print("[FAILED] no IR records created")
        return 1

    try:
        save_result = save_explanation_ir_artifacts(
            build_result=build_result,
            run_mode=inputs.run_mode,
            has_ground_truth=inputs.has_ground_truth,
            input_path=inputs.xai_evidence_path,
            xai_quality_summary_path=inputs.xai_quality_summary_path,
            xai_concept_aggregation_path=inputs.xai_concept_aggregation_path,
            xai_quality_manifest_path=inputs.xai_quality_manifest_path,
            loader_warnings=inputs.warnings,
        )
    except Exception as exc:
        print(f"[FAILED] save artifacts: {exc}")
        return 1

    print(f"status: {save_result.status}")
    print(f"jsonl: {save_result.artifact_paths.explanation_ir_jsonl}")
    print(f"summary: {save_result.artifact_paths.explanation_ir_summary_csv}")
    print(f"quality_report: {save_result.artifact_paths.explanation_ir_quality_report_json}")
    print(f"manifest: {save_result.artifact_paths.explanation_ir_manifest_json}")

    if save_result.errors:
        print("errors:")
        for error in save_result.errors[:10]:
            print(f"- {error}")

    if save_result.warnings:
        print("warnings:")
        for warning in save_result.warnings[:10]:
            print(f"- {warning}")

        if len(save_result.warnings) > 10:
            print(f"... {len(save_result.warnings) - 10} more warnings")

    if save_result.status == "FAILED":
        return 1

    if fail_on_warnings and save_result.status == "PASSED_WITH_WARNINGS":
        return 2

    return 0
