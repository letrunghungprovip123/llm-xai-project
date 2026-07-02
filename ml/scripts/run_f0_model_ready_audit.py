from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]

TREE_DIR = PROJECT_ROOT / "data" / "processed" / "model_ready" / "tree"
LINEAR_DIR = PROJECT_ROOT / "data" / "processed" / "model_ready" / "linear"

REGISTRY_DIR = PROJECT_ROOT / "ml" / "registry"
REPORT_DIR = PROJECT_ROOT / "data" / "reports"
AUDIT_DIR = REPORT_DIR / "model_ready_audit"
MANIFEST_DIR = PROJECT_ROOT / "data" / "manifests"

AUDIT_DIR.mkdir(parents=True, exist_ok=True)
MANIFEST_DIR.mkdir(parents=True, exist_ok=True)

TREE_X_TRAIN_PATH = TREE_DIR / "X_train_tree.parquet"
TREE_X_VALID_PATH = TREE_DIR / "X_valid_tree.parquet"
TREE_X_TEST_PATH = TREE_DIR / "X_test_tree.parquet"
TREE_Y_TRAIN_PATH = TREE_DIR / "y_train.parquet"
TREE_Y_VALID_PATH = TREE_DIR / "y_valid.parquet"
TREE_Y_TEST_PATH = TREE_DIR / "y_test.parquet"

LINEAR_X_TRAIN_PATH = LINEAR_DIR / "X_train_linear.parquet"
LINEAR_X_VALID_PATH = LINEAR_DIR / "X_valid_linear.parquet"
LINEAR_X_TEST_PATH = LINEAR_DIR / "X_test_linear.parquet"
LINEAR_Y_TRAIN_PATH = LINEAR_DIR / "y_train.parquet"
LINEAR_Y_VALID_PATH = LINEAR_DIR / "y_valid.parquet"
LINEAR_Y_TEST_PATH = LINEAR_DIR / "y_test.parquet"

PREPROCESSED_FEATURE_COLUMNS_TREE_PATH = REGISTRY_DIR / "preprocessed_feature_columns_tree.json"
PREPROCESSED_FEATURE_COLUMNS_LINEAR_PATH = REGISTRY_DIR / "preprocessed_feature_columns_linear.json"
PREPROCESSED_FEATURE_MAPPING_TREE_PATH = REGISTRY_DIR / "preprocessed_feature_mapping_tree.json"
PREPROCESSED_FEATURE_MAPPING_LINEAR_PATH = REGISTRY_DIR / "preprocessed_feature_mapping_linear.json"
PREPROCESSING_MANIFEST_PATH = MANIFEST_DIR / "preprocessing_manifest.json"

MODEL_READY_AUDIT_MANIFEST_PATH = MANIFEST_DIR / "model_ready_audit_manifest.json"
MODEL_READY_AUDIT_SUMMARY_PATH = REPORT_DIR / "model_ready_audit_summary.md"

TARGET_COLUMN = "TARGET"

PSI_BINS = 10
PSI_EPSILON = 1e-6

HIGH_SKEW_THRESHOLD = 2.0
HIGH_KURTOSIS_THRESHOLD = 10.0
HIGH_ZERO_RATE_THRESHOLD = 0.95
HIGH_OUTLIER_RATE_THRESHOLD = 0.05
PSI_LOW_RISK_THRESHOLD = 0.10
PSI_MEDIUM_RISK_THRESHOLD = 0.25


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def relative(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT))


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(data: Any, path: Path) -> None:
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def ensure_inputs_exist() -> None:
    required_files = [
        TREE_X_TRAIN_PATH,
        TREE_X_VALID_PATH,
        TREE_X_TEST_PATH,
        TREE_Y_TRAIN_PATH,
        TREE_Y_VALID_PATH,
        TREE_Y_TEST_PATH,
        LINEAR_X_TRAIN_PATH,
        LINEAR_X_VALID_PATH,
        LINEAR_X_TEST_PATH,
        LINEAR_Y_TRAIN_PATH,
        LINEAR_Y_VALID_PATH,
        LINEAR_Y_TEST_PATH,
    ]

    missing = [
        relative(path)
        for path in required_files
        if not path.exists()
    ]

    if missing:
        raise FileNotFoundError(f"Missing required model-ready files: {missing}")


def load_model_ready_data() -> dict[str, pd.DataFrame]:
    print("[F0 Audit] Loading model-ready datasets ...")

    return {
        "X_train_tree": pd.read_parquet(TREE_X_TRAIN_PATH),
        "X_valid_tree": pd.read_parquet(TREE_X_VALID_PATH),
        "X_test_tree": pd.read_parquet(TREE_X_TEST_PATH),
        "y_train_tree": pd.read_parquet(TREE_Y_TRAIN_PATH),
        "y_valid_tree": pd.read_parquet(TREE_Y_VALID_PATH),
        "y_test_tree": pd.read_parquet(TREE_Y_TEST_PATH),

        "X_train_linear": pd.read_parquet(LINEAR_X_TRAIN_PATH),
        "X_valid_linear": pd.read_parquet(LINEAR_X_VALID_PATH),
        "X_test_linear": pd.read_parquet(LINEAR_X_TEST_PATH),
        "y_train_linear": pd.read_parquet(LINEAR_Y_TRAIN_PATH),
        "y_valid_linear": pd.read_parquet(LINEAR_Y_VALID_PATH),
        "y_test_linear": pd.read_parquet(LINEAR_Y_TEST_PATH),
    }


def count_inf(df: pd.DataFrame) -> int:
    numeric_df = df.select_dtypes(include=[np.number])
    if numeric_df.empty:
        return 0
    return int(np.isinf(numeric_df.to_numpy()).sum())


def count_missing(df: pd.DataFrame) -> int:
    return int(df.isna().sum().sum())


def count_object_columns(df: pd.DataFrame) -> int:
    return int(len(df.select_dtypes(include=["object", "string", "category"]).columns))


def get_feature_mapping(pipeline_type: str) -> dict[str, dict[str, Any]]:
    if pipeline_type == "tree":
        return read_json(PREPROCESSED_FEATURE_MAPPING_TREE_PATH, default={}) or {}

    if pipeline_type == "linear":
        return read_json(PREPROCESSED_FEATURE_MAPPING_LINEAR_PATH, default={}) or {}

    return {}


def safe_float(value: Any) -> float | None:
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
        if np.isinf(value):
            return None
        return float(value)
    except Exception:
        return None


def safe_int(value: Any) -> int | None:
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
        return int(value)
    except Exception:
        return None


def compute_numeric_feature_stats(
    X: pd.DataFrame,
    y: pd.DataFrame,
    split_name: str,
    pipeline_type: str,
    feature_mapping: dict[str, dict[str, Any]],
) -> pd.DataFrame:
    print(f"[F0 Audit] Computing numeric stats for {pipeline_type}/{split_name} ...")

    rows = []

    target = None
    if TARGET_COLUMN in y.columns:
        target = y[TARGET_COLUMN].reset_index(drop=True)

    for feature in X.columns:
        series = X[feature]

        numeric_series = pd.to_numeric(series, errors="coerce")
        non_null = numeric_series.dropna()

        row: dict[str, Any] = {
            "pipeline_type": pipeline_type,
            "split": split_name,
            "feature": feature,
            "original_feature": feature_mapping.get(feature, {}).get("original_feature", feature),
            "encoded_from": feature_mapping.get(feature, {}).get("encoded_from"),
            "concept": feature_mapping.get(feature, {}).get("concept"),
            "concept_display_name": feature_mapping.get(feature, {}).get("concept_display_name"),
            "value_type": feature_mapping.get(feature, {}).get("value_type"),
            "unit": feature_mapping.get(feature, {}).get("unit"),
            "display_name": feature_mapping.get(feature, {}).get("display_name"),
            "dtype": str(series.dtype),
            "row_count": int(len(series)),
            "non_null_count": int(series.notna().sum()),
            "missing_count": int(series.isna().sum()),
            "missing_rate": float(series.isna().mean()),
            "inf_count": int(np.isinf(numeric_series.to_numpy(dtype=float, na_value=np.nan)).sum()),
            "unique_count": int(series.nunique(dropna=True)),
        }

        if non_null.empty:
            row.update({
                "mean": None,
                "median": None,
                "std": None,
                "var": None,
                "min": None,
                "max": None,
                "range": None,
                "q01": None,
                "q05": None,
                "q10": None,
                "q25": None,
                "q50": None,
                "q75": None,
                "q90": None,
                "q95": None,
                "q99": None,
                "iqr": None,
                "skewness": None,
                "skew_direction": "all_missing",
                "kurtosis": None,
                "zero_count": None,
                "zero_rate": None,
                "negative_count": None,
                "negative_rate": None,
                "positive_count": None,
                "positive_rate": None,
                "outlier_count_iqr": None,
                "outlier_rate_iqr": None,
                "zscore_outlier_count_abs3": None,
                "zscore_outlier_rate_abs3": None,
                "target_correlation": None,
                "mean_target_0": None,
                "mean_target_1": None,
                "mean_diff_target_1_minus_0": None,
                "median_target_0": None,
                "median_target_1": None,
                "median_diff_target_1_minus_0": None,
            })
            rows.append(row)
            continue

        q01 = non_null.quantile(0.01)
        q05 = non_null.quantile(0.05)
        q10 = non_null.quantile(0.10)
        q25 = non_null.quantile(0.25)
        q50 = non_null.quantile(0.50)
        q75 = non_null.quantile(0.75)
        q90 = non_null.quantile(0.90)
        q95 = non_null.quantile(0.95)
        q99 = non_null.quantile(0.99)

        iqr = q75 - q25
        lower_iqr = q25 - 1.5 * iqr
        upper_iqr = q75 + 1.5 * iqr

        outlier_mask_iqr = (numeric_series < lower_iqr) | (numeric_series > upper_iqr)
        outlier_count_iqr = int(outlier_mask_iqr.sum())
        outlier_rate_iqr = float(outlier_count_iqr / len(series))

        mean_value = non_null.mean()
        median_value = non_null.median()
        std_value = non_null.std()
        var_value = non_null.var()
        min_value = non_null.min()
        max_value = non_null.max()

        if std_value is not None and std_value > 0:
            zscores = (numeric_series - mean_value) / std_value
            zscore_outlier_mask = zscores.abs() > 3
            zscore_outlier_count = int(zscore_outlier_mask.sum())
            zscore_outlier_rate = float(zscore_outlier_count / len(series))
        else:
            zscore_outlier_count = 0
            zscore_outlier_rate = 0.0

        skewness = non_null.skew()
        kurtosis = non_null.kurtosis()

        if pd.isna(skewness):
            skew_direction = "unknown"
        elif skewness > 0.5:
            skew_direction = "right_skewed"
        elif skewness < -0.5:
            skew_direction = "left_skewed"
        else:
            skew_direction = "approximately_symmetric"

        zero_count = int((numeric_series == 0).sum())
        negative_count = int((numeric_series < 0).sum())
        positive_count = int((numeric_series > 0).sum())

        target_corr = None
        mean_target_0 = None
        mean_target_1 = None
        mean_diff = None
        median_target_0 = None
        median_target_1 = None
        median_diff = None

        if target is not None and numeric_series.nunique(dropna=True) > 1:
            try:
                target_corr = numeric_series.corr(target)
            except Exception:
                target_corr = None

            try:
                mean_target_0 = numeric_series[target == 0].mean()
                mean_target_1 = numeric_series[target == 1].mean()
                mean_diff = mean_target_1 - mean_target_0

                median_target_0 = numeric_series[target == 0].median()
                median_target_1 = numeric_series[target == 1].median()
                median_diff = median_target_1 - median_target_0
            except Exception:
                pass

        row.update({
            "mean": safe_float(mean_value),
            "median": safe_float(median_value),
            "std": safe_float(std_value),
            "var": safe_float(var_value),
            "min": safe_float(min_value),
            "max": safe_float(max_value),
            "range": safe_float(max_value - min_value),
            "q01": safe_float(q01),
            "q05": safe_float(q05),
            "q10": safe_float(q10),
            "q25": safe_float(q25),
            "q50": safe_float(q50),
            "q75": safe_float(q75),
            "q90": safe_float(q90),
            "q95": safe_float(q95),
            "q99": safe_float(q99),
            "iqr": safe_float(iqr),
            "skewness": safe_float(skewness),
            "skew_direction": skew_direction,
            "kurtosis": safe_float(kurtosis),
            "zero_count": zero_count,
            "zero_rate": float(zero_count / len(series)),
            "negative_count": negative_count,
            "negative_rate": float(negative_count / len(series)),
            "positive_count": positive_count,
            "positive_rate": float(positive_count / len(series)),
            "outlier_count_iqr": outlier_count_iqr,
            "outlier_rate_iqr": outlier_rate_iqr,
            "zscore_outlier_count_abs3": zscore_outlier_count,
            "zscore_outlier_rate_abs3": zscore_outlier_rate,
            "target_correlation": safe_float(target_corr),
            "mean_target_0": safe_float(mean_target_0),
            "mean_target_1": safe_float(mean_target_1),
            "mean_diff_target_1_minus_0": safe_float(mean_diff),
            "median_target_0": safe_float(median_target_0),
            "median_target_1": safe_float(median_target_1),
            "median_diff_target_1_minus_0": safe_float(median_diff),
        })

        rows.append(row)

    return pd.DataFrame(rows)


def compute_dataset_level_audit(
    data: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    print("[F0 Audit] Computing dataset-level audit ...")

    rows = []

    dataset_pairs = [
        ("tree", "train", data["X_train_tree"], data["y_train_tree"]),
        ("tree", "valid", data["X_valid_tree"], data["y_valid_tree"]),
        ("tree", "test", data["X_test_tree"], data["y_test_tree"]),
        ("linear", "train", data["X_train_linear"], data["y_train_linear"]),
        ("linear", "valid", data["X_valid_linear"], data["y_valid_linear"]),
        ("linear", "test", data["X_test_linear"], data["y_test_linear"]),
    ]

    for pipeline_type, split_name, X, y in dataset_pairs:
        object_columns = X.select_dtypes(include=["object", "string", "category"]).columns.tolist()

        target_positive_count = None
        target_negative_count = None
        target_positive_rate = None

        if TARGET_COLUMN in y.columns:
            target_positive_count = int((y[TARGET_COLUMN] == 1).sum())
            target_negative_count = int((y[TARGET_COLUMN] == 0).sum())
            target_positive_rate = float((y[TARGET_COLUMN] == 1).mean())

        rows.append({
            "pipeline_type": pipeline_type,
            "split": split_name,
            "x_rows": int(len(X)),
            "x_columns": int(X.shape[1]),
            "y_rows": int(len(y)),
            "y_columns": int(y.shape[1]),
            "target_column": TARGET_COLUMN if TARGET_COLUMN in y.columns else None,
            "target_positive_count": target_positive_count,
            "target_negative_count": target_negative_count,
            "target_positive_rate": target_positive_rate,
            "missing_count": count_missing(X),
            "inf_count": count_inf(X),
            "object_column_count": len(object_columns),
            "object_columns_sample": ", ".join(object_columns[:20]),
            "duplicate_columns_count": int(pd.Index(X.columns).duplicated().sum()),
            "sk_id_curr_in_X": "SK_ID_CURR" in X.columns,
            "target_in_X": TARGET_COLUMN in X.columns,
            "memory_mb": float(X.memory_usage(deep=True).sum() / (1024 ** 2)),
        })

    return pd.DataFrame(rows)


def calculate_psi_for_feature(
    train_series: pd.Series,
    compare_series: pd.Series,
    bins: int = PSI_BINS,
) -> float | None:
    train_values = pd.to_numeric(train_series, errors="coerce").dropna()
    compare_values = pd.to_numeric(compare_series, errors="coerce").dropna()

    if train_values.empty or compare_values.empty:
        return None

    if train_values.nunique(dropna=True) <= 1:
        return 0.0

    try:
        quantiles = np.linspace(0, 1, bins + 1)
        bin_edges = np.unique(np.quantile(train_values, quantiles))

        if len(bin_edges) <= 2:
            min_value = train_values.min()
            max_value = train_values.max()
            if min_value == max_value:
                return 0.0
            bin_edges = np.linspace(min_value, max_value, bins + 1)

        train_counts, _ = np.histogram(train_values, bins=bin_edges)
        compare_counts, _ = np.histogram(compare_values, bins=bin_edges)

        train_perc = train_counts / max(train_counts.sum(), 1)
        compare_perc = compare_counts / max(compare_counts.sum(), 1)

        train_perc = np.clip(train_perc, PSI_EPSILON, None)
        compare_perc = np.clip(compare_perc, PSI_EPSILON, None)

        psi = np.sum((compare_perc - train_perc) * np.log(compare_perc / train_perc))

        return float(psi)

    except Exception:
        return None


def classify_psi_risk(psi: float | None) -> str:
    if psi is None:
        return "not_available"

    if psi < PSI_LOW_RISK_THRESHOLD:
        return "low"

    if psi < PSI_MEDIUM_RISK_THRESHOLD:
        return "medium"

    return "high"


def compute_drift_audit_for_pipeline(
    X_train: pd.DataFrame,
    X_valid: pd.DataFrame,
    X_test: pd.DataFrame,
    pipeline_type: str,
    feature_mapping: dict[str, dict[str, Any]],
) -> pd.DataFrame:
    print(f"[F0 Audit] Computing PSI drift audit for {pipeline_type} ...")

    rows = []

    for feature in X_train.columns:
        valid_psi = calculate_psi_for_feature(X_train[feature], X_valid[feature])
        test_psi = calculate_psi_for_feature(X_train[feature], X_test[feature])

        rows.append({
            "pipeline_type": pipeline_type,
            "feature": feature,
            "original_feature": feature_mapping.get(feature, {}).get("original_feature", feature),
            "encoded_from": feature_mapping.get(feature, {}).get("encoded_from"),
            "concept": feature_mapping.get(feature, {}).get("concept"),
            "valid_psi_vs_train": valid_psi,
            "valid_psi_risk": classify_psi_risk(valid_psi),
            "test_psi_vs_train": test_psi,
            "test_psi_risk": classify_psi_risk(test_psi),
        })

    return pd.DataFrame(rows)


def compute_warning_flags(feature_stats: pd.DataFrame) -> pd.DataFrame:
    print("[F0 Audit] Computing feature warning flags ...")

    rows = []

    for _, row in feature_stats.iterrows():
        flags = []

        skewness = row.get("skewness")
        kurtosis = row.get("kurtosis")
        zero_rate = row.get("zero_rate")
        outlier_rate_iqr = row.get("outlier_rate_iqr")
        missing_rate = row.get("missing_rate")
        inf_count = row.get("inf_count")

        if pd.notna(missing_rate) and missing_rate > 0:
            flags.append("has_missing")

        if pd.notna(inf_count) and inf_count > 0:
            flags.append("has_inf")

        if pd.notna(skewness) and abs(skewness) >= HIGH_SKEW_THRESHOLD:
            flags.append("high_skewness")

        if pd.notna(kurtosis) and kurtosis >= HIGH_KURTOSIS_THRESHOLD:
            flags.append("high_kurtosis")

        if pd.notna(zero_rate) and zero_rate >= HIGH_ZERO_RATE_THRESHOLD:
            flags.append("mostly_zero")

        if pd.notna(outlier_rate_iqr) and outlier_rate_iqr >= HIGH_OUTLIER_RATE_THRESHOLD:
            flags.append("high_iqr_outlier_rate")

        rows.append({
            "pipeline_type": row.get("pipeline_type"),
            "split": row.get("split"),
            "feature": row.get("feature"),
            "original_feature": row.get("original_feature"),
            "encoded_from": row.get("encoded_from"),
            "concept": row.get("concept"),
            "warning_flag_count": len(flags),
            "warning_flags": "|".join(flags),
        })

    return pd.DataFrame(rows)


def compute_one_hot_audit(
    feature_mapping: dict[str, dict[str, Any]],
    pipeline_type: str,
) -> pd.DataFrame:
    print(f"[F0 Audit] Computing one-hot audit for {pipeline_type} ...")

    rows = []

    for preprocessed_feature, meta in feature_mapping.items():
        if meta.get("encoded_from") != "one_hot":
            continue

        rows.append({
            "pipeline_type": pipeline_type,
            "preprocessed_feature": preprocessed_feature,
            "original_feature": meta.get("original_feature"),
            "concept": meta.get("concept"),
            "concept_display_name": meta.get("concept_display_name"),
            "display_name": meta.get("display_name"),
            "value_type": meta.get("value_type"),
            "unit": meta.get("unit"),
        })

    return pd.DataFrame(rows)


def compute_concept_summary(
    feature_stats: pd.DataFrame,
) -> pd.DataFrame:
    print("[F0 Audit] Computing concept-level summary ...")

    if feature_stats.empty:
        return pd.DataFrame()

    summary = (
        feature_stats
        .groupby(["pipeline_type", "split", "concept"], dropna=False)
        .agg(
            feature_count=("feature", "count"),
            avg_missing_rate=("missing_rate", "mean"),
            avg_zero_rate=("zero_rate", "mean"),
            avg_abs_skewness=("skewness", lambda s: float(np.nanmean(np.abs(s))) if len(s) else None),
            avg_outlier_rate_iqr=("outlier_rate_iqr", "mean"),
            max_abs_target_correlation=("target_correlation", lambda s: float(np.nanmax(np.abs(s))) if s.notna().any() else None),
        )
        .reset_index()
    )

    return summary


def save_audit_csvs(
    dataset_audit: pd.DataFrame,
    tree_feature_stats: pd.DataFrame,
    linear_feature_stats: pd.DataFrame,
    feature_warning_flags: pd.DataFrame,
    drift_audit: pd.DataFrame,
    one_hot_audit: pd.DataFrame,
    concept_summary: pd.DataFrame,
) -> dict[str, str]:
    output_paths = {
        "dataset_level_audit": AUDIT_DIR / "dataset_level_audit.csv",
        "tree_feature_numeric_audit": AUDIT_DIR / "tree_feature_numeric_audit.csv",
        "linear_feature_numeric_audit": AUDIT_DIR / "linear_feature_numeric_audit.csv",
        "feature_warning_flags": AUDIT_DIR / "feature_warning_flags.csv",
        "split_drift_psi_audit": AUDIT_DIR / "split_drift_psi_audit.csv",
        "one_hot_feature_audit": AUDIT_DIR / "one_hot_feature_audit.csv",
        "concept_level_audit": AUDIT_DIR / "concept_level_audit.csv",
    }

    dataset_audit.to_csv(output_paths["dataset_level_audit"], index=False)
    tree_feature_stats.to_csv(output_paths["tree_feature_numeric_audit"], index=False)
    linear_feature_stats.to_csv(output_paths["linear_feature_numeric_audit"], index=False)
    feature_warning_flags.to_csv(output_paths["feature_warning_flags"], index=False)
    drift_audit.to_csv(output_paths["split_drift_psi_audit"], index=False)
    one_hot_audit.to_csv(output_paths["one_hot_feature_audit"], index=False)
    concept_summary.to_csv(output_paths["concept_level_audit"], index=False)

    return {
        name: relative(path)
        for name, path in output_paths.items()
    }


def build_summary_report(
    dataset_audit: pd.DataFrame,
    tree_feature_stats: pd.DataFrame,
    linear_feature_stats: pd.DataFrame,
    feature_warning_flags: pd.DataFrame,
    drift_audit: pd.DataFrame,
    output_files: dict[str, str],
) -> dict[str, Any]:
    errors = []
    warnings = []

    for _, row in dataset_audit.iterrows():
        pipeline_type = row["pipeline_type"]
        split_name = row["split"]

        if row["missing_count"] != 0:
            errors.append(f"{pipeline_type}/{split_name}: missing_count={row['missing_count']}")

        if row["inf_count"] != 0:
            errors.append(f"{pipeline_type}/{split_name}: inf_count={row['inf_count']}")

        if row["object_column_count"] != 0:
            errors.append(f"{pipeline_type}/{split_name}: object_column_count={row['object_column_count']}")

        if row["sk_id_curr_in_X"] is True:
            errors.append(f"{pipeline_type}/{split_name}: SK_ID_CURR found in X")

        if row["target_in_X"] is True:
            errors.append(f"{pipeline_type}/{split_name}: TARGET found in X")

        if row["x_rows"] != row["y_rows"]:
            errors.append(f"{pipeline_type}/{split_name}: X/y row mismatch")

    high_psi_rows = drift_audit[
        (drift_audit["valid_psi_risk"] == "high") |
        (drift_audit["test_psi_risk"] == "high")
    ]

    if len(high_psi_rows) > 0:
        warnings.append(f"High PSI drift features found: {len(high_psi_rows)}")

    high_warning_features = feature_warning_flags[
        feature_warning_flags["warning_flag_count"] > 0
    ]

    if len(high_warning_features) > 0:
        warnings.append(f"Features with distribution warning flags: {len(high_warning_features)}")

    summary = {
        "audit_name": "final_model_ready_data_audit",
        "created_at": now_iso(),
        "status": "passed" if not errors else "blocked",
        "error_count": len(errors),
        "errors": errors,
        "warning_count": len(warnings),
        "warnings": warnings,
        "dataset_level_rows": int(len(dataset_audit)),
        "tree_feature_audit_rows": int(len(tree_feature_stats)),
        "linear_feature_audit_rows": int(len(linear_feature_stats)),
        "feature_warning_rows": int(len(feature_warning_flags)),
        "features_with_warning_flags": int(len(high_warning_features)),
        "high_psi_feature_rows": int(len(high_psi_rows)),
        "output_files": output_files,
    }

    return summary


def write_summary_md(summary: dict[str, Any]) -> None:
    md = []

    md.append("# Final Model-Ready Data Audit Summary\n")
    md.append(f"Created at: `{summary['created_at']}`\n")

    md.append("## Status\n")
    md.append(f"- Status: `{summary['status']}`")
    md.append(f"- Error count: `{summary['error_count']}`")
    md.append(f"- Warning count: `{summary['warning_count']}`")
    md.append(f"- Features with warning flags: `{summary['features_with_warning_flags']}`")
    md.append(f"- High PSI feature rows: `{summary['high_psi_feature_rows']}`\n")

    md.append("## What This Audit Covers\n")
    md.append("- Dataset-level model-ready validation")
    md.append("- Per-feature numeric descriptive statistics")
    md.append("- Mean, median, standard deviation, variance, min/max")
    md.append("- Quantiles: p1, p5, p10, p25, p50, p75, p90, p95, p99")
    md.append("- IQR outlier audit")
    md.append("- Z-score outlier audit")
    md.append("- Skewness and skew direction")
    md.append("- Kurtosis")
    md.append("- Zero/negative/positive value rates")
    md.append("- Target correlation and target-wise mean/median differences")
    md.append("- Train vs valid/test PSI drift audit")
    md.append("- One-hot encoded feature mapping")
    md.append("- Concept-level summary\n")

    md.append("## Output CSV Files\n")
    for name, path in summary["output_files"].items():
        md.append(f"- `{name}`: `{path}`")

    if summary["warnings"]:
        md.append("\n## Warnings\n")
        for warning in summary["warnings"]:
            md.append(f"- {warning}")

    if summary["errors"]:
        md.append("\n## Blocking Errors\n")
        for error in summary["errors"]:
            md.append(f"- {error}")

    MODEL_READY_AUDIT_SUMMARY_PATH.write_text("\n".join(md), encoding="utf-8")


def main() -> None:
    print("=== Batch F0: Final Model-Ready Data Audit ===")
    print("This audit does not change data. It creates CSV reports describing the dataset before model training.\n")

    ensure_inputs_exist()

    data = load_model_ready_data()

    tree_mapping = get_feature_mapping("tree")
    linear_mapping = get_feature_mapping("linear")

    dataset_audit = compute_dataset_level_audit(data)

    tree_train_stats = compute_numeric_feature_stats(
        X=data["X_train_tree"],
        y=data["y_train_tree"],
        split_name="train",
        pipeline_type="tree",
        feature_mapping=tree_mapping,
    )
    tree_valid_stats = compute_numeric_feature_stats(
        X=data["X_valid_tree"],
        y=data["y_valid_tree"],
        split_name="valid",
        pipeline_type="tree",
        feature_mapping=tree_mapping,
    )
    tree_test_stats = compute_numeric_feature_stats(
        X=data["X_test_tree"],
        y=data["y_test_tree"],
        split_name="test",
        pipeline_type="tree",
        feature_mapping=tree_mapping,
    )

    tree_feature_stats = pd.concat(
        [tree_train_stats, tree_valid_stats, tree_test_stats],
        axis=0,
        ignore_index=True,
    )

    linear_train_stats = compute_numeric_feature_stats(
        X=data["X_train_linear"],
        y=data["y_train_linear"],
        split_name="train",
        pipeline_type="linear",
        feature_mapping=linear_mapping,
    )
    linear_valid_stats = compute_numeric_feature_stats(
        X=data["X_valid_linear"],
        y=data["y_valid_linear"],
        split_name="valid",
        pipeline_type="linear",
        feature_mapping=linear_mapping,
    )
    linear_test_stats = compute_numeric_feature_stats(
        X=data["X_test_linear"],
        y=data["y_test_linear"],
        split_name="test",
        pipeline_type="linear",
        feature_mapping=linear_mapping,
    )

    linear_feature_stats = pd.concat(
        [linear_train_stats, linear_valid_stats, linear_test_stats],
        axis=0,
        ignore_index=True,
    )

    all_feature_stats = pd.concat(
        [tree_feature_stats, linear_feature_stats],
        axis=0,
        ignore_index=True,
    )

    feature_warning_flags = compute_warning_flags(all_feature_stats)

    tree_drift = compute_drift_audit_for_pipeline(
        X_train=data["X_train_tree"],
        X_valid=data["X_valid_tree"],
        X_test=data["X_test_tree"],
        pipeline_type="tree",
        feature_mapping=tree_mapping,
    )

    linear_drift = compute_drift_audit_for_pipeline(
        X_train=data["X_train_linear"],
        X_valid=data["X_valid_linear"],
        X_test=data["X_test_linear"],
        pipeline_type="linear",
        feature_mapping=linear_mapping,
    )

    drift_audit = pd.concat(
        [tree_drift, linear_drift],
        axis=0,
        ignore_index=True,
    )

    tree_one_hot = compute_one_hot_audit(
        feature_mapping=tree_mapping,
        pipeline_type="tree",
    )

    linear_one_hot = compute_one_hot_audit(
        feature_mapping=linear_mapping,
        pipeline_type="linear",
    )

    one_hot_audit = pd.concat(
        [tree_one_hot, linear_one_hot],
        axis=0,
        ignore_index=True,
    )

    concept_summary = compute_concept_summary(all_feature_stats)

    output_files = save_audit_csvs(
        dataset_audit=dataset_audit,
        tree_feature_stats=tree_feature_stats,
        linear_feature_stats=linear_feature_stats,
        feature_warning_flags=feature_warning_flags,
        drift_audit=drift_audit,
        one_hot_audit=one_hot_audit,
        concept_summary=concept_summary,
    )

    summary = build_summary_report(
        dataset_audit=dataset_audit,
        tree_feature_stats=tree_feature_stats,
        linear_feature_stats=linear_feature_stats,
        feature_warning_flags=feature_warning_flags,
        drift_audit=drift_audit,
        output_files=output_files,
    )

    write_json(summary, MODEL_READY_AUDIT_MANIFEST_PATH)
    write_summary_md(summary)

    print("\n=== Final Model-Ready Data Audit completed ===")
    print("Produced CSV files:")
    for _, path in output_files.items():
        print(f"- {path}")

    print("\nProduced summary files:")
    print("- data/reports/model_ready_audit_summary.md")
    print("- data/manifests/model_ready_audit_manifest.json")

    print(f"\nAudit status: {summary['status']}")
    print(f"Warnings: {summary['warning_count']}")
    print(f"Errors: {summary['error_count']}")

    if summary["status"] == "passed":
        print("\nNext: Batch F - Model Training Layer")
    else:
        print("\nFix blocking audit errors before model training.")


if __name__ == "__main__":
    main()