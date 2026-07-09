"""
Configuration for Batch I - LLM Explanation Layer.

Stage:
    v1.1 template-based explanation generator.

Important:
    This stage does NOT call an external LLM/API.
    It creates a deterministic, schema-compatible explanation baseline from
    Batch H llm_input_contract.
"""

from __future__ import annotations

from pathlib import Path
from typing import List


# =============================================================================
# Project paths
# =============================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[3]


# =============================================================================
# Batch metadata
# =============================================================================

BATCH_NAME = "Batch I - LLM Explanation Layer"
BATCH_SHORT_NAME = "I"
SOURCE_BATCH_NAME = "Batch H - Concept-aware Explanation IR Layer"

EXPLANATION_SCHEMA_VERSION = "v1.1"
GENERATOR_VERSION = "v1.1"

GENERATOR_TYPE_TEMPLATE = "template"
GENERATOR_NAME_TEMPLATE = "deterministic_template_generator"

USES_EXTERNAL_AI_API = False


# =============================================================================
# Run modes
# =============================================================================

RUN_MODE_EVALUATION = "evaluation"
RUN_MODE_INFERENCE = "inference"
RUN_MODE_AUTO = "auto"

DEFAULT_RUN_MODE = RUN_MODE_EVALUATION

SUPPORTED_RUN_MODES: List[str] = [
    RUN_MODE_AUTO,
    RUN_MODE_EVALUATION,
    RUN_MODE_INFERENCE,
]


# =============================================================================
# Default input paths
# =============================================================================

DEFAULT_IR_INPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "reports"
    / "explanation_ir"
    / RUN_MODE_EVALUATION
    / "explanation_ir.jsonl"
)

DEFAULT_IR_INPUT_INFERENCE_PATH = (
    PROJECT_ROOT
    / "data"
    / "reports"
    / "explanation_ir"
    / RUN_MODE_INFERENCE
    / "explanation_ir.jsonl"
)


# =============================================================================
# Output paths
# =============================================================================

def get_output_dir_for_mode(
    run_mode: str,
    generator_type: str = GENERATOR_TYPE_TEMPLATE,
) -> Path:
    return (
        PROJECT_ROOT
        / "data"
        / "reports"
        / "llm_explanations"
        / run_mode
        / generator_type
    )


def get_explanation_jsonl_output_path(
    run_mode: str,
    generator_type: str = GENERATOR_TYPE_TEMPLATE,
) -> Path:
    return get_output_dir_for_mode(run_mode, generator_type) / "llm_explanations.jsonl"


def get_explanation_summary_output_path(
    run_mode: str,
    generator_type: str = GENERATOR_TYPE_TEMPLATE,
) -> Path:
    return get_output_dir_for_mode(run_mode, generator_type) / "llm_explanation_summary.csv"


def get_explanation_quality_report_output_path(
    run_mode: str,
    generator_type: str = GENERATOR_TYPE_TEMPLATE,
) -> Path:
    return get_output_dir_for_mode(run_mode, generator_type) / "llm_explanation_quality_report.json"


def get_explanation_manifest_output_path(
    run_mode: str,
    generator_type: str = GENERATOR_TYPE_TEMPLATE,
) -> Path:
    return (
        PROJECT_ROOT
        / "data"
        / "manifests"
        / f"llm_explanation_manifest_{run_mode}_{generator_type}.json"
    )


def ensure_output_dirs_for_mode(
    run_mode: str,
    generator_type: str = GENERATOR_TYPE_TEMPLATE,
) -> None:
    get_output_dir_for_mode(run_mode, generator_type).mkdir(
        parents=True,
        exist_ok=True,
    )

    get_explanation_manifest_output_path(
        run_mode,
        generator_type,
    ).parent.mkdir(
        parents=True,
        exist_ok=True,
    )


# =============================================================================
# Template generation settings
# =============================================================================

DEFAULT_LANGUAGE = "vi"
DEFAULT_AUDIENCE = "credit_risk_reviewer"
DEFAULT_STYLE = "clear_concise_non_technical"

DEFAULT_MAX_PRIMARY_FEATURES_TO_MENTION = 6
DEFAULT_MAX_SUPPORTING_GROUPS_TO_MENTION = 5
DEFAULT_MAX_RISK_REDUCING_FEATURES_TO_MENTION = 4

PREFERRED_RISK_TERM = "rủi ro gặp khó khăn trong thanh toán"
DEFAULT_AUDIENCE_DESCRIPTION = (
    "credit_risk_reviewer: người xem xét rủi ro tín dụng, cần giải thích rõ, "
    "có số liệu chính, nhưng không quá học thuật."
)


# =============================================================================
# Required explanation sections v1.1
# =============================================================================

SECTION_PREDICTION = "prediction"
SECTION_CONTRIBUTION_OVERVIEW = "contribution_overview"
SECTION_MAIN_RISK_DRIVERS = "main_risk_drivers"
SECTION_SUPPORTING_EVIDENCE_GROUPS = "supporting_evidence_groups"
SECTION_RISK_REDUCING_FACTORS = "risk_reducing_factors"
SECTION_LIMITATIONS = "limitations"

REQUIRED_OUTPUT_SECTIONS = [
    SECTION_PREDICTION,
    SECTION_CONTRIBUTION_OVERVIEW,
    SECTION_MAIN_RISK_DRIVERS,
    SECTION_SUPPORTING_EVIDENCE_GROUPS,
    SECTION_RISK_REDUCING_FACTORS,
    SECTION_LIMITATIONS,
]


# =============================================================================
# Quality/status constants
# =============================================================================

RECORD_STATUS_GENERATED = "generated"
RECORD_STATUS_WARNING = "warning"
RECORD_STATUS_FAILED = "failed"

BATCH_STATUS_PASSED = "PASSED"
BATCH_STATUS_PASSED_WITH_WARNINGS = "PASSED_WITH_WARNINGS"
BATCH_STATUS_FAILED = "FAILED"