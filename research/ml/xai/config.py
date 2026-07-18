from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


BATCH_NAME = "Batch G — XAI Evidence Layer"
BATCH_SHORT_NAME = "batch_g_xai_evidence_layer"

PROJECT_ROOT = Path.cwd()


RUN_MODE_EVALUATION = "evaluation"
RUN_MODE_INFERENCE = "inference"

DEFAULT_RUN_MODE = RUN_MODE_EVALUATION
SUPPORTED_RUN_MODES = (
    RUN_MODE_EVALUATION,
    RUN_MODE_INFERENCE,
)


RANDOM_STATE = 42

ID_COLUMN = "SK_ID_CURR"
TARGET_COLUMN = "TARGET"

POSITIVE_CLASS = 1
NEGATIVE_CLASS = 0

POSITIVE_LABEL_TEXT = "high_default_risk"
NEGATIVE_LABEL_TEXT = "low_default_risk"
UNKNOWN_LABEL_TEXT = "unknown_label"

EXPECTED_DATASET_BRANCH = "tree"
EXPECTED_BEST_MODEL_NAME = "hist_gradient_boosting"

DEFAULT_THRESHOLD_FALLBACK = 0.5


EVALUATION_CASE_GROUPS = (
    "top_high_risk",
    "low_risk",
    "true_positive",
    "false_positive",
    "false_negative",
    "near_threshold",
)

INFERENCE_CASE_GROUPS = (
    "top_high_risk",
    "low_risk",
    "near_threshold",
)


@dataclass(frozen=True)
class XAIConfig:
    run_mode: str = DEFAULT_RUN_MODE

    random_state: int = RANDOM_STATE

    cases_per_group: int = 20

    top_k_features: int | None = None

    shap_background_sample_size: int = 200

    shap_debug_case_limit: int = 5

    shap_output_space: str = "probability"

    xai_method: str = "SHAP"

    evaluation_case_groups: tuple[str, ...] = EVALUATION_CASE_GROUPS

    inference_case_groups: tuple[str, ...] = INFERENCE_CASE_GROUPS

    additivity_tolerance: float = 1e-2


XAI_CONFIG = XAIConfig()


BEST_MODEL_PATH = PROJECT_ROOT / "artifacts/models/best_model.joblib"

MODEL_REGISTRY_PATH = PROJECT_ROOT / "ml/registry/model_registry.json"


X_TEST_TREE_PATH = PROJECT_ROOT / "data/processed/model_ready/tree/X_test_tree.parquet"
Y_TEST_TREE_PATH = PROJECT_ROOT / "data/processed/model_ready/tree/y_test.parquet"
MODEL_PREDICTIONS_TEST_PATH = PROJECT_ROOT / "data/reports/model_predictions_test.csv"


X_INFERENCE_TREE_PATH = (
    PROJECT_ROOT
    / "data/processed/model_ready/inference/X_inference_tree.parquet"
)
MODEL_PREDICTIONS_INFERENCE_PATH = (
    PROJECT_ROOT
    / "data/reports/model_predictions_inference.csv"
)


TREE_FEATURE_COLUMNS_PATH = PROJECT_ROOT / "ml/registry/preprocessed_feature_columns_tree.json"
TREE_FEATURE_MAPPING_PATH = PROJECT_ROOT / "ml/registry/preprocessed_feature_mapping_tree.json"

FEATURE_REGISTRY_CSV_PATH = PROJECT_ROOT / "ml/registry/feature_registry.csv"
FEATURE_REGISTRY_YAML_PATH = PROJECT_ROOT / "ml/registry/feature_registry.yaml"
CONCEPT_REGISTRY_PATH = PROJECT_ROOT / "ml/registry/concept_registry.yaml"

MODEL_METRICS_SUMMARY_PATH = PROJECT_ROOT / "data/reports/model_metrics_summary.csv"
MODEL_THRESHOLD_ANALYSIS_VALID_PATH = PROJECT_ROOT / "data/reports/model_threshold_analysis_valid.csv"
MODEL_FEATURE_IMPORTANCE_PATH = PROJECT_ROOT / "data/reports/model_feature_importance.csv"
MODEL_TRAINING_MANIFEST_PATH = PROJECT_ROOT / "data/manifests/model_training_manifest.json"


XAI_OUTPUT_DIR = PROJECT_ROOT / "data/reports/xai"
XAI_MANIFEST_DIR = PROJECT_ROOT / "data/manifests"

XAI_SELECTED_CASES_CSV_PATH = XAI_OUTPUT_DIR / "xai_selected_cases.csv"
XAI_LOCAL_EVIDENCE_JSONL_PATH = XAI_OUTPUT_DIR / "xai_local_evidence.jsonl"
XAI_EVIDENCE_SUMMARY_CSV_PATH = XAI_OUTPUT_DIR / "xai_evidence_summary.csv"
XAI_EVIDENCE_MANIFEST_PATH = XAI_MANIFEST_DIR / "xai_evidence_manifest.json"
XAI_QUALITY_REPORT_JSON_PATH = XAI_OUTPUT_DIR / "xai_quality_report.json"


def validate_run_mode(run_mode: str | None = None) -> str:
    if run_mode is None:
        run_mode = XAI_CONFIG.run_mode

    if run_mode not in SUPPORTED_RUN_MODES:
        raise ValueError(
            f"Unsupported run_mode={run_mode!r}. "
            f"Supported modes are: {SUPPORTED_RUN_MODES}"
        )

    return run_mode


def get_case_groups_for_mode(run_mode: str | None = None) -> tuple[str, ...]:
    run_mode = validate_run_mode(run_mode)

    if run_mode == RUN_MODE_EVALUATION:
        return XAI_CONFIG.evaluation_case_groups

    if run_mode == RUN_MODE_INFERENCE:
        return XAI_CONFIG.inference_case_groups

    raise ValueError(f"Unsupported run_mode: {run_mode}")


def mode_has_ground_truth(run_mode: str | None = None) -> bool:
    run_mode = validate_run_mode(run_mode)
    return run_mode == RUN_MODE_EVALUATION


def get_x_data_path_for_mode(run_mode: str | None = None) -> Path:
    run_mode = validate_run_mode(run_mode)

    if run_mode == RUN_MODE_EVALUATION:
        return X_TEST_TREE_PATH

    if run_mode == RUN_MODE_INFERENCE:
        return X_INFERENCE_TREE_PATH

    raise ValueError(f"Unsupported run_mode: {run_mode}")


def get_y_data_path_for_mode(run_mode: str | None = None) -> Path | None:
    run_mode = validate_run_mode(run_mode)

    if run_mode == RUN_MODE_EVALUATION:
        return Y_TEST_TREE_PATH

    if run_mode == RUN_MODE_INFERENCE:
        return None

    raise ValueError(f"Unsupported run_mode: {run_mode}")


def get_predictions_path_for_mode(run_mode: str | None = None) -> Path:
    run_mode = validate_run_mode(run_mode)

    if run_mode == RUN_MODE_EVALUATION:
        return MODEL_PREDICTIONS_TEST_PATH

    if run_mode == RUN_MODE_INFERENCE:
        return MODEL_PREDICTIONS_INFERENCE_PATH

    raise ValueError(f"Unsupported run_mode: {run_mode}")


def get_required_input_paths(run_mode: str | None = None) -> dict[str, Path]:
    run_mode = validate_run_mode(run_mode)

    common_paths = {
        "best_model": BEST_MODEL_PATH,
        "model_registry": MODEL_REGISTRY_PATH,
        "tree_feature_columns": TREE_FEATURE_COLUMNS_PATH,
        "tree_feature_mapping": TREE_FEATURE_MAPPING_PATH,
        "feature_registry_csv": FEATURE_REGISTRY_CSV_PATH,
        "concept_registry": CONCEPT_REGISTRY_PATH,
    }

    if run_mode == RUN_MODE_EVALUATION:
        return {
            **common_paths,
            "x_tree": X_TEST_TREE_PATH,
            "y": Y_TEST_TREE_PATH,
            "model_predictions": MODEL_PREDICTIONS_TEST_PATH,
        }

    if run_mode == RUN_MODE_INFERENCE:
        return {
            **common_paths,
            "x_tree": X_INFERENCE_TREE_PATH,
            "model_predictions": MODEL_PREDICTIONS_INFERENCE_PATH,
        }

    raise ValueError(f"Unsupported run_mode: {run_mode}")


def get_optional_input_paths() -> dict[str, Path]:
    return {
        "feature_registry_yaml": FEATURE_REGISTRY_YAML_PATH,
        "model_metrics_summary": MODEL_METRICS_SUMMARY_PATH,
        "model_threshold_analysis_valid": MODEL_THRESHOLD_ANALYSIS_VALID_PATH,
        "model_feature_importance": MODEL_FEATURE_IMPORTANCE_PATH,
        "model_training_manifest": MODEL_TRAINING_MANIFEST_PATH,
    }


def get_output_paths() -> dict[str, Path]:
    return {
        "xai_selected_cases_csv": XAI_SELECTED_CASES_CSV_PATH,
        "xai_local_evidence_jsonl": XAI_LOCAL_EVIDENCE_JSONL_PATH,
        "xai_evidence_summary_csv": XAI_EVIDENCE_SUMMARY_CSV_PATH,
        "xai_evidence_manifest": XAI_EVIDENCE_MANIFEST_PATH,
        "xai_quality_report_json": XAI_QUALITY_REPORT_JSON_PATH,
    }


def ensure_output_dirs() -> None:
    XAI_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    XAI_MANIFEST_DIR.mkdir(parents=True, exist_ok=True)


def find_missing_required_inputs(
    run_mode: str | None = None,
) -> dict[str, Path]:
    return {
        name: path
        for name, path in get_required_input_paths(run_mode).items()
        if not path.exists()
    }


def validate_required_inputs_exist(run_mode: str | None = None) -> None:
    run_mode = validate_run_mode(run_mode)
    missing = find_missing_required_inputs(run_mode)

    if missing:
        missing_lines = "\n".join(
            f"- {name}: {path}" for name, path in missing.items()
        )
        raise FileNotFoundError(
            f"Batch G cannot start in run_mode={run_mode!r} "
            "because required input files are missing:\n"
            f"{missing_lines}"
        )


def get_config_summary(run_mode: str | None = None) -> dict[str, object]:
    run_mode = validate_run_mode(run_mode)

    return {
        "batch_name": BATCH_NAME,
        "batch_short_name": BATCH_SHORT_NAME,
        "project_root": str(PROJECT_ROOT),
        "run_mode": run_mode,
        "has_ground_truth": mode_has_ground_truth(run_mode),
        "supported_run_modes": list(SUPPORTED_RUN_MODES),
        "expected_best_model_name": EXPECTED_BEST_MODEL_NAME,
        "expected_dataset_branch": EXPECTED_DATASET_BRANCH,
        "id_column": ID_COLUMN,
        "target_column": TARGET_COLUMN,
        "positive_class": POSITIVE_CLASS,
        "negative_class": NEGATIVE_CLASS,
        "positive_label_text": POSITIVE_LABEL_TEXT,
        "negative_label_text": NEGATIVE_LABEL_TEXT,
        "unknown_label_text": UNKNOWN_LABEL_TEXT,
        "default_threshold_fallback": DEFAULT_THRESHOLD_FALLBACK,
        "xai_config": {
            "random_state": XAI_CONFIG.random_state,
            "cases_per_group": XAI_CONFIG.cases_per_group,
            "top_k_features": XAI_CONFIG.top_k_features,
            "shap_background_sample_size": XAI_CONFIG.shap_background_sample_size,
            "shap_debug_case_limit": XAI_CONFIG.shap_debug_case_limit,
            "shap_output_space": XAI_CONFIG.shap_output_space,
            "xai_method": XAI_CONFIG.xai_method,
            "case_groups": list(get_case_groups_for_mode(run_mode)),
            "evaluation_case_groups": list(XAI_CONFIG.evaluation_case_groups),
            "inference_case_groups": list(XAI_CONFIG.inference_case_groups),
            "additivity_tolerance": XAI_CONFIG.additivity_tolerance,
        },
        "mode_paths": {
            "x_data_path": str(get_x_data_path_for_mode(run_mode)),
            "y_data_path": (
                None
                if get_y_data_path_for_mode(run_mode) is None
                else str(get_y_data_path_for_mode(run_mode))
            ),
            "predictions_path": str(get_predictions_path_for_mode(run_mode)),
        },
        "required_input_paths": {
            name: str(path)
            for name, path in get_required_input_paths(run_mode).items()
        },
        "optional_input_paths": {
            name: str(path)
            for name, path in get_optional_input_paths().items()
        },
        "output_paths": {
            name: str(path)
            for name, path in get_output_paths().items()
        },
    }


__all__ = [
    "BATCH_NAME",
    "BATCH_SHORT_NAME",
    "PROJECT_ROOT",
    "RUN_MODE_EVALUATION",
    "RUN_MODE_INFERENCE",
    "DEFAULT_RUN_MODE",
    "SUPPORTED_RUN_MODES",
    "RANDOM_STATE",
    "ID_COLUMN",
    "TARGET_COLUMN",
    "POSITIVE_CLASS",
    "NEGATIVE_CLASS",
    "POSITIVE_LABEL_TEXT",
    "NEGATIVE_LABEL_TEXT",
    "UNKNOWN_LABEL_TEXT",
    "EXPECTED_DATASET_BRANCH",
    "EXPECTED_BEST_MODEL_NAME",
    "DEFAULT_THRESHOLD_FALLBACK",
    "EVALUATION_CASE_GROUPS",
    "INFERENCE_CASE_GROUPS",
    "XAIConfig",
    "XAI_CONFIG",
    "BEST_MODEL_PATH",
    "MODEL_REGISTRY_PATH",
    "X_TEST_TREE_PATH",
    "Y_TEST_TREE_PATH",
    "MODEL_PREDICTIONS_TEST_PATH",
    "X_INFERENCE_TREE_PATH",
    "MODEL_PREDICTIONS_INFERENCE_PATH",
    "TREE_FEATURE_COLUMNS_PATH",
    "TREE_FEATURE_MAPPING_PATH",
    "FEATURE_REGISTRY_CSV_PATH",
    "FEATURE_REGISTRY_YAML_PATH",
    "CONCEPT_REGISTRY_PATH",
    "MODEL_METRICS_SUMMARY_PATH",
    "MODEL_THRESHOLD_ANALYSIS_VALID_PATH",
    "MODEL_FEATURE_IMPORTANCE_PATH",
    "MODEL_TRAINING_MANIFEST_PATH",
    "XAI_OUTPUT_DIR",
    "XAI_MANIFEST_DIR",
    "XAI_SELECTED_CASES_CSV_PATH",
    "XAI_LOCAL_EVIDENCE_JSONL_PATH",
    "XAI_EVIDENCE_SUMMARY_CSV_PATH",
    "XAI_EVIDENCE_MANIFEST_PATH",
    "XAI_QUALITY_REPORT_JSON_PATH",
    "validate_run_mode",
    "get_case_groups_for_mode",
    "mode_has_ground_truth",
    "get_x_data_path_for_mode",
    "get_y_data_path_for_mode",
    "get_predictions_path_for_mode",
    "get_required_input_paths",
    "get_optional_input_paths",
    "get_output_paths",
    "ensure_output_dirs",
    "find_missing_required_inputs",
    "validate_required_inputs_exist",
    "get_config_summary",
]