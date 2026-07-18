from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from ..common.paths import DEFAULT_PATHS

PROJECT_ROOT = DEFAULT_PATHS.project_root

BATCH_NAME = "Batch H v2 - Quality-aware Explanation IR Layer"
BATCH_SHORT_NAME = "H_v2"
SOURCE_BATCH_NAME = "Batch G - XAI Evidence Layer"
SOURCE_QUALITY_BATCH_NAME = "Batch G+ - XAI Evidence Quality Evaluation"

IR_SCHEMA_VERSION = "v2.0"
BUILDER_VERSION = "v2"

RUN_MODE_EVALUATION = "evaluation"
RUN_MODE_INFERENCE = "inference"
RUN_MODE_AUTO = "auto"

SUPPORTED_RUN_MODES = (
    RUN_MODE_EVALUATION,
    RUN_MODE_INFERENCE,
    RUN_MODE_AUTO,
)

DEFAULT_RUN_MODE = RUN_MODE_EVALUATION

DEFAULT_XAI_EVIDENCE_PATH = PROJECT_ROOT / "data/reports/xai/xai_local_evidence.jsonl"

XAI_EVIDENCE_PATHS_BY_MODE = {
    RUN_MODE_EVALUATION: DEFAULT_XAI_EVIDENCE_PATH,
    RUN_MODE_INFERENCE: PROJECT_ROOT / "data/reports/xai/inference/xai_local_evidence.jsonl",
}

XAI_QUALITY_REPORTS_DIR = PROJECT_ROOT / "data/reports/xai_quality"

DEFAULT_XAI_QUALITY_SUMMARY_PATH = (
    XAI_QUALITY_REPORTS_DIR / "xai_evidence_quality_summary.csv"
)

DEFAULT_XAI_CONCEPT_AGGREGATION_PATH = (
    XAI_QUALITY_REPORTS_DIR / "xai_concept_aggregation_report.csv"
)

DEFAULT_XAI_QUALITY_MANIFEST_PATH = (
    PROJECT_ROOT / "data/manifests/xai_evidence_quality_manifest.json"
)

EXPLANATION_IR_REPORTS_DIR = PROJECT_ROOT / "data/reports/explanation_ir_v2"
MANIFESTS_DIR = PROJECT_ROOT / "data/manifests"

STATUS_PASSED = "PASSED"
STATUS_PASSED_WITH_WARNINGS = "PASSED_WITH_WARNINGS"
STATUS_FAILED = "FAILED"

RECORD_STATUS_PASSED = "passed"
RECORD_STATUS_WARNING = "warning"
RECORD_STATUS_FAILED = "failed"

DEFAULT_LLM_TARGET_LANGUAGE = "vi"
DEFAULT_LLM_AUDIENCE = "credit_risk_reviewer"
DEFAULT_LLM_STYLE = "clear_concise_non_technical"

DEFAULT_TOP_K_FOR_LLM = 10
DEFAULT_AUDIT_TOP_K = 20

DEFAULT_MAX_RISK_FACTORS_PER_DIRECTION = 5
DEFAULT_MAX_CONCEPTS_FOR_LLM = 5

STRONG_ABS_SHAP_THRESHOLD = 0.10
MODERATE_ABS_SHAP_THRESHOLD = 0.03
NEUTRAL_SHAP_EPSILON = 1e-12

S3_COVERAGE_THRESHOLD = 0.60
S4_COVERAGE_THRESHOLD = 0.70

ADAPTIVE_K_MIN = 3
ADAPTIVE_K_MAX_S3 = 10
ADAPTIVE_K_MAX_S4 = 20

LOW_ENTROPY_THRESHOLD = 0.40
HIGH_ENTROPY_THRESHOLD = 0.70

MIN_TOP10_COVERAGE_FOR_READY = 0.50
MAX_ADDITIVITY_ERROR_FOR_READY = 0.01
MAX_CONCEPT_SUM_ERROR_FOR_READY = 1e-8
MAX_UNKNOWN_CONCEPT_SHARE_FOR_READY = 0.05

CLAIM_SCOPE_LOCAL_CASE = "local_case"


def validate_run_mode(run_mode: Optional[str]) -> str:
    mode = (run_mode or DEFAULT_RUN_MODE).strip().lower()

    if mode not in SUPPORTED_RUN_MODES:
        raise ValueError(
            f"Unsupported run_mode={run_mode!r}. "
            f"Supported modes: {SUPPORTED_RUN_MODES}"
        )

    return mode


def validate_resolved_mode(run_mode: str) -> str:
    mode = validate_run_mode(run_mode)

    if mode == RUN_MODE_AUTO:
        raise ValueError("run_mode='auto' must be resolved before output is written.")

    return mode


def mode_has_ground_truth(run_mode: str) -> bool:
    mode = validate_resolved_mode(run_mode)
    return mode == RUN_MODE_EVALUATION


def validate_input_path_exists(path: str | Path) -> Path:
    p = Path(path)

    if not p.exists():
        raise FileNotFoundError(f"Input file does not exist: {p}")

    if not p.is_file():
        raise ValueError(f"Input path is not a file: {p}")

    return p


def resolve_xai_evidence_input_path(
    run_mode: str,
    input_path: Optional[str | Path] = None,
) -> Path:
    if input_path is not None:
        return validate_input_path_exists(input_path)

    mode = validate_run_mode(run_mode)

    if mode == RUN_MODE_AUTO:
        return validate_input_path_exists(DEFAULT_XAI_EVIDENCE_PATH)

    return validate_input_path_exists(XAI_EVIDENCE_PATHS_BY_MODE[mode])


def resolve_optional_input_path(
    path: Optional[str | Path],
    default_path: Path,
) -> Optional[Path]:
    selected = Path(path) if path is not None else default_path

    if selected.exists() and selected.is_file():
        return selected

    return None


def get_output_dir_for_mode(run_mode: str) -> Path:
    mode = validate_resolved_mode(run_mode)
    return EXPLANATION_IR_REPORTS_DIR / mode


def get_ir_jsonl_output_path(run_mode: str) -> Path:
    return get_output_dir_for_mode(run_mode) / "explanation_ir_v2.jsonl"


def get_ir_summary_output_path(run_mode: str) -> Path:
    return get_output_dir_for_mode(run_mode) / "explanation_ir_v2_summary.csv"


def get_ir_quality_report_output_path(run_mode: str) -> Path:
    return get_output_dir_for_mode(run_mode) / "explanation_ir_v2_quality_report.json"


def get_ir_manifest_output_path(run_mode: str) -> Path:
    mode = validate_resolved_mode(run_mode)
    return MANIFESTS_DIR / f"explanation_ir_v2_manifest_{mode}.json"


def ensure_output_dirs_for_mode(run_mode: str) -> None:
    get_output_dir_for_mode(run_mode).mkdir(parents=True, exist_ok=True)
    MANIFESTS_DIR.mkdir(parents=True, exist_ok=True)


def get_output_paths_for_mode(run_mode: str) -> Dict[str, str]:
    return {
        "explanation_ir_v2_jsonl": str(get_ir_jsonl_output_path(run_mode)),
        "explanation_ir_v2_summary_csv": str(get_ir_summary_output_path(run_mode)),
        "explanation_ir_v2_quality_report_json": str(get_ir_quality_report_output_path(run_mode)),
        "explanation_ir_v2_manifest_json": str(get_ir_manifest_output_path(run_mode)),
    }


def get_config_summary(
    run_mode: str = DEFAULT_RUN_MODE,
    input_path: Optional[str | Path] = None,
    xai_quality_summary_path: Optional[str | Path] = None,
    xai_concept_aggregation_path: Optional[str | Path] = None,
    xai_quality_manifest_path: Optional[str | Path] = None,
) -> Dict[str, Any]:
    mode = validate_run_mode(run_mode)

    if mode == RUN_MODE_AUTO:
        output_paths = None
    else:
        output_paths = get_output_paths_for_mode(mode)

    return {
        "batch_name": BATCH_NAME,
        "batch_short_name": BATCH_SHORT_NAME,
        "ir_schema_version": IR_SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        "requested_run_mode": mode,
        "inputs": {
            "xai_local_evidence": str(input_path or XAI_EVIDENCE_PATHS_BY_MODE.get(mode, DEFAULT_XAI_EVIDENCE_PATH)),
            "xai_quality_summary": str(xai_quality_summary_path or DEFAULT_XAI_QUALITY_SUMMARY_PATH),
            "xai_concept_aggregation": str(xai_concept_aggregation_path or DEFAULT_XAI_CONCEPT_AGGREGATION_PATH),
            "xai_quality_manifest": str(xai_quality_manifest_path or DEFAULT_XAI_QUALITY_MANIFEST_PATH),
        },
        "outputs": output_paths,
        "adaptive_selection_contract_defaults": {
            "s3_coverage_threshold": S3_COVERAGE_THRESHOLD,
            "s4_coverage_threshold": S4_COVERAGE_THRESHOLD,
            "k_min": ADAPTIVE_K_MIN,
            "k_max_s3": ADAPTIVE_K_MAX_S3,
            "k_max_s4": ADAPTIVE_K_MAX_S4,
            "low_entropy_threshold": LOW_ENTROPY_THRESHOLD,
            "high_entropy_threshold": HIGH_ENTROPY_THRESHOLD,
            "cosine_redundancy_core_enabled": False,
        },
    }
