"""Orchestration tuần tự cho preprocessing train/valid/test."""

from __future__ import annotations

from .transforms import (
    ARTIFACT_DIR,
    LINEAR_DIR,
    MANIFEST_DIR,
    REGISTRY_DIR,
    REPORT_DIR,
    TREE_DIR,
    build_model_ready_dataset,
    ensure_inputs_exist,
    infer_feature_groups,
    load_feature_metadata,
    load_id_columns,
    load_model_feature_columns,
    load_split_data,
    load_target_column,
    save_artifacts_and_registries,
    save_model_ready_outputs,
    validate_model_ready_dataset,
    validate_raw_split_inputs,
    validate_y_splits,
    write_json,
    write_manifests_and_summary,
    write_preprocessing_report,
)
from ..common.paths import create_directories


def run_preprocessing() -> None:
    """Fit trên train, transform valid/test, validate rồi mới ghi artifacts."""

    create_directories(TREE_DIR, LINEAR_DIR, REPORT_DIR, MANIFEST_DIR, REGISTRY_DIR, ARTIFACT_DIR)

    print("=== Batch E: Preprocessing Layer ===")
    print("This batch fits preprocessing on train only and transforms valid/test.")
    print("It creates tree-ready and linear-ready model matrices.")
    print("No model training, SHAP, or LLM explanation is performed.\n")

    ensure_inputs_exist()
    model_feature_columns = load_model_feature_columns()
    id_columns = load_id_columns()
    target_column = load_target_column()
    feature_metadata = load_feature_metadata()
    train_x, train_y, valid_x, valid_y, test_x, test_y = load_split_data()

    input_validation = validate_raw_split_inputs(
        X_train=train_x,
        y_train=train_y,
        X_valid=valid_x,
        y_valid=valid_y,
        X_test=test_x,
        y_test=test_y,
        model_feature_columns=model_feature_columns,
        id_columns=id_columns,
        target_column=target_column,
        feature_metadata=feature_metadata,
    )
    target_validation = validate_y_splits(
        y_train=train_y,
        y_valid=valid_y,
        y_test=test_y,
        target_column=target_column,
    )
    if input_validation["status"] != "passed" or target_validation["status"] != "passed":
        write_json(input_validation, MANIFEST_DIR / "batch_e_input_validation_failed.json")
        write_json(target_validation, MANIFEST_DIR / "batch_e_target_validation_failed.json")
        raise RuntimeError("Batch E input/target validation failed.")

    train_model = train_x[model_feature_columns].copy()
    valid_model = valid_x[model_feature_columns].copy()
    test_model = test_x[model_feature_columns].copy()
    feature_groups = infer_feature_groups(
        X_train=train_model,
        model_feature_columns=model_feature_columns,
        feature_metadata=feature_metadata,
    )
    print_feature_group_summary(feature_groups)

    tree_outputs = build_model_ready_dataset(
        X_train=train_model,
        X_valid=valid_model,
        X_test=test_model,
        numeric_features=feature_groups["numeric_features"],
        categorical_features=feature_groups["categorical_features"],
        binary_features=feature_groups["binary_features"],
        feature_metadata=feature_metadata,
        pipeline_type="tree",
    )
    linear_outputs = build_model_ready_dataset(
        X_train=train_model,
        X_valid=valid_model,
        X_test=test_model,
        numeric_features=feature_groups["numeric_features"],
        categorical_features=feature_groups["categorical_features"],
        binary_features=feature_groups["binary_features"],
        feature_metadata=feature_metadata,
        pipeline_type="linear",
    )

    train_tree, valid_tree, test_tree, tree_artifact, tree_mapping = tree_outputs
    train_linear, valid_linear, test_linear, linear_artifact, linear_mapping = linear_outputs
    tree_validation = validate_model_ready_dataset(
        X_train_ready=train_tree,
        X_valid_ready=valid_tree,
        X_test_ready=test_tree,
        pipeline_type="tree",
    )
    linear_validation = validate_model_ready_dataset(
        X_train_ready=train_linear,
        X_valid_ready=valid_linear,
        X_test_ready=test_linear,
        pipeline_type="linear",
    )
    if tree_validation["status"] != "passed" or linear_validation["status"] != "passed":
        write_preprocessing_report(
            input_validation=input_validation,
            y_validation=target_validation,
            feature_groups=feature_groups,
            tree_validation=tree_validation,
            linear_validation=linear_validation,
            output_files={},
            artifact_files={},
        )
        raise RuntimeError("Batch E preprocessing validation failed. Check preprocessing_report.md")

    output_files = save_model_ready_outputs(
        X_train_tree=train_tree,
        X_valid_tree=valid_tree,
        X_test_tree=test_tree,
        X_train_linear=train_linear,
        X_valid_linear=valid_linear,
        X_test_linear=test_linear,
        y_train=train_y,
        y_valid=valid_y,
        y_test=test_y,
    )
    artifact_files = save_artifacts_and_registries(
        tree_artifact=tree_artifact,
        linear_artifact=linear_artifact,
        tree_mapping=tree_mapping,
        linear_mapping=linear_mapping,
    )
    write_preprocessing_report(
        input_validation=input_validation,
        y_validation=target_validation,
        feature_groups=feature_groups,
        tree_validation=tree_validation,
        linear_validation=linear_validation,
        output_files=output_files,
        artifact_files=artifact_files,
    )
    write_manifests_and_summary(
        input_validation=input_validation,
        y_validation=target_validation,
        feature_groups=feature_groups,
        tree_validation=tree_validation,
        linear_validation=linear_validation,
        output_files=output_files,
        artifact_files=artifact_files,
    )
    print_summary()


def print_feature_group_summary(feature_groups: dict[str, list[str]]) -> None:
    """In số lượng feature theo đúng thứ tự lịch sử."""

    print("[Batch E] Feature groups:")
    print(f"- Numeric: {len(feature_groups['numeric_features'])}")
    print(f"- Binary: {len(feature_groups['binary_features'])}")
    print(f"- Categorical: {len(feature_groups['categorical_features'])}")


def print_summary() -> None:
    """In đúng danh sách output lịch sử của Batch E."""

    print("\n=== Batch E completed ===")
    print("Produced files:")
    for output_path in [
        "data/processed/model_ready/tree/X_train_tree.parquet",
        "data/processed/model_ready/tree/X_valid_tree.parquet",
        "data/processed/model_ready/tree/X_test_tree.parquet",
        "data/processed/model_ready/tree/y_train.parquet",
        "data/processed/model_ready/tree/y_valid.parquet",
        "data/processed/model_ready/tree/y_test.parquet",
        "data/processed/model_ready/linear/X_train_linear.parquet",
        "data/processed/model_ready/linear/X_valid_linear.parquet",
        "data/processed/model_ready/linear/X_test_linear.parquet",
        "data/processed/model_ready/linear/y_train.parquet",
        "data/processed/model_ready/linear/y_valid.parquet",
        "data/processed/model_ready/linear/y_test.parquet",
        "artifacts/preprocessing/tree_preprocessor.joblib",
        "artifacts/preprocessing/linear_preprocessor.joblib",
        "ml/registry/preprocessed_feature_columns_tree.json",
        "ml/registry/preprocessed_feature_columns_linear.json",
        "ml/registry/preprocessed_feature_mapping_tree.json",
        "ml/registry/preprocessed_feature_mapping_linear.json",
        "data/reports/preprocessing_report.md",
        "data/reports/batch_e_preprocessing_summary.md",
        "data/manifests/preprocessing_manifest.json",
        "data/manifests/batch_e_preprocessing_summary.json",
    ]:
        print(f"- {output_path}")

    print("\nBatch E status: preprocessing_layer_completed")
    print("Next: Batch F - Model Training Layer")
