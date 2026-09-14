"""Orchestration tuần tự cho leakage audit và data split."""

from __future__ import annotations

from .splitter import (
    MANIFEST_DIR,
    REGISTRY_DIR,
    REPORT_DIR,
    SPLIT_DIR,
    build_model_feature_metadata,
    ensure_inputs_exist,
    load_batch_c_outputs,
    make_stratified_split,
    run_leakage_audit,
    save_model_feature_metadata,
    save_split_outputs,
    write_batch_d_summary,
    write_leakage_audit_report,
    write_split_manifest,
    write_split_report,
)
from ..common.paths import create_directories


def run_data_split() -> None:
    """Audit leakage trước, sau đó split và chỉ ghi output khi validation pass."""

    create_directories(SPLIT_DIR, REPORT_DIR, MANIFEST_DIR, REGISTRY_DIR)

    print("=== Batch D: Leakage + Split Layer ===")
    print("This batch performs leakage audit and stratified train/valid/test split.")
    print("No preprocessing, encoding, scaling, or model training is performed.\n")

    ensure_inputs_exist()
    features, target, registry = load_batch_c_outputs()
    feature_metadata = build_model_feature_metadata(X=features, registry_df=registry)
    feature_metadata_files = save_model_feature_metadata(feature_metadata)

    leakage_stats = run_leakage_audit(X=features, y=target, registry_df=registry)
    if leakage_stats["status"] != "passed":
        write_leakage_audit_report(leakage_stats)
        raise RuntimeError(
            "Leakage audit blocked Batch D. Check data/reports/leakage_audit_report.md"
        )

    train_x, train_y, valid_x, valid_y, test_x, test_y, split_stats = make_stratified_split(
        X=features,
        y=target,
    )
    if split_stats["status"] != "passed":
        raise RuntimeError("Split validation failed before saving outputs.")

    split_files = save_split_outputs(
        X_train=train_x,
        y_train=train_y,
        X_valid=valid_x,
        y_valid=valid_y,
        X_test=test_x,
        y_test=test_y,
    )
    output_files = {**split_files, **feature_metadata_files}

    write_leakage_audit_report(leakage_stats)
    write_split_report(split_stats, output_files)
    write_split_manifest(
        split_stats=split_stats,
        leakage_stats=leakage_stats,
        output_files=output_files,
        model_feature_metadata=feature_metadata,
    )
    write_batch_d_summary(
        leakage_stats=leakage_stats,
        split_stats=split_stats,
        output_files=output_files,
        model_feature_metadata=feature_metadata,
    )
    print_summary()


def print_summary() -> None:
    """In đúng danh sách output lịch sử của Batch D."""

    print("\n=== Batch D completed ===")
    print("Produced files:")
    for output_path in [
        "data/processed/splits/X_train.parquet",
        "data/processed/splits/y_train.parquet",
        "data/processed/splits/X_valid.parquet",
        "data/processed/splits/y_valid.parquet",
        "data/processed/splits/X_test.parquet",
        "data/processed/splits/y_test.parquet",
        "ml/registry/model_feature_columns.json",
        "ml/registry/id_columns.json",
        "ml/registry/target_column.json",
        "ml/registry/model_feature_metadata.json",
        "data/reports/leakage_audit_report.md",
        "data/reports/split_report.md",
        "data/reports/batch_d_leakage_split_summary.md",
        "data/manifests/split_manifest.json",
        "data/manifests/batch_d_leakage_split_summary.json",
    ]:
        print(f"- {output_path}")

    print("\nBatch D status: leakage_split_layer_completed")
    print("Next: Batch E - Preprocessing Layer")
