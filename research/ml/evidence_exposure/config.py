from pathlib import Path

DEFAULT_RUN_MODE = "evaluation"

INPUT_IR_PATH = Path("data/reports/explanation_ir_v2/evaluation/explanation_ir_v2.jsonl")
OUTPUT_DIR = Path("data/reports/evidence_exposure/evaluation")
MANIFEST_DIR = Path("data/manifests")

EVIDENCE_PACKAGE_SCHEMA_VERSION = "2.1"
BUILDER_VERSION = "2.1"

S1_TOP_K = 10
S2_TOP_K = 10

S3_COVERAGE_THRESHOLD = 0.60
S3_K_MIN = 3
S3_K_MAX = 10

S4_COVERAGE_THRESHOLD = 0.70
S4_K_MIN = 5
S4_K_MAX = 20

LEVEL_FILE_NAMES = {
    "S0": "prediction_only.jsonl",
    "S1": "raw_shap_fixed_topk.jsonl",
    "S2": "semantic_shap_fixed_topk.jsonl",
    "S3": "adaptive_coverage_constraints.jsonl",
    "S4": "adaptive_entropy_concept_quality.jsonl",
    "S5": "backend_overguided.jsonl",
}

FORBIDDEN_PROMPT_KEYS = {
    "true_label",
    "true_label_text",
    "has_ground_truth",
    "case_type",
    "selection_stratum",
    "prediction_outcome",
    "selection_rank",
    "row_index",
    "SK_ID_CURR",
    "customer_id",
}
