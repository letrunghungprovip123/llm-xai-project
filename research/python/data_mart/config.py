"""Configuration for the analytical data mart.

Claim artifacts are resolved from one approved release contract instead of a
hard-coded candidate directory. This makes the report lineage explicit and
prevents accidental mixing of Candidate and V4 outputs.
"""

from research.python.common.paths import DEFAULT_PATHS
from research.python.common.research_release import (
    load_claim_measurement_release,
    resolve_official_release_paths,
)

REPO_ROOT = DEFAULT_PATHS.project_root
VALIDATION_ROOT = REPO_ROOT / "data/reports/llm_validation/validation_v1"

CLAIM_MEASUREMENT_RELEASE = load_claim_measurement_release()
_RELEASE_INPUT_PATHS = resolve_official_release_paths(
    CLAIM_MEASUREMENT_RELEASE
)

INPUT_PATHS = {
    "evidence_packages": (
        VALIDATION_ROOT / "canonicalization/evidence_packages_36.jsonl"
    ),
    "generation_index": (
        VALIDATION_ROOT / "canonicalization/generation_index.jsonl"
    ),
    "final_claims": _RELEASE_INPUT_PATHS["final_claims"],
    "validation_results": _RELEASE_INPUT_PATHS["validation_results"],
    "generation_summaries": _RELEASE_INPUT_PATHS["generation_summaries"],
}

OUTPUT_DIR = VALIDATION_ROOT / "analysis/data_mart"

EXPECTED_COUNTS = {
    "cases": 36,
    "models": 3,
    "evidence_levels": 6,
    "evidence_packages": 216,
    "generations": 648,
    "usable_generations": 638,
    "unusable_generations": 10,
    "claims": 14_667,
    "validation_results": 14_667,
    "generation_summaries": 648,
}

EXPECTED_VALIDATION_STATUS_COUNTS = {
    key: int(value)
    for key, value in CLAIM_MEASUREMENT_RELEASE["official"][
        "status_counts"
    ].items()
}

EXPECTED_STRATUM_COUNTS = {
    "top_high_risk": 6,
    "low_risk": 6,
    "true_positive": 6,
    "false_positive": 6,
    "false_negative": 6,
    "near_threshold": 6,
}

EVIDENCE_LEVEL_DEFINITIONS = [
    {
        "evidence_level": "S0",
        "evidence_order": 0,
        "evidence_label": "Prediction-only control",
        "description": (
            "Prediction information without feature-level evidence."
        ),
        "semantic_guidance_level": "none",
        "structural_guidance_level": "low",
        "safe_phrase_available": False,
        "adaptive_selection": False,
        "concept_evidence_available": False,
        "backend_skeleton_available": False,
        "intended_role": "prediction_only_control",
    },
    {
        "evidence_level": "S1",
        "evidence_order": 1,
        "evidence_label": "Raw top-feature evidence",
        "description": (
            "Fixed top-10 SHAP features with raw identifiers and directions."
        ),
        "semantic_guidance_level": "none",
        "structural_guidance_level": "low",
        "safe_phrase_available": False,
        "adaptive_selection": False,
        "concept_evidence_available": False,
        "backend_skeleton_available": False,
        "intended_role": "independent_synthesis_baseline",
    },
    {
        "evidence_level": "S2",
        "evidence_order": 2,
        "evidence_label": "Semantically enriched top features",
        "description": (
            "Fixed top-10 features enriched with display names, concepts, "
            "strength labels, values and safe phrases."
        ),
        "semantic_guidance_level": "high",
        "structural_guidance_level": "low",
        "safe_phrase_available": True,
        "adaptive_selection": False,
        "concept_evidence_available": False,
        "backend_skeleton_available": False,
        "intended_role": "semantic_grounding",
    },
    {
        "evidence_level": "S3",
        "evidence_order": 3,
        "evidence_label": "Adaptive compact evidence",
        "description": (
            "Coverage-aware adaptive feature selection with semantic "
            "enrichment and compact evidence volume."
        ),
        "semantic_guidance_level": "high",
        "structural_guidance_level": "medium",
        "safe_phrase_available": True,
        "adaptive_selection": True,
        "concept_evidence_available": False,
        "backend_skeleton_available": False,
        "intended_role": "adaptive_compact",
    },
    {
        "evidence_level": "S4",
        "evidence_order": 4,
        "evidence_label": "Rich concept-aware evidence",
        "description": (
            "Coverage-aware rich feature evidence with concept grouping and "
            "XAI quality metadata."
        ),
        "semantic_guidance_level": "high",
        "structural_guidance_level": "medium",
        "safe_phrase_available": True,
        "adaptive_selection": True,
        "concept_evidence_available": True,
        "backend_skeleton_available": False,
        "intended_role": "rich_evidence_stress_test",
    },
    {
        "evidence_level": "S5",
        "evidence_order": 5,
        "evidence_label": "Backend-controlled explanation skeleton",
        "description": (
            "Rich evidence plus a backend-defined factor order and narrative "
            "skeleton."
        ),
        "semantic_guidance_level": "high",
        "structural_guidance_level": "high",
        "safe_phrase_available": True,
        "adaptive_selection": True,
        "concept_evidence_available": True,
        "backend_skeleton_available": True,
        "intended_role": "controlled_rendering",
    },
]

MODEL_LABELS = {
    "qwen3_8b": "Qwen3 8B",
    "deepseek_v4_flash": "DeepSeek V4 Flash",
    "phi4_mini_instruct": "Phi-4 Mini Instruct",
}

TABLE_FILE_NAMES = {
    "cases": "cases.csv",
    "models": "models.csv",
    "evidence_levels": "evidence_levels.csv",
    "evidence_packages": "evidence_packages.csv",
    "evidence_items": "evidence_items.csv",
    "generations": "generations.csv",
    "claims": "claims.csv",
}

VALIDATION_FILE_NAME = "data_mart_validation.json"
