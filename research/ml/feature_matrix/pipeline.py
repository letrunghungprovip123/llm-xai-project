"""Orchestration tuần tự cho feature matrix và registry."""

from __future__ import annotations

from .matrix_registry import (
    CONCEPT_REGISTRY,
    MANIFEST_DIR,
    PROCESSED_DIR,
    REGISTRY_DIR,
    REPORT_DIR,
    build_feature_registry,
    build_unified_feature_matrix,
    ensure_inputs_exist,
    registry_to_dataframe,
    replace_inf_with_nan,
    save_yaml,
    validate_feature_registry,
    validate_final_matrix,
    validate_target,
    write_batch_c_summary,
    write_feature_matrix_registry_report,
)
from ..common.paths import create_directories


def run_feature_matrix() -> None:
    """Merge feature groups, tạo registry, rồi validate toàn bộ output."""

    create_directories(PROCESSED_DIR, REPORT_DIR, MANIFEST_DIR, REGISTRY_DIR)

    print("=== Batch C: Feature Matrix + Registry Layer ===")
    print("This batch merges Batch B feature groups into one official feature matrix.")
    print("It also separates TARGET and builds concept/feature registries.")
    print("No split, preprocessing, model training, SHAP, or LLM explanation is performed.\n")

    ensure_inputs_exist()
    matrix, target, group_stats = build_unified_feature_matrix()
    matrix = replace_inf_with_nan(matrix)
    target = replace_inf_with_nan(target)

    print("[Batch C] Saving feature_matrix_full.parquet ...")
    matrix.to_parquet(PROCESSED_DIR / "feature_matrix_full.parquet", index=False)
    print("[Batch C] Saving target_full.parquet ...")
    target.to_parquet(PROCESSED_DIR / "target_full.parquet", index=False)

    print("[Batch C] Building concept registry ...")
    save_yaml(CONCEPT_REGISTRY, REGISTRY_DIR / "concept_registry.yaml")
    print("[Batch C] Building feature registry ...")
    feature_registry = build_feature_registry(matrix)
    save_yaml(feature_registry, REGISTRY_DIR / "feature_registry.yaml")
    registry_frame = registry_to_dataframe(feature_registry)
    registry_frame.to_csv(REGISTRY_DIR / "feature_registry.csv", index=False)

    print("[Batch C] Validating final matrix ...")
    final_matrix_stats = validate_final_matrix(matrix, expected_rows=len(target))
    print("[Batch C] Validating target ...")
    target_stats = validate_target(target)
    print("[Batch C] Validating registries ...")
    registry_stats = validate_feature_registry(
        matrix=matrix,
        concept_registry=CONCEPT_REGISTRY,
        feature_registry=feature_registry,
    )

    write_feature_matrix_registry_report(
        group_stats=group_stats,
        final_matrix_stats=final_matrix_stats,
        target_stats=target_stats,
        registry_stats=registry_stats,
    )
    write_batch_c_summary(
        final_matrix_stats=final_matrix_stats,
        target_stats=target_stats,
        registry_stats=registry_stats,
        group_stats=group_stats,
    )

    all_passed = (
        final_matrix_stats["status"] == "passed"
        and target_stats["status"] == "passed"
        and registry_stats["status"] == "passed"
        and all(stats["status"] == "merged" for stats in group_stats)
    )
    print_summary(all_passed)


def print_summary(all_passed: bool) -> None:
    """In đúng summary lịch sử của Batch C."""

    print("\n=== Batch C completed ===")
    print("Produced files:")
    for output_path in [
        "data/processed/feature_matrix_full.parquet",
        "data/processed/target_full.parquet",
        "ml/registry/concept_registry.yaml",
        "ml/registry/feature_registry.yaml",
        "ml/registry/feature_registry.csv",
        "data/reports/feature_matrix_registry_report.md",
        "data/reports/batch_c_feature_matrix_registry_summary.md",
        "data/manifests/batch_c_feature_matrix_registry_summary.json",
    ]:
        print(f"- {output_path}")

    if all_passed:
        print("\nBatch C status: feature_matrix_registry_layer_completed")
        print("Next: Batch D - Leakage + Split Layer")
    else:
        print("\nBatch C status: blocked")
        print("Check data/reports/feature_matrix_registry_report.md for errors.")
