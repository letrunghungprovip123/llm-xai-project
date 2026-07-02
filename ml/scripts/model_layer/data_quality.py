from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ml.scripts.model_layer.config import (
    ID_COLUMN,
    TARGET_COLUMN,
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
    TREE_FEATURE_COLUMNS_PATH,
    LINEAR_FEATURE_COLUMNS_PATH,
    get_required_input_paths,
)


# ============================================================
# Data Containers
# ============================================================

@dataclass(frozen=True)
class DatasetBranch:
    """
    Một nhánh dữ liệu model-ready.

    Ví dụ:
        - tree branch: dùng cho RandomForest, HistGradientBoosting
        - linear branch: dùng cho LogisticRegression

    X_*:
        Feature matrix đã preprocessing.

    y_*:
        Target dataframe. Có thể chứa SK_ID_CURR + TARGET.

    feature_columns:
        Danh sách cột expected lấy từ registry.
        Dùng để kiểm tra thứ tự cột và schema.
    """

    name: str
    X_train: pd.DataFrame
    X_valid: pd.DataFrame
    X_test: pd.DataFrame
    y_train: pd.DataFrame
    y_valid: pd.DataFrame
    y_test: pd.DataFrame
    feature_columns: list[str]


@dataclass(frozen=True)
class ModelReadyDatasets:
    """
    Toàn bộ dữ liệu đầu vào chính thức của Model Layer.

    linear:
        Dùng cho Logistic Regression.

    tree:
        Dùng cho tree-based models.
    """

    linear: DatasetBranch
    tree: DatasetBranch


@dataclass(frozen=True)
class QualityGateResult:
    """
    Kết quả kiểm tra chất lượng dữ liệu trước khi train.

    status:
        "passed" hoặc "failed"

    checks:
        Danh sách các check đã chạy.

    errors:
        Lỗi nghiêm trọng. Nếu có error thì không nên train model.

    warnings:
        Cảnh báo không nhất thiết chặn train.
    """

    status: str
    checks: list[dict[str, Any]]
    errors: list[str]
    warnings: list[str]


# ============================================================
# Basic File Helpers
# ============================================================

def load_json_list(path: Path) -> list[str]:
    """
    Đọc file JSON chứa danh sách string.

    Dùng cho:
        preprocessed_feature_columns_tree.json
        preprocessed_feature_columns_linear.json
    """

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError(f"Expected JSON list at {path}, got {type(data).__name__}")

    if not all(isinstance(item, str) for item in data):
        raise ValueError(f"Expected all items in {path} to be strings")

    return data


def check_required_input_files_exist() -> list[str]:
    """
    Kiểm tra toàn bộ input path bắt buộc có tồn tại không.

    Trả về:
        list lỗi. Nếu list rỗng nghĩa là đủ file.
    """

    errors: list[str] = []

    for name, path in get_required_input_paths().items():
        if not path.exists():
            errors.append(f"Missing required input file: {name} -> {path}")

    return errors


# ============================================================
# Load Model-Ready Data
# ============================================================

def load_dataset_branch(
    *,
    name: str,
    x_train_path: Path,
    x_valid_path: Path,
    x_test_path: Path,
    y_train_path: Path,
    y_valid_path: Path,
    y_test_path: Path,
    feature_columns_path: Path,
) -> DatasetBranch:
    """
    Load một nhánh dữ liệu model-ready.

    Hàm này chỉ đọc data.
    Quality check chi tiết sẽ làm ở run_quality_gate().
    """

    X_train = pd.read_parquet(x_train_path)
    X_valid = pd.read_parquet(x_valid_path)
    X_test = pd.read_parquet(x_test_path)

    y_train = pd.read_parquet(y_train_path)
    y_valid = pd.read_parquet(y_valid_path)
    y_test = pd.read_parquet(y_test_path)

    feature_columns = load_json_list(feature_columns_path)

    return DatasetBranch(
        name=name,
        X_train=X_train,
        X_valid=X_valid,
        X_test=X_test,
        y_train=y_train,
        y_valid=y_valid,
        y_test=y_test,
        feature_columns=feature_columns,
    )


def load_model_ready_datasets() -> ModelReadyDatasets:
    """
    Load cả hai nhánh dữ liệu:
        - linear-ready
        - tree-ready

    Đây là hàm chính mà run_f_model_training_layer.py sẽ gọi.
    """

    missing_file_errors = check_required_input_files_exist()
    if missing_file_errors:
        joined_errors = "\n".join(missing_file_errors)
        raise FileNotFoundError(
            "Cannot load model-ready datasets because some required files are missing:\n"
            f"{joined_errors}"
        )

    linear = load_dataset_branch(
        name="linear",
        x_train_path=LINEAR_X_TRAIN_PATH,
        x_valid_path=LINEAR_X_VALID_PATH,
        x_test_path=LINEAR_X_TEST_PATH,
        y_train_path=LINEAR_Y_TRAIN_PATH,
        y_valid_path=LINEAR_Y_VALID_PATH,
        y_test_path=LINEAR_Y_TEST_PATH,
        feature_columns_path=LINEAR_FEATURE_COLUMNS_PATH,
    )

    tree = load_dataset_branch(
        name="tree",
        x_train_path=TREE_X_TRAIN_PATH,
        x_valid_path=TREE_X_VALID_PATH,
        x_test_path=TREE_X_TEST_PATH,
        y_train_path=TREE_Y_TRAIN_PATH,
        y_valid_path=TREE_Y_VALID_PATH,
        y_test_path=TREE_Y_TEST_PATH,
        feature_columns_path=TREE_FEATURE_COLUMNS_PATH,
    )

    return ModelReadyDatasets(linear=linear, tree=tree)


# ============================================================
# Target Helpers
# ============================================================

def extract_target(y_df: pd.DataFrame) -> pd.Series:
    """
    Lấy TARGET từ y dataframe.

    y_df có thể chứa:
        - TARGET
        - SK_ID_CURR + TARGET

    Model chỉ train bằng TARGET.
    """

    if TARGET_COLUMN not in y_df.columns:
        raise ValueError(f"Target column '{TARGET_COLUMN}' not found in y dataframe")

    return y_df[TARGET_COLUMN]


def extract_ids_or_row_index(y_df: pd.DataFrame) -> pd.Series:
    """
    Lấy SK_ID_CURR nếu có.

    Nếu y file không có SK_ID_CURR, dùng row index thay thế.
    Hàm này chủ yếu dùng cho prediction output sau này.
    """

    if ID_COLUMN in y_df.columns:
        return y_df[ID_COLUMN]

    return pd.Series(
        data=np.arange(len(y_df)),
        name="row_index",
        index=y_df.index,
    )


# ============================================================
# Quality Checks
# ============================================================

def check_shape_alignment(branch: DatasetBranch) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Kiểm tra số dòng X và y có khớp không.
    """

    checks: list[dict[str, Any]] = []
    errors: list[str] = []

    split_pairs = [
        ("train", branch.X_train, branch.y_train),
        ("valid", branch.X_valid, branch.y_valid),
        ("test", branch.X_test, branch.y_test),
    ]

    for split, X, y in split_pairs:
        passed = len(X) == len(y)

        checks.append(
            {
                "branch": branch.name,
                "check": "shape_alignment",
                "split": split,
                "x_rows": len(X),
                "y_rows": len(y),
                "passed": passed,
            }
        )

        if not passed:
            errors.append(
                f"[{branch.name}/{split}] X rows ({len(X)}) != y rows ({len(y)})"
            )

    return checks, errors


def check_column_consistency(branch: DatasetBranch) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Kiểm tra train/valid/test có cùng danh sách cột và đúng registry không.

    Đây là check cực quan trọng.
    Nếu thứ tự cột lệch, model có thể predict sai nhưng không báo lỗi.
    """

    checks: list[dict[str, Any]] = []
    errors: list[str] = []

    train_columns = list(branch.X_train.columns)
    valid_columns = list(branch.X_valid.columns)
    test_columns = list(branch.X_test.columns)
    expected_columns = branch.feature_columns

    valid_matches_train = valid_columns == train_columns
    test_matches_train = test_columns == train_columns
    train_matches_registry = train_columns == expected_columns

    checks.extend(
        [
            {
                "branch": branch.name,
                "check": "valid_columns_match_train",
                "passed": valid_matches_train,
                "train_col_count": len(train_columns),
                "valid_col_count": len(valid_columns),
            },
            {
                "branch": branch.name,
                "check": "test_columns_match_train",
                "passed": test_matches_train,
                "train_col_count": len(train_columns),
                "test_col_count": len(test_columns),
            },
            {
                "branch": branch.name,
                "check": "train_columns_match_registry",
                "passed": train_matches_registry,
                "train_col_count": len(train_columns),
                "registry_col_count": len(expected_columns),
            },
        ]
    )

    if not valid_matches_train:
        errors.append(f"[{branch.name}] X_valid columns do not match X_train columns")

    if not test_matches_train:
        errors.append(f"[{branch.name}] X_test columns do not match X_train columns")

    if not train_matches_registry:
        errors.append(
            f"[{branch.name}] X_train columns do not match feature registry columns"
        )

    return checks, errors


def check_forbidden_columns(branch: DatasetBranch) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Kiểm tra X không chứa ID/target/raw auxiliary IDs.

    Những cột này không được phép là model feature.
    """

    checks: list[dict[str, Any]] = []
    errors: list[str] = []

    forbidden_columns = {
        ID_COLUMN,
        TARGET_COLUMN,
        "SK_ID_BUREAU",
        "SK_ID_PREV",
    }

    split_frames = [
        ("train", branch.X_train),
        ("valid", branch.X_valid),
        ("test", branch.X_test),
    ]

    for split, X in split_frames:
        found = sorted(forbidden_columns.intersection(set(X.columns)))
        passed = len(found) == 0

        checks.append(
            {
                "branch": branch.name,
                "check": "forbidden_columns",
                "split": split,
                "found": found,
                "passed": passed,
            }
        )

        if not passed:
            errors.append(f"[{branch.name}/{split}] Forbidden columns found in X: {found}")

    return checks, errors


def check_missing_and_infinite(branch: DatasetBranch) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Kiểm tra X không có NaN và không có inf/-inf.
    """

    checks: list[dict[str, Any]] = []
    errors: list[str] = []

    split_frames = [
        ("train", branch.X_train),
        ("valid", branch.X_valid),
        ("test", branch.X_test),
    ]

    for split, X in split_frames:
        missing_count = int(X.isna().sum().sum())

        numeric_values = X.select_dtypes(include=[np.number]).to_numpy()
        infinite_count = int(np.isinf(numeric_values).sum())

        passed = missing_count == 0 and infinite_count == 0

        checks.append(
            {
                "branch": branch.name,
                "check": "missing_and_infinite",
                "split": split,
                "missing_count": missing_count,
                "infinite_count": infinite_count,
                "passed": passed,
            }
        )

        if missing_count > 0:
            errors.append(f"[{branch.name}/{split}] Missing values found: {missing_count}")

        if infinite_count > 0:
            errors.append(f"[{branch.name}/{split}] Infinite values found: {infinite_count}")

    return checks, errors


def check_no_object_columns(branch: DatasetBranch) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Kiểm tra X không còn object/string/category columns.

    Model-ready data phải là numeric/bool.
    """

    checks: list[dict[str, Any]] = []
    errors: list[str] = []

    invalid_dtypes = ["object", "string", "category"]

    split_frames = [
        ("train", branch.X_train),
        ("valid", branch.X_valid),
        ("test", branch.X_test),
    ]

    for split, X in split_frames:
        invalid_columns = [
            column
            for column, dtype in X.dtypes.items()
            if str(dtype) in invalid_dtypes
        ]

        passed = len(invalid_columns) == 0

        checks.append(
            {
                "branch": branch.name,
                "check": "no_object_columns",
                "split": split,
                "invalid_column_count": len(invalid_columns),
                "invalid_columns_preview": invalid_columns[:20],
                "passed": passed,
            }
        )

        if not passed:
            errors.append(
                f"[{branch.name}/{split}] Non-numeric columns found: {invalid_columns[:20]}"
            )

    return checks, errors


def check_target_validity(branch: DatasetBranch) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """
    Kiểm tra TARGET:
        - tồn tại
        - không missing
        - chỉ có 0/1
        - positive rate hợp lý
    """

    checks: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []

    split_targets = [
        ("train", branch.y_train),
        ("valid", branch.y_valid),
        ("test", branch.y_test),
    ]

    for split, y_df in split_targets:
        if TARGET_COLUMN not in y_df.columns:
            checks.append(
                {
                    "branch": branch.name,
                    "check": "target_validity",
                    "split": split,
                    "passed": False,
                    "reason": "target_missing",
                }
            )
            errors.append(f"[{branch.name}/{split}] TARGET column missing")
            continue

        y = y_df[TARGET_COLUMN]
        missing_count = int(y.isna().sum())
        unique_values = sorted(y.dropna().unique().tolist())
        allowed_values = [0, 1]
        positive_rate = float((y == 1).mean())

        passed = (
            missing_count == 0
            and unique_values == allowed_values
        )

        checks.append(
            {
                "branch": branch.name,
                "check": "target_validity",
                "split": split,
                "missing_count": missing_count,
                "unique_values": unique_values,
                "positive_rate": positive_rate,
                "passed": passed,
            }
        )

        if missing_count > 0:
            errors.append(f"[{branch.name}/{split}] TARGET missing count: {missing_count}")

        if unique_values != allowed_values:
            errors.append(
                f"[{branch.name}/{split}] TARGET values must be [0, 1], got {unique_values}"
            )

        if positive_rate < 0.01 or positive_rate > 0.5:
            warnings.append(
                f"[{branch.name}/{split}] Unusual positive rate: {positive_rate:.6f}"
            )

    return checks, errors, warnings


def check_branch_quality(branch: DatasetBranch) -> QualityGateResult:
    """
    Chạy toàn bộ quality checks cho một branch.
    """

    all_checks: list[dict[str, Any]] = []
    all_errors: list[str] = []
    all_warnings: list[str] = []

    check_functions = [
        check_shape_alignment,
        check_column_consistency,
        check_forbidden_columns,
        check_missing_and_infinite,
        check_no_object_columns,
    ]

    for check_function in check_functions:
        checks, errors = check_function(branch)
        all_checks.extend(checks)
        all_errors.extend(errors)

    target_checks, target_errors, target_warnings = check_target_validity(branch)
    all_checks.extend(target_checks)
    all_errors.extend(target_errors)
    all_warnings.extend(target_warnings)

    status = "passed" if not all_errors else "failed"

    return QualityGateResult(
        status=status,
        checks=all_checks,
        errors=all_errors,
        warnings=all_warnings,
    )


def run_quality_gate(datasets: ModelReadyDatasets) -> QualityGateResult:
    """
    Chạy quality gate cho cả linear và tree branch.

    Nếu có bất kỳ error nào thì status = failed.
    """

    linear_result = check_branch_quality(datasets.linear)
    tree_result = check_branch_quality(datasets.tree)

    all_checks = linear_result.checks + tree_result.checks
    all_errors = linear_result.errors + tree_result.errors
    all_warnings = linear_result.warnings + tree_result.warnings

    status = "passed" if not all_errors else "failed"

    return QualityGateResult(
        status=status,
        checks=all_checks,
        errors=all_errors,
        warnings=all_warnings,
    )


# ============================================================
# Summary Helpers
# ============================================================

def summarize_branch(branch: DatasetBranch) -> dict[str, Any]:
    """
    Tạo summary ngắn cho một dataset branch.
    """

    y_train = extract_target(branch.y_train)
    y_valid = extract_target(branch.y_valid)
    y_test = extract_target(branch.y_test)

    return {
        "branch": branch.name,
        "x_train_shape": list(branch.X_train.shape),
        "x_valid_shape": list(branch.X_valid.shape),
        "x_test_shape": list(branch.X_test.shape),
        "feature_count": len(branch.feature_columns),
        "train_positive_rate": float((y_train == 1).mean()),
        "valid_positive_rate": float((y_valid == 1).mean()),
        "test_positive_rate": float((y_test == 1).mean()),
        "y_train_columns": list(branch.y_train.columns),
        "y_valid_columns": list(branch.y_valid.columns),
        "y_test_columns": list(branch.y_test.columns),
    }


def summarize_datasets(datasets: ModelReadyDatasets) -> dict[str, Any]:
    """
    Summary cho cả hai branch.
    """

    return {
        "linear": summarize_branch(datasets.linear),
        "tree": summarize_branch(datasets.tree),
    }

