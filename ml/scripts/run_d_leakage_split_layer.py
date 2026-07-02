from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split


PROJECT_ROOT = Path(__file__).resolve().parents[2]

PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
SPLIT_DIR = PROCESSED_DIR / "splits"
REPORT_DIR = PROJECT_ROOT / "data" / "reports"
MANIFEST_DIR = PROJECT_ROOT / "data" / "manifests"
REGISTRY_DIR = PROJECT_ROOT / "ml" / "registry"

SPLIT_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)
MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
REGISTRY_DIR.mkdir(parents=True, exist_ok=True)

FEATURE_MATRIX_PATH = PROCESSED_DIR / "feature_matrix_full.parquet"
TARGET_PATH = PROCESSED_DIR / "target_full.parquet"
FEATURE_REGISTRY_CSV_PATH = REGISTRY_DIR / "feature_registry.csv"

MODEL_FEATURE_COLUMNS_PATH = REGISTRY_DIR / "model_feature_columns.json"
ID_COLUMNS_PATH = REGISTRY_DIR / "id_columns.json"
TARGET_COLUMN_PATH = REGISTRY_DIR / "target_column.json"
MODEL_FEATURE_METADATA_PATH = REGISTRY_DIR / "model_feature_metadata.json"

RANDOM_STATE = 42

TRAIN_RATIO = 0.70
VALID_RATIO = 0.15
TEST_RATIO = 0.15

ID_COLUMNS = ["SK_ID_CURR"]
TARGET_COLUMN = "TARGET"

FORBIDDEN_IN_X = {
    "TARGET",
    "SK_ID_BUREAU",
    "SK_ID_PREV",
}

SUSPICIOUS_NAME_KEYWORDS = [
    "target",
    "label",
    "default",
    "prediction",
    "predicted",
    "probability",
    "proba",
    "score_model",
    "post_event",
    "future",
    "after_target",
]

CORRELATION_WARNING_THRESHOLD = 0.80
TARGET_RATE_GAP_WARNING_THRESHOLD = 0.01


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def relative(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT))


def ensure_inputs_exist() -> None:
    missing = []

    required_files = [
        FEATURE_MATRIX_PATH,
        TARGET_PATH,
    ]

    for path in required_files:
        if not path.exists():
            missing.append(relative(path))

    if missing:
        raise FileNotFoundError(f"Missing required Batch D input files: {missing}")


def count_inf(df: pd.DataFrame) -> int:
    numeric_df = df.select_dtypes(include=[np.number])

    if numeric_df.empty:
        return 0

    return int(np.isinf(numeric_df.to_numpy()).sum())


def load_batch_c_outputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame | None]:
    print("[Batch D] Loading feature matrix ...")
    X = pd.read_parquet(FEATURE_MATRIX_PATH)

    print("[Batch D] Loading target ...")
    y = pd.read_parquet(TARGET_PATH)

    registry_df = None

    if FEATURE_REGISTRY_CSV_PATH.exists():
        print("[Batch D] Loading feature registry ...")
        registry_df = pd.read_csv(FEATURE_REGISTRY_CSV_PATH)
    else:
        print("[Batch D] feature_registry.csv not found. Registry checks will be limited.")

    return X, y, registry_df


def validate_x_y_alignment(X: pd.DataFrame, y: pd.DataFrame) -> dict[str, Any]:
    errors = []

    if "SK_ID_CURR" not in X.columns:
        errors.append("X is missing SK_ID_CURR")

    if "SK_ID_CURR" not in y.columns:
        errors.append("y is missing SK_ID_CURR")

    if "TARGET" not in y.columns:
        errors.append("y is missing TARGET")

    if errors:
        return {
            "status": "blocked",
            "errors": errors,
        }

    x_rows = len(X)
    y_rows = len(y)

    x_duplicate = int(X["SK_ID_CURR"].duplicated().sum())
    y_duplicate = int(y["SK_ID_CURR"].duplicated().sum())

    if x_rows != y_rows:
        errors.append(f"row count mismatch: X={x_rows}, y={y_rows}")

    if x_duplicate > 0:
        errors.append(f"duplicate SK_ID_CURR in X: {x_duplicate}")

    if y_duplicate > 0:
        errors.append(f"duplicate SK_ID_CURR in y: {y_duplicate}")

    x_ids = set(X["SK_ID_CURR"].tolist())
    y_ids = set(y["SK_ID_CURR"].tolist())

    missing_y_for_x = len(x_ids - y_ids)
    missing_x_for_y = len(y_ids - x_ids)

    if missing_y_for_x > 0:
        errors.append(f"IDs in X but not in y: {missing_y_for_x}")

    if missing_x_for_y > 0:
        errors.append(f"IDs in y but not in X: {missing_x_for_y}")

    aligned = X[["SK_ID_CURR"]].merge(
        y[["SK_ID_CURR", "TARGET"]],
        on="SK_ID_CURR",
        how="left",
    )

    missing_target_after_merge = int(aligned["TARGET"].isna().sum())

    if missing_target_after_merge > 0:
        errors.append(f"missing TARGET after X/y alignment: {missing_target_after_merge}")

    target_values = sorted(y["TARGET"].dropna().unique().tolist())

    if not set(target_values).issubset({0, 1}):
        errors.append(f"unexpected TARGET values: {target_values}")

    return {
        "x_rows": int(x_rows),
        "y_rows": int(y_rows),
        "x_duplicate_sk_id_curr": x_duplicate,
        "y_duplicate_sk_id_curr": y_duplicate,
        "missing_y_for_x": int(missing_y_for_x),
        "missing_x_for_y": int(missing_x_for_y),
        "missing_target_after_merge": missing_target_after_merge,
        "target_values": target_values,
        "target_positive_count": int((y["TARGET"] == 1).sum()),
        "target_negative_count": int((y["TARGET"] == 0).sum()),
        "target_positive_rate": float((y["TARGET"] == 1).mean()),
        "status": "passed" if not errors else "blocked",
        "errors": errors,
    }


def check_target_and_id_leakage(X: pd.DataFrame) -> dict[str, Any]:
    errors = []
    warnings = []

    forbidden_found = sorted([c for c in FORBIDDEN_IN_X if c in X.columns])

    if forbidden_found:
        errors.append(f"forbidden columns found in X: {forbidden_found}")

    inf_count = count_inf(X)

    if inf_count > 0:
        errors.append(f"inf/-inf values found in X: {inf_count}")

    suspicious_name_features = []

    for col in X.columns:
        lower = col.lower()

        if col == "SK_ID_CURR":
            continue

        matched_keywords = [
            keyword for keyword in SUSPICIOUS_NAME_KEYWORDS
            if keyword in lower
        ]

        if matched_keywords:
            suspicious_name_features.append(
                {
                    "feature": col,
                    "matched_keywords": matched_keywords,
                }
            )

    if suspicious_name_features:
        warnings.append(
            f"suspicious feature names found: {len(suspicious_name_features)}"
        )

    return {
        "forbidden_columns_found": forbidden_found,
        "inf_count": int(inf_count),
        "suspicious_name_feature_count": len(suspicious_name_features),
        "suspicious_name_features": suspicious_name_features[:100],
        "status": "passed" if not errors else "blocked",
        "warnings": warnings,
        "errors": errors,
    }


def check_registry_consistency(
    X: pd.DataFrame,
    registry_df: pd.DataFrame | None,
) -> dict[str, Any]:
    errors = []
    warnings = []

    feature_columns = [
        c for c in X.columns
        if c not in ID_COLUMNS
    ]

    if registry_df is None:
        warnings.append("feature_registry.csv not found; registry consistency check skipped")
        return {
            "feature_count": len(feature_columns),
            "registry_entry_count": None,
            "missing_registry_entry_count": None,
            "extra_registry_entry_count": None,
            "unknown_concept_count": None,
            "allowed_for_model_false_count": None,
            "sensitive_feature_count": None,
            "explanation_limited_feature_count": None,
            "status": "warning",
            "warnings": warnings,
            "errors": errors,
        }

    if "feature_name" not in registry_df.columns:
        errors.append("feature_registry.csv missing feature_name column")
        return {
            "status": "blocked",
            "warnings": warnings,
            "errors": errors,
        }

    registry_features = set(registry_df["feature_name"].astype(str).tolist())
    matrix_features = set(feature_columns)

    missing_registry_entries = sorted(list(matrix_features - registry_features))
    extra_registry_entries = sorted(list(registry_features - matrix_features))

    if missing_registry_entries:
        errors.append(f"missing registry entries: {len(missing_registry_entries)}")

    if extra_registry_entries:
        warnings.append(f"extra registry entries not in matrix: {len(extra_registry_entries)}")

    unknown_concept_count = None
    if "concept" in registry_df.columns:
        unknown_concept_count = int((registry_df["concept"] == "unknown_feature_group").sum())
        if unknown_concept_count > 0:
            warnings.append(f"features mapped to unknown_feature_group: {unknown_concept_count}")

    allowed_for_model_false_count = None
    if "allowed_for_model" in registry_df.columns:
        allowed_for_model_false_count = int(
            registry_df["allowed_for_model"].astype(str).str.lower().isin(["false", "0"]).sum()
        )
        if allowed_for_model_false_count > 0:
            warnings.append(f"features marked allowed_for_model=False: {allowed_for_model_false_count}")

    sensitive_feature_count = None
    if "sensitive" in registry_df.columns:
        sensitive_feature_count = int(
            registry_df["sensitive"].astype(str).str.lower().isin(["true", "1"]).sum()
        )

    explanation_limited_count = None
    if "allowed_in_user_explanation" in registry_df.columns:
        explanation_limited_count = int(
            (registry_df["allowed_in_user_explanation"].astype(str).str.lower() == "limited").sum()
        )

    return {
        "feature_count": len(feature_columns),
        "registry_entry_count": int(len(registry_df)),
        "missing_registry_entry_count": len(missing_registry_entries),
        "missing_registry_entries": missing_registry_entries[:100],
        "extra_registry_entry_count": len(extra_registry_entries),
        "extra_registry_entries": extra_registry_entries[:100],
        "unknown_concept_count": unknown_concept_count,
        "allowed_for_model_false_count": allowed_for_model_false_count,
        "sensitive_feature_count": sensitive_feature_count,
        "explanation_limited_feature_count": explanation_limited_count,
        "status": "passed" if not errors else "blocked",
        "warnings": warnings,
        "errors": errors,
    }


def check_numeric_correlation_warnings(
    X: pd.DataFrame,
    y: pd.DataFrame,
) -> dict[str, Any]:
    warnings = []

    merged = X.merge(
        y[["SK_ID_CURR", "TARGET"]],
        on="SK_ID_CURR",
        how="inner",
    )

    feature_columns = [
        c for c in X.columns
        if c not in ID_COLUMNS
    ]

    numeric_features = [
        c for c in feature_columns
        if pd.api.types.is_numeric_dtype(merged[c])
    ]

    suspicious_correlations = []
    top_correlations = []

    for col in numeric_features:
        series = merged[col]

        if series.nunique(dropna=True) <= 1:
            continue

        try:
            corr = series.corr(merged["TARGET"])
        except Exception:
            continue

        if pd.isna(corr):
            continue

        abs_corr = abs(float(corr))

        item = {
            "feature": col,
            "correlation_with_target": float(corr),
            "abs_correlation": abs_corr,
        }

        top_correlations.append(item)

        if abs_corr >= CORRELATION_WARNING_THRESHOLD:
            suspicious_correlations.append(item)

    suspicious_correlations = sorted(
        suspicious_correlations,
        key=lambda x: x["abs_correlation"],
        reverse=True,
    )

    top_correlations = sorted(
        top_correlations,
        key=lambda x: x["abs_correlation"],
        reverse=True,
    )[:30]

    if suspicious_correlations:
        warnings.append(
            f"features with abs(correlation with TARGET) >= {CORRELATION_WARNING_THRESHOLD}: "
            f"{len(suspicious_correlations)}"
        )

    return {
        "numeric_feature_count_checked": len(numeric_features),
        "correlation_warning_threshold": CORRELATION_WARNING_THRESHOLD,
        "suspicious_correlation_count": len(suspicious_correlations),
        "suspicious_correlations": suspicious_correlations[:50],
        "top_correlations": top_correlations,
        "status": "passed",
        "warnings": warnings,
        "errors": [],
    }


def run_leakage_audit(
    X: pd.DataFrame,
    y: pd.DataFrame,
    registry_df: pd.DataFrame | None,
) -> dict[str, Any]:
    print("[Batch D] Running X/y alignment check ...")
    alignment = validate_x_y_alignment(X, y)

    print("[Batch D] Running target/ID leakage check ...")
    target_id_leakage = check_target_and_id_leakage(X)

    print("[Batch D] Running registry consistency check ...")
    registry_consistency = check_registry_consistency(X, registry_df)

    print("[Batch D] Running numeric correlation warning check ...")
    correlation = check_numeric_correlation_warnings(X, y)

    errors = []
    warnings = []

    for section in [
        alignment,
        target_id_leakage,
        registry_consistency,
        correlation,
    ]:
        errors.extend(section.get("errors", []))
        warnings.extend(section.get("warnings", []))

    status = "passed" if not errors else "blocked"

    return {
        "created_at": now_iso(),
        "alignment": alignment,
        "target_id_leakage": target_id_leakage,
        "registry_consistency": registry_consistency,
        "correlation_warning_check": correlation,
        "warning_count": len(warnings),
        "warnings": warnings,
        "error_count": len(errors),
        "errors": errors,
        "status": status,
    }


def build_model_feature_metadata(
    X: pd.DataFrame,
    registry_df: pd.DataFrame | None,
) -> dict[str, Any]:
    feature_columns = [
        c for c in X.columns
        if c not in ID_COLUMNS and c not in FORBIDDEN_IN_X
    ]

    excluded_columns = [
        c for c in X.columns
        if c in ID_COLUMNS or c in FORBIDDEN_IN_X
    ]

    allowed_for_model_false_excluded = []

    if (
        registry_df is not None
        and "feature_name" in registry_df.columns
        and "allowed_for_model" in registry_df.columns
    ):
        blocked = registry_df[
            registry_df["allowed_for_model"].astype(str).str.lower().isin(["false", "0"])
        ]["feature_name"].astype(str).tolist()

        allowed_for_model_false_excluded = sorted(
            [c for c in blocked if c in feature_columns]
        )

        feature_columns = [
            c for c in feature_columns
            if c not in allowed_for_model_false_excluded
        ]

        excluded_columns.extend(allowed_for_model_false_excluded)

    metadata = {
        "created_at": now_iso(),
        "id_columns": ID_COLUMNS,
        "target_column": TARGET_COLUMN,
        "model_feature_columns": feature_columns,
        "model_feature_count": len(feature_columns),
        "excluded_columns": sorted(set(excluded_columns)),
        "allowed_for_model_false_excluded": allowed_for_model_false_excluded,
        "note": (
            "X_train/X_valid/X_test keep SK_ID_CURR for traceability, "
            "but Batch E/F must use model_feature_columns.json for actual model inputs."
        ),
    }

    return metadata


def save_model_feature_metadata(metadata: dict[str, Any]) -> dict[str, str]:
    MODEL_FEATURE_COLUMNS_PATH.write_text(
        json.dumps(metadata["model_feature_columns"], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    ID_COLUMNS_PATH.write_text(
        json.dumps(metadata["id_columns"], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    TARGET_COLUMN_PATH.write_text(
        json.dumps(metadata["target_column"], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    MODEL_FEATURE_METADATA_PATH.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return {
        "model_feature_columns": relative(MODEL_FEATURE_COLUMNS_PATH),
        "id_columns": relative(ID_COLUMNS_PATH),
        "target_column": relative(TARGET_COLUMN_PATH),
        "model_feature_metadata": relative(MODEL_FEATURE_METADATA_PATH),
    }


def make_stratified_split(
    X: pd.DataFrame,
    y: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    print("[Batch D] Creating aligned X/y dataframe ...")

    y_small = y[["SK_ID_CURR", "TARGET"]].copy()

    full = X.merge(y_small, on="SK_ID_CURR", how="inner")

    if len(full) != len(X):
        raise ValueError(f"X/y merge changed row count: X={len(X)}, merged={len(full)}")

    if full["TARGET"].nunique(dropna=True) < 2:
        raise ValueError("TARGET has fewer than 2 classes. Stratified split cannot run.")

    train_df, temp_df = train_test_split(
        full,
        test_size=(VALID_RATIO + TEST_RATIO),
        random_state=RANDOM_STATE,
        stratify=full["TARGET"],
    )

    valid_relative_size = VALID_RATIO / (VALID_RATIO + TEST_RATIO)

    valid_df, test_df = train_test_split(
        temp_df,
        test_size=(1.0 - valid_relative_size),
        random_state=RANDOM_STATE,
        stratify=temp_df["TARGET"],
    )

    X_train = train_df.drop(columns=["TARGET"]).reset_index(drop=True)
    y_train = train_df[["SK_ID_CURR", "TARGET"]].reset_index(drop=True)

    X_valid = valid_df.drop(columns=["TARGET"]).reset_index(drop=True)
    y_valid = valid_df[["SK_ID_CURR", "TARGET"]].reset_index(drop=True)

    X_test = test_df.drop(columns=["TARGET"]).reset_index(drop=True)
    y_test = test_df[["SK_ID_CURR", "TARGET"]].reset_index(drop=True)

    split_stats = build_split_stats(
        X_train=X_train,
        y_train=y_train,
        X_valid=X_valid,
        y_valid=y_valid,
        X_test=X_test,
        y_test=y_test,
        full_positive_rate=float(full["TARGET"].mean()),
        full_rows=len(full),
    )

    return X_train, y_train, X_valid, y_valid, X_test, y_test, split_stats


def build_split_stats(
    X_train: pd.DataFrame,
    y_train: pd.DataFrame,
    X_valid: pd.DataFrame,
    y_valid: pd.DataFrame,
    X_test: pd.DataFrame,
    y_test: pd.DataFrame,
    full_positive_rate: float,
    full_rows: int,
) -> dict[str, Any]:
    train_ids = set(X_train["SK_ID_CURR"].tolist())
    valid_ids = set(X_valid["SK_ID_CURR"].tolist())
    test_ids = set(X_test["SK_ID_CURR"].tolist())

    train_valid_overlap = len(train_ids & valid_ids)
    train_test_overlap = len(train_ids & test_ids)
    valid_test_overlap = len(valid_ids & test_ids)

    split_parts = {
        "train": y_train,
        "valid": y_valid,
        "test": y_test,
    }

    split_summary = {}

    warnings = []
    errors = []

    row_total = len(y_train) + len(y_valid) + len(y_test)

    if row_total != full_rows:
        errors.append(f"split row total mismatch: full={full_rows}, split_total={row_total}")

    for name, y_part in split_parts.items():
        positive_count = int((y_part["TARGET"] == 1).sum())
        negative_count = int((y_part["TARGET"] == 0).sum())
        positive_rate = float((y_part["TARGET"] == 1).mean())
        target_rate_gap = abs(positive_rate - full_positive_rate)

        if target_rate_gap > TARGET_RATE_GAP_WARNING_THRESHOLD:
            warnings.append(
                f"{name} target rate gap from full dataset is high: {target_rate_gap:.6f}"
            )

        split_summary[name] = {
            "rows": int(len(y_part)),
            "positive_count": positive_count,
            "negative_count": negative_count,
            "positive_rate": positive_rate,
            "target_rate_gap_from_full": target_rate_gap,
        }

    if train_valid_overlap > 0:
        errors.append(f"train/valid ID overlap: {train_valid_overlap}")

    if train_test_overlap > 0:
        errors.append(f"train/test ID overlap: {train_test_overlap}")

    if valid_test_overlap > 0:
        errors.append(f"valid/test ID overlap: {valid_test_overlap}")

    return {
        "split_strategy": "stratified_by_TARGET",
        "split_unit": "SK_ID_CURR",
        "random_state": RANDOM_STATE,
        "ratios": {
            "train": TRAIN_RATIO,
            "valid": VALID_RATIO,
            "test": TEST_RATIO,
        },
        "full_rows": int(full_rows),
        "split_row_total": int(row_total),
        "full_positive_rate": full_positive_rate,
        "splits": split_summary,
        "id_overlap_check": {
            "train_valid_overlap": train_valid_overlap,
            "train_test_overlap": train_test_overlap,
            "valid_test_overlap": valid_test_overlap,
        },
        "warning_count": len(warnings),
        "warnings": warnings,
        "error_count": len(errors),
        "errors": errors,
        "status": "passed" if not errors else "blocked",
    }


def save_split_outputs(
    X_train: pd.DataFrame,
    y_train: pd.DataFrame,
    X_valid: pd.DataFrame,
    y_valid: pd.DataFrame,
    X_test: pd.DataFrame,
    y_test: pd.DataFrame,
) -> dict[str, str]:
    outputs = {
        "X_train": SPLIT_DIR / "X_train.parquet",
        "y_train": SPLIT_DIR / "y_train.parquet",
        "X_valid": SPLIT_DIR / "X_valid.parquet",
        "y_valid": SPLIT_DIR / "y_valid.parquet",
        "X_test": SPLIT_DIR / "X_test.parquet",
        "y_test": SPLIT_DIR / "y_test.parquet",
    }

    print("[Batch D] Saving split parquet files ...")

    X_train.to_parquet(outputs["X_train"], index=False)
    y_train.to_parquet(outputs["y_train"], index=False)

    X_valid.to_parquet(outputs["X_valid"], index=False)
    y_valid.to_parquet(outputs["y_valid"], index=False)

    X_test.to_parquet(outputs["X_test"], index=False)
    y_test.to_parquet(outputs["y_test"], index=False)

    return {
        name: relative(path)
        for name, path in outputs.items()
    }


def write_leakage_audit_report(leakage_stats: dict[str, Any]) -> None:
    path = REPORT_DIR / "leakage_audit_report.md"

    md = []

    md.append("# Leakage Audit Report\n")
    md.append(f"Created at: `{now_iso()}`\n")

    md.append("## Overall Status\n")
    md.append(f"- Status: `{leakage_stats['status']}`")
    md.append(f"- Error count: `{leakage_stats['error_count']}`")
    md.append(f"- Warning count: `{leakage_stats['warning_count']}`\n")

    alignment = leakage_stats["alignment"]
    md.append("## X/y Alignment Check\n")
    md.append(f"- X rows: `{alignment.get('x_rows')}`")
    md.append(f"- y rows: `{alignment.get('y_rows')}`")
    md.append(f"- Duplicate SK_ID_CURR in X: `{alignment.get('x_duplicate_sk_id_curr')}`")
    md.append(f"- Duplicate SK_ID_CURR in y: `{alignment.get('y_duplicate_sk_id_curr')}`")
    md.append(f"- IDs in X but not y: `{alignment.get('missing_y_for_x')}`")
    md.append(f"- IDs in y but not X: `{alignment.get('missing_x_for_y')}`")
    md.append(f"- Missing TARGET after merge: `{alignment.get('missing_target_after_merge')}`")
    md.append(f"- TARGET values: `{alignment.get('target_values')}`")
    md.append(f"- TARGET positive rate: `{alignment.get('target_positive_rate')}`")
    md.append(f"- Status: `{alignment.get('status')}`\n")

    target_id = leakage_stats["target_id_leakage"]
    md.append("## Target and ID Leakage Check\n")
    md.append(f"- Forbidden columns found: `{target_id['forbidden_columns_found']}`")
    md.append(f"- Inf/-inf count: `{target_id['inf_count']}`")
    md.append(f"- Suspicious name feature count: `{target_id['suspicious_name_feature_count']}`")
    md.append(f"- Status: `{target_id['status']}`\n")

    if target_id["suspicious_name_features"]:
        md.append("### Suspicious Feature Name Examples\n")
        for item in target_id["suspicious_name_features"][:30]:
            md.append(f"- `{item['feature']}` matched `{item['matched_keywords']}`")
        md.append("")

    registry = leakage_stats["registry_consistency"]
    md.append("## Registry Consistency Check\n")
    md.append(f"- Feature count in matrix: `{registry.get('feature_count')}`")
    md.append(f"- Registry entry count: `{registry.get('registry_entry_count')}`")
    md.append(f"- Missing registry entries: `{registry.get('missing_registry_entry_count')}`")
    md.append(f"- Extra registry entries: `{registry.get('extra_registry_entry_count')}`")
    md.append(f"- Unknown concept count: `{registry.get('unknown_concept_count')}`")
    md.append(f"- allowed_for_model=False count: `{registry.get('allowed_for_model_false_count')}`")
    md.append(f"- Sensitive feature count: `{registry.get('sensitive_feature_count')}`")
    md.append(f"- Explanation-limited feature count: `{registry.get('explanation_limited_feature_count')}`")
    md.append(f"- Status: `{registry.get('status')}`\n")

    corr = leakage_stats["correlation_warning_check"]
    md.append("## Correlation Warning Check\n")
    md.append(f"- Numeric features checked: `{corr['numeric_feature_count_checked']}`")
    md.append(f"- Warning threshold: `abs(correlation) >= {corr['correlation_warning_threshold']}`")
    md.append(f"- Suspicious correlation count: `{corr['suspicious_correlation_count']}`")
    md.append(f"- Status: `{corr['status']}`\n")

    md.append("### Top Numeric Correlations with TARGET\n")
    md.append("| Feature | Correlation | Abs correlation |")
    md.append("|---|---:|---:|")
    for item in corr["top_correlations"][:30]:
        md.append(
            f"| `{item['feature']}` | `{item['correlation_with_target']:.6f}` | "
            f"`{item['abs_correlation']:.6f}` |"
        )

    if leakage_stats["warnings"]:
        md.append("\n## Warnings\n")
        for warning in leakage_stats["warnings"]:
            md.append(f"- {warning}")

    if leakage_stats["errors"]:
        md.append("\n## Blocking Errors\n")
        for error in leakage_stats["errors"]:
            md.append(f"- {error}")

    path.write_text("\n".join(md), encoding="utf-8")


def write_split_report(split_stats: dict[str, Any], output_files: dict[str, str]) -> None:
    path = REPORT_DIR / "split_report.md"

    md = []

    md.append("# Split Report\n")
    md.append(f"Created at: `{now_iso()}`\n")

    md.append("## Split Configuration\n")
    md.append(f"- Split strategy: `{split_stats['split_strategy']}`")
    md.append(f"- Split unit: `{split_stats['split_unit']}`")
    md.append(f"- Random state: `{split_stats['random_state']}`")
    md.append(f"- Train ratio: `{split_stats['ratios']['train']}`")
    md.append(f"- Valid ratio: `{split_stats['ratios']['valid']}`")
    md.append(f"- Test ratio: `{split_stats['ratios']['test']}`")
    md.append(f"- Full rows: `{split_stats['full_rows']}`")
    md.append(f"- Split row total: `{split_stats['split_row_total']}`")
    md.append(f"- Full positive rate: `{split_stats['full_positive_rate']:.6f}`\n")

    md.append("## Split Summary\n")
    md.append("| Split | Rows | Positive | Negative | Positive rate | Gap from full |")
    md.append("|---|---:|---:|---:|---:|---:|")

    for split_name, stats in split_stats["splits"].items():
        md.append(
            f"| {split_name} | {stats['rows']} | {stats['positive_count']} | "
            f"{stats['negative_count']} | {stats['positive_rate']:.6f} | "
            f"{stats['target_rate_gap_from_full']:.6f} |"
        )

    overlap = split_stats["id_overlap_check"]
    md.append("\n## ID Overlap Check\n")
    md.append(f"- Train/valid overlap: `{overlap['train_valid_overlap']}`")
    md.append(f"- Train/test overlap: `{overlap['train_test_overlap']}`")
    md.append(f"- Valid/test overlap: `{overlap['valid_test_overlap']}`")
    md.append(f"- Split status: `{split_stats['status']}`\n")

    md.append("## Output Files\n")
    for name, file_path in output_files.items():
        md.append(f"- `{name}`: `{file_path}`")

    if split_stats["warnings"]:
        md.append("\n## Warnings\n")
        for warning in split_stats["warnings"]:
            md.append(f"- {warning}")

    if split_stats["errors"]:
        md.append("\n## Blocking Errors\n")
        for error in split_stats["errors"]:
            md.append(f"- {error}")

    path.write_text("\n".join(md), encoding="utf-8")


def write_split_manifest(
    split_stats: dict[str, Any],
    leakage_stats: dict[str, Any],
    output_files: dict[str, str],
    model_feature_metadata: dict[str, Any],
) -> None:
    manifest = {
        "split_name": "home_credit_default_risk_v1",
        "created_at": now_iso(),
        "source_files": {
            "feature_matrix": relative(FEATURE_MATRIX_PATH),
            "target": relative(TARGET_PATH),
            "feature_registry_csv": (
                relative(FEATURE_REGISTRY_CSV_PATH)
                if FEATURE_REGISTRY_CSV_PATH.exists()
                else None
            ),
        },
        "split_config": {
            "strategy": split_stats["split_strategy"],
            "split_unit": split_stats["split_unit"],
            "random_state": split_stats["random_state"],
            "ratios": split_stats["ratios"],
        },
        "model_feature_metadata": {
            "model_feature_count": model_feature_metadata["model_feature_count"],
            "id_columns": model_feature_metadata["id_columns"],
            "target_column": model_feature_metadata["target_column"],
            "excluded_columns": model_feature_metadata["excluded_columns"],
            "allowed_for_model_false_excluded": model_feature_metadata[
                "allowed_for_model_false_excluded"
            ],
        },
        "split_stats": split_stats,
        "leakage_status": leakage_stats["status"],
        "leakage_warning_count": leakage_stats["warning_count"],
        "leakage_error_count": leakage_stats["error_count"],
        "output_files": output_files,
    }

    path = MANIFEST_DIR / "split_manifest.json"
    path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def write_batch_d_summary(
    leakage_stats: dict[str, Any],
    split_stats: dict[str, Any],
    output_files: dict[str, str],
    model_feature_metadata: dict[str, Any],
) -> None:
    all_passed = (
        leakage_stats["status"] == "passed"
        and split_stats["status"] == "passed"
    )

    completed_before = 16
    batch_d_steps = 2
    completed = completed_before + (batch_d_steps if all_passed else 0)
    total = 20
    remaining = total - completed

    summary = {
        "batch_name": "batch_d_leakage_split_layer",
        "created_at": now_iso(),
        "assumption": "Batch A, Batch B, and Batch C were already completed.",
        "pipeline_group": "Batch D - Leakage + Split Layer",
        "pipeline_group_status": "leakage_split_layer_completed" if all_passed else "blocked",
        "technical_steps_completed": completed,
        "technical_steps_total": total,
        "technical_steps_remaining": remaining,
        "leakage_status": leakage_stats["status"],
        "leakage_warning_count": leakage_stats["warning_count"],
        "leakage_error_count": leakage_stats["error_count"],
        "split_status": split_stats["status"],
        "split_warning_count": split_stats["warning_count"],
        "split_error_count": split_stats["error_count"],
        "model_feature_count": model_feature_metadata["model_feature_count"],
        "excluded_columns": model_feature_metadata["excluded_columns"],
        "split_stats": split_stats,
        "outputs": {
            **output_files,
            "leakage_audit_report": "data/reports/leakage_audit_report.md",
            "split_report": "data/reports/split_report.md",
            "split_manifest": "data/manifests/split_manifest.json",
            "batch_d_summary_report": "data/reports/batch_d_leakage_split_summary.md",
            "batch_d_summary_manifest": "data/manifests/batch_d_leakage_split_summary.json",
        },
        "next_group": "Batch E - Preprocessing Layer" if all_passed else None,
    }

    manifest_path = MANIFEST_DIR / "batch_d_leakage_split_summary.json"
    manifest_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    report_path = REPORT_DIR / "batch_d_leakage_split_summary.md"

    md = []

    md.append("# Batch D Summary — Leakage + Split Layer\n")
    md.append("Assumption: Batch A, Batch B, and Batch C were already completed.\n")

    md.append("## Batch Status\n")
    md.append(f"- Status: `{'leakage_split_layer_completed' if all_passed else 'blocked'}`")
    md.append(f"- Technical steps completed: `{completed}/{total}`")
    md.append(f"- Technical steps remaining: `{remaining}/{total}`")

    if all_passed:
        md.append("- Next group: `Batch E - Preprocessing Layer`")
    else:
        md.append("- Next group: blocked until errors are fixed")

    md.append("\n## Leakage Audit\n")
    md.append(f"- Status: `{leakage_stats['status']}`")
    md.append(f"- Warning count: `{leakage_stats['warning_count']}`")
    md.append(f"- Error count: `{leakage_stats['error_count']}`")

    md.append("\n## Split Summary\n")
    md.append(f"- Status: `{split_stats['status']}`")
    md.append(f"- Strategy: `{split_stats['split_strategy']}`")
    md.append(f"- Split unit: `{split_stats['split_unit']}`")
    md.append(f"- Random state: `{split_stats['random_state']}`")
    md.append(f"- Full rows: `{split_stats['full_rows']}`")
    md.append(f"- Split row total: `{split_stats['split_row_total']}`")
    md.append(f"- Full positive rate: `{split_stats['full_positive_rate']:.6f}`")

    md.append("\n| Split | Rows | Positive rate |")
    md.append("|---|---:|---:|")
    for split_name, stats in split_stats["splits"].items():
        md.append(
            f"| {split_name} | {stats['rows']} | {stats['positive_rate']:.6f} |"
        )

    md.append("\n## Model Feature Metadata\n")
    md.append(f"- Model feature count: `{model_feature_metadata['model_feature_count']}`")
    md.append(f"- ID columns: `{model_feature_metadata['id_columns']}`")
    md.append(f"- Target column: `{model_feature_metadata['target_column']}`")
    md.append(f"- Excluded columns: `{model_feature_metadata['excluded_columns']}`")
    md.append(
        f"- allowed_for_model=False excluded: "
        f"`{model_feature_metadata['allowed_for_model_false_excluded']}`"
    )

    md.append("\n## ID Overlap Check\n")
    overlap = split_stats["id_overlap_check"]
    md.append(f"- Train/valid overlap: `{overlap['train_valid_overlap']}`")
    md.append(f"- Train/test overlap: `{overlap['train_test_overlap']}`")
    md.append(f"- Valid/test overlap: `{overlap['valid_test_overlap']}`")

    md.append("\n## Output Files\n")
    for name, file_path in summary["outputs"].items():
        md.append(f"- `{name}`: `{file_path}`")

    if leakage_stats["warnings"] or split_stats["warnings"]:
        md.append("\n## Warnings\n")
        for warning in leakage_stats["warnings"]:
            md.append(f"- Leakage: {warning}")
        for warning in split_stats["warnings"]:
            md.append(f"- Split: {warning}")

    if leakage_stats["errors"] or split_stats["errors"]:
        md.append("\n## Blocking Errors\n")
        for error in leakage_stats["errors"]:
            md.append(f"- Leakage: {error}")
        for error in split_stats["errors"]:
            md.append(f"- Split: {error}")

    report_path.write_text("\n".join(md), encoding="utf-8")


def main() -> None:
    print("=== Batch D: Leakage + Split Layer ===")
    print("This batch performs leakage audit and stratified train/valid/test split.")
    print("No preprocessing, encoding, scaling, or model training is performed.\n")

    ensure_inputs_exist()

    X, y, registry_df = load_batch_c_outputs()

    model_feature_metadata = build_model_feature_metadata(
        X=X,
        registry_df=registry_df,
    )

    model_feature_metadata_files = save_model_feature_metadata(
        model_feature_metadata,
    )

    leakage_stats = run_leakage_audit(
        X=X,
        y=y,
        registry_df=registry_df,
    )

    if leakage_stats["status"] != "passed":
        write_leakage_audit_report(leakage_stats)
        raise RuntimeError(
            "Leakage audit blocked Batch D. Check data/reports/leakage_audit_report.md"
        )

    X_train, y_train, X_valid, y_valid, X_test, y_test, split_stats = make_stratified_split(
        X=X,
        y=y,
    )

    if split_stats["status"] != "passed":
        raise RuntimeError("Split validation failed before saving outputs.")

    output_files = save_split_outputs(
        X_train=X_train,
        y_train=y_train,
        X_valid=X_valid,
        y_valid=y_valid,
        X_test=X_test,
        y_test=y_test,
    )

    output_files = {
        **output_files,
        **model_feature_metadata_files,
    }

    write_leakage_audit_report(leakage_stats)
    write_split_report(split_stats, output_files)
    write_split_manifest(
        split_stats=split_stats,
        leakage_stats=leakage_stats,
        output_files=output_files,
        model_feature_metadata=model_feature_metadata,
    )
    write_batch_d_summary(
        leakage_stats=leakage_stats,
        split_stats=split_stats,
        output_files=output_files,
        model_feature_metadata=model_feature_metadata,
    )

    print("\n=== Batch D completed ===")
    print("Produced files:")
    print("- data/processed/splits/X_train.parquet")
    print("- data/processed/splits/y_train.parquet")
    print("- data/processed/splits/X_valid.parquet")
    print("- data/processed/splits/y_valid.parquet")
    print("- data/processed/splits/X_test.parquet")
    print("- data/processed/splits/y_test.parquet")
    print("- ml/registry/model_feature_columns.json")
    print("- ml/registry/id_columns.json")
    print("- ml/registry/target_column.json")
    print("- ml/registry/model_feature_metadata.json")
    print("- data/reports/leakage_audit_report.md")
    print("- data/reports/split_report.md")
    print("- data/reports/batch_d_leakage_split_summary.md")
    print("- data/manifests/split_manifest.json")
    print("- data/manifests/batch_d_leakage_split_summary.json")

    print("\nBatch D status: leakage_split_layer_completed")
    print("Next: Batch E - Preprocessing Layer")


if __name__ == "__main__":
    main()