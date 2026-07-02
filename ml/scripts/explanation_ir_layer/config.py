"""
Configuration for Batch H - Concept-aware Explanation IR Layer.

This module centralizes:
- batch identity
- run modes
- input/output paths
- SHAP strength thresholds
- top-k settings
- path helpers
- config summaries

Batch H is mode-aware:
- evaluation: uses XAI evidence generated from labeled test data
- inference: uses XAI evidence generated from unlabeled inference data
- auto: infers mode from the input evidence file

Important:
Batch H uses the same IR schema for evaluation and inference.
Mode only affects input path, output path, validation rules, and metadata.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional


# =============================================================================
# Project roots
# =============================================================================

# This file lives at:
#   ml/scripts/explanation_ir_layer/config.py
#
# parents:
#   0 = explanation_ir_layer
#   1 = scripts
#   2 = ml
#   3 = project root
PROJECT_ROOT = Path(__file__).resolve().parents[3]


# =============================================================================
# Batch identity
# =============================================================================

BATCH_NAME = "Batch H - Concept-aware Explanation IR Layer"
BATCH_SHORT_NAME = "H"
SOURCE_BATCH_NAME = "Batch G - XAI Evidence Layer"

IR_SCHEMA_VERSION = "v1.0"
BUILDER_VERSION = "v1"


# =============================================================================
# Run modes
# =============================================================================

RUN_MODE_EVALUATION = "evaluation"
RUN_MODE_INFERENCE = "inference"
RUN_MODE_AUTO = "auto"

SUPPORTED_RUN_MODES = (
    RUN_MODE_EVALUATION,
    RUN_MODE_INFERENCE,
    RUN_MODE_AUTO,
)

DEFAULT_RUN_MODE = RUN_MODE_EVALUATION


# =============================================================================
# Input paths
# =============================================================================

# Current real Batch G output path.
# This is the file you already have after running:
#   python3 -m ml.scripts.xai_layer.run_g_xai_evidence_layer --mode evaluation
DEFAULT_XAI_EVIDENCE_PATH = PROJECT_ROOT / "data/reports/xai/xai_local_evidence.jsonl"

# Future-ready mode-specific paths.
# If Batch G later writes outputs by mode, Batch H can use these paths directly.
XAI_EVIDENCE_PATHS_BY_MODE = {
    RUN_MODE_EVALUATION: DEFAULT_XAI_EVIDENCE_PATH,
    RUN_MODE_INFERENCE: PROJECT_ROOT
    / "data/reports/xai/inference/xai_local_evidence.jsonl",
}


# =============================================================================
# Output paths
# =============================================================================

EXPLANATION_IR_REPORTS_DIR = PROJECT_ROOT / "data/reports/explanation_ir"
MANIFESTS_DIR = PROJECT_ROOT / "data/manifests"


def get_output_dir_for_mode(run_mode: str) -> Path:
    """
    Return the output directory for a resolved mode.

    Example:
        evaluation -> data/reports/explanation_ir/evaluation
        inference  -> data/reports/explanation_ir/inference

    Note:
        auto is not a final output mode. It must be resolved to evaluation or
        inference before saving outputs.
    """
    resolved_mode = validate_resolved_mode(run_mode)
    return EXPLANATION_IR_REPORTS_DIR / resolved_mode


def get_ir_jsonl_output_path(run_mode: str) -> Path:
    """Return explanation_ir.jsonl path for the given resolved mode."""
    return get_output_dir_for_mode(run_mode) / "explanation_ir.jsonl"


def get_ir_summary_output_path(run_mode: str) -> Path:
    """Return explanation_ir_summary.csv path for the given resolved mode."""
    return get_output_dir_for_mode(run_mode) / "explanation_ir_summary.csv"


def get_ir_quality_report_output_path(run_mode: str) -> Path:
    """Return explanation_ir_quality_report.json path for the given resolved mode."""
    return get_output_dir_for_mode(run_mode) / "explanation_ir_quality_report.json"


def get_ir_manifest_output_path(run_mode: str) -> Path:
    """Return explanation_ir manifest path for the given resolved mode."""
    resolved_mode = validate_resolved_mode(run_mode)
    return MANIFESTS_DIR / f"explanation_ir_manifest_{resolved_mode}.json"


# =============================================================================
# Explanation IR build settings
# =============================================================================

# Max number of visible feature factors per direction passed to the LLM contract.
# The full feature_factors list can still contain more factors if available.
DEFAULT_MAX_FEATURE_FACTORS_PER_DIRECTION = 5

# Max number of concept summaries surfaced in the LLM input contract.
DEFAULT_MAX_CONCEPT_SUMMARIES = 5

# SHAP values are in probability space from Batch G.
# These thresholds are used to assign weak/moderate/strong contribution labels.
STRONG_ABS_SHAP_THRESHOLD = 0.10
MODERATE_ABS_SHAP_THRESHOLD = 0.03

# Values very close to zero are treated as neutral.
NEUTRAL_SHAP_EPSILON = 1e-12

# Default target language hint for Batch I.
# Batch H still does not generate final natural-language explanation.
DEFAULT_LLM_TARGET_LANGUAGE = "vi"

# Default audience hint for Batch I.
DEFAULT_LLM_AUDIENCE = "credit_risk_reviewer"

# Default style hint for Batch I.
DEFAULT_LLM_STYLE = "clear_concise_non_technical"


# =============================================================================
# Status constants
# =============================================================================

STATUS_PASSED = "PASSED"
STATUS_PASSED_WITH_WARNINGS = "PASSED_WITH_WARNINGS"
STATUS_FAILED = "FAILED"

RECORD_STATUS_PASSED = "passed"
RECORD_STATUS_WARNING = "warning"
RECORD_STATUS_FAILED = "failed"


# =============================================================================
# Claim and policy constants
# =============================================================================

CLAIM_SCOPE_LOCAL_CASE = "local_case"

FORBIDDEN_RULE_TYPES = (
    "no_certainty",
    "no_real_world_causality",
    "no_unsupported_feature_or_concept",
    "no_direction_reversal",
    "no_unsupported_magnitude",
    "no_sensitive_or_hidden_feature_exposure",
    "no_raw_data_overclaim",
    "no_global_generalization_from_local_explanation",
)


# =============================================================================
# Validation helpers
# =============================================================================

def validate_run_mode(run_mode: Optional[str]) -> str:
    """
    Validate a user-provided run mode.

    Allows:
        evaluation
        inference
        auto

    Returns:
        normalized run_mode string
    """
    mode = (run_mode or DEFAULT_RUN_MODE).strip().lower()

    if mode not in SUPPORTED_RUN_MODES:
        raise ValueError(
            f"Unsupported run_mode={run_mode!r}. "
            f"Supported modes: {SUPPORTED_RUN_MODES}"
        )

    return mode


def validate_resolved_mode(run_mode: str) -> str:
    """
    Validate a final/resolved mode.

    Unlike validate_run_mode(), this does NOT allow auto.
    Output paths and manifests must use a real mode:
        evaluation or inference
    """
    mode = validate_run_mode(run_mode)

    if mode == RUN_MODE_AUTO:
        raise ValueError(
            "run_mode='auto' must be resolved to 'evaluation' or 'inference' "
            "before calling output path helpers."
        )

    return mode


def mode_has_ground_truth(run_mode: str) -> bool:
    """
    Return whether a resolved mode is expected to have ground truth labels.
    """
    mode = validate_resolved_mode(run_mode)
    return mode == RUN_MODE_EVALUATION


def get_default_xai_evidence_path_for_mode(run_mode: str) -> Path:
    """
    Return the default input XAI evidence path for a resolved mode.
    """
    mode = validate_resolved_mode(run_mode)
    return XAI_EVIDENCE_PATHS_BY_MODE[mode]


def resolve_xai_evidence_input_path(
    run_mode: str,
    input_path: Optional[str | Path] = None,
) -> Path:
    """
    Resolve the input XAI evidence path.

    Priority:
        1. explicit input_path
        2. default path for evaluation/inference mode

    For auto mode:
        explicit input_path is recommended.
        If no input_path is provided, use the current real Batch G default path.
    """
    mode = validate_run_mode(run_mode)

    if input_path is not None:
        return Path(input_path).expanduser().resolve()

    if mode == RUN_MODE_AUTO:
        return DEFAULT_XAI_EVIDENCE_PATH

    return get_default_xai_evidence_path_for_mode(mode)


def validate_input_path_exists(path: str | Path) -> Path:
    """
    Validate that an input file exists.
    """
    resolved = Path(path).expanduser().resolve()

    if not resolved.exists():
        raise FileNotFoundError(f"Input file does not exist: {resolved}")

    if not resolved.is_file():
        raise FileNotFoundError(f"Input path is not a file: {resolved}")

    return resolved


def ensure_output_dirs_for_mode(run_mode: str) -> Dict[str, Path]:
    """
    Create output directories for the given resolved mode.
    """
    mode = validate_resolved_mode(run_mode)

    output_dir = get_output_dir_for_mode(mode)
    output_dir.mkdir(parents=True, exist_ok=True)

    MANIFESTS_DIR.mkdir(parents=True, exist_ok=True)

    return {
        "output_dir": output_dir,
        "manifests_dir": MANIFESTS_DIR,
    }


# =============================================================================
# Config summaries
# =============================================================================

def get_output_paths_for_mode(run_mode: str) -> Dict[str, str]:
    """
    Return all output paths for a resolved mode as strings.
    """
    mode = validate_resolved_mode(run_mode)

    return {
        "explanation_ir_jsonl": str(get_ir_jsonl_output_path(mode)),
        "explanation_ir_summary_csv": str(get_ir_summary_output_path(mode)),
        "explanation_ir_quality_report_json": str(
            get_ir_quality_report_output_path(mode)
        ),
        "explanation_ir_manifest_json": str(get_ir_manifest_output_path(mode)),
    }


def get_config_summary(
    run_mode: str = DEFAULT_RUN_MODE,
    input_path: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """
    Return a JSON-serializable config summary.
    """
    mode = validate_run_mode(run_mode)
    resolved_input_path = resolve_xai_evidence_input_path(mode, input_path)

    output_paths: Dict[str, str] | None
    if mode == RUN_MODE_AUTO:
        output_paths = None
    else:
        output_paths = get_output_paths_for_mode(mode)

    return {
        "batch_name": BATCH_NAME,
        "batch_short_name": BATCH_SHORT_NAME,
        "source_batch_name": SOURCE_BATCH_NAME,
        "ir_schema_version": IR_SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        "run_mode": mode,
        "default_run_mode": DEFAULT_RUN_MODE,
        "supported_run_modes": list(SUPPORTED_RUN_MODES),
        "input_xai_evidence_path": str(resolved_input_path),
        "output_paths": output_paths,
        "settings": {
            "max_feature_factors_per_direction": DEFAULT_MAX_FEATURE_FACTORS_PER_DIRECTION,
            "max_concept_summaries": DEFAULT_MAX_CONCEPT_SUMMARIES,
            "strong_abs_shap_threshold": STRONG_ABS_SHAP_THRESHOLD,
            "moderate_abs_shap_threshold": MODERATE_ABS_SHAP_THRESHOLD,
            "neutral_shap_epsilon": NEUTRAL_SHAP_EPSILON,
            "llm_target_language": DEFAULT_LLM_TARGET_LANGUAGE,
            "llm_audience": DEFAULT_LLM_AUDIENCE,
            "llm_style": DEFAULT_LLM_STYLE,
        },
        "forbidden_rule_types": list(FORBIDDEN_RULE_TYPES),
    }


if __name__ == "__main__":
    import json

    print(json.dumps(get_config_summary(), indent=2, ensure_ascii=False))