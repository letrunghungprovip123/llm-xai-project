from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from ..common.paths import DEFAULT_PATHS

# ============================================================
# Project Root
# ============================================================
#

PROJECT_ROOT: Final[Path] = DEFAULT_PATHS.project_root


# ============================================================
# Global Model Layer Settings
# ============================================================

BATCH_NAME: Final[str] = "Batch F — Model Training Layer"

TARGET_COLUMN: Final[str] = "TARGET"
ID_COLUMN: Final[str] = "SK_ID_CURR"

RANDOM_STATE: Final[int] = 42
DEFAULT_THRESHOLD: Final[float] = 0.5

MODEL_VERSION: Final[str] = "v1"

POSITIVE_CLASS: Final[int] = 1
NEGATIVE_CLASS: Final[int] = 0

SELECTION_PRIMARY_METRIC: Final[str] = "average_precision"
SELECTION_SECONDARY_METRIC: Final[str] = "roc_auc"
SELECTION_TIEBREAKER_METRIC: Final[str] = "brier_score"


# ============================================================
# Input Directories
# ============================================================

TREE_MODEL_READY_DIR: Final[Path] = (
    PROJECT_ROOT / "data" / "processed" / "model_ready" / "tree"
)

LINEAR_MODEL_READY_DIR: Final[Path] = (
    PROJECT_ROOT / "data" / "processed" / "model_ready" / "linear"
)


# ============================================================
# Tree-ready Dataset Paths
# ============================================================

TREE_X_TRAIN_PATH: Final[Path] = TREE_MODEL_READY_DIR / "X_train_tree.parquet"
TREE_X_VALID_PATH: Final[Path] = TREE_MODEL_READY_DIR / "X_valid_tree.parquet"
TREE_X_TEST_PATH: Final[Path] = TREE_MODEL_READY_DIR / "X_test_tree.parquet"

TREE_Y_TRAIN_PATH: Final[Path] = TREE_MODEL_READY_DIR / "y_train.parquet"
TREE_Y_VALID_PATH: Final[Path] = TREE_MODEL_READY_DIR / "y_valid.parquet"
TREE_Y_TEST_PATH: Final[Path] = TREE_MODEL_READY_DIR / "y_test.parquet"


# ============================================================
# Linear-ready Dataset Paths
# ============================================================

LINEAR_X_TRAIN_PATH: Final[Path] = LINEAR_MODEL_READY_DIR / "X_train_linear.parquet"
LINEAR_X_VALID_PATH: Final[Path] = LINEAR_MODEL_READY_DIR / "X_valid_linear.parquet"
LINEAR_X_TEST_PATH: Final[Path] = LINEAR_MODEL_READY_DIR / "X_test_linear.parquet"

LINEAR_Y_TRAIN_PATH: Final[Path] = LINEAR_MODEL_READY_DIR / "y_train.parquet"
LINEAR_Y_VALID_PATH: Final[Path] = LINEAR_MODEL_READY_DIR / "y_valid.parquet"
LINEAR_Y_TEST_PATH: Final[Path] = LINEAR_MODEL_READY_DIR / "y_test.parquet"


# ============================================================
# Registry Input Paths
# ============================================================

REGISTRY_DIR: Final[Path] = PROJECT_ROOT / "ml" / "registry"

TREE_FEATURE_COLUMNS_PATH: Final[Path] = (
    REGISTRY_DIR / "preprocessed_feature_columns_tree.json"
)

LINEAR_FEATURE_COLUMNS_PATH: Final[Path] = (
    REGISTRY_DIR / "preprocessed_feature_columns_linear.json"
)

TREE_FEATURE_MAPPING_PATH: Final[Path] = (
    REGISTRY_DIR / "preprocessed_feature_mapping_tree.json"
)

LINEAR_FEATURE_MAPPING_PATH: Final[Path] = (
    REGISTRY_DIR / "preprocessed_feature_mapping_linear.json"
)

RAW_FEATURE_REGISTRY_CSV_PATH: Final[Path] = REGISTRY_DIR / "feature_registry.csv"
RAW_FEATURE_REGISTRY_YAML_PATH: Final[Path] = REGISTRY_DIR / "feature_registry.yaml"
CONCEPT_REGISTRY_PATH: Final[Path] = REGISTRY_DIR / "concept_registry.yaml"


# ============================================================
# Output Directories
# ============================================================

MODEL_ARTIFACT_DIR: Final[Path] = PROJECT_ROOT / "artifacts" / "models"
REPORT_DIR: Final[Path] = PROJECT_ROOT / "data" / "reports"
MANIFEST_DIR: Final[Path] = PROJECT_ROOT / "data" / "manifests"


# ============================================================
# Model Artifact Output Paths
# ============================================================

LOGISTIC_REGRESSION_MODEL_PATH: Final[Path] = (
    MODEL_ARTIFACT_DIR / "logistic_regression.joblib"
)

RANDOM_FOREST_MODEL_PATH: Final[Path] = (
    MODEL_ARTIFACT_DIR / "random_forest.joblib"
)

HIST_GRADIENT_BOOSTING_MODEL_PATH: Final[Path] = (
    MODEL_ARTIFACT_DIR / "hist_gradient_boosting.joblib"
)

BEST_MODEL_PATH: Final[Path] = MODEL_ARTIFACT_DIR / "best_model.joblib"


# ============================================================
# Report Output Paths
# ============================================================

MODEL_METRICS_SUMMARY_PATH: Final[Path] = (
    REPORT_DIR / "model_metrics_summary.csv"
)

MODEL_PREDICTIONS_VALID_PATH: Final[Path] = (
    REPORT_DIR / "model_predictions_valid.csv"
)

MODEL_PREDICTIONS_TEST_PATH: Final[Path] = (
    REPORT_DIR / "model_predictions_test.csv"
)

MODEL_THRESHOLD_ANALYSIS_VALID_PATH: Final[Path] = (
    REPORT_DIR / "model_threshold_analysis_valid.csv"
)

MODEL_FEATURE_IMPORTANCE_PATH: Final[Path] = (
    REPORT_DIR / "model_feature_importance.csv"
)

MODEL_TRAINING_REPORT_PATH: Final[Path] = (
    REPORT_DIR / "model_training_report.md"
)


# ============================================================
# Registry / Manifest Output Paths
# ============================================================

MODEL_REGISTRY_PATH: Final[Path] = REGISTRY_DIR / "model_registry.json"

MODEL_TRAINING_MANIFEST_PATH: Final[Path] = (
    MANIFEST_DIR / "model_training_manifest.json"
)


# ============================================================
# Model Configuration
# ============================================================

@dataclass(frozen=True)
class ModelConfig:
    """
    Metadata cấu hình cho một model trong Batch F.

    dataset_branch:
        - "linear": dùng dữ liệu linear-ready
        - "tree": dùng dữ liệu tree-ready

    artifact_path:
        nơi lưu model sau khi train

    enabled:
        cho phép bật/tắt model mà không cần xóa code
    """

    model_name: str
    model_family: str
    dataset_branch: str
    artifact_path: Path
    enabled: bool = True


MODEL_CONFIGS: Final[list[ModelConfig]] = [
    ModelConfig(
        model_name="logistic_regression",
        model_family="linear",
        dataset_branch="linear",
        artifact_path=LOGISTIC_REGRESSION_MODEL_PATH,
        enabled=True,
    ),
    ModelConfig(
        model_name="random_forest",
        model_family="tree",
        dataset_branch="tree",
        artifact_path=RANDOM_FOREST_MODEL_PATH,
        enabled=True,
    ),
    ModelConfig(
        model_name="hist_gradient_boosting",
        model_family="tree_boosting",
        dataset_branch="tree",
        artifact_path=HIST_GRADIENT_BOOSTING_MODEL_PATH,
        enabled=True,
    ),
]


# ============================================================
# Thresholds for Analysis
# ============================================================

THRESHOLDS_FOR_ANALYSIS: Final[list[float]] = [
    0.05,
    0.10,
    0.15,
    0.20,
    0.25,
    0.30,
    0.40,
    0.50,
]


# ============================================================
# Directory Creation
# ============================================================

def ensure_output_dirs() -> None:
    """
    Tạo các output folder cần thiết cho Model Layer.

    Hàm này không tạo input folder.
    Nó chỉ tạo folder output để tránh lỗi khi save model/report.
    """

    MODEL_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# Path Collections for Validation / Manifest
# ============================================================

def get_required_input_paths() -> dict[str, Path]:
    """
    Trả về toàn bộ input path bắt buộc của Model Layer.

    File data_quality.py sẽ dùng hàm này để kiểm tra file nào thiếu.
    Manifest cũng có thể dùng để ghi lại input của Batch F.
    """

    return {
        "tree_x_train": TREE_X_TRAIN_PATH,
        "tree_x_valid": TREE_X_VALID_PATH,
        "tree_x_test": TREE_X_TEST_PATH,
        "tree_y_train": TREE_Y_TRAIN_PATH,
        "tree_y_valid": TREE_Y_VALID_PATH,
        "tree_y_test": TREE_Y_TEST_PATH,
        "linear_x_train": LINEAR_X_TRAIN_PATH,
        "linear_x_valid": LINEAR_X_VALID_PATH,
        "linear_x_test": LINEAR_X_TEST_PATH,
        "linear_y_train": LINEAR_Y_TRAIN_PATH,
        "linear_y_valid": LINEAR_Y_VALID_PATH,
        "linear_y_test": LINEAR_Y_TEST_PATH,
        "tree_feature_columns": TREE_FEATURE_COLUMNS_PATH,
        "linear_feature_columns": LINEAR_FEATURE_COLUMNS_PATH,
        "tree_feature_mapping": TREE_FEATURE_MAPPING_PATH,
        "linear_feature_mapping": LINEAR_FEATURE_MAPPING_PATH,
        "raw_feature_registry_csv": RAW_FEATURE_REGISTRY_CSV_PATH,
        "concept_registry": CONCEPT_REGISTRY_PATH,
    }


def get_output_paths() -> dict[str, Path]:
    """
    Trả về toàn bộ output path chính của Model Layer.

    artifacts.py sẽ dùng để save file.
    Manifest cũng dùng để ghi output của Batch F.
    """

    return {
        "logistic_regression_model": LOGISTIC_REGRESSION_MODEL_PATH,
        "random_forest_model": RANDOM_FOREST_MODEL_PATH,
        "hist_gradient_boosting_model": HIST_GRADIENT_BOOSTING_MODEL_PATH,
        "best_model": BEST_MODEL_PATH,
        "model_metrics_summary": MODEL_METRICS_SUMMARY_PATH,
        "model_predictions_valid": MODEL_PREDICTIONS_VALID_PATH,
        "model_predictions_test": MODEL_PREDICTIONS_TEST_PATH,
        "model_threshold_analysis_valid": MODEL_THRESHOLD_ANALYSIS_VALID_PATH,
        "model_feature_importance": MODEL_FEATURE_IMPORTANCE_PATH,
        "model_training_report": MODEL_TRAINING_REPORT_PATH,
        "model_registry": MODEL_REGISTRY_PATH,
        "model_training_manifest": MODEL_TRAINING_MANIFEST_PATH,
    }
