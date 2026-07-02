from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from ml.scripts.xai_layer.case_selection import (
    SelectedCasesResult,
    summarize_selected_cases,
)
from ml.scripts.xai_layer.config import (
    BATCH_NAME,
    BATCH_SHORT_NAME,
    MODEL_REGISTRY_PATH,
    XAI_EVIDENCE_MANIFEST_PATH,
    XAI_EVIDENCE_SUMMARY_CSV_PATH,
    XAI_LOCAL_EVIDENCE_JSONL_PATH,
    XAI_QUALITY_REPORT_JSON_PATH,
    XAI_SELECTED_CASES_CSV_PATH,
    get_config_summary,
    get_optional_input_paths,
    get_output_paths,
    get_predictions_path_for_mode,
    get_required_input_paths,
    get_x_data_path_for_mode,
    get_y_data_path_for_mode,
    ensure_output_dirs,
)
from ml.scripts.xai_layer.evidence_builder import (
    EvidenceBuildResult,
    summarize_evidence_build_result,
)
from ml.scripts.xai_layer.evidence_schema import (
    to_json_safe,
    utc_now_iso,
)
from ml.scripts.xai_layer.loaders import XAIInputs
from ml.scripts.xai_layer.shap_explainer import (
    LocalShapResult,
    summarize_local_shap_result,
)


@dataclass(frozen=True)
class XAIArtifactPaths:
    selected_cases_csv: Path
    local_evidence_jsonl: Path
    evidence_summary_csv: Path
    quality_report_json: Path
    evidence_manifest_json: Path


@dataclass(frozen=True)
class XAIArtifactSaveResult:
    artifact_paths: XAIArtifactPaths
    manifest: dict[str, Any]
    quality_report: dict[str, Any]
    saved_file_count: int
    warnings: list[str]


def write_json(
    *,
    data: dict[str, Any],
    path: Path,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        json.dump(
            to_json_safe(data),
            file,
            ensure_ascii=False,
            indent=2,
        )

    return path


def write_jsonl(
    *,
    records: list[dict[str, Any]],
    path: Path,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(
                json.dumps(
                    to_json_safe(record),
                    ensure_ascii=False,
                )
            )
            file.write("\n")

    return path


def write_csv(
    *,
    dataframe: pd.DataFrame,
    path: Path,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    dataframe.to_csv(path, index=False)
    return path


def get_artifact_paths() -> XAIArtifactPaths:
    return XAIArtifactPaths(
        selected_cases_csv=XAI_SELECTED_CASES_CSV_PATH,
        local_evidence_jsonl=XAI_LOCAL_EVIDENCE_JSONL_PATH,
        evidence_summary_csv=XAI_EVIDENCE_SUMMARY_CSV_PATH,
        quality_report_json=XAI_QUALITY_REPORT_JSON_PATH,
        evidence_manifest_json=XAI_EVIDENCE_MANIFEST_PATH,
    )


def path_status(paths: dict[str, Path]) -> dict[str, dict[str, Any]]:
    status: dict[str, dict[str, Any]] = {}

    for name, path in paths.items():
        exists = path.exists()

        status[name] = {
            "path": str(path),
            "exists": bool(exists),
            "size_bytes": int(path.stat().st_size) if exists else None,
        }

    return status


def collect_warnings(
    *,
    selected_cases_result: SelectedCasesResult,
    shap_result: LocalShapResult,
    evidence_result: EvidenceBuildResult,
) -> list[str]:
    warnings: list[str] = []

    warnings.extend(selected_cases_result.warnings)
    warnings.extend(shap_result.warnings)
    warnings.extend(evidence_result.warnings)

    return warnings


def build_quality_report(
    *,
    inputs: XAIInputs,
    selected_cases_result: SelectedCasesResult,
    shap_result: LocalShapResult,
    evidence_result: EvidenceBuildResult,
) -> dict[str, Any]:
    selected_cases_summary = summarize_selected_cases(selected_cases_result)
    shap_summary = summarize_local_shap_result(shap_result)
    evidence_summary = summarize_evidence_build_result(evidence_result)

    warnings = collect_warnings(
        selected_cases_result=selected_cases_result,
        shap_result=shap_result,
        evidence_result=evidence_result,
    )

    status = "PASSED" if not warnings else "PASSED_WITH_WARNINGS"

    failed_additivity_count = int(evidence_summary["failed_additivity_count"])
    mapping_missing_total = int(evidence_summary["mapping_missing_total"])

    if failed_additivity_count > 0:
        status = "FAILED"

    y_shape = None if inputs.y is None else list(inputs.y.shape)

    quality_report = {
        "batch_name": BATCH_NAME,
        "batch_short_name": BATCH_SHORT_NAME,
        "status": status,
        "created_at": utc_now_iso(),
        "run_mode": inputs.run_mode,
        "has_ground_truth": inputs.has_ground_truth,
        "model": {
            "model_name": inputs.model_bundle.model_name,
            "model_version": inputs.model_bundle.model_version,
            "model_family": inputs.model_bundle.model_family,
            "dataset_branch": inputs.model_bundle.dataset_branch,
            "feature_count": inputs.model_bundle.feature_count,
            "estimator_type": type(inputs.model_bundle.estimator).__name__,
            "default_threshold": inputs.model_bundle.default_threshold,
        },
        "data": {
            "X_shape": list(inputs.X.shape),
            "y_shape": y_shape,
            "predictions_shape": list(inputs.predictions.shape),
            "X_test_shape": list(inputs.X.shape),
            "y_test_shape": y_shape,
            "predictions_test_shape": list(inputs.predictions.shape),
            "feature_registry_shape": list(inputs.feature_registry.shape),
            "feature_mapping_count": len(inputs.feature_mapping),
            "concept_registry_keys": list(inputs.concept_registry.keys()),
        },
        "case_selection": selected_cases_summary,
        "shap": shap_summary,
        "evidence": evidence_summary,
        "quality_checks": {
            "run_mode": inputs.run_mode,
            "has_ground_truth": inputs.has_ground_truth,
            "selected_case_count": int(selected_cases_summary["total_selected_cases"]),
            "evidence_record_count": int(evidence_summary["record_count"]),
            "shap_case_count": int(shap_summary["case_count"]),
            "shap_feature_count": int(shap_summary["feature_count"]),
            "mapping_missing_total": mapping_missing_total,
            "failed_additivity_count": failed_additivity_count,
            "passed_additivity_count": int(shap_summary["passed_additivity_count"]),
            "warning_count": int(len(warnings)),
        },
        "warnings": warnings,
    }

    return quality_report


def build_manifest(
    *,
    inputs: XAIInputs,
    selected_cases_result: SelectedCasesResult,
    shap_result: LocalShapResult,
    evidence_result: EvidenceBuildResult,
    quality_report: dict[str, Any],
    artifact_paths: XAIArtifactPaths,
) -> dict[str, Any]:
    required_inputs = get_required_input_paths(inputs.run_mode)
    optional_inputs = get_optional_input_paths()
    output_paths = get_output_paths()

    y_path = get_y_data_path_for_mode(inputs.run_mode)

    manifest = {
        "batch_name": BATCH_NAME,
        "batch_short_name": BATCH_SHORT_NAME,
        "status": quality_report["status"],
        "created_at": utc_now_iso(),
        "run_mode": inputs.run_mode,
        "has_ground_truth": inputs.has_ground_truth,
        "purpose": (
            "Generate structured local XAI evidence using the selected best model, "
            "model-ready features, model predictions, representative case selection, "
            "and SHAP local attribution."
        ),
        "model": {
            "model_name": inputs.model_bundle.model_name,
            "model_version": inputs.model_bundle.model_version,
            "model_family": inputs.model_bundle.model_family,
            "dataset_branch": inputs.model_bundle.dataset_branch,
            "feature_count": inputs.model_bundle.feature_count,
            "estimator_type": type(inputs.model_bundle.estimator).__name__,
            "default_threshold": inputs.model_bundle.default_threshold,
        },
        "xai_method": {
            "method": "SHAP",
            "explainer_type": shap_result.explainer_type,
            "output_space": shap_result.output_space,
            "case_count": int(len(shap_result.selected_cases)),
            "feature_count": int(len(shap_result.feature_names)),
            "top_k_features": int(
                evidence_result.summary["top_k"].iloc[0]
                if not evidence_result.summary.empty
                else 0
            ),
        },
        "inputs": {
            "run_mode": inputs.run_mode,
            "has_ground_truth": inputs.has_ground_truth,
            "required": {
                name: str(path)
                for name, path in required_inputs.items()
            },
            "optional": {
                name: str(path)
                for name, path in optional_inputs.items()
            },
            "primary_runtime_inputs": {
                "model_registry": str(MODEL_REGISTRY_PATH),
                "best_model": str(required_inputs["best_model"]),
                "X_data": str(get_x_data_path_for_mode(inputs.run_mode)),
                "y_data": None if y_path is None else str(y_path),
                "model_predictions": str(get_predictions_path_for_mode(inputs.run_mode)),
            },
        },
        "outputs": {
            "selected_cases_csv": str(artifact_paths.selected_cases_csv),
            "local_evidence_jsonl": str(artifact_paths.local_evidence_jsonl),
            "evidence_summary_csv": str(artifact_paths.evidence_summary_csv),
            "quality_report_json": str(artifact_paths.quality_report_json),
            "evidence_manifest_json": str(artifact_paths.evidence_manifest_json),
        },
        "output_path_status": path_status(output_paths),
        "config": get_config_summary(inputs.run_mode),
        "quality_report": quality_report,
    }

    return manifest


def validate_artifact_payloads(
    *,
    selected_cases_result: SelectedCasesResult,
    shap_result: LocalShapResult,
    evidence_result: EvidenceBuildResult,
) -> None:
    selected_cases = selected_cases_result.selected_cases

    if selected_cases.empty:
        raise ValueError("Cannot save artifacts because selected_cases is empty.")

    if not evidence_result.records:
        raise ValueError("Cannot save artifacts because evidence records are empty.")

    if not evidence_result.record_dicts:
        raise ValueError("Cannot save artifacts because evidence record dicts are empty.")

    if evidence_result.summary.empty:
        raise ValueError("Cannot save artifacts because evidence summary is empty.")

    if len(evidence_result.records) != len(selected_cases):
        raise ValueError(
            "Evidence record count does not match selected case count. "
            f"{len(evidence_result.records)} != {len(selected_cases)}"
        )

    if shap_result.shap_values.shape[0] != len(selected_cases):
        raise ValueError(
            "SHAP row count does not match selected case count. "
            f"{shap_result.shap_values.shape[0]} != {len(selected_cases)}"
        )


def save_xai_artifacts(
    *,
    inputs: XAIInputs,
    selected_cases_result: SelectedCasesResult,
    shap_result: LocalShapResult,
    evidence_result: EvidenceBuildResult,
) -> XAIArtifactSaveResult:
    ensure_output_dirs()

    validate_artifact_payloads(
        selected_cases_result=selected_cases_result,
        shap_result=shap_result,
        evidence_result=evidence_result,
    )

    artifact_paths = get_artifact_paths()

    write_csv(
        dataframe=selected_cases_result.selected_cases,
        path=artifact_paths.selected_cases_csv,
    )

    write_jsonl(
        records=evidence_result.record_dicts,
        path=artifact_paths.local_evidence_jsonl,
    )

    write_csv(
        dataframe=evidence_result.summary,
        path=artifact_paths.evidence_summary_csv,
    )

    quality_report = build_quality_report(
        inputs=inputs,
        selected_cases_result=selected_cases_result,
        shap_result=shap_result,
        evidence_result=evidence_result,
    )

    write_json(
        data=quality_report,
        path=artifact_paths.quality_report_json,
    )

    manifest = build_manifest(
        inputs=inputs,
        selected_cases_result=selected_cases_result,
        shap_result=shap_result,
        evidence_result=evidence_result,
        quality_report=quality_report,
        artifact_paths=artifact_paths,
    )

    write_json(
        data=manifest,
        path=artifact_paths.evidence_manifest_json,
    )

    warnings = collect_warnings(
        selected_cases_result=selected_cases_result,
        shap_result=shap_result,
        evidence_result=evidence_result,
    )

    return XAIArtifactSaveResult(
        artifact_paths=artifact_paths,
        manifest=manifest,
        quality_report=quality_report,
        saved_file_count=5,
        warnings=warnings,
    )


def summarize_artifact_save_result(
    result: XAIArtifactSaveResult,
) -> dict[str, Any]:
    paths = {
        "selected_cases_csv": result.artifact_paths.selected_cases_csv,
        "local_evidence_jsonl": result.artifact_paths.local_evidence_jsonl,
        "evidence_summary_csv": result.artifact_paths.evidence_summary_csv,
        "quality_report_json": result.artifact_paths.quality_report_json,
        "evidence_manifest_json": result.artifact_paths.evidence_manifest_json,
    }

    return {
        "status": result.quality_report["status"],
        "run_mode": result.quality_report["run_mode"],
        "has_ground_truth": result.quality_report["has_ground_truth"],
        "saved_file_count": int(result.saved_file_count),
        "paths": {
            name: str(path)
            for name, path in paths.items()
        },
        "path_status": path_status(paths),
        "warning_count": int(len(result.warnings)),
        "warnings": result.warnings,
    }


__all__ = [
    "XAIArtifactPaths",
    "XAIArtifactSaveResult",
    "write_json",
    "write_jsonl",
    "write_csv",
    "get_artifact_paths",
    "path_status",
    "collect_warnings",
    "build_quality_report",
    "build_manifest",
    "validate_artifact_payloads",
    "save_xai_artifacts",
    "summarize_artifact_save_result",
]