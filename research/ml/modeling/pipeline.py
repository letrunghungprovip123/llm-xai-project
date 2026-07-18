from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from .artifacts import (
    save_all_model_artifacts,
    to_jsonable,
)
from .config import (
    BATCH_NAME,
    BEST_MODEL_PATH,
    DEFAULT_THRESHOLD,
    MODEL_REGISTRY_PATH,
    MODEL_TRAINING_MANIFEST_PATH,
    MODEL_VERSION,
    RANDOM_STATE,
    SELECTION_PRIMARY_METRIC,
    SELECTION_SECONDARY_METRIC,
    SELECTION_TIEBREAKER_METRIC,
    ensure_output_dirs,
)
from .data_quality import (
    ModelReadyDatasets,
    QualityGateResult,
    load_model_ready_datasets,
    run_quality_gate,
    summarize_datasets,
)
from .evaluation import (
    EvaluationResult,
    evaluate_trained_models,
)
from .training import (
    TrainingResult,
    train_all_models,
)


# ============================================================
# Pipeline Result Container
# ============================================================

@dataclass(frozen=True)
class ModelLayerRunResult:
    """
    Result object for the full Batch F Model Training Layer run.

    This object is mostly useful when this runner is imported and called
    from another Python module.

    In normal usage, users run:
        python3 -m research.ml.modeling.main
    """

    status: str
    runtime_seconds: float
    dataset_summary: dict[str, Any]
    quality_result: QualityGateResult
    training_result: TrainingResult
    evaluation_result: EvaluationResult
    artifact_result: dict[str, Any]


# ============================================================
# Console Helpers
# ============================================================

def print_section(title: str) -> None:
    """
    Print a readable section header.
    """

    print()
    print("=" * 80)
    print(title)
    print("=" * 80)


def print_json(payload: dict[str, Any]) -> None:
    """
    Print a JSON-safe payload.
    """

    print(
        json.dumps(
            to_jsonable(payload),
            indent=2,
            ensure_ascii=False,
        )
    )


def print_quality_summary(quality_result: QualityGateResult) -> None:
    """
    Print quality gate result.
    """

    print(f"Quality gate status: {quality_result.status}")
    print(f"Check count: {len(quality_result.checks)}")
    print(f"Error count: {len(quality_result.errors)}")
    print(f"Warning count: {len(quality_result.warnings)}")

    if quality_result.errors:
        print()
        print("Quality gate errors:")
        for error in quality_result.errors:
            print(f"  - {error}")

    if quality_result.warnings:
        print()
        print("Quality gate warnings:")
        for warning in quality_result.warnings:
            print(f"  - {warning}")


def print_training_summary(training_result: TrainingResult) -> None:
    """
    Print training result summary.
    """

    print(f"Trained model count: {len(training_result.trained_models)}")
    print(f"Skipped model count: {len(training_result.skipped_models)}")
    print(f"Training error count: {len(training_result.errors)}")

    if training_result.trained_models:
        print()
        print("Trained models:")
        for trained_model in training_result.trained_models:
            print(
                f"  - {trained_model.model_name} "
                f"family={trained_model.model_family}, "
                f"branch={trained_model.dataset_branch}, "
                f"features={trained_model.feature_count}, "
                f"rows={trained_model.train_rows}, "
                f"training_seconds={trained_model.training_seconds:.2f}"
            )

    if training_result.skipped_models:
        print()
        print("Skipped models:")
        for skipped_model in training_result.skipped_models:
            print(f"  - {skipped_model}")

    if training_result.errors:
        print()
        print("Training errors:")
        for error in training_result.errors:
            print(f"  - {error}")


def print_evaluation_summary(evaluation_result: EvaluationResult) -> None:
    """
    Print concise metrics and best model result.
    """

    metrics_columns = [
        "model_name",
        "split",
        "roc_auc",
        "average_precision",
        "precision",
        "recall",
        "f1",
        "brier_score",
        "positive_prediction_rate",
    ]

    metrics_df = evaluation_result.metrics_df.copy()

    available_columns = [
        column
        for column in metrics_columns
        if column in metrics_df.columns
    ]

    print("Metrics summary:")
    print(metrics_df[available_columns].to_string(index=False))

    print()
    print("Best model:")
    print(f"  model_name: {evaluation_result.best_model.model_name}")
    print(f"  model_family: {evaluation_result.best_model.model_family}")
    print(f"  dataset_branch: {evaluation_result.best_model.dataset_branch}")
    print(f"  selection_primary_metric: {SELECTION_PRIMARY_METRIC}")
    print(
        "  best_valid_"
        f"{SELECTION_PRIMARY_METRIC}: "
        f"{evaluation_result.best_valid_evaluation.metrics[SELECTION_PRIMARY_METRIC]:.6f}"
    )
    print(
        "  best_valid_"
        f"{SELECTION_SECONDARY_METRIC}: "
        f"{evaluation_result.best_valid_evaluation.metrics[SELECTION_SECONDARY_METRIC]:.6f}"
    )
    print(
        "  best_valid_"
        f"{SELECTION_TIEBREAKER_METRIC}: "
        f"{evaluation_result.best_valid_evaluation.metrics[SELECTION_TIEBREAKER_METRIC]:.6f}"
    )

    print()
    print("Best model test metrics:")
    print_json(evaluation_result.best_test_evaluation.metrics)


def print_artifact_summary(artifact_result: dict[str, Any]) -> None:
    """
    Print saved artifact paths.
    """

    print("Artifact save result:")
    print_json(artifact_result)


# ============================================================
# Pipeline Validation Helpers
# ============================================================

def stop_if_quality_gate_failed(quality_result: QualityGateResult) -> None:

    if quality_result.status == "passed":
        return

    raise RuntimeError(
        "Model Layer stopped because quality gate failed. "
        "Fix data issues before training models."
    )


def stop_if_training_failed(training_result: TrainingResult) -> None:


    if training_result.errors:
        raise RuntimeError(
            "Model Layer stopped because at least one training error occurred. "
            f"Errors: {training_result.errors}"
        )

    if not training_result.trained_models:
        raise RuntimeError(
            "Model Layer stopped because no model was trained."
        )


# ============================================================
# Main Pipeline
# ============================================================

def run_model_training_layer() -> ModelLayerRunResult:


    pipeline_start = time.perf_counter()

    print_section(BATCH_NAME)
    print(f"Model version: {MODEL_VERSION}")
    print(f"Random state: {RANDOM_STATE}")
    print(f"Default threshold: {DEFAULT_THRESHOLD}")
    print(f"Selection primary metric: {SELECTION_PRIMARY_METRIC}")
    print(f"Selection secondary metric: {SELECTION_SECONDARY_METRIC}")
    print(f"Selection tiebreaker metric: {SELECTION_TIEBREAKER_METRIC}")

    print_section("Step 1 — Prepare Output Directories")
    ensure_output_dirs()
    print("Output directories are ready.")

    print_section("Step 2 — Load Model-Ready Datasets")
    datasets: ModelReadyDatasets = load_model_ready_datasets()
    dataset_summary = summarize_datasets(datasets)
    print_json(dataset_summary)

    print_section("Step 3 — Run Quality Gate")
    quality_result = run_quality_gate(datasets)
    print_quality_summary(quality_result)
    stop_if_quality_gate_failed(quality_result)

    print_section("Step 4 — Train Models")
    training_result = train_all_models(datasets)
    print_training_summary(training_result)
    stop_if_training_failed(training_result)

    print_section("Step 5 — Evaluate Models")
    evaluation_result = evaluate_trained_models(
        trained_models=training_result.trained_models,
        datasets=datasets,
    )
    print_evaluation_summary(evaluation_result)

    print_section("Step 6 — Save Artifacts")
    artifact_result = save_all_model_artifacts(
        training_result=training_result,
        evaluation_result=evaluation_result,
        quality_result=quality_result,
    )
    print_artifact_summary(artifact_result)

    runtime_seconds = time.perf_counter() - pipeline_start

    print_section("Batch F Completed")
    print("Status: PASSED")
    print(f"Runtime seconds: {runtime_seconds:.2f}")
    print(f"Best model: {evaluation_result.best_model.model_name}")
    print(f"Best model artifact: {BEST_MODEL_PATH}")
    print(f"Model registry: {MODEL_REGISTRY_PATH}")
    print(f"Training manifest: {MODEL_TRAINING_MANIFEST_PATH}")
    print()
    print("Next layer: Batch G — XAI Evidence Layer")

    return ModelLayerRunResult(
        status="passed",
        runtime_seconds=runtime_seconds,
        dataset_summary=dataset_summary,
        quality_result=quality_result,
        training_result=training_result,
        evaluation_result=evaluation_result,
        artifact_result=artifact_result,
    )
