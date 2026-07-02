"""
Schema for Batch I - LLM Explanation Layer.

This schema is shared by:
- v0.1 template generator
- v1.0 future LLM/API generator

Therefore, Batch J can validate explanations without caring whether the
explanation came from a template or an external LLM.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ml.scripts.llm_explanation_layer.config import (
    BATCH_NAME,
    BATCH_SHORT_NAME,
    EXPLANATION_SCHEMA_VERSION,
    GENERATOR_NAME_TEMPLATE,
    GENERATOR_TYPE_TEMPLATE,
    GENERATOR_VERSION,
    USES_EXTERNAL_AI_API,
)


# =============================================================================
# Helpers
# =============================================================================

def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def dataclass_to_dict(obj: Any) -> Any:
    """
    Convert dataclass or nested object into JSON-safe dictionaries/lists.
    """
    if is_dataclass(obj):
        return dataclass_to_dict(asdict(obj))

    if isinstance(obj, dict):
        return {str(k): dataclass_to_dict(v) for k, v in obj.items()}

    if isinstance(obj, list):
        return [dataclass_to_dict(v) for v in obj]

    if isinstance(obj, tuple):
        return [dataclass_to_dict(v) for v in obj]

    return obj


# =============================================================================
# Dataclasses
# =============================================================================

@dataclass
class LLMGeneratorInfo:
    generator_type: str = GENERATOR_TYPE_TEMPLATE
    generator_name: str = GENERATOR_NAME_TEMPLATE
    generator_version: str = GENERATOR_VERSION
    uses_external_ai_api: bool = USES_EXTERNAL_AI_API
    provider: Optional[str] = None
    model_name: Optional[str] = None


@dataclass
class LLMSourceInfo:
    source_ir_id: str
    source_evidence_id: str
    trace_id: str
    source_batch: str
    source_ir_schema_version: Optional[str] = None


@dataclass
class LLMPredictionInfo:
    predicted_label: Optional[str]
    predicted_class: Optional[int]
    probability: Optional[float]
    probability_display: Optional[str]
    probability_percent_display: Optional[str]
    threshold: Optional[float]
    threshold_display: Optional[str]
    threshold_percent_display: Optional[str]
    threshold_comparison: Optional[str]


@dataclass
class LLMSourceContract:
    allowed_claim_ids: List[str]
    forbidden_rule_ids: List[str]
    must_include: List[str]
    must_not: List[str]
    required_output_sections: List[str]


@dataclass
class LLMExplanationSections:
    prediction: str
    main_risk_drivers: str
    risk_reducing_factors: str
    limitations: str


@dataclass
class LLMExplanationPayload:
    language: str
    sections: LLMExplanationSections
    full_text: str


@dataclass
class LLMExplanationQuality:
    status: str
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    section_count: int = 0
    character_count: int = 0
    has_prediction_section: bool = False
    has_main_risk_drivers_section: bool = False
    has_risk_reducing_factors_section: bool = False
    has_limitations_section: bool = False


@dataclass
class LLMExplanationMetadata:
    batch_name: str = BATCH_NAME
    batch_short_name: str = BATCH_SHORT_NAME
    explanation_schema_version: str = EXPLANATION_SCHEMA_VERSION
    created_at: str = field(default_factory=utc_now_iso)


@dataclass
class LLMExplanationRecord:
    explanation_id: str
    source_ir_id: str
    source_evidence_id: str
    trace_id: str
    run_mode: str
    has_ground_truth: bool
    created_at: str
    generator: LLMGeneratorInfo
    source: LLMSourceInfo
    customer: Dict[str, Any]
    model: Dict[str, Any]
    prediction: LLMPredictionInfo
    source_contract: LLMSourceContract
    explanation: LLMExplanationPayload
    quality: LLMExplanationQuality
    metadata: LLMExplanationMetadata


@dataclass
class LLMExplanationBuildResult:
    explanation_records: List[LLMExplanationRecord]
    explanation_record_dicts: List[Dict[str, Any]]
    summary_rows: List[Dict[str, Any]]
    warnings: List[str]
    errors: List[str]