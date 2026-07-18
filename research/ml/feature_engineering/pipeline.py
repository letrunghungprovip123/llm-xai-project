"""Orchestration tuần tự cho stage feature engineering."""

from __future__ import annotations

from .feature_groups import (
    INTERIM_DIR,
    MANIFEST_DIR,
    REPORT_DIR,
    build_application_features,
    build_bureau_balance_features,
    build_bureau_features,
    build_credit_card_features,
    build_installments_features,
    build_pos_cash_features,
    build_previous_application_features,
    ensure_raw_files_exist,
    load_base_customers,
    run_feature_builder,
    write_batch_b_summary,
    write_feature_group_report,
)
from ..common.paths import create_directories


FEATURE_BUILDERS = [
    ("application_features", "application_features.parquet", build_application_features),
    ("bureau_features", "bureau_features.parquet", build_bureau_features),
    ("bureau_balance_features", "bureau_balance_features.parquet", build_bureau_balance_features),
    (
        "previous_application_features",
        "previous_application_features.parquet",
        build_previous_application_features,
    ),
    ("installments_features", "installments_features.parquet", build_installments_features),
    ("pos_cash_features", "pos_cash_features.parquet", build_pos_cash_features),
    ("credit_card_features", "credit_card_features.parquet", build_credit_card_features),
]


def run_feature_engineering() -> None:
    """Xây từng feature group rồi validate trước khi công bố manifest."""

    create_directories(INTERIM_DIR, REPORT_DIR, MANIFEST_DIR)

    print("=== Batch B: Feature Engineering Layer ===")
    print("This batch creates customer-level feature groups.")
    print("No preprocessing, model training, SHAP, or LLM explanation is performed.\n")

    ensure_raw_files_exist()
    base_customers = load_base_customers()
    expected_rows = len(base_customers)
    print(f"[Batch B] Base customers from application_train: {expected_rows}")

    stats_list = []
    for group_name, output_filename, builder in FEATURE_BUILDERS:
        stats = run_feature_builder(
            group_name=group_name,
            output_filename=output_filename,
            builder=builder,
            base_customers=base_customers,
            expected_rows=expected_rows,
        )
        stats_list.append(stats)

    write_feature_group_report(stats_list)
    write_batch_b_summary(stats_list)
    all_passed = all(stats["status"] == "passed" for stats in stats_list)
    print_summary(all_passed)


def print_summary(all_passed: bool) -> None:
    """In đúng summary lịch sử của Batch B."""

    print("\n=== Batch B completed ===")
    print("Produced files:")
    for output_path in [
        "data/interim/application_features.parquet",
        "data/interim/bureau_features.parquet",
        "data/interim/bureau_balance_features.parquet",
        "data/interim/previous_application_features.parquet",
        "data/interim/installments_features.parquet",
        "data/interim/pos_cash_features.parquet",
        "data/interim/credit_card_features.parquet",
        "data/reports/feature_group_build_report.md",
        "data/reports/batch_b_feature_engineering_summary.md",
        "data/manifests/batch_b_feature_engineering_summary.json",
    ]:
        print(f"- {output_path}")

    if all_passed:
        print("\nBatch B status: feature_engineering_layer_completed")
        print("Next: Batch C - Feature Matrix + Registry Layer")
    else:
        print("\nBatch B status: blocked")
        print("Check data/reports/feature_group_build_report.md for errors.")
