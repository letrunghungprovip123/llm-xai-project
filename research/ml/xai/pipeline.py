from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .artifacts import (
    save_xai_artifacts,
    summarize_artifact_save_result,
)
from .case_selection import (
    select_representative_cases,
    summarize_selected_cases,
)
from .config import (
    BATCH_NAME,
    DEFAULT_RUN_MODE,
    XAI_CONFIG,
    ensure_output_dirs,
    get_config_summary,
    validate_required_inputs_exist,
    validate_run_mode,
)
from .evidence_builder import (
    build_local_evidence_records,
    summarize_evidence_build_result,
)
from .loaders import (
    load_xai_inputs,
    summarize_loaded_inputs,
)
from .shap_explainer import (
    compute_local_shap_values,
    summarize_local_shap_result,
)


@dataclass(frozen=True)
class XAIPipelineResult:
    status: str
    run_mode: str
    has_ground_truth: bool
    runtime_seconds: float
    loaded_summary: dict[str, Any]
    selected_cases_summary: dict[str, Any]
    shap_summary: dict[str, Any]
    evidence_summary: dict[str, Any]
    artifact_summary: dict[str, Any]


def print_section(title: str) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def print_config_summary(run_mode: str) -> None:
    config_summary = get_config_summary(run_mode)

    print_section("Batch configuration")
    print("Batch:", config_summary["batch_name"])
    print("Project root:", config_summary["project_root"])
    print("Run mode:", config_summary["run_mode"])
    print("Has ground truth:", config_summary["has_ground_truth"])
    print("Expected model:", config_summary["expected_best_model_name"])
    print("Expected dataset branch:", config_summary["expected_dataset_branch"])
    print("Cases per group:", config_summary["xai_config"]["cases_per_group"])
    print("Top-k features:", config_summary["xai_config"]["top_k_features"])
    print("SHAP background sample size:", config_summary["xai_config"]["shap_background_sample_size"])
    print("Case groups:", config_summary["xai_config"]["case_groups"])
    print("X data path:", config_summary["mode_paths"]["x_data_path"])
    print("y data path:", config_summary["mode_paths"]["y_data_path"])
    print("Predictions path:", config_summary["mode_paths"]["predictions_path"])


def run_pipeline(
    run_mode: str = DEFAULT_RUN_MODE,
) -> XAIPipelineResult:
    run_mode = validate_run_mode(run_mode)

    started_at = time.perf_counter()

    print_section(BATCH_NAME)
    print("Starting Batch G XAI Evidence Layer...")
    print("Run mode:", run_mode)

    ensure_output_dirs()

    print_config_summary(run_mode)

    print_section("Step 1 - Validate required inputs")
    validate_required_inputs_exist(run_mode)
    print("Required input files exist.")
    print("Input validation mode:", run_mode)

    print_section("Step 2 - Load XAI inputs")
    inputs = load_xai_inputs(run_mode=run_mode)
    loaded_summary = summarize_loaded_inputs(inputs)

    print("Loaded XAI inputs successfully.")
    print("Run mode:", loaded_summary["run_mode"])
    print("Has ground truth:", loaded_summary["has_ground_truth"])
    print("Model:", loaded_summary["model"]["model_name"])
    print("Model version:", loaded_summary["model"]["model_version"])
    print("Model family:", loaded_summary["model"]["model_family"])
    print("Dataset branch:", loaded_summary["model"]["dataset_branch"])
    print("Estimator type:", loaded_summary["model"]["estimator_type"])
    print("Feature count:", loaded_summary["model"]["feature_count"])
    print("X shape:", loaded_summary["data"]["X_shape"])
    print("y shape:", loaded_summary["data"]["y_shape"])
    print("predictions shape:", loaded_summary["data"]["predictions_shape"])

    print_section("Step 3 - Select representative cases")
    selected_cases_result = select_representative_cases(
        inputs,
        run_mode=run_mode,
    )

    selected_cases_summary = summarize_selected_cases(selected_cases_result)

    print("Selected representative cases successfully.")
    print("Run mode:", selected_cases_summary["run_mode"])
    print("Has ground truth:", selected_cases_summary["has_ground_truth"])
    print("Total selected cases:", selected_cases_summary["total_selected_cases"])
    print("Group counts:", selected_cases_summary["group_counts"])
    print("Warnings:", selected_cases_summary["warnings"])
    print("First 5 evidence IDs:", selected_cases_summary["first_5_evidence_ids"])

    print_section("Step 4 - Compute local SHAP values")
    shap_result = compute_local_shap_values(
        inputs=inputs,
        selected_cases=selected_cases_result.selected_cases,
        background_sample_size=XAI_CONFIG.shap_background_sample_size,
    )

    shap_summary = summarize_local_shap_result(shap_result)

    print("Computed local SHAP values successfully.")
    print("Case count:", shap_summary["case_count"])
    print("Feature count:", shap_summary["feature_count"])
    print("SHAP values shape:", shap_summary["shap_values_shape"])
    print("Explainer type:", shap_summary["explainer_type"])
    print("Output space:", shap_summary["output_space"])
    print("Max additivity error:", shap_summary["additivity_error_max"])
    print("Failed additivity count:", shap_summary["failed_additivity_count"])
    print("Warnings:", shap_summary["warnings"])

    print_section("Step 5 - Build structured XAI evidence")
    evidence_result = build_local_evidence_records(
        inputs=inputs,
        shap_result=shap_result,
        top_k=XAI_CONFIG.top_k_features,
    )

    evidence_summary = summarize_evidence_build_result(evidence_result)

    print("Built structured local evidence records successfully.")
    print("Record count:", evidence_summary["record_count"])
    print("Summary shape:", evidence_summary["summary_shape"])
    print("Run mode counts:", evidence_summary["run_mode_counts"])
    print("Has ground truth counts:", evidence_summary["has_ground_truth_counts"])
    print("Case type counts:", evidence_summary["case_type_counts"])
    print("Mapping missing total:", evidence_summary["mapping_missing_total"])
    print("Failed additivity count:", evidence_summary["failed_additivity_count"])
    print("Warnings:", evidence_summary["warnings"])

    print_section("Step 6 - Save XAI artifacts")
    artifact_save_result = save_xai_artifacts(
        inputs=inputs,
        selected_cases_result=selected_cases_result,
        shap_result=shap_result,
        evidence_result=evidence_result,
    )

    artifact_summary = summarize_artifact_save_result(artifact_save_result)

    print("Saved XAI artifacts successfully.")
    print("Status:", artifact_summary["status"])
    print("Run mode:", artifact_summary["run_mode"])
    print("Has ground truth:", artifact_summary["has_ground_truth"])
    print("Saved file count:", artifact_summary["saved_file_count"])
    print("Warning count:", artifact_summary["warning_count"])
    print("Warnings:", artifact_summary["warnings"])

    print("\nOutput paths:")
    for name, path in artifact_summary["paths"].items():
        print(f"- {name}: {path}")

    runtime_seconds = time.perf_counter() - started_at

    final_status = str(artifact_summary["status"])

    print_section("Batch G completed")
    print("Status:", final_status)
    print("Run mode:", run_mode)
    print("Has ground truth:", inputs.has_ground_truth)
    print("Runtime seconds:", round(runtime_seconds, 2))
    print("Best model:", loaded_summary["model"]["model_name"])
    print("Explainer:", shap_summary["explainer_type"])
    print("Evidence records:", evidence_summary["record_count"])
    print("Failed additivity count:", evidence_summary["failed_additivity_count"])
    print("Mapping missing total:", evidence_summary["mapping_missing_total"])

    return XAIPipelineResult(
        status=final_status,
        run_mode=run_mode,
        has_ground_truth=inputs.has_ground_truth,
        runtime_seconds=runtime_seconds,
        loaded_summary=loaded_summary,
        selected_cases_summary=selected_cases_summary,
        shap_summary=shap_summary,
        evidence_summary=evidence_summary,
        artifact_summary=artifact_summary,
    )
